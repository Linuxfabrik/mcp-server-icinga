# SPDX-License-Identifier: Unlicense

"""Tests for `mcp_server_icinga.plugin_catalog`.

The tests load the actual Linuxfabrik `monitoring-plugins` checkout the
developer has on disk. This validates the parser against real plugins
rather than synthetic samples. The checkout is discovered relative to this
repository; when it is not present the tests are skipped with a clear
reason so the suite still runs on a clean clone of mcp-server-icinga.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server_icinga.plugin_catalog import Catalog, load_from_path
from mcp_server_icinga.plugin_catalog.parser import (
    _classify_state,
    _parse_fact_sheet,
    _parse_perfdata,
    _parse_states,
)

_REPO_CANDIDATES = [
    Path('/home/markusfrei/git/linuxfabrik/github/monitoring-plugins'),
    Path(__file__).resolve().parents[2] / 'monitoring-plugins',
]


def _find_monitoring_plugins() -> Path | None:
    for candidate in _REPO_CANDIDATES:
        check_plugins = candidate / 'check-plugins'
        if check_plugins.is_dir():
            return check_plugins
    return None


@pytest.fixture(scope='module')
def live_catalog() -> Catalog:
    check_plugins = _find_monitoring_plugins()
    if check_plugins is None:
        pytest.skip(
            'No local monitoring-plugins checkout found; this test needs '
            'the repository at one of the well-known dev paths.'
        )
    return load_from_path(check_plugins)


# ---------------------------------------------------------------------------
# Catalog-level smoke tests
# ---------------------------------------------------------------------------


def test_catalog_loads_many_plugins(live_catalog: Catalog) -> None:
    assert live_catalog.source == 'live'
    assert live_catalog.built_at is not None
    # The real repo has ~230+ plugins; we use 150 as a conservative floor.
    assert len(live_catalog.plugins) >= 150


def test_catalog_has_known_plugins(live_catalog: Catalog) -> None:
    for expected in ('gitlab-version', 'disk-usage', 'mailq', 'load', 'procs'):
        assert expected in live_catalog.plugins, f'missing {expected} in catalog'


# ---------------------------------------------------------------------------
# gitlab-version is our reference plugin - use it to validate every field
# ---------------------------------------------------------------------------


def test_gitlab_version_metadata(live_catalog: Catalog) -> None:
    entry = live_catalog.plugins['gitlab-version']
    assert entry.name == 'gitlab-version'
    assert entry.version is not None
    assert entry.version.isdigit()
    assert entry.description is not None
    assert 'GitLab' in entry.description
    assert entry.runs_on == 'Cross-platform'
    assert entry.source_path.startswith('check-plugins/gitlab-version/')


def test_gitlab_version_argparse(live_catalog: Catalog) -> None:
    entry = live_catalog.plugins['gitlab-version']
    flags = {a.long_flag for a in entry.args}
    # These flags all land via plain add_argument calls in the source.
    assert {
        '--check-major',
        '--check-minor',
        '--check-patch',
        '--check-security',
        '--insecure',
        '--no-proxy',
        '--offset-eol',
        '--path',
        '--timeout',
    } <= flags


def test_gitlab_version_director_mapping(live_catalog: Catalog) -> None:
    entry = live_catalog.plugins['gitlab-version']
    assert entry.director_check_commands == ['cmd-check-gitlab-version']
    assert entry.director_vars_prefix == 'gitlab_version'


def test_gitlab_version_states(live_catalog: Catalog) -> None:
    entry = live_catalog.plugins['gitlab-version']
    states = {s.state for s in entry.states}
    # The README documents at least OK, WARN and UNKNOWN paths.
    assert 'OK' in states
    assert 'WARN' in states
    assert 'UNKNOWN' in states


def test_gitlab_version_perfdata(live_catalog: Catalog) -> None:
    entry = live_catalog.plugins['gitlab-version']
    names = [p.name for p in entry.perfdata]
    assert 'gitlab-version' in names


# ---------------------------------------------------------------------------
# Unit tests on the README-section parsers (no repo needed)
# ---------------------------------------------------------------------------


def test_parse_fact_sheet_simple() -> None:
    readme = """## Fact Sheet

| Fact | Value |
|----|----|
| Runs on   | Cross-platform |
| Compiled for Windows | No |

## Other
"""
    facts = _parse_fact_sheet(readme)
    assert facts['Runs on'] == 'Cross-platform'
    assert facts['Compiled for Windows'] == 'No'


def test_parse_states_classifies_correctly() -> None:
    readme = """## States

* OK if nothing is wrong.
* WARN if thresholds are breached.
* CRIT if a hard limit is hit.
* UNKNOWN if the plugin cannot determine state.

## Next
"""
    states = _parse_states(readme)
    assert [s.state for s in states] == ['OK', 'WARN', 'CRIT', 'UNKNOWN']


def test_parse_perfdata_table() -> None:
    readme = """## Perfdata / Metrics

| Name | Type | Description |
|----|----|----|
| count | Number | Count of widgets |
| usage_pct | Percentage | Disk usage |

## Next
"""
    rows = _parse_perfdata(readme)
    assert len(rows) == 2
    assert rows[0].name == 'count'
    assert rows[0].type == 'Number'
    assert rows[1].name == 'usage_pct'


def test_classify_state_fallback() -> None:
    assert _classify_state('OK when empty.') == 'OK'
    assert _classify_state('warn if something.') == 'WARN'
    assert _classify_state('critical if broken.') == 'CRIT'
    assert _classify_state('unknown when unreachable.') == 'UNKNOWN'
    assert _classify_state('something else entirely') == 'OTHER'


# ---------------------------------------------------------------------------
# Loader error handling
# ---------------------------------------------------------------------------


def test_load_from_path_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_from_path(tmp_path / 'does-not-exist')


# ---------------------------------------------------------------------------
# read_plugin_source helper
# ---------------------------------------------------------------------------

_SAMPLE_PLUGIN = """\
#!/usr/bin/env python3
DESCRIPTION = 'sample'


def helper():
    return 1


def main():
    return helper()
"""


def _catalog_with_source(tmp_path: Path) -> tuple[Catalog, Path]:
    """Build a one-plugin catalog backed by a real file under tmp_path."""
    from mcp_server_icinga.plugin_catalog.schema import PluginCatalogEntry

    source_file = tmp_path / 'check-plugins' / 'sample' / 'sample'
    source_file.parent.mkdir(parents=True)
    source_file.write_text(_SAMPLE_PLUGIN, encoding='utf-8')
    entry = PluginCatalogEntry(name='sample', source_path='check-plugins/sample/sample')
    return Catalog(source='live', plugins={'sample': entry}), tmp_path


def test_read_plugin_source_whole_file(tmp_path: Path) -> None:
    from mcp_server_icinga.server import _read_plugin_source_payload

    catalog, base = _catalog_with_source(tmp_path)
    result = _read_plugin_source_payload(catalog, base, 'sample')
    assert result['name'] == 'sample'
    assert result['source_path'] == 'check-plugins/sample/sample'
    assert 'def main():' in result['source']
    assert result['line_count'] == _SAMPLE_PLUGIN.count('\n') + 1
    assert 'function' not in result


def test_read_plugin_source_single_function(tmp_path: Path) -> None:
    from mcp_server_icinga.server import _read_plugin_source_payload

    catalog, base = _catalog_with_source(tmp_path)
    result = _read_plugin_source_payload(catalog, base, 'sample', function='main')
    assert result['function'] == 'main'
    assert result['source'].startswith('def main():')
    assert 'def helper():' not in result['source']


def test_read_plugin_source_unknown_function_lists_available(tmp_path: Path) -> None:
    from mcp_server_icinga.server import _read_plugin_source_payload

    catalog, base = _catalog_with_source(tmp_path)
    with pytest.raises(ValueError, match='helper, main'):
        _read_plugin_source_payload(catalog, base, 'sample', function='nope')


def test_read_plugin_source_unknown_plugin(tmp_path: Path) -> None:
    from mcp_server_icinga.server import _read_plugin_source_payload

    catalog, base = _catalog_with_source(tmp_path)
    with pytest.raises(ValueError, match='unknown plugin'):
        _read_plugin_source_payload(catalog, base, 'ghost')


def test_read_plugin_source_requires_local_catalog(tmp_path: Path) -> None:
    from mcp_server_icinga.server import _read_plugin_source_payload

    catalog, _base = _catalog_with_source(tmp_path)
    with pytest.raises(ValueError, match='requires a local catalog'):
        _read_plugin_source_payload(catalog, None, 'sample')
