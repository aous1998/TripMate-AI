from langchain_core.messages import HumanMessage, SystemMessage

from agents.common import describe_trip, mark_done
from llm import get_llm
from state import TravelState


def itinerary_agent(state: TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Trip Details:
{describe_trip(state.get('trip'))}

Flight Results:
{state.get('flight_results') or 'Not requested.'}

Hotel Results:
{state.get('hotel_results') or 'Not requested.'}

Make the itinerary practical, budget-aware, and easy to follow.
Show all costs in euros (EUR) unless the user asks for a different currency.
"""

    response = get_llm().invoke([
        SystemMessage(content="You are an expert travel planner."),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "completed": mark_done(state, "itinerary_agent"),
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
