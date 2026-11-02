# -----------------------------------------------------------------------------
# tests/test_agents.py - unit tests for single agents and tools, called
# directly (without the graph). Real HTTP calls are replaced by fakes.
# -----------------------------------------------------------------------------
from conftest import FakeLLM
from agents.budget import budget_agent, format_budget, user_budget_in_eur
from agents.weather import weather_agent
from llm import set_llm
from tools import currency_tool, weather_tool


# Pretends to be a `requests` response: .json() returns the payload we give it.
class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


# A minimal state containing only what budget_agent reads.
def budget_state(**trip):
    return {"trip": trip, "completed": [], "llm_calls": 0}


# The total is added up in Python from the lines (200 + 600 + 250), and compared with the budget.
def test_budget_total_is_computed_from_lines(fake_tools):
    set_llm(FakeLLM())

    result = budget_agent(budget_state(destination="Paris", budget=1000, currency="EUR"))

    budget = result["budget"]
    assert budget["total_eur"] == 1050  # 200 + 600 + 250, not whatever the model claims
    assert budget["budget_eur"] == 1000
    assert budget["within_budget"] is False
    assert result["completed"] == ["budget_agent"]


# A USD budget is converted through the currency tool (the fake returns 920.0).
def test_budget_converts_other_currencies_to_eur(fake_tools):
    amount, note = user_budget_in_eur({"budget": 1000, "currency": "usd"})

    assert amount == 920.0
    assert fake_tools["convert_currency"] == [
        {"amount": 1000, "from_currency": "USD", "to_currency": "EUR"}
    ]
    assert "1000 USD is about 920 EUR" in note


# No budget amount: no conversion call at all.
def test_budget_without_amount_skips_conversion(fake_tools):
    assert user_budget_in_eur({"currency": "USD"}) == (None, "")
    assert fake_tools["convert_currency"] == []


# The Markdown table and the OVER verdict.
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


# No destination: the weather tool is never called.
def test_weather_agent_without_destination_skips_tool(fake_tools):
    result = weather_agent({"trip": {}, "completed": []})

    assert fake_tools["weather_forecast"] == []
    assert result["weather"].startswith("Weather unavailable")


# A tool that raises becomes a short text note; the agent still finishes.
def test_failed_tool_becomes_a_note_not_a_crash(monkeypatch):
    def broken_call_tool(name, **arguments):
        raise RuntimeError("Tavily key invalid")

    monkeypatch.setattr("tools.mcp_client.call_tool", broken_call_tool)

    result = weather_agent({"trip": {"destination": "Oslo"}, "completed": []})

    assert result["weather"] == "weather_forecast unavailable: Tavily key invalid"
    assert result["completed"] == ["weather_agent"]


# The weather tool turns Open-Meteo's daily lists into readable lines (HTTP faked).
def test_weather_tool_formats_open_meteo_forecast(monkeypatch):
    requests_made = []

        # Record what was requested and return a fixed two-day forecast.
    def fake_get(url, params, timeout):
        requests_made.append((url, params))
        return FakeResponse({"daily": {
            "time": ["2026-10-18", "2026-10-19"],
            "weather_code": [2, 63],
            "temperature_2m_min": [8.4, 9.6],
            "temperature_2m_max": [15.2, 13.9],
            "precipitation_probability_max": [10, 80],
        }})

    # Replace requests.get inside weather_tool for this test only.
    monkeypatch.setattr(weather_tool.requests, "get", fake_get)

    text = weather_tool.get_weather_forecast("Paris")

    # Paris resolves through the airport table, so only the forecast is requested.
    assert len(requests_made) == 1
    assert requests_made[0][1]["latitude"] == 49.0128
    assert "Weather forecast for Paris (next 2 days):" in text
    assert "- 2026-10-18: Partly cloudy, 8–15°C, 10% chance of rain" in text
    assert "- 2026-10-19: Rain, 10–14°C, 80% chance of rain" in text


# Regression test for a real bug: a missing Tavily key used to break ALL tools.
def test_tavily_client_is_created_on_first_use(monkeypatch):
    # The MCP server imports every tool module; a missing Tavily key must not
    # break the import (and with it every other tool).
    import importlib
    from tools import tavily_tool

    # No key in the environment, and stop load_dotenv() from reading the real .env ...
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    # ... then re-import the module, as the MCP server would.
    importlib.reload(tavily_tool)

    assert tavily_tool._client is None


# The currency tool sends the right query and multiplies by the rate; same currency = no request.
def test_currency_tool_uses_ecb_rate(monkeypatch):
    def fake_get(url, params, timeout):
        assert params == {"base": "USD", "symbols": "EUR"}
        return FakeResponse({"rates": {"EUR": 0.9}})

    monkeypatch.setattr(currency_tool.requests, "get", fake_get)

    assert currency_tool.convert_currency(200, "usd") == 180.0
    assert currency_tool.convert_currency(50, "EUR", "eur") == 50
