# Linuxfabrik MCP Server for Icinga

Model Context Protocol (MCP) server that lets AI clients such as Claude work with Icinga installations through natural language. Targets Linux System Engineers who run Icinga in production and want a chat-driven interface for daily triage, incident investigation and routine operations on top of the existing Icinga REST APIs.

Made by [Linuxfabrik](https://www.linuxfabrik.ch).


## Status

Early development. Architecture, configuration and tool surface are unstable and will change.


## Scope

The server bridges three Icinga surfaces and the Linuxfabrik monitoring stack:

- **Icinga 2 Core REST API** (port 5665): live host and service objects, on-demand checks, acknowledgements, downtimes.
- **Icinga Web 2 / Icinga DB Web module**: richer state projections, history, comments, notifications, with the limitations of the Icinga Web surface.
- **Icinga Director API**: object browsing, service template introspection, command catalog.
- **Linuxfabrik [monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins) catalog**: implementation, inputs, outputs, states and perfdata of every check plugin, so the server can explain why a service is alerting, not just that it is.
- **Time series database** (default: InfluxDB, modular): historical perfdata for trending, flapping analysis and root-cause investigation.

Each backend lives in its own module so that operators can wire up only what they actually run. The server transparently flags information that the underlying API does not expose, instead of guessing.


## Links

- [GitHub Repository](https://github.com/Linuxfabrik/mcp-server-icinga)
- [Issue Tracker](https://github.com/Linuxfabrik/mcp-server-icinga/issues)
- [Discussions](https://github.com/Linuxfabrik/mcp-server-icinga/discussions)
- [Linuxfabrik Website](https://www.linuxfabrik.ch)
