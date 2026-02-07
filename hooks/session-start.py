#!/usr/bin/env python3
"""SessionStart hook — injects recent shared context into Claude Code sessions."""

import json
import os
import sys
import urllib.request

TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")
SERVER = os.environ.get("MCP_SERVER_URL", "https://claude-connector.ckcompute.xyz")


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        data = {}

    # Determine project from cwd
    cwd = data.get("cwd", "")
    project = os.path.basename(cwd) if cwd else "default"

    context_parts = []

    # Fetch recent activity from MCP server
    try:
        activity = call_mcp_tool("get_recent_activity", {
            "project": project,
            "hours": 48,
        })
        if activity:
            artifacts = activity.get("artifacts", [])
            sessions = activity.get("sessions", [])

            if artifacts:
                context_parts.append("## Recent Shared Context")
                for a in artifacts[:10]:
                    title = a.get("title", a.get("type", ""))
                    content = a.get("content", "")[:200]
                    created = a.get("created_at", "")[:19]
                    context_parts.append(f"- **[{a.get('type')}]** {title} ({created})")
                    if content:
                        context_parts.append(f"  {content}")

            if sessions:
                context_parts.append("\n## Recent Sessions")
                for s in sessions[:5]:
                    summary = s.get("summary", "No summary")
                    source = s.get("source", "unknown")
                    started = s.get("started_at", "")[:19]
                    context_parts.append(f"- [{source}] {started}: {summary}")
    except Exception:
        # Silently fail — don't block session start
        pass

    output = {}
    if context_parts:
        output["additionalContext"] = "\n".join(context_parts)

    json.dump(output, sys.stdout)


def call_mcp_tool(tool_name: str, arguments: dict) -> dict | None:
    """Call an MCP tool via the server's HTTP endpoint."""
    url = f"{SERVER}/mcp"

    # Use JSON-RPC to call the tool
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
            "Authorization": f"Bearer {TOKEN}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read())
            # Extract text content from MCP response
            if "result" in result:
                content = result["result"].get("content", [])
                for item in content:
                    if item.get("type") == "text":
                        return json.loads(item["text"])
    except Exception:
        return None
    return None


if __name__ == "__main__":
    main()
