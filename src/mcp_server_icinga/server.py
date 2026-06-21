# SPDX-License-Identifier: Unlicense

"""MCP server entrypoint.

Starts a Model Context Protocol server over stdio, registers the tools
that match the loaded configuration and runs the event loop. The
configuration is loaded once at startup; tools whose backend is not
configured are simply not registered, so a deployment with only the
Icinga 2 Core API works without an Icinga Director or TSDB section.
"""

from __future__ import annotations

import ast
import sys
import time
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
        'name': 'Linuxfabrik Icinga',
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


def _extract_function_source(source: str, function: str) -> str:
    """Return the source segment of the named top-level function.

    Raises `ValueError` listing the available top-level functions when the
    name is not found.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name == function
        ):
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                return segment
    available = ', '.join(
        sorted(
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )
    )
    raise ValueError(
        f'no top-level function {function!r} in the plugin source. '
        f'Available functions: {available or "<none>"}.'
    )


def _read_plugin_source_payload(
    catalog: Catalog,
    base_dir: Path | None,
    name: str,
    function: str | None = None,
) -> dict[str, Any]:
    """Return the on-disk source of a plugin, optionally a single function.

    `base_dir` is the monitoring-plugins repository root (the parent of the
    configured `check-plugins` directory); plugin `source_path` values are
    relative to it. Raises `ValueError` when the plugin is unknown, when no
    local checkout is available (bundled-snapshot mode), or when the resolved
    path escapes the repository root.
    """
    entry = catalog.plugins.get(name)
    if entry is None:
        raise ValueError(
            f'unknown plugin {name!r}. Use list_plugins() to discover available names.'
        )
    if base_dir is None:
        raise ValueError(
            f'source for {name!r} is unavailable: it requires a local catalog, '
            f'set monitoring_plugins.catalog_path to a monitoring-plugins checkout.'
        )

    root = Path(base_dir).resolve()
    path = (root / entry.source_path).resolve()
    # Defensive: source_path comes from our own loader, but never read outside
    # the repository root regardless.
    if root != path and root not in path.parents:
        raise ValueError(f'refusing to read {entry.source_path!r} outside {root}')
    try:
        source = path.read_text(encoding='utf-8')
    except OSError as exc:
        raise ValueError(f'cannot read source for {name!r}: {exc}') from exc

    if function is not None:
        source = _extract_function_source(source, function)

    payload: dict[str, Any] = {
        'name': name,
        'source_path': entry.source_path,
        'line_count': source.count('\n') + 1,
        'source': source,
    }
    if function is not None:
        payload['function'] = function
    return payload


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


# ---------------------------------------------------------------------------
# Icinga 2 Core actions (write)
# ---------------------------------------------------------------------------


def _resolve_write_client(
    config: Config, instance: str | None = None
) -> Icinga2CoreClient:
    """Return a write-capable Icinga 2 Core client or raise a clear error.

    Like `_resolve_core_client`, but only instances whose `icinga2_core`
    backend carries write credentials qualify. Auto-selects when exactly one
    does; otherwise lists the candidates.
    """
    write_instances = sorted(
        name
        for name, inst in config.instances.items()
        if inst.icinga2_core is not None
        and inst.icinga2_core.write_password is not None
    )

    if instance is None:
        if len(write_instances) == 1:
            instance = write_instances[0]
        else:
            choices = ', '.join(write_instances) or '<none>'
            raise ValueError(
                f'several instances have write credentials ({choices}); '
                f'specify which one via the instance parameter.'
            )

    client = _resolve_core_client(config, instance)
    if client.write_author is None:
        raise ValueError(
            f'instance {instance!r} has no write credentials configured; '
            f'acknowledge / downtime / reschedule are disabled for it.'
        )
    return client


def _object_target(host: str, service: str | None) -> tuple[str, str, dict[str, Any]]:
    """Build the (type, filter, filter_vars) targeting one host or service."""
    if service is not None:
        return (
            'Service',
            'host.name==host_name && service.name==service_name',
            {'host_name': host, 'service_name': service},
        )
    return ('Host', 'host.name==host_name', {'host_name': host})


def _action_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Condense an Icinga actions response into an ok flag plus per-object rows."""
    rows: list[dict[str, Any]] = []
    for item in results:
        row: dict[str, Any] = {
            'code': item.get('code'),
            'status': item.get('status'),
        }
        if 'name' in item:
            # schedule-downtime returns the created downtime name.
            row['name'] = item['name']
        rows.append(row)
    ok = bool(rows) and all((row['code'] or 0) < 400 for row in rows)
    return {'ok': ok, 'count': len(rows), 'results': rows}


def _acknowledge_payload(
    client: Icinga2CoreClient,
    host: str,
    service: str | None,
    comment: str,
    sticky: bool = False,
    notify: bool = False,
    expiry_hours: float | None = None,
) -> dict[str, Any]:
    object_type, filter_expr, filter_vars = _object_target(host, service)
    body: dict[str, Any] = {
        'type': object_type,
        'filter': filter_expr,
        'filter_vars': filter_vars,
        'author': client.write_author or '',
        'comment': comment,
        'sticky': sticky,
        'notify': notify,
    }
    if expiry_hours is not None:
        body['expiry'] = int(time.time() + expiry_hours * 3600)
    return _action_result(client.run_action('acknowledge-problem', body))


def _schedule_downtime_payload(
    client: Icinga2CoreClient,
    host: str,
    service: str | None,
    comment: str,
    hours: float = 2.0,
    all_services: bool = False,
) -> dict[str, Any]:
    object_type, filter_expr, filter_vars = _object_target(host, service)
    start = int(time.time())
    body: dict[str, Any] = {
        'type': object_type,
        'filter': filter_expr,
        'filter_vars': filter_vars,
        'author': client.write_author or '',
        'comment': comment,
        'start_time': start,
        'end_time': int(start + hours * 3600),
        'fixed': True,
    }
    if object_type == 'Host' and all_services:
        body['all_services'] = True
    return _action_result(client.run_action('schedule-downtime', body))


def _remove_downtime_payload(
    client: Icinga2CoreClient, host: str, service: str | None
) -> dict[str, Any]:
    object_type, filter_expr, filter_vars = _object_target(host, service)
    body: dict[str, Any] = {
        'type': object_type,
        'filter': filter_expr,
        'filter_vars': filter_vars,
        'author': client.write_author or '',
    }
    return _action_result(client.run_action('remove-downtime', body))


def _reschedule_check_payload(
    client: Icinga2CoreClient,
    host: str,
    service: str | None,
    force: bool = False,
) -> dict[str, Any]:
    object_type, filter_expr, filter_vars = _object_target(host, service)
    body: dict[str, Any] = {
        'type': object_type,
        'filter': filter_expr,
        'filter_vars': filter_vars,
        'force': force,
    }
    return _action_result(client.run_action('reschedule-check', body))


def build_server(
    config: Config, config_path: Path, catalog: Catalog | None = None
) -> FastMCP:
    """Wire a FastMCP instance with the tools matching the loaded config.

    Catalog-backed tools (list_plugins, explain_plugin,
    find_plugin_for_check_command, catalog_info) are only registered when a
    catalog was loaded successfully. That follows the principle-of-least-
    privilege pattern: unconfigured backends produce no tools.
    """
    mcp = FastMCP('Linuxfabrik Icinga')

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

        @mcp.tool()
        def read_plugin_source(
            name: str, function: str | None = None
        ) -> dict[str, Any]:
            """Return the Python source code of a monitoring plugin.

            Use this when `explain_plugin(name)` metadata is not enough and you
            need the actual logic: how thresholds are computed, what each exit
            state means, or exactly what the check queries. This reads the
            plugin's real source from the configured local checkout.

            - `name`: exact plugin directory name, e.g. `'disk-usage'`.
            - `function`: optionally return just one top-level function's
              source (e.g. `'main'`) instead of the whole file, to save tokens
              when you only need a specific part.

            Returns the source text, its path within the monitoring-plugins
            tree and the line count. Raises when the plugin or function is
            unknown, or when the server runs without a local catalog checkout.
            """
            base = config.monitoring_plugins.catalog_path
            base_dir = base.parent if base is not None else None
            return _read_plugin_source_payload(catalog, base_dir, name, function)

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

    if any(
        inst.icinga2_core is not None and inst.icinga2_core.write_password is not None
        for inst in config.instances.values()
    ):

        @mcp.tool()
        def acknowledge_problem(
            host: str,
            comment: str,
            service: str | None = None,
            instance: str | None = None,
            sticky: bool = False,
            notify: bool = False,
            expiry_hours: float | None = None,
        ) -> dict[str, Any]:
            """Acknowledge the current problem of a host or service.

            This mutates Icinga: it suppresses repeat notifications for the
            current problem and is attributed to the configured write user.
            Only available for instances that have write credentials.

            - `host`: exact host name. Required.
            - `comment`: why it is being acknowledged. Required.
            - `service`: service name on `host`; omit to acknowledge the host
              problem itself.
            - `instance`: deployment name; omit when only one write-capable
              instance is configured.
            - `sticky`: keep the acknowledgement until full recovery (not just
              until the state improves). Defaults to false.
            - `notify`: send an acknowledgement notification. Defaults to false.
            - `expiry_hours`: auto-remove the acknowledgement after this many
              hours. Omit for no expiry.
            """
            client = _resolve_write_client(config, instance)
            return _acknowledge_payload(
                client,
                host,
                service,
                comment,
                sticky=sticky,
                notify=notify,
                expiry_hours=expiry_hours,
            )

        @mcp.tool()
        def schedule_downtime(
            host: str,
            comment: str,
            service: str | None = None,
            instance: str | None = None,
            hours: float = 2.0,
            all_services: bool = False,
        ) -> dict[str, Any]:
            """Schedule a fixed downtime for a host or service, starting now.

            This mutates Icinga: it suppresses notifications for the window and
            is attributed to the configured write user. Only available for
            instances that have write credentials.

            - `host`: exact host name. Required.
            - `comment`: reason for the downtime. Required.
            - `service`: service name on `host`; omit to put the host into
              downtime.
            - `instance`: deployment name; omit when only one write-capable
              instance is configured.
            - `hours`: downtime length in hours from now. Defaults to 2.
            - `all_services`: when targeting a host, also put all its services
              into downtime. Ignored for a single service.

            The result includes the created downtime name, which
            `remove_downtime` can act on.
            """
            client = _resolve_write_client(config, instance)
            return _schedule_downtime_payload(
                client, host, service, comment, hours=hours, all_services=all_services
            )

        @mcp.tool()
        def remove_downtime(
            host: str,
            service: str | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            """Remove scheduled downtimes from a host or service.

            This mutates Icinga and is only available for instances that have
            write credentials.

            - `host`: exact host name. Required.
            - `service`: service name on `host`; omit to remove the host's own
              downtimes (service downtimes added via `all_services` are removed
              with the host downtime).
            - `instance`: deployment name; omit when only one write-capable
              instance is configured.
            """
            client = _resolve_write_client(config, instance)
            return _remove_downtime_payload(client, host, service)

        @mcp.tool()
        def reschedule_check(
            host: str,
            service: str | None = None,
            instance: str | None = None,
            force: bool = False,
        ) -> dict[str, Any]:
            """Trigger an immediate check of a host or service.

            This mutates Icinga (it makes the object run its check now) and is
            only available for instances that have write credentials.

            - `host`: exact host name. Required.
            - `service`: service name on `host`; omit to recheck the host.
            - `instance`: deployment name; omit when only one write-capable
              instance is configured.
            - `force`: run the check even if active checks or the time period
              would normally suppress it. Defaults to false.
            """
            client = _resolve_write_client(config, instance)
            return _reschedule_check_payload(client, host, service, force=force)

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
