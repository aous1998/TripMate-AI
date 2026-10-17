import os

import pytest
from langchain_core.messages import AIMessage

# The tool modules read API keys at import time; tests never call the real APIs.
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("AVIATIONSTACK_API_KEY", "test-key")

from llm import set_llm  # noqa: E402
from state import BudgetEstimate, BudgetLine, SupervisorDecision  # noqa: E402


DEFAULT_BUDGET = BudgetEstimate(
    lines=[
        BudgetLine(category="Flights", amount_eur=200, note="return"),
        BudgetLine(category="Accommodation", amount_eur=600, note="6 nights"),
        BudgetLine(category="Food", amount_eur=250),
    ],
    assumptions="Mid-range hotel.",
)


class FakeLLM:
    """Stands in for ChatGroq: canned structured outputs and numbered text answers."""

    def __init__(self, decision=None, budget=DEFAULT_BUDGET, fail_structured=False):
        self.outputs = {SupervisorDecision: decision, BudgetEstimate: budget}
        self.fail_structured = fail_structured
        self.prompts = []

    def with_structured_output(self, schema):
        llm = self

        class StructuredRunner:
            def invoke(self, messages):
                if llm.fail_structured:
                    raise ValueError("model returned no tool call")
                return llm.outputs[schema]

        return StructuredRunner()

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        return AIMessage(content=f"fake answer {len(self.prompts)}")


@pytest.fixture
def fake_tools(monkeypatch):
    """Replace every external API and record the arguments each one receives."""
    calls = {"flights": [], "hotels": [], "weather": [], "guide": [], "currency": []}

    def recorder(name, result):
        def fake(*args, **kwargs):
            calls[name].append(args[0] if len(args) == 1 else args)
            return result
        return fake

    monkeypatch.setattr("agents.flight.search_flights", recorder("flights", "FAKE FLIGHTS"))
    monkeypatch.setattr("agents.hotel.tavily_search", recorder("hotels", "FAKE HOTELS"))
    monkeypatch.setattr("agents.weather.get_weather_forecast", recorder("weather", "FAKE WEATHER"))
    monkeypatch.setattr("agents.local_guide.tavily_search", recorder("guide", "FAKE GUIDE SEARCH"))
    monkeypatch.setattr("agents.budget.convert_currency", recorder("currency", 920.0))
    return calls


@pytest.fixture(autouse=True)
def reset_llm():
    yield
    set_llm(None)
