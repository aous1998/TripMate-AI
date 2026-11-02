# TripMate AI: system design interview pack

Fifteen diagrams in three Excalidraw files (open them at https://excalidraw.com, via **Open**):

| File | Views |
| --- | --- |
| `architecture.excalidraw` | 0 Read this first, 1 Context, 2 Containers, 3 The graph, 4 One request, 5 Data and state, 6 Trust and safety |
| `interview-diagrams.excalidraw` | 7 Request lifecycle, 8 LLM calls, 9 Tool call over MCP, 10 Failure modes, 11 Data model, 12 Latency and cost, 13 Evaluation, 14 Deployment and scaling |
| `system-design.excalidraw` | One-page whiteboard version: goals, rules, the whole flow |

Solid boxes are what the code does today. Dashed boxes are either unverified (external services the sandbox could not reach) or proposals that are not built, and each view says which.

## A typical AI system design interview, in order

| # | The interviewer asks | Show | Say (and be ready to defend) |
| --- | --- | --- | --- |
| 1 | "What are you building, for whom?" | system-design, view 0 | One sentence in, a full trip plan out. The user approves research before planning. Numbers are never invented. |
| 2 | "Draw the high-level architecture." | views 1, 2 | Browser, one FastAPI process running a LangGraph graph, an MCP tool server subprocess, PostgreSQL for state, Groq for the LLM, four external APIs. |
| 3 | "Why multi-agent? How do agents coordinate?" | view 3 | A supervisor makes one structured-output call to extract typed trip details and pick agents, then routes in code. Plan once, route deterministically: cheaper and more predictable than asking the LLM after every step. Order is fixed by `AGENT_ORDER`, so dependencies are always met. |
| 4 | "Walk me through one request." | view 4 | Nineteen steps from a real traced run, including the pause for review and a real tool failure that became a note. |
| 5 | "What are the states of a request? How does human-in-the-loop work?" | view 7 | `interrupt()` saves the graph state in PostgreSQL and the API returns `needs_review`. `Command(resume=...)` continues it on any server, even after a restart (tested). Max 3 change requests. |
| 6 | "What goes into each LLM call? How do you get reliable structured output?" | view 8 | 5 calls per full trip. Two use structured output (Pydantic schemas via function calling), validated and coerced. The budget total is computed in code, not by the LLM. Tool output is fenced in `<data>` tags. |
| 7 | "How do agents use tools?" | view 9 | Every API sits behind an MCP server. One stdio session is kept open by a background event-loop thread, so sync agents call tools like functions (about 3 ms overhead measured). Tool errors come back with their reason. |
| 8 | "What happens when things fail?" | view 10 | Retries with retry-after for the LLM, a fallback plan if structured output breaks, tool failures degrade to notes, in-process tools if MCP is down, fail fast if the DB is missing. A retired model (which happened) needs a config change. |
| 9 | "How do you handle safety and prompt injection?" | view 6 | Input rules before any LLM call, an off-topic flag in the supervisor's output, `<data>` fencing for web text, validators on structured output, secret redaction and a code-computed budget check on the answer, DOMPurify in the browser. Also say what is NOT covered: no auth, no rate limits, regex rules can be rephrased around. |
| 10 | "Show me your data model and API." | views 5, 11 | `TravelState`, `TripDetails`, `SupervisorDecision`, `BudgetEstimate`; two endpoints; checkpoints keyed by `thread_id`. No retention policy yet. |
| 11 | "What's your latency? Where does the time go? What does it cost?" | view 12 | Measured: about 25 ms of app overhead per full trip in memory, about 80 ms with local PostgreSQL. LLM and API latency, tokens and cost were not measured. Say so. Then: parallel research, streaming, caching, smaller models where quality allows. |
| 12 | "How do you know it works? How do you evaluate an LLM system?" | view 13 | 50 pytest tests: deterministic unit tests with a fake LLM, plus real MCP and real PostgreSQL integration tests. The gap is LLM answer quality. Proposed: routing eval on a golden set, LLM-as-judge rubric, red-team set, online metrics. |
| 13 | "How would you deploy and scale it?" | view 14 | Today one process, one shared DB connection. App replicas are stateless (state is in Postgres by `thread_id`), so: gateway with auth and rate limits, N replicas, a connection pool, tracing. The LLM provider's rate limit is the real ceiling. |

## Measurements behind the numbers

All from this repo, using `docs/architecture/` scripts and the test suite. The LLM and APIs were faked, so these are the app's own costs only.

| What | Value | How |
| --- | --- | --- |
| App overhead per full trip, in-memory state | median 25 ms, p95 30 ms | 20 runs, review on, `InMemorySaver` |
| Same, local PostgreSQL checkpointer | median 80 ms, p95 121 ms | 20 runs, `PostgresSaver` |
| MCP tool call overhead | about 3 ms | warm stdio session, `lookup_airport` |
| MCP server startup | about 2 s | first `list_tools()` |
| LLM calls per full trip | 5 | traced run (supervisor, local guide, itinerary, budget, responder) |
| Checkpoint rows per full trip | 20 | traced run, `checkpoints` table |
| Tests | 50 (43 unit, 7 integration) | `pytest --collect-only` with `TEST_DATABASE_URL` set |

Not measured: LLM latency, tokens, cost, external API latency, behaviour on Windows.

## Trade-offs worth naming

- **Plan once vs. ask the LLM every step.** One planning call plus code routing is cheap and testable, but cannot react to what an agent found (for example, skip hotels if no flights exist). An LLM-per-step supervisor could, at the cost of more calls and less predictability.
- **Sequential vs. parallel research.** The four research agents are independent and run one after another today. Running them in parallel (LangGraph `Send`) would cut latency.
- **MCP over stdio vs. direct calls.** MCP adds a process and about 3 ms per call, but gives one tool contract any MCP client can use, and isolates API code from the graph.
- **Regex input rules vs. an LLM classifier.** Rules are free and run before any LLM call, but can be bypassed; the supervisor's topic flag is a second layer. A dedicated moderation model would be the next step.
- **Human review default on.** Better plans and a natural place to catch bad research, at the cost of a second round trip for the user.

Rebuild the interview diagrams with `python docs/architecture/interview_diagrams.py <out-dir>`.
