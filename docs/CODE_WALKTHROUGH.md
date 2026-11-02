# TripMate AI: code walkthrough

This document explains the whole codebase step by step, in the order things happen when the app runs. Read it top to bottom once; afterwards each part works as a reference.

Line numbers match the commented code. If they drift after later edits, search for the function name. Every code file also has its own comments; Part 14 lists every file in the repository.

---

## Part 0. The big picture

TripMate takes one sentence such as *"Plan 7 days from Berlin to Nice under 1500 euros"* and returns flights, hotels, weather, local tips, a day-by-day itinerary and a budget.

Inside, one request moves through these layers:

```text
Browser page (templates/index.html + static/script.js)
   |  HTTP JSON
FastAPI routes (app.py)
   |  Python call
backend.py  -> run_travel_agent() / resume_travel_agent()
   |  graph.invoke()
LangGraph graph (workflow.py) made of nodes (agents/*.py)
   |  run_tool()                      |  get_llm()
MCP client (tools/mcp_client.py)     Groq LLM (llm.py)
   |  stdio
MCP server (mcp_server.py) -> tools/*.py -> external APIs
   ...and after every node, the graph state is saved to PostgreSQL
```

### File map

| File | Role |
| --- | --- |
| `app.py` | Web server: the HTTP routes |
| `backend.py` | Connects to PostgreSQL, compiles the graph, runs and resumes requests |
| `workflow.py` | Wires the graph: which nodes exist and how they connect |
| `state.py` | The shared state every node reads and writes, plus typed schemas |
| `llm.py` | Creates the Groq chat model once and shares it |
| `agents/supervisor.py` | Plans which agents to run and routes between them |
| `agents/flight.py`, `hotel.py`, `weather.py`, `local_guide.py`, `itinerary.py`, `budget.py` | The six specialist agents |
| `agents/review.py` | The human-in-the-loop pause |
| `agents/responder.py` | Writes the final answer |
| `agents/guardrails.py` | Input and output safety checks |
| `agents/common.py` | Small helpers shared by agents |
| `mcp_server.py` | MCP server exposing the tools |
| `tools/mcp_client.py` | How agents call the MCP server |
| `tools/flight_tool.py`, `tavily_tool.py`, `weather_tool.py`, `currency_tool.py` | The actual API code |
| `templates/index.html`, `static/script.js`, `static/style.css` | The web page |
| `cli.py` | Run one request from the terminal |
| `tests/` | The test suite |

### Five ideas you need first

1. **Graph.** LangGraph runs a *graph*: **nodes** are Python functions, **edges** say which node runs next. A **conditional edge** calls a function that returns the name of the next node.
2. **State.** All nodes share one dictionary, the **state** (`TravelState` in `state.py`). A node receives the current state and returns *only the fields it wants to change*. LangGraph merges those changes in.
3. **Checkpointer.** After every node, LangGraph saves the whole state to PostgreSQL under a `thread_id`. That is what makes pausing and resuming possible.
4. **Structured output.** Instead of asking the LLM for free text, some calls ask for an object that matches a Pydantic class (`SupervisorDecision`, `BudgetEstimate`). LangChain turns the class into a tool schema, and the model fills it in.
5. **MCP (Model Context Protocol).** A standard way to expose tools. The tools live in a separate server process; the agents talk to it as a client.

---

## Part 1. Startup: what happens when you run `python app.py`

### Step 1.1: `app.py` starts uvicorn

At the bottom of `app.py` (`if __name__ == "__main__":`), `uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)` starts the web server. `127.0.0.1` means only your own computer can reach it; `reload=True` restarts it when you edit a file. (Docker instead runs `uvicorn app:app --host 0.0.0.0`, which accepts connections from the network.)

uvicorn imports `app.py`, and the first thing `app.py` does is `from backend import ...`. **Importing `backend.py` is where most of the startup work happens.**

### Step 1.2: `backend.py` prepares everything (runs once, at import)

Top to bottom:

1. **`load_dotenv()`** reads your `.env` file into environment variables (API keys, `DATABASE_URL`, and so on).
2. **`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` = `certifi.where()`** point HTTPS libraries at a known certificate bundle, which avoids SSL errors on some Windows setups.
3. **`get_llm()`** (line 68) creates the Groq model now. If `GROQ_API_KEY` is missing it raises an error, so the app fails at startup instead of on the first request. This is called *fail fast*.
4. **`get_database_url()`** (line 44) reads `DATABASE_URL`. If it has no `sslmode=`, it appends `sslmode=require`, because hosted databases such as Supabase need SSL.
5. **`psycopg.connect(...)`** (line 79) opens one connection to PostgreSQL. `autocommit=True` means each statement is saved immediately; `row_factory=dict_row` returns rows as dictionaries.
6. **`PostgresSaver(_conn)` and `checkpointer.setup()`** (lines 88-89) create LangGraph's checkpoint tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations`) if they do not exist yet.
7. **`travel_graph = build_graph().compile(checkpointer=checkpointer)`** (line 93) builds the graph from `workflow.py` and compiles it into something runnable, with PostgreSQL attached.
8. **`mcp_client.start()`** (line 96) starts the MCP server subprocess and lists its tools, so the first request is not slowed down. You see `MCP tool server connected: search_flights, web_search, ...` in the console.

### Step 1.3: `llm.py`, the shared model

```python
_llm = None

def get_llm():
    if _llm is None:
        _llm = ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                        api_key=api_key, max_retries=4)
    return _llm
```

- The model is created **once** and reused (a lazy singleton).
- `GROQ_MODEL` lets you switch models from `.env` without code changes. This exists because Groq retired the original model.
- `max_retries=4`: if Groq answers "too many requests", the SDK waits as long as Groq says (the `retry-after` header) and tries again, up to 4 times.
- `set_llm()` lets the tests swap in a fake model.

### Step 1.4: `app.py` sets up routes

- `app.mount("/static", ...)` serves `static/script.js` and `static/style.css`.
- `Jinja2Templates("templates")` serves `templates/index.html`.
- Two Pydantic request models describe the JSON the API accepts:
  - `TravelRequest`: `message`, optional `thread_id`, `human_review` (default `True`)
  - `ReviewRequest`: `thread_id`, `approved`, optional `feedback`

FastAPI validates incoming JSON against these classes automatically and returns a 422 error if a field is the wrong type.

---

## Part 2. The page: what the browser does

### Step 2.1: Loading the page

`GET /` (`app.py` line 87) returns `templates/index.html`. The page loads three libraries from a CDN:

- **marked**: turns the Markdown answer into HTML
- **DOMPurify**: removes anything dangerous from that HTML before it is shown
- **html2pdf**: the "Download PDF" button

Then it loads `static/script.js`.

### Step 2.2: Remembering the conversation

The first line of `script.js`:

```js
let currentThreadId = localStorage.getItem("travel_thread_id") || null;
```

The browser remembers your `thread_id`, so later requests continue the same conversation in the database.

### Step 2.3: Clicking "Generate Plan": `sendMessage()` (line 242)

1. Reads your text from the box. If it is empty, it shows an error and stops.
2. `setLoading(true)` shows the spinner and disables the buttons.
3. `postJSON("/api/travel", {message, thread_id, human_review})`, where `human_review` comes from the "Let me review flights & hotels" checkbox.
4. `handleResponse(data)` (line 203) saves the `thread_id` and then:
   - `status == "needs_review"` calls `showReview()`, which shows the review panel
   - otherwise it calls `showResult()`, which shows the final answer

Pressing **Ctrl+Enter** also calls `sendMessage()` (the `keydown` listener at the end of the file).

---

## Part 3. The API: `POST /api/travel`

`travel_planner()` in `app.py` (line 102):

1. Strips the message. If it is empty, it returns HTTP 400.
2. Calls `run_travel_agent(user_input, thread_id, human_review)` from `backend.py`.
3. Returns `{"success": true, ...result}`.
4. Any exception goes to `error_response()`, which prints the traceback and returns HTTP 500 with the message.

**Why `def` and not `async def`?** The graph is slow, synchronous code (LLM and API calls). FastAPI runs plain `def` endpoints in a worker thread, so one long request does not freeze the server for everyone else.

---

## Part 4. `backend.run_travel_agent()`: starting a request

`backend.py` line 109:

```python
def run_travel_agent(user_input, thread_id=None, human_review=True):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"
    result = travel_graph.invoke(
        new_request_state(user_input, review_enabled=human_review),
        config=thread_config(thread_id),
    )
    return build_response(thread_id, result)
```

1. **New conversation?** It creates a random `thread_id`.
2. **`new_request_state()`** (`workflow.py` line 99) builds the starting state. Because one thread is reused for many requests, it resets *every* per-request field (`plan=None`, `completed=[]`, results empty, `revisions=0`, ...). Only `messages` keeps growing as chat history.
3. **`travel_graph.invoke(state, config)`** runs the graph until it ends or pauses. `config = {"configurable": {"thread_id": ...}}` tells the checkpointer where to save.
4. **`build_response()`** (line 161) turns the final state into the JSON reply:
   - If the result contains `__interrupt__`, the graph paused for review, so it returns `status: "needs_review"` plus the flights, hotels and trip to show.
   - Otherwise it returns `status: "done"` plus `answer`, `trip`, `agents_run`, `budget`, `guardrail`, and the other fields.

---

## Part 5. The shared state: `state.py`

### `TravelState` (line 175)

A `TypedDict`, meaning a dictionary with known keys. Grouped by purpose:

| Group | Fields | Written by |
| --- | --- | --- |
| Request | `user_query`, `messages`, `review_enabled` | `new_request_state()` |
| Plan | `trip`, `plan`, `completed`, `next_agent` | supervisor and every agent |
| Results | `flight_results`, `hotel_results`, `weather`, `local_tips`, `itinerary`, `budget` | the six specialists |
| Safety and review | `guardrail`, `guardrail_notes`, `final_answer`, `feedback`, `revisions` | guardrails and `human_review` |
| Counters | `llm_calls` | every node that calls the LLM |

`messages` is declared as `Annotated[list[AnyMessage], operator.add]`. That `operator.add` is a **reducer**: when a node returns `{"messages": [x]}`, LangGraph *appends* `x` instead of replacing the list. Every other field is simply overwritten.

### `AGENT_ORDER` (top of the file)

```python
["flight_agent", "hotel_agent", "weather_agent", "local_guide_agent", "itinerary_agent", "budget_agent"]
```

The order agents always run in, so each agent finds the results it depends on: the itinerary needs flights and hotels; the budget needs the itinerary. `AgentName` is the same list as a `Literal` type, which forces the LLM to choose only valid names.

### `TripDetails` (line 56)

What the supervisor extracts from your sentence: `origin`, `destination`, `duration_days`, `budget`, `currency`, `travelers`, `interests`, `hotel_preferences`. Each field has a `description`; those descriptions are sent to the LLM as instructions.

Its **validators** (lines 98-128) clean up bad LLM output instead of failing:

| Validator | Example |
| --- | --- |
| `normalise_currency` | `" usd "` becomes `USD`; anything that is not 3 letters becomes `EUR` |
| `clamp_duration` | `90` becomes `60`; `0` or `"a week"` becomes `None` |
| `positive_budget` | `-5` becomes `None` |
| `clamp_travelers` | `0` becomes `1`; `50` becomes `20` |

`_number()` (line 47) converts a value to a number and returns `None` instead of crashing on text.

### `SupervisorDecision` (line 131)

What the supervisor's LLM call must return: `is_travel_request`, `trip` (a `TripDetails`), `agents` (a list of `AgentName`) and `reasoning`.

### `BudgetLine` and `BudgetEstimate` (lines 147-172)

The budget agent's output: a list of lines (`category`, `amount_eur`, `note`) plus `assumptions`. `non_negative` turns negative costs into 0.

---

## Part 6. Wiring the graph: `workflow.py`

`build_graph()` (line 60) creates the graph:

```python
graph.add_node("input_guardrail", input_guardrail)
graph.add_node("supervisor", supervisor_agent)
... six specialists, human_review, responder, output_guardrail, blocked_response

graph.add_edge(START, "input_guardrail")
graph.add_conditional_edges("input_guardrail", route_after_input, ["supervisor", "blocked_response"])
graph.add_conditional_edges("supervisor", route, [*SPECIALISTS, "human_review", "responder", "blocked_response"])
for each specialist:  graph.add_edge(name, "supervisor")      # always report back
graph.add_edge("human_review", "supervisor")
graph.add_edge("responder", "output_guardrail")
graph.add_edge("output_guardrail", END)
graph.add_edge("blocked_response", END)
```

Picture a **hub and spokes**. The supervisor is the hub; each specialist is a spoke that always returns to the hub, and the hub decides the next spoke. The line `assert list(SPECIALISTS) == AGENT_ORDER` stops the program at startup if someone adds an agent in one place and forgets the other.

---

## Part 7. The request, node by node

The example used below is a full trip with review on: *"Plan 7 days from Berlin to Nice under 1500 euros"*. These are the 19 steps actually recorded from a real run.

### Step 1: `input_guardrail` (`agents/guardrails.py` line 158)

Runs before any LLM call. `check_input()` (line 74) returns a reason to block, or `None`:

1. Empty after stripping spaces → `"empty"`
2. Longer than `MAX_INPUT_CHARS` (1500) → `"too_long"`
3. Matches one of `INJECTION_PATTERNS` (regular expressions such as *ignore ... previous ... instructions* or *reveal ... system prompt*) → `"prompt_injection"`
4. Contains a card number → `"card_number"`. `contains_card_number()` finds runs of 13-19 digits, and `luhn_valid()` checks the Luhn checksum that every real card number passes, so ordinary phone numbers usually don't trigger it.

The node writes `guardrail = {"blocked": True/False, "reason": ...}`. Then the conditional edge `route_after_input()` sends the request to `blocked_response` or to `supervisor`.

**`blocked_response`** (line 172) looks up a fixed polite message in `BLOCK_MESSAGES` and stores it as `final_answer`. No LLM is used, which is why a blocked request costs nothing.

### Step 2: `supervisor`, the first visit, which plans (`agents/supervisor.py`)

`supervisor_agent()` (line 43) runs many times per request:

```python
if state["plan"] is None:          # first visit only
    update = plan_request(state)   # the ONE LLM call
...
update["next_agent"] = pick_next_agent(plan, completed)
```

**`plan_request()`** (line 64):

1. **`planning_request()`** (line 114) builds the text to send: your sentence, plus any change requests from the review.
2. **One structured-output call:**

   ```python
   decision = get_llm().with_structured_output(SupervisorDecision).invoke([
       SystemMessage(SUPERVISOR_PROMPT), HumanMessage(request_text)])
   ```

   `SUPERVISOR_PROMPT` (line 23) describes the six agents and when to pick each. The model returns a `SupervisorDecision` object, already validated by Pydantic.
3. **Fallback:** if the call fails (bad JSON, model error), the `except` block plans *every* agent. Slower, but you still get an answer.
4. **Off-topic:** if `is_travel_request` is false, it returns an empty plan with `guardrail = {"blocked": True, "reason": "off_topic"}`. The supervisor then routes to `blocked_response`.
5. **Sort the plan:** `[agent for agent in AGENT_ORDER if agent in chosen]` keeps only the chosen agents, in the fixed order, whatever order the LLM listed them in.
6. **`with_review_step()`** (`agents/review.py` line 39) inserts `"human_review"` just before the itinerary/budget, if review is on, there are fewer than 3 revisions, and the plan has both research (flights or hotels) and work that builds on it (itinerary or budget).
7. Returns `trip` (as a dict), `plan`, `llm_calls + 1` and a log message.

For the example, the plan is: `flight, hotel, weather, local_guide, human_review, itinerary, budget`.

**Routing on every visit:** `pick_next_agent()` (line 124) returns the first agent in the plan that is not yet in `completed`, or `"responder"` when all are done. `route()` (line 133) just reads `state["next_agent"]`; it is the function the conditional edge calls.

### Step 3: `flight_agent` (`agents/flight.py`)

```python
if trip has origin and destination:
    query = f"from {origin} to {destination}"    # e.g. "from Berlin to Nice"
else:
    query = state["user_query"]
return {"flight_results": run_tool("search_flights", query=query, limit=5),
        "completed": mark_done(state, "flight_agent"), ...}
```

- `run_tool()` sends the call through MCP (Part 8).
- `mark_done()` returns `completed + ["flight_agent"]`, so the supervisor knows this agent has finished.

**Inside `tools/flight_tool.py`**, which is what the tool actually runs:

1. **`parse_route(query)`** (line 394) finds the departure and arrival airports by trying patterns in order: words like "global flights" → `"DAC NRT"`-style 3-letter codes → *from X to Y* → *to Y from X* → *from X* → *to X* → any countries or cities mentioned.
2. **`resolve_location_to_iata(place)`** (line 279) turns a place into an airport code: a 3-letter code is kept as it is, then known cities (`CITY_MAIN_AIRPORT`, e.g. berlin → BER), then countries (`COUNTRY_MAIN_AIRPORT`, e.g. Japan → NRT), then a scored search of the `airportsdata` airport database.
3. **`search_flights()`** (line 554) calls `https://api.aviationstack.com/v1/flights` with `dep_iata` and `arr_iata`, then formats each flight with `format_flight()`. AviationStack gives live flight *status*, not ticket prices, and the text says so.

Errors such as a missing key or an API error come back as *text*, not exceptions.

### Step 4: `supervisor` again, routing only

The plan already exists, so there is no LLM call. `pick_next_agent()` returns `hotel_agent`. This repeats between every pair of agents (steps 4, 6, 8, 10, 13, 15 and 17), and each of these visits takes milliseconds.

### Step 5: `hotel_agent` (`agents/hotel.py`)

Builds `"Best hotels in Nice"`, adding `" (budget, near the beach)"` if `hotel_preferences` was extracted, then calls `run_tool("web_search", ...)`.

**`tools/tavily_tool.py`:** `get_client()` creates the `TavilyClient` the first time it is needed, not when the file loads. That matters because the MCP server loads every tool file: if the client were created at load time, a missing Tavily key would crash the server and break *all* tools (this was a real bug, found while writing this guide). Now a missing key only makes web search say "unavailable". `tavily_search()` asks for 5 results and formats each one as a number, title, URL and a snippet cut to 300 characters.

### Step 7: `weather_agent` (`agents/weather.py`)

Calls `run_tool("weather_forecast", location=destination)`, or writes "Weather unavailable" if there is no destination.

**`tools/weather_tool.py`:**

1. **`locate()`** (line 37) finds coordinates. It reuses `resolve_location_to_iata()` because airport records include latitude and longitude, and that works for countries too (France → CDG → Paris). If that fails, it asks Open-Meteo's geocoding API.
2. **`get_weather_forecast()`** (line 57) calls Open-Meteo for 7 days of `weather_code`, min/max temperature and rain chance, translates the codes with `WEATHER_CODES` (e.g. 63 → "Rain") and adds a note that this is a live forecast.

### Step 9: `local_guide_agent` (`agents/local_guide.py`)

1. Searches the web for *"Nice travel tips entry requirements local transport money etiquette for travelers from Berlin"*.
2. Calls the LLM to turn the results into short tips: entry/visa basics, getting around, money and etiquette, in under 250 words.
3. The search results are wrapped with **`as_data("web_search", ...)`**, and the system prompt ends with **`UNTRUSTED_DATA_RULE`** (both in `agents/common.py`). Part 9 explains why.

### Steps 10-12: `human_review`, the pause (`agents/review.py` line 60)

```python
answer = interrupt({"trip": ..., "flight_results": ..., "hotel_results": ..., "weather": ...,
                    "revision": revisions, "max_revisions": 3})
```

**`interrupt()` is the key line.** On the first run, it *stops the graph right here*. LangGraph has already saved the state in PostgreSQL. `invoke()` returns with an `__interrupt__` entry, and `build_response()` turns that into `status: "needs_review"` (step 11).

In the browser, `showReview()` (`script.js` line 174) shows flights and hotels. It deliberately uses `textContent`, never HTML, because this is raw web text.

When you click **Approve** or **Request changes**, `submitReview()` (line 276) calls `POST /api/travel/review`, which runs `resume_travel_agent()` (`backend.py` line 127):

1. **`travel_graph.get_state(config).interrupts`**: if nothing is waiting, it raises `ReviewError`, which becomes HTTP 400 "not waiting for a review".
2. If you asked for changes, the feedback must not be empty, and it goes through the **same `check_input()`** as a new message, because it will be sent to the LLM.
3. **`travel_graph.invoke(Command(resume={"approved": ..., "feedback": ...}), config)`** continues the paused run.

When resumed, **the `human_review` node runs again from its first line**, and this time `interrupt()` *returns your answer* instead of pausing (step 12):

- **Approved** (or no feedback): it marks `human_review` done, and the supervisor moves on to the itinerary.
- **Changes requested**: it adds the feedback (cut to 500 characters) to `feedback`, increases `revisions`, and resets `plan=None`, `completed=[]` and the research results. The supervisor therefore **plans again** (step 2), and its prompt now includes your feedback ("cheaper hotels near the beach" can set `hotel_preferences`). Research runs again and you are asked again. After 3 change requests, `with_review_step()` stops adding the pause.

Because the state is in PostgreSQL, you can approve even after the server has restarted. A test proves this (`test_paused_review_survives_a_restart`).

### Step 14: `itinerary_agent` (`agents/itinerary.py`)

One LLM call with your request, the trip details (`describe_trip()`), your change requests (`describe_feedback()`), and every research result wrapped in `<data>` tags. The instructions say to be budget-aware, plan indoor activities on bad-weather days, and show costs in euros. The answer (Markdown) goes into `itinerary`.

### Step 16: `budget_agent` (`agents/budget.py`)

1. **`user_budget_in_eur()`** (line 78): if your budget is in another currency, the `convert_currency` tool turns it into euros at today's European Central Bank rate (via the Frankfurter API) and writes a note such as "1000 USD is about 920 EUR".
2. **Structured LLM call** with `with_structured_output(BudgetEstimate)`: one line per category (flights, accommodation, food, ...).
3. **The total is computed in Python**, not by the LLM:

   ```python
   total = round(sum(line.amount_eur for line in estimate.lines), 2)
   within_budget = total <= budget_eur
   ```

   LLMs make arithmetic mistakes; code doesn't.
4. If the structured call fails, `budget = {"error": "A structured budget estimate was not available."}` and the answer simply has no budget table.

**`format_budget()`** (line 103) turns this into a Markdown table for the responder, plus a "within / OVER budget" line.

### Step 18: `responder_agent` (`agents/responder.py`)

The last LLM call. It receives everything (trip, feedback, all results in `<data>` tags, the budget table) and writes the final answer in fixed sections: Trip Summary, Flights, Hotels, Weather, Local Tips, Day-by-Day Itinerary, Estimated Budget, Final Recommendations. Sections whose data wasn't requested are skipped. It is told to use the budget table's total *exactly*.

### Step 19: `output_guardrail` (`agents/guardrails.py` line 183)

Checks the responder's message before you see it:

1. **`redact_secrets()`** (line 119) replaces anything that looks like a Groq key (`gsk_...`), a Tavily key (`tvly-...`), an OpenAI-style key, or a password inside a `postgresql://` URL with `[redacted]`.
2. **`budget_check_note()`** (line 136) appends a verdict computed in code: "✅ within your budget" or "⚠️ €150 over your budget".

The result is stored as `final_answer`; that is what the API returns.

### Back in the browser

`showResult()` (`script.js` line 131):

- `renderMarkdown()` runs the answer through `marked` and then `DOMPurify.sanitize()`, so any HTML the AI repeated from a web page can't run in your browser.
- It shows "Agents used: Supervisor → Flight → … → Responder" from `agents_run`, or "Stopped by guardrail: …" if the request was blocked.

---

## Part 8. How a tool call travels (MCP)

Every agent calls tools through **`run_tool()`** in `agents/common.py` (line 15):

```python
def run_tool(name, **arguments):
    try:
        return mcp_client.call_tool(name, **arguments)
    except Exception as e:
        return f"{name} unavailable: {e}"      # the run continues
```

A broken API therefore never crashes the whole request; the answer just says that part is unavailable.

### `tools/mcp_client.py`

The agents are normal synchronous Python, but the MCP library is `async`. The client bridges the two:

1. **`get_client()`** (line 137) creates one `MCPToolClient` that will start `python mcp_server.py` as a subprocess. It passes the environment variables, so the server gets your API keys.
2. **`connect()`** (line 58) starts a **background thread running an asyncio event loop**. On that loop, **`_hold_session()`** (line 77) opens the stdio connection and the MCP session, then waits forever. Keeping that one task alive keeps the connection open for the life of the app.
3. **`call(name, arguments)`** (line 118) sends `session.call_tool(...)` to the background loop with `run_coroutine_threadsafe()` and waits up to 90 seconds (`CALL_TIMEOUT`) for the answer. If the server reports an error (`is_error`), it raises `MCPToolError` with the real reason.
4. **`call_tool()`** (line 175) is the function agents use:
   - It tries MCP first.
   - If the *tool* failed (`MCPToolError`), it re-raises, and `run_tool()` turns that into a note.
   - If the *MCP server itself* is broken, it sets `_unavailable = True`, prints a warning, and from then on runs the tool **in-process** by importing `TOOLS` from `mcp_server.py`. `USE_MCP=false` in `.env` forces this mode.

### `mcp_server.py`

1. Loads `.env` and imports the four tool modules.
2. Defines five small functions: `search_flights`, `web_search`, `weather_forecast`, `convert_currency` and `lookup_airport`. **Their type hints and docstrings become the tool schemas** other MCP clients see.
3. **`report_errors()`** (line 78) wraps each tool. The MCP library hides the reason for unexpected errors, so the wrapper converts every exception into a `ToolError` that carries the real message (e.g. "invalid API key").
4. `server = MCPServer("tripmate-tools", ...)` registers all five with `server.tool()`.
5. When run directly, `server.run()` speaks MCP over stdin/stdout. That is why tools must never `print()`: stdout carries the protocol.

### `tools/currency_tool.py`

`convert_currency()` returns the amount unchanged if both currencies are the same. Otherwise it calls `https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR` and multiplies by the rate.

---

## Part 9. Safety, explained once

| Risk | Where it is handled | How |
| --- | --- | --- |
| Someone types "ignore your instructions" | `input_guardrail` | Regex patterns; blocked before any LLM call |
| Off-topic requests (homework, code) | `supervisor` | The `is_travel_request` field in its structured output |
| Card numbers pasted in | `input_guardrail` | 13-19 digits that pass the Luhn checksum |
| **A web page containing hidden instructions** (prompt injection through tool output) | `as_data()` + `UNTRUSTED_DATA_RULE` in `agents/common.py` | Tool text is wrapped in `<data source="...">...</data>`; every system prompt says text inside `<data>` is information, never instructions. `as_data()` also breaks any `</data>` inside the text, so a page can't close the wrapper early |
| The LLM returns nonsense values | `state.py` validators | Values are coerced to safe ones |
| The LLM gets arithmetic wrong | `budget_agent`, `output_guardrail` | Totals and the budget verdict are computed in code |
| A secret leaks into the answer | `output_guardrail` | `redact_secrets()` |
| Malicious HTML in the answer | `script.js` | `DOMPurify`; review panel uses `textContent` |

**Not protected:** there is no login and no rate limit, and anyone who knows a `thread_id` could resume it. The regex rules can be bypassed by rephrasing.

---

## Part 10. The terminal version: `cli.py`

1. Asks for a request with `input()`.
2. Calls `run_travel_agent(..., thread_id="cli_user")`.
3. While the status is `needs_review`, it prints flights and hotels and asks you to press Enter to approve or type changes, then calls `resume_travel_agent()`.
4. Prints the final answer.

It uses the same `backend.py` as the web app, so it needs the same `.env`.

---

## Part 11. The tests: `tests/`

The tests never call the real AI or APIs, so they are fast, free and give the same result every time.

### `conftest.py`, the shared test tools

- **`FakeLLM`** stands in for `ChatGroq`:
  - `with_structured_output(schema).invoke(...)` returns a preset `SupervisorDecision` or `BudgetEstimate`, or raises an error if `fail_structured=True`.
  - `invoke(...)` returns `"fake answer 1"`, `"fake answer 2"`, … and records every prompt, so a test can check what was sent.
- **`fake_tools`** replaces `tools.mcp_client.call_tool` with a fake that records every tool call and returns fixed text. Because *every* agent reaches APIs only through this one function, a single replacement covers them all.
- **`decision(...)`** builds a supervisor decision in one line; **`run_graph(...)`** runs the graph with an in-memory checkpointer.
- **`reset_llm`** runs after every test and removes the fake model.

### What each test file proves

| File | Tests | Proves |
| --- | --- | --- |
| `test_supervisor.py` | 9 | All six agents run in order; only the needed agents run; the order follows `AGENT_ORDER` not the LLM; fallback runs everything; a reused thread starts fresh; German cities map to the right airports |
| `test_agents.py` | 9 | Budget total is computed in code; the Tavily client is only created when first used; currency conversion; budget table formatting; a failed tool becomes a note; weather and currency tools format real API responses correctly (with fake HTTP) |
| `test_guardrails.py` | 18 | Normal requests pass; injections, long input and card numbers are blocked *without any LLM call*; off-topic refusal; secrets redacted; budget verdict; the `<data>` wrapper can't be closed early; validators |
| `test_review.py` | 8 | The graph pauses after research; approval continues; changes re-plan with the feedback; at most 3 revisions; no pause when review is off or not useful; hotel preferences reach the search |
| `test_mcp.py` | 5 | Starts the *real* MCP server: lists its tools, runs a tool, reports errors with reasons, falls back to in-process mode |
| `test_postgres_e2e.py` | 2 | With a real database (`TEST_DATABASE_URL`): the full API flow including bad feedback, and resuming after a simulated restart |

Run them with `python -m pytest`.

---

## Part 12. Running it in Docker

- **`Dockerfile`**: starts from `python:3.11-slim`, installs `requirements.txt`, copies the code, and runs `uvicorn app:app --host 0.0.0.0 --port 8000`.
- **`.dockerignore`**: keeps `.env`, `.git` and caches out of the image, so your keys are never baked in. You pass them at run time with `docker run --env-file .env -p 8000:8000 tripmate-ai`.

---

## Part 13. One request, summarised as state changes

| Step | Node | Main state change |
| --- | --- | --- |
| start | `new_request_state` | `user_query` set; `plan=None`, `completed=[]`, results empty |
| 1 | `input_guardrail` | `guardrail = {blocked: False}` |
| 2 | `supervisor` (LLM) | `trip = {origin: Berlin, destination: Nice, ...}`; `plan = [flight, hotel, weather, local_guide, human_review, itinerary, budget]`; `next_agent = flight_agent` |
| 3 | `flight_agent` | `flight_results`; `completed = [flight_agent]` |
| 4 | `supervisor` | `next_agent = hotel_agent` |
| 5-9 | hotel, weather, local guide (+ supervisor in between) | `hotel_results`, `weather`, `local_tips` |
| 10 | `supervisor` | `next_agent = human_review` |
| 11 | `human_review` | **pause**; API returns `needs_review` |
| 12 | `human_review` (resumed) | `completed += [human_review]` |
| 13-16 | itinerary, budget (+ supervisor) | `itinerary`; `budget = {lines, total_eur, within_budget, ...}` |
| 17 | `supervisor` | all done, so `next_agent = responder` |
| 18 | `responder` (LLM) | final message appended to `messages` |
| 19 | `output_guardrail` | `final_answer` (redacted, plus budget verdict) |

That is 5 LLM calls in total: supervisor, local guide, itinerary, budget and responder. Everything else is plain Python.

---

## Part 14. Every file, one by one

Parts 1-13 follow a request through the code. This part is the other view: every file in the repository, what it is for, and what is inside it. Every code file now also carries its own comments: a header block at the top saying what the file does, and comments on each function, helper and non-obvious line. Read this table to find a file, then read the file's own comments for the details.

The comments were added without changing any code. That was checked mechanically: every Python file's syntax tree is identical to before, every non-comment line of the JavaScript, HTML, CSS and config files is identical, and all 51 tests still pass.

### Application code

| File | What it is | What is inside |
| --- | --- | --- |
| `app.py` | The web server (FastAPI) | `TravelRequest` / `ReviewRequest` (the JSON bodies), `GET /` (the page), `GET /health`, `POST /api/travel`, `POST /api/travel/review`, and the `uvicorn.run(...)` block that starts the server on `127.0.0.1:8000`. Errors become JSON with `success: false`. |
| `backend.py` | The bridge between the API and the graph | Startup (load `.env`, certificates, `get_llm()`, database connection, `PostgresSaver`, compile the graph, start MCP), `get_database_url()`, `run_travel_agent()`, `resume_travel_agent()`, `ReviewError`, `thread_config()`, `build_response()`. |
| `workflow.py` | The graph wiring | `SPECIALISTS` (the six agents), `build_graph()` (nodes and edges), `new_request_state()` (resets every per-request field). |
| `state.py` | The data shapes | `AgentName`, `AGENT_ORDER`, `_number()`, `TripDetails` and its four validators, `SupervisorDecision`, `BudgetLine`, `BudgetEstimate`, `TravelState`. |
| `llm.py` | The shared model | `get_llm()` creates one `ChatGroq` (model from `GROQ_MODEL`, 4 retries) on first use; `set_llm()` lets tests swap in a fake. |
| `cli.py` | Terminal version | Asks for a request, runs it on thread `cli_user`, loops over the review (Enter = approve, text = changes), prints the answer. |
| `mcp_server.py` | The MCP tool server (its own process) | Five tool wrappers (`search_flights`, `web_search`, `weather_forecast`, `convert_currency`, `lookup_airport`), the `TOOLS` dict (also used for the in-process fallback), `report_errors()`, the `MCPServer` object and its registration loop. |

### Agents (`agents/`)

| File | Node(s) | LLM calls | What it does |
| --- | --- | --- | --- |
| `__init__.py` | - | - | Empty; marks the folder as a Python package. |
| `common.py` | - | - | Shared helpers: `run_tool()`, `UNTRUSTED_DATA_RULE`, `as_data()`, `describe_trip()`, `describe_feedback()`, `mark_done()`. |
| `guardrails.py` | `input_guardrail`, `blocked_response`, `output_guardrail` (+ router `route_after_input`) | 0 | Length / injection / card-number checks (`check_input`, `contains_card_number`, `luhn_valid`), `BLOCK_MESSAGES`, `redact_secrets()`, `budget_check_note()`. |
| `supervisor.py` | `supervisor` (+ router `route`) | 1 per request | `SUPERVISOR_PROMPT`, `supervisor_agent()`, `plan_request()`, `planning_request()`, `pick_next_agent()`. |
| `flight.py` | `flight_agent` | 0 | Builds "from X to Y" and calls the `search_flights` tool. |
| `hotel.py` | `hotel_agent` | 0 | Builds "Best hotels in X (preferences)" and calls `web_search`. |
| `weather.py` | `weather_agent` | 0 | Calls `weather_forecast` for the destination. |
| `local_guide.py` | `local_guide_agent` | 1 | Web search for entry, transport, money and etiquette, then the LLM writes short tips. |
| `review.py` | `human_review` | 0 | `with_review_step()` (where to pause), `human_review()` (the `interrupt()`, approve or reset for a re-plan), limits `MAX_REVISIONS = 3`, `MAX_FEEDBACK_CHARS = 500`. |
| `itinerary.py` | `itinerary_agent` | 1 | Day-by-day plan from all research, the trip details and the change requests. |
| `budget.py` | `budget_agent` | 1 | `budget_agent()` (structured `BudgetEstimate`, total added in Python), `user_budget_in_eur()`, `format_budget()` (Markdown table). |
| `responder.py` | `responder` | 1 | Writes the final Markdown answer from everything gathered. |

### Tools (`tools/`)

| File | Service | What is inside |
| --- | --- | --- |
| `__init__.py` | - | Empty; marks the folder as a Python package. |
| `mcp_client.py` | (talks to `mcp_server.py`) | `MCPToolError`, `MCPToolClient` (`connect`, `_hold_session`, `close`, `_run`, `list_tools`, `call`), `get_client()`, `mcp_enabled()`, `start()`, `call_tool()` with the in-process fallback. |
| `flight_tool.py` | AviationStack (key) | The place-name tables (`COUNTRY_ALIASES`, `COUNTRY_MAIN_AIRPORT`, `CITY_MAIN_AIRPORT`), `clean_text()`, `country_name_to_code()`, `airport_country_matches()`, `get_best_airport_for_country()`, `resolve_location_to_iata()`, `find_location_mentions()`, `parse_route()`, `format_flight()`, `search_flights()`. |
| `tavily_tool.py` | Tavily (key) | Lazy `get_client()` and `tavily_search()` (top 5 results, snippets cut to 300 characters). |
| `weather_tool.py` | Open-Meteo (free) | `WEATHER_CODES`, `locate()` (airport table first, then geocoding), `get_weather_forecast()`. |
| `currency_tool.py` | Frankfurter / ECB (free) | `convert_currency()`. |

### The web page

| File | What is inside |
| --- | --- |
| `templates/index.html` | Five parts: header, request form (text box, example chips, review checkbox), review panel, result panel (with Copy and Download PDF), error box. Loads `marked`, `DOMPurify` and `html2pdf.js` from CDNs, then `script.js`. |
| `static/script.js` | `setPrompt`, `setLoading`, `showError` / `hideError`, `formatAgentName`, `renderMarkdown` (sanitised), `describeTrip`, `showResult`, `showReview`, `handleResponse`, `postJSON`, `sendMessage`, `submitReview`, `copyResult` (clipboard, plain text), `downloadPDF` (html2pdf: A4, the white answer area), and the Ctrl+Enter shortcut. |
| `static/style.css` | The dark glass design: page background and glow circles, cards, text boxes, buttons, review grid, the white "paper" answer area and its tables, the spinner animation, print rules (only the answer is printed), and the phone layout (under 760px wide). |

### Configuration and packaging

| File | Purpose |
| --- | --- |
| `.env.example` | Template for `.env`: `DATABASE_URL`, `GROQ_API_KEY`, `GROQ_MODEL`, `AVIATIONSTACK_API_KEY`, `TAVILY_API_KEY`, `DEFAULT_ORIGIN_IATA`, plus the optional `USE_MCP` and `TEST_DATABASE_URL`. |
| `requirements.txt` | Exact package versions for the app. `langchain-community` and `langchain-tavily` are listed but not imported by the current code. |
| `requirements-dev.txt` | `requirements.txt` plus `pytest`. |
| `pytest.ini` | Lets tests import project modules and limits test discovery to `tests/`. |
| `Dockerfile` | Python 3.11 image: install the requirements, copy the code, run `uvicorn app:app` on `0.0.0.0:8000`. |
| `.dockerignore` | Keeps `.env`, `.git`, virtual environments and caches out of the image. |
| `.gitignore` | Standard Python ignore list; the important entry is `.env`. |
| `LICENSE` | MIT licence (from the original project). |

### Tests (`tests/`)

| File | What it proves |
| --- | --- |
| `conftest.py` | Provides `FakeLLM`, `decision()`, `run_graph()`, the `fake_tools` fixture, and resets the model after every test. |
| `test_supervisor.py` | Planning and routing: all six agents in order, only the needed agents, `AGENT_ORDER` wins over the LLM's order, fallback when planning fails, a reused thread starts fresh. |
| `test_agents.py` | Single agents and tools: budget total computed in code, currency conversion, Markdown budget table, weather formatting, a failing tool becomes a note, the lazy Tavily client. |
| `test_guardrails.py` | Input blocking, off-topic refusal, secret redaction, the code-computed budget check, the `<data>` fence, the Pydantic validators. |
| `test_review.py` | Pause after research, approve, change request and re-plan, the 3-revision limit, no pause when it is not useful. |
| `test_mcp.py` | Starts the real MCP server: tool list, calls, error reporting, `USE_MCP=false`, fallback when the server dies. |
| `test_postgres_e2e.py` | Through the HTTP API with a real PostgreSQL database (needs `TEST_DATABASE_URL`): the full review flow, and resuming a paused review after a "restart". |

### Documentation and diagrams

| File | What it is |
| --- | --- |
| `README.md` | Project overview, setup and screenshot. |
| `docs/CODE_WALKTHROUGH.md` | This document. |
| `docs/images/tripmate-home.webp` | The screenshot used in the README. |
| `docs/architecture/architecture.excalidraw` | Architecture views 0-6 (context, containers, graph, one request, data, trust). Generated by `gen.py`. |
| `docs/architecture/system-design.excalidraw` | Whiteboard-style system design. Generated by `system_design.py`. |
| `docs/architecture/interview-diagrams.excalidraw` | Interview views 7-14 (lifecycle, LLM calls, MCP sequence, failures, data model, latency, evaluation, deployment). Generated by `interview_diagrams.py`. |
| `docs/architecture/database.excalidraw` | The database: the four PostgreSQL checkpoint tables with every column, how they connect, and what one real conversation stores. Generated by `database_diagram.py` from the real schema. |
| `docs/architecture/gen.py`, `system_design.py`, `interview_diagrams.py`, `database_diagram.py` | The scripts that draw those diagrams from code (commented: how to read the coordinates, what each view shows). |
| `docs/architecture/excalidraw_lib.py` | The `Canvas` helper used by `interview_diagrams.py`. |
| `docs/architecture/verify.py` | Checks a diagram against the code (file paths exist; nodes, routes, tools, env vars and services are all shown). |
| `docs/architecture/graph-from-langgraph.mmd` | The graph as LangGraph itself draws it (Mermaid). |
| `docs/architecture/REPORT.md`, `INTERVIEW.md` | How the diagrams were made and checked, and the facts behind the interview views. |
| `demo.excalidraw` | The original project's demo drawing (an embedded screenshot and a short description). It is a data file, so it has no comments. |

---

## Where to change things

| You want to… | Change |
| --- | --- |
| Use a different model | `GROQ_MODEL` in `.env` |
| Change the default departure airport | `DEFAULT_ORIGIN_IATA` in `.env` |
| Add a seventh agent | Create `agents/<name>.py`; add it to `SPECIALISTS` (`workflow.py`), `AgentName` and `AGENT_ORDER` (`state.py`), and the agent list in `SUPERVISOR_PROMPT` (`agents/supervisor.py`) |
| Add a tool | Write the function in `tools/`, add a wrapper and register it in `mcp_server.py` (`TOOLS`), and call it with `run_tool("name", ...)` |
| Change how the answer looks | The section list in `agents/responder.py` |
| Allow longer messages | `MAX_INPUT_CHARS` in `agents/guardrails.py` |
| Allow more review rounds | `MAX_REVISIONS` in `agents/review.py` |
