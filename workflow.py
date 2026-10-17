"""Builds the TripMate graph: a supervisor that routes to specialist agents.

    START -> supervisor -> one of the six specialists -> supervisor -> ...
                       \\-> responder -> END   once every planned agent has run
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.budget import budget_agent
from agents.flight import flight_agent
from agents.hotel import hotel_agent
from agents.itinerary import itinerary_agent
from agents.local_guide import local_guide_agent
from agents.responder import responder_agent
from agents.supervisor import route, supervisor_agent
from agents.weather import weather_agent
from state import AGENT_ORDER, TravelState


SPECIALISTS = {
    "flight_agent": flight_agent,
    "hotel_agent": hotel_agent,
    "weather_agent": weather_agent,
    "local_guide_agent": local_guide_agent,
    "itinerary_agent": itinerary_agent,
    "budget_agent": budget_agent,
}

assert list(SPECIALISTS) == AGENT_ORDER, "SPECIALISTS must match state.AGENT_ORDER"


def build_graph() -> StateGraph:
    graph = StateGraph(TravelState)

    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("responder", responder_agent)

    for name, agent in SPECIALISTS.items():
        graph.add_node(name, agent)
        # Every specialist reports back to the supervisor, which picks the next step.
        graph.add_edge(name, "supervisor")

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route, [*SPECIALISTS, "responder"])
    graph.add_edge("responder", END)

    return graph


def new_request_state(user_input: str) -> dict:
    """Input for one request. Threads are reused across requests, so every
    per-request field is reset here; messages accumulate as chat history."""
    return {
        "messages": [HumanMessage(content=user_input)],
        "user_query": user_input,
        "trip": None,
        "plan": None,
        "completed": [],
        "next_agent": "",
        "flight_results": "",
        "hotel_results": "",
        "weather": "",
        "local_tips": "",
        "itinerary": "",
        "budget": None,
        "llm_calls": 0,
    }
