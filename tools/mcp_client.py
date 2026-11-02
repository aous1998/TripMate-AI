"""Calls TripMate's tools through the MCP server (mcp_server.py) over stdio.

One server process is started on first use and reused for every call. A
background thread owns the asyncio loop and the MCP session, so the sync
LangGraph agents can call a tool with a plain function call.

Set USE_MCP=false to call the tools in-process instead.
"""
# -----------------------------------------------------------------------------
# tools/mcp_client.py - the agents' side of MCP.
#
# The problem it solves:
#   the MCP SDK is ASYNC (async/await), but the agents are normal (sync)
#   functions. So this file runs one asyncio event loop in a background thread,
#   keeps one MCP session open in it, and offers a plain function:
#       call_tool("web_search", query="...")  ->  "1. **Result** ..."
#
# Picture:
#   agent thread --call_tool()--> [background thread: asyncio loop + MCP session]
#                                     |  stdin/stdout (JSON-RPC)
#                                     v
#                              child process: python mcp_server.py
#
# Fallback: if the server cannot start, tools are imported from mcp_server.py
# and run directly in this process, so the app keeps working.
# -----------------------------------------------------------------------------

import asyncio               # Python's async framework (event loop, tasks, events)
import concurrent.futures    # Future: a "result that will arrive later", usable across threads
import os
import sys
import threading
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client


# Absolute path of mcp_server.py: this file's folder (tools/) -> its parent (project root).
SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp_server.py"
CONNECT_TIMEOUT = 60   # seconds to wait for the server to start
CALL_TIMEOUT = 90      # seconds to wait for one tool call


class MCPToolError(RuntimeError):
    """The tool ran on the MCP server and reported an error."""
    # Separate class so call_tool() can tell "the TOOL failed" (re-raise)
    # from "the SERVER is broken" (switch to in-process).


class MCPToolClient:
    def __init__(self, params: StdioServerParameters):
        self._params = params        # how to start the server (command, args, env, cwd)
        self._loop = None            # the asyncio event loop (lives in a background thread)
        self._session = None         # the open MCP ClientSession, once connected
        self._closed = None          # asyncio.Event; setting it ends the session
        self._lock = threading.Lock()   # stops two threads connecting at the same time

    def connect(self):
        # `with self._lock:` - only one thread at a time may run this block.
        with self._lock:
            # Already connected: nothing to do.
            if self._session is not None:
                return

            # First time: create an event loop and run it forever in a daemon
            # thread (a daemon thread does not keep the program alive on exit).
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                threading.Thread(target=self._loop.run_forever, name="mcp-client", daemon=True).start()

            # Start _hold_session() on the loop and wait (in this thread) until
            # it reports "ready" - or raise if it failed or took too long.
            ready = concurrent.futures.Future()
            asyncio.run_coroutine_threadsafe(self._hold_session(ready), self._loop)
            ready.result(timeout=CONNECT_TIMEOUT)

    async def _hold_session(self, ready: concurrent.futures.Future):
        # The transport and session are async context managers, so one task
        # keeps them open for the life of the process; calls run as other tasks.
        try:
            # stdio_client starts `python mcp_server.py` and connects to its stdin/stdout.
            async with stdio_client(self._params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()          # MCP handshake
                    self._closed = asyncio.Event()
                    self._session = session
                    ready.set_result(None)              # tell connect() we are ready
                    # Wait here (keeping both "with" blocks open) until close() is called.
                    await self._closed.wait()
        except Exception as e:
            if not ready.done():
                # Failed while connecting: connect() will raise this error.
                ready.set_exception(e)
            else:
                # Failed later (e.g. the server process died).
                print("MCP session closed:", e)
        finally:
            # Either way the session is gone; the next call will reconnect.
            self._session = None

    def close(self):
        """Stop the server process."""
        # Setting the event (from another thread, hence call_soon_threadsafe)
        # lets _hold_session() leave its "with" blocks, which stops the server.
        if self._session is not None:
            self._loop.call_soon_threadsafe(self._closed.set)

    def _run(self, coroutine, timeout: float):
        # Run an async call on the background loop and wait for its result here.
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout=timeout)

    def list_tools(self) -> list[str]:
        # Ask the server which tools it offers; return just their names.
        self.connect()
        result = self._run(self._session.list_tools(), timeout=CALL_TIMEOUT)
        return [tool.name for tool in result.tools]

    def call(self, name: str, arguments: dict) -> str:
        self.connect()
        result = self._run(self._session.call_tool(name, arguments), timeout=CALL_TIMEOUT)
        # The result is a list of content blocks; join the text blocks together.
        text = "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")

        # The tool itself reported an error (e.g. missing API key).
        if result.is_error:
            raise MCPToolError(f"MCP tool '{name}' failed: {text}")

        return text


# Module-level state: one shared client, and a flag set once the server is
# known to be broken (then every call goes straight to the in-process fallback).
_client = None
_unavailable = False


def get_client() -> MCPToolClient:
    global _client

    if _client is None:
        _client = MCPToolClient(StdioServerParameters(
            command=sys.executable,          # the same Python that runs the app
            args=[str(SERVER_SCRIPT)],       # -> python /path/to/mcp_server.py
            env=dict(os.environ),  # pass the API keys through to the server
            cwd=str(SERVER_SCRIPT.parent),   # run it from the project folder
        ))

    return _client


def mcp_enabled() -> bool:
    # USE_MCP defaults to "true"; "0", "false" or "no" switch MCP off.
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
        # Remember the failure; tools will run in-process from now on.
        # {e!r} prints the error with its type, e.g. TimeoutError().
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
            # The tool failed (not the server): pass the error on unchanged.
            # Running it in-process would fail the same way.
            raise
        except Exception as e:
            # The server is broken (crashed, timeout ...): fall back for good.
            _unavailable = True
            print(f"MCP tool server unavailable, tools will run in-process: {e!r}")

    # In-process path: import the same tool functions and call them directly.
    # (Imported here, not at the top, so it only loads when needed.)
    from mcp_server import TOOLS

    # str(...) because convert_currency returns a float, the others text.
    return str(TOOLS[name](**arguments))
