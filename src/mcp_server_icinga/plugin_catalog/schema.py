# SPDX-License-Identifier: Unlicense

"""Pydantic schema for the Linuxfabrik monitoring-plugins catalog."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PluginArg(BaseModel):
    """A single argparse argument of a plugin."""

    model_config = ConfigDict(extra='forbid')

    long_flag: str
    """The canonical long flag, e.g. `--warning`. Always present."""

    short_flag: str | None = None
    """The short flag, e.g. `-w`, when the plugin defines one."""

    dest: str | None = None
    """Argparse `dest` for this argument."""

    help: str | None = None
    """Help text. `None` when the plugin uses a helper call
    (`lib.args.help(...)`) that the AST parser cannot resolve in isolation."""

    help_source: str | None = None
    """Raw AST dump of the help expression when it was not a literal.
    Useful for Phase 3b when we add `lib.args.HELP_TEXTS` resolution."""

    default: Any = None
    """Default value, when expressible as a Python literal."""

    type: str | None = None
    """Type callable name as a string (`int`, `str`, ...). `None` when the
    callable is a helper the AST parser cannot resolve."""

    action: str | None = None
    """Argparse `action`, e.g. `store`, `store_true`, `append`."""

    required: bool = False


class PluginPerfdata(BaseModel):
    """A perfdata metric a plugin emits."""

    model_config = ConfigDict(extra='forbid')

    name: str
    type: str | None = None
    description: str | None = None


class PluginStateRule(BaseModel):
    """A state transition rule extracted from the `States` README section."""

    model_config = ConfigDict(extra='forbid')

    state: str
    """`OK`, `WARN`, `CRIT`, `UNKNOWN` or another token the README uses."""

    condition: str
    """The rule text as written in the README."""


class PluginCatalogEntry(BaseModel):
    """Catalog record for one monitoring plugin."""

    model_config = ConfigDict(extra='forbid')

    name: str
    """Plugin directory name, e.g. `gitlab-version`."""

    version: str | None = None
    """Plugin `__version__`, e.g. `'2026041901'`."""

    description: str | None = None
    """Value of the `DESCRIPTION` module constant."""

    runs_on: str | None = None
    """From the README Fact Sheet: `Cross-platform` / `Linux` / `Windows`."""

    check_interval_recommendation: str | None = None
    """From the README Fact Sheet."""

    can_be_called_without_parameters: str | None = None
    """From the README Fact Sheet."""

    compiled_for_windows: str | None = None
    """From the README Fact Sheet."""

    uses_state_file: str | None = None
    """Raw Fact Sheet value if set, e.g. `$TEMP/linuxfabrik-...db`."""

    args: list[PluginArg] = Field(default_factory=list)
    perfdata: list[PluginPerfdata] = Field(default_factory=list)
    states: list[PluginStateRule] = Field(default_factory=list)

    director_check_commands: list[str] = Field(default_factory=list)
    """All Icinga Director command object names associated with this plugin,
    e.g. `['cmd-check-gitlab-version']`. Empty when no Director basket ships."""

    director_vars_prefix: str | None = None
    """Varname prefix used by the Director service template, e.g.
    `gitlab_version` for vars like `gitlab_version_check_major`."""

    source_path: str
    """Relative path of the plugin source within the monitoring-plugins tree,
    e.g. `check-plugins/gitlab-version/gitlab-version`."""

    readme_path: str | None = None

    has_windows_variant: bool = False
    """True when `<name>.windows` (PowerShell) ships next to the plugin."""

    has_windows_python_variant: bool = False
    """True when `<name>.windows.python` ships."""


class Catalog(BaseModel):
    """The full plugin catalog plus provenance metadata."""

    model_config = ConfigDict(extra='forbid')

    source: str
    """`live` or `bundled-snapshot`."""

    built_at: str | None = None
    """ISO 8601 timestamp when the catalog was materialised."""

    monitoring_plugins_ref: str | None = None
    """Git ref the snapshot was built from, when the catalog is bundled.
    `None` for live catalogs."""

    plugins: dict[str, PluginCatalogEntry] = Field(default_factory=dict)
    """Plugin name -> catalog entry."""
