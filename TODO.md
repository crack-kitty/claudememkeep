Remaining steps:
  1. [done] Deploy via onramp
  2. [done] Register MCP server with Claude Code
  3. [done] Configure hooks in Claude Code settings
  4. [done] Set up Claude.ai Connector (authless — OAuth blocked by anthropics/claude-code#5826)
  5. [done] End-to-end verified: Claude.ai → save → Claude Code → read

Future:
  - Re-enable HybridAuthProvider OAuth when Anthropic fixes their client
  - Consider Cloudflare WAF rate limiting for the authless endpoint
