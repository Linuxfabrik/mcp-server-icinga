<h1 align="center">
  Linuxfabrik MCP Server for Icinga
</h1>
<p align="center">
  Model Context Protocol (MCP) server for Icinga. Lets AI clients such as Claude triage, investigate and operate Icinga installations through the Icinga 2 Core, Icinga Web and Icinga Director REST APIs, with deep awareness of the Linuxfabrik monitoring-plugins catalog and historical perfdata from a time series database.
  <span>&#8226;</span>
  <b>made by <a href="https://linuxfabrik.ch/">Linuxfabrik</a></b>
</p>
<div align="center">

![License](https://img.shields.io/github/license/linuxfabrik/mcp-server-icinga)
![Python](https://img.shields.io/badge/Python-3.14+-3776ab)
![Status](https://img.shields.io/badge/Status-early%20development-orange)
![GitHub Issues](https://img.shields.io/github/issues/linuxfabrik/mcp-server-icinga)
[![GitHubSponsors](https://img.shields.io/github/sponsors/Linuxfabrik?label=GitHub%20Sponsors)](https://github.com/sponsors/Linuxfabrik)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-ff6600)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=7AW3VVX62TR4A&source=url)

</div>

<br />

# MCP Server for Icinga

`mcp-server-icinga` is a Model Context Protocol (MCP) server that lets AI clients such as Claude work with Icinga installations through natural language. It targets Linux System Engineers who run Icinga in production and want a chat-driven interface for daily triage, incident investigation and routine operations on top of the existing Icinga REST APIs.

This project was developed with the assistance of Claude Code by Anthropic.


## Scope

The server bridges three Icinga surfaces and the Linuxfabrik monitoring stack:

- **Icinga 2 Core REST API** (port 5665): live host and service objects, on-demand checks, acknowledgements, downtimes.
- **Icinga Web 2 / Icinga DB Web module**: richer state projections, history, comments, notifications, with the limitations of the Icinga Web surface.
- **Icinga Director API**: object browsing, service template introspection, command catalog.
- **Linuxfabrik [monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins) catalog**: implementation, inputs, outputs, states and perfdata of every check plugin, so the server can explain why a service is alerting, not just that it is.
- **Time series database** (default: InfluxDB, modular): historical perfdata for trending, flapping analysis and root-cause investigation.

Each backend lives in its own module so that operators can wire up only what they actually run. The server transparently flags information that the underlying API does not expose, instead of guessing.


## Status

Early development. Architecture, configuration and tool surface are unstable and will change.


## Requirements

- Python 3.14 or newer.
- Reachable Icinga installation (one or more of: Icinga 2 Core API, Icinga Web 2 with the Icinga DB Web module, Icinga Director).
- Optional: a time series database backend for historical perfdata. Default integration is InfluxDB; the TSDB layer is modular so other backends can be plugged in.


## Installation

Installation instructions will be documented once the first release is cut.


## Configuration

Configuration documentation will follow as soon as the configuration surface stabilises.


## Related Projects

- [Linuxfabrik monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins): the check plugin catalog this server understands.
- [Linuxfabrik lib](https://github.com/Linuxfabrik/lib): shared Python helpers.
- [Icinga/icinga-mcp](https://github.com/Icinga/icinga-mcp): upstream proof-of-concept MCP server by the Icinga team. Different scope, different architecture.


## License

Released into the public domain under the [Unlicense](LICENSE).
