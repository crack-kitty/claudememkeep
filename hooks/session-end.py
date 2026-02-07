#!/usr/bin/env python3
"""SessionEnd hook — saves session summary to shared memory."""

import json
import os
import sys

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

    if not session_id:
        json.dump({}, sys.stdout)
        return

    # Extract a structured summary from the transcript
    summary = extract_summary(transcript_path)

    # Update the session record (upserts — session-start already created the row)
    try:
        call_mcp_tool("log_session", {
            "session_id": session_id,
            "source": "claude_code",
            "project": project,
            "summary": summary,
        })
    except Exception as e:
        print(f"[session-end] log_session failed: {e}", file=sys.stderr)

    json.dump({}, sys.stdout)


def extract_summary(transcript_path: str) -> str:
    """Extract first user message + last assistant message from transcript."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    first_user = ""
    last_assistant = ""

    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    role = entry.get("role", "")
                    content = _extract_text(entry)

                    if not content:
                        continue

                    if role == "user" and not first_user:
                        first_user = content
                    elif role == "assistant":
                        last_assistant = content
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"[session-end] transcript read failed: {e}", file=sys.stderr)
        return ""

    parts = []
    if first_user:
        parts.append(f"Task: {first_user[:500]}")
    if last_assistant:
        parts.append(f"Outcome: {last_assistant[:1000]}")

    return "\n\n".join(parts)


def _extract_text(entry: dict) -> str:
    """Extract text content from a transcript entry."""
    content = entry.get("content", "")
    if isinstance(content, list):
        texts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        content = "\n".join(texts)
    if isinstance(content, str):
        return content.strip()
    return ""


if __name__ == "__main__":
    main()
