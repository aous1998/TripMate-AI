"""Shared graph state and the typed schemas the supervisor fills in."""

import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field


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


class SupervisorDecision(BaseModel):
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
    llm_calls: int
