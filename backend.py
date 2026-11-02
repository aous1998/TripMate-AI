# =============================================================================
# backend.py - connects everything and runs one travel request
#
# Two jobs:
#   A) STARTUP (runs once, the moment app.py imports this file):
#        - read the .env settings
#        - create the LLM (fails fast if the Groq key is missing)
#        - connect to PostgreSQL and create LangGraph's checkpoint tables
#        - build and compile the agent graph (workflow.py)
#        - start the MCP tool server (tools/mcp_client.py)
#   B) PER REQUEST (called by app.py):
#        - run_travel_agent()    : start a new request
#        - resume_travel_agent() : continue a request paused for human review
#        - build_response()      : turn the graph's final state into JSON
# =============================================================================

import os                       # read environment variables (os.getenv / os.environ)
import certifi                  # a trusted list of HTTPS certificates
from dotenv import load_dotenv  # loads KEY=value lines from the .env file

# Copy every KEY=value from .env into the environment, so os.getenv("GROQ_API_KEY")
# etc. work everywhere. This must happen before the imports below read any settings.
load_dotenv()

# Tell HTTPS libraries to trust certifi's certificate list. This avoids
# "certificate verify failed" errors on some Windows/macOS Python installs.
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import uuid                     # generates random unique ids (for new thread_ids)

import psycopg                  # the PostgreSQL driver
from psycopg.rows import dict_row   # makes database rows come back as dicts

from langgraph.checkpoint.postgres import PostgresSaver   # saves graph state to PostgreSQL
from langgraph.types import Command                       # used to resume a paused graph

from agents.guardrails import BLOCK_MESSAGES, check_input # input safety check (reused for review feedback)
from llm import get_llm                                   # creates/returns the shared Groq model
from tools import mcp_client                              # starts and talks to the MCP tool server
from workflow import build_graph, new_request_state       # the graph wiring and the starting state


def get_database_url():
    # Read the PostgreSQL connection string from .env, e.g.
    # postgresql://user:password@host:5432/dbname
    database_url = os.getenv("DATABASE_URL")

    # Without a database the app cannot save state, so stop with a clear message.
    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your PostgreSQL connection URL to .env"
        )

    # Hosted databases (Supabase, Neon, ...) require an encrypted connection.
    # If the URL does not say which SSL mode to use, ask for SSL ("require").
    # A local PostgreSQL usually has no SSL: put ?sslmode=disable in the URL for that.
    if "sslmode=" not in database_url:
        # URL parameters start with "?" and are joined with "&".
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


# Fail fast at startup if the Groq key is missing.
# (get_llm() raises an error immediately instead of on the first user request.)
get_llm()


# =========================
# PostgreSQL Checkpointer
# =========================
DATABASE_URL = get_database_url()

# Open ONE connection to PostgreSQL, shared by every request.
#   autocommit=True      -> every statement is saved immediately (no manual commit)
#   row_factory=dict_row -> rows come back as {"column": value} dicts, which LangGraph expects
_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

# The "checkpointer" saves the whole graph state after every node, keyed by thread_id.
# setup() creates its tables (checkpoints, checkpoint_writes, checkpoint_blobs,
# checkpoint_migrations) if they do not exist yet. Safe to run on every start.
checkpointer = PostgresSaver(_conn)
checkpointer.setup()

# build_graph() describes the nodes and edges (workflow.py); compile() turns that
# description into something we can run, with the PostgreSQL checkpointer attached.
travel_graph = build_graph().compile(checkpointer=checkpointer)

# Start the MCP tool server now, so the first request is not slowed down.
mcp_client.start()


# =========================
# Functions for FastAPI
# =========================

class ReviewError(ValueError):
    """The review answer cannot be applied (nothing to review, or unsafe feedback)."""
    # app.py catches this specific error and replies with HTTP 400 (the user's fault),
    # instead of HTTP 500 (the server's fault).


def run_travel_agent(user_input: str, thread_id: str | None = None, human_review: bool = True):
    # No thread_id means a brand new conversation: make a random, unique one,
    # e.g. "user_3f2a9c...". The browser stores it and sends it back next time.
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    # Run the graph from START until it reaches END, or until it pauses
    # for human review (an "interrupt").
    #   - new_request_state(...) is the starting state for this request
    #   - thread_config(...) tells the checkpointer which conversation to save under
    result = travel_graph.invoke(
        new_request_state(user_input, review_enabled=human_review),
        config=thread_config(thread_id),
    )
    # Turn the final state into the JSON shape the browser expects.
    return build_response(thread_id, result)


def resume_travel_agent(thread_id: str, approved: bool, feedback: str = ""):
    """Answer a pending human review: approve the research, or request changes."""
    config = thread_config(thread_id)

    # get_state() loads the saved state of this conversation from PostgreSQL.
    # `.interrupts` is non-empty only if the graph is paused, waiting for an answer.
    if not travel_graph.get_state(config).interrupts:
        raise ReviewError("This plan is not waiting for a review. Please start a new request.")

    feedback = (feedback or "").strip()
    if not approved:
        # "Request changes" without saying what to change makes no sense.
        if not feedback:
            raise ReviewError("Please describe what you would like to change.")
        # The feedback goes to the LLM, so it passes the same input guardrail.
        reason = check_input(feedback)
        if reason:
            raise ReviewError(BLOCK_MESSAGES[reason])

    # Command(resume=...) continues the paused graph. Inside agents/review.py,
    # the paused interrupt() call now returns this dict instead of pausing again.
    result = travel_graph.invoke(
        Command(resume={"approved": approved, "feedback": feedback}),
        config=config,
    )
    return build_response(thread_id, result)


def thread_config(thread_id: str) -> dict:
    # LangGraph's standard config format. The checkpointer uses thread_id to know
    # which saved conversation to load and update.
    return {"configurable": {"thread_id": thread_id}}


def build_response(thread_id: str, result: dict) -> dict:
    # If the graph paused, LangGraph puts the pause information under "__interrupt__".
    interrupts = result.get("__interrupt__")

    if interrupts:
        # Paused for review: send the research (flights, hotels, trip details)
        # that agents/review.py passed to interrupt(), so the page can show it.
        return {
            "status": "needs_review",
            "thread_id": thread_id,
            "review": interrupts[0].value,
            "agents_run": result.get("completed", []),
        }

    # Finished. final_answer is the text after the output guardrail; if it is
    # empty (should not happen) fall back to the last chat message.
    final_answer = result.get("final_answer") or result["messages"][-1].content

    # Everything the page (and anyone using the API) might want to show.
    # .get(key, default) avoids an error if a field was never set.
    return {
        "status": "done",
        "thread_id": thread_id,
        "answer": final_answer,                                # the final answer (Markdown)
        "trip": result.get("trip"),                            # extracted trip details
        "agents_run": result.get("completed", []),             # which agents ran, in order
        "revisions": result.get("revisions", 0),               # how many change requests
        "flight_results": result.get("flight_results", ""),    # raw research results...
        "hotel_results": result.get("hotel_results", ""),
        "weather": result.get("weather", ""),
        "local_tips": result.get("local_tips", ""),
        "itinerary": result.get("itinerary", ""),
        "budget": result.get("budget"),                        # itemised budget (dict)
        "guardrail": result.get("guardrail"),                  # was the request blocked? why?
        "guardrail_notes": result.get("guardrail_notes", []),  # what the output guardrail did
        "llm_calls": result.get("llm_calls", 0),               # how many LLM calls were made
    }
