"""Supervisor: extracts typed trip details, plans which agents to run, and routes."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from llm import get_llm
from state import AGENT_ORDER, SupervisorDecision, TravelState, TripDetails


SUPERVISOR_PROMPT = """You are the supervisor of a team of travel-planning agents.
Read the user's request, extract the trip details, and choose which specialist agents are needed.

Agents:
- flight_agent: live flight information between the origin and the destination.
- hotel_agent: hotel and accommodation suggestions at the destination.
- itinerary_agent: a practical day-by-day travel plan.

Choose only the agents the request actually needs. A complete trip plan needs all of them;
a question that is only about hotels needs only hotel_agent.
If the user does not mention a currency, use EUR."""


def supervisor_agent(state: TravelState):
    """Plan once per request, then on every visit route to the next pending agent."""
    update = {}
    plan = state.get("plan")

    if plan is None:
        update = plan_request(state)
        plan = update["plan"]

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
    except Exception as e:
        # Some models handle structured output poorly; running every agent
        # is slower but still answers the request.
        print("Supervisor could not plan, running all agents:", e)
        trip = TripDetails()
        chosen = list(AGENT_ORDER)
        reasoning = "Planning failed, so every agent runs."

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
