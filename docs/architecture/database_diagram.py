"""Database diagram for TripMate AI (Excalidraw): the PostgreSQL checkpoint tables.

Usage: python docs/architecture/database_diagram.py <out-dir>
Writes database.excalidraw (plus db_view_<n>.json chunks for the Excalidraw MCP viewer).
"""
# -----------------------------------------------------------------------------
# The schema below was read from a real database (information_schema and
# pg_indexes) after langgraph-checkpoint-postgres 3.1.0 ran checkpointer.setup().
# The row counts in view 2 come from one real test conversation
# (tests/test_postgres_e2e.py: plan, pause for review, approve, finish).
#
# How to read this script: c.view() starts a framed view; table() draws a
# table as a coloured header plus a white body with one line per column.
# The x/y numbers are only layout (pixels, y grows downwards).
# -----------------------------------------------------------------------------
import sys
from pathlib import Path

# Make `import excalidraw_lib` work from any folder (it sits next to this file).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from excalidraw_lib import BLUE, GREEN, PURPLE, RED, TEAL, WHITE, YELLOW, Canvas  # noqa: E402

c = Canvas("db")
LINE = 22.5   # height of one text line at font size 18


def table(x, y, w, name, columns, fill=TEAL):
    """A table: header box with the name, body box with one line per column."""
    c.box(x, y, w, 46, name, fill, 20)
    body_h = len(columns) * LINE + 26
    # The body is a plain white rectangle (no label); the column lines are a separate,
    # left-aligned text element so they read like a list.
    c.cur.append({"type": "rectangle", "id": c.nid("tb"), "x": x, "y": y + 46, "width": w, "height": body_h,
                  "backgroundColor": WHITE, "fillStyle": "solid", "strokeColor": "#06b6d4"})
    c.text(x + 16, y + 59, "\n".join(columns), 18)
    return y + 46 + body_h   # bottom edge, for arrows


# ------------------------------------------------------------- View 1: the tables
ox, oy = c.view(0, 0, 1120, 840, "TripMate database: LangGraph checkpoint tables",
                "PostgreSQL (Supabase). Created by checkpointer.setup() in backend.py. PK = part of the primary key.")

cp_bottom = table(ox + 40, oy + 120, 470, "checkpoints   (one row per graph step)", [
    "thread_id  PK  text  - the conversation",
    "checkpoint_ns  PK  text  - '' (no subgraphs)",
    "checkpoint_id  PK  text  - one per step",
    "parent_checkpoint_id  text  - step before",
    "type  text",
    "checkpoint  jsonb  - the state snapshot",
    "metadata  jsonb  - {source, step, ...}",
])

table(ox + 600, oy + 120, 480, "checkpoint_blobs   (list / dict values)", [
    "thread_id  PK  text",
    "checkpoint_ns  PK  text",
    "channel  PK  text  - a state key, e.g. messages",
    "version  PK  text  - new when the value changes",
    "type  text  - msgpack",
    "blob  bytea  - the value, serialised",
])
c.arrow(ox + 510, oy + 250, ox + 600, oy + 250, "versions", fs=16)

wr_top = oy + 470
table(ox + 40, wr_top, 470, "checkpoint_writes   (outputs of each node)", [
    "thread_id  PK  text",
    "checkpoint_ns  PK  text",
    "checkpoint_id  PK  text  - the step it belongs to",
    "task_id  PK  text  - the node run that wrote it",
    "idx  PK  integer  - order within the task",
    "channel  text  - state key, or __interrupt__",
    "type  text  - msgpack",
    "blob  bytea  - the written value",
    "task_path  text",
])
c.arrow(ox + 275, wr_top, ox + 275, cp_bottom, "checkpoint_id", fs=16)

table(ox + 600, oy + 470, 480, "checkpoint_migrations", [
    "v  PK  integer  - schema versions 0-9 applied",
], fill=YELLOW)

c.box(ox + 600, oy + 610, 480, 200,
      "How the tables connect (no foreign keys):\n"
      "the 3 data tables share the key thread_id\n"
      "(+ an extra index on it in each table).\n"
      "checkpoint.channel_versions names the blob\n"
      "(channel, version) of each list/dict value.\n"
      "parent_checkpoint_id chains the steps.", YELLOW, 18)

# ------------------------------------------------------------- View 2: one conversation
ox, oy = c.view(0, 1000, 1120, 840, "One conversation in the database (a real test run)",
                "Plan a week in Nice from Berlin -> pause for review -> approve -> final answer")

steps = [
    ("1. POST /api/travel\nthread_id = e2e_7074...", BLUE),
    ("2. graph.invoke(state, thread_id)\nruns node after node", PURPLE),
    ("3. After EVERY node: 1 checkpoint row,\nits writes, and blobs for changed lists/dicts", TEAL),
    ("4. human_review: interrupt()\nwrites __interrupt__, the run stops", YELLOW),
    ("5. POST /api/travel/review -> Command(resume)\nloads the latest checkpoint for thread_id,\nwrites __resume__, continues to the end", GREEN),
]
y = oy + 110
for i, (label, fill) in enumerate(steps):
    h = 110 if i == len(steps) - 1 else 90
    c.box(ox + 40, y, 520, h, label, fill, 18)
    if i < len(steps) - 1:
        c.arrow(ox + 300, y + h, ox + 300, y + h + 30)
    y += h + 30

c.box(ox + 620, oy + 110, 460, 130,
      "Rows for this one conversation:\n20 in checkpoints\n80 in checkpoint_writes\n26 in checkpoint_blobs", TEAL, 18)
c.box(ox + 620, oy + 270, 460, 190,
      "Stored inline in checkpoint (jsonb):\ntext, numbers, booleans, None\nuser_query, flight_results, hotel_results,\nweather, local_tips, itinerary, final_answer,\nnext_agent, llm_calls, revisions", WHITE, 18, stroke="#06b6d4")
c.box(ox + 620, oy + 490, 460, 130,
      "Stored in checkpoint_blobs (msgpack):\nlists and dicts\nmessages, plan, completed, trip, budget,\nguardrail, feedback, guardrail_notes", WHITE, 18, stroke="#06b6d4")
c.box(ox + 620, oy + 650, 460, 110,
      "Weak spots: rows are never deleted\n(add a cleanup job), and backend.py uses\none connection, not a pool.", RED, 18)


# Run as a script: write the per-view JSON files and the .excalidraw file.
if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    c.save_views(out, "db")
    n = c.save_native(out / "database.excalidraw")
    print("views:", len(c.views), "elements per view:", [len(v) for v in c.views], "native:", n)
