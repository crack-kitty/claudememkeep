#!/usr/bin/env python3
"""SessionEnd hook — saves session summary to shared memory."""

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

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")
    cwd = data.get("cwd", "")
    project = os.path.basename(cwd) if cwd else "default"

    if not session_id:
        return

    # Read transcript to extract last assistant summary
    summary = extract_summary(transcript_path)

    # Log the session
    try:
        call_mcp_tool("log_session", {
            "session_id": session_id,
            "source": "claude_code",
            "project": project,
            "summary": summary,
        })
    except Exception:
        pass

    # Save the summary as a context artifact if substantial
    if summary and len(summary) > 50:
        try:
            call_mcp_tool("save_context", {
                "project": project,
                "content": summary,
                "type": "context",
                "title": f"Session summary: {session_id[:12]}",
                "tags": ["auto-captured", "session-end"],
            })
        except Exception:
            pass

    json.dump({}, sys.stdout)


def extract_summary(transcript_path: str) -> str:
    """Extract the last assistant message from a JSONL transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    last_assistant = ""
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("role") == "assistant":
                        # Extract text content
                        content = entry.get("content", "")
                        if isinstance(content, list):
                            texts = [
                                c.get("text", "")
                                for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            ]
                            content = "\n".join(texts)
                        if isinstance(content, str) and content.strip():
                            last_assistant = content.strip()
                except json.JSONDecodeError:
                    continue
    except Exception:
        return ""

    # Truncate to reasonable length
    if len(last_assistant) > 2000:
        last_assistant = last_assistant[:2000] + "..."

    return last_assistant


def call_mcp_tool(tool_name: str, arguments: dict) -> dict | None:
    """Call an MCP tool via the server's HTTP endpoint."""
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
            "Authorization": f"Bearer {TOKEN}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            result = json.loads(resp.read())
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
