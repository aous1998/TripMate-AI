from langchain_core.messages import AIMessage

from agents.common import mark_done, run_tool
from state import TravelState


def weather_agent(state: TravelState):
    destination = (state.get("trip") or {}).get("destination")

    if destination:
        weather = run_tool("weather_forecast", location=destination)
    else:
        weather = "Weather unavailable: no destination was given."

    return {
        "weather": weather,
        "completed": mark_done(state, "weather_agent"),
        "messages": [AIMessage(content="Weather forecast fetched.")],
    }
