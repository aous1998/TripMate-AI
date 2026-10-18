import json, re, subprocess, sys
from pathlib import Path
diagram, repo = sys.argv[1], Path(sys.argv[2])
text = "\n".join(e.get("text", "") for e in json.load(open(diagram))["elements"])
ok = lambda c: "PASS" if c else "FAIL"

print("1) File paths on the diagram exist")
paths = sorted(set(re.findall(r"[\w./-]+\.(?:py|html|js|css|txt)\b|Dockerfile", text)))
missing = [p for p in paths if not (repo / p).exists()]
print(f"   {ok(not missing)}  {len(paths)} paths, missing: {missing or 'none'}")

print("2) Coverage of facts extracted from the code")
wf = (repo / "workflow.py").read_text() + (repo / "state.py").read_text()
nodes = set(re.findall(r'add_node\("(\w+)"', wf)) | set(re.findall(r'"(\w+_agent)"', (repo / "state.py").read_text()))
routes = set(re.findall(r'@app\.(?:get|post)\("([^"]+)"', (repo / "app.py").read_text())) - {"/favicon.ico", "/", "/health"}
tools = set(re.findall(r"for tool in \[([^\]]+)\]", (repo / "mcp_server.py").read_text())[0].replace(" ", "").split(","))
envs = set()
for f in repo.rglob("*.py"):
    if "tests" in f.parts: continue
    envs |= set(re.findall(r'os\.getenv\("([A-Z_]+)"', f.read_text()))
externals = {"Groq", "Tavily", "AviationStack", "Open-Meteo", "Frankfurter", "PostgreSQL", "jsDelivr"}
for name, items in [("graph nodes", nodes), ("API routes", routes), ("MCP tools", tools), ("env vars", envs), ("external services", externals)]:
    miss = sorted(i for i in items if i not in text)
    print(f"   {ok(not miss)}  {name}: {len(items) - len(miss)}/{len(items)} on diagram; missing: {miss or 'none'}")
