"""AI system design interview diagrams for TripMate AI (Excalidraw).

Usage: python docs/architecture/interview_diagrams.py <out-dir>
Writes interview-diagrams.excalidraw (plus iv_view_<n>.json chunks for the MCP viewer).
Facts and measurements behind each view are listed in INTERVIEW.md.
"""
# -----------------------------------------------------------------------------
# How to read this script: views 7-14 for an AI system design interview, drawn
# with the Canvas helper from excalidraw_lib.py. c.view() starts a framed view;
# c.box(), c.text() and c.arrow() add elements at pixel positions relative to
# the view's corner (ox, oy). The labels carry the content; the numbers are
# only layout. The facts behind each view are documented in INTERVIEW.md.
# -----------------------------------------------------------------------------
import sys
from pathlib import Path

# Make `import excalidraw_lib` work from any folder (it sits next to this file).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from excalidraw_lib import BLUE, GRAY, GREEN, ORANGE, PURPLE, RED, TEAL, WHITE, YELLOW, Canvas  # noqa: E402

# One canvas; every element id starts with "iv".
c = Canvas("iv")
# The views sit on a grid: 2 columns (x positions) and 4 rows (y positions).
COLS, ROWS = (0, 1350), (0, 1050, 2100, 3150)

# ------------------------------------------------------------- 7 Request lifecycle
# View 7: the states one request moves through, and the arrows between them.
ox, oy = c.view(COLS[0], ROWS[0], 1200, 900, "7 - Request lifecycle (state machine)",
                "What state is a request in, and what does the API return in each one?")
rx = c.box(ox + 40, oy + 130, 190, 80, "received\nPOST /api/travel", BLUE)
sc = c.box(ox + 280, oy + 130, 190, 80, "screening\ninput_guardrail", RED)
pl = c.box(ox + 520, oy + 130, 190, 80, "planning\nsupervisor (LLM)", PURPLE)
rs = c.box(ox + 760, oy + 130, 220, 80, "researching\nflight, hotel,\nweather, local guide", GREEN, 15)
c.arrow(ox + 230, oy + 170, ox + 280, oy + 170)
c.arrow(ox + 470, oy + 170, ox + 520, oy + 170, "ok")
c.arrow(ox + 710, oy + 170, ox + 760, oy + 170)
bl = c.box(ox + 280, oy + 330, 190, 80, "blocked\npolite refusal", RED)
c.arrow(ox + 375, oy + 210, ox + 375, oy + 330, "unsafe", color="#ef4444")
c.arrow(ox + 560, oy + 210, ox + 470, oy + 340, "off-topic", color="#ef4444")
aw = c.box(ox + 760, oy + 320, 240, 100, "awaiting_review\ninterrupt(), state in DB\nAPI: status needs_review", YELLOW, 15)
c.arrow(ox + 870, oy + 210, ox + 870, oy + 320, "research done")
c.arrow(ox + 800, oy + 320, ox + 660, oy + 210, "changes (max 3)", dashed=True)
wr = c.box(ox + 760, oy + 540, 240, 90, "writing plan\nitinerary + budget (LLM)", PURPLE)
c.arrow(ox + 880, oy + 420, ox + 880, oy + 540, "approve")
an = c.box(ox + 500, oy + 545, 200, 80, "answering\nresponder (LLM)", PURPLE)
c.arrow(ox + 760, oy + 585, ox + 700, oy + 585)
ck = c.box(ox + 260, oy + 545, 200, 80, "checking\noutput_guardrail", RED)
c.arrow(ox + 500, oy + 585, ox + 460, oy + 585)
dn = c.box(ox + 40, oy + 545, 180, 80, "done\nAPI: status done", BLUE)
c.arrow(ox + 260, oy + 585, ox + 220, oy + 585)
c.arrow(ox + 300, oy + 410, ox + 160, oy + 545, "status done\n+ guardrail", color="#ef4444")
c.box(ox + 1010, oy + 450, 160, 130, "Review off, or no\nitinerary/budget\nrequested: no\npause", YELLOW, 14)
c.box(ox + 40, oy + 700, 560, 150,
      "Error state: any uncaught exception (e.g. Groq still failing after 4 retries,\n"
      "database down) returns HTTP 500 with the message.\n"
      "A new request on a paused thread starts fresh; the old pause is dropped\n"
      "(verified against LangGraph 1.2.2).", GRAY, 15, dashed=True)
c.box(ox + 640, oy + 700, 530, 150,
      "Talking point: the pause is just saved graph state. Any server\n"
      "can resume it later with Command(resume=...), even after a\n"
      "restart (tested: test_paused_review_survives_a_restart).", WHITE, 15)

# ------------------------------------------------------------- 8 LLM calls & context
# View 8: a table of every LLM call: what goes in, what comes out, and the safety checks.
ox, oy = c.view(COLS[1], ROWS[0], 1200, 900, "8 - LLM calls: context in, output out",
                "5 LLM calls per full trip. Model: GROQ_MODEL (default openai/gpt-oss-120b), max_retries=4.")
heads = ["Context sent", "Call", "Output", "Checks / fallback"]
xs, ws = [40, 380, 590, 830], [320, 190, 220, 340]
for h, x in zip(heads, xs):
    c.text(ox + x, oy + 110, h, 18, "#2563eb")
rows = [
    ("request + review feedback", "supervisor", "SupervisorDecision\n(structured)", "Pydantic coerces values;\nfailure -> run every agent"),
    ("web results in <data>", "local guide", "tips text\n(<= 250 words)", "tool failure -> note\ninstead of results"),
    ("trip, feedback, flights,\nhotels, weather, tips in <data>", "itinerary", "day-by-day plan\n(markdown)", "none: error -> HTTP 500"),
    ("trip, flights, hotels,\nitinerary in <data>", "budget", "BudgetEstimate\n(structured lines)", "total summed in code;\nfailure -> 'unavailable'"),
    ("everything + budget table", "responder", "final answer\n(markdown)", "output guardrail: redact,\nbudget check in code"),
]
for i, row in enumerate(rows):
    y = oy + 150 + i * 120
    fills = [ORANGE, PURPLE, GREEN, RED]
    for j, (txt, x, w) in enumerate(zip(row, xs, ws)):
        c.box(ox + x, y, w, 90, txt, fills[j], 15)
        if j < 3:
            c.arrow(ox + x + w, y + 45, ox + xs[j + 1], y + 45)
c.text(ox + 40, oy + 760,
       "Every system prompt ends with UNTRUSTED_DATA_RULE: text inside <data> tags is information, never instructions.\n"
       "Structured outputs use function calling (with_structured_output). Token counts and cost are not tracked yet.", 15, "#555555")

# ------------------------------------------------------------- 9 Tool call over MCP
# View 9: a sequence diagram of one tool call, from the agent through MCP to the external API and back.
ox, oy = c.view(COLS[0], ROWS[1], 1200, 900, "9 - One tool call over MCP (sequence)",
                "Example: hotel_agent asks for web_search. Same path for every tool.")
lanes = [("Agent node\nagents/hotel.py", 40, PURPLE), ("run_tool()\nagents/common.py", 270, GREEN),
         ("MCP client thread\ntools/mcp_client.py", 500, GREEN), ("MCP server process\nmcp_server.py", 730, GREEN),
         ("External API\nTavily", 960, ORANGE)]
for label, x, fill in lanes:
    c.box(ox + x, oy + 110, 200, 60, label, fill, 14, dashed=(fill == ORANGE))
    c.line(ox + x + 100, oy + 170, ox + x + 100, oy + 760)
msgs = [(0, 1, "run_tool('web_search', query)", False), (1, 2, "call_tool() (sync)", False),
        (2, 3, "tools/call (JSON-RPC, stdio)", False), (3, 4, "HTTPS, timeout 15-30 s", False),
        (4, 3, "results", True), (3, 2, "text, or is_error + reason", True),
        (2, 1, "text, or raise MCPToolError", True), (1, 0, "text, or 'web_search unavailable: ...'", True)]
for i, (a, b, label, back) in enumerate(msgs):
    y = oy + 215 + i * 62
    x1, x2 = ox + lanes[a][1] + 100, ox + lanes[b][1] + 100
    c.arrow(x1, y, x2, y, label, dashed=back, fs=13)
c.box(ox + 40, oy + 770, 360, 110, "One server process per app, started\nat startup; one session held open by a\nbackground asyncio loop thread.", WHITE, 14)
c.box(ox + 420, oy + 770, 360, 110, "Measured: about 3 ms per call once\nconnected (excluding the API).\nCALL_TIMEOUT 90 s, CONNECT_TIMEOUT 60 s.", TEAL, 14)
c.box(ox + 800, oy + 770, 370, 110, "Server down -> tools run in-process\n(warning printed). USE_MCP=false\nforces it.", YELLOW, 14)

# ------------------------------------------------------------- 10 Failure modes
# View 10: a table of what can fail, what the code does about it, and what the user sees.
ox, oy = c.view(COLS[1], ROWS[1], 1200, 900, "10 - Failure modes and fallbacks",
                "What breaks, how the code notices, and what the user sees.")
for h, x in zip(["What fails", "What the code does", "What the user sees"], [40, 380, 800]):
    c.text(ox + x, oy + 105, h, 18, "#2563eb")
fails = [
    ("Groq rate limit / 5xx", "SDK retries, honouring retry-after\n(max_retries=4)", "slower answer; if still failing: error"),
    ("Model retired (404)", "nothing automatic", "error until GROQ_MODEL is changed\n(happened: llama-3.3-70b-versatile)"),
    ("Supervisor output malformed", "catch, plan = every agent", "full plan, a little slower"),
    ("Budget output malformed", "catch, budget = 'unavailable'", "answer without the budget table"),
    ("API down or bad key", "ToolError over MCP -> run_tool note", "'... unavailable' line, rest of plan"),
    ("MCP server won't start", "start() fails -> in-process tools", "nothing (warning in the console)"),
    ("Server restart during review", "state is in PostgreSQL", "Approve still works (tested)"),
    ("PostgreSQL unreachable", "fail fast at startup; else HTTP 500", "app won't start / error message"),
    ("Unsafe or off-topic input", "input guardrail / supervisor flag", "polite refusal, no agents run"),
]
for i, (what, how, sees) in enumerate(fails):
    y = oy + 140 + i * 82
    c.box(ox + 40, y, 320, 66, what, RED, 15)
    c.box(ox + 380, y, 400, 66, how, YELLOW, 14)
    c.box(ox + 800, y, 370, 66, sees, BLUE, 14)
    c.arrow(ox + 360, y + 33, ox + 380, y + 33)
    c.arrow(ox + 780, y + 33, ox + 800, y + 33)

# ------------------------------------------------------------- 11 Data model
# View 11: the data shapes (TravelState, TripDetails, SupervisorDecision, BudgetEstimate, API JSON, database).
ox, oy = c.view(COLS[0], ROWS[2], 1200, 900, "11 - Data model and contracts",
                "Typed schemas in state.py, the API contract in app.py and backend.py, storage in PostgreSQL.")
ts = c.box(ox + 40, oy + 120, 360, 470,
           "TravelState (graph state)\n\nuser_query, messages\ntrip: TripDetails (as dict)\nplan, completed, next_agent\n"
           "flight_results, hotel_results\nweather, local_tips, itinerary\nbudget: {lines, total_eur,\n  budget_eur, within_budget}\n"
           "guardrail, guardrail_notes\nreview_enabled, feedback, revisions\nfinal_answer, llm_calls", PURPLE, 15)
td = c.box(ox + 460, oy + 120, 330, 200,
           "TripDetails\norigin, destination\nduration_days (1-60)\nbudget (> 0), currency (ISO)\ntravelers (1-20)\ninterests, hotel_preferences", GREEN, 15)
sd = c.box(ox + 840, oy + 120, 320, 140, "SupervisorDecision\nis_travel_request\ntrip: TripDetails\nagents: AgentName[]\nreasoning", GREEN, 15)
be = c.box(ox + 460, oy + 370, 330, 140, "BudgetEstimate\nlines: BudgetLine[]\n  (category, amount_eur >= 0, note)\nassumptions", GREEN, 15)
c.arrow(ox + 840, oy + 190, ox + 790, oy + 210, "trip")
c.arrow(ox + 460, oy + 220, ox + 400, oy + 230, "stored")
c.arrow(ox + 460, oy + 440, ox + 400, oy + 440, "+ totals\nin code", fs=13)
api = c.box(ox + 840, oy + 300, 320, 290,
            "API contract\n\nPOST /api/travel\n{message, thread_id?, human_review}\n\nPOST /api/travel/review\n{thread_id, approved, feedback?}\n\n"
            "reply: status needs_review\n  {review: flights, hotels, trip}\nor status done {answer, budget,\n  agents_run, guardrail, ...}", BLUE, 14)
pg = c.box(ox + 40, oy + 640, 560, 150,
           "PostgreSQL (langgraph-checkpoint-postgres)\ncheckpoints, checkpoint_writes, checkpoint_blobs,\ncheckpoint_migrations\n"
           "key: thread_id. A full trip wrote 20 checkpoint rows.", TEAL, 15)
c.arrow(ox + 220, oy + 590, ox + 220, oy + 640, "saved after every node")
c.box(ox + 640, oy + 640, 520, 150,
      "Validators coerce bad LLM values instead of failing\n(e.g. currency 'euros' -> EUR, 90 days -> 60).\n"
      "Nothing is ever deleted: no retention policy yet.", YELLOW, 15)

# ------------------------------------------------------------- 12 Latency & cost
# View 12: the slowest path through a request, and ideas to make it faster or cheaper.
ox, oy = c.view(COLS[1], ROWS[2], 1200, 900, "12 - Latency and cost: critical path",
                "Every step runs one after another. Purple = LLM call, orange = external API.")
path = [("guard", RED), ("supervisor\nLLM", PURPLE), ("flights\nAPI", ORANGE), ("hotels\nAPI", ORANGE),
        ("weather\nAPI", ORANGE), ("guide\nAPI + LLM", PURPLE), ("YOU\nreview", YELLOW), ("itinerary\nLLM", PURPLE),
        ("budget\nLLM", PURPLE), ("responder\nLLM", PURPLE), ("guard", RED)]
for i, (label, fill) in enumerate(path):
    x = ox + 40 + i * 104
    c.box(x, oy + 130, 92, 80, label, fill, 13)
    if i:
        c.arrow(x - 12, oy + 170, x, oy + 170)
c.box(ox + 40, oy + 250, 540, 200,
      "Measured (fake LLM and APIs, n=20 runs):\n- app overhead per full trip: median 25 ms\n  with in-memory state\n"
      "- with local PostgreSQL: median 80 ms\n  (p95 121 ms): saving state costs about 55 ms\n- MCP tool call overhead: about 3 ms\n- LLM calls per full trip: 5", TEAL, 15)
c.box(ox + 620, oy + 250, 540, 200,
      "NOT measured (sandbox can't reach them):\n- LLM latency and tokens per call\n- external API latency\n- cost per request\n"
      "So the real end-to-end time is unknown;\nthe LLM calls almost certainly dominate.", GRAY, 15, dashed=True)
c.text(ox + 40, oy + 485, "How to make it faster and cheaper (proposals, not built):", 18, "#2563eb")
ideas = [("Run the 4 research agents in\nparallel (LangGraph Send):\nthey don't depend on each other", GREEN),
         ("Stream the responder's\ntokens to the browser\n(time to first word)", GREEN),
         ("Cache tool results per\ndestination + day\n(weather, tips, hotels)", GREEN),
         ("Smaller model for the\nsupervisor and local guide;\nkeep the big one for planning", GREEN)]
for i, (label, fill) in enumerate(ideas):
    c.box(ox + 40 + i * 285, oy + 530, 265, 120, label, fill, 14, dashed=True)
c.box(ox + 40, oy + 690, 1120, 110,
      "Interview answer: 'The critical path is 5 sequential LLM calls plus 4 API calls. I'd measure first\n"
      "(tracing per node), then parallelise research, stream the answer, and cache. Our own overhead is\n"
      "about 80 ms, so the gains are in the model and API calls.'", WHITE, 15)

# ------------------------------------------------------------- 13 Evaluation & testing
# View 13: what the tests cover today, and which evaluations a production version would add.
ox, oy = c.view(COLS[0], ROWS[3], 1200, 900, "13 - Evaluation and testing",
                "What is tested today (51 pytest tests) and what an AI team would add.")
c.text(ox + 40, oy + 105, "Today", 20, "#2563eb")
c.box(ox + 40, oy + 140, 540, 90, "Browser click-through (Playwright, run by hand):\nreview -> changes -> approve, guardrail, mobile", BLUE, 14)
c.box(ox + 40, oy + 245, 540, 110,
      "Integration (7): real MCP server over stdio (5),\nFastAPI + real PostgreSQL incl. restart (2)\ntests/test_mcp.py, tests/test_postgres_e2e.py", TEAL, 14)
c.box(ox + 40, oy + 370, 540, 160,
      "Unit, fake LLM + fake tools (44):\nguardrails 18, supervisor 9, agents 9, review 8\nrouting, order, fallbacks, budget maths, validators,\n"
      "interrupt / resume / max revisions", GREEN, 14)
c.box(ox + 40, oy + 545, 540, 80, "Not covered: real LLM output quality.\nFake LLMs prove the plumbing, not the answers.", GRAY, 14, dashed=True)
c.text(ox + 620, oy + 105, "To add (proposals)", 20, "#2563eb")
evals = [("Routing eval: golden set of requests\n-> expected agents; measure accuracy", PURPLE),
         ("Answer quality: LLM-as-judge rubric\n(fits budget, uses the research, no\ninvented flights) on a fixed set", PURPLE),
         ("Red-team set for guardrails:\ninjection pass rate, false refusals", RED),
         ("Online: approval rate at review,\nchange-request rate, p50/p95 latency,\ncost per trip, thumbs up/down", BLUE)]
for i, (label, fill) in enumerate(evals):
    c.box(ox + 620, oy + 140 + i * 125, 540, 105, label, fill, 14, dashed=True)
c.box(ox + 40, oy + 670, 1120, 120,
      "Interview answer: 'Unit tests with a fake LLM make the graph deterministic, so routing, fallbacks and\n"
      "guardrails are tested on every commit. LLM quality needs a separate eval set, scored by rules and an\n"
      "LLM judge, run before changing the model or prompts.'", WHITE, 15)

# ------------------------------------------------------------- 14 Deployment & scaling
# View 14: how it is deployed today, and how it would scale behind a gateway.
ox, oy = c.view(COLS[1], ROWS[3], 1200, 900, "14 - Deployment today, and how it would scale",
                "Solid = what exists. Dashed = proposal, not built.")
c.text(ox + 40, oy + 105, "Today", 20, "#2563eb")
dev = c.box(ox + 40, oy + 140, 340, 130, "Laptop: python app.py\n127.0.0.1:8000 (local only)\n+ MCP server subprocess", PURPLE, 15)
dock = c.box(ox + 40, oy + 290, 340, 130, "Docker: uvicorn app:app\n0.0.0.0:8000 (whole network)\n+ MCP server subprocess", PURPLE, 15)
sb = c.box(ox + 460, oy + 210, 280, 130, "Supabase PostgreSQL\n(session pooler)\nall graph state", TEAL, 15)
c.arrow(ox + 380, oy + 205, ox + 460, oy + 250, "SQL")
c.arrow(ox + 380, oy + 355, ox + 460, oy + 310, "SQL")
c.box(ox + 790, oy + 140, 370, 280,
      "Limits found in the code:\n- one psycopg connection shared by\n  all worker threads (psycopg_pool is\n  installed but unused)\n"
      "- no auth, no rate limit\n- no tracing\n- checkpoints never deleted", RED, 15, dashed=True)
c.text(ox + 40, oy + 450, "Scaled out (proposal)", 20, "#2563eb")
gw = c.box(ox + 40, oy + 490, 250, 120, "API gateway:\nauth, rate limits,\nTLS", BLUE, 15, dashed=True)
for i in range(3):
    c.box(ox + 360 + i * 20, oy + 480 + i * 20, 260, 120, "App replica\n(FastAPI + graph\n+ MCP server)", PURPLE, 15, dashed=True)
c.arrow(ox + 290, oy + 550, ox + 360, oy + 550)
c.box(ox + 720, oy + 490, 220, 120, "Managed Postgres\n+ connection pool", TEAL, 15, dashed=True)
c.arrow(ox + 660, oy + 550, ox + 720, oy + 550)
c.box(ox + 960, oy + 490, 200, 120, "Tracing\n(OpenTelemetry\nor LangSmith)", GRAY, 15, dashed=True)
c.box(ox + 40, oy + 660, 1120, 130,
      "Interview answer: 'Replicas are stateless: every graph state lives in Postgres under its thread_id, so any\n"
      "replica can resume a paused review. Scale by adding replicas behind a gateway, pool the DB connections,\n"
      "and let the gateway handle auth and rate limits. The LLM provider's rate limit is the real ceiling.'", WHITE, 15)

# Run as a script: write the per-view JSON files and the .excalidraw file, then print a summary.
if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    c.save_views(out, "iv")
    n = c.save_native(out / "interview-diagrams.excalidraw")
    print("views:", len(c.views), "elements per view:", [len(v) for v in c.views], "native:", n)
