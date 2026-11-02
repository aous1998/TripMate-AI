"""Supervisor: extracts typed trip details, plans which agents to run, and routes."""
# -----------------------------------------------------------------------------
# agents/supervisor.py - the "manager" of the agent team.
#
# The supervisor is visited many times per request, but calls the LLM only ONCE:
#   1st visit : plan_request() asks the LLM for a SupervisorDecision
#               (trip details + which agents are needed) and stores the plan.
#   later     : pick_next_agent() simply returns the first plan entry that is
#               not in "completed" yet - plain Python, no LLM call.
# This "plan once, then route" design is cheaper and more predictable than
# asking the LLM "who's next?" after every step.
# -----------------------------------------------------------------------------

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.review import with_review_step    # adds "human_review" into the plan if enabled
from llm import get_llm
from state import AGENT_ORDER, SupervisorDecision, TravelState, TripDetails


# The system prompt: tells the LLM its role, describes each agent, and gives the
# rules for choosing. The schema of SupervisorDecision (state.py) is sent too.
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
If the user does not mention a currency, use EUR.
If the user has reviewed earlier results and asked for changes, apply them to the trip details
(for example a new origin, a lower budget, or hotel preferences)."""


def supervisor_agent(state: TravelState):
    """Plan once per request, then on every visit route to the next pending agent."""
    update = {}                 # the state changes this visit will return
    plan = state.get("plan")

    # plan is None only on the first visit of a request (see workflow.new_request_state)
    # and after a review with feedback (agents/review.py resets it to re-plan).
    if plan is None:
        update = plan_request(state)
        plan = update["plan"]

    # The off-topic check lives in plan_request; it sets guardrail.blocked.
    # Look at this visit's update first, then the stored state.
    guardrail = update.get("guardrail") or state.get("guardrail") or {}
    if guardrail.get("blocked"):
        update["next_agent"] = "blocked_response"
    else:
        update["next_agent"] = pick_next_agent(plan, state.get("completed", []))
    return update


def plan_request(state: TravelState) -> dict:
    # The one LLM call of the supervisor.
    try:
        # with_structured_output(SupervisorDecision) makes the model answer by
        # "calling a function" whose arguments follow the SupervisorDecision schema;
        # LangChain turns those arguments into a SupervisorDecision object.
        decision = get_llm().with_structured_output(SupervisorDecision).invoke([
            SystemMessage(content=SUPERVISOR_PROMPT),
            HumanMessage(content=planning_request(state)),
        ])
        trip = decision.trip
        chosen = decision.agents
        reasoning = decision.reasoning
        on_topic = decision.is_travel_request
    except Exception as e:
        # Some models handle structured output poorly; running every agent
        # is slower but still answers the request.
        print("Supervisor could not plan, running all agents:", e)
        trip = TripDetails()          # all defaults (unknown origin, EUR, 1 traveler ...)
        chosen = list(AGENT_ORDER)
        reasoning = "Planning failed, so every agent runs."
        on_topic = True

    # Not a travel request: empty plan and a "blocked" flag, so the supervisor
    # routes to blocked_response, which shows the off_topic message.
    if not on_topic:
        return {
            "trip": trip.model_dump(),     # Pydantic object -> plain dict (storable in the state)
            "plan": [],
            "guardrail": {"blocked": True, "reason": "off_topic"},
            "llm_calls": state.get("llm_calls", 0) + 1,
            "messages": [AIMessage(content=f"Supervisor: not a travel request. {reasoning}")],
        }

    # Put the chosen agents in the fixed AGENT_ORDER (the LLM may list them in
    # any order), then insert "human_review" after the research if it is enabled.
    plan = with_review_step([agent for agent in AGENT_ORDER if agent in chosen], state)

    return {
        "trip": trip.model_dump(),
        "plan": plan,
        "llm_calls": state.get("llm_calls", 0) + 1,
        # A log line in the chat history, e.g. "Supervisor plan: hotel_agent. Only hotels asked."
        # `or 'answer directly'` is shown when the plan is empty.
        "messages": [
            AIMessage(content=f"Supervisor plan: {', '.join(plan) or 'answer directly'}. {reasoning}")
        ],
    }


def planning_request(state: TravelState) -> str:
    # The text the supervisor LLM receives: the user's request, plus any change
    # requests from the human review (so a re-plan uses the new wishes).
    request = state["user_query"]
    if state.get("feedback"):
        changes = "\n".join(f"- {change}" for change in state["feedback"])
        request += f"\n\nThe user reviewed the first results and asked for these changes:\n{changes}"
    return request


def pick_next_agent(plan: list[str], completed: list[str]) -> str:
    # The first agent of the plan that has not finished yet ...
    for agent in plan:
        if agent not in completed:
            return agent
    # ... or, when all are done, the responder writes the final answer.
    return "responder"


def route(state: TravelState) -> str:
    # Used by the conditional edge in workflow.py: the next node's name is
    # whatever supervisor_agent stored in next_agent.
    return state["next_agent"]
