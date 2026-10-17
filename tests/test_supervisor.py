from typing import get_args

from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeLLM
from llm import set_llm
from state import AGENT_ORDER, AgentName, SupervisorDecision, TripDetails
from tools.flight_tool import parse_route
from workflow import build_graph, new_request_state


def decision(agents, **trip):
    return SupervisorDecision(trip=TripDetails(**trip), agents=agents, reasoning="test")


def run(llm, query, thread_id="t1", checkpointer=None):
    set_llm(llm)
    graph = build_graph().compile(checkpointer=checkpointer or InMemorySaver())
    return graph.invoke(
        new_request_state(query),
        {"configurable": {"thread_id": thread_id}},
    )


def test_full_trip_runs_every_agent_in_order(fake_tools):
    llm = FakeLLM(decision(
        ["flight_agent", "hotel_agent", "itinerary_agent"],
        origin="Berlin", destination="Paris", duration_days=7, budget=1500,
    ))

    result = run(llm, "Plan 7 days from Berlin to Paris under 1500 euros")

    assert result["completed"] == AGENT_ORDER
    assert result["flight_results"] == "FAKE FLIGHTS"
    assert result["hotel_results"] == "FAKE HOTELS"
    assert result["itinerary"] == "fake answer 1"
    assert result["messages"][-1].content == "fake answer 2"  # responder
    assert result["llm_calls"] == 3  # supervisor, itinerary, responder


def test_agents_use_supervisor_trip_details(fake_tools):
    llm = FakeLLM(decision(
        ["flight_agent", "hotel_agent"], origin="Hamburg", destination="Lisbon",
    ))

    run(llm, "I want to go somewhere sunny, maybe Lisbon, leaving Hamburg")

    assert fake_tools["flights"] == ["from Hamburg to Lisbon"]
    assert fake_tools["hotels"] == ["Best hotels in Lisbon"]


def test_hotel_question_skips_other_agents(fake_tools):
    llm = FakeLLM(decision(["hotel_agent"], destination="Rome"))

    result = run(llm, "Which hotels are good in Rome?")

    assert result["completed"] == ["hotel_agent"]
    assert fake_tools["flights"] == []
    assert result["itinerary"] == ""


def test_plan_follows_agent_order_not_llm_order(fake_tools):
    llm = FakeLLM(decision(["itinerary_agent", "flight_agent"], origin="Munich", destination="Rome"))

    result = run(llm, "Flights and a plan for Rome")

    assert result["completed"] == ["flight_agent", "itinerary_agent"]


def test_no_agents_goes_straight_to_responder(fake_tools):
    llm = FakeLLM(decision([]))

    result = run(llm, "Thanks!")

    assert result["completed"] == []
    assert result["messages"][-1].content == "fake answer 1"


def test_failed_planning_falls_back_to_every_agent(fake_tools):
    llm = FakeLLM(fail_structured=True)
    query = "Plan a trip from Germany to France"

    result = run(llm, query)

    assert result["completed"] == AGENT_ORDER
    assert fake_tools["flights"] == [query]  # no extracted route, so raw query


def test_reused_thread_plans_each_request_fresh(fake_tools):
    checkpointer = InMemorySaver()
    run(FakeLLM(decision(AGENT_ORDER, origin="Berlin", destination="Paris")),
        "Full trip to Paris", checkpointer=checkpointer)

    result = run(FakeLLM(decision(["hotel_agent"], destination="Nice")),
                 "Now just hotels in Nice", checkpointer=checkpointer)

    assert result["completed"] == ["hotel_agent"]
    assert result["flight_results"] == ""


def test_agent_name_schema_matches_agent_order():
    assert list(get_args(AgentName)) == AGENT_ORDER


def test_german_cities_resolve_to_main_airports():
    assert parse_route("from Berlin to Paris") == ("BER", "CDG")
    assert parse_route("from Hamburg to Dubai") == ("HAM", "DXB")
