import os

import pytest
from langchain_core.messages import AIMessage

# The tool modules read API keys at import time; tests never call the real APIs.
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("AVIATIONSTACK_API_KEY", "test-key")

from llm import set_llm  # noqa: E402


class FakeLLM:
    """Stands in for ChatGroq: returns a fixed supervisor decision and canned text."""

    def __init__(self, decision=None, fail_structured=False):
        self.decision = decision
        self.fail_structured = fail_structured
        self.prompts = []

    def with_structured_output(self, schema):
        llm = self

        class StructuredRunner:
            def invoke(self, messages):
                if llm.fail_structured:
                    raise ValueError("model returned no tool call")
                return llm.decision

        return StructuredRunner()

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        return AIMessage(content=f"fake answer {len(self.prompts)}")


@pytest.fixture
def fake_tools(monkeypatch):
    """Replace the flight and hotel APIs and record the queries they receive."""
    calls = {"flights": [], "hotels": []}

    def fake_flights(query):
        calls["flights"].append(query)
        return "FAKE FLIGHTS"

    def fake_hotels(query):
        calls["hotels"].append(query)
        return "FAKE HOTELS"

    monkeypatch.setattr("agents.flight.search_flights", fake_flights)
    monkeypatch.setattr("agents.hotel.tavily_search", fake_hotels)
    return calls


@pytest.fixture(autouse=True)
def reset_llm():
    yield
    set_llm(None)
