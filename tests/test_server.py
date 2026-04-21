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

# Fake values used only as test fixtures: the path is never opened (only
# stringified for display in the health_check payload), and the passwords
# are passed to Pydantic SecretStr fields that exist solely to exercise the
# config schema. Annotated # nosec to keep bandit quiet about hardcoded
# /tmp paths and password-shaped strings in tests.
_FAKE_CONFIG_PATH = Path('/tmp/mcp-test-config.yaml')  # nosec B108
_FAKE_READ_PASSWORD = 'fixture-read-password'  # nosec B105
_FAKE_WRITE_PASSWORD = 'fixture-write-password'  # nosec B105


# ---------------------------------------------------------------------------
# _health_check_payload
# ---------------------------------------------------------------------------


def test_health_check_payload_no_backends() -> None:
    payload = _health_check_payload(Config(), _FAKE_CONFIG_PATH)
    assert payload['name'] == 'mcp-server-icinga'
    assert payload['version'] == __version__
    assert payload['config_path'] == str(_FAKE_CONFIG_PATH)
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
                'password': _FAKE_READ_PASSWORD,
            }
        ),
    )
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert payload['backends']['icinga2_core'] is True
    assert payload['icinga2_core_write_enabled'] is False


def test_health_check_payload_core_with_write_credentials() -> None:
    config = Config(
        icinga2_core=Icinga2CoreConfig.model_validate(
            {
                'url': 'https://icinga.example.com:5665',
                'username': 'r',
                'password': _FAKE_READ_PASSWORD,
                'write_username': 'w',
                'write_password': _FAKE_WRITE_PASSWORD,
            }
        ),
    )
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert payload['icinga2_core_write_enabled'] is True


def test_health_check_payload_catalog_live() -> None:
    config = Config(
        monitoring_plugins=MonitoringPluginsConfig(
            catalog_path=Path('/opt/lf/monitoring-plugins/check-plugins'),
        ),
    )
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert payload['monitoring_plugins_catalog'] == 'live'


# ---------------------------------------------------------------------------
# build_server
# ---------------------------------------------------------------------------


def test_build_server_returns_fastmcp_instance() -> None:
    server = build_server(Config(), _FAKE_CONFIG_PATH)
    assert isinstance(server, FastMCP)


def test_build_server_registers_health_check_tool() -> None:
    server = build_server(Config(), _FAKE_CONFIG_PATH)
    # FastMCP exposes a private tool manager. If a future SDK release moves
    # this attribute, adjust the assertion to whatever the new public API is.
    tools = server._tool_manager._tools
    assert 'health_check' in tools
