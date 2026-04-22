# SPDX-License-Identifier: Unlicense

"""AST-based parser for a single monitoring plugin.

Deliberately static: no `import` of plugin source, no runtime introspection.
The parser operates on `ast.Module` trees and regex-based extraction of
README sections. That keeps the catalog loader free of any dependency on
`linuxfabrik-lib` or any plugin-specific runtime environment.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from mcp_server_icinga.plugin_catalog.schema import (
    PluginArg,
    PluginCatalogEntry,
    PluginPerfdata,
    PluginStateRule,
)


def parse_plugin(plugin_dir: Path, repo_root: Path) -> PluginCatalogEntry:
    """Parse one plugin directory into a `PluginCatalogEntry`.

    `plugin_dir` is the `check-plugins/<name>/` folder.
    `repo_root` is the monitoring-plugins root, used to build relative paths.
    """
    name = plugin_dir.name
    source = plugin_dir / name
    readme = plugin_dir / 'README.md'
    director_dir = plugin_dir / 'icingaweb2-module-director'

    source_text = source.read_text(encoding='utf-8')
    tree = ast.parse(source_text, filename=str(source))

    constants = _collect_top_level_constants(tree)
    version = _as_string(_find_top_level_value(tree, '__version__'))
    description = _as_string(_find_top_level_value(tree, 'DESCRIPTION'))
    args = _extract_argparse_args(tree, constants)

    readme_text = readme.read_text(encoding='utf-8') if readme.is_file() else ''
    fact_sheet = _parse_fact_sheet(readme_text)
    states = _parse_states(readme_text)
    perfdata = _parse_perfdata(readme_text)

    director_commands, director_prefix = _parse_director(director_dir, name)

    return PluginCatalogEntry(
        name=name,
        version=version,
        description=description,
        runs_on=fact_sheet.get('Runs on') or fact_sheet.get('Run on'),
        check_interval_recommendation=fact_sheet.get('Check Interval Recommendation'),
        can_be_called_without_parameters=fact_sheet.get(
            'Can be called without parameters'
        ),
        compiled_for_windows=fact_sheet.get('Compiled for Windows'),
        uses_state_file=fact_sheet.get('Uses State File'),
        args=args,
        perfdata=perfdata,
        states=states,
        director_check_commands=director_commands,
        director_vars_prefix=director_prefix,
        source_path=str(source.relative_to(repo_root)),
        readme_path=str(readme.relative_to(repo_root)) if readme.is_file() else None,
        has_windows_variant=(plugin_dir / f'{name}.windows').exists(),
        has_windows_python_variant=(plugin_dir / f'{name}.windows.python').exists(),
    )


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _find_top_level_value(tree: ast.Module, name: str) -> ast.AST | None:
    """Return the RHS AST node of `name = ...` at module top level."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return node.value
    return None


def _collect_top_level_constants(tree: ast.Module) -> dict[str, Any]:
    """Evaluate every `NAME = <literal>` at module top level.

    Used to resolve `default=DEFAULT_CRIT` style references inside
    `add_argument()` calls.
    """
    constants: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    value = _as_literal(node.value)
                    if value is not None:
                        constants[target.id] = value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            value = _as_literal(node.value)
            if value is not None:
                constants[node.target.id] = value
    return constants


def _as_literal(node: ast.AST | None) -> Any:
    """Evaluate an AST node as a Python literal, or return `None`."""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _as_string(node: ast.AST | None) -> str | None:
    """Evaluate an AST node as a string literal (including multi-line), else `None`."""
    value = _as_literal(node)
    if isinstance(value, str):
        return value.strip() or None
    return None


def _unparse(node: ast.AST | None) -> str | None:
    """Return `ast.unparse(node)` or `None`. Handles older Pythons defensively."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except AttributeError:
        return None


# ---------------------------------------------------------------------------
# argparse extraction
# ---------------------------------------------------------------------------


def _extract_argparse_args(
    tree: ast.Module, constants: dict[str, Any]
) -> list[PluginArg]:
    """Find every `parser.add_argument(...)` call and translate to PluginArg."""
    args: list[PluginArg] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != 'add_argument':
            continue

        flag_positions = [_as_literal(a) for a in node.args]
        flags = [f for f in flag_positions if isinstance(f, str) and f.startswith('-')]
        if not flags:
            continue
        long_flag = next((f for f in flags if f.startswith('--')), flags[0])
        short_flag = next(
            (f for f in flags if not f.startswith('--') and f.startswith('-')), None
        )

        kwargs: dict[str, ast.AST] = {}
        for kw in node.keywords:
            if kw.arg is not None:
                kwargs[kw.arg] = kw.value

        help_node = kwargs.get('help')
        help_literal = _as_string(help_node) if help_node is not None else None
        help_source = None if help_literal is not None else _unparse(help_node)

        default_node = kwargs.get('default')
        default_value = _as_literal(default_node)
        if default_value is None and isinstance(default_node, ast.Name):
            default_value = constants.get(default_node.id)

        type_node = kwargs.get('type')
        type_name: str | None = None
        if isinstance(type_node, ast.Name):
            type_name = type_node.id
        elif isinstance(type_node, ast.Attribute):
            type_name = _unparse(type_node)

        action_value = _as_literal(kwargs.get('action'))
        dest_value = _as_literal(kwargs.get('dest'))
        required_value = bool(_as_literal(kwargs.get('required')) or False)

        args.append(
            PluginArg(
                long_flag=long_flag,
                short_flag=short_flag,
                dest=dest_value if isinstance(dest_value, str) else None,
                help=help_literal,
                help_source=help_source,
                default=default_value,
                type=type_name,
                action=action_value if isinstance(action_value, str) else None,
                required=required_value,
            )
        )
    return args


# ---------------------------------------------------------------------------
# README parsing
# ---------------------------------------------------------------------------


def _extract_section(readme: str, heading: str) -> str:
    """Return the body below `## <heading>` up to the next heading at any level."""
    pattern = rf'^##\s+{re.escape(heading)}\s*\n(.*?)(?=^#{{1,6}}\s|\Z)'
    match = re.search(pattern, readme, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ''


def _parse_fact_sheet(readme: str) -> dict[str, str]:
    """Parse the `## Fact Sheet` table into a key -> value dict."""
    body = _extract_section(readme, 'Fact Sheet')
    if not body:
        return {}
    facts: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('|') or not line.endswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) != 2:
            continue
        key, value = cells
        if key.lower() == 'fact' or set(key) <= {'-', ':', ' '}:
            continue  # table header or separator
        facts[key] = value
    return facts


def _parse_states(readme: str) -> list[PluginStateRule]:
    """Parse the `## States` bulleted list into `PluginStateRule`s."""
    body = _extract_section(readme, 'States')
    if not body:
        return []
    rules: list[PluginStateRule] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith('*'):
            continue
        text = stripped.lstrip('*').strip()
        state = _classify_state(text)
        rules.append(PluginStateRule(state=state, condition=text))
    return rules


_STATE_KEYWORDS = {
    'OK': re.compile(r'\bOK\b', re.IGNORECASE),
    'WARN': re.compile(r'\b(WARN(ING)?)\b', re.IGNORECASE),
    'CRIT': re.compile(r'\b(CRIT(ICAL)?)\b', re.IGNORECASE),
    'UNKNOWN': re.compile(r'\bUNKNOWN\b', re.IGNORECASE),
}


def _classify_state(condition: str) -> str:
    """Best-effort state classification from the rule's first few words."""
    head = condition.split('.', 1)[0][:80]
    for state, pattern in _STATE_KEYWORDS.items():
        if pattern.search(head):
            return state
    return 'OTHER'


def _parse_perfdata(readme: str) -> list[PluginPerfdata]:
    """Parse the `## Perfdata / Metrics` table into PluginPerfdata rows."""
    body = _extract_section(readme, 'Perfdata / Metrics')
    if not body:
        return []
    rows: list[PluginPerfdata] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith('|') or not line.endswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) != 3:
            continue
        name, ptype, description = cells
        if name.lower() == 'name' or set(name) <= {'-', ':', ' '}:
            continue
        rows.append(
            PluginPerfdata(
                name=name,
                type=ptype or None,
                description=description or None,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Director basket JSON
# ---------------------------------------------------------------------------


def _parse_director(
    director_dir: Path, plugin_name: str
) -> tuple[list[str], str | None]:
    """Extract command names and varname prefix from all *.json baskets in
    `icingaweb2-module-director/`."""
    if not director_dir.is_dir():
        return [], None

    commands: list[str] = []
    prefix: str | None = None

    for json_file in sorted(director_dir.glob('*.json')):
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for cmd_name in data.get('Command') or {}:
            if cmd_name not in commands:
                commands.append(cmd_name)
        if prefix is None:
            for df in (data.get('Datafield') or {}).values():
                varname = df.get('varname', '') if isinstance(df, dict) else ''
                if varname:
                    # Prefix is everything up to the trailing '_<optionname>'. As a
                    # stable heuristic we use the plugin name with hyphens replaced
                    # by underscores, which is the Linuxfabrik convention.
                    prefix = plugin_name.replace('-', '_')
                    break
    return commands, prefix
