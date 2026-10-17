from langchain_core.messages import HumanMessage, SystemMessage

from agents.common import mark_done
from llm import get_llm
from state import TravelState
from tools.tavily_tool import tavily_search


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

    search_results = tavily_search(query)

    prompt = f"""
Write short, practical local tips for a trip to {destination}{f' from {origin}' if origin else ''}.

Use these search results:
{search_results}

Cover, in a few bullet points each:
1. Entry and visa basics (say that requirements depend on the traveler's nationality and should be checked officially)
2. Getting around (airport transfer, public transport, passes)
3. Money and payments (currency, cards, tipping)
4. Etiquette and safety

Keep it under 250 words.
"""

    response = get_llm().invoke([
        SystemMessage(content="You are a knowledgeable local travel guide."),
        HumanMessage(content=prompt),
    ])

    return {
        "local_tips": response.content,
        "completed": mark_done(state, "local_guide_agent"),
        "messages": [response],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
