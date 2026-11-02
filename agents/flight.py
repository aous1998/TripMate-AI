# -----------------------------------------------------------------------------
# agents/flight.py - the flight specialist.
# No LLM call: it builds a search text and calls the "search_flights" MCP tool
# (AviationStack live flights, see tools/flight_tool.py).
# -----------------------------------------------------------------------------

from langchain_core.messages import AIMessage

from agents.common import mark_done, run_tool
from state import TravelState


def flight_agent(state: TravelState):
    # The trip details the supervisor extracted (or an empty dict if none).
    trip = state.get("trip") or {}

    # The supervisor's extracted route is more reliable than parsing free text.
    if trip.get("origin") and trip.get("destination"):
        query = f"from {trip['origin']} to {trip['destination']}"   # e.g. "from Berlin to Paris"
    else:
        # Fallback: let the flight tool try to find the cities in the raw request.
        query = state["user_query"]

    # Return only the state keys this agent changes.
    return {
        # Up to 5 flights as text; on failure run_tool returns an error text instead.
        "flight_results": run_tool("search_flights", query=query, limit=5),
        "completed": mark_done(state, "flight_agent"),
        "messages": [AIMessage(content="Flight results fetched.")],
    }
