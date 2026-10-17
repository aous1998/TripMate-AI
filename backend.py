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

from llm import get_llm
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


# =========================
# Function for FastAPI
# =========================

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    result = travel_graph.invoke(new_request_state(user_input), config=config)

    final_answer = result["messages"][-1].content

    return {
        "thread_id": thread_id,
        "answer": final_answer,
        "trip": result.get("trip"),
        "agents_run": result.get("completed", []),
        "flight_results": result.get("flight_results", ""),
        "hotel_results": result.get("hotel_results", ""),
        "weather": result.get("weather", ""),
        "local_tips": result.get("local_tips", ""),
        "itinerary": result.get("itinerary", ""),
        "budget": result.get("budget"),
        "llm_calls": result.get("llm_calls", 0),
    }
