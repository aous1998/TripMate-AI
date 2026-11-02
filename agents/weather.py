# -----------------------------------------------------------------------------
# agents/weather.py - the weather specialist.
# No LLM call: it calls the "weather_forecast" MCP tool
# (Open-Meteo, free and keyless, see tools/weather_tool.py).
# -----------------------------------------------------------------------------

from langchain_core.messages import AIMessage

from agents.common import mark_done, run_tool
from state import TravelState


def weather_agent(state: TravelState):
    # `(state.get("trip") or {})` avoids an error when trip is None.
    destination = (state.get("trip") or {}).get("destination")

    if destination:
        weather = run_tool("weather_forecast", location=destination)
    else:
        # Without a destination there is nothing to look up.
        weather = "Weather unavailable: no destination was given."

    return {
        "weather": weather,
        "completed": mark_done(state, "weather_agent"),
        "messages": [AIMessage(content="Weather forecast fetched.")],
    }
