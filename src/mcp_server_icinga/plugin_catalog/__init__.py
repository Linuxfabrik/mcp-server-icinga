# SPDX-License-Identifier: Unlicense

"""Linuxfabrik monitoring-plugins catalog: schema, parser, loader.

The catalog is a static, queryable description of every plugin in the
`monitoring-plugins` repository: its argparse arguments, perfdata metrics,
state rules, Icinga Director command mapping and general metadata.

Two sources are planned:

- **live** - walk a local `check-plugins/` directory at startup; used in dev
  when `monitoring_plugins.catalog_path` is configured.
- **bundled-snapshot** - JSON file shipped with the package, regenerated at
  each release. Not yet implemented; Phase 3b.
"""

from mcp_server_icinga.plugin_catalog.loader import load_from_path
from mcp_server_icinga.plugin_catalog.schema import (
    Catalog,
    PluginArg,
    PluginCatalogEntry,
    PluginPerfdata,
    PluginStateRule,
)

__all__ = [
    'Catalog',
    'PluginArg',
    'PluginCatalogEntry',
    'PluginPerfdata',
    'PluginStateRule',
    'load_from_path',
]
