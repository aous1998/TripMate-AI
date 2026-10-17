from langchain_core.messages import HumanMessage, SystemMessage

from agents.budget import format_budget
from agents.common import describe_trip
from llm import get_llm
from state import TravelState


def responder_agent(state: TravelState):
    """Write the final answer from whatever the specialist agents gathered."""
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Trip Details:
{describe_trip(state.get('trip'))}

Flights:
{state.get('flight_results') or 'Not requested.'}

Hotels:
{state.get('hotel_results') or 'Not requested.'}

Weather:
{state.get('weather') or 'Not requested.'}

Local Tips:
{state.get('local_tips') or 'Not requested.'}

Itinerary:
{state.get('itinerary') or 'Not requested.'}

Budget Estimate:
{format_budget(state.get('budget'))}

Format the final answer beautifully using these sections, and skip any section
whose data was not requested:

1. Trip Summary
2. Flight Information
3. Hotel Suggestions
4. Weather
5. Local Tips
6. Day-by-Day Itinerary
7. Estimated Budget
8. Final Recommendations

Important:
- Be clear and practical.
- If a Budget Estimate table is given, use its figures and total exactly; do not invent different totals.
- Show all costs and the estimated budget in euros (EUR) unless the user asks for a different currency.
- Mention that live flight API may not provide ticket prices if pricing is unavailable.
- Keep the response useful for real travel planning.
"""

    response = get_llm().invoke([
        SystemMessage(content="You are a professional AI travel booking assistant."),
        HumanMessage(content=final_prompt)
    ])

    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
