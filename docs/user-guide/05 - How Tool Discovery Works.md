# How Tool Discovery Works

Concrete walk-through of what happens between "I write a Python function in `server.py`" and "Claude calls that function in response to my prompt". Uses the `health_check` tool as the running example because it has the smallest possible signature (no parameters) and we ship it on every deployment.


## The big picture, in four steps

1. **Source.** A Python function in `src/mcp_server_icinga/server.py` is decorated with `@mcp.tool()` from the `mcp` SDK's `FastMCP` API.
2. **Registration.** When `build_server()` runs at startup, the decorator inspects the function's docstring and type hints and produces a JSON-Schema description of the tool. That description goes into a per-server tool registry.
3. **Handshake.** When the MCP client (Claude Desktop, Claude Code, ...) spawns the server it asks `tools/list`. The server returns the registry as JSON. The client injects this list into the LLM's context for every following turn.
4. **Call.** Given a user message, the LLM picks a tool from the list, emits a structured `tools/call`, the server runs the underlying Python function, and the LLM turns the result into a natural-language reply.

Each step gets a section below with the real bytes that flow.


## Step 1: the source

The full registration of `health_check` lives in [`src/mcp_server_icinga/server.py`](https://github.com/Linuxfabrik/mcp-server-icinga/blob/main/src/mcp_server_icinga/server.py). Reduced to the parts the MCP layer actually consumes:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP('Linuxfabrik Icinga')

@mcp.tool()
def health_check() -> dict[str, Any]:
    """Report server status and which backends are configured.

    Returns the server name and version, the path of the loaded
    configuration file, a per-backend availability map and the status
    of the monitoring-plugins catalog. This is a pure inspection of the
    loaded configuration; it does not perform any live network checks.

    Use this to confirm that the MCP server is running with the
    configuration you expect after a restart of the MCP client.
    """
    return _health_check_payload(config, config_path, catalog)
```

Three things matter:

- **The function name** becomes the MCP tool name (`health_check`).
- **The docstring** becomes the tool description that the LLM sees. Everything between the triple quotes lands verbatim in the registry. This is the only handle the LLM has to decide whether the tool is relevant for a given user request, so docstrings are part of the API surface and we treat them as such.
- **The type hints** drive the JSON-Schema for the inputs and the result type. `health_check` has no parameters, so the input schema is empty. A tool with parameters and defaults gets a richer schema; we look at one further down.


## Step 2: what the decorator turns that into

`@mcp.tool()` walks the function signature and docstring, derives a JSON-Schema description and registers everything in `FastMCP._tool_manager`. The registered entry for `health_check` looks like this when serialised, with the `description` value shortened here for readability (in the actual payload it is the full docstring from above, with line breaks escaped as `\n`):

```json
{
  "name": "health_check",
  "description": "Report server status and which backends are configured.\n\n... (full docstring from Step 1) ...\n",
  "inputSchema": {
    "type": "object",
    "title": "health_checkArguments",
    "properties": {}
  }
}
```

For comparison, here is what `list_plugins(runs_on: str | None = None, name_contains: str | None = None)` produces. Notice how the optional parameters become `anyOf [string, null]` with `default: null`, and how `required` is omitted because both have defaults:

```json
{
  "name": "list_plugins",
  "description": "List every Linuxfabrik monitoring plugin the server knows about.\n\n...\n\nOptional filters, combined with logical AND:\n\n- `runs_on`: keep only plugins whose Fact Sheet says they run on\n  this platform, e.g. `'Linux'`, `'Windows'`, `'Cross-platform'`.\n- `name_contains`: case-insensitive substring match against the\n  plugin name. ...\n",
  "inputSchema": {
    "type": "object",
    "title": "list_pluginsArguments",
    "properties": {
      "runs_on": {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": null,
        "title": "Runs On"
      },
      "name_contains": {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "default": null,
        "title": "Name Contains"
      }
    }
  }
}
```

And `find_plugin_for_check_command(check_command: str)`, where the parameter has no default, is correctly marked as required:

```json
{
  "name": "find_plugin_for_check_command",
  "description": "Resolve an Icinga Director check command to the underlying\nmonitoring plugin.\n\n...",
  "inputSchema": {
    "type": "object",
    "title": "find_plugin_for_check_commandArguments",
    "properties": {
      "check_command": {"type": "string", "title": "Check Command"}
    },
    "required": ["check_command"]
  }
}
```

These are the actual payloads the SDK emits, captured live from the running server. The LLM never sees the Python source; it only sees these JSON descriptions.


## Step 3: the handshake over stdio

When the MCP client launches `mcp-server-icinga`, it speaks JSON-RPC 2.0 over stdin/stdout. After the initial `initialize` call, the client asks for the tool list:

```json
// Client -> server
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
```

The server replies with every registered tool in one message:

```json
// Server -> client
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      { "name": "health_check", "description": "...", "inputSchema": {...} },
      { "name": "catalog_info", "description": "...", "inputSchema": {...} },
      { "name": "list_plugins", "description": "...", "inputSchema": {...} },
      { "name": "explain_plugin", "description": "...", "inputSchema": {...} },
      { "name": "find_plugin_for_check_command", "description": "...", "inputSchema": {...} },
      { "name": "read_plugin_source", "description": "...", "inputSchema": {...} }
    ]
  }
}
```

The tool list depends on what the configuration enabled. With an empty `config.yaml` only `health_check` is in there. With `monitoring_plugins.catalog_path` set, the catalog tools join (`catalog_info`, `list_plugins`, `explain_plugin`, `find_plugin_for_check_command`, `read_plugin_source`). An instance with an `icinga2_core` backend adds the live host and service tools, and write credentials add the action tools. Tools whose backend section is missing from the configuration never enter the registry, so the LLM never sees them and cannot try to call them. That is the project's principle-of-least-privilege boundary; omitting `icinga2_core.write_password` is therefore a real, enforceable read-only mode, not just a hint.


## Step 4: an end-to-end call

User types in Claude Code:

> Run the `health_check` tool from the `linuxfabrik-icinga` MCP server.

What happens, in order:

1. **The LLM reads its context.** The tool list from step 3 is part of the prompt for this turn. The LLM sees that the `linuxfabrik-icinga` server exposes a `health_check` tool whose description starts with "Report server status and which backends are configured." That matches the user's request directly.

2. **The LLM emits a structured tool call.** Internally this is the same function-calling mechanism it uses for any tool. The Claude Code client receives a request to call `health_check` on the `linuxfabrik-icinga` server with no arguments, and forwards the JSON-RPC over stdio:

    ```json
    // Client -> server
    {
      "jsonrpc": "2.0",
      "id": 7,
      "method": "tools/call",
      "params": {
        "name": "health_check",
        "arguments": {}
      }
    }
    ```

3. **The server runs the function.** FastMCP looks up `health_check`, validates the (empty) arguments against the input schema, calls the Python function, captures its return value, and wraps it in an MCP tool-result message:

    ```json
    // Server -> client
    {
      "jsonrpc": "2.0",
      "id": 7,
      "result": {
        "content": [
          {
            "type": "text",
            "text": "{\"name\": \"Linuxfabrik Icinga\", \"version\": \"0.0.0\", \"config_path\": \"/home/markusfrei/.config/Linuxfabrik/mcp-server-icinga/config.yaml\", \"instances\": {}, \"monitoring_plugins_catalog\": {\"source\": \"live\", \"built_at\": \"2026-04-22T08:00:00+00:00\", \"monitoring_plugins_ref\": null, \"plugin_count\": 251}}"
          }
        ],
        "isError": false
      }
    }
    ```

    The dict the function returned was JSON-serialised and packed as a single text content block. Tools can also return image blocks, resource references or multiple blocks; for our use case plain JSON is enough.

4. **The LLM reads the result.** The tool result is appended to the conversation as a hidden message. The LLM then composes a human-readable answer:

    > Health-Check erfolgreich. Der Server `Linuxfabrik Icinga v0.0.0` laeuft und laedt die Konfig aus `/home/markusfrei/.config/Linuxfabrik/mcp-server-icinga/config.yaml`. Aktuell ist keine Icinga-Instanz konfiguriert. Der Plugin-Katalog laedt live, kennt 251 Plugins.


## Why this design matters when you write tools

Two practical consequences that are not obvious from the steps above:

- **Errors propagate.** Raising an exception inside the function turns into `isError: true` on the tool result; the LLM sees the message and can tell the user about it. We use this to signal "unknown plugin" in `explain_plugin` rather than returning a sentinel value, because a clean error message is more useful to the LLM than an empty result it has to interpret.
- **Restart the MCP client to refresh.** Tool descriptions are cached for the life of the spawned server process. After editing a docstring or adding a tool, the next `tools/list` only happens when the client respawns the server, which usually means restarting Claude Desktop or running the equivalent `claude mcp` reload command. There is no hot reload.


## Want to see it for real?

Run the MCP server with stderr captured, and watch the JSON-RPC traffic in the Claude Code or Claude Desktop logs. On Linux Claude Desktop logs land in `~/.config/Claude/logs/`. Each MCP server has its own log file with a `[server-name]` prefix. The full request/response pairs appear there in real time.

For a richer trace, use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector), a small developer tool that speaks MCP and prints every message. Point it at `mcp-server-icinga` and you can call any tool by hand and see the exact wire payloads, which is the fastest way to debug a docstring or a parameter schema before exposing it to the LLM.
