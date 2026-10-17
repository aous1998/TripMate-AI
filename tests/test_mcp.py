"""Integration tests: start the real MCP server over stdio and call it."""

import os
import sys

import pytest
from mcp import StdioServerParameters

from tools import mcp_client
from tools.mcp_client import MCPToolClient, MCPToolError


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


def test_server_lists_every_tool(client):
    assert set(client.list_tools()) == {
        "search_flights", "web_search", "weather_forecast", "convert_currency", "lookup_airport",
    }


def test_tool_call_runs_on_the_server(client):
    assert client.call("lookup_airport", {"location": "Berlin"}) == "BER"
    assert client.call("lookup_airport", {"location": "France"}) == "CDG"
    assert client.call("convert_currency", {"amount": 50, "from_currency": "EUR"}) == "50.0"


def test_tool_errors_are_reported_with_their_reason(client):
    with pytest.raises(MCPToolError, match="Error executing tool convert_currency"):
        client.call("convert_currency", {"amount": "not a number", "from_currency": "USD"})


def test_use_mcp_false_runs_tools_in_process(monkeypatch):
    monkeypatch.setenv("USE_MCP", "false")
    monkeypatch.setattr(mcp_client, "get_client", lambda: pytest.fail("MCP should not be used"))

    assert mcp_client.call_tool("lookup_airport", location="Munich") == "MUC"


def test_unreachable_server_falls_back_to_in_process(monkeypatch):
    class DeadClient:
        def call(self, name, arguments):
            raise ConnectionError("server process exited")

    monkeypatch.setattr(mcp_client, "get_client", lambda: DeadClient())
    monkeypatch.setattr(mcp_client, "_unavailable", False)

    assert mcp_client.call_tool("lookup_airport", location="Hamburg") == "HAM"
    assert mcp_client._unavailable is True
