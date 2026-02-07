#!/usr/bin/env python3
"""PreCompact hook — archives transcript before context compression."""

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

    if not transcript_path or not os.path.exists(transcript_path):
        json.dump({}, sys.stdout)
        return

    # Read and summarize transcript content
    transcript_summary = summarize_transcript(transcript_path)

    if transcript_summary:
        try:
            call_mcp_tool("save_context", {
                "project": project,
                "content": transcript_summary,
                "type": "context",
                "title": f"Pre-compact archive: {session_id[:12] if session_id else 'unknown'}",
                "tags": ["auto-captured", "pre-compact"],
            })
        except Exception:
            pass

    json.dump({}, sys.stdout)


def summarize_transcript(transcript_path: str) -> str:
    """Build a summary of the transcript for archival."""
    messages = []
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    role = entry.get("role", "")
                    content = entry.get("content", "")

                    if isinstance(content, list):
                        texts = [
                            c.get("text", "")
                            for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        ]
                        content = "\n".join(texts)

                    if isinstance(content, str) and content.strip():
                        # Keep first 500 chars of each message
                        truncated = content.strip()[:500]
                        messages.append(f"[{role}]: {truncated}")
                except json.JSONDecodeError:
                    continue
    except Exception:
        return ""

    if not messages:
        return ""

    # Build a compact summary, limit total to 5000 chars
    summary = "\n\n".join(messages)
    if len(summary) > 5000:
        summary = summary[:5000] + "\n\n[...truncated]"

    return summary


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
