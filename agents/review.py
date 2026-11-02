"""Human-in-the-loop: pause after research so the user can approve or ask for changes.

The pause uses LangGraph's interrupt(): the graph's state is saved by the
PostgreSQL checkpointer, the API returns the research to the user, and the
run continues from the same point when the user answers (even after a restart).
"""
# -----------------------------------------------------------------------------
# agents/review.py - the human review step.
#
# Flow when the "review flights & hotels" box is ticked:
#   supervisor plan: flight, hotel, weather, local_guide, HUMAN_REVIEW, itinerary, budget
#   1. research agents run
#   2. human_review calls interrupt(...) -> the run stops, state is saved,
#      backend.py returns status "needs_review" with the research
#   3. the user clicks Approve or sends changes -> backend.resume_travel_agent()
#      -> Command(resume={...}) -> human_review runs again and interrupt()
#      now RETURNS that answer
#   4a. approved  -> mark done, continue with itinerary and budget
#   4b. changes   -> reset research, supervisor re-plans with the feedback
# -----------------------------------------------------------------------------

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt   # pauses the graph and waits for outside input

from agents.common import mark_done
from state import TravelState


# Agents whose results the user reviews.
RESEARCH_AGENTS = {"flight_agent", "hotel_agent"}
# Agents that build on that research (they must wait for the review).
DOWNSTREAM_AGENTS = {"itinerary_agent", "budget_agent"}
# After this many change requests, no more reviews (prevents endless loops).
MAX_REVISIONS = 3
# Longest feedback text we keep.
MAX_FEEDBACK_CHARS = 500


def with_review_step(plan: list[str], state: TravelState) -> list[str]:
    """Insert a review between the research agents and the agents that build on them.

    Only worth asking when there is research to approve and work still to do
    with it; after MAX_REVISIONS change requests the run continues unreviewed.
    """
    # Review switched off, or the user already asked for changes 3 times.
    if not state.get("review_enabled") or state.get("revisions", 0) >= MAX_REVISIONS:
        return plan
    # `&` = set intersection. Both a research agent AND a downstream agent
    # must be in the plan, otherwise a review has nothing useful to do.
    if not (RESEARCH_AGENTS & set(plan) and DOWNSTREAM_AGENTS & set(plan)):
        return plan

    # Index of the first downstream agent; put "human_review" right before it.
    # next(...) returns the first value the generator produces.
    first_downstream = next(i for i, agent in enumerate(plan) if agent in DOWNSTREAM_AGENTS)
    # plan[:i] = everything before i, plan[i:] = from i to the end.
    return plan[:first_downstream] + ["human_review"] + plan[first_downstream:]


def human_review(state: TravelState):
    # interrupt() pauses here. On resume the node runs again from the top and
    # interrupt() returns the user's answer instead of pausing.
    # The dict passed in is what the user is shown (backend.py reads it from
    # the saved state and sends it to the browser as "review").
    answer = interrupt({
        "trip": state.get("trip"),
        "flight_results": state.get("flight_results", ""),
        "hotel_results": state.get("hotel_results", ""),
        "weather": state.get("weather", ""),
        "revision": state.get("revisions", 0),
        "max_revisions": MAX_REVISIONS,
    })

    # answer = {"approved": bool, "feedback": str} sent by resume_travel_agent().
    # Clean it: never None, no outer spaces, at most 500 characters.
    feedback = str(answer.get("feedback") or "").strip()[:MAX_FEEDBACK_CHARS]

    # Approved (or "not approved" but with no text): continue the plan.
    if answer.get("approved", True) or not feedback:
        return {
            "completed": mark_done(state, "human_review"),
            "messages": [AIMessage(content="User approved the research results.")],
        }

    # Changes requested: the supervisor re-plans with the feedback and the
    # research agents run again, followed by another review.
    return {
        "feedback": state.get("feedback", []) + [feedback],   # keep earlier feedback too
        "revisions": state.get("revisions", 0) + 1,
        "plan": None,              # None -> the supervisor calls the LLM again
        "completed": [],           # nothing counts as done any more
        "flight_results": "",      # clear the old research
        "hotel_results": "",
        "weather": "",
        "local_tips": "",
        "messages": [HumanMessage(content=f"Requested changes: {feedback}")],
    }
