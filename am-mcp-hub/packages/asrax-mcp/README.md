# @asrax/mcp

stdio MCP client for Cursor against **AM MCP Hub**.

```bash
npm install -g @asrax/mcp
# or
npx @asrax/mcp
```

## Cursor `mcp.json`

```json
{
  "mcpServers": {
    "asrax": {
      "command": "npx",
      "args": ["-y", "@asrax/mcp"],
      "env": {
        "ASRAX_MCP_URL": "https://am-dev.asrax.in/mcp",
        "ASRAX_KEY_ID": "…",
        "ASRAX_KEY_SECRET": "…"
      }
    }
  }
}
```

Credentials load from `~/.asrax/credentials.env` (or `ASRAX_HOME`). Legacy `~/.am` is still read as a fallback.

Local hub:

```bash
ASRAX_MCP_URL=http://127.0.0.1:8130/mcp HUB_ADMIN_TOKEN=dev npx @asrax/mcp
```
