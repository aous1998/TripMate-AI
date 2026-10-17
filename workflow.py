"""Builds the TripMate graph: a supervisor that routes to specialist agents.

    START -> input_guardrail -> supervisor -> one of the six specialists -> supervisor -> ...
                                          \\-> responder -> output_guardrail -> END
    The supervisor also routes to human_review (an interrupt) between research
    and the itinerary. Blocked or off-topic requests go to blocked_response -> END.
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.budget import budget_agent
from agents.flight import flight_agent
from agents.guardrails import (
    blocked_response,
    input_guardrail,
    output_guardrail,
    route_after_input,
)
from agents.hotel import hotel_agent
from agents.itinerary import itinerary_agent
from agents.local_guide import local_guide_agent
from agents.responder import responder_agent
from agents.review import human_review
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

    graph.add_node("input_guardrail", input_guardrail)
    graph.add_node("blocked_response", blocked_response)
    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("responder", responder_agent)
    graph.add_node("output_guardrail", output_guardrail)
    graph.add_node("human_review", human_review)
    graph.add_edge("human_review", "supervisor")

    for name, agent in SPECIALISTS.items():
        graph.add_node(name, agent)
        # Every specialist reports back to the supervisor, which picks the next step.
        graph.add_edge(name, "supervisor")

    graph.add_edge(START, "input_guardrail")
    graph.add_conditional_edges("input_guardrail", route_after_input, ["supervisor", "blocked_response"])
    graph.add_conditional_edges(
        "supervisor", route, [*SPECIALISTS, "human_review", "responder", "blocked_response"],
    )
    graph.add_edge("responder", "output_guardrail")
    graph.add_edge("output_guardrail", END)
    graph.add_edge("blocked_response", END)

    return graph


def new_request_state(user_input: str, review_enabled: bool = False) -> dict:
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
        "guardrail": None,
        "final_answer": "",
        "guardrail_notes": [],
        "review_enabled": review_enabled,
        "feedback": [],
        "revisions": 0,
        "llm_calls": 0,
    }
