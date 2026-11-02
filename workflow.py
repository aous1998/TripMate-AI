"""Builds the TripMate graph: a supervisor that routes to specialist agents.

    START -> input_guardrail -> supervisor -> one of the six specialists -> supervisor -> ...
                                          \\-> responder -> output_guardrail -> END
    The supervisor also routes to human_review (an interrupt) between research
    and the itinerary. Blocked or off-topic requests go to blocked_response -> END.
"""
# -----------------------------------------------------------------------------
# workflow.py - the "wiring diagram" of the app.
#
# LangGraph vocabulary used below:
#   node              = a Python function that receives the state and returns changes
#   edge              = "after node A, always run node B"
#   conditional edge  = "after node A, call a function that returns the NAME of the next node"
#   START / END       = special names for where a run begins and finishes
#
# Shape of the graph ("hub and spokes"):
#   the supervisor is the hub; every specialist is a spoke that always returns
#   to the hub, and the hub decides which spoke runs next.
# -----------------------------------------------------------------------------

from langchain_core.messages import HumanMessage          # a chat message written by the user
from langgraph.graph import END, START, StateGraph        # the graph builder and its start/end markers

# Every node function the graph uses (one file per agent in agents/).
from agents.budget import budget_agent
from agents.flight import flight_agent
from agents.guardrails import (
    blocked_response,      # fixed polite refusal for blocked requests
    input_guardrail,       # safety check that runs first
    output_guardrail,      # final check on the answer
    route_after_input,     # decides: blocked_response or supervisor
)
from agents.hotel import hotel_agent
from agents.itinerary import itinerary_agent
from agents.local_guide import local_guide_agent
from agents.responder import responder_agent
from agents.review import human_review
from agents.supervisor import route, supervisor_agent
from agents.weather import weather_agent
from state import AGENT_ORDER, TravelState


# The six specialist agents: node name -> function.
# The supervisor can route to any of these.
SPECIALISTS = {
    "flight_agent": flight_agent,
    "hotel_agent": hotel_agent,
    "weather_agent": weather_agent,
    "local_guide_agent": local_guide_agent,
    "itinerary_agent": itinerary_agent,
    "budget_agent": budget_agent,
}

# Safety net for developers: if someone adds an agent here but forgets
# state.AGENT_ORDER (or the other way round), the app refuses to start.
assert list(SPECIALISTS) == AGENT_ORDER, "SPECIALISTS must match state.AGENT_ORDER"


def build_graph() -> StateGraph:
    # Create an empty graph whose shared state has the shape of TravelState.
    graph = StateGraph(TravelState)

    # Register the nodes (name -> function).
    graph.add_node("input_guardrail", input_guardrail)
    graph.add_node("blocked_response", blocked_response)
    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("responder", responder_agent)
    graph.add_node("output_guardrail", output_guardrail)
    graph.add_node("human_review", human_review)
    # After the human review (approved or not), go back to the supervisor.
    graph.add_edge("human_review", "supervisor")

    for name, agent in SPECIALISTS.items():
        graph.add_node(name, agent)
        # Every specialist reports back to the supervisor, which picks the next step.
        graph.add_edge(name, "supervisor")

    # Every run starts with the input guardrail.
    graph.add_edge(START, "input_guardrail")
    # route_after_input() returns "supervisor" or "blocked_response".
    # The list says which node names that function is allowed to return.
    graph.add_conditional_edges("input_guardrail", route_after_input, ["supervisor", "blocked_response"])
    # route() returns state["next_agent"], which the supervisor just set.
    # `*SPECIALISTS` unpacks the six specialist names into the list.
    graph.add_conditional_edges(
        "supervisor", route, [*SPECIALISTS, "human_review", "responder", "blocked_response"],
    )
    # The end of a normal run: responder -> output guardrail -> END.
    graph.add_edge("responder", "output_guardrail")
    graph.add_edge("output_guardrail", END)
    # The end of a blocked run.
    graph.add_edge("blocked_response", END)

    # Return the description; backend.py calls .compile() on it.
    return graph


def new_request_state(user_input: str, review_enabled: bool = False) -> dict:
    """Input for one request. Threads are reused across requests, so every
    per-request field is reset here; messages accumulate as chat history."""
    # Every key of TravelState (state.py) gets a fresh value. If we left a field
    # out, the value from this conversation's PREVIOUS request would still be
    # in the saved state and could leak into the new answer.
    return {
        "messages": [HumanMessage(content=user_input)],  # APPENDED to the chat history (reducer)
        "user_query": user_input,      # the user's text, read by every agent
        "trip": None,                  # filled by the supervisor
        "plan": None,                  # None = "the supervisor has not planned yet"
        "completed": [],               # agents finished so far
        "next_agent": "",              # set by the supervisor on every visit
        "flight_results": "",          # research results, filled by the specialists
        "hotel_results": "",
        "weather": "",
        "local_tips": "",
        "itinerary": "",
        "budget": None,
        "guardrail": None,             # set by input_guardrail / supervisor
        "final_answer": "",            # set by output_guardrail / blocked_response
        "guardrail_notes": [],
        "review_enabled": review_enabled,   # the "review flights & hotels" checkbox
        "feedback": [],                # the user's change requests from the review
        "revisions": 0,                # how many change requests so far
        "llm_calls": 0,                # counter, for information only
    }
