# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

* Add configuration layer: YAML file with one section per backend (Icinga 2 Core, Icinga Web, Icinga Director, time series database, monitoring-plugins catalog), secrets referenced via the `!env VAR_NAME` tag and resolved from environment variables at load time. Lookup order: `$ICINGA_MCP_CONFIG`, then `$XDG_CONFIG_HOME/mcp-server-icinga/config.yaml`, then `/etc/mcp-server-icinga/config.yaml`. Annotated example shipped at `examples/config.example.yaml`.
* Add MCP stdio server skeleton built on the `mcp` Python SDK (`FastMCP`), registered as the `mcp-server-icinga` console script and runnable via `python -m mcp_server_icinga`. Ships one tool, `health_check`, that confirms the server is up and reports which backends are configured.
* Add User Guide under `docs/user-guide/` covering Introduction, Installation, Configuration, and Quickstart with Claude (Desktop and Code).
* Add MkDocs-based documentation site at <https://linuxfabrik.github.io/mcp-server-icinga/>, served via GitHub Pages and rebuilt on every merge to `main`.
* Initial project skeleton with `pyproject.toml`, `README.md`, `CHANGELOG.md`, `LICENSE` (Unlicense), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` and `SECURITY.md`.
