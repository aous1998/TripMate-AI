from langchain_core.messages import HumanMessage, SystemMessage

from agents.common import UNTRUSTED_DATA_RULE, as_data, mark_done, run_tool
from llm import get_llm
from state import TravelState


def local_guide_agent(state: TravelState):
    trip = state.get("trip") or {}
    destination = trip.get("destination")

    if not destination:
        return {
            "local_tips": "Local tips unavailable: no destination was given.",
            "completed": mark_done(state, "local_guide_agent"),
        }

    origin = trip.get("origin")
    query = f"{destination} travel tips entry requirements local transport money etiquette"
    if origin:
        query += f" for travelers from {origin}"

    search_results = run_tool("web_search", query=query)

    prompt = f"""
Write short, practical local tips for a trip to {destination}{f' from {origin}' if origin else ''}.

Use these search results:
{as_data('web_search', search_results, empty='No results.')}

Cover, in a few bullet points each:
1. Entry and visa basics (say that requirements depend on the traveler's nationality and should be checked officially)
2. Getting around (airport transfer, public transport, passes)
3. Money and payments (currency, cards, tipping)
4. Etiquette and safety

Keep it under 250 words.
"""

    response = get_llm().invoke([
        SystemMessage(content=f"You are a knowledgeable local travel guide. {UNTRUSTED_DATA_RULE}"),
        HumanMessage(content=prompt),
    ])

    return {
        "local_tips": response.content,
        "completed": mark_done(state, "local_guide_agent"),
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
