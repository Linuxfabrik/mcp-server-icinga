# Quickstart with Claude

This page brings up `mcp-server-icinga` end-to-end and verifies it with Claude. The smoke test uses `health_check`, which confirms the server starts, finds its configuration and reports which backends it knows about - enough to validate the installation, the config file lookup, the secret injection and the MCP transport in one shot. The catalog and Icinga 2 Core tools then come online as you configure their backends.


## 1. Prepare a minimal configuration

For the smoke test you do not need any Icinga backend at all. Create an empty configuration file at the user-default path:

```bash
mkdir --parents ~/.config/Linuxfabrik/mcp-server-icinga
touch ~/.config/Linuxfabrik/mcp-server-icinga/config.yaml
```

The server accepts an empty file as a valid configuration: nothing is wired up, only `health_check` is exposed.

For a more interesting smoke test, register one Icinga instance so that `health_check` lists it under `instances`:

```yaml
instances:
  prod:
    icinga2_core:
      url: 'https://icinga2.example.com:5665'
      username: 'mcp-readonly'
      password: !env ICINGA2_PROD_PASSWORD
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
    "linuxfabrik-icinga": {
      "command": "mcp-server-icinga",
      "env": {
        "ICINGA_MCP_CONFIG": "/home/yourself/.config/Linuxfabrik/mcp-server-icinga/config.yaml",
        "ICINGA2_PROD_PASSWORD": "linuxfabrik"
      }
    }
  }
}
```

If `mcp-server-icinga` is not on the PATH that Claude Desktop sees (common with `pipx` or virtualenv installs), use the absolute path of the binary instead, for example `/home/yourself/.local/bin/mcp-server-icinga` or `/home/yourself/venvs/mcp-server-icinga/bin/mcp-server-icinga`.

Restart Claude Desktop. The server appears under the "Connected MCP servers" indicator (the small slider icon at the bottom of the conversation field).


### Claude Code

Register the server with the `claude mcp` CLI. With `--scope user` it is available in every project, not just the current directory:

```bash
claude mcp add --scope user linuxfabrik-icinga -- mcp-server-icinga
```

If `mcp-server-icinga` is not on the PATH that Claude Code spawns (common with a virtualenv or source install), pass the absolute path of the binary instead. For the editable install from [Installation](02 - Installation.md) that is the venv's `bin/`:

```bash
claude mcp add --scope user linuxfabrik-icinga -- /path/to/mcp-server-icinga/.venv/bin/mcp-server-icinga
```

Drop `--scope user` to register the server only for the current project (written to `.mcp.json` at the project root). The equivalent JSON is:

```json
{
  "mcpServers": {
    "linuxfabrik-icinga": {
      "command": "mcp-server-icinga",
      "env": {
        "ICINGA_MCP_CONFIG": "/home/yourself/.config/Linuxfabrik/mcp-server-icinga/config.yaml",
        "ICINGA2_PROD_PASSWORD": "linuxfabrik"
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

> Run the `health_check` tool from the `linuxfabrik-icinga` MCP server.

> Show me the status of the `linuxfabrik-icinga` MCP server.

> Which Icinga backends does the `linuxfabrik-icinga` MCP server know about?

Expected response: Claude calls `health_check`, returns a JSON-shaped payload similar to:

```json
{
  "name": "Linuxfabrik Icinga",
  "version": "0.0.0",
  "config_path": "/home/yourself/.config/Linuxfabrik/mcp-server-icinga/config.yaml",
  "instances": {
    "prod": {
      "icinga2_core": true,
      "icinga_web": false,
      "icinga_director": false,
      "tsdb": false,
      "icinga2_core_write_enabled": false
    }
  },
  "monitoring_plugins_catalog": {
    "source": "bundled-snapshot (not yet implemented)"
  }
}
```

That confirms:

- the binary starts in the environment Claude spawns it in,
- the configuration file is found,
- the YAML parses cleanly and the `!env` references resolve,
- the MCP stdio transport works end-to-end.

If anything is off, check the Claude Desktop or Claude Code MCP logs - on Linux they live under `~/.config/Claude/logs/` and `~/.config/claude/logs/` respectively. The server itself writes any startup error to its stderr, which the MCP client captures into those logs.


## 4. Try the plugin catalog

If you added `monitoring_plugins.catalog_path` to the config, the catalog tools register and `health_check` reports `monitoring_plugins_catalog.source: live` with a plugin count (restart the MCP client first). A couple of quick checks:

> List all plugins that run on Windows.

> Explain the `gitlab-version` plugin. What does it check, what arguments does it take, what states can it return?

This is where the catalog pays off: the server combines its catalog tools in one turn so Claude's reasoning stays grounded in the actual plugin source instead of the LLM's training data. See [Example Prompts](06 - Example Prompts.md) for the full set, including reading a plugin's source and the live host and service tools.


## 5. Iterate

Fill out the rest of the configuration ([Configuration](03 - Configuration.md)) and the matching tools light up in the next `health_check` and `tools/list` after a client restart. An instance with a reachable `icinga2_core` backend enables the live host and service tools; adding write credentials enables acknowledge, downtime and recheck. Backends appear automatically as their config sections are filled in.
