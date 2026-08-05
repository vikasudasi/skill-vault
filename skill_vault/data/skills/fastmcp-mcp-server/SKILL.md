---
name: fastmcp-mcp-server
description: Build Model Context Protocol servers with FastMCP — tools, resources, transports (stdio + streamable-http), and testing.
tags: [mcp, fastmcp, llm, python, ai, protocol]
triggers: [mcp server, fastmcp, model context protocol, tool, agent integration]
complexity: high
time_estimate: 60-120 min
prerequisites: [python 3.11, fastmcp, understanding of MCP]
source: Skill Vault curated library
---

# Building MCP Servers with FastMCP

Use when exposing capabilities or data to AI agents via the Model Context Protocol.

## Minimal tool server

```python
from fastmcp import FastMCP

mcp = FastMCP("my-server")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    mcp.run()
```

## Transports matter

- **stdio** — local, one process. Must NOT print to stdout (pure JSON-RPC); send
  logs to stderr. Do NOT pass host/port kwargs to `run()` in stdio mode — it
  silently breaks the handshake.
- **streamable-http** — remote; pass `host`/`port`. Mount the app via
  `mcp.http_app()` behind your web framework when serving remotely.

## Keep tool surfaces thin

Expose a small number of discovery tools that return **lightweight metadata**
first, then a fetch tool for full payloads on demand — progressive disclosure.
This is exactly Skill Vault's `search_skills` → `get_skill` pattern and keeps
agent context small.

## Testing tools directly

Invoke through the runtime so the error/translation layer is exercised:

```python
from fastmcp.exceptions import ToolError

with pytest.raises(ToolError):
    await server.call_tool("add", {"a": 1, "b": "x"})
```

## Pitfalls

- Keep tool schemas narrow and typed; agents rely on them.
- Never log request payloads/secrets to stdout.
- For errors, raise typed exceptions the framework translates to MCP error codes.
