"""Whiteboard-style system design of TripMate AI (Excalidraw).

Usage: python docs/architecture/system_design.py docs/architecture
Writes system-design.excalidraw (plus sd_view_<n>.json chunks for the Excalidraw MCP viewer).
"""
import json, random, sys
from pathlib import Path

OUT = Path(sys.argv[1])
WHITE, PURPLE, GREEN, RED, ORANGE, TEAL, BLUE = (
    "#ffffff", "#e5dbff", "#b2f2bb", "#ffc9c9", "#ffd8a8", "#c3fae8", "#dbe4ff")
chunks, cur = [], None
_n = [0]


def nid(p):
    _n[0] += 1
    return f"sd{p}{_n[0]}"


def chunk(cam_x, cam_y, w=1200, h=900):
    global cur
    cur = [{"type": "cameraUpdate", "width": w, "height": h, "x": cam_x, "y": cam_y}]
    chunks.append(cur)


def shape(kind, x, y, w, h, label, fill=WHITE, stroke="#1e1e1e", fs=18, dashed=False):
    e = {"type": kind, "id": nid(kind[0]), "x": x, "y": y, "width": w, "height": h,
         "backgroundColor": fill, "fillStyle": "solid", "strokeColor": stroke,
         "label": {"text": label, "fontSize": fs}}
    if kind == "rectangle":
        e["roundness"] = {"type": 3}
    if dashed:
        e["strokeStyle"] = "dashed"
    cur.append(e)
    return e


def note(x, y, w, h, label, fs=16):
    """Red 'watch out' note, like the hand-drawn original."""
    e = shape("rectangle", x, y, w, h, label, WHITE, "#e03131", fs)
    e["label"]["strokeColor"] = "#e03131"
    return e


def text(x, y, s, fs=18, color="#1e1e1e"):
    cur.append({"type": "text", "id": nid("t"), "x": x, "y": y, "text": s, "fontSize": fs, "strokeColor": color})


def arrow(x1, y1, x2, y2, label=None, dashed=False, color="#1e1e1e", fs=16):
    e = {"type": "arrow", "id": nid("a"), "x": x1, "y": y1, "width": abs(x2 - x1), "height": abs(y2 - y1),
         "points": [[0, 0], [x2 - x1, y2 - y1]], "strokeColor": color, "strokeWidth": 2, "endArrowhead": "arrow"}
    if dashed:
        e["strokeStyle"] = "dashed"
    if label:
        e["label"] = {"text": label, "fontSize": fs}
    cur.append(e)


# --- requirements, written like the whiteboard notes --------------------------
chunk(330, -40)
text(450, 0, "TripMate AI - system design: how one trip request is handled", 28)
text(450, 60,
     "Goals:\n"
     "1. One sentence in -> flights, hotels, weather, local tips, day-by-day plan, budget in EUR\n"
     "2. The user approves the research before the plan is built\n"
     "3. Never invent numbers: budget totals are computed in code\n\n"
     "Scope: flights, hotels, weather, local tips, itinerary, budget\n\n"
     "Rules:\n"
     "1. Off-topic or unsafe input -> refused before any LLM call\n"
     "2. Agents run in a fixed order: research -> your review -> itinerary -> budget\n"
     "3. Max 3 change requests, then the plan continues\n"
     "4. Text from the web or APIs is data, never instructions\n\n"
     "Backend & DBs:\n"
     "PostgreSQL: graph state per thread_id (survives restarts)\n"
     "No vector DB: live data comes from APIs, not from documents", 20)

# --- entry: observability, channel, input guardrail --------------------------
chunk(150, 520)
shape("rectangle", 200, 590, 1500, 50,
      "Observability today: llm_calls, agents_run and guardrail_notes in every API reply   (no tracing or evals yet)", WHITE, fs=18)
note(300, 715, 240, 90, "no login or\nrate limit yet")
ch = shape("rectangle", 600, 700, 280, 120, "User channel:\nweb page (index.html)\nPOST /api/travel", BLUE)
shape("diamond", 1000, 660, 340, 200, "Input guardrail:\nlength limit\nprompt injection\ncard numbers (Luhn)", RED, fs=16)
arrow(880, 760, 1000, 760, "every message")
shape("rectangle", 1420, 715, 260, 90, "Blocked:\npolite refusal,\nno LLM call", RED, fs=16)
arrow(1340, 760, 1420, 760, "unsafe")

# --- supervisor, state, human review ------------------------------------------
shape("ellipse", 650, 950, 360, 190,
      "Supervisor agent:\n- extracts trip details\n  (structured output)\n- picks agents, routes\n  in a fixed order", PURPLE)
arrow(1170, 860, 960, 975, "allowed")
shape("rectangle", 150, 980, 300, 130, "PostgreSQL\nstate saved after\nevery step\nkey: thread_id", TEAL)
arrow(650, 1045, 450, 1045, "save / load state", dashed=True)
shape("rectangle", 1450, 970, 300, 130, "Human in the loop:\napprove flights & hotels\nor request changes\n(max 3)", GREEN)
arrow(1010, 1020, 1450, 1020, "2. pause after research (interrupt)")
arrow(1450, 1075, 1005, 1075, "changes -> re-plan, research again", dashed=True)

# --- research agents and the MCP tool server ----------------------------------
chunk(80, 1080)
research = [("Flight agent\nlive flights", 150, GREEN), ("Hotel agent\nhotel ideas", 420, GREEN),
            ("Weather agent\n7-day forecast", 690, GREEN), ("Local guide agent\nentry, transport,\nmoney tips (LLM)", 960, PURPLE)]
for i, (label, x, fill) in enumerate(research):
    shape("ellipse", x, 1260, 240, 130, label, fill, fs=16)
    arrow(830, 1140, x + 120, 1260, "1. research (fixed order)" if i == 1 else None)
text(1100, 1150, "every agent reports back\nto the supervisor", 16, "#555555")
note(1230, 1270, 220, 90, "web text fenced\nin <data> tags:\nnever obey it")
shape("rectangle", 300, 1500, 700, 110,
      "MCP tool server (mcp_server.py)\nsearch_flights - web_search - weather_forecast\nconvert_currency - lookup_airport", GREEN, fs=16)
for (x1, x2) in [(270, 400), (540, 560), (810, 760), (1080, 920)]:
    arrow(x1, 1390, x2, 1500, "tool call (MCP, stdio)" if x1 == 540 else None, fs=14)
shape("rectangle", 1100, 1500, 420, 110, "AviationStack - Tavily\nOpen-Meteo - Frankfurter", ORANGE, dashed=True)
arrow(1000, 1555, 1100, 1555, "HTTPS")
text(300, 1622, "if a tool fails -> it becomes a note in the answer, the run continues", 16, "#555555")

# --- planning, answer and output guardrail ------------------------------------
chunk(200, 1300, 1600, 1200)
shape("ellipse", 1460, 1700, 280, 140, "Itinerary agent\nday-by-day plan\n(LLM)", PURPLE, fs=16)
arrow(1600, 1100, 1600, 1700, "3. approved -> plan")
shape("ellipse", 1020, 1700, 300, 150, "Budget agent\nitemised EUR estimate\n(LLM structured output)", PURPLE, fs=16)
arrow(1460, 1770, 1320, 1775, "uses the plan", fs=14)
arrow(1100, 1720, 950, 1612, "convert non-EUR budget", fs=14)
note(1020, 1880, 300, 80, "never trust LLM math:\ntotal = sum of lines, in code")
shape("ellipse", 620, 1700, 280, 140, "Responder agent\nwrites the final\nanswer (LLM)", PURPLE, fs=16)
arrow(1020, 1775, 900, 1770, "table + total", fs=14)
shape("rectangle", 250, 1715, 260, 110, "Groq LLM\nopenai/gpt-oss-120b", ORANGE, dashed=True)
arrow(620, 1770, 510, 1770, "LLM calls\n(5 per trip)", fs=14)
shape("diamond", 560, 1900, 400, 200, "Output guardrail:\nredact keys/passwords\nadd budget check\n(computed in code)", RED, fs=16)
arrow(760, 1840, 760, 1900)
shape("rectangle", 120, 1950, 320, 100, "Answer shown in the browser\n(sanitised with DOMPurify)", BLUE, fs=16)
arrow(560, 2000, 440, 2000, "respond\nto the user", fs=14)
cur.append({"type": "cameraUpdate", "width": 2400, "height": 1800, "x": -150, "y": 280})
cur.append({"type": "cameraUpdate", "width": 2900, "height": 2175, "x": -350, "y": -30})

# --- outputs -------------------------------------------------------------------
for i, c in enumerate(chunks):
    (OUT / f"sd_view_{i}.json").write_text(json.dumps(c, separators=(",", ":")))

rnd = random.Random(11)


def base(e):
    d = {"angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
         "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [],
         "frameId": None, "roundness": None, "seed": rnd.randint(1, 2**31), "version": 1,
         "versionNonce": rnd.randint(1, 2**31), "isDeleted": False, "boundElements": [], "updated": 1,
         "link": None, "locked": False}
    d.update({k: v for k, v in e.items() if k != "label"})
    return d


def text_el(s, fs, x, y, container=None, color="#1e1e1e"):
    lines = s.split("\n")
    w, h = max(len(l) for l in lines) * fs * 0.55, len(lines) * fs * 1.25
    return {**base({"type": "text", "id": nid("nt"), "x": x - (w / 2 if container else 0),
                    "y": y - (h / 2 if container else 0), "width": w, "height": h, "strokeColor": color}),
            "text": s, "originalText": s, "fontSize": fs, "fontFamily": 1, "lineHeight": 1.25,
            "textAlign": "center" if container else "left", "verticalAlign": "middle" if container else "top",
            "containerId": container, "autoResize": True}


native = []
for c in chunks:
    for e in c:
        if e["type"] == "cameraUpdate":
            continue
        if e["type"] == "text":
            native.append(text_el(e["text"], e["fontSize"], e["x"], e["y"], color=e["strokeColor"]))
            continue
        el = base(e)
        if e["type"] == "arrow":
            el.update({"lastCommittedPoint": None, "startBinding": None, "endBinding": None,
                       "startArrowhead": None, "endArrowhead": "arrow"})
        native.append(el)
        if "label" in e:
            if e["type"] == "arrow":
                mx, my = e["x"] + e["points"][1][0] / 2, e["y"] + e["points"][1][1] / 2
            else:
                mx, my = e["x"] + e["width"] / 2, e["y"] + e["height"] / 2
            t = text_el(e["label"]["text"], e["label"]["fontSize"], mx, my, el["id"],
                        e["label"].get("strokeColor", "#1e1e1e"))
            el["boundElements"].append({"type": "text", "id": t["id"]})
            native.append(t)

(OUT / "system-design.excalidraw").write_text(json.dumps(
    {"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": native,
     "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}}, indent=1))
print("chunks:", [len(c) for c in chunks], "native elements:", len(native))
