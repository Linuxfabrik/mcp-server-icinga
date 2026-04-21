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


def _health_check_payload(config: Config, config_path: Path) -> dict[str, Any]:
    """Compute the payload returned by the `health_check` tool.

    Pure function: no network, no side effects. Lives outside the FastMCP
    decorator wrapper so it can be unit-tested without spinning up the
    server.
    """
    return {
        'name': 'mcp-server-icinga',
        'version': __version__,
        'config_path': str(config_path),
        'backends': {
            'icinga2_core': config.icinga2_core is not None,
            'icinga_web': config.icinga_web is not None,
            'icinga_director': config.icinga_director is not None,
            'tsdb': config.tsdb is not None,
        },
        'icinga2_core_write_enabled': (
            config.icinga2_core is not None
            and config.icinga2_core.write_password is not None
        ),
        'monitoring_plugins_catalog': (
            'live'
            if config.monitoring_plugins.catalog_path
            else 'bundled-snapshot (not yet implemented)'
        ),
    }


def build_server(config: Config, config_path: Path) -> FastMCP:
    """Wire a FastMCP instance with the tools matching the loaded config."""
    mcp = FastMCP('mcp-server-icinga')

    @mcp.tool()
    def health_check() -> dict[str, Any]:
        """Report server status and which backends are configured.

        Returns the server name and version, the path of the loaded
        configuration file and a per-backend availability map. This is a
        pure inspection of the loaded configuration; it does not perform
        any live network checks against Icinga or the TSDB.

        Use this to confirm that the MCP server is running with the
        configuration you expect after a restart of the MCP client.
        """
        return _health_check_payload(config, config_path)

    return mcp


def main() -> int:
    """CLI entrypoint, registered as the `mcp-server-icinga` console script."""
    try:
        config_path = find_config_path()
        config = load_config(config_path)
    except ConfigError as exc:
        print(f'mcp-server-icinga: {exc}', file=sys.stderr)
        return 1

    server = build_server(config, config_path)
    server.run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
