<h1 align="center">
  Linuxfabrik MCP Server for Icinga
</h1>
<p align="center">
  Model Context Protocol (MCP) server for Icinga. Lets AI clients such as Claude triage, investigate and operate Icinga installations through the Icinga 2 Core, Icinga Web and Icinga Director REST APIs, with deep awareness of the Linuxfabrik monitoring-plugins catalog and historical perfdata from a time series database.
  <span>&#8226;</span>
  <b>made by <a href="https://linuxfabrik.ch/">Linuxfabrik</a></b>
</p>
<div align="center" markdown>

![GitHub Stars](https://img.shields.io/github/stars/linuxfabrik/mcp-server-icinga)
[![Star History Chart](https://api.star-history.com/svg?repos=Linuxfabrik/mcp-server-icinga&type=Date)](https://star-history.com/#Linuxfabrik/mcp-server-icinga&Date)
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

> If this MCP server helps you operating your Icinga installation through your AI assistant, please give it a star.

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

The server runs anywhere Python 3.14 runs. It does not need to live on the Icinga master, but it does need network access to the Icinga REST APIs you point it at, and an MCP-capable client (tested with [Claude Desktop](https://claude.ai/download) and [Claude Code](https://docs.claude.com/en/docs/claude-code)).

Until the first PyPI release, install directly from GitHub:

```bash
pip install --user git+https://github.com/Linuxfabrik/mcp-server-icinga.git
```

For local development, install in editable mode inside a virtual environment:

```bash
git clone https://github.com/Linuxfabrik/mcp-server-icinga.git
cd mcp-server-icinga
python3.14 -m venv .venv
source .venv/bin/activate
pip install --editable '.'
```

The package exposes both a console script and a runnable module:

```bash
mcp-server-icinga              # started by the MCP client over stdio
python -m mcp_server_icinga    # equivalent
```

Without a configuration file the server exits with a clear error pointing at the lookup order. See the [Installation guide](https://linuxfabrik.github.io/mcp-server-icinga/user-guide/02%20-%20Installation/) for the full walkthrough.


## Configuration

The server is configured through a single YAML file. It describes one or more Icinga deployments ("instances") plus the global Linuxfabrik monitoring-plugins catalog. Secrets do not live in the YAML; they are resolved at load time from environment variables (`!env`) or files on disk (`!file`).

The configuration file is looked up in this order, first match wins:

1. The path in the `ICINGA_MCP_CONFIG` environment variable.
2. `$XDG_CONFIG_HOME/mcp-server-icinga/config.yaml` (default: `~/.config/mcp-server-icinga/config.yaml`).
3. `/etc/mcp-server-icinga/config.yaml`.

A minimal read-only setup with a single instance:

```yaml
instances:
  prod:
    icinga2_core:
      url: 'https://icinga2.example.com:5665'
      username: 'mcp-readonly'
      password: !env ICINGA2_PROD_PASSWORD
```

The instance name (`prod` above) is the identifier you reference in chat ("what is currently red on `prod`?"). Each instance carries up to four independently optional backends (`icinga2_core`, `icinga_web`, `icinga_director`, `tsdb`); a tool whose backend is absent on the targeted instance is simply not registered. An annotated example with every backend ships at [`examples/config.example.yaml`](examples/config.example.yaml).

For the field reference, secret handling and wiring the server into Claude Desktop or Claude Code, see the [Configuration guide](https://linuxfabrik.github.io/mcp-server-icinga/user-guide/03%20-%20Configuration/) and the [Quickstart](https://linuxfabrik.github.io/mcp-server-icinga/user-guide/04%20-%20Quickstart%20with%20Claude/).


## Related Projects

- [Linuxfabrik monitoring-plugins](https://github.com/Linuxfabrik/monitoring-plugins): the check plugin catalog this server understands.
- [Linuxfabrik lib](https://github.com/Linuxfabrik/lib): shared Python helpers.
- [Icinga/icinga-mcp](https://github.com/Icinga/icinga-mcp): upstream proof-of-concept MCP server by the Icinga team. Different scope, different architecture.


## License

Released into the public domain under the [Unlicense](LICENSE).
