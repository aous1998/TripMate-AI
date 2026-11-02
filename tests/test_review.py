"""Human-in-the-loop review: the graph pauses with interrupt() and resumes with Command."""

# -----------------------------------------------------------------------------
# tests/test_review.py - tests for agents/review.py (human-in-the-loop).
# The graph runs with an in-memory checkpointer, pauses at interrupt(), and is
# resumed with Command(resume=...) exactly as backend.resume_travel_agent() does.
# -----------------------------------------------------------------------------
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.review import MAX_REVISIONS, with_review_step
from conftest import FakeLLM, decision
from llm import set_llm
from state import AGENT_ORDER
from workflow import build_graph, new_request_state

# The agents that run before the review in a full trip.
RESEARCH = ["flight_agent", "hotel_agent", "weather_agent", "local_guide_agent"]


# Start a request with review switched on (by default). Returns the graph and
# config (needed to resume) and the result of the first run.
def start(llm, query, review=True):
    set_llm(llm)
    graph = build_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "review-test"}}
    return graph, config, graph.invoke(new_request_state(query, review_enabled=review), config)


# Resume the paused graph with the user's answer.
def answer(graph, config, approved, feedback=""):
    return graph.invoke(Command(resume={"approved": approved, "feedback": feedback}), config)


# Fake LLM planning a full trip Berlin -> Nice.
def full_trip_llm(**trip):
    return FakeLLM(decision(AGENT_ORDER, origin="Berlin", destination="Nice", **trip))


# A paused run's result contains "__interrupt__" with the review payload.
def test_full_trip_pauses_after_research(fake_tools):
    graph, config, result = start(full_trip_llm(), "Plan a week in Nice from Berlin")

    review = result["__interrupt__"][0].value
    assert review["flight_results"] == "FAKE FLIGHTS"
    assert review["hotel_results"] == "FAKE HOTELS"
    assert review["trip"]["destination"] == "Nice"
    assert result["completed"] == RESEARCH
    assert result["itinerary"] == "" and result["budget"] is None


# Approve -> the rest of the plan runs and the run finishes.
def test_approval_continues_to_itinerary_and_budget(fake_tools):
    graph, config, _ = start(full_trip_llm(), "Plan a week in Nice from Berlin")

    result = answer(graph, config, approved=True)

    assert "__interrupt__" not in result
    assert result["completed"] == RESEARCH + ["human_review", "itinerary_agent", "budget_agent"]
    assert result["final_answer"]


# Change request -> re-plan with the feedback, research again, pause again.
def test_change_request_replans_and_researches_again(fake_tools):
    llm = full_trip_llm()
    graph, config, _ = start(llm, "Plan a week in Nice from Berlin")

    result = answer(graph, config, approved=False, feedback="cheaper hotels near the beach")

    # The supervisor planned again with the feedback, research re-ran, and we pause again.
    assert "cheaper hotels near the beach" in llm.structured_prompts[1]
    assert len(fake_tools["hotels"]) == 2
    assert result["__interrupt__"][0].value["revision"] == 1

    result = answer(graph, config, approved=True)

    assert result["revisions"] == 1
    assert result["feedback"] == ["cheaper hotels near the beach"]
    assert any("cheaper hotels near the beach" in prompt for prompt in llm.prompts)  # itinerary sees it


# After MAX_REVISIONS change requests, the run finishes without asking again.
def test_reviews_stop_after_max_revisions(fake_tools):
    graph, config, result = start(full_trip_llm(), "Plan a week in Nice from Berlin")

    for i in range(MAX_REVISIONS):
        assert "__interrupt__" in result
        result = answer(graph, config, approved=False, feedback=f"change {i}")

    assert "__interrupt__" not in result
    assert result["revisions"] == MAX_REVISIONS
    assert "budget_agent" in result["completed"]


# Checkbox off -> no pause at all.
def test_review_disabled_runs_straight_through(fake_tools):
    _, _, result = start(full_trip_llm(), "Plan a week in Nice from Berlin", review=False)

    assert "__interrupt__" not in result
    assert result["completed"] == AGENT_ORDER


# Only hotels asked: nothing builds on the research, so no review.
def test_no_review_without_work_that_builds_on_research(fake_tools):
    _, _, result = start(FakeLLM(decision(["hotel_agent"], destination="Nice")), "Hotels in Nice?")

    assert "__interrupt__" not in result
    assert result["completed"] == ["hotel_agent"]


# hotel_preferences from the supervisor end up in the hotel search text.
def test_hotel_preferences_shape_the_search(fake_tools):
    llm = FakeLLM(decision(["hotel_agent"], destination="Nice", hotel_preferences="budget, near the beach"))

    start(llm, "Cheap hotels near the beach in Nice", review=False)

    assert fake_tools["hotels"] == ["Best hotels in Nice (budget, near the beach)"]


# with_review_step() puts human_review in the right place, or leaves the plan alone.
def test_with_review_step_placement():
    on = {"review_enabled": True, "revisions": 0}

    assert with_review_step(AGENT_ORDER, on) == RESEARCH + ["human_review", "itinerary_agent", "budget_agent"]
    assert with_review_step(["hotel_agent", "budget_agent"], on) == ["hotel_agent", "human_review", "budget_agent"]
    assert with_review_step(["weather_agent", "itinerary_agent"], on) == ["weather_agent", "itinerary_agent"]
    assert with_review_step(AGENT_ORDER, {"review_enabled": False}) == AGENT_ORDER
    assert with_review_step(AGENT_ORDER, {"review_enabled": True, "revisions": MAX_REVISIONS}) == AGENT_ORDER
