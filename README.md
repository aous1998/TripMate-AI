# ✈️ TripMate AI — A Multi-Agent Travel Planner with LangGraph

An open-source AI travel planner that turns a natural-language trip request into a practical travel plan with flight suggestions, hotel ideas, and a day-by-day itinerary. The project uses a multi-agent workflow built with LangGraph, LangChain, and FastAPI.

Maintained by [Aous Abdulhamid](https://github.com/aous1998).

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
├── cli.py                # Run one request from the terminal
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

## API Endpoints

- GET /health - Health check
- POST /api/travel - Submit a travel request

Example request:

```bash
curl -X POST http://127.0.0.1:8000/api/travel \
  -H "Content-Type: application/json" \
  -d '{"message":"Plan a 3-day trip to Tokyo with a budget of $1200"}'
```

## How the Workflow Works

```text
START -> supervisor -> one of six specialists -> supervisor -> ... -> responder -> END
```

1. The user submits a travel request.
2. The **supervisor** makes one structured-output LLM call that extracts typed trip details (origin, destination, days, budget, currency, travelers, interests) and picks which specialists the request needs.
3. The supervisor routes to the next pending specialist through a conditional edge. Each specialist writes its result to the shared state and hands back to the supervisor.
4. Specialists always run in dependency order (research first, then the itinerary, then the budget), whatever order the LLM listed them in.
5. When every planned agent has run, the **responder** writes the final answer from whatever was gathered.

If structured output fails, the supervisor falls back to running every agent, so the request still gets an answer.

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

## Contributing

Contributions are welcome. If you want to improve the app, add new travel features, or fix issues:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Open a pull request

## Acknowledgments

This project is based on [TripMate AI](https://github.com/entbappy/TripMate-AI-A-Multi-Agent-Travel-Planner-with-LangGraph) by Bappy Ahmed, released under the MIT License. It is built with the help of modern LLM tooling and travel APIs, and it is intended as a practical example of combining LangGraph agents with real-world applications.

## License

Released under the [MIT License](LICENSE).
