# ✈️ TripMate AI — A Multi-Agent Travel Planner with LangGraph

An open-source AI travel planner that turns a natural-language trip request into a practical plan: flights, hotels, weather, local tips, a day-by-day itinerary and an itemised budget in euros. A LangGraph supervisor routes each request to the specialist agents it needs, the agents reach every API through an MCP server, the user can approve or change the research before the plan is built, and guardrails screen both input and output.

Maintained by [Aous Abdulhamid](https://github.com/aous1998).

![TripMate AI home screen](docs/images/tripmate-home.webp)

## Why this project?

Planning a trip usually means jumping between multiple websites, tools, and spreadsheets. This project brings that flow into one experience: a supervisor agent reads the request, extracts the trip details, and routes work to only the specialist agents it needs:

| Agent | What it does | Data source |
| --- | --- | --- |
| `flight_agent` | Live flights between origin and destination | AviationStack |
| `hotel_agent` | Hotel suggestions at the destination | Tavily search |
| `weather_agent` | 7-day forecast at the destination | Open-Meteo |
| `local_guide_agent` | Entry, transport, money and etiquette tips | Tavily search + LLM |
| `itinerary_agent` | Day-by-day plan that uses all of the above | LLM |
| `budget_agent` | Itemised EUR estimate checked against the user's budget | LLM structured output + ECB rates (Frankfurter) |

A responder agent then writes the final answer.

## Features

- ✈️ Flight research using AviationStack
- 🏨 Hotel suggestions using Tavily search
- 🌦️ Weather forecasts using Open-Meteo
- 🗺️ Local tips (entry, transport, money, etiquette)
- 💶 Itemised budget in EUR, with totals computed in code and foreign budgets converted at ECB rates
- 🧭 Supervisor agent that extracts typed trip details and routes to only the agents a request needs
- 🧠 Multi-agent orchestration with LangGraph
- 🔌 All tools served by an MCP server; agents call them through an MCP client over stdio
- 🙋 Human-in-the-loop: the graph pauses after flight and hotel research so the user can approve or request changes, then resumes from the PostgreSQL checkpoint
- 🛡️ Guardrails on input (prompt injection, off-topic, card numbers), on tool data and on output (secret redaction, code-computed budget check)
- 📝 Structured travel itinerary generation
- 🌐 FastAPI backend with a simple web interface
- 💾 Conversation state persistence using PostgreSQL
- ⚡ LLM-powered responses with Groq

## Tech Stack

- Python 3.10+
- FastAPI
- Jinja2 + HTML/CSS/JavaScript frontend
- LangGraph
- LangChain
- Model Context Protocol (official `mcp` Python SDK)
- Groq LLMs
- PostgreSQL
- Tavily API
- AviationStack API
- Open-Meteo API (no key needed)
- Frankfurter API for ECB exchange rates (no key needed)

## Project Structure

```text
.
├── app.py                # FastAPI app entry point
├── backend.py            # PostgreSQL checkpointer + run_travel_agent()
├── workflow.py           # LangGraph graph: supervisor, specialists, responder
├── state.py              # Typed graph state and supervisor schemas
├── llm.py                # Shared Groq chat model
├── mcp_server.py         # MCP server exposing the travel tools
├── agents/               # Supervisor, six specialists, responder
├── tools/                # API integrations + mcp_client.py (MCP client for the agents)
├── tests/                # Offline tests (fake LLM, no API keys needed)
├── cli.py                # Run one request from the terminal (with review prompts)
├── requirements.txt      # Python dependencies
├── static/               # Static frontend assets
└── templates/            # HTML templates
```

## Prerequisites

Before running the project locally, make sure you have:

- Python 3.10 or newer installed
- PostgreSQL running and accessible
- API keys for:
  - Groq
  - Tavily
  - AviationStack

## Environment Variables

Create a .env file in the project root with the following variables:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
TAVILY_API_KEY=your_tavily_api_key
DEFAULT_ORIGIN_IATA=FRA
```

Optional: `USE_MCP=false` runs the tools in-process instead of through the MCP server.

## Installation

```bash
git clone https://github.com/aous1998/TripMate-AI.git
cd TripMate-AI
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your keys (`copy .env.example .env` on Windows).

## Running the App

Start the FastAPI server:

```bash
python app.py
```

Then open your browser at:

```text
http://127.0.0.1:8000/
```

## Running with Docker

```bash
docker build -t tripmate-ai .
docker run --env-file .env -p 8000:8000 tripmate-ai
```

Keys are passed at run time with `--env-file`; `.dockerignore` keeps `.env` out of the image. The MCP tool server starts inside the container automatically.

## API Endpoints

- GET /health - Health check
- POST /api/travel - Submit a travel request (`message`, optional `thread_id`, `human_review`: default `true`)
- POST /api/travel/review - Answer a paused review (`thread_id`, `approved`, optional `feedback`)

`/api/travel` returns `"status": "needs_review"` with the flight and hotel research when the graph pauses for approval, or `"status": "done"` with the final `answer`.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/travel \
  -H "Content-Type: application/json" \
  -d '{"message":"Plan a 3-day trip to Tokyo with a budget of $1200"}'
```

## How the Workflow Works

```text
START -> input_guardrail -> supervisor -> one of six specialists -> supervisor -> ...
                                       -> human_review (pause) -> supervisor -> ...
                                       -> responder -> output_guardrail -> END
Blocked or off-topic requests: -> blocked_response -> END
```

1. The user submits a travel request, and the **input guardrail** screens it before any LLM call.
2. The **supervisor** makes one structured-output LLM call that extracts typed trip details (origin, destination, days, budget, currency, travelers, interests) and picks which specialists the request needs.
3. The supervisor routes to the next pending specialist through a conditional edge. Each specialist writes its result to the shared state and hands back to the supervisor.
4. Specialists always run in dependency order (research first, then the itinerary, then the budget), whatever order the LLM listed them in.
5. When every planned agent has run, the **responder** writes the final answer from whatever was gathered, and the **output guardrail** checks it.

If structured output fails, the supervisor falls back to running every agent, so the request still gets an answer.

## Human-in-the-Loop Review

When a request needs both research (flights or hotels) and work that builds on it (itinerary or budget), the supervisor inserts a `human_review` step after the research:

1. `human_review` calls LangGraph's `interrupt()`. The graph state is saved by the PostgreSQL checkpointer and the API returns the flights and hotels with `"status": "needs_review"`.
2. The web page shows them with **Approve** and **Request changes** buttons.
3. `POST /api/travel/review` resumes the same thread with `Command(resume=...)`. Because the state lives in PostgreSQL, a paused plan survives a server restart.
4. **Approve** continues to the itinerary and budget. **Request changes** (e.g. "cheaper hotels near the beach") sends the feedback back to the supervisor, which re-extracts the trip details (including `hotel_preferences`), re-runs the research and asks again.
5. After three change requests the run continues without asking again. Feedback passes the same input guardrail as a new request.

Untick "Let me review flights & hotels" on the page (or send `"human_review": false`) to run straight through.

## Guardrails

| Layer | Where | What it does |
| --- | --- | --- |
| Input rules | `agents/guardrails.py` | Blocks empty or over-long input, prompt-injection phrases ("ignore previous instructions", "reveal your system prompt", ...) and payment card numbers (Luhn-checked), before any LLM call |
| Topic check | Supervisor structured output | `is_travel_request: false` sends the request to a polite refusal without running any agent |
| Structured output validation | `state.py` (Pydantic validators) | Coerces bad LLM values instead of failing: currency codes, trip length 1-60 days, positive budgets, 1-20 travelers, non-negative costs |
| Untrusted tool data | `agents/common.py` | Web and API results are fenced in `<data>` tags and the model is told never to follow instructions inside them, to resist prompt injection from web pages |
| Output checks | `output_guardrail` node | Redacts anything that looks like an API key or database password, and appends a budget verdict computed in code from the itemised estimate |

## MCP Tool Server

The agents never call an API directly. Every tool lives in `mcp_server.py`, an MCP server built with the official Python SDK:

| Tool | Purpose |
| --- | --- |
| `search_flights` | Live flights for a route (AviationStack) |
| `web_search` | Web results with snippets (Tavily) |
| `weather_forecast` | Daily forecast for a city or country (Open-Meteo) |
| `convert_currency` | ECB exchange rates (Frankfurter) |
| `lookup_airport` | Main airport code for a city or country |

`tools/mcp_client.py` starts the server once as a subprocess over stdio and keeps one MCP session open in a background thread, so the synchronous LangGraph agents call tools with a plain function call (about 3 ms of overhead per call once connected). Tool errors come back as MCP error results with their real reason, and the agent turns them into a note instead of failing the request. If the server cannot start, tools run in-process with a warning; set `USE_MCP=false` to do that deliberately.

Any other MCP client can use the same server, e.g. by configuring `python mcp_server.py` as a stdio server.

## Running Tests

The tests use a fake LLM and fake tools, so they need no API keys or database:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

`tests/test_mcp.py` starts the real MCP server over stdio. To also run the end-to-end tests against a real PostgreSQL database (FastAPI endpoints, checkpointer, and resuming a paused review after a "restart"), point `TEST_DATABASE_URL` at an empty database:

```bash
TEST_DATABASE_URL="postgresql://postgres:password@localhost:5432/travel_db?sslmode=disable" python -m pytest
```

## Contributing

Contributions are welcome. If you want to improve the app, add new travel features, or fix issues:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Open a pull request

## Acknowledgments

This project is based on [TripMate AI](https://github.com/entbappy/TripMate-AI-A-Multi-Agent-Travel-Planner-with-LangGraph) by Bappy Ahmed, released under the MIT License. The original is a fixed four-step pipeline (flight, hotel, itinerary, final answer) with a FastAPI web UI and PostgreSQL checkpointing.

Added in this version: the supervisor with typed trip extraction and conditional routing, the weather, local-guide and budget agents, the MCP tool server and client, the guardrails, human-in-the-loop review with interrupt/resume, sanitised rendering, and the test suite.

## License

Released under the [MIT License](LICENSE).
