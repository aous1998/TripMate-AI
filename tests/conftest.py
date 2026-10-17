import os

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

# The tool modules read API keys at import time; tests never call the real APIs.
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("AVIATIONSTACK_API_KEY", "test-key")

from llm import set_llm  # noqa: E402
from state import BudgetEstimate, BudgetLine, SupervisorDecision, TripDetails  # noqa: E402
from workflow import build_graph, new_request_state  # noqa: E402


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

    def __init__(self, decision=None, budget=DEFAULT_BUDGET, fail_structured=False, answers=None):
        self.outputs = {SupervisorDecision: decision, BudgetEstimate: budget}
        self.fail_structured = fail_structured
        self.answers = answers or {}  # call number -> text, e.g. {1: "..."}
        self.prompts = []
        self.structured_calls = 0
        self.structured_prompts = []

    def with_structured_output(self, schema):
        llm = self

        class StructuredRunner:
            def invoke(self, messages):
                llm.structured_calls += 1
                llm.structured_prompts.append(messages[-1].content)
                if llm.fail_structured:
                    raise ValueError("model returned no tool call")
                return llm.outputs[schema]

        return StructuredRunner()

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        n = len(self.prompts)
        return AIMessage(content=self.answers.get(n, f"fake answer {n}"))


def decision(agents, is_travel_request=True, **trip):
    return SupervisorDecision(
        is_travel_request=is_travel_request,
        trip=TripDetails(**trip),
        agents=agents,
        reasoning="test",
    )


def run_graph(llm, query, thread_id="t1", checkpointer=None):
    set_llm(llm)
    graph = build_graph().compile(checkpointer=checkpointer or InMemorySaver())
    return graph.invoke(
        new_request_state(query),
        {"configurable": {"thread_id": thread_id}},
    )


@pytest.fixture
def fake_tools(monkeypatch):
    """Replace the MCP tool calls (every agent's only way to reach an API)
    and record the arguments each tool receives."""
    calls = {"search_flights": [], "hotels": [], "guide": [], "weather_forecast": [], "convert_currency": []}

    def fake_call_tool(name, **arguments):
        if name == "web_search":
            # Hotels and local tips both use web search; tell them apart by query.
            kind = "hotels" if arguments["query"].startswith("Best hotels") else "guide"
            calls[kind].append(arguments["query"])
            return "FAKE HOTELS" if kind == "hotels" else "FAKE GUIDE SEARCH"

        calls[name].append(arguments)
        return {
            "search_flights": "FAKE FLIGHTS",
            "weather_forecast": "FAKE WEATHER",
            "convert_currency": "920.0",
        }[name]

    monkeypatch.setattr("tools.mcp_client.call_tool", fake_call_tool)
    return calls


@pytest.fixture(autouse=True)
def reset_llm():
    yield
    set_llm(None)
