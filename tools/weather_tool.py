"""7-day weather forecast from Open-Meteo (free, no API key)."""
# -----------------------------------------------------------------------------
# tools/weather_tool.py - daily weather forecast for a city or country.
#
# Two steps:
#   1. locate()  : place name -> (name, latitude, longitude)
#                  first via the airport table in flight_tool.py (fast, offline),
#                  otherwise via Open-Meteo's geocoding search
#   2. forecast  : coordinates -> daily weather from Open-Meteo
# -----------------------------------------------------------------------------

import requests

# Reuse the airport table: every airport has a city and coordinates.
from tools.flight_tool import AIRPORTS, resolve_location_to_iata


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"          # weather data
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"  # place name -> coordinates

# WMO weather codes used by Open-Meteo.
# The API returns a number per day (e.g. 61); this table turns it into words.
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Heavy rain showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def locate(location: str):
    """Return (place name, latitude, longitude) for a city or country, or None."""
    # Countries and cities both resolve to a main airport, which has coordinates.
    # e.g. "France" -> "CDG" -> Paris (49.0, 2.55)
    iata = resolve_location_to_iata(location)
    if iata and iata in AIRPORTS:
        airport = AIRPORTS[iata]
        return airport.get("city") or location, airport["lat"], airport["lon"]

    # Not in the airport table: ask Open-Meteo's geocoder for the best match.
    response = requests.get(GEOCODING_URL, params={"name": location, "count": 1}, timeout=15)
    # `or []` handles answers without a "results" key (nothing found).
    results = response.json().get("results") or []
    if results:
        return results[0]["name"], results[0]["latitude"], results[0]["longitude"]

    # Unknown place.
    return None


def get_weather_forecast(location: str, days: int = 7) -> str:
    try:
        place = locate(location)
        if not place:
            return f"Weather unavailable: could not find a location for '{location}'."

        # Unpack the tuple into three variables.
        name, lat, lon = place
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                # The daily values we want (comma-separated list).
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",          # dates in the destination's local time zone
                # Open-Meteo allows 1..16 days; clamp the request into that range.
                "forecast_days": min(max(days, 1), 16),
            },
            timeout=15,
        )
        # "daily" holds parallel lists: daily["time"][i] belongs to daily["weather_code"][i], ...
        daily = response.json()["daily"]
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        # Network problem or an unexpected answer: return a readable text, never crash.
        return f"Weather unavailable: {e}"

    lines = [f"Weather forecast for {name} (next {len(daily['time'])} days):"]

    # One line per day.
    for i, day in enumerate(daily["time"]):
        condition = WEATHER_CODES.get(daily["weather_code"][i], "Unknown")
        low = daily["temperature_2m_min"][i]
        high = daily["temperature_2m_max"][i]
        rain = daily["precipitation_probability_max"][i]
        # The rain chance can be missing (None) for some days.
        rain_text = f", {rain}% chance of rain" if rain is not None else ""
        # e.g. "- 2026-11-03: Light rain, 8–14°C, 60% chance of rain"
        lines.append(f"- {day}: {condition}, {low:.0f}–{high:.0f}°C{rain_text}")

    # Forecasts only cover the next days, not a trip months away.
    lines.append(
        "Note: this is the live forecast for the coming days. For trips further ahead, "
        "treat it as an indication and rely on typical seasonal weather."
    )

    return "\n".join(lines)
