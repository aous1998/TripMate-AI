# -----------------------------------------------------------------------------
# tests/conftest.py - shared test helpers. pytest loads this file automatically
# before the tests in this folder.
#
# Key idea: the tests never call Groq or any real API. Instead:
#   FakeLLM      replaces the Groq model (via llm.set_llm) and returns canned answers
#   fake_tools   replaces mcp_client.call_tool and records every tool call
# So the tests are fast, free, repeatable, and test OUR logic (routing,
# guardrails, budget maths, review flow) rather than the model.
# -----------------------------------------------------------------------------
import os

import pytest
from langchain_core.messages import AIMessage
# InMemorySaver: a checkpointer that keeps state in memory (no database needed).
from langgraph.checkpoint.memory import InMemorySaver

# The tool modules read API keys at import time; tests never call the real APIs.
os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("AVIATIONSTACK_API_KEY", "test-key")

# These imports come after the os.environ lines on purpose (hence "noqa: E402").
from llm import set_llm  # noqa: E402
from state import BudgetEstimate, BudgetLine, SupervisorDecision, TripDetails  # noqa: E402
from workflow import build_graph, new_request_state  # noqa: E402


# A budget the fake budget LLM returns: 200 + 600 + 250 = 1050 EUR in total.
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

    # decision : the SupervisorDecision to return (which agents, which trip)
    # budget   : the BudgetEstimate to return
    # fail_structured=True simulates a model that cannot do structured output
    # answers  : text for specific free-text calls, by call number
    def __init__(self, decision=None, budget=DEFAULT_BUDGET, fail_structured=False, answers=None):
        # schema class -> the object with_structured_output(schema).invoke() returns
        self.outputs = {SupervisorDecision: decision, BudgetEstimate: budget}
        self.fail_structured = fail_structured
        self.answers = answers or {}  # call number -> text, e.g. {1: "..."}
        self.prompts = []               # every free-text prompt, in order (tests inspect these)
        self.structured_calls = 0       # how many structured calls were made
        self.structured_prompts = []    # their prompts

    # Mimics ChatGroq.with_structured_output(schema): returns an object with .invoke().
    def with_structured_output(self, schema):
        # `llm` lets the inner class reach the FakeLLM (inside it, `self` is the runner).
        llm = self

        class StructuredRunner:
            def invoke(self, messages):
                llm.structured_calls += 1
                llm.structured_prompts.append(messages[-1].content)
                if llm.fail_structured:
                    raise ValueError("model returned no tool call")
                return llm.outputs[schema]

        return StructuredRunner()

    # Mimics a normal free-text call: record the prompt, return an AIMessage.
    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        n = len(self.prompts)
        # e.g. "fake answer 1" for the first call, unless `answers` says otherwise.
        return AIMessage(content=self.answers.get(n, f"fake answer {n}"))


# Helper: build a SupervisorDecision quickly, e.g. decision(["hotel_agent"], destination="Paris").
def decision(agents, is_travel_request=True, **trip):
    return SupervisorDecision(
        is_travel_request=is_travel_request,
        trip=TripDetails(**trip),
        agents=agents,
        reasoning="test",
    )


# Helper: run one whole request through the real graph with the given fake LLM.
# Returns the final state (a dict) so tests can check any field.
def run_graph(llm, query, thread_id="t1", checkpointer=None):
    set_llm(llm)
    graph = build_graph().compile(checkpointer=checkpointer or InMemorySaver())
    return graph.invoke(
        new_request_state(query),
        {"configurable": {"thread_id": thread_id}},
    )


# A pytest fixture: a test that has a parameter called fake_tools gets this return value.
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

    # monkeypatch swaps the real function for the fake one during this test only
    # (pytest puts the original back afterwards).
    monkeypatch.setattr("tools.mcp_client.call_tool", fake_call_tool)
    return calls


# autouse=True: runs around EVERY test. Code after `yield` runs when the test ends.
@pytest.fixture(autouse=True)
def reset_llm():
    yield
    # Forget the fake LLM so the next test starts clean.
    set_llm(None)
