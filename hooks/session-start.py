#!/usr/bin/env python3
"""SessionStart hook — registers session, syncs MEMORY.md, injects recent context."""

import glob
import hashlib
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
    cwd = data.get("cwd", "")
    project = os.path.basename(cwd) if cwd else "default"

    # Register the session immediately so there's a record even if session crashes
    if session_id:
        call_mcp_tool("log_session", {
            "session_id": session_id,
            "source": "claude_code",
            "project": project,
        })

    # Sync MEMORY.md if it changed
    sync_memory_md(cwd, project)

    # Fetch recent activity and inject as context
    context_parts = []
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
    except Exception as e:
        print(f"[session-start] fetch activity failed: {e}", file=sys.stderr)

    output = {}
    if context_parts:
        output["additionalContext"] = "\n".join(context_parts)

    json.dump(output, sys.stdout)


def sync_memory_md(cwd: str, project: str):
    """Push MEMORY.md to shared memory if its content has changed."""
    if not cwd:
        return

    memory_path = find_memory_md(cwd)
    if not memory_path:
        return

    try:
        with open(memory_path) as f:
            content = f.read()
    except Exception:
        return

    if not content.strip():
        return

    # Check hash to avoid redundant pushes
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    hash_dir = os.path.expanduser("~/.claude/.memhash")
    hash_file = os.path.join(hash_dir, project)

    try:
        os.makedirs(hash_dir, exist_ok=True)
        if os.path.exists(hash_file):
            with open(hash_file) as f:
                stored_hash = f.read().strip()
            if stored_hash == content_hash:
                return  # No change
    except Exception:
        pass  # If we can't read the hash, push anyway

    # Push to shared memory
    result = call_mcp_tool("save_context", {
        "project": project,
        "content": content,
        "type": "context",
        "title": f"MEMORY.md sync — {project}",
        "tags": ["memory-md", "auto-sync"],
    })

    if result is not None:
        # Update stored hash only on successful push
        try:
            with open(hash_file, "w") as f:
                f.write(content_hash)
        except Exception as e:
            print(f"[session-start] failed to write hash: {e}", file=sys.stderr)


def find_memory_md(cwd: str) -> str | None:
    """Find the project MEMORY.md file."""
    # Check the Claude Code project memory path pattern
    # ~/.claude/projects/-{sanitized_cwd}/memory/MEMORY.md
    home = os.path.expanduser("~")
    sanitized = cwd.replace("/", "-")
    project_memory = os.path.join(home, ".claude", "projects", sanitized, "memory", "MEMORY.md")
    if os.path.exists(project_memory):
        return project_memory

    # Also check via glob for flexibility (e.g. different sanitization)
    pattern = os.path.join(home, ".claude", "projects", "*", "memory", "MEMORY.md")
    for path in glob.glob(pattern):
        # Match if the sanitized cwd appears in the path
        if sanitized in path or os.path.basename(cwd) in path:
            return path

    return None


if __name__ == "__main__":
    main()
