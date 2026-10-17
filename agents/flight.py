from langchain_core.messages import AIMessage

from agents.common import mark_done
from state import TravelState
from tools.flight_tool import search_flights


def flight_agent(state: TravelState):
    trip = state.get("trip") or {}

    # The supervisor's extracted route is more reliable than parsing free text.
    if trip.get("origin") and trip.get("destination"):
        query = f"from {trip['origin']} to {trip['destination']}"
    else:
        query = state["user_query"]

    return {
        "flight_results": search_flights(query),
        "completed": mark_done(state, "flight_agent"),
        "messages": [AIMessage(content="Flight results fetched.")],
    }
