from pathlib import Path
import traceback
import uvicorn

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backend import ReviewError, resume_travel_agent, run_travel_agent

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="TripMate AI",
    description="LangGraph Multi-Agent Travel Planner with FastAPI Frontend",
    version="1.0.0"
)


app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)



class TravelRequest(BaseModel):
    message: str
    thread_id: str | None = None
    human_review: bool = True


class ReviewRequest(BaseModel):
    thread_id: str
    approved: bool
    feedback: str | None = None



@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


# Sync endpoints: FastAPI runs them in a worker thread, so a long graph run
# does not block the server's event loop.
@app.post("/api/travel")
def travel_planner(request_data: TravelRequest):
    try:
        user_message = request_data.message.strip()

        if not user_message:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "Message cannot be empty."
                }
            )

        result = run_travel_agent(
            user_input=user_message,
            thread_id=request_data.thread_id,
            human_review=request_data.human_review,
        )

        return JSONResponse(content={"success": True, **result})

    except Exception as e:
        return error_response(e)


@app.post("/api/travel/review")
def review_plan(request_data: ReviewRequest):
    try:
        result = resume_travel_agent(
            thread_id=request_data.thread_id,
            approved=request_data.approved,
            feedback=request_data.feedback or "",
        )

        return JSONResponse(content={"success": True, **result})

    except ReviewError as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})

    except Exception as e:
        return error_response(e)


def error_response(e: Exception) -> JSONResponse:
    print("ERROR:", e)
    traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(e)
        }
    )



@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "message": "AI Travel Planner API is running"
    }


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={})



if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
