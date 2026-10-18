# Architecture diagram: facts and verification

`architecture.excalidraw` (open it at https://excalidraw.com, via **Open**) was built from the code at commit `1764774`, not from the README. Rebuild it with `python docs/architecture/gen.py docs/architecture` and check it with `python docs/architecture/verify.py docs/architecture/architecture.excalidraw .`.

Also here: `system-design.excalidraw`, a one-page whiteboard-style system design (goals, rules, components and the labelled request flow). Rebuild it with `python docs/architecture/system_design.py <out-dir>`.

## Views

0. Read this first: summary, reading order, run/test commands, legend
1. Context: users and external services
2. Containers: browser, FastAPI process, MCP server subprocess, PostgreSQL
3. The LangGraph graph: every node and edge, with file paths
4. One request, numbered from a real traced run
5. Data and state
6. Trust and safety

## Facts extracted from the code

| What | Found | How |
| --- | --- | --- |
| Entry points | `python app.py` (uvicorn, 127.0.0.1:8000), Docker `uvicorn app:app --host 0.0.0.0`, `python mcp_server.py`, `cli.py` | `grep __main__`, Dockerfile `CMD` |
| Graph | 12 nodes + START/END, 22 edges (11 conditional) | `graph.get_graph()` output, saved as `graph-from-langgraph.mmd` |
| API | `POST /api/travel`, `POST /api/travel/review`, `GET /`, `GET /health` | `@app.get/post` in `app.py` |
| MCP tools | `search_flights`, `web_search`, `weather_forecast`, `convert_currency`, `lookup_airport` | `mcp_server.py`, live `list_tools()` |
| External services | Groq, Tavily, AviationStack, Open-Meteo, Frankfurter, PostgreSQL, jsDelivr/cdnjs (browser) | URL and client grep |
| Settings | Required: `DATABASE_URL`, `GROQ_API_KEY`, `TAVILY_API_KEY`. Optional: `AVIATIONSTACK_API_KEY`, `GROQ_MODEL`, `DEFAULT_ORIGIN_IATA`, `USE_MCP` | `os.getenv` grep, plus starting the app with each key unset |
| Storage | 4 PostgreSQL tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations`) keyed by `thread_id`; browser `localStorage.travel_thread_id` | `pg_tables` after a run, `script.js` |
| Most-changed files | `README.md`, `backend.py`, `app.py`, `templates/index.html`, `tests/conftest.py` | `git log --name-only` |

## Real run used for view 4

Real `backend.py`, real PostgreSQL, real MCP server subprocess; only the LLM was faked (the sandbox cannot reach Groq). Recorded with `travel_graph.stream(..., stream_mode="updates")`:

`input_guardrail -> supervisor -> flight_agent -> supervisor -> hotel_agent -> supervisor -> weather_agent -> supervisor -> local_guide_agent -> supervisor -> (pause) || resume -> human_review -> supervisor -> itinerary_agent -> supervisor -> budget_agent -> supervisor -> responder -> output_guardrail`

The trace wrote 20 checkpoint rows, and the MCP calls were `search_flights, web_search, weather_forecast, web_search`. Tavily was unreachable, so the run showed the failure path for real: the error became a note and the run continued.

## Verification

| Check | Result |
| --- | --- |
| Every file path on the diagram exists | PASS: 23/23 |
| Graph nodes on the diagram | PASS: 12/12 |
| API routes | PASS: 2/2 |
| MCP tools | PASS: 5/5 (first pass 2/5, fixed) |
| Settings / env vars | PASS: 7/7 (first pass 2/7, fixed) |
| External services | PASS: 7/7 |
| View 4 matches a fresh real trace | PASS: 19/19 steps in order |

Eight newcomer questions, answered from the diagram only, then checked against the code:

| # | Question | First pass | After fixes |
| --- | --- | --- | --- |
| 1 | Where do I add a 7th agent? | partial (missed `AgentName` and the supervisor prompt) | correct |
| 2 | Which steps call the LLM? | correct (5 files call `get_llm()`) | correct |
| 3 | What happens if Tavily is down? | correct (seen in the trace; test passes) | correct |
| 4 | Does a paused review survive a restart? | correct (`test_paused_review_survives_a_restart`) | correct |
| 5 | Which keys do I need? | partial (did not say which are required) | correct |
| 6 | How do agents call external APIs? | correct (no agent imports an API module) | correct |
| 7 | Does the LLM choose the run order? | correct (`test_plan_follows_agent_order_not_llm_order`) | correct |
| 8 | Can others on my network use it? | partial (bind address missing) | correct |

Score: 5/8 on the first pass, 8/8 after fixing the diagram.

## Not verified

- Real responses from Groq, Tavily, AviationStack, Open-Meteo and Frankfurter: blocked in the sandbox, faked in tests. These are drawn dashed.
- The MCP server on Windows.

## Findings from the scan (not fixed)

- `langchain-community`, `langchain-tavily` and `psycopg_pool` are in `requirements.txt` but nothing imports them.
- Checkpoints are never deleted, so the database grows with every request.
- The API has no authentication or rate limiting, and any client can read or resume any `thread_id` it knows.
