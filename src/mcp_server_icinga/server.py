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
from mcp_server_icinga.icinga2_core import (
    HOST_STATE_CODES,
    SERVICE_STATE_CODES,
    Icinga2CoreClient,
    Icinga2CoreNotFoundError,
    summarize_host,
    summarize_service,
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


def _resolve_core_client(
    config: Config, instance: str | None = None
) -> Icinga2CoreClient:
    """Return an Icinga 2 Core client for `instance` or raise a clear error.

    Pure config lookup, no network. When `instance` is omitted and exactly
    one configured instance has an `icinga2_core` backend, that instance is
    auto-selected; with several to choose from, a `ValueError` lists them so
    the caller can name one. Also raises when a named instance is unknown or
    has no `icinga2_core` backend, so the LLM gets an actionable message
    instead of a connection error.
    """
    core_instances = sorted(
        name for name, inst in config.instances.items() if inst.icinga2_core is not None
    )

    if instance is None:
        if len(core_instances) == 1:
            instance = core_instances[0]
        else:
            choices = ', '.join(core_instances) or '<none>'
            raise ValueError(
                f'several instances have an icinga2_core backend ({choices}); '
                f'specify which one via the instance parameter.'
            )

    inst = config.instances.get(instance)
    if inst is None:
        known = ', '.join(sorted(config.instances)) or '<none>'
        raise ValueError(
            f'unknown instance {instance!r}. Configured instances: {known}. '
            f'Call health_check() to inspect them.'
        )
    if inst.icinga2_core is None:
        raise ValueError(
            f'instance {instance!r} has no icinga2_core backend configured.'
        )
    return Icinga2CoreClient(inst.icinga2_core)


def _state_code(state: str, codes: dict[str, int], kind: str) -> int:
    """Translate a caller-supplied state label into its numeric code."""
    code = codes.get(state.upper())
    if code is None:
        valid = ', '.join(sorted(codes))
        raise ValueError(f'invalid {kind} state {state!r}. Valid states: {valid}.')
    return code


def _list_hosts_payload(
    client: Icinga2CoreClient,
    state: str | None = None,
    name_contains: str | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    filter_vars: dict[str, Any] = {}
    if state is not None:
        conditions.append('host.state==host_state')
        filter_vars['host_state'] = _state_code(state, HOST_STATE_CODES, 'host')
    if name_contains is not None:
        conditions.append('match(pattern, host.name)')
        filter_vars['pattern'] = f'*{name_contains}*'
    filter_expr = ' && '.join(conditions) or None
    results = client.query_hosts(filter=filter_expr, filter_vars=filter_vars or None)
    summaries = [summarize_host(row) for row in results]
    summaries.sort(key=lambda row: row['name'] or '')
    return summaries


def _list_services_payload(
    client: Icinga2CoreClient,
    host: str | None = None,
    state: str | None = None,
    name_contains: str | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    filter_vars: dict[str, Any] = {}
    if host is not None:
        conditions.append('service.host_name==host_name')
        filter_vars['host_name'] = host
    if state is not None:
        conditions.append('service.state==service_state')
        filter_vars['service_state'] = _state_code(
            state, SERVICE_STATE_CODES, 'service'
        )
    if name_contains is not None:
        conditions.append('match(pattern, service.name)')
        filter_vars['pattern'] = f'*{name_contains}*'
    filter_expr = ' && '.join(conditions) or None
    results = client.query_services(filter=filter_expr, filter_vars=filter_vars or None)
    summaries = [summarize_service(row) for row in results]
    summaries.sort(key=lambda row: row['name'] or '')
    return summaries


def _get_host_payload(client: Icinga2CoreClient, name: str) -> dict[str, Any]:
    results = client.query_hosts(
        filter='host.name==host_name', filter_vars={'host_name': name}
    )
    if not results:
        raise Icinga2CoreNotFoundError(f'no host named {name!r}')
    return summarize_host(results[0])


def _get_service_payload(
    client: Icinga2CoreClient, host: str, service: str
) -> dict[str, Any]:
    results = client.query_services(
        filter='service.host_name==host_name && service.name==service_name',
        filter_vars={'host_name': host, 'service_name': service},
    )
    if not results:
        raise Icinga2CoreNotFoundError(f'no service {service!r} on host {host!r}')
    return summarize_service(results[0])


def _get_problems_payload(client: Icinga2CoreClient) -> dict[str, Any]:
    hosts = client.query_hosts(filter='host.state!=0')
    services = client.query_services(filter='service.state!=0')
    host_summaries = [summarize_host(row) for row in hosts]
    service_summaries = [summarize_service(row) for row in services]
    host_summaries.sort(key=lambda row: row['name'] or '')
    service_summaries.sort(key=lambda row: row['name'] or '')
    return {
        'hosts': host_summaries,
        'services': service_summaries,
        'host_problem_count': len(host_summaries),
        'service_problem_count': len(service_summaries),
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

    if any(inst.icinga2_core is not None for inst in config.instances.values()):

        @mcp.tool()
        def list_hosts(
            instance: str | None = None,
            state: str | None = None,
            name_contains: str | None = None,
        ) -> list[dict[str, Any]]:
            """List monitored hosts of one Icinga instance with their state.

            `instance` is the configured deployment name (e.g. `'prod-zh'`);
            omit it when only one instance is configured. Call `health_check()`
            to discover the configured instance names.

            Each entry is a compact summary: name, address, current state
            (`UP`/`DOWN`), soft/hard state type, whether it is acknowledged
            or in downtime, the last check plugin output and perfdata, and
            check timestamps.

            Optional filters, combined with logical AND:

            - `state`: keep only hosts in this state, one of `UP`, `DOWN`
              (case-insensitive).
            - `name_contains`: case-insensitive substring match against the
              host name.

            For everything in a problem state across hosts and services at
            once, prefer `get_problems(instance)`.
            """
            client = _resolve_core_client(config, instance)
            return _list_hosts_payload(client, state=state, name_contains=name_contains)

        @mcp.tool()
        def list_services(
            instance: str | None = None,
            host: str | None = None,
            state: str | None = None,
            name_contains: str | None = None,
        ) -> list[dict[str, Any]]:
            """List monitored services of one Icinga instance with their state.

            `instance` is the configured deployment name (e.g. `'prod-zh'`);
            omit it when only one instance is configured. Call `health_check()`
            to discover the configured instance names.

            Each entry is a compact summary: full name (`host!service`), the
            service and host name, the host's state for context, current
            service state (`OK`/`WARNING`/`CRITICAL`/`UNKNOWN`), state type,
            acknowledgement and downtime flags, the check command, the last
            check plugin output and perfdata, and check timestamps.

            Optional filters, combined with logical AND:

            - `host`: keep only services of this exact host name.
            - `state`: keep only services in this state, one of `OK`,
              `WARNING`, `CRITICAL`, `UNKNOWN` (case-insensitive).
            - `name_contains`: case-insensitive substring match against the
              service name.

            The `check_command` field bridges to plugin knowledge: pass it to
            `find_plugin_for_check_command(check_command)` to learn what the
            service actually checks.
            """
            client = _resolve_core_client(config, instance)
            return _list_services_payload(
                client, host=host, state=state, name_contains=name_contains
            )

        @mcp.tool()
        def get_host(name: str, instance: str | None = None) -> dict[str, Any]:
            """Return the full state summary for a single host.

            `name` is the exact host name. `instance` is the configured
            deployment name (e.g. `'prod-zh'`); omit it when only one instance
            is configured. Raises when the host does not exist; use
            `list_hosts(name_contains=...)` to discover names.
            """
            client = _resolve_core_client(config, instance)
            return _get_host_payload(client, name)

        @mcp.tool()
        def get_service(
            host: str, service: str, instance: str | None = None
        ) -> dict[str, Any]:
            """Return the full state summary for a single service.

            `host` is the exact host name and `service` the service name on
            that host. `instance` is the configured deployment name (e.g.
            `'prod-zh'`); omit it when only one instance is configured. Raises
            when the service does not exist; use `list_services(host=...)` to
            discover names.
            """
            client = _resolve_core_client(config, instance)
            return _get_service_payload(client, host, service)

        @mcp.tool()
        def get_problems(instance: str | None = None) -> dict[str, Any]:
            """Return everything in a problem state on one Icinga instance.

            `instance` is the configured deployment name (e.g. `'prod-zh'`);
            omit it when only one instance is configured. Returns all hosts
            that are not `UP` and all services that are not `OK`, each as a
            compact summary, plus the respective problem counts. This is the
            starting point for triage: one call gives the full picture of what
            is currently alerting.
            """
            client = _resolve_core_client(config, instance)
            return _get_problems_payload(client)

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
