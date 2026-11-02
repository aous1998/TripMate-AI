"""TripMate MCP server: exposes the travel tools over the Model Context Protocol.

The agents start this automatically over stdio (see tools/mcp_client.py).
It can also be used by any MCP client, e.g. `python mcp_server.py`.

Tools must not print to stdout: on the stdio transport, stdout carries the protocol.
"""
# -----------------------------------------------------------------------------
# mcp_server.py - a separate program that offers the travel tools.
#
# MCP (Model Context Protocol) is a standard way to publish tools. A client
# starts this file as a child process and sends JSON messages through its
# stdin/stdout ("stdio transport"):  "list your tools", "call tool X with Y".
#
# Each tool below is a thin wrapper around the real code in tools/. The
# function's name, type hints and docstring become the tool's public
# description, which any MCP client (not only TripMate) can read.
# -----------------------------------------------------------------------------

import functools        # functools.wraps keeps a function's name/docstring when wrapping it
import os

import certifi
from dotenv import load_dotenv

# This runs in its own process, so it loads .env and sets the certificate
# bundle itself (same as backend.py does for the main app).
load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# The imports come after load_dotenv() on purpose (the tool modules read
# settings when imported). "noqa: E402" tells linters this order is intended.
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from tools import currency_tool, flight_tool, tavily_tool, weather_tool  # noqa: E402


# --- The five tools -----------------------------------------------------------
# Keep the docstrings short and accurate: they are what clients see.

def search_flights(query: str, limit: int = 5) -> str:
    """Live flights for a route such as 'from Berlin to Paris' (AviationStack)."""
    return flight_tool.search_flights(query, limit=limit)


def web_search(query: str) -> str:
    """Top web results with short snippets (Tavily)."""
    return tavily_tool.tavily_search(query)


def weather_forecast(location: str, days: int = 7) -> str:
    """Daily forecast for a city or country (Open-Meteo)."""
    return weather_tool.get_weather_forecast(location, days=days)


def convert_currency(amount: float, from_currency: str, to_currency: str = "EUR") -> float:
    """Convert an amount between ISO 4217 currencies at the latest ECB rate (Frankfurter)."""
    return currency_tool.convert_currency(amount, from_currency, to_currency)


def lookup_airport(location: str) -> str:
    """Main airport IATA code for a city or country, e.g. 'Berlin' -> 'BER'. Empty if unknown."""
    # `or ""` turns None (not found) into an empty string.
    return flight_tool.resolve_location_to_iata(location) or ""


# All tools by name: {"search_flights": search_flights, ...}.
# Also used by tools/mcp_client.py to run a tool directly (in-process)
# when this server cannot be started.
TOOLS = {
    tool.__name__: tool
    for tool in [search_flights, web_search, weather_forecast, convert_currency, lookup_airport]
}

def report_errors(tool):
    """Send the real failure reason to the client; MCPServer hides unexpected errors."""
    # A "decorator-style" wrapper: returns a new function that calls `tool`,
    # but converts any exception into ToolError. MCPServer passes a ToolError's
    # message to the client; other errors only say "Error executing tool".
    @functools.wraps(tool)   # keep the original name, type hints and docstring
    def wrapper(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except Exception as e:
            # e.g. "MissingAPIKeyError: No API key provided ..."
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return wrapper


# The MCP server object. log_level="WARNING" keeps its console output quiet.
server = MCPServer(
    "tripmate-tools",
    instructions="Travel research tools for TripMate AI: flights, web search, weather, currency, airports.",
    log_level="WARNING",
)

# Register every tool, each wrapped by report_errors.
# server.tool() returns a decorator; calling it with a function registers that function.
for tool in TOOLS.values():
    server.tool()(report_errors(tool))


# `python mcp_server.py` -> start serving over stdin/stdout until the client disconnects.
if __name__ == "__main__":
    server.run()
