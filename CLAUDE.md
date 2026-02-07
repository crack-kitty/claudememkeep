# claudememkeep — Shared MCP Memory Server

## What This Is

A FastMCP server providing shared context/memory between Claude Code and Claude.ai sessions. Both interfaces connect via MCP protocol and can read/write project context, decisions, and session summaries.

## Architecture

- **server/app.py** — FastMCP server with 6 tools + health endpoint
- **server/db.py** — asyncpg database layer (PostgreSQL)
- **server/models.py** — Pydantic input/output models
- **sql/schema.sql** — PostgreSQL schema with full-text search
- **hooks/** — Claude Code lifecycle hooks (session-start, session-end, pre-compact)

## Tech Stack

- Python 3.12, FastMCP 2.x, asyncpg, uvicorn
- PostgreSQL 16 with TSVECTOR full-text search
- Docker, deployed via onramp framework as `claude-connector.ckcompute.xyz`

## MCP Tools

| Tool | Purpose |
|------|---------|
| `save_context` | Store decisions, notes, context, code changes |
| `search_context` | Full-text search across artifacts |
| `get_project_summary` | Overview: recent decisions, sessions, counts |
| `log_decision` | Convenience wrapper for decision artifacts |
| `get_recent_activity` | All activity from last N hours |
| `log_session` | Register/update session records |

## Development

```bash
# Local dev
docker compose up

# Health check
curl http://localhost:8081/health

# Deploy via onramp
cd /apps/onramp && make enable-service claude-connector && make restart
```

## Key Design Decisions

- PostgreSQL over SQLite for concurrent access and proper FTS
- Bearer token auth via FastMCP's StaticTokenVerifier
- Stateless HTTP transport (no SSE) for Claude.ai Connector compatibility
- Hooks use raw urllib (no dependencies) for reliability
- Schema auto-applied via both asyncpg init and Docker initdb.d mount
