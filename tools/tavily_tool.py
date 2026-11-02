# -----------------------------------------------------------------------------
# tools/tavily_tool.py - web search with Tavily (needs TAVILY_API_KEY).
# Used by the hotel agent and the local guide agent (through MCP, tool
# "web_search"). Returns the top 5 results as numbered text.
# -----------------------------------------------------------------------------

from tavily import TavilyClient   # Tavily's official Python client
import os
from dotenv import load_dotenv

# Read .env so TAVILY_API_KEY is available even when this file is used on its own.
load_dotenv()

# The shared Tavily client; created the first time it is needed.
_client = None


def get_client():
    # Created on first use, not at import: the MCP server imports every tool
    # module, so a missing Tavily key must only break web search.
    global _client
    if _client is None:
        _client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _client


def tavily_search(query):
    # Ask Tavily for the 5 best web results for the query.
    response = get_client().search(
        query= query,
        max_results= 5
    )

    results = []

    # response["results"] is a list of dicts with title, url, content, ...
    # enumerate(..., 1) numbers them starting at 1.
    for i, r in enumerate(response["results"], 1):
        # .get(key, default) avoids an error if a field is missing.
        title   = r.get("title", "Unknown")
        url     = r.get("url", "")
        snippet = r.get("content", "").strip()
        # Keep only the first 300 characters to avoid wall-of-text
        # rsplit(" ", 1)[0] cuts back to the last full word before adding "...".
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."

        # One result, e.g.:
        #   1. **Hotel Le Marais**
        #      https://example.com/...
        #      A charming hotel in ...
        results.append(f"{i}. **{title}**\n   {url}\n   {snippet}")

    # Blank line between results.
    return "\n\n".join(results)
