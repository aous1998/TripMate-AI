# -----------------------------------------------------------------------------
# docs/architecture/verify.py - checks that a diagram matches the real code.
# Usage: python docs/architecture/verify.py <diagram.excalidraw> <repo folder>
#   1) every file path written on the diagram exists in the repo
#   2) the diagram mentions every graph node, API route, MCP tool, environment
#      variable and external service that the code actually has
# Prints PASS/FAIL per check. It reads the code with regular expressions, so it
# is a quick sanity check, not a parser.
# -----------------------------------------------------------------------------
import json, re, subprocess, sys
from pathlib import Path
# The two command-line arguments.
diagram, repo = sys.argv[1], Path(sys.argv[2])
# All text on the diagram (every element's "text" field) as one string.
text = "\n".join(e.get("text", "") for e in json.load(open(diagram))["elements"])
# Small helper: True -> "PASS", False -> "FAIL".
ok = lambda c: "PASS" if c else "FAIL"

print("1) File paths on the diagram exist")
# Anything that looks like a file name (.py/.html/.js/.css/.txt) or "Dockerfile".
paths = sorted(set(re.findall(r"[\w./-]+\.(?:py|html|js|css|txt)\b|Dockerfile", text)))
missing = [p for p in paths if not (repo / p).exists()]
print(f"   {ok(not missing)}  {len(paths)} paths, missing: {missing or 'none'}")

print("2) Coverage of facts extracted from the code")
# Facts read from the code: graph node names (add_node(...) and the *_agent names in state.py) ...
wf = (repo / "workflow.py").read_text() + (repo / "state.py").read_text()
nodes = set(re.findall(r'add_node\("(\w+)"', wf)) | set(re.findall(r'"(\w+_agent)"', (repo / "state.py").read_text()))
# ... HTTP routes in app.py (minus trivial ones) ...
routes = set(re.findall(r'@app\.(?:get|post)\("([^"]+)"', (repo / "app.py").read_text())) - {"/favicon.ico", "/", "/health"}
# ... the five tool names from the list in mcp_server.py ...
tools = set(re.findall(r"for tool in \[([^\]]+)\]", (repo / "mcp_server.py").read_text())[0].replace(" ", "").split(","))
# ... and every os.getenv("NAME") in the app code (tests excluded).
envs = set()
for f in repo.rglob("*.py"):
    if "tests" in f.parts: continue
    envs |= set(re.findall(r'os\.getenv\("([A-Z_]+)"', f.read_text()))
# External services are a fixed list (they are not easy to extract from code).
externals = {"Groq", "Tavily", "AviationStack", "Open-Meteo", "Frankfurter", "PostgreSQL", "jsDelivr"}
# For each group: count how many items appear on the diagram and list the missing ones.
for name, items in [("graph nodes", nodes), ("API routes", routes), ("MCP tools", tools), ("env vars", envs), ("external services", externals)]:
    miss = sorted(i for i in items if i not in text)
    print(f"   {ok(not miss)}  {name}: {len(items) - len(miss)}/{len(items)} on diagram; missing: {miss or 'none'}")
