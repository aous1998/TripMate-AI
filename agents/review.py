"""Human-in-the-loop: pause after research so the user can approve or ask for changes.

The pause uses LangGraph's interrupt(): the graph's state is saved by the
PostgreSQL checkpointer, the API returns the research to the user, and the
run continues from the same point when the user answers (even after a restart).
"""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from agents.common import mark_done
from state import TravelState


RESEARCH_AGENTS = {"flight_agent", "hotel_agent"}
DOWNSTREAM_AGENTS = {"itinerary_agent", "budget_agent"}
MAX_REVISIONS = 3
MAX_FEEDBACK_CHARS = 500


def with_review_step(plan: list[str], state: TravelState) -> list[str]:
    """Insert a review between the research agents and the agents that build on them.

    Only worth asking when there is research to approve and work still to do
    with it; after MAX_REVISIONS change requests the run continues unreviewed.
    """
    if not state.get("review_enabled") or state.get("revisions", 0) >= MAX_REVISIONS:
        return plan
    if not (RESEARCH_AGENTS & set(plan) and DOWNSTREAM_AGENTS & set(plan)):
        return plan

    first_downstream = next(i for i, agent in enumerate(plan) if agent in DOWNSTREAM_AGENTS)
    return plan[:first_downstream] + ["human_review"] + plan[first_downstream:]


def human_review(state: TravelState):
    # interrupt() pauses here. On resume the node runs again from the top and
    # interrupt() returns the user's answer instead of pausing.
    answer = interrupt({
        "trip": state.get("trip"),
        "flight_results": state.get("flight_results", ""),
        "hotel_results": state.get("hotel_results", ""),
        "weather": state.get("weather", ""),
        "revision": state.get("revisions", 0),
        "max_revisions": MAX_REVISIONS,
    })

    feedback = str(answer.get("feedback") or "").strip()[:MAX_FEEDBACK_CHARS]

    if answer.get("approved", True) or not feedback:
        return {
            "completed": mark_done(state, "human_review"),
            "messages": [AIMessage(content="User approved the research results.")],
        }

    # Changes requested: the supervisor re-plans with the feedback and the
    # research agents run again, followed by another review.
    return {
        "feedback": state.get("feedback", []) + [feedback],
        "revisions": state.get("revisions", 0) + 1,
        "plan": None,
        "completed": [],
        "flight_results": "",
        "hotel_results": "",
        "weather": "",
        "local_tips": "",
        "messages": [HumanMessage(content=f"Requested changes: {feedback}")],
    }
