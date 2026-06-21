# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Breaking Changes

* Configuration schema now groups all per-deployment backends under `instances.<name>`. The previous flat layout (`icinga2_core:` directly at the top level) is rejected with a clear error. Migration: wrap your existing flat configuration in `instances:` with a name of your choice (e.g. `instances.default:`). Allowed because there are no PyPI releases yet and the tool surface that depends on the old shape is not in production use.
* `health_check` payload changed shape: the previous `backends` and `icinga2_core_write_enabled` keys are replaced by a per-instance map under the new `instances` key, where each value carries the same flags. `monitoring_plugins_catalog` is now always a dict instead of sometimes being a string.


### Added

* Add configuration layer: YAML file with one section per backend (Icinga 2 Core, Icinga Web, Icinga Director, time series database, monitoring-plugins catalog), secrets referenced via the `!env VAR_NAME` tag and resolved from environment variables at load time. Lookup order: `$ICINGA_MCP_CONFIG`, then `$XDG_CONFIG_HOME/Linuxfabrik/mcp-server-icinga/config.yaml`, then `/etc/Linuxfabrik/mcp-server-icinga/config.yaml`. Annotated example shipped at `examples/config.example.yaml`.
* Add Icinga 2 Core read-only tools for any instance that has an `icinga2_core` backend configured: list and inspect hosts and services with their current state, output and perfdata, filter by state or name, look up a single host or service, and get a one-call problem overview of everything that is not `OK`/`UP` for triage. Each service carries its `check_command`, which bridges into the monitoring-plugins catalog to explain what a failing service actually checks.
* Add Icinga 2 Core write actions, registered only for instances that carry separate write credentials: acknowledge a host or service problem, schedule and remove downtimes, and trigger an immediate recheck. Actions are attributed to the configured write user, so read-only deployments stay strictly read-only.
* Add Linuxfabrik monitoring-plugins catalog: AST-based parser for every plugin's source file (extracts `__version__`, `DESCRIPTION`, every argparse argument with default and help text), regex-based parser for the README sections (`Fact Sheet`, `States`, `Perfdata / Metrics`), and JSON parser for the Icinga Director basket (`cmd-check-*` command names plus the `<plugin>_*` variable prefix). When the configuration sets `monitoring_plugins.catalog_path`, the server registers four catalog tools: `catalog_info`, `list_plugins(runs_on?, name_contains?)`, `explain_plugin(name)`, and `find_plugin_for_check_command(check_command)`. The bridge from "service X has check_command cmd-check-Y" to "Y is a plugin that does Z" is the foundation for the project's flagship root-cause-analysis tools that follow in later phases.
* Add User Guide chapter "How Tool Discovery Works" that walks through what happens between writing a Python function in `server.py` and Claude calling that function from a chat prompt. Shows the actual JSON-Schema each tool produces (captured live from the running server), the `tools/list` and `tools/call` JSON-RPC payloads on the wire, and the consequences for tool authors (docstrings as the LLM-facing API surface, type hints as the schema, errors as `isError`, server-side registration as a real least-privilege boundary).
* Add multi-instance support: the configuration schema now wraps backend sections under `instances.<name>` so a single MCP server can talk to several Icinga deployments (tenants, sites, environments). Instance names are arbitrary identifiers chosen by the operator (`prod-zh`, `staging`, `customer-acme`). Future Icinga-facing tools take an `instance` parameter. The `monitoring_plugins` catalog stays global because the same Linuxfabrik plugins apply across every Icinga deployment.
* Add `!file /path/to/secret-file` YAML tag for sourcing secrets from disk instead of the environment. Trailing newlines are stripped, so files written by systemd `LoadCredential=`, Docker / Podman secrets, or `echo "secret" > file` work without surprises. Combined with `!env`, operators can mix per-instance credential delivery according to what their environment already provides.
* Add MCP stdio server skeleton built on the `mcp` Python SDK (`FastMCP`), registered as the `mcp-server-icinga` console script and runnable via `python -m mcp_server_icinga`. Ships one tool, `health_check`, that confirms the server is up and reports which backends are configured.
* Add User Guide under `docs/user-guide/` covering Introduction, Installation, Configuration, and Quickstart with Claude (Desktop and Code).
* Add MkDocs-based documentation site at <https://linuxfabrik.github.io/mcp-server-icinga/>, served via GitHub Pages and rebuilt on every merge to `main`.
* Initial project skeleton with `pyproject.toml`, `README.md`, `CHANGELOG.md`, `LICENSE` (Unlicense), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` and `SECURITY.md`.
