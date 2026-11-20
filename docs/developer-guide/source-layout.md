# Source Layout

All runtime code lives under `src/mcp_server_icinga/` ([src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/), so the installed package is what gets tested, not the working copy). This page walks every file in that tree in order of importance and usage rather than alphabetically: start at the server that ties everything together, then the configuration it reads at startup, then the backend packages it talks to, and finally the small glue files.

```text
src/mcp_server_icinga/
├── server.py             # MCP entrypoint and tool registration
├── config.py             # configuration models and YAML loading
├── icinga2_core/         # Icinga 2 Core REST backend
│   ├── client.py
│   └── __init__.py
├── plugin_catalog/       # Linuxfabrik monitoring-plugins catalog
│   ├── loader.py
│   ├── parser.py
│   ├── schema.py
│   └── __init__.py
├── __init__.py           # package version and public API
└── __main__.py           # `python -m mcp_server_icinga` shim
```


## `server.py`

The heart of the project and the right place to start reading. It owns:

- `main()`: the process entrypoint behind both the `mcp-server-icinga` console script and `python -m mcp_server_icinga`. It locates and loads the configuration, optionally loads the monitoring-plugins catalog, builds the server and runs the stdio event loop.
- `build_server()`: wires an `MCPServer` instance and registers tools conditionally. A tool is only exposed when its backend is present in the loaded configuration. An instance without `icinga2_core` gets no host or service tools, and a deployment without a catalog path gets no catalog tools. This registration step is a real least-privilege boundary, not cosmetic: a tool that is never registered cannot be called.
- The tool functions themselves. Their docstrings are the LLM-facing API surface, so they are written for the model, not just for a human reader.
- The pure payload helpers (`_health_check_payload`, `_list_hosts_payload`, `_get_problems_payload`, ...). These do the actual work and contain no MCP machinery, so they are unit-tested directly without spinning up a server or touching the network. The decorated tool functions stay thin wrappers around them.


## `config.py`

Defines the shape of the configuration and loads it. Everything downstream keys off the models here, and `main()` loads them once at startup before anything else happens.

- Pydantic models describe the whole configuration tree: `Config` at the top, a map of `instances.<name>` to `InstanceConfig`, each holding the optional per-backend sections (`Icinga2CoreConfig`, `IcingaWebConfig`, `IcingaDirectorConfig`, `InfluxDBConfig`), plus the global `MonitoringPluginsConfig`. Every model uses `extra='forbid'`, so a typo in a key is rejected with a clear error instead of being silently ignored.
- A `SafeLoader` subclass adds the `!env VAR_NAME` and `!file /path` YAML tags that resolve secrets at load time, keeping passwords and tokens out of the YAML file itself.
- `find_config_path()` implements the lookup order (`$ICINGA_MCP_CONFIG`, then the XDG user path, then `/etc`), and `load_config()` parses, resolves secrets and validates in one call.


## `icinga2_core/`

The Icinga 2 Core REST API backend (port 5665). This is the package that turns "what is broken right now" questions into live API calls.

### `icinga2_core/client.py`

A synchronous client around the object-query endpoints (`/v1/objects/hosts`, `/v1/objects/services`).

- It issues a `POST` with the `X-HTTP-Method-Override: GET` header and passes filters in the request body via `filter` plus `filter_vars`. Parameter binding through `filter_vars` keeps caller-supplied values out of the filter string, so there is no Icinga DSL escaping to get wrong.
- The state-code mappings (host `UP`/`DOWN`, service `OK`/`WARNING`/`CRITICAL`/`UNKNOWN`) are verified against the Icinga 2 source and used by the `summarize_host` / `summarize_service` helpers, which collapse a verbose object-query result into a compact, token-efficient dict for the model.
- A small error hierarchy (`Icinga2CoreError` and friends) maps HTTP and network failures to actionable messages. The constructor accepts an injectable transport, which is the seam the tests use to drive the client against canned responses with no real Icinga.

### `icinga2_core/__init__.py`

Re-exports the client, its errors, the state-code maps and the summarisers so the rest of the codebase imports from the package, not from individual modules.


## `plugin_catalog/`

A static, queryable description of every plugin in the Linuxfabrik `monitoring-plugins` repository: argparse arguments, perfdata metrics, state rules, Icinga Director command mapping and metadata. It is what lets the server explain why a service alerts, not just that it does.

### `plugin_catalog/loader.py`

The public entry point (`load_from_path`). It walks a `check-plugins/` directory, parses each plugin and assembles a `Catalog`. Plugins that fail to parse are skipped with a warning so one broken plugin does not take down the whole catalog.

### `plugin_catalog/parser.py`

Parses a single plugin. Deliberately static: it works on `ast` trees and regex extraction of README sections, never importing plugin source or doing runtime introspection. That keeps the loader free of any plugin-specific runtime dependency.

### `plugin_catalog/schema.py`

The Pydantic models the parser fills and the loader returns: `Catalog`, `PluginCatalogEntry`, `PluginArg`, `PluginPerfdata` and `PluginStateRule`. Reading these first is the quickest way to understand what knowledge the catalog actually holds.

### `plugin_catalog/__init__.py`

Re-exports the schema models and `load_from_path`, and documents the two catalog sources (a live directory walk, and a bundled JSON snapshot regenerated per release).


## `__init__.py`

The package root. Holds `__version__` (the single source of truth that `pyproject.toml` reads at build time) and re-exports the configuration public API so callers can import it straight from `mcp_server_icinga`.


## `__main__.py`

A three-line shim that makes `python -m mcp_server_icinga` an alternative to the console script by delegating to `server.main()`.
