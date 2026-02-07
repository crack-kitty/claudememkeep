#!/usr/bin/env python3
"""PreCompact hook — archives user messages before context compression."""

import json
import os
import sys
from datetime import datetime, timezone

# Add hooks dir to path for shared module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import call_mcp_tool


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

    summary = extract_user_messages(transcript_path)

    if summary:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        try:
            call_mcp_tool("save_context", {
                "project": project,
                "content": summary,
                "type": "context",
                "title": f"Compact — {project} @ {timestamp}",
                "tags": ["auto-captured", "pre-compact"],
            })
        except Exception as e:
            print(f"[pre-compact] save_context failed: {e}", file=sys.stderr)

    json.dump({}, sys.stdout)


def extract_user_messages(transcript_path: str) -> str:
    """Extract user messages from transcript (300 chars each, 3000 total cap)."""
    messages = []
    total_len = 0

    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("role") != "user":
                        continue

                    content = entry.get("content", "")
                    if isinstance(content, list):
                        texts = [
                            c.get("text", "")
                            for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        ]
                        content = "\n".join(texts)

                    if isinstance(content, str) and content.strip():
                        truncated = content.strip()[:300]
                        msg = f"- {truncated}"
                        if total_len + len(msg) > 3000:
                            break
                        messages.append(msg)
                        total_len += len(msg)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"[pre-compact] transcript read failed: {e}", file=sys.stderr)
        return ""

    return "\n".join(messages)


if __name__ == "__main__":
    main()
