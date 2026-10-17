"""Human-in-the-loop review: the graph pauses with interrupt() and resumes with Command."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.review import MAX_REVISIONS, with_review_step
from conftest import FakeLLM, decision
from llm import set_llm
from state import AGENT_ORDER
from workflow import build_graph, new_request_state

RESEARCH = ["flight_agent", "hotel_agent", "weather_agent", "local_guide_agent"]


def start(llm, query, review=True):
    set_llm(llm)
    graph = build_graph().compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "review-test"}}
    return graph, config, graph.invoke(new_request_state(query, review_enabled=review), config)


def answer(graph, config, approved, feedback=""):
    return graph.invoke(Command(resume={"approved": approved, "feedback": feedback}), config)


def full_trip_llm(**trip):
    return FakeLLM(decision(AGENT_ORDER, origin="Berlin", destination="Nice", **trip))


def test_full_trip_pauses_after_research(fake_tools):
    graph, config, result = start(full_trip_llm(), "Plan a week in Nice from Berlin")

    review = result["__interrupt__"][0].value
    assert review["flight_results"] == "FAKE FLIGHTS"
    assert review["hotel_results"] == "FAKE HOTELS"
    assert review["trip"]["destination"] == "Nice"
    assert result["completed"] == RESEARCH
    assert result["itinerary"] == "" and result["budget"] is None


def test_approval_continues_to_itinerary_and_budget(fake_tools):
    graph, config, _ = start(full_trip_llm(), "Plan a week in Nice from Berlin")

    result = answer(graph, config, approved=True)

    assert "__interrupt__" not in result
    assert result["completed"] == RESEARCH + ["human_review", "itinerary_agent", "budget_agent"]
    assert result["final_answer"]


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


def test_reviews_stop_after_max_revisions(fake_tools):
    graph, config, result = start(full_trip_llm(), "Plan a week in Nice from Berlin")

    for i in range(MAX_REVISIONS):
        assert "__interrupt__" in result
        result = answer(graph, config, approved=False, feedback=f"change {i}")

    assert "__interrupt__" not in result
    assert result["revisions"] == MAX_REVISIONS
    assert "budget_agent" in result["completed"]


def test_review_disabled_runs_straight_through(fake_tools):
    _, _, result = start(full_trip_llm(), "Plan a week in Nice from Berlin", review=False)

    assert "__interrupt__" not in result
    assert result["completed"] == AGENT_ORDER


def test_no_review_without_work_that_builds_on_research(fake_tools):
    _, _, result = start(FakeLLM(decision(["hotel_agent"], destination="Nice")), "Hotels in Nice?")

    assert "__interrupt__" not in result
    assert result["completed"] == ["hotel_agent"]


def test_hotel_preferences_shape_the_search(fake_tools):
    llm = FakeLLM(decision(["hotel_agent"], destination="Nice", hotel_preferences="budget, near the beach"))

    start(llm, "Cheap hotels near the beach in Nice", review=False)

    assert fake_tools["hotels"] == ["Best hotels in Nice (budget, near the beach)"]


def test_with_review_step_placement():
    on = {"review_enabled": True, "revisions": 0}

    assert with_review_step(AGENT_ORDER, on) == RESEARCH + ["human_review", "itinerary_agent", "budget_agent"]
    assert with_review_step(["hotel_agent", "budget_agent"], on) == ["hotel_agent", "human_review", "budget_agent"]
    assert with_review_step(["weather_agent", "itinerary_agent"], on) == ["weather_agent", "itinerary_agent"]
    assert with_review_step(AGENT_ORDER, {"review_enabled": False}) == AGENT_ORDER
    assert with_review_step(AGENT_ORDER, {"review_enabled": True, "revisions": MAX_REVISIONS}) == AGENT_ORDER
