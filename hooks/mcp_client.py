"""Shared MCP client for Claude Code hooks."""

import json
import os
import sys
import urllib.request

TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
SERVER = os.environ.get("MCP_SERVER_URL", "https://claude-connector.example.com")

_MISSING_TOKEN_WARNING = """
╔══════════════════════════════════════════════════════════════════╗
║  claude-connector: MCP_AUTH_TOKEN is not set!                    ║
║                                                                  ║
║  The hooks can't talk to the server without it.                  ║
║  Create ~/.claude/.secrets with this line:                       ║
║                                                                  ║
║    export MCP_AUTH_TOKEN=your-token-here                         ║
║                                                                  ║
║  Get your token from:                                            ║
║    grep CLAUDE_CONNECTOR_AUTH_TOKEN                               ║
║      /apps/onramp/services-enabled/claude-connector.env          ║
╚══════════════════════════════════════════════════════════════════╝
""".strip()

_token_warned = False


def call_mcp_tool(tool_name: str, arguments: dict, timeout: int = 10) -> dict | None:
    """Call an MCP tool via the server's HTTP endpoint."""
    global _token_warned
    if not TOKEN and not _token_warned:
        print(_MISSING_TOKEN_WARNING, file=sys.stderr)
        _token_warned = True
        return None

    url = f"{SERVER}/mcp"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {TOKEN}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            # Parse SSE format: extract the JSON from "data: {...}" line
            result = _parse_sse(raw)
            if result and "result" in result:
                content = result["result"].get("content", [])
                for item in content:
                    if item.get("type") == "text":
                        return json.loads(item["text"])
    except Exception as e:
        print(f"[mcp_client] {tool_name} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    return None


def _parse_sse(raw: str) -> dict | None:
    """Parse an SSE response, extracting JSON from the data: line."""
    for line in raw.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    # Fall back to parsing the whole thing as JSON (non-SSE response)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
