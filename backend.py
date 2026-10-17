import os
import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import uuid

import psycopg
from psycopg.rows import dict_row

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from agents.guardrails import BLOCK_MESSAGES, check_input
from llm import get_llm
from tools import mcp_client
from workflow import build_graph, new_request_state


def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your PostgreSQL connection URL to .env"
        )

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


# Fail fast at startup if the Groq key is missing.
get_llm()


# =========================
# PostgreSQL Checkpointer
# =========================
DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)

checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = build_graph().compile(checkpointer=checkpointer)

# Start the MCP tool server now, so the first request is not slowed down.
mcp_client.start()


# =========================
# Functions for FastAPI
# =========================

class ReviewError(ValueError):
    """The review answer cannot be applied (nothing to review, or unsafe feedback)."""


def run_travel_agent(user_input: str, thread_id: str | None = None, human_review: bool = True):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    result = travel_graph.invoke(
        new_request_state(user_input, review_enabled=human_review),
        config=thread_config(thread_id),
    )
    return build_response(thread_id, result)


def resume_travel_agent(thread_id: str, approved: bool, feedback: str = ""):
    """Answer a pending human review: approve the research, or request changes."""
    config = thread_config(thread_id)

    if not travel_graph.get_state(config).interrupts:
        raise ReviewError("This plan is not waiting for a review. Please start a new request.")

    feedback = (feedback or "").strip()
    if not approved:
        if not feedback:
            raise ReviewError("Please describe what you would like to change.")
        # The feedback goes to the LLM, so it passes the same input guardrail.
        reason = check_input(feedback)
        if reason:
            raise ReviewError(BLOCK_MESSAGES[reason])

    result = travel_graph.invoke(
        Command(resume={"approved": approved, "feedback": feedback}),
        config=config,
    )
    return build_response(thread_id, result)


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def build_response(thread_id: str, result: dict) -> dict:
    interrupts = result.get("__interrupt__")

    if interrupts:
        return {
            "status": "needs_review",
            "thread_id": thread_id,
            "review": interrupts[0].value,
            "agents_run": result.get("completed", []),
        }

    final_answer = result.get("final_answer") or result["messages"][-1].content

    return {
        "status": "done",
        "thread_id": thread_id,
        "answer": final_answer,
        "trip": result.get("trip"),
        "agents_run": result.get("completed", []),
        "revisions": result.get("revisions", 0),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather": result.get("weather", ""),
        "local_tips": result.get("local_tips", ""),
        "itinerary": result.get("itinerary", ""),
        "budget": result.get("budget"),
        "guardrail": result.get("guardrail"),
        "guardrail_notes": result.get("guardrail_notes", []),
        "llm_calls": result.get("llm_calls", 0),
    }
