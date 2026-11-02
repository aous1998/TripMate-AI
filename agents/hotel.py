# -----------------------------------------------------------------------------
# agents/hotel.py - the hotel specialist.
# No LLM call: it builds a search text and calls the "web_search" MCP tool
# (Tavily web search, see tools/tavily_tool.py).
# -----------------------------------------------------------------------------

from langchain_core.messages import AIMessage

from agents.common import mark_done, run_tool
from state import TravelState


def hotel_agent(state: TravelState):
    trip = state.get("trip") or {}

    if trip.get("destination"):
        # e.g. "Best hotels in Paris" ...
        query = f"Best hotels in {trip['destination']}"
        if trip.get("hotel_preferences"):
            # ... plus the preferences, e.g. "Best hotels in Paris (budget, near the Louvre)".
            query += f" ({trip['hotel_preferences']})"
    else:
        # No destination known: search with the user's own words.
        query = f"Best hotels for {state['user_query']}"

    return {
        "hotel_results": run_tool("web_search", query=query),
        "completed": mark_done(state, "hotel_agent"),
        "messages": [AIMessage(content="Hotel information fetched.")],
    }
