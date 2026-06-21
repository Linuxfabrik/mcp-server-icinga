# SPDX-License-Identifier: Unlicense

"""Tests for `mcp_server_icinga.server`."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_server_icinga import __version__
from mcp_server_icinga.config import (
    Config,
    Icinga2CoreConfig,
    InstanceConfig,
    MonitoringPluginsConfig,
)
from mcp_server_icinga.server import (
    _health_check_payload,
    _resolve_core_client,
    build_server,
)

_ICINGA2_CORE_TOOLS = {
    'get_host',
    'get_problems',
    'get_service',
    'list_hosts',
    'list_services',
}

# Fake values used only as test fixtures: the path is never opened (only
# stringified for display in the health_check payload), and the passwords
# are passed to Pydantic SecretStr fields that exist solely to exercise the
# config schema. Annotated # nosec to keep bandit quiet about hardcoded
# /tmp paths and password-shaped strings in tests.
_FAKE_CONFIG_PATH = Path('/tmp/mcp-test-config.yaml')  # nosec B108
_FAKE_READ_PASSWORD = 'linuxfabrik'  # nosec B105
_FAKE_WRITE_PASSWORD = 'linuxfabrik'  # nosec B105


def _instance_with_core(write: bool = False) -> InstanceConfig:
    payload: dict = {
        'url': 'https://icinga.example.com:5665',
        'username': 'r',
        'password': _FAKE_READ_PASSWORD,
    }
    if write:
        payload['write_username'] = 'w'
        payload['write_password'] = _FAKE_WRITE_PASSWORD
    return InstanceConfig(icinga2_core=Icinga2CoreConfig.model_validate(payload))


# ---------------------------------------------------------------------------
# _health_check_payload
# ---------------------------------------------------------------------------


def test_health_check_payload_no_instances() -> None:
    payload = _health_check_payload(Config(), _FAKE_CONFIG_PATH)
    assert payload['name'] == 'mcp-server-icinga'
    assert payload['version'] == __version__
    assert payload['config_path'] == str(_FAKE_CONFIG_PATH)
    assert payload['instances'] == {}
    assert payload['monitoring_plugins_catalog']['source'].startswith(
        'bundled-snapshot'
    )


def test_health_check_payload_single_instance_read_only() -> None:
    config = Config(instances={'prod': _instance_with_core(write=False)})
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert payload['instances'] == {
        'prod': {
            'icinga2_core': True,
            'icinga_web': False,
            'icinga_director': False,
            'tsdb': False,
            'icinga2_core_write_enabled': False,
        }
    }


def test_health_check_payload_instance_with_write_credentials() -> None:
    config = Config(instances={'prod': _instance_with_core(write=True)})
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert payload['instances']['prod']['icinga2_core_write_enabled'] is True


def test_health_check_payload_multiple_instances() -> None:
    config = Config(
        instances={
            'prod-zh': _instance_with_core(write=True),
            'prod-fr': _instance_with_core(write=False),
            'staging': _instance_with_core(write=False),
        }
    )
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert set(payload['instances'].keys()) == {'prod-zh', 'prod-fr', 'staging'}
    assert payload['instances']['prod-zh']['icinga2_core_write_enabled'] is True
    assert payload['instances']['staging']['icinga2_core_write_enabled'] is False


def test_health_check_payload_catalog_configured_but_not_loaded() -> None:
    config = Config(
        monitoring_plugins=MonitoringPluginsConfig(
            catalog_path=Path('/opt/lf/monitoring-plugins/check-plugins'),
        ),
    )
    payload = _health_check_payload(config, _FAKE_CONFIG_PATH)
    assert payload['monitoring_plugins_catalog'] == {
        'source': 'configured-but-not-loaded',
    }


def test_health_check_payload_catalog_loaded() -> None:
    from mcp_server_icinga.plugin_catalog.schema import Catalog

    catalog = Catalog(
        source='live',
        built_at='2026-04-22T08:00:00+00:00',
        plugins={},
    )
    payload = _health_check_payload(Config(), _FAKE_CONFIG_PATH, catalog=catalog)
    assert payload['monitoring_plugins_catalog'] == {
        'source': 'live',
        'built_at': '2026-04-22T08:00:00+00:00',
        'monitoring_plugins_ref': None,
        'plugin_count': 0,
    }


# ---------------------------------------------------------------------------
# build_server
# ---------------------------------------------------------------------------


def test_build_server_returns_fastmcp_instance() -> None:
    server = build_server(Config(), _FAKE_CONFIG_PATH)
    assert isinstance(server, FastMCP)


def test_build_server_registers_health_check_tool_only_when_no_catalog() -> None:
    server = build_server(Config(), _FAKE_CONFIG_PATH)
    tools = server._tool_manager._tools
    assert 'health_check' in tools
    assert 'catalog_info' not in tools
    assert 'list_plugins' not in tools
    assert 'explain_plugin' not in tools
    assert 'find_plugin_for_check_command' not in tools


def test_build_server_registers_catalog_tools_when_catalog_given() -> None:
    from mcp_server_icinga.plugin_catalog.schema import Catalog

    empty_catalog = Catalog(source='live', plugins={})
    server = build_server(Config(), _FAKE_CONFIG_PATH, catalog=empty_catalog)
    tools = server._tool_manager._tools
    assert {
        'health_check',
        'catalog_info',
        'list_plugins',
        'explain_plugin',
        'find_plugin_for_check_command',
    } <= tools.keys()


# ---------------------------------------------------------------------------
# Icinga 2 Core tool registration
# ---------------------------------------------------------------------------


def test_build_server_omits_core_tools_without_icinga2_core() -> None:
    server = build_server(Config(), _FAKE_CONFIG_PATH)
    tools = server._tool_manager._tools
    assert _ICINGA2_CORE_TOOLS.isdisjoint(tools.keys())


def test_build_server_registers_core_tools_with_icinga2_core() -> None:
    config = Config(instances={'prod': _instance_with_core()})
    server = build_server(config, _FAKE_CONFIG_PATH)
    tools = server._tool_manager._tools
    assert tools.keys() >= _ICINGA2_CORE_TOOLS


# ---------------------------------------------------------------------------
# _resolve_core_client
# ---------------------------------------------------------------------------


def test_resolve_core_client_unknown_instance() -> None:
    config = Config(instances={'prod': _instance_with_core()})
    with pytest.raises(ValueError, match='unknown instance'):
        _resolve_core_client(config, 'staging')


def test_resolve_core_client_missing_backend() -> None:
    config = Config(instances={'prod': InstanceConfig()})
    with pytest.raises(ValueError, match='no icinga2_core backend'):
        _resolve_core_client(config, 'prod')


def test_resolve_core_client_returns_client() -> None:
    from mcp_server_icinga.icinga2_core import Icinga2CoreClient

    config = Config(instances={'prod': _instance_with_core()})
    assert isinstance(_resolve_core_client(config, 'prod'), Icinga2CoreClient)


def test_resolve_core_client_auto_selects_single_instance() -> None:
    from mcp_server_icinga.icinga2_core import Icinga2CoreClient

    config = Config(instances={'prod': _instance_with_core()})
    assert isinstance(_resolve_core_client(config), Icinga2CoreClient)


def test_resolve_core_client_auto_selects_only_core_instance() -> None:
    # Instances without an icinga2_core backend do not count towards the
    # auto-selection, so a single core instance is still unambiguous.
    from mcp_server_icinga.icinga2_core import Icinga2CoreClient

    config = Config(
        instances={'prod': _instance_with_core(), 'web-only': InstanceConfig()}
    )
    assert isinstance(_resolve_core_client(config), Icinga2CoreClient)


def test_resolve_core_client_ambiguous_without_instance() -> None:
    config = Config(
        instances={'prod-zh': _instance_with_core(), 'prod-fr': _instance_with_core()}
    )
    with pytest.raises(ValueError, match='several instances'):
        _resolve_core_client(config)
