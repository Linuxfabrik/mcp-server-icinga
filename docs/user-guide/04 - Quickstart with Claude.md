# Quickstart with Claude

This page walks through bringing up `mcp-server-icinga` end-to-end and verifying it works with Claude. At this stage of the project the only tool registered is `health_check`, which confirms the server starts, finds its configuration and reports which backends it knows about. That is enough to validate the installation, the configuration file lookup, the secret injection and the MCP transport in one shot. Real Icinga tools follow in later releases.


## 1. Prepare a minimal configuration

For the smoke test you do not need any Icinga backend at all. Create an empty configuration file at the user-default path:

```bash
mkdir --parents ~/.config/mcp-server-icinga
touch ~/.config/mcp-server-icinga/config.yaml
```

The server accepts an empty file as a valid configuration: nothing is wired up, only `health_check` is exposed.

For a more interesting smoke test, fill in just the `icinga2_core` section so that `health_check` reports `icinga2_core: true`:

```yaml
icinga2_core:
  url: 'https://icinga2.example.com:5665'
  username: 'mcp-readonly'
  password: !env ICINGA2_CORE_PASSWORD
  verify_tls: true
```


## 2. Wire the server into Claude


### Claude Desktop

Edit Claude Desktop's configuration file:

- Linux: `~/.config/Claude/claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an entry under `mcpServers`:

```json
{
  "mcpServers": {
    "icinga": {
      "command": "mcp-server-icinga",
      "env": {
        "ICINGA_MCP_CONFIG": "/home/yourself/.config/mcp-server-icinga/config.yaml",
        "ICINGA2_CORE_PASSWORD": "the-actual-password"
      }
    }
  }
}
```

If `mcp-server-icinga` is not on the PATH that Claude Desktop sees (common with `pipx` or virtualenv installs), use the absolute path of the binary instead, for example `/home/yourself/.local/bin/mcp-server-icinga` or `/home/yourself/venvs/mcp-server-icinga/bin/mcp-server-icinga`.

Restart Claude Desktop. The server appears under the "Connected MCP servers" indicator (the small slider icon at the bottom of the conversation field).


### Claude Code

In a project directory, register the server with the `claude mcp` CLI:

```bash
claude mcp add icinga -- mcp-server-icinga
```

Or write the equivalent JSON into `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "icinga": {
      "command": "mcp-server-icinga",
      "env": {
        "ICINGA_MCP_CONFIG": "/home/yourself/.config/mcp-server-icinga/config.yaml",
        "ICINGA2_CORE_PASSWORD": "the-actual-password"
      }
    }
  }
}
```

Verify the registration:

```bash
claude mcp list
```


## 3. Test it from Claude

Open a chat with Claude and ask it to use the new server. Useful first prompts:

> Run the `health_check` tool from the `icinga` MCP server.

> Show me the status of the icinga MCP server.

> Which Icinga backends does the icinga MCP server know about?

Expected response: Claude calls `health_check`, returns a JSON-shaped payload similar to:

```json
{
  "name": "mcp-server-icinga",
  "version": "0.0.0",
  "config_path": "/home/yourself/.config/mcp-server-icinga/config.yaml",
  "backends": {
    "icinga2_core": true,
    "icinga_web": false,
    "icinga_director": false,
    "tsdb": false
  },
  "icinga2_core_write_enabled": false,
  "monitoring_plugins_catalog": "bundled-snapshot (not yet implemented)"
}
```

That confirms:

- the binary starts in the environment Claude spawns it in,
- the configuration file is found,
- the YAML parses cleanly and the `!env` references resolve,
- the MCP stdio transport works end-to-end.

If anything is off, check the Claude Desktop or Claude Code MCP logs - on Linux they live under `~/.config/Claude/logs/` and `~/.config/claude/logs/` respectively. The server itself writes any startup error to its stderr, which the MCP client captures into those logs.


## 4. Iterate

Once the smoke test works, fill out the rest of the configuration ([Configuration](03 - Configuration.md)) and watch the new backends light up in the next `health_check` response. The next releases of `mcp-server-icinga` will add real Icinga tools on top; they appear automatically as the server-side tool list grows.
