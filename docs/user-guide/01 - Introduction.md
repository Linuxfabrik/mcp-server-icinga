# Introduction

`mcp-server-icinga` is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that lets AI clients work with Icinga installations through natural language. It targets Linux System Engineers who run Icinga in production and want a chat-driven interface for daily triage, incident investigation and routine operations on top of the existing Icinga REST APIs.


## What kind of "server" is this?

The word "server" misleads when you come from the sysadmin side, where a server is usually a daemon that listens on a port. `mcp-server-icinga` is neither. It is a short-lived Python process that the MCP client spawns and talks to over `stdin`/`stdout`.

Concretely:

- **There is no systemd unit, no `mcp-server-icinga start`, no port listening on your network.** You will not find it with `ss --listening`, you do not open a firewall rule for it, you do not add it to a load balancer.
- **The MCP client (Claude Desktop, Claude Code, MCPO, ...) spawns the process on demand.** It launches `mcp-server-icinga` as a subprocess when it starts, and kills it when it exits. Each client window typically gets its own process.
- **Transport is JSON-RPC over `stdin`/`stdout`.** All communication between the client and the server happens through pipes; no socket is opened. The server itself reaches out to Icinga's REST APIs over HTTPS, but that traffic leaves the machine where you ran the client and your MCP-server credentials live, not the other way around.
- **Installation lives next to the client, not next to Icinga.** Put the package on your laptop next to Claude Desktop, or on the host where Claude Code runs. The Icinga server keeps running where it always did; the MCP server only needs network access to its REST APIs.
- **Restarting means restarting the MCP client.** The server is a child process of the client. Edits to the configuration or a freshly installed version of the package take effect after the next client restart.

There is an alternative MCP transport mode, "streamable-http", that runs as a real HTTP daemon and serves multiple clients at once. We deliberately do not use it: stdio matches the way Claude Desktop and Claude Code natively spawn servers, keeps deployment trivial (`pip install`, no service to manage), avoids exposing another network surface, and keeps the Icinga credentials on the operator's machine instead of concentrating them in a hosted service. The reasoning is recorded in [Design Decisions](../developer-guide/02 - Design Decisions.md).


## What it bridges

Five sources of knowledge, each behind its own module so that you only configure what you actually run:

- **Icinga 2 Core REST API** (port 5665): live host and service objects, on-demand checks, acknowledgements, downtimes.
- **Icinga Web 2 / Icinga DB Web module**: richer state projections, history, comments, notifications, with the limitations of the Icinga Web surface.
- **Icinga Director API**: object browsing, service template introspection, command catalog.
- **Linuxfabrik [monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins) catalog**: implementation, inputs, outputs, states and perfdata of every check plugin, so the server can explain why a service is alerting, not just that it is.
- **Time series database** (default: InfluxDB, modular): historical perfdata for trending, flapping analysis and root-cause investigation.


## What you can ask

The server is built for natural-language investigation of a real Icinga fleet. Its flagship use case is root-cause analysis - explaining *why* something alerts, not just *that* it does, by combining live state, the plugin catalog and historical perfdata:

> Why is `web01` slow around noon on weekdays?

> `ntp-offset` on `bastion` has been WARN for three days. Real drift, or a plugin bug?

Triage ("what is currently red?"), operations (acknowledge, downtime, reschedule) and plugin-catalog questions are the building blocks that get there. What actually works depends on which backends you configured and which tools have landed; see [Example Prompts](06 - Example Prompts.md) for the current set, grouped by what each one needs.


## Status

This project is in early development; architecture, configuration and tool surface are unstable and will change. The current build ships the configuration layer, the monitoring-plugins catalog tools, and read-only plus write tools for the Icinga 2 Core REST API. Icinga Web, Icinga Director and the time series database backends are not implemented yet.


## Audience

Linux System Engineers who:

- Already run Icinga in production
- Already have an MCP-capable client installed (Claude Desktop, Claude Code, MCPO, ...)
- Want to triage and operate their monitoring from a chat interface without writing API requests by hand


## How Claude finds the tools

When the MCP client starts, it spawns the server and asks it for its tool list (name, docstring description, argument schema). That list is injected into the conversation, so when you ask a question the LLM matches your wording against the tool descriptions and calls the most relevant one. Two consequences are worth knowing while you write configuration or read tool output:

- **Tool descriptions are the single source of intent matching.** A vague docstring gets a tool invoked at the wrong moment, or not at all. Docstrings are written for the LLM and treated as API surface.
- **The server, not Claude, controls what is possible.** Tools are only registered for backends present in the configuration. Without `icinga2_core.write_password` the write tools are never exposed, so Claude cannot acknowledge or schedule a downtime even if you ask it to - the principle of least privilege, applied to the MCP surface.

For the full mechanism with the real JSON-RPC payloads, see [How Tool Discovery Works](05 - How Tool Discovery Works.md).


## Where to go next

- [Installation](02 - Installation.md): get the server onto your machine
- [Configuration](03 - Configuration.md): wire it to your Icinga REST APIs
- [Quickstart with Claude](04 - Quickstart with Claude.md): connect it to Claude and try the first prompt
