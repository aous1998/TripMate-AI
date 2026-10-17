from langchain_core.messages import AIMessage

from agents.common import mark_done
from state import TravelState
from tools.weather_tool import get_weather_forecast


def weather_agent(state: TravelState):
    destination = (state.get("trip") or {}).get("destination")

    if destination:
        weather = get_weather_forecast(destination)
    else:
        weather = "Weather unavailable: no destination was given."

    return {
        "weather": weather,
        "completed": mark_done(state, "weather_agent"),
        "messages": [AIMessage(content="Weather forecast fetched.")],
    }
