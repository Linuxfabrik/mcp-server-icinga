# SPDX-License-Identifier: Unlicense

"""Tests for `mcp_server_icinga.config`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_server_icinga.config import (
    _SYSTEM_PATH,
    Config,
    ConfigError,
    InfluxDBConfig,
    find_config_path,
    load_config,
)

# ---------------------------------------------------------------------------
# !env tag
# ---------------------------------------------------------------------------


def _instance_yaml(password_line: str) -> str:
    return (
        'instances:\n'
        '  prod:\n'
        '    icinga2_core:\n'
        "      url: 'https://icinga.example.com:5665'\n"
        "      username: 'mcp'\n"
        f'      {password_line}\n'
    )


def test_env_tag_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FOO_PASSWORD', 'sup3r-s3cret')
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml('password: !env FOO_PASSWORD'))
    config = load_config(cfg)
    assert config.instances['prod'].icinga2_core is not None
    assert (
        config.instances['prod'].icinga2_core.password.get_secret_value()
        == 'sup3r-s3cret'
    )


def test_env_tag_missing_var_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv('MISSING_VAR', raising=False)
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml('password: !env MISSING_VAR'))
    with pytest.raises(ConfigError, match='MISSING_VAR'):
        load_config(cfg)


def test_env_tag_empty_name_raises(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml("password: !env ''"))
    with pytest.raises(ConfigError, match='requires an environment variable name'):
        load_config(cfg)


# ---------------------------------------------------------------------------
# !file tag
# ---------------------------------------------------------------------------


def test_file_tag_resolves(tmp_path: Path) -> None:
    secret_file = tmp_path / 'secret'
    secret_file.write_text('file-secret\n', encoding='utf-8')  # trailing newline
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml(f'password: !file {secret_file}'))
    config = load_config(cfg)
    assert config.instances['prod'].icinga2_core is not None
    assert (
        config.instances['prod'].icinga2_core.password.get_secret_value()
        == 'file-secret'
    )


def test_file_tag_strips_only_trailing_newline(tmp_path: Path) -> None:
    secret_file = tmp_path / 'secret'
    secret_file.write_text('  spaced-secret  \n', encoding='utf-8')
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml(f'password: !file {secret_file}'))
    config = load_config(cfg)
    assert (
        config.instances['prod'].icinga2_core.password.get_secret_value()
        == '  spaced-secret  '
    )


def test_file_tag_missing_path_raises(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml(f'password: !file {tmp_path}/does-not-exist'))
    with pytest.raises(ConfigError, match='does not exist'):
        load_config(cfg)


def test_file_tag_empty_path_raises(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml("password: !file ''"))
    with pytest.raises(ConfigError, match='non-empty path'):
        load_config(cfg)


def test_file_tag_directory_raises(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(_instance_yaml(f'password: !file {tmp_path}'))
    with pytest.raises(ConfigError, match='not a regular file'):
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
    assert config.instances == {}


def test_empty_instances_dict_is_valid(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text('instances: {}\n')
    config = load_config(cfg)
    assert config.instances == {}


def test_multiple_instances_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ('PROD_ZH_PW', 'PROD_FR_PW', 'STG_PW'):
        monkeypatch.setenv(name, f'value-of-{name}')

    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'instances:\n'
        '  prod-zh:\n'
        '    icinga2_core:\n'
        "      url: 'https://icinga2-prod-zh.example.com:5665'\n"
        "      username: 'mcp'\n"
        '      password: !env PROD_ZH_PW\n'
        '  prod-fr:\n'
        '    icinga2_core:\n'
        "      url: 'https://icinga2-prod-fr.example.com:5665'\n"
        "      username: 'mcp'\n"
        '      password: !env PROD_FR_PW\n'
        '  staging:\n'
        '    icinga2_core:\n'
        "      url: 'https://icinga2-stg.example.com:5665'\n"
        "      username: 'mcp'\n"
        '      password: !env STG_PW\n'
    )
    config = load_config(cfg)
    assert set(config.instances.keys()) == {'prod-zh', 'prod-fr', 'staging'}
    assert (
        config.instances['prod-zh'].icinga2_core.password.get_secret_value()
        == 'value-of-PROD_ZH_PW'
    )


def test_full_instance_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ('CORE_PW', 'CORE_WRITE_PW', 'WEB_PW', 'DIR_PW', 'TSDB_TOKEN'):
        monkeypatch.setenv(name, f'value-of-{name}')

    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'instances:\n'
        '  prod:\n'
        '    icinga2_core:\n'
        "      url: 'https://icinga.example.com:5665'\n"
        "      username: 'r'\n"
        '      password: !env CORE_PW\n'
        "      write_username: 'w'\n"
        '      write_password: !env CORE_WRITE_PW\n'
        '      verify_tls: false\n'
        '      timeout: 12\n'
        '    icinga_web:\n'
        "      url: 'https://icingaweb.example.com'\n"
        "      username: 'web'\n"
        '      password: !env WEB_PW\n'
        '    icinga_director:\n'
        "      url: 'https://icingaweb.example.com/director'\n"
        "      username: 'dir'\n"
        '      password: !env DIR_PW\n'
        '    tsdb:\n'
        "      type: 'influxdb'\n"
        "      url: 'http://influxdb.example.com:8086'\n"
        "      org: 'linuxfabrik'\n"
        "      bucket: 'icinga'\n"
        '      token: !env TSDB_TOKEN\n'
        'monitoring_plugins:\n'
        "  catalog_path: '/opt/lf/monitoring-plugins/check-plugins'\n"
    )
    config = load_config(cfg)
    inst = config.instances['prod']
    assert inst.icinga2_core is not None
    assert inst.icinga2_core.write_password is not None
    assert (
        inst.icinga2_core.write_password.get_secret_value() == 'value-of-CORE_WRITE_PW'
    )
    assert inst.icinga2_core.verify_tls is False
    assert inst.icinga2_core.timeout == 12
    assert isinstance(inst.tsdb, InfluxDBConfig)
    assert inst.tsdb.bucket == 'icinga'
    assert config.monitoring_plugins.catalog_path == Path(
        '/opt/lf/monitoring-plugins/check-plugins'
    )


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text("nonsense_key: 'whatever'\n")
    with pytest.raises(ConfigError, match='nonsense_key'):
        load_config(cfg)


def test_old_flat_schema_rejected(tmp_path: Path) -> None:
    """The pre-instances flat layout must fail clearly, not silently."""
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'icinga2_core:\n'
        "  url: 'https://icinga.example.com:5665'\n"
        "  username: 'mcp'\n"
        "  password: 'linuxfabrik'\n"
    )
    with pytest.raises(ConfigError, match='icinga2_core'):
        load_config(cfg)


def test_missing_required_field_clear_error(tmp_path: Path) -> None:
    cfg = tmp_path / 'config.yaml'
    cfg.write_text(
        'instances:\n'
        '  prod:\n'
        '    icinga2_core:\n'
        "      url: 'https://icinga.example.com:5665'\n"
        "      username: 'mcp'\n"
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
    cfg.write_text("instances:\n  prod:\n    icinga2_core:\n      url: 'broken\n")
    with pytest.raises(ConfigError, match='YAML error'):
        load_config(cfg)


def test_load_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match='not found'):
        load_config(tmp_path / 'nope.yaml')


# ---------------------------------------------------------------------------
# Bundled example config validates
# ---------------------------------------------------------------------------


def test_bundled_example_validates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The shipped examples/config.example.yaml must parse cleanly.

    The example references env vars and !file paths; we substitute the
    !file paths in a copy and inject placeholder env vars.
    """
    for name in (
        'ICINGA_WEB_PROD_ZH_PASSWORD',
        'ICINGA_DIRECTOR_PROD_ZH_PASSWORD',
        'INFLUXDB_PROD_ZH_TOKEN',
        'ICINGA_WEB_PROD_FR_PASSWORD',
        'ICINGA_DIRECTOR_PROD_FR_PASSWORD',
        'INFLUXDB_PROD_FR_TOKEN',
        'ICINGA2_STG_PASSWORD',
    ):
        monkeypatch.setenv(name, 'placeholder')

    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / 'examples' / 'config.example.yaml'
    text = example.read_text(encoding='utf-8')

    # Replace the !file references in the example (which point at runtime
    # credential paths that do not exist on the test host) with !file
    # references to a real fixture file.
    secret_file = tmp_path / 'fixture-password'
    secret_file.write_text('fixture\n', encoding='utf-8')
    text = re.sub(
        r'!file /run/credentials/mcp-server-icinga/[A-Za-z0-9_-]+',
        f'!file {secret_file}',
        text,
    )
    test_copy = tmp_path / 'config.yaml'
    test_copy.write_text(text, encoding='utf-8')

    config = load_config(test_copy)
    assert set(config.instances.keys()) == {'prod-zh', 'prod-fr', 'staging'}
    assert config.instances['prod-zh'].icinga2_core is not None
    assert config.instances['prod-zh'].icinga_web is not None
    assert config.instances['prod-zh'].icinga_director is not None
    assert isinstance(config.instances['prod-zh'].tsdb, InfluxDBConfig)
    assert config.monitoring_plugins.catalog_path is not None


# ---------------------------------------------------------------------------
# Sanity: _SYSTEM_PATH constant points where it should
# ---------------------------------------------------------------------------


def test_system_path_constant() -> None:
    assert Path('/etc/mcp-server-icinga/config.yaml') == _SYSTEM_PATH
