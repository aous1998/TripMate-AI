"""Supervisor: extracts typed trip details, plans which agents to run, and routes."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from llm import get_llm
from state import AGENT_ORDER, SupervisorDecision, TravelState, TripDetails


SUPERVISOR_PROMPT = """You are the supervisor of a team of travel-planning agents.
Read the user's request, extract the trip details, and choose which specialist agents are needed.

Agents:
- flight_agent: live flight information between the origin and the destination.
- hotel_agent: hotel and accommodation suggestions at the destination.
- weather_agent: the weather forecast at the destination.
- local_guide_agent: entry/visa basics, local transport, money and etiquette tips.
- itinerary_agent: a practical day-by-day travel plan.
- budget_agent: an itemised cost estimate in EUR, checked against the user's budget.

If the request is not about travel, set is_travel_request to false and choose no agents.
Choose only the agents the request actually needs. A complete trip plan needs all of them;
a question that is only about hotels needs only hotel_agent, and a weather question
needs only weather_agent.
If the user does not mention a currency, use EUR."""


def supervisor_agent(state: TravelState):
    """Plan once per request, then on every visit route to the next pending agent."""
    update = {}
    plan = state.get("plan")

    if plan is None:
        update = plan_request(state)
        plan = update["plan"]

    guardrail = update.get("guardrail") or state.get("guardrail") or {}
    if guardrail.get("blocked"):
        update["next_agent"] = "blocked_response"
    else:
        update["next_agent"] = pick_next_agent(plan, state.get("completed", []))
    return update


def plan_request(state: TravelState) -> dict:
    try:
        decision = get_llm().with_structured_output(SupervisorDecision).invoke([
            SystemMessage(content=SUPERVISOR_PROMPT),
            HumanMessage(content=state["user_query"]),
        ])
        trip = decision.trip
        chosen = decision.agents
        reasoning = decision.reasoning
        on_topic = decision.is_travel_request
    except Exception as e:
        # Some models handle structured output poorly; running every agent
        # is slower but still answers the request.
        print("Supervisor could not plan, running all agents:", e)
        trip = TripDetails()
        chosen = list(AGENT_ORDER)
        reasoning = "Planning failed, so every agent runs."
        on_topic = True

    if not on_topic:
        return {
            "trip": trip.model_dump(),
            "plan": [],
            "guardrail": {"blocked": True, "reason": "off_topic"},
            "llm_calls": state.get("llm_calls", 0) + 1,
            "messages": [AIMessage(content=f"Supervisor: not a travel request. {reasoning}")],
        }

    plan = [agent for agent in AGENT_ORDER if agent in chosen]

    return {
        "trip": trip.model_dump(),
        "plan": plan,
        "llm_calls": state.get("llm_calls", 0) + 1,
        "messages": [
            AIMessage(content=f"Supervisor plan: {', '.join(plan) or 'answer directly'}. {reasoning}")
        ],
    }


def pick_next_agent(plan: list[str], completed: list[str]) -> str:
    for agent in plan:
        if agent not in completed:
            return agent
    return "responder"


def route(state: TravelState) -> str:
    return state["next_agent"]
