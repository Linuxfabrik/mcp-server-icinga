# SPDX-License-Identifier: Unlicense

"""MCP server entrypoint.

Starts a Model Context Protocol server over stdio, registers the tools
that match the loaded configuration and runs the event loop. The
configuration is loaded once at startup; tools whose backend is not
configured are simply not registered, so a deployment with only the
Icinga 2 Core API works without an Icinga Director or TSDB section.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server_icinga import __version__
from mcp_server_icinga.config import (
    Config,
    ConfigError,
    find_config_path,
    load_config,
)
from mcp_server_icinga.plugin_catalog import Catalog, load_from_path


def _health_check_payload(
    config: Config, config_path: Path, catalog: Catalog | None = None
) -> dict[str, Any]:
    """Compute the payload returned by the `health_check` tool.

    Pure function: no network, no side effects. Lives outside the FastMCP
    decorator wrapper so it can be unit-tested without spinning up the
    server.
    """
    if catalog is not None:
        catalog_status: dict[str, Any] = {
            'source': catalog.source,
            'built_at': catalog.built_at,
            'monitoring_plugins_ref': catalog.monitoring_plugins_ref,
            'plugin_count': len(catalog.plugins),
        }
    elif config.monitoring_plugins.catalog_path:
        catalog_status = {'source': 'configured-but-not-loaded'}
    else:
        catalog_status = {'source': 'bundled-snapshot (not yet implemented)'}

    instances_status: dict[str, dict[str, Any]] = {}
    for name, inst in config.instances.items():
        instances_status[name] = {
            'icinga2_core': inst.icinga2_core is not None,
            'icinga_web': inst.icinga_web is not None,
            'icinga_director': inst.icinga_director is not None,
            'tsdb': inst.tsdb is not None,
            'icinga2_core_write_enabled': (
                inst.icinga2_core is not None
                and inst.icinga2_core.write_password is not None
            ),
        }

    return {
        'name': 'mcp-server-icinga',
        'version': __version__,
        'config_path': str(config_path),
        'instances': instances_status,
        'monitoring_plugins_catalog': catalog_status,
    }


def _plugin_summary(entry: Any) -> dict[str, Any]:
    """Compact summary row for `list_plugins` output."""
    description = entry.description or ''
    if len(description) > 200:
        description = description[:197].rstrip() + '...'
    return {
        'name': entry.name,
        'version': entry.version,
        'runs_on': entry.runs_on,
        'description': description or None,
    }


def build_server(
    config: Config, config_path: Path, catalog: Catalog | None = None
) -> FastMCP:
    """Wire a FastMCP instance with the tools matching the loaded config.

    Catalog-backed tools (list_plugins, explain_plugin,
    find_plugin_for_check_command, catalog_info) are only registered when a
    catalog was loaded successfully. That follows the principle-of-least-
    privilege pattern: unconfigured backends produce no tools.
    """
    mcp = FastMCP('mcp-server-icinga')

    @mcp.tool()
    def health_check() -> dict[str, Any]:
        """Report server status and which backends are configured.

        Returns the server name and version, the path of the loaded
        configuration file, a per-backend availability map and the status
        of the monitoring-plugins catalog. This is a pure inspection of the
        loaded configuration; it does not perform any live network checks.

        Use this to confirm that the MCP server is running with the
        configuration you expect after a restart of the MCP client.
        """
        return _health_check_payload(config, config_path, catalog)

    if catalog is not None:

        @mcp.tool()
        def catalog_info() -> dict[str, Any]:
            """Report where the Linuxfabrik monitoring-plugins catalog knowledge
            comes from and when it was materialised.

            Use this to understand whether the server is reasoning against a
            live checkout of the `monitoring-plugins` repo or a bundled
            snapshot from an `mcp-server-icinga` release.
            """
            return {
                'source': catalog.source,
                'built_at': catalog.built_at,
                'monitoring_plugins_ref': catalog.monitoring_plugins_ref,
                'plugin_count': len(catalog.plugins),
            }

        @mcp.tool()
        def list_plugins(
            runs_on: str | None = None, name_contains: str | None = None
        ) -> list[dict[str, Any]]:
            """List every Linuxfabrik monitoring plugin the server knows about.

            Each entry in the returned list is a compact summary (name,
            version, runs_on platform, truncated description). For full
            details use `explain_plugin(name)`.

            Optional filters, combined with logical AND:

            - `runs_on`: keep only plugins whose Fact Sheet says they run on
              this platform, e.g. `'Linux'`, `'Windows'`, `'Cross-platform'`.
            - `name_contains`: case-insensitive substring match against the
              plugin name. Useful for "list all *-version plugins":
              `name_contains='-version'`.
            """
            needle = name_contains.lower() if name_contains else None
            result: list[dict[str, Any]] = []
            for entry in catalog.plugins.values():
                if runs_on is not None and entry.runs_on != runs_on:
                    continue
                if needle is not None and needle not in entry.name.lower():
                    continue
                result.append(_plugin_summary(entry))
            result.sort(key=lambda row: row['name'])
            return result

        @mcp.tool()
        def explain_plugin(name: str) -> dict[str, Any]:
            """Return the full catalog entry for a plugin.

            Includes version, description, Fact Sheet metadata, all argparse
            arguments with defaults and help text, perfdata metrics, state
            rules parsed from the README `## States` section, and the
            mapping to Icinga Director check commands and variable prefixes.

            `name` is the exact plugin directory name from the
            `monitoring-plugins` repository, e.g. `'gitlab-version'` or
            `'disk-usage'`. When unsure, call `list_plugins(name_contains=...)`
            first.

            Raises when `name` is unknown.
            """
            entry = catalog.plugins.get(name)
            if entry is None:
                raise ValueError(
                    f'unknown plugin {name!r}. Use list_plugins() to discover available names.'
                )
            return entry.model_dump(mode='json')

        @mcp.tool()
        def find_plugin_for_check_command(
            check_command: str,
        ) -> dict[str, Any] | None:
            """Resolve an Icinga Director check command to the underlying
            monitoring plugin.

            Icinga services reference a `check_command` like
            `'cmd-check-gitlab-version'`. This tool returns the full catalog
            entry for the plugin that backs that command, or `None` when no
            plugin in the catalog declares the command.

            Use this to bridge "service X is CRIT with check_command Y" to
            plugin-level knowledge for root-cause analysis.
            """
            for entry in catalog.plugins.values():
                if check_command in entry.director_check_commands:
                    return entry.model_dump(mode='json')
            return None

    return mcp


def main() -> int:
    """CLI entrypoint, registered as the `mcp-server-icinga` console script."""
    try:
        config_path = find_config_path()
        config = load_config(config_path)
    except ConfigError as exc:
        print(f'mcp-server-icinga: {exc}', file=sys.stderr)
        return 1

    catalog: Catalog | None = None
    if config.monitoring_plugins.catalog_path:
        try:
            catalog = load_from_path(config.monitoring_plugins.catalog_path)
        except (FileNotFoundError, OSError) as exc:
            print(
                f'mcp-server-icinga: could not load plugin catalog from '
                f'{config.monitoring_plugins.catalog_path}: {exc}',
                file=sys.stderr,
            )
            return 1

    server = build_server(config, config_path, catalog=catalog)
    server.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
