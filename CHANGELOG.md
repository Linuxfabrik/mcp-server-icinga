# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

**Highlights:** First working shape of the server: read-only Icinga 2 Core tools for hosts, services and a one-call problem overview, optional write actions for acknowledgements, downtimes and rechecks, and a parser for the Linuxfabrik monitoring-plugins catalog that turns "service X runs check_command Y" into "Y checks Z". One server can serve several Icinga deployments through `instances.<name>`. Nothing is released to PyPI yet, so the configuration schema is still moving.

### Changed

* The configuration schema groups all per-deployment backends under `instances.<name>`; the previous flat layout with `icinga2_core:` at the top level is rejected with a clear error. Wrap an existing flat configuration in `instances:` with a name of your choice, for example `instances.default:`.
* The `health_check` payload replaces the `backends` and `icinga2_core_write_enabled` keys with a per-instance map under `instances`, where each value carries the same flags, and `monitoring_plugins_catalog` is always a dict instead of sometimes being a string.
* The server needs version 2 of the `mcp` Python SDK. A fresh installation picks it up on its own; an existing virtual environment still holding version 1 has to be upgraded, otherwise the server fails to start.

### Added

* Add configuration layer: YAML file with one section per backend (Icinga 2 Core, Icinga Web, Icinga Director, time series database, monitoring-plugins catalog), secrets referenced via the `!env VAR_NAME` tag and resolved from environment variables at load time. Lookup order: `$ICINGA_MCP_CONFIG`, then `$XDG_CONFIG_HOME/Linuxfabrik/mcp-server-icinga/config.yaml`, then `/etc/Linuxfabrik/mcp-server-icinga/config.yaml`. Annotated example shipped at `examples/config.example.yaml`.
* Add Icinga 2 Core read-only tools for any instance that has an `icinga2_core` backend configured: list and inspect hosts and services with their current state, output and perfdata, filter by state or name, look up a single host or service, and get a one-call problem overview of everything that is not `OK`/`UP` for triage. Each service carries its `check_command`, which bridges into the monitoring-plugins catalog to explain what a failing service actually checks.
* Add Icinga 2 Core write actions, registered only for instances that carry separate write credentials: acknowledge a host or service problem, schedule and remove downtimes, and trigger an immediate recheck. Actions are attributed to the configured write user, so read-only deployments stay strictly read-only.
* Add the Linuxfabrik monitoring-plugins catalog, which parses each plugin's source, README and Icinga Director basket, and registers five tools when `monitoring_plugins.catalog_path` is set: `catalog_info`, `list_plugins`, `explain_plugin`, `find_plugin_for_check_command` and `read_plugin_source`, the last returning a plugin's actual Python source so the assistant can explain the real check logic rather than only the extracted metadata.
* Add User Guide chapter "How Tool Discovery Works", which walks through what happens between writing a Python function in `server.py` and Claude calling it from a chat prompt, showing the JSON-Schema each tool produces and the `tools/list` and `tools/call` payloads on the wire.
* Add multi-instance support, so a single MCP server can talk to several Icinga deployments (tenants, sites, environments) under operator-chosen names such as `prod-zh` or `customer-acme`, with Icinga-facing tools taking an `instance` parameter. The `monitoring_plugins` catalog stays global, since the same plugins apply across every deployment.
* Add the `!file /path/to/secret-file` YAML tag for sourcing secrets from disk instead of the environment, stripping trailing newlines so files written by systemd `LoadCredential=`, Docker and Podman secrets or a plain `echo` work without surprises.
* Add MCP stdio server skeleton built on the `mcp` Python SDK, registered as the `mcp-server-icinga` console script and runnable via `python -m mcp_server_icinga`. Ships one tool, `health_check`, that confirms the server is up and reports which backends are configured.
* Add User Guide under `docs/user-guide/` covering Introduction, Installation, Configuration, and Quickstart with Claude (Desktop and Code).
* Add MkDocs-based documentation site at <https://linuxfabrik.github.io/mcp-server-icinga/>, served via GitHub Pages and rebuilt on every merge to `main`.
* Initial project skeleton with `pyproject.toml`, `README.md`, `CHANGELOG.md`, `LICENSE` (Unlicense), `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md` and `SECURITY.md`.


### Security

* The workflows that build the documentation and the PyPI package install their tools from hash-pinned requirements files, so a compromised or resurrected package version cannot slip into a release.
