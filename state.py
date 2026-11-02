"""Shared graph state and the typed schemas the supervisor fills in."""
# -----------------------------------------------------------------------------
# state.py - the data shapes of the app.
#
#   TravelState        : the ONE dictionary every graph node reads and updates
#   TripDetails        : trip facts the supervisor extracts from the user's sentence
#   SupervisorDecision : the supervisor LLM's structured answer
#   BudgetLine/Estimate: the budget LLM's structured answer
#
# The Pydantic classes double as instructions for the LLM: LangChain turns each
# class (field names, types and `description` texts) into a JSON schema that the
# model must fill in. That is what "structured output" means.
# -----------------------------------------------------------------------------

import operator            # operator.add is used as a "reducer" (see TravelState.messages)
import re                  # regular expressions (used to check currency codes)
from typing import Annotated, Literal, TypedDict   # type-hint helpers

from langchain_core.messages import AnyMessage      # any chat message (user, AI, system)
from pydantic import BaseModel, Field, field_validator   # data classes with validation


# Specialist agents the supervisor can route to. AGENT_ORDER is the order
# they run in, so each agent sees the results it depends on.
# `Literal[...]` means "only these exact strings are allowed": the LLM cannot
# invent an agent name, because the schema it receives lists only these.
AgentName = Literal[
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "local_guide_agent",
    "itinerary_agent",
    "budget_agent",
]
# Same names as a normal list, in run order: research first, then the itinerary
# (needs the research), then the budget (needs the itinerary).
AGENT_ORDER: list[str] = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "local_guide_agent",
    "itinerary_agent",
    "budget_agent",
]


def _number(value) -> float | None:
    # Try to turn anything into a number: 5 -> 5.0, "7" -> 7.0.
    # Text like "a week" or None returns None instead of crashing.
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TripDetails(BaseModel):
    # Each field: type, default value, and a description the LLM reads.
    # `str | None` means "a string, or nothing if the user did not say".
    origin: str | None = Field(
        default=None,
        description="Departure city or country, e.g. 'Berlin' or 'Germany'. Null if not mentioned.",
    )
    destination: str | None = Field(
        default=None,
        description="Main destination city or country. Null if unclear.",
    )
    duration_days: int | None = Field(
        default=None,
        description="Trip length in days, if mentioned.",
    )
    budget: float | None = Field(
        default=None,
        description="Total trip budget amount, if mentioned.",
    )
    currency: str = Field(
        default="EUR",
        description="ISO 4217 code of the budget currency, e.g. EUR or USD.",
    )
    travelers: int = Field(
        default=1,
        description="Number of travelers.",
    )
    # default_factory=list gives each object its own new empty list
    # (a plain `default=[]` would be shared between objects).
    interests: list[str] = Field(
        default_factory=list,
        description="Activities or themes the user mentioned, e.g. museums, food, beaches.",
    )
    hotel_preferences: str | None = Field(
        default=None,
        description="Accommodation preferences, e.g. 'budget', 'near the beach', 'boutique'. Null if none.",
    )

    # Guardrails on the LLM's structured output: coerce bad values instead of
    # failing, so one odd field never breaks planning.
    # @field_validator(name, mode="before") runs BEFORE Pydantic checks the type,
    # so we can repair the raw value the LLM sent.
    @field_validator("currency", mode="before")
    @classmethod
    def normalise_currency(cls, value):
        # " usd " -> "USD". Anything that is not exactly 3 letters -> "EUR".
        code = str(value or "EUR").strip().upper()
        return code if re.fullmatch(r"[A-Z]{3}", code) else "EUR"

    @field_validator("duration_days", mode="before")
    @classmethod
    def clamp_duration(cls, value):
        # Not a number, or less than 1 day -> "unknown" (None).
        days = _number(value)
        if days is None or days < 1:
            return None
        # More than 60 days is treated as 60.
        return min(int(days), 60)

    @field_validator("budget", mode="before")
    @classmethod
    def positive_budget(cls, value):
        # A budget of zero or less makes no sense -> "unknown" (None).
        amount = _number(value)
        if amount is None or amount <= 0:
            return None
        return amount

    @field_validator("travelers", mode="before")
    @classmethod
    def clamp_travelers(cls, value):
        # Keep the number of travelers between 1 and 20 (unknown -> 1).
        return min(max(int(_number(value) or 1), 1), 20)


class SupervisorDecision(BaseModel):
    # What the supervisor's ONE LLM call must return.
    is_travel_request: bool = Field(
        default=True,
        description="True if the request is about planning or researching travel; "
                    "false for anything unrelated (coding, homework, general chat).",
    )
    trip: TripDetails                       # the extracted trip facts (nested object)
    agents: list[AgentName] = Field(        # which specialists to run
        description="The specialist agents needed to answer this request.",
    )
    reasoning: str = Field(                 # a short explanation, written to the chat log
        description="One short sentence explaining why these agents were chosen.",
    )


class BudgetLine(BaseModel):
    # One row of the budget table.
    category: str = Field(
        description="Cost category, e.g. Flights, Accommodation, Food, Local transport, Activities.",
    )
    amount_eur: float = Field(
        description="Estimated cost in EUR for the whole trip and all travelers.",
    )

    # A negative or non-numeric cost becomes 0.
    # (The validator sits between two fields; Pydantic still sees all three fields.)
    @field_validator("amount_eur", mode="before")
    @classmethod
    def non_negative(cls, value):
        return max(_number(value) or 0.0, 0.0)
    note: str = Field(
        default="",
        description="Short basis for the estimate, e.g. '6 nights at about 120 EUR'.",
    )


class BudgetEstimate(BaseModel):
    # What the budget agent's LLM call must return. The TOTAL is deliberately
    # not a field: agents/budget.py adds the lines up in Python.
    lines: list[BudgetLine] = Field(description="One line per cost category.")
    assumptions: str = Field(description="One or two sentences on the main assumptions.")


class TravelState(TypedDict):
    # The shared state. A TypedDict is a normal dict with known keys and types.
    # A node returns only the keys it changes; LangGraph merges them in.
    # Normally a returned value REPLACES the old one. For `messages`, the
    # Annotated[..., operator.add] part is a "reducer": returned messages are
    # ADDED to the end of the list (old + new), building a chat history.
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str            # the user's request text
    trip: dict | None          # TripDetails as a dict, set by the supervisor
    plan: list[str] | None     # agents to run; None until the supervisor has planned
    completed: list[str]       # agents that have finished, in run order
    next_agent: str            # where the supervisor routes next
    flight_results: str        # text from flight_agent
    hotel_results: str         # text from hotel_agent
    weather: str               # text from weather_agent
    local_tips: str            # text from local_guide_agent
    itinerary: str             # text from itinerary_agent
    budget: dict | None        # set by budget_agent; totals are computed in code
    guardrail: dict | None     # {"blocked": bool, "reason": str}
    review_enabled: bool       # pause for human approval after research
    feedback: list[str]        # change requests from the human review
    revisions: int             # how many times the user asked for changes
    final_answer: str          # the answer after output guardrails
    guardrail_notes: list[str] # what the output guardrail changed (for information)
    llm_calls: int             # how many LLM calls this request made
