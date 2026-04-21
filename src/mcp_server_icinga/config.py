# SPDX-License-Identifier: Unlicense

"""Configuration loading and validation.

The configuration is a YAML file that describes the topology of all backends
the MCP server can talk to (Icinga 2 Core, Icinga Web, Icinga Director, the
TSDB and the local monitoring-plugins catalog). Secrets are not stored in the
YAML itself; they are referenced via the `!env VAR_NAME` tag and resolved
from environment variables at load time.

Lookup order for the config file (first match wins):

1. ``$ICINGA_MCP_CONFIG`` (explicit override)
2. ``$XDG_CONFIG_HOME/mcp-server-icinga/config.yaml`` (default
   ``~/.config/mcp-server-icinga/config.yaml``)
3. ``/etc/mcp-server-icinga/config.yaml``

Every backend section is optional. Tools whose backend is absent simply do
not get registered with the MCP server, so a read-only deployment that only
talks to Icinga 2 Core works without ever configuring Icinga Director or
the TSDB.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, ValidationError


class ConfigError(Exception):
    """Raised when the configuration cannot be located, parsed or validated."""


# ---------------------------------------------------------------------------
# YAML loader with `!env VAR_NAME` resolution
# ---------------------------------------------------------------------------


class _EnvLoader(yaml.SafeLoader):
    """SafeLoader subclass that knows the `!env` scalar tag."""


def _env_constructor(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> str:
    var_name = loader.construct_scalar(node).strip()
    if not var_name:
        raise ConfigError('!env tag requires an environment variable name')
    value = os.environ.get(var_name)
    if value is None:
        raise ConfigError(
            f'environment variable {var_name!r} is referenced via !env but not set'
        )
    return value


_EnvLoader.add_constructor('!env', _env_constructor)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class _BackendBase(BaseModel):
    """Common fields for every Icinga REST backend."""

    model_config = ConfigDict(extra='forbid')

    url: HttpUrl
    username: str = Field(min_length=1)
    password: SecretStr
    verify_tls: bool = True
    ca_bundle: Path | None = None
    timeout: int = Field(default=8, ge=1, le=300)


class Icinga2CoreConfig(_BackendBase):
    """Icinga 2 Core REST API on port 5665.

    Optional `write_username` / `write_password` enable mutating tools
    (acknowledge, downtime, reschedule). When unset the server only registers
    read-only tools for this backend.
    """

    write_username: str | None = None
    write_password: SecretStr | None = None


class IcingaWebConfig(_BackendBase):
    """Icinga Web 2 with the Icinga DB Web module."""


class IcingaDirectorConfig(_BackendBase):
    """Icinga Director module of Icinga Web 2."""


class InfluxDBConfig(BaseModel):
    """InfluxDB 2.x time series backend for historical perfdata."""

    model_config = ConfigDict(extra='forbid')

    type: Literal['influxdb']
    url: HttpUrl
    org: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    token: SecretStr
    verify_tls: bool = True
    ca_bundle: Path | None = None
    timeout: int = Field(default=8, ge=1, le=300)


# Discriminated union: future TSDB backends (Prometheus, Graphite, ...) plug
# in here as additional members keyed by `type`.
TSDBConfig = Annotated[InfluxDBConfig, Field(discriminator='type')]


class MonitoringPluginsConfig(BaseModel):
    """Linuxfabrik monitoring-plugins catalog source.

    `catalog_path` points at a local checkout of the
    https://github.com/Linuxfabrik/monitoring-plugins repo (the
    `check-plugins` directory). When unset the server falls back to the JSON
    snapshot bundled with the package.
    """

    model_config = ConfigDict(extra='forbid')

    catalog_path: Path | None = None


class Config(BaseModel):
    """Top-level configuration for `mcp-server-icinga`."""

    model_config = ConfigDict(extra='forbid')

    icinga2_core: Icinga2CoreConfig | None = None
    icinga_web: IcingaWebConfig | None = None
    icinga_director: IcingaDirectorConfig | None = None
    tsdb: TSDBConfig | None = None
    monitoring_plugins: MonitoringPluginsConfig = Field(
        default_factory=MonitoringPluginsConfig,
    )


# ---------------------------------------------------------------------------
# Lookup and load
# ---------------------------------------------------------------------------

_ENV_VAR = 'ICINGA_MCP_CONFIG'
_USER_RELATIVE = Path('mcp-server-icinga') / 'config.yaml'
_SYSTEM_PATH = Path('/etc/mcp-server-icinga/config.yaml')


def _user_config_path() -> Path:
    xdg = os.environ.get('XDG_CONFIG_HOME')
    base = Path(xdg) if xdg else Path.home() / '.config'
    return base / _USER_RELATIVE


def find_config_path() -> Path:
    """Return the path to the config file according to the lookup order.

    Raises `ConfigError` if no candidate file exists.
    """
    explicit = os.environ.get(_ENV_VAR)
    if explicit:
        return Path(explicit)

    user_path = _user_config_path()
    if user_path.is_file():
        return user_path

    if _SYSTEM_PATH.is_file():
        return _SYSTEM_PATH

    raise ConfigError(
        f'no config file found. Set {_ENV_VAR}, or create {user_path} or {_SYSTEM_PATH}'
    )


def load_config(path: Path | str | None = None) -> Config:
    """Load and validate the YAML config from `path` or via the lookup order."""
    config_path = Path(path) if path is not None else find_config_path()

    if not config_path.is_file():
        raise ConfigError(f'config file not found: {config_path}')

    try:
        with config_path.open(encoding='utf-8') as fh:
            # _EnvLoader is a SafeLoader subclass, so this is equivalent to
            # yaml.safe_load() plus the !env tag resolver registered above.
            raw = yaml.load(fh, Loader=_EnvLoader)  # nosec B506
    except yaml.YAMLError as exc:
        raise ConfigError(f'YAML error in {config_path}: {exc}') from exc

    if raw is None:
        raw = {}

    if not isinstance(raw, dict):
        raise ConfigError(
            f'top-level YAML in {config_path} must be a mapping, got {type(raw).__name__}'
        )

    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f'invalid config in {config_path}:\n{exc}') from exc
