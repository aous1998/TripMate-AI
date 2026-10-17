"""TripMate MCP server: exposes the travel tools over the Model Context Protocol.

The agents start this automatically over stdio (see tools/mcp_client.py).
It can also be used by any MCP client, e.g. `python mcp_server.py`.

Tools must not print to stdout: on the stdio transport, stdout carries the protocol.
"""

import functools
import os

import certifi
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from tools import currency_tool, flight_tool, tavily_tool, weather_tool  # noqa: E402


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
    return flight_tool.resolve_location_to_iata(location) or ""


TOOLS = {
    tool.__name__: tool
    for tool in [search_flights, web_search, weather_forecast, convert_currency, lookup_airport]
}

def report_errors(tool):
    """Send the real failure reason to the client; MCPServer hides unexpected errors."""
    @functools.wraps(tool)
    def wrapper(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return wrapper


server = MCPServer(
    "tripmate-tools",
    instructions="Travel research tools for TripMate AI: flights, web search, weather, currency, airports.",
    log_level="WARNING",
)

for tool in TOOLS.values():
    server.tool()(report_errors(tool))


if __name__ == "__main__":
    server.run()
