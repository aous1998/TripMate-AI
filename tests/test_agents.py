from conftest import FakeLLM
from agents.budget import budget_agent, format_budget, user_budget_in_eur
from agents.weather import weather_agent
from llm import set_llm
from tools import currency_tool, weather_tool


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


def budget_state(**trip):
    return {"trip": trip, "completed": [], "llm_calls": 0}


def test_budget_total_is_computed_from_lines(fake_tools):
    set_llm(FakeLLM())

    result = budget_agent(budget_state(destination="Paris", budget=1000, currency="EUR"))

    budget = result["budget"]
    assert budget["total_eur"] == 1050  # 200 + 600 + 250, not whatever the model claims
    assert budget["budget_eur"] == 1000
    assert budget["within_budget"] is False
    assert result["completed"] == ["budget_agent"]


def test_budget_converts_other_currencies_to_eur(fake_tools):
    amount, note = user_budget_in_eur({"budget": 1000, "currency": "usd"})

    assert amount == 920.0
    assert fake_tools["currency"] == [(1000, "USD", "EUR")]
    assert "1000 USD is about 920 EUR" in note


def test_budget_without_amount_skips_conversion(fake_tools):
    assert user_budget_in_eur({"currency": "USD"}) == (None, "")
    assert fake_tools["currency"] == []


def test_format_budget_flags_over_budget():
    text = format_budget({
        "lines": [{"category": "Flights", "amount_eur": 300, "note": "return"}],
        "total_eur": 300,
        "budget_eur": 250,
        "within_budget": False,
        "assumptions": "Economy fares.",
        "conversion_note": "",
    })

    assert "| Flights | 300 | return |" in text
    assert "| **Total** | **300** | |" in text
    assert "OVER budget" in text


def test_weather_agent_without_destination_skips_tool(fake_tools):
    result = weather_agent({"trip": {}, "completed": []})

    assert fake_tools["weather"] == []
    assert result["weather"].startswith("Weather unavailable")


def test_weather_tool_formats_open_meteo_forecast(monkeypatch):
    requests_made = []

    def fake_get(url, params, timeout):
        requests_made.append((url, params))
        return FakeResponse({"daily": {
            "time": ["2026-10-18", "2026-10-19"],
            "weather_code": [2, 63],
            "temperature_2m_min": [8.4, 9.6],
            "temperature_2m_max": [15.2, 13.9],
            "precipitation_probability_max": [10, 80],
        }})

    monkeypatch.setattr(weather_tool.requests, "get", fake_get)

    text = weather_tool.get_weather_forecast("Paris")

    # Paris resolves through the airport table, so only the forecast is requested.
    assert len(requests_made) == 1
    assert requests_made[0][1]["latitude"] == 49.0128
    assert "Weather forecast for Paris (next 2 days):" in text
    assert "- 2026-10-18: Partly cloudy, 8–15°C, 10% chance of rain" in text
    assert "- 2026-10-19: Rain, 10–14°C, 80% chance of rain" in text


def test_currency_tool_uses_ecb_rate(monkeypatch):
    def fake_get(url, params, timeout):
        assert params == {"base": "USD", "symbols": "EUR"}
        return FakeResponse({"rates": {"EUR": 0.9}})

    monkeypatch.setattr(currency_tool.requests, "get", fake_get)

    assert currency_tool.convert_currency(200, "usd") == 180.0
    assert currency_tool.convert_currency(50, "EUR", "eur") == 50
