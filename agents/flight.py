from langchain_core.messages import AIMessage

from agents.common import mark_done, run_tool
from state import TravelState


def flight_agent(state: TravelState):
    trip = state.get("trip") or {}

    # The supervisor's extracted route is more reliable than parsing free text.
    if trip.get("origin") and trip.get("destination"):
        query = f"from {trip['origin']} to {trip['destination']}"
    else:
        query = state["user_query"]

    return {
        "flight_results": run_tool("search_flights", query=query, limit=5),
        "completed": mark_done(state, "flight_agent"),
        "messages": [AIMessage(content="Flight results fetched.")],
    }
