# =============================================================================
# app.py - the web server (the "front door" of TripMate AI)
#
# What this file does:
#   1. Creates the FastAPI application.
#   2. Serves the web page (templates/index.html) and its CSS/JS (static/).
#   3. Defines the HTTP API the page talks to:
#        POST /api/travel         -> start a new travel request
#        POST /api/travel/review  -> answer a paused review (approve / request changes)
#        GET  /health             -> "is the server alive?" check
#   4. Starts the uvicorn web server when you run `python app.py`.
#
# This file contains NO travel logic. It only receives HTTP requests,
# hands them to backend.py, and turns the result into a JSON reply.
# =============================================================================

# --- Standard library imports ------------------------------------------------
from pathlib import Path   # builds file paths that work on Windows, macOS and Linux
import traceback           # prints the full error stack when something crashes
import uvicorn             # the web server program that actually runs the app

# --- FastAPI (web framework) imports ----------------------------------------
from fastapi import FastAPI, Request                        # the app object, and the incoming request
from fastapi.responses import HTMLResponse, JSONResponse    # reply types: an HTML page, or JSON data
from fastapi.staticfiles import StaticFiles                 # serves fixed files (CSS, JavaScript)
from fastapi.templating import Jinja2Templates              # renders HTML templates
from pydantic import BaseModel                              # describes and validates JSON request bodies

# --- Our own code -------------------------------------------------------------
# Importing backend.py runs its startup code: it connects to PostgreSQL,
# builds the agent graph and starts the MCP tool server (see backend.py).
from backend import ReviewError, resume_travel_agent, run_travel_agent

# The folder this file lives in. Used to find templates/ and static/
# no matter which folder you start the server from.
BASE_DIR = Path(__file__).resolve().parent

# The FastAPI application. title/description/version appear on the
# auto-generated API docs page at http://127.0.0.1:8000/docs
app = FastAPI(
    title="TripMate AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI Frontend",
    version="1.0.0"
)


# Serve everything in the static/ folder under the URL /static/...
# e.g. static/script.js is downloaded by the browser from /static/script.js
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)


# Jinja2 renders HTML files from the templates/ folder.
templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)



# =============================================================================
# Request bodies (what JSON the API accepts)
# FastAPI checks incoming JSON against these classes automatically. If a field
# is missing or has the wrong type, it replies with HTTP 422 before our code runs.
# =============================================================================

class TravelRequest(BaseModel):
    message: str                     # the user's trip request, e.g. "Plan 7 days in Nice"
    thread_id: str | None = None     # conversation id; None means "start a new conversation"
    human_review: bool = True        # pause after research so the user can approve it?


class ReviewRequest(BaseModel):
    thread_id: str                   # which paused conversation to continue
    approved: bool                   # True = "Approve", False = "Request changes"
    feedback: str | None = None      # what to change (only used when approved is False)



# =============================================================================
# Routes (URL -> Python function)
# =============================================================================

# GET / -> the web page. `async def` is fine here: rendering a template is fast.
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Render templates/index.html. Jinja2 needs the request object;
    # context={} means we pass no extra variables into the template.
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


# Sync endpoints: FastAPI runs them in a worker thread, so a long graph run
# does not block the server's event loop.
# POST /api/travel -> start a new travel request.
@app.post("/api/travel")
def travel_planner(request_data: TravelRequest):
    try:
        # Remove spaces/newlines at both ends of the message.
        user_message = request_data.message.strip()

        # An empty message is the user's mistake -> HTTP 400 "Bad Request".
        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty."
                }
            )

        # Hand the work to backend.py. This runs the whole agent graph and
        # returns a dict with status "done" (final answer) or
        # "needs_review" (paused, waiting for the user's approval).
        result = run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id,
            human_review=request_data.human_review,
        )

        # `**result` copies every key of `result` into this dict,
        # so the reply is {"success": true, "status": ..., "answer": ..., ...}.
        return JSONResponse(content={"success": True, **result})

    except Exception as e:
        # Anything unexpected (e.g. the LLM provider is down) -> HTTP 500.
        return error_response(e)


# POST /api/travel/review -> answer a paused review.
@app.post("/api/travel/review")
def review_plan(request_data: ReviewRequest):
    try:
        # Continue the paused graph with the user's decision.
        # `request_data.feedback or ""` turns None into an empty string.
        result = resume_travel_agent(
            thread_id=request_data.thread_id,
            approved=request_data.approved,
            feedback=request_data.feedback or "",
        )

        return JSONResponse(content={"success": True, **result})

    except ReviewError as e:
        # A problem with what the user sent (nothing waiting for review,
        # empty or unsafe feedback) -> HTTP 400 with a readable message.
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})

    except Exception as e:
        # Anything else -> HTTP 500.
        return error_response(e)


def error_response(e: Exception) -> JSONResponse:
    # Print the error and the full stack trace in the server console,
    # so you can see exactly which line failed.
    print("ERROR:", e)
    traceback.print_exc()

    # Tell the browser something went wrong (HTTP 500 "Internal Server Error").
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(e)
        }
    )



# GET /health -> a tiny check that the server is running (useful for Docker
# or a load balancer). It does not touch the LLM or the database.
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "AI Travel Planner API is running"
    }


# Browsers ask for /favicon.ico (the tab icon) automatically. We have none,
# so we answer with an empty JSON object instead of a 404 error in the logs.
@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})



# This block runs only when you start the file directly: `python app.py`.
# (It does not run when uvicorn or the tests import this file.)
if __name__ == "__main__":
    uvicorn.run(
        "app:app",          # "file name : variable name" of the FastAPI app
        host="127.0.0.1",   # only this computer can connect (use 0.0.0.0 to allow your network)
        port=8000,          # open http://127.0.0.1:8000 in the browser
        reload=True         # restart automatically when you save a code change
    )
