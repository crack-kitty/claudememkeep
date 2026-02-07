# claudememkeep — Shared MCP Memory Server

A shared memory layer for Claude Code and Claude.ai. Both interfaces connect to the same MCP server to read and write project context, decisions, and session history in real time.

## What It Does

- **Claude Code** connects via MCP tools and (optionally) lifecycle hooks
- **Claude.ai** connects via a Connector
- Both read/write to the same PostgreSQL database
- Full-text search across all stored context
- Automatic session capture via Claude Code hooks

## Prerequisites

- [Onramp](https://github.com/traefikturkey/onramp) deployment framework with Traefik
- [Joyride](https://github.com/traefikturkey/joyride) DNS (with clustering enabled if multi-host)
- Docker and Docker Compose
- Claude Code CLI installed

## Installation

### Step 1: Deploy via Onramp

```bash
cd /apps/onramp
make enable-service claude-connector
make restart
```

This will:
- Symlink the service YAML into `services-enabled/`
- Auto-generate secure values for `CLAUDE_CONNECTOR_AUTH_TOKEN` and `CLAUDE_CONNECTOR_DB_PASSWORD`
- Create the PostgreSQL data directory
- Build and start both the MCP server and its database

### Step 2: Verify the deployment

```bash
curl https://claude-connector.YOUR_DOMAIN/health
# Should return: {"status":"healthy"}
```

### Step 3: Retrieve your auth token

The token was auto-generated during Step 1. Retrieve it with:

```bash
grep CLAUDE_CONNECTOR_AUTH_TOKEN /apps/onramp/services-enabled/claude-connector.env
```

Save this value — you'll need it for Steps 4 and 6.

### Step 4: Register MCP server with Claude Code

```bash
claude mcp add claude-connector \
  -t http \
  -s user \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -- https://claude-connector.YOUR_DOMAIN/mcp
```

Verify it works by starting a Claude Code session and asking it to call `get_project_summary`.

### Step 5: Configure hooks (optional)

Hooks automate context capture. They inject recent shared context at session start and save session summaries at session end.

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "MCP_AUTH_TOKEN=YOUR_TOKEN_HERE python3 /path/to/claudememkeep/hooks/session-start.py",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "MCP_AUTH_TOKEN=YOUR_TOKEN_HERE python3 /path/to/claudememkeep/hooks/session-end.py",
            "timeout": 30
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "MCP_AUTH_TOKEN=YOUR_TOKEN_HERE python3 /path/to/claudememkeep/hooks/pre-compact.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/claudememkeep` with the actual path where this repo lives, and `YOUR_TOKEN_HERE` with the token from Step 3.

The hooks use environment variables so you can also set `MCP_AUTH_TOKEN` globally in your shell profile instead of inlining it.

### Step 6: Connect Claude.ai (optional)

1. Go to **Claude.ai** > **Settings** > **Connectors** > **Add custom connector**
2. Name: `claude-connector` (or whatever you like)
3. URL: `https://claude-connector.YOUR_DOMAIN/mcp`
4. Leave OAuth client ID and secret blank
5. Enable the connector in conversations as needed

> **Note on auth:** The server currently runs authless because Claude.ai's OAuth
> implementation for custom MCP servers is broken
> ([anthropics/claude-code#5826](https://github.com/anthropics/claude-code/issues/5826)).
> A `HybridAuthProvider` with full OAuth + static bearer token support is ready in
> `server/app.py` — uncomment the `auth =` line when Anthropic fixes their client.
> Claude Code continues to send its bearer token which is harmlessly ignored.

## MCP Tools

Once connected, these tools are available:

| Tool | Description |
|------|-------------|
| `save_context` | Store a piece of context (decision, note, code_change, or context) |
| `search_context` | Full-text search across all stored artifacts |
| `get_project_summary` | Overview: recent decisions, sessions, artifact counts |
| `log_decision` | Quick way to record a decision with reasoning |
| `get_recent_activity` | Everything from the last N hours |
| `log_session` | Register or update a session record |

## Configuration

### Environment variables

All configuration is in `/apps/onramp/services-enabled/claude-connector.env`:

| Variable | Purpose | Default |
|----------|---------|---------|
| `CLAUDE_CONNECTOR_AUTH_TOKEN` | Bearer token for MCP auth | Auto-generated |
| `CLAUDE_CONNECTOR_DB_PASSWORD` | PostgreSQL password | Auto-generated |
| `CLAUDE_CONNECTOR_DB_USER` | PostgreSQL user | `claude_connector` |
| `CLAUDE_CONNECTOR_DB_NAME` | Database name | `claude_connector` |
| `CLAUDE_CONNECTOR_HOST_NAME` | Subdomain for Traefik | `claude-connector` |

### Hook environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `MCP_AUTH_TOKEN` | Auth token (same as above) | None (required) |
| `MCP_SERVER_URL` | Server base URL | `https://claude-connector.ckcompute.xyz` |

Override `MCP_SERVER_URL` if your domain differs from the default.

## Local Development

```bash
# Start local dev stack (MCP server + PostgreSQL)
docker compose up --build

# Health check
curl http://localhost:8081/health

# Test a tool call
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer dev-token" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_project_summary",
      "arguments": {"project": "default"}
    }
  }'
```

The local dev stack uses `dev-token` as the auth token and maps to port 8081.

## Architecture

```
Claude Code ──MCP──> ┌─────────────────────┐
                     │  FastMCP Server      │
                     │  (server/app.py)     │──> PostgreSQL
                     │  6 tools + /health   │    (full-text search)
Claude.ai ───MCP──> └─────────────────────┘

Hooks (optional):
  SessionStart  → injects recent context into new sessions
  SessionEnd    → saves session summary
  PreCompact    → archives transcript before context compression
```
