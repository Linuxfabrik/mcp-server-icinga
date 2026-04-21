# SPDX-License-Identifier: Unlicense

"""Tests for `mcp_server_icinga.config`."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server_icinga.config import (
    Config,
    ConfigError,
    InfluxDBConfig,
    _SYSTEM_PATH,
    find_config_path,
    load_config,
)


# ---------------------------------------------------------------------------
# !env tag
# ---------------------------------------------------------------------------


def test_env_tag_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FOO_PASSWORD', 'sup3r-s3cret')
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'icinga2_core:\n'
        "  url: 'https://icinga.example.com:5665'\n"
        "  username: 'mcp'\n"
        '  password: !env FOO_PASSWORD\n'
    )
    config = load_config(cfg)
    assert config.icinga2_core is not None
    assert config.icinga2_core.password.get_secret_value() == 'sup3r-s3cret'


def test_env_tag_missing_var_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MISSING_VAR', raising=False)
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'icinga2_core:\n'
        "  url: 'https://icinga.example.com:5665'\n"
        "  username: 'mcp'\n"
        '  password: !env MISSING_VAR\n'
    )
    with pytest.raises(ConfigError, match='MISSING_VAR'):
        load_config(cfg)


def test_env_tag_empty_name_raises(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'icinga2_core:\n'
        "  url: 'https://icinga.example.com:5665'\n"
        "  username: 'mcp'\n"
        "  password: !env ''\n"
    )
    with pytest.raises(ConfigError, match='requires an environment variable name'):
        load_config(cfg)


# ---------------------------------------------------------------------------
# Lookup order
# ---------------------------------------------------------------------------


def test_find_config_path_prefers_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / 'somewhere.yaml'
    explicit.touch()
    monkeypatch.setenv('ICINGA_MCP_CONFIG', str(explicit))
    assert find_config_path() == explicit


def test_find_config_path_returns_env_path_even_if_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Honour explicit user intent; load_config will then raise a clear error.
    monkeypatch.setenv('ICINGA_MCP_CONFIG', str(tmp_path / 'does-not-exist.yaml'))
    assert find_config_path() == tmp_path / 'does-not-exist.yaml'


def test_find_config_path_falls_back_to_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('ICINGA_MCP_CONFIG', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    user_path = tmp_path / 'mcp-server-icinga' / 'config.yaml'
    user_path.parent.mkdir(parents=True)
    user_path.touch()
    assert find_config_path() == user_path


def test_find_config_path_raises_when_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('ICINGA_MCP_CONFIG', raising=False)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    # Pretend the system path also does not exist.
    monkeypatch.setattr(
        'mcp_server_icinga.config._SYSTEM_PATH', tmp_path / 'no-system-config.yaml'
    )
    with pytest.raises(ConfigError, match='no config file found'):
        find_config_path()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_empty_config_is_valid(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text('')
    config = load_config(cfg)
    assert isinstance(config, Config)
    assert config.icinga2_core is None
    assert config.icinga_web is None
    assert config.icinga_director is None
    assert config.tsdb is None


def test_full_config_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        'CORE_PW',
        'CORE_WRITE_PW',
        'WEB_PW',
        'DIR_PW',
        'TSDB_TOKEN',
    ):
        monkeypatch.setenv(name, f'value-of-{name}')

    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'icinga2_core:\n'
        "  url: 'https://icinga.example.com:5665'\n"
        "  username: 'r'\n"
        '  password: !env CORE_PW\n'
        "  write_username: 'w'\n"
        '  write_password: !env CORE_WRITE_PW\n'
        '  verify_tls: false\n'
        '  timeout: 12\n'
        'icinga_web:\n'
        "  url: 'https://icingaweb.example.com'\n"
        "  username: 'web'\n"
        '  password: !env WEB_PW\n'
        'icinga_director:\n'
        "  url: 'https://icingaweb.example.com/director'\n"
        "  username: 'dir'\n"
        '  password: !env DIR_PW\n'
        'tsdb:\n'
        "  type: 'influxdb'\n"
        "  url: 'http://influxdb.example.com:8086'\n"
        "  org: 'linuxfabrik'\n"
        "  bucket: 'icinga'\n"
        '  token: !env TSDB_TOKEN\n'
        'monitoring_plugins:\n'
        "  catalog_path: '/opt/lf/monitoring-plugins/check-plugins'\n"
    )
    config = load_config(cfg)

    assert config.icinga2_core is not None
    assert config.icinga2_core.write_password is not None
    assert config.icinga2_core.write_password.get_secret_value() == 'value-of-CORE_WRITE_PW'
    assert config.icinga2_core.verify_tls is False
    assert config.icinga2_core.timeout == 12
    assert isinstance(config.tsdb, InfluxDBConfig)
    assert config.tsdb.bucket == 'icinga'
    assert config.monitoring_plugins.catalog_path == Path(
        '/opt/lf/monitoring-plugins/check-plugins'
    )


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text("nonsense_key: 'whatever'\n")
    with pytest.raises(ConfigError, match='nonsense_key'):
        load_config(cfg)


def test_missing_required_field_clear_error(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'icinga2_core:\n'
        "  url: 'https://icinga.example.com:5665'\n"
        "  username: 'mcp'\n"
        # password missing on purpose
    )
    with pytest.raises(ConfigError, match='password'):
        load_config(cfg)


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text('- just\n- a\n- list\n')
    with pytest.raises(ConfigError, match='must be a mapping'):
        load_config(cfg)


def test_yaml_syntax_error_raises_configerror(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text("icinga2_core:\n  url: 'missing-quote\n")
    with pytest.raises(ConfigError, match='YAML error'):
        load_config(cfg)


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match='not found'):
        load_config(tmp_path / 'nope.yaml')


# ---------------------------------------------------------------------------
# Bundled example config validates
# ---------------------------------------------------------------------------


def test_bundled_example_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shipped examples/config.example.yaml must parse cleanly."""
    for name in (
        'ICINGA2_CORE_PASSWORD',
        'ICINGA_WEB_PASSWORD',
        'ICINGA_DIRECTOR_PASSWORD',
        'INFLUXDB_TOKEN',
    ):
        monkeypatch.setenv(name, 'placeholder')

    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / 'examples' / 'config.example.yaml'
    config = load_config(example)
    assert config.icinga2_core is not None
    assert config.icinga_web is not None
    assert config.icinga_director is not None
    assert isinstance(config.tsdb, InfluxDBConfig)
    assert config.monitoring_plugins.catalog_path is not None


# ---------------------------------------------------------------------------
# Sanity: _SYSTEM_PATH constant points where it should
# ---------------------------------------------------------------------------


def test_system_path_constant() -> None:
    assert _SYSTEM_PATH == Path('/etc/mcp-server-icinga/config.yaml')
