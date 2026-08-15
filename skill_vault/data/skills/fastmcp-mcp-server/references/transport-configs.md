# Transport Configuration Reference

## Transport comparison

| Feature | stdio | streamable-http | SSE (deprecated) |
|---------|-------|-----------------|-------------------|
| Network access | Local only | Remote | Remote |
| Process model | One client per server process | Multi-client | Multi-client |
| Production ready | No | Yes | No (use streamable-http) |
| Debugging | Hard (stdout is protocol) | Easy (HTTP tools) | Moderate |

## stdio mode details

```python
mcp.run()  # defaults to stdio
```

- The MCP client spawns your server as a subprocess
- All JSON-RPC communication flows over stdin/stdout
- **CRITICAL:** Never `print()` to stdout — it corrupts the protocol
- Use `logging` → stderr or `sys.stderr.write()` for debug output
- No `host`/`port` arguments — the transport is the process pipes

## streamable-http mode

```python
mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

- Uses stateless HTTP with optional SSE streaming for server→client notifications
- Suitable for remote deployment behind a reverse proxy
- Can mount behind FastAPI: `app.mount("/mcp", mcp.http_app())`

## Testing tools

Invoke through the runtime to exercise the full validation+error pipeline:

```python
from fastmcp.exceptions import ToolError

with pytest.raises(ToolError):
    await mcp.call_tool("add_numbers", {"a": 1, "b": "not_a_number"})
```