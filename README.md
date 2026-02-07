# claudememkeep — Shared MCP Memory Server

A shared memory layer for Claude Code and Claude.ai. Both interfaces connect to the same MCP server to read and write project context, decisions, and session history in real time.

## What It Does

- **Claude Code** connects via MCP tools and (optionally) lifecycle hooks
- **Claude.ai** connects via a Connector
- Both read/write to the same PostgreSQL database
- Full-text search across all stored context
- Automatic session capture via Claude Code hooks

## Architecture: Server vs. Hooks

This repo contains **two separate pieces** that are deployed differently:

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Server (Docker)                   │
│         server/app.py + PostgreSQL database              │
│         Runs once, centrally, serves everyone            │
│                                                         │
│   Claude.ai ──Connector──> /mcp ──> 6 tools ──> DB     │
│   Claude Code ──MCP─────> /mcp ──> 6 tools ──> DB     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              Hooks (local per machine)                   │
│         hooks/*.py — run by Claude Code locally          │
│         Each machine running Claude Code needs its own   │
│         copy of these files + configuration              │
│                                                         │
│   SessionStart  → registers session, syncs MEMORY.md    │
│   SessionEnd    → saves structured session summary      │
│   PreCompact    → archives user messages before compact  │
└─────────────────────────────────────────────────────────┘
```

**The server** (`server/`, `sql/`) is the shared bridge between Claude Code and Claude.ai. It gets packaged into a Docker image and deployed once — via onramp, plain Docker, or however you like. Both Claude.ai (via Connector) and Claude Code (via MCP) connect to it and share the same database. Changes to server code require rebuilding the container (`make update-service claude-connector`).

**The hooks** (`hooks/`) are client-side scripts that run locally on each machine where Claude Code is installed. They automate context capture — syncing MEMORY.md, saving session summaries, archiving transcripts before compaction. The server can serve multiple Claude Code instances across different machines, but each machine needs its own local copy of the hooks configured in `~/.claude/settings.json`.

**When do you need to update what?**

| Change made to... | What to do |
|---|---|
| `server/` or `sql/` | Rebuild and restart the container |
| `hooks/` | `git pull` on each machine running Claude Code |
| `docker-compose.yml` or onramp config | `make restart` in onramp |

## Prerequisites

- [Onramp](https://github.com/traefikturkey/onramp) deployment framework with Traefik
- Docker and Docker Compose
- Claude Code CLI installed

> **Note on Onramp:** This application was built to run inside the onramp framework, which handles Traefik routing, env scaffolding, and service lifecycle. Onramp also installs Docker and Compose for you, so if you're using onramp those aren't separate prerequisites. That said, the server is just a Docker Compose stack — if you'd rather run it standalone, fork away and adapt the compose file to your setup.

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

### Step 3: Set up your secrets file

The token was auto-generated during Step 1. Create a secrets file that the hooks will source:

```bash
# Get your token
grep CLAUDE_CONNECTOR_AUTH_TOKEN /apps/onramp/services-enabled/claude-connector.env

# Create ~/.claude/.secrets (gitignored, one-time setup per machine)
cat > ~/.claude/.secrets << 'EOF'
export MCP_AUTH_TOKEN=your-token-here
export MCP_SERVER_URL=https://claude-connector.your-domain.com
EOF
```

Replace both values with your actual token and domain. This is a one-time setup per machine. If you skip this step, the hooks will print a clear error telling you what to do.

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

Hooks automate context capture. They register sessions, sync MEMORY.md, save structured summaries, and archive transcripts before compaction.

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'source ~/.claude/.secrets 2>/dev/null; python3 /path/to/claudememkeep/hooks/session-start.py'",
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
            "command": "bash -c 'source ~/.claude/.secrets 2>/dev/null; python3 /path/to/claudememkeep/hooks/session-end.py'",
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
            "command": "bash -c 'source ~/.claude/.secrets 2>/dev/null; python3 /path/to/claudememkeep/hooks/pre-compact.py'",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/claudememkeep` with the actual path where this repo lives. The token is read from `~/.claude/.secrets` which you created in Step 3 — no secrets in this file.

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

These are sourced from `~/.claude/.secrets` (see Step 3):

| Variable | Purpose | Default |
|----------|---------|---------|
| `MCP_AUTH_TOKEN` | Auth token (same as above) | None (required) |
| `MCP_SERVER_URL` | Server base URL | `https://claude-connector.example.com` |

Override `MCP_SERVER_URL` in `~/.claude/.secrets` if your domain differs from the default.

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

See [Architecture: Server vs. Hooks](#architecture-server-vs-hooks) at the top for the full picture.
