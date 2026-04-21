# Introduction

`mcp-server-icinga` is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that lets AI clients work with Icinga installations through natural language. It targets Linux System Engineers who run Icinga in production and want a chat-driven interface for daily triage, incident investigation and routine operations on top of the existing Icinga REST APIs.


## What it bridges

Five sources of knowledge, each behind its own module so that you only configure what you actually run:

- **Icinga 2 Core REST API** (port 5665): live host and service objects, on-demand checks, acknowledgements, downtimes.
- **Icinga Web 2 / Icinga DB Web module**: richer state projections, history, comments, notifications, with the limitations of the Icinga Web surface.
- **Icinga Director API**: object browsing, service template introspection, command catalog.
- **Linuxfabrik [monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins) catalog**: implementation, inputs, outputs, states and perfdata of every check plugin, so the server can explain why a service is alerting, not just that it is.
- **Time series database** (default: InfluxDB, modular): historical perfdata for trending, flapping analysis and root-cause investigation.


## Example prompts

Once the full tool surface lands, these are the kinds of questions the server is built to answer. Today only the smoke-test prompts under "Available now" actually work; the rest sit on the roadmap and inform every implementation decision. The list is here so you know what you are aiming at when you wire the server up.

### Flagship: root-cause analysis ("why?")

The headline use case for this project. Every other capability exists to serve these. They need live state, historical perfdata from the time series database and the full plugin catalog knowledge to be answered well, which is exactly what the server is built to combine:

> Why is `web01` slow around noon on weekdays?

> Why does `app99` have high load so often?

> Why do the backups on `backup01` sometimes take four hours and sometimes forty minutes?

> Is there a correlation between the memory usage on `db-prod-01` and the query latency we see on `app01`?

> `ntp-offset` on `bastion` has been WARN for three days with the same message and nobody is reacting. Is it a real, persistent drift, or a bug in the plugin?

> I just changed `lib/disk.py` in monitoring-plugins. Which services have been WARN since my push and could be related?

### Triage

Answers that need live Icinga state, optionally combined with the plugin catalog:

> What is currently red?

> Show me all unhandled criticals on hosts in the `database` service group.

> The mail server allegedly hangs - what do `mailq`, `load` and `procs` report on `mail01`?

> Service X on host Y was briefly down yesterday around 22:30 - what happened?

> Which services have flapped most often in the last seven days?

> Why is `disk-usage` alerting on `db-prod-01` right now? Use the live plugin output and the plugin source to explain it.

### Operations

Write-through actions against Icinga, only available when the MCP server is configured with write credentials:

> Acknowledge all unhandled criticals on `db-prod-01` for 24 hours with the comment "investigating".

> Schedule a downtime tomorrow 02:00-04:00 UTC on all hosts with `servicegroup=database` and a comment referencing the maintenance window.

> Reschedule the `deb-updates` check on every host in the `frontend` host group right now.

### Available now

These prompts work against the current build.

**Server status:**

> Run the `health_check` tool from the `icinga` MCP server.

> Which Icinga backends does the icinga MCP server know about?

**Plugin catalog** (requires `monitoring_plugins.catalog_path` configured, see [Configuration](03 - Configuration.md)):

> Use `catalog_info` to tell me where the plugin knowledge comes from.

> List all Linuxfabrik monitoring plugins whose names contain `-version`.

> List all plugins that run on Windows.

> Explain the `gitlab-version` plugin. What does it check, what arguments does it take, what states can it return?

> What plugin is behind the Icinga check command `cmd-check-disk-usage`?

> I have a service in Icinga that uses `cmd-check-mailq`. What perfdata does it emit and what states can it go into?

> Which plugins use the `--always-ok` flag? Sample five and show their descriptions.

The shape of the root-cause prompts above is what the project is ultimately designed for: natural-language investigation against a real Icinga fleet, with the server bridging Claude's reasoning to the existing Icinga REST APIs, the Linuxfabrik plugin catalog and historical perfdata in a time series database. Triage and operations are the building blocks that get us there.


## Status

This project is in early development. Architecture, configuration and tool surface are unstable and will change. The current build ships only the configuration layer and a `health_check` tool that confirms the server is up and reports which backends it knows about.


## Audience

Linux System Engineers who:

- Already run Icinga in production
- Already have an MCP-capable client installed (Claude Desktop, Claude Code, MCPO, ...)
- Want to triage and operate their monitoring from a chat interface without writing API requests by hand


## How Claude finds the tools

It looks like magic in the chat window, but the wiring is straightforward. When the MCP client (Claude Desktop, Claude Code, ...) starts up, it reads its `mcpServers` configuration and spawns each entry as a subprocess. Communication between the client and the server happens over stdin/stdout using the [Model Context Protocol](https://modelcontextprotocol.io). Four steps:

1. **Spawn.** The client launches `mcp-server-icinga` and injects the configured environment variables. The server reads its YAML config, validates it, and goes into the MCP message loop.

2. **Handshake.** Right after the spawn the client asks the server `tools/list`. The server replies with every tool it has registered: name, human-readable description (the function's docstring), and a JSON Schema for the arguments. This list is then injected into every conversation turn so the LLM knows what is available.

3. **Intent matching.** When you ask "what is the status of the icinga server?", the LLM matches your wording against the available tool descriptions, picks the most relevant one (`health_check`) and emits a structured tool call with the right arguments.

4. **Call and response.** The client forwards the call to the server, the server runs the corresponding Python function, returns a result, the LLM gets that result back and turns it into a natural-language answer.

Two consequences fall out of this design and are worth knowing while you write configuration or read tool output:

- **Tool descriptions are the single source of intent matching.** A tool with a vague docstring will be invoked at the wrong moments, or not at all. We document tools assuming the LLM is the only reader.
- **The server, not Claude, controls what is possible.** Tools are only registered for backends that exist in the configuration. A configuration without `icinga2_core.write_password` simply does not expose write tools, so Claude cannot accidentally acknowledge or schedule a downtime even if you ask it to. This is the principle of least privilege, applied to the MCP surface.


## Where to go next

- [Installation](02 - Installation.md): get the server onto your machine
- [Configuration](03 - Configuration.md): wire it to your Icinga REST APIs
- [Quickstart with Claude](04 - Quickstart with Claude.md): connect it to Claude and try the first prompt
