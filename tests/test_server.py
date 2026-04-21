# SPDX-License-Identifier: Unlicense

"""Tests for `mcp_server_icinga.server`."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcp_server_icinga import __version__
from mcp_server_icinga.config import (
    Config,
    Icinga2CoreConfig,
    MonitoringPluginsConfig,
)
from mcp_server_icinga.server import _health_check_payload, build_server


# ---------------------------------------------------------------------------
# _health_check_payload
# ---------------------------------------------------------------------------


def test_health_check_payload_no_backends() -> None:
    payload = _health_check_payload(Config(), Path('/tmp/missing.yaml'))
    assert payload['name'] == 'mcp-server-icinga'
    assert payload['version'] == __version__
    assert payload['config_path'] == '/tmp/missing.yaml'
    assert payload['backends'] == {
        'icinga2_core': False,
        'icinga_web': False,
        'icinga_director': False,
        'tsdb': False,
    }
    assert payload['icinga2_core_write_enabled'] is False
    assert 'bundled-snapshot' in payload['monitoring_plugins_catalog']


def test_health_check_payload_core_read_only() -> None:
    config = Config(
        icinga2_core=Icinga2CoreConfig.model_validate(
            {
                'url': 'https://icinga.example.com:5665',
                'username': 'r',
                'password': 'r-pw',
            }
        ),
    )
    payload = _health_check_payload(config, Path('/tmp/x.yaml'))
    assert payload['backends']['icinga2_core'] is True
    assert payload['icinga2_core_write_enabled'] is False


def test_health_check_payload_core_with_write_credentials() -> None:
    config = Config(
        icinga2_core=Icinga2CoreConfig.model_validate(
            {
                'url': 'https://icinga.example.com:5665',
                'username': 'r',
                'password': 'r-pw',
                'write_username': 'w',
                'write_password': 'w-pw',
            }
        ),
    )
    payload = _health_check_payload(config, Path('/tmp/x.yaml'))
    assert payload['icinga2_core_write_enabled'] is True


def test_health_check_payload_catalog_live() -> None:
    config = Config(
        monitoring_plugins=MonitoringPluginsConfig(
            catalog_path=Path('/opt/lf/monitoring-plugins/check-plugins'),
        ),
    )
    payload = _health_check_payload(config, Path('/tmp/x.yaml'))
    assert payload['monitoring_plugins_catalog'] == 'live'


# ---------------------------------------------------------------------------
# build_server
# ---------------------------------------------------------------------------


def test_build_server_returns_fastmcp_instance() -> None:
    server = build_server(Config(), Path('/tmp/x.yaml'))
    assert isinstance(server, FastMCP)


def test_build_server_registers_health_check_tool() -> None:
    server = build_server(Config(), Path('/tmp/x.yaml'))
    # FastMCP exposes a private tool manager. If a future SDK release moves
    # this attribute, adjust the assertion to whatever the new public API is.
    tools = server._tool_manager._tools
    assert 'health_check' in tools
