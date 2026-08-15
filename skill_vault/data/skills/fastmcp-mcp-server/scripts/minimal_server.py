#!/usr/bin/env python3
"""Minimal FastMCP server with tools, resources, and stdio + HTTP transports.

Run stdio:   python minimal_server.py
Run HTTP:    python minimal_server.py --http
Test:        python minimal_server.py --test
"""

from __future__ import annotations

import sys

from fastmcp import FastMCP

# ── Server ──────────────────────────────────────────────────────────────

mcp = FastMCP("demo-server")


# ── Tools ───────────────────────────────────────────────────────────────


@mcp.tool()
def echo(message: str) -> str:
    """Echo back the given message."""
    return f"You said: {message}"


@mcp.tool()
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@mcp.tool()
def get_server_info() -> str:
    """Return metadata about this MCP server."""
    return "demo-server v1.0.0 — FastMCP demo"


# ── Resources ───────────────────────────────────────────────────────────


@mcp.resource("config://app")
def get_app_config() -> str:
    """Return application configuration as plain text."""
    return "mode=production\nlog_level=INFO\n"


# ── Prompts ─────────────────────────────────────────────────────────────


@mcp.prompt()
def summarize(text: str) -> str:
    """Prompt template that asks the model to summarize text."""
    return f"Please summarize the following text in one sentence:\n{text}"


# ── Entry points ────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--test" in sys.argv:
        # Self-test: invoke tools directly through the runtime
        import asyncio

        async def _test():
            result = await mcp.call_tool("echo", {"message": "hello"})
            assert "You said: hello" in result[0].text, f"Unexpected: {result}"
            print("✓ Tool test passed")

            result2 = await mcp.call_tool("add_numbers", {"a": 2, "b": 3})
            assert "5" in result2[0].text or 5 == float(result2[0].text)
            print("✓ Add test passed")

            print("All tests passed.")

        asyncio.run(_test())
    elif "--http" in sys.argv:
        # Run as HTTP server for remote access
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
    else:
        # Default: stdio transport (for local MCP clients)
        mcp.run()
