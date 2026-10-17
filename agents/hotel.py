from langchain_core.messages import AIMessage

from agents.common import mark_done, run_tool
from state import TravelState


def hotel_agent(state: TravelState):
    trip = state.get("trip") or {}

    if trip.get("destination"):
        query = f"Best hotels in {trip['destination']}"
    else:
        query = f"Best hotels for {state['user_query']}"

    return {
        "hotel_results": run_tool("web_search", query=query),
        "completed": mark_done(state, "hotel_agent"),
        "messages": [AIMessage(content="Hotel information fetched.")],
    }
