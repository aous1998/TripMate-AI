# -----------------------------------------------------------------------------
# tests/test_supervisor.py - tests for the supervisor's planning and routing
# (agents/supervisor.py), run through the whole graph with a fake LLM.
# -----------------------------------------------------------------------------
from typing import get_args

from langgraph.checkpoint.memory import InMemorySaver

from conftest import FakeLLM, decision
# `as run` gives the imported helper a shorter name in this file.
from conftest import run_graph as run
from state import AGENT_ORDER, AgentName
from tools.flight_tool import parse_route


# A full trip: all six agents run in AGENT_ORDER, each result lands in its field,
# and exactly 5 LLM calls are made. The fake numbers its free-text answers:
# 1 = local guide, 2 = itinerary, 3 = responder.
def test_full_trip_runs_all_six_agents_in_order(fake_tools):
    llm = FakeLLM(decision(
        AGENT_ORDER, origin="Berlin", destination="Paris", duration_days=7, budget=1500,
    ))

    result = run(llm, "Plan 7 days from Berlin to Paris under 1500 euros")

    assert result["completed"] == AGENT_ORDER
    assert len(AGENT_ORDER) == 6
    assert result["flight_results"] == "FAKE FLIGHTS"
    assert result["hotel_results"] == "FAKE HOTELS"
    assert result["weather"] == "FAKE WEATHER"
    assert result["local_tips"] == "fake answer 1"
    assert result["itinerary"] == "fake answer 2"
    assert result["budget"]["total_eur"] == 1050
    assert result["messages"][-1].content == "fake answer 3"  # responder
    assert result["final_answer"].startswith("fake answer 3")
    # supervisor, local guide, itinerary, budget, responder
    assert result["llm_calls"] == 5


# Agents use the trip details the supervisor extracted, not the raw sentence.
def test_agents_use_supervisor_trip_details(fake_tools):
    llm = FakeLLM(decision(
        ["flight_agent", "hotel_agent", "weather_agent"], origin="Hamburg", destination="Lisbon",
    ))

    run(llm, "I want to go somewhere sunny, maybe Lisbon, leaving Hamburg")

    assert fake_tools["search_flights"] == [{"query": "from Hamburg to Lisbon", "limit": 5}]
    assert fake_tools["hotels"] == ["Best hotels in Lisbon"]
    assert fake_tools["weather_forecast"] == [{"location": "Lisbon"}]


# A hotel-only question runs only the hotel agent.
def test_hotel_question_skips_other_agents(fake_tools):
    llm = FakeLLM(decision(["hotel_agent"], destination="Rome"))

    result = run(llm, "Which hotels are good in Rome?")

    assert result["completed"] == ["hotel_agent"]
    assert fake_tools["search_flights"] == []
    assert fake_tools["weather_forecast"] == []
    assert result["itinerary"] == ""
    assert result["budget"] is None


# Whatever order the LLM lists agents in, they run in AGENT_ORDER.
def test_plan_follows_agent_order_not_llm_order(fake_tools):
    llm = FakeLLM(decision(
        ["budget_agent", "itinerary_agent", "weather_agent", "flight_agent"],
        origin="Munich", destination="Rome",
    ))

    result = run(llm, "Flights, weather, a plan and costs for Rome")

    assert result["completed"] == ["flight_agent", "weather_agent", "itinerary_agent", "budget_agent"]


# An empty plan goes straight to the responder.
def test_no_agents_goes_straight_to_responder(fake_tools):
    llm = FakeLLM(decision([]))

    result = run(llm, "Thanks!")

    assert result["completed"] == []
    assert result["messages"][-1].content == "fake answer 1"


# If structured output fails, every agent runs (and budget reports its own error).
def test_failed_planning_falls_back_to_every_agent(fake_tools):
    llm = FakeLLM(fail_structured=True)
    query = "Plan a trip from Germany to France"

    result = run(llm, query)

    assert result["completed"] == AGENT_ORDER
    assert fake_tools["search_flights"] == [{"query": query, "limit": 5}]  # no extracted route
    assert result["budget"] == {"error": "A structured budget estimate was not available."}


# The same thread used twice: the second request does not see the first one's results.
def test_reused_thread_plans_each_request_fresh(fake_tools):
    checkpointer = InMemorySaver()
    run(FakeLLM(decision(AGENT_ORDER, origin="Berlin", destination="Paris")),
        "Full trip to Paris", checkpointer=checkpointer)

    result = run(FakeLLM(decision(["hotel_agent"], destination="Nice")),
                 "Now just hotels in Nice", checkpointer=checkpointer)

    assert result["completed"] == ["hotel_agent"]
    assert result["flight_results"] == ""
    assert result["budget"] is None


# The Literal type the LLM sees and AGENT_ORDER must list the same agents.
def test_agent_name_schema_matches_agent_order():
    assert list(get_args(AgentName)) == AGENT_ORDER


# German cities map to their main airports in the flight tool.
def test_german_cities_resolve_to_main_airports():
    assert parse_route("from Berlin to Paris") == ("BER", "CDG")
    assert parse_route("from Hamburg to Dubai") == ("HAM", "DXB")
