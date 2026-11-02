# -----------------------------------------------------------------------------
# agents/responder.py - writes the final answer the user sees.
# Runs after every planned agent has finished. One LLM call that combines all
# results into one well-formatted Markdown answer. The output guardrail then
# checks that answer before it is returned.
# -----------------------------------------------------------------------------

from langchain_core.messages import HumanMessage, SystemMessage

from agents.budget import format_budget
from agents.common import UNTRUSTED_DATA_RULE, as_data, describe_feedback, describe_trip
from llm import get_llm
from state import TravelState


def responder_agent(state: TravelState):
    """Write the final answer from whatever the specialist agents gathered."""
    # Everything the agents found goes into one prompt. Sections whose agent
    # did not run show "Not requested." and the LLM is told to skip them.
    # The budget is a ready-made Markdown table (format_budget), and the prompt
    # tells the LLM to copy its figures exactly instead of inventing new ones.
    final_prompt = f"""
Generate the final travel response for the user.

User Request:
{state['user_query']}

Trip Details:
{describe_trip(state.get('trip'))}

User Change Requests (apply these):
{describe_feedback(state)}

Flights:
{as_data('flights', state.get('flight_results'))}

Hotels:
{as_data('hotels', state.get('hotel_results'))}

Weather:
{as_data('weather', state.get('weather'))}

Local Tips:
{as_data('local_tips', state.get('local_tips'))}

Itinerary:
{as_data('itinerary', state.get('itinerary'))}

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
        SystemMessage(content=f"You are a professional AI travel booking assistant. {UNTRUSTED_DATA_RULE}"),
        HumanMessage(content=final_prompt)
    ])

    # The answer is added as the newest message; output_guardrail reads
    # state["messages"][-1] (the last message) and turns it into final_answer.
    return {
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
