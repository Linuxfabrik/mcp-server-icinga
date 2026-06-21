# SPDX-License-Identifier: Unlicense

"""Configuration loading and validation.

The configuration is a YAML file that describes one or more Icinga
deployments ("instances") the MCP server can talk to, plus the global
Linuxfabrik monitoring-plugins catalog. Each instance is a tenant- or
site-shaped grouping of up to four backends: Icinga 2 Core REST API,
Icinga Web 2, Icinga Director and a time series database.

Secrets are not stored in the YAML itself. Two custom YAML tags resolve
them at load time:

- `!env VAR_NAME` reads the value from an environment variable. The MCP
  client (Claude Desktop, Claude Code, MCPO, ...) is expected to inject
  these into the server process when it spawns it.
- `!file /path/to/secret-file` reads the value from a file. Trailing
  newlines are stripped. Works with systemd `LoadCredential=`, Docker /
  Podman secrets, or any plain file with restricted permissions.

Lookup order for the config file (first match wins):

1. ``$ICINGA_MCP_CONFIG`` (explicit override)
2. ``$XDG_CONFIG_HOME/Linuxfabrik/mcp-server-icinga/config.yaml`` (default
   ``~/.config/Linuxfabrik/mcp-server-icinga/config.yaml``)
3. ``/etc/Linuxfabrik/mcp-server-icinga/config.yaml``

Every backend section inside an instance is independently optional. The
instances dict itself can be empty: a configuration without any instance
still loads cleanly and the server only registers the global tools
(`health_check`, plus the catalog tools when `monitoring_plugins.catalog_path`
is set).
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
# YAML loader with !env and !file resolution
# ---------------------------------------------------------------------------


class _SecretResolvingLoader(yaml.SafeLoader):
    """SafeLoader subclass that knows the `!env` and `!file` scalar tags."""


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


def _file_constructor(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> str:
    raw_path = loader.construct_scalar(node).strip()
    if not raw_path:
        raise ConfigError('!file tag requires a non-empty path')
    path = Path(raw_path)
    if not path.is_file():
        raise ConfigError(
            f'!file path does not exist or is not a regular file: {raw_path}'
        )
    try:
        # Trailing newline is stripped: systemd LoadCredential, Docker secrets
        # and `echo "secret" > file` all leave one behind, and a stray newline
        # in a token or password makes for confusing failures down the line.
        return path.read_text(encoding='utf-8').rstrip('\n')
    except OSError as exc:
        raise ConfigError(f'cannot read !file {raw_path}: {exc}') from exc


_SecretResolvingLoader.add_constructor('!env', _env_constructor)
_SecretResolvingLoader.add_constructor('!file', _file_constructor)


# ---------------------------------------------------------------------------
# Pydantic models: per-backend
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
    read-only tools for this backend on this instance.
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


# ---------------------------------------------------------------------------
# Pydantic models: per-instance and top level
# ---------------------------------------------------------------------------


class InstanceConfig(BaseModel):
    """One Icinga deployment (tenant, site, environment).

    All four backend sections are optional. An instance with only
    `icinga2_core` is valid; tools whose backend is absent on the
    targeted instance simply refuse with a clear error.
    """

    model_config = ConfigDict(extra='forbid')

    icinga2_core: Icinga2CoreConfig | None = None
    icinga_web: IcingaWebConfig | None = None
    icinga_director: IcingaDirectorConfig | None = None
    tsdb: TSDBConfig | None = None


class MonitoringPluginsConfig(BaseModel):
    """Linuxfabrik monitoring-plugins catalog source.

    Global, not per-instance: the same plugin catalog applies across every
    Icinga deployment the server talks to.

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

    instances: dict[str, InstanceConfig] = Field(default_factory=dict)
    """Map of instance name (e.g. `prod-zh`, `staging`) to backend config.
    May be empty, in which case the server only exposes global tools."""

    monitoring_plugins: MonitoringPluginsConfig = Field(
        default_factory=MonitoringPluginsConfig,
    )


# ---------------------------------------------------------------------------
# Lookup and load
# ---------------------------------------------------------------------------

_ENV_VAR = 'ICINGA_MCP_CONFIG'
_USER_RELATIVE = Path('Linuxfabrik') / 'mcp-server-icinga' / 'config.yaml'
_SYSTEM_PATH = Path('/etc/Linuxfabrik/mcp-server-icinga/config.yaml')


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
            # _SecretResolvingLoader is a SafeLoader subclass, so this is
            # equivalent to yaml.safe_load() plus the !env and !file
            # resolvers registered above.
            raw = yaml.load(fh, Loader=_SecretResolvingLoader)  # nosec B506
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
