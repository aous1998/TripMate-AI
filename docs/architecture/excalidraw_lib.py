"""Tiny helpers for building Excalidraw diagrams in code.

Shapes use the `label` shorthand understood by the Excalidraw MCP viewer;
`save_native` expands them into a regular .excalidraw file (bound text).
"""
import json
import random
from pathlib import Path

BLUE, PURPLE, GREEN, RED, YELLOW, ORANGE, TEAL, GRAY, WHITE = (
    "#a5d8ff", "#d0bfff", "#b2f2bb", "#ffc9c9", "#fff3bf", "#ffd8a8", "#c3fae8", "#f1f3f5", "#ffffff")
STROKE = {BLUE: "#4a9eed", PURPLE: "#8b5cf6", GREEN: "#22c55e", RED: "#ef4444", YELLOW: "#f59e0b",
          ORANGE: "#f59e0b", TEAL: "#06b6d4", GRAY: "#868e96", WHITE: "#1e1e1e"}


class Canvas:
    def __init__(self, prefix):
        self.prefix = prefix
        self.views = []
        self.cur = None
        self.n = 0

    def nid(self, p):
        self.n += 1
        return f"{self.prefix}{p}{self.n}"

    # ---- views -------------------------------------------------------------
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

    def text(self, x, y, s, fs=16, color="#1e1e1e"):
        self.cur.append({"type": "text", "id": self.nid("t"), "x": x, "y": y, "text": s,
                         "fontSize": fs, "strokeColor": color})

    def line(self, x1, y1, x2, y2, color="#adb5bd", dashed=True):
        e = {"type": "arrow", "id": self.nid("l"), "x": x1, "y": y1, "width": abs(x2 - x1),
             "height": abs(y2 - y1), "points": [[0, 0], [x2 - x1, y2 - y1]], "strokeColor": color,
             "strokeWidth": 1, "endArrowhead": None, "startArrowhead": None}
        if dashed:
            e["strokeStyle"] = "dashed"
        self.cur.append(e)

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
    def texts(self):
        out = []
        for v in self.views:
            for e in v:
                out.append(e.get("text") or (e.get("label") or {}).get("text") or "")
        return "\n".join(out)

    def save_views(self, out_dir: Path, stem: str):
        for i, v in enumerate(self.views):
            (out_dir / f"{stem}_view_{i}.json").write_text(json.dumps(v, separators=(",", ":")))

    def save_native(self, path: Path, seed=3):
        rnd = random.Random(seed)

        def base(e):
            d = {"angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
                 "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100, "groupIds": [],
                 "frameId": None, "roundness": None, "seed": rnd.randint(1, 2**31), "version": 1,
                 "versionNonce": rnd.randint(1, 2**31), "isDeleted": False, "boundElements": [],
                 "updated": 1, "link": None, "locked": False}
            d.update({k: v for k, v in e.items() if k != "label"})
            return d

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

        native = []
        for v in self.views:
            for e in v:
                if e["type"] == "cameraUpdate":
                    continue
                if e["type"] == "text":
                    native.append(text_el(e["text"], e["fontSize"], e["x"], e["y"], color=e["strokeColor"]))
                    continue
                el = base(e)
                if e["type"] == "arrow":
                    el.update({"lastCommittedPoint": None, "startBinding": None, "endBinding": None,
                               "startArrowhead": e.get("startArrowhead"),
                               "endArrowhead": e.get("endArrowhead", "arrow")})
                native.append(el)
                if "label" in e:
                    if e["type"] == "arrow":
                        mx, my = e["x"] + e["points"][1][0] / 2, e["y"] + e["points"][1][1] / 2
                    else:
                        mx, my = e["x"] + e["width"] / 2, e["y"] + e["height"] / 2
                    t = text_el(e["label"]["text"], e["label"]["fontSize"], mx, my, el["id"])
                    el["boundElements"].append({"type": "text", "id": t["id"]})
                    native.append(t)

        path.write_text(json.dumps({"type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
                                    "elements": native,
                                    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
                                    "files": {}}, indent=1))
        return len(native)
