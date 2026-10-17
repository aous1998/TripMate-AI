"""Shared graph state and the typed schemas the supervisor fills in."""

import operator
import re
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field, field_validator


# Specialist agents the supervisor can route to. AGENT_ORDER is the order
# they run in, so each agent sees the results it depends on.
AgentName = Literal[
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "local_guide_agent",
    "itinerary_agent",
    "budget_agent",
]
AGENT_ORDER: list[str] = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "local_guide_agent",
    "itinerary_agent",
    "budget_agent",
]


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TripDetails(BaseModel):
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
    @field_validator("currency", mode="before")
    @classmethod
    def normalise_currency(cls, value):
        code = str(value or "EUR").strip().upper()
        return code if re.fullmatch(r"[A-Z]{3}", code) else "EUR"

    @field_validator("duration_days", mode="before")
    @classmethod
    def clamp_duration(cls, value):
        days = _number(value)
        if days is None or days < 1:
            return None
        return min(int(days), 60)

    @field_validator("budget", mode="before")
    @classmethod
    def positive_budget(cls, value):
        amount = _number(value)
        if amount is None or amount <= 0:
            return None
        return amount

    @field_validator("travelers", mode="before")
    @classmethod
    def clamp_travelers(cls, value):
        return min(max(int(_number(value) or 1), 1), 20)


class SupervisorDecision(BaseModel):
    is_travel_request: bool = Field(
        default=True,
        description="True if the request is about planning or researching travel; "
                    "false for anything unrelated (coding, homework, general chat).",
    )
    trip: TripDetails
    agents: list[AgentName] = Field(
        description="The specialist agents needed to answer this request.",
    )
    reasoning: str = Field(
        description="One short sentence explaining why these agents were chosen.",
    )


class BudgetLine(BaseModel):
    category: str = Field(
        description="Cost category, e.g. Flights, Accommodation, Food, Local transport, Activities.",
    )
    amount_eur: float = Field(
        description="Estimated cost in EUR for the whole trip and all travelers.",
    )

    @field_validator("amount_eur", mode="before")
    @classmethod
    def non_negative(cls, value):
        return max(_number(value) or 0.0, 0.0)
    note: str = Field(
        default="",
        description="Short basis for the estimate, e.g. '6 nights at about 120 EUR'.",
    )


class BudgetEstimate(BaseModel):
    lines: list[BudgetLine] = Field(description="One line per cost category.")
    assumptions: str = Field(description="One or two sentences on the main assumptions.")


class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    trip: dict | None          # TripDetails as a dict, set by the supervisor
    plan: list[str] | None     # agents to run; None until the supervisor has planned
    completed: list[str]       # agents that have finished, in run order
    next_agent: str            # where the supervisor routes next
    flight_results: str
    hotel_results: str
    weather: str
    local_tips: str
    itinerary: str
    budget: dict | None        # set by budget_agent; totals are computed in code
    guardrail: dict | None     # {"blocked": bool, "reason": str}
    review_enabled: bool       # pause for human approval after research
    feedback: list[str]        # change requests from the human review
    revisions: int             # how many times the user asked for changes
    final_answer: str          # the answer after output guardrails
    guardrail_notes: list[str]
    llm_calls: int
