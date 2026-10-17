from langchain_core.messages import AIMessage

from agents.common import mark_done
from state import TravelState
from tools.tavily_tool import tavily_search


def hotel_agent(state: TravelState):
    trip = state.get("trip") or {}

    if trip.get("destination"):
        query = f"Best hotels in {trip['destination']}"
    else:
        query = f"Best hotels for {state['user_query']}"

    return {
        "hotel_results": tavily_search(query),
        "completed": mark_done(state, "hotel_agent"),
        "messages": [AIMessage(content="Hotel information fetched.")],
    }
