# SPDX-License-Identifier: Unlicense

"""Catalog loader: walk a `check-plugins/` directory and build a `Catalog`."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from mcp_server_icinga.plugin_catalog.parser import parse_plugin
from mcp_server_icinga.plugin_catalog.schema import Catalog, PluginCatalogEntry


def load_from_path(check_plugins_dir: Path | str) -> Catalog:
    """Walk `check_plugins_dir` and build a `Catalog` from every plugin found.

    Plugins that fail to parse are skipped with a stderr warning so a single
    malformed plugin does not poison the entire catalog.
    """
    check_plugins = Path(check_plugins_dir).resolve()
    if not check_plugins.is_dir():
        raise FileNotFoundError(f'check-plugins directory not found: {check_plugins}')

    repo_root = check_plugins.parent
    plugins: dict[str, PluginCatalogEntry] = {}

    for plugin_dir in sorted(check_plugins.iterdir()):
        if not plugin_dir.is_dir():
            continue
        name = plugin_dir.name
        source = plugin_dir / name
        if not source.is_file():
            # Not a standard plugin layout; skip silently. Common for
            # readme-only or asset-only folders.
            continue
        try:
            plugins[name] = parse_plugin(plugin_dir, repo_root)
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            print(
                f'plugin_catalog: skipping {name}: {type(exc).__name__}: {exc}',
                file=sys.stderr,
            )

    return Catalog(
        source='live',
        built_at=datetime.now(UTC).isoformat(timespec='seconds'),
        monitoring_plugins_ref=None,
        plugins=plugins,
    )
