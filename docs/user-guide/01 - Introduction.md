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

Only smoke-test prompts work at this stage of the project:

> Run the `health_check` tool from the `icinga` MCP server.

> Which Icinga backends does the icinga MCP server know about?

The shape of the root-cause prompts above is what the project is ultimately designed for: natural-language investigation against a real Icinga fleet, with the server bridging Claude's reasoning to the existing Icinga REST APIs, the Linuxfabrik plugin catalog and historical perfdata in a time series database. Triage and operations are the building blocks that get us there.


## Status

This project is in early development. Architecture, configuration and tool surface are unstable and will change. The current build ships only the configuration layer and a `health_check` tool that confirms the server is up and reports which backends it knows about.


## Audience

Linux System Engineers who:

- Already run Icinga in production
- Already have an MCP-capable client installed (Claude Desktop, Claude Code, MCPO, ...)
- Want to triage and operate their monitoring from a chat interface without writing API requests by hand


## Where to go next

- [Installation](02 - Installation.md): get the server onto your machine
- [Configuration](03 - Configuration.md): wire it to your Icinga REST APIs
- [Quickstart with Claude](04 - Quickstart with Claude.md): connect it to Claude and try the first prompt
