"""FastMCP shared memory server."""

import os

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
from mcp.server.auth.settings import ClientRegistrationOptions
from starlette.responses import JSONResponse

from server import db

_token = os.environ.get("MCP_AUTH_TOKEN", "dev-token")
_base_url = os.environ.get("MCP_BASE_URL", "https://claude-connector.example.com")


class HybridAuthProvider(InMemoryOAuthProvider):
    """OAuth provider that also accepts a static bearer token.

    Claude.ai uses the full OAuth flow (DCR + authorize + token exchange).
    Claude Code and hooks use a pre-shared bearer token.
    """

    def __init__(self, base_url: str, static_token: str):
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
        )
        self._static_token = static_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if token == self._static_token:
            return AccessToken(
                token=token,
                client_id="claude-code",
                scopes=[],
                expires_at=None,
            )
        return await super().verify_token(token)


# TODO: Switch to HybridAuthProvider once Claude.ai fixes OAuth with custom MCP servers
# See: https://github.com/anthropics/claude-code/issues/11814
# auth = HybridAuthProvider(base_url=_base_url, static_token=_token)
mcp = FastMCP("Shared Memory")


@mcp.tool()
async def save_context(
    project: str,
    content: str,
    type: str,
    title: str | None = None,
    tags: list[str] = [],
) -> dict:
    """Store a piece of context in shared memory.

    Use this to save decisions, notes, code changes, or general context
    that should be shared across Claude Code and Claude.ai sessions.

    Args:
        project: Project identifier (e.g. 'claudememkeep', 'default')
        content: The context content to save
        type: One of: decision, context, note, code_change
        title: Optional short title for the artifact
        tags: Optional list of tags for categorization
    """
    if type not in ("decision", "context", "note", "code_change"):
        return {"error": "type must be one of: decision, context, note, code_change"}
    result = await db.save_artifact(
        project=project, type=type, content=content, title=title, tags=tags
    )
    return {"saved": result}


@mcp.tool()
async def search_context(
    query: str, project: str = "default", limit: int = 5
) -> dict:
    """Full-text search across shared memory artifacts.

    Searches titles (higher weight) and content using PostgreSQL full-text search.
    Returns ranked results.

    Args:
        query: Search query (supports natural language and boolean operators)
        project: Project to search in
        limit: Maximum number of results (1-50)
    """
    results = await db.search_artifacts(query=query, project=project, limit=limit)
    return {"results": results, "count": len(results)}


@mcp.tool()
async def get_project_summary(project: str = "default") -> dict:
    """Get an overview of a project's shared memory.

    Returns recent decisions (last 10), recent sessions (last 5),
    and artifact counts by type.

    Args:
        project: Project identifier
    """
    return await db.get_summary(project=project)


@mcp.tool()
async def log_decision(
    project: str, decision: str, reasoning: str = ""
) -> dict:
    """Log a decision to shared memory.

    Convenience wrapper that saves an artifact with type='decision'.
    Use this when a significant decision is made during a session.

    Args:
        project: Project identifier
        decision: The decision that was made
        reasoning: Why this decision was made
    """
    content = decision
    if reasoning:
        content = f"{decision}\n\nReasoning: {reasoning}"
    result = await db.save_artifact(
        project=project, type="decision", content=content, title=decision[:200]
    )
    return {"logged": result}


@mcp.tool()
async def get_recent_activity(
    project: str = "default", hours: int = 48
) -> dict:
    """Get all recent artifacts and sessions.

    Returns everything from the last N hours, ordered by recency.

    Args:
        project: Project identifier
        hours: How many hours back to look (1-720)
    """
    return await db.get_recent(project=project, hours=hours)


@mcp.tool()
async def log_session(
    session_id: str, source: str, project: str = "default", summary: str = ""
) -> dict:
    """Register or update a session in shared memory.

    Call at session start to register, and at session end to update with summary.

    Args:
        session_id: Unique session identifier
        source: Either 'claude_ai' or 'claude_code'
        project: Project identifier
        summary: Session summary (usually set at session end)
    """
    if source not in ("claude_ai", "claude_code"):
        return {"error": "source must be 'claude_ai' or 'claude_code'"}
    result = await db.upsert_session(
        session_id=session_id, source=source, project=project, summary=summary
    )
    return {"session": result}


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Health check endpoint."""
    try:
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return JSONResponse({"status": "healthy"})
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "error": str(e)}, status_code=503)


# ASGI app for uvicorn
app = mcp.http_app(path="/mcp", stateless_http=True)

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8080, path="/mcp", stateless_http=True)
