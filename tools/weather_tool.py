"""7-day weather forecast from Open-Meteo (free, no API key)."""

import requests

from tools.flight_tool import AIRPORTS, resolve_location_to_iata


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# WMO weather codes used by Open-Meteo.
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
    iata = resolve_location_to_iata(location)
    if iata and iata in AIRPORTS:
        airport = AIRPORTS[iata]
        return airport.get("city") or location, airport["lat"], airport["lon"]

    response = requests.get(GEOCODING_URL, params={"name": location, "count": 1}, timeout=15)
    results = response.json().get("results") or []
    if results:
        return results[0]["name"], results[0]["latitude"], results[0]["longitude"]

    return None


def get_weather_forecast(location: str, days: int = 7) -> str:
    try:
        place = locate(location)
        if not place:
            return f"Weather unavailable: could not find a location for '{location}'."

        name, lat, lon = place
        response = requests.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": min(max(days, 1), 16),
            },
            timeout=15,
        )
        daily = response.json()["daily"]
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        return f"Weather unavailable: {e}"

    lines = [f"Weather forecast for {name} (next {len(daily['time'])} days):"]

    for i, day in enumerate(daily["time"]):
        condition = WEATHER_CODES.get(daily["weather_code"][i], "Unknown")
        low = daily["temperature_2m_min"][i]
        high = daily["temperature_2m_max"][i]
        rain = daily["precipitation_probability_max"][i]
        rain_text = f", {rain}% chance of rain" if rain is not None else ""
        lines.append(f"- {day}: {condition}, {low:.0f}–{high:.0f}°C{rain_text}")

    lines.append(
        "Note: this is the live forecast for the coming days. For trips further ahead, "
        "treat it as an indication and rely on typical seasonal weather."
    )

    return "\n".join(lines)
