# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

* Add configuration layer: YAML file with one section per backend (Icinga 2 Core, Icinga Web, Icinga Director, time series database, monitoring-plugins catalog), secrets referenced via the `!env VAR_NAME` tag and resolved from environment variables at load time. Lookup order: `$ICINGA_MCP_CONFIG`, then `$XDG_CONFIG_HOME/mcp-server-icinga/config.yaml`, then `/etc/mcp-server-icinga/config.yaml`. Annotated example shipped at `examples/config.example.yaml`.
* Add Linuxfabrik monitoring-plugins catalog: AST-based parser for every plugin's source file (extracts `__version__`, `DESCRIPTION`, every argparse argument with default and help text), regex-based parser for the README sections (`Fact Sheet`, `States`, `Perfdata / Metrics`), and JSON parser for the Icinga Director basket (`cmd-check-*` command names plus the `<plugin>_*` variable prefix). When the configuration sets `monitoring_plugins.catalog_path`, the server registers four catalog tools: `catalog_info`, `list_plugins(runs_on?, name_contains?)`, `explain_plugin(name)`, and `find_plugin_for_check_command(check_command)`. The bridge from "service X has check_command cmd-check-Y" to "Y is a plugin that does Z" is the foundation for the project's flagship root-cause-analysis tools that follow in later phases.
* Add MCP stdio server skeleton built on the `mcp` Python SDK (`FastMCP`), registered as the `mcp-server-icinga` console script and runnable via `python -m mcp_server_icinga`. Ships one tool, `health_check`, that confirms the server is up and reports which backends are configured.
* Add User Guide under `docs/user-guide/` covering Introduction, Installation, Configuration, and Quickstart with Claude (Desktop and Code).
* Add MkDocs-based documentation site at <https://linuxfabrik.github.io/mcp-server-icinga/>, served via GitHub Pages and rebuilt on every merge to `main`.
* Initial project skeleton with `pyproject.toml`, `README.md`, `CHANGELOG.md`, `LICENSE` (Unlicense), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` and `SECURITY.md`.
