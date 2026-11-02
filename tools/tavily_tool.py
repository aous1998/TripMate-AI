from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    # Created on first use, not at import: the MCP server imports every tool
    # module, so a missing Tavily key must only break web search.
    global _client
    if _client is None:
        _client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    return _client


def tavily_search(query):
    response = get_client().search(
        query= query,
        max_results= 5
    )

    results = []

    for i, r in enumerate(response["results"], 1):
        title   = r.get("title", "Unknown")
        url     = r.get("url", "")
        snippet = r.get("content", "").strip()
        # Keep only the first 300 characters to avoid wall-of-text
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."

        results.append(f"{i}. **{title}**\n   {url}\n   {snippet}")

    return "\n\n".join(results)
