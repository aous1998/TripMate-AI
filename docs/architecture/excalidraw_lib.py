"""Tiny helpers for building Excalidraw diagrams in code.

Shapes use the `label` shorthand understood by the Excalidraw MCP viewer;
`save_native` expands them into a regular .excalidraw file (bound text).
"""
# -----------------------------------------------------------------------------
# docs/architecture/excalidraw_lib.py - used by interview_diagrams.py to draw
# diagrams with code instead of by hand. (gen.py and system_design.py are older
# and carry their own copies of these helpers.)
#
# A Canvas collects "views" (one framed diagram each). Each view is a list of
# simple element dicts (box, text, line, arrow). They can be saved as:
#   save_views()  -> one JSON file per view, for the Excalidraw MCP viewer
#   save_native() -> one normal .excalidraw file you can open on excalidraw.com
# -----------------------------------------------------------------------------
import json
import random
from pathlib import Path

# Fill colours (pastel) and, below, the matching darker outline colour for each.
BLUE, PURPLE, GREEN, RED, YELLOW, ORANGE, TEAL, GRAY, WHITE = (
    "#a5d8ff", "#d0bfff", "#b2f2bb", "#ffc9c9", "#fff3bf", "#ffd8a8", "#c3fae8", "#f1f3f5", "#ffffff")
STROKE = {BLUE: "#4a9eed", PURPLE: "#8b5cf6", GREEN: "#22c55e", RED: "#ef4444", YELLOW: "#f59e0b",
          ORANGE: "#f59e0b", TEAL: "#06b6d4", GRAY: "#868e96", WHITE: "#1e1e1e"}


# One drawing made of several views.
class Canvas:
    def __init__(self, prefix):
        self.prefix = prefix  # added to every element id so ids from different canvases never clash
        self.views = []  # list of views; each view is a list of elements
        self.cur = None  # the view new elements are added to
        self.n = 0  # counter used to make unique ids

    # A new unique id, e.g. "arch_r12".
    def nid(self, p):
        self.n += 1
        return f"{self.prefix}{p}{self.n}"

    # ---- views -------------------------------------------------------------
    # Start a new view: a camera position (for the MCP viewer), a grey frame,
    # a big title and an optional subtitle. Returns the top-left corner.
    def view(self, x, y, w, h, title, sub=None, cam=(1200, 900)):
        self.cur = [{"type": "cameraUpdate", "width": cam[0], "height": cam[1], "x": x - 40, "y": y - 40}]
        self.views.append(self.cur)
        self.cur.append({"type": "rectangle", "id": self.nid("fr"), "x": x, "y": y, "width": w, "height": h,
                         "backgroundColor": "#f8f9fa", "fillStyle": "solid", "strokeColor": "#adb5bd",
                         "strokeWidth": 2, "roundness": {"type": 3}})
        self.text(x + 30, y + 22, title, 30)
        if sub:
            self.text(x + 30, y + 66, sub, 17, "#555555")
        return x, y

    # ---- elements ----------------------------------------------------------
    # A shape with a centred label. kind = "rectangle", "ellipse" or "diamond";
    # the outline colour defaults to the darker partner of the fill colour.
    def box(self, x, y, w, h, label, fill=WHITE, fs=16, dashed=False, kind="rectangle", stroke=None):
        e = {"type": kind, "id": self.nid(kind[0]), "x": x, "y": y, "width": w, "height": h,
             "backgroundColor": fill, "fillStyle": "solid", "strokeColor": stroke or STROKE[fill],
             "label": {"text": label, "fontSize": fs}}
        if kind == "rectangle":
            e["roundness"] = {"type": 3}
        if dashed:
            e["strokeStyle"] = "dashed"
        self.cur.append(e)
        return e

    # Free text at a position.
    def text(self, x, y, s, fs=16, color="#1e1e1e"):
        self.cur.append({"type": "text", "id": self.nid("t"), "x": x, "y": y, "text": s,
                         "fontSize": fs, "strokeColor": color})

    # A plain line (an arrow without arrowheads), dashed by default, used for separators.
    def line(self, x1, y1, x2, y2, color="#adb5bd", dashed=True):
        e = {"type": "arrow", "id": self.nid("l"), "x": x1, "y": y1, "width": abs(x2 - x1),
             "height": abs(y2 - y1), "points": [[0, 0], [x2 - x1, y2 - y1]], "strokeColor": color,
             "strokeWidth": 1, "endArrowhead": None, "startArrowhead": None}
        if dashed:
            e["strokeStyle"] = "dashed"
        self.cur.append(e)

    # An arrow from (x1, y1) to (x2, y2), optionally labelled, dashed or two-headed.
    def arrow(self, x1, y1, x2, y2, label=None, color="#1e1e1e", dashed=False, fs=14, both=False):
        e = {"type": "arrow", "id": self.nid("a"), "x": x1, "y": y1, "width": abs(x2 - x1),
             "height": abs(y2 - y1), "points": [[0, 0], [x2 - x1, y2 - y1]], "strokeColor": color,
             "strokeWidth": 2, "endArrowhead": "arrow"}
        if both:
            e["startArrowhead"] = "arrow"
        if dashed:
            e["strokeStyle"] = "dashed"
        if label:
            e["label"] = {"text": label, "fontSize": fs}
        self.cur.append(e)

    # ---- output ------------------------------------------------------------
    # All text in the drawing as one string (used by verify-style checks).
    def texts(self):
        out = []
        for v in self.views:
            for e in v:
                out.append(e.get("text") or (e.get("label") or {}).get("text") or "")
        return "\n".join(out)

    # One compact JSON file per view.
    def save_views(self, out_dir: Path, stem: str):
        for i, v in enumerate(self.views):
            (out_dir / f"{stem}_view_{i}.json").write_text(json.dumps(v, separators=(",", ":")))

    # Write a real .excalidraw file. The simple dicts lack many fields Excalidraw
    # needs, and labels must become separate text elements bound to their shape.
    # A fixed random seed makes the hand-drawn look identical on every run.
    def save_native(self, path: Path, seed=3):
        rnd = random.Random(seed)

        # Default values for every field an Excalidraw element needs, then our own values on top.
        def base(e):
            d = {"angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
                 "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [],
                 "frameId": None, "roundness": None, "seed": rnd.randint(1, 2**31), "version": 1,
                 "versionNonce": rnd.randint(1, 2**31), "isDeleted": False, "boundElements": [],
                 "updated": 1, "link": None, "locked": False}
            d.update({k: v for k, v in e.items() if k != "label"})
            return d

        # A text element. Inside a shape (container) it is centred on (x, y);
        # its size is estimated from the number of characters and lines.
        def text_el(s, fs, x, y, container=None, color="#1e1e1e"):
            lines = s.split("\n")
            w, h = max(len(l) for l in lines) * fs * 0.55, len(lines) * fs * 1.25
            return {**base({"type": "text", "id": self.nid("nt"), "x": x - (w / 2 if container else 0),
                            "y": y - (h / 2 if container else 0), "width": w, "height": h,
                            "strokeColor": color}),
                    "text": s, "originalText": s, "fontSize": fs, "fontFamily": 1, "lineHeight": 1.25,
                    "textAlign": "center" if container else "left",
                    "verticalAlign": "middle" if container else "top", "containerId": container,
                    "autoResize": True}

        # Convert every element of every view.
        native = []
        for v in self.views:
            for e in v:
                if e["type"] == "cameraUpdate":  # camera positions only matter for the MCP viewer
                    continue
                if e["type"] == "text":
                    native.append(text_el(e["text"], e["fontSize"], e["x"], e["y"], color=e["strokeColor"]))
                    continue
                el = base(e)
                    # Arrows need a few extra fields.
                if e["type"] == "arrow":
                    el.update({"lastCommittedPoint": None, "startBinding": None, "endBinding": None,
                               "startArrowhead": e.get("startArrowhead"),
                               "endArrowhead": e.get("endArrowhead", "arrow")})
                native.append(el)
                # A label becomes a text element centred on the shape (or the arrow's middle), bound to it.
                if "label" in e:
                    if e["type"] == "arrow":
                        mx, my = e["x"] + e["points"][1][0] / 2, e["y"] + e["points"][1][1] / 2
                    else:
                        mx, my = e["x"] + e["width"] / 2, e["y"] + e["height"] / 2
                    t = text_el(e["label"]["text"], e["label"]["fontSize"], mx, my, el["id"])
                    el["boundElements"].append({"type": "text", "id": t["id"]})
                    native.append(t)

        # Save the file; return how many elements were written.
        path.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
                                    "elements": native,
                                    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
                                    "files": {}}, indent=1))
        return len(native)
