"""Integration tests: start the real MCP server over stdio and call it."""

# -----------------------------------------------------------------------------
# tests/test_mcp.py - starts the REAL mcp_server.py as a child process and talks
# to it over MCP, just like the app does. Only lookup_airport and
# convert_currency (same-currency) are called, because they need no network.
# -----------------------------------------------------------------------------
import os
import sys

import pytest
from mcp import StdioServerParameters

from tools import mcp_client
from tools.mcp_client import MCPToolClient, MCPToolError


# scope="module": one server process is shared by all tests in this file.
# Code after `yield` stops the server when the tests are done.
@pytest.fixture(scope="module")
def client():
    client = MCPToolClient(StdioServerParameters(
        command=sys.executable,
        args=[str(mcp_client.SERVER_SCRIPT)],
        env=dict(os.environ),
        cwd=str(mcp_client.SERVER_SCRIPT.parent),
    ))
    yield client
    client.close()


# The server advertises exactly our five tools.
def test_server_lists_every_tool(client):
    assert set(client.list_tools()) == {
        "search_flights", "web_search", "weather_forecast", "convert_currency", "lookup_airport",
    }


# Tool calls run on the server; results come back as text.
def test_tool_call_runs_on_the_server(client):
    assert client.call("lookup_airport", {"location": "Berlin"}) == "BER"
    assert client.call("lookup_airport", {"location": "France"}) == "CDG"
    assert client.call("convert_currency", {"amount": 50, "from_currency": "EUR"}) == "50.0"


# Wrong argument types are rejected by the server's input validation, and the
# client turns that into an MCPToolError (instead of silently falling back).
def test_tool_errors_are_reported_with_their_reason(client):
    with pytest.raises(MCPToolError, match="Error executing tool convert_currency"):
        client.call("convert_currency", {"amount": "not a number", "from_currency": "USD"})


# USE_MCP=false: tools run in-process; get_client() must not even be called.
def test_use_mcp_false_runs_tools_in_process(monkeypatch):
    monkeypatch.setenv("USE_MCP", "false")
    monkeypatch.setattr(mcp_client, "get_client", lambda: pytest.fail("MCP should not be used"))

    assert mcp_client.call_tool("lookup_airport", location="Munich") == "MUC"


# The server is dead: call_tool falls back to running the tool in-process and remembers it.
def test_unreachable_server_falls_back_to_in_process(monkeypatch):
    class DeadClient:
        def call(self, name, arguments):
            raise ConnectionError("server process exited")

    monkeypatch.setattr(mcp_client, "get_client", lambda: DeadClient())
    monkeypatch.setattr(mcp_client, "_unavailable", False)

    assert mcp_client.call_tool("lookup_airport", location="Hamburg") == "HAM"
    assert mcp_client._unavailable is True
