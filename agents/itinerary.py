from langchain_core.messages import HumanMessage, SystemMessage

from agents.common import UNTRUSTED_DATA_RULE, as_data, describe_feedback, describe_trip, mark_done
from llm import get_llm
from state import TravelState


def itinerary_agent(state: TravelState):
    prompt = f"""
Create a complete travel itinerary.

User Query:
{state['user_query']}

Trip Details:
{describe_trip(state.get('trip'))}

User Change Requests (apply these):
{describe_feedback(state)}

Flight Results:
{as_data('flights', state.get('flight_results'))}

Hotel Results:
{as_data('hotels', state.get('hotel_results'))}

Weather:
{as_data('weather', state.get('weather'))}

Local Tips:
{as_data('local_tips', state.get('local_tips'))}

Make the itinerary practical, budget-aware, and easy to follow.
Plan indoor activities on days with bad weather in the forecast.
Show all costs in euros (EUR) unless the user asks for a different currency.
"""

    response = get_llm().invoke([
        SystemMessage(content=f"You are an expert travel planner. {UNTRUSTED_DATA_RULE}"),
        HumanMessage(content=prompt)
    ])

    return {
        "itinerary": response.content,
        "completed": mark_done(state, "itinerary_agent"),
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
