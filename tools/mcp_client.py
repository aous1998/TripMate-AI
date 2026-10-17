"""Calls TripMate's tools through the MCP server (mcp_server.py) over stdio.

One server process is started on first use and reused for every call. A
background thread owns the asyncio loop and the MCP session, so the sync
LangGraph agents can call a tool with a plain function call.

Set USE_MCP=false to call the tools in-process instead.
"""

import asyncio
import concurrent.futures
import os
import sys
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client


SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp_server.py"
CONNECT_TIMEOUT = 60
CALL_TIMEOUT = 90


class MCPToolError(RuntimeError):
    """The tool ran on the MCP server and reported an error."""


class MCPToolClient:
    def __init__(self, params: StdioServerParameters):
        self._params = params
        self._loop = None
        self._session = None
        self._closed = None
        self._lock = threading.Lock()

    def connect(self):
        with self._lock:
            if self._session is not None:
                return

            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(target=self._loop.run_forever, name="mcp-client", daemon=True).start()

            ready = concurrent.futures.Future()
            asyncio.run_coroutine_threadsafe(self._hold_session(ready), self._loop)
            ready.result(timeout=CONNECT_TIMEOUT)

    async def _hold_session(self, ready: concurrent.futures.Future):
        # The transport and session are async context managers, so one task
        # keeps them open for the life of the process; calls run as other tasks.
        try:
            async with stdio_client(self._params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._closed = asyncio.Event()
                    self._session = session
                    ready.set_result(None)
                    await self._closed.wait()
        except Exception as e:
            if not ready.done():
                ready.set_exception(e)
            else:
                print("MCP session closed:", e)
        finally:
            self._session = None

    def close(self):
        """Stop the server process."""
        if self._session is not None:
            self._loop.call_soon_threadsafe(self._closed.set)

    def _run(self, coroutine, timeout: float):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout=timeout)

    def list_tools(self) -> list[str]:
        self.connect()
        result = self._run(self._session.list_tools(), timeout=CALL_TIMEOUT)
        return [tool.name for tool in result.tools]

    def call(self, name: str, arguments: dict) -> str:
        self.connect()
        result = self._run(self._session.call_tool(name, arguments), timeout=CALL_TIMEOUT)
        text = "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")

        if result.is_error:
            raise MCPToolError(f"MCP tool '{name}' failed: {text}")

        return text


_client = None
_unavailable = False


def get_client() -> MCPToolClient:
    global _client

    if _client is None:
        _client = MCPToolClient(StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_SCRIPT)],
            env=dict(os.environ),  # pass the API keys through to the server
            cwd=str(SERVER_SCRIPT.parent),
        ))

    return _client


def mcp_enabled() -> bool:
    return os.getenv("USE_MCP", "true").lower() not in ("0", "false", "no")


def start() -> list[str]:
    """Connect at startup so the first request is not slowed down. Returns the tool names."""
    global _unavailable

    if not mcp_enabled():
        return []

    try:
        names = get_client().list_tools()
        print(f"MCP tool server connected: {', '.join(names)}")
        return names
    except Exception as e:
        _unavailable = True
        print(f"MCP tool server unavailable, tools will run in-process: {e!r}")
        return []


def call_tool(name: str, **arguments) -> str:
    """Run a tool through MCP; if the MCP server itself is down, run it in-process."""
    global _unavailable

    if mcp_enabled() and not _unavailable:
        try:
            return get_client().call(name, arguments)
        except MCPToolError:
            raise
        except Exception as e:
            _unavailable = True
            print(f"MCP tool server unavailable, tools will run in-process: {e!r}")

    from mcp_server import TOOLS

    return str(TOOLS[name](**arguments))
