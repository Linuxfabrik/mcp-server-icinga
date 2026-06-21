# SPDX-License-Identifier: Unlicense

"""Synchronous client for the Icinga 2 Core REST API (port 5665).

The client wraps the object-query endpoints (`/v1/objects/hosts`,
`/v1/objects/services`) that the read-only MCP tools build on. It follows
the Icinga best practice of issuing a `POST` with the
`X-HTTP-Method-Override: GET` header and passing the filter in the request
body via `filter` plus `filter_vars`. Parameter binding through
`filter_vars` keeps user-supplied values (host names, search patterns) out
of the filter string, so there is no DSL escaping to get wrong.

Only read access is implemented here. Mutating actions (acknowledge,
schedule-downtime, reschedule-check) live behind the optional write
credentials and are added separately.

The state-code mappings are verified against the Icinga 2 source
(`lib/icinga/checkresult.ti`): host states `Up=0`, `Down=1`; service
states `OK=0`, `Warning=1`, `Critical=2`, `Unknown=3`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from mcp_server_icinga.config import Icinga2CoreConfig

# Numeric state codes to human-readable labels.
HOST_STATES: dict[int, str] = {0: 'UP', 1: 'DOWN'}
SERVICE_STATES: dict[int, str] = {0: 'OK', 1: 'WARNING', 2: 'CRITICAL', 3: 'UNKNOWN'}
STATE_TYPES: dict[int, str] = {0: 'SOFT', 1: 'HARD'}

# Reverse maps, used to translate a caller-supplied state label into the
# numeric code an Icinga filter expression compares against.
HOST_STATE_CODES: dict[str, int] = {label: code for code, label in HOST_STATES.items()}
SERVICE_STATE_CODES: dict[str, int] = {
    label: code for code, label in SERVICE_STATES.items()
}

# Curated attribute lists keep the response small and the summaries stable
# regardless of how much Icinga would return by default.
_HOST_ATTRS = [
    'acknowledgement',
    'address',
    'address6',
    'display_name',
    'downtime_depth',
    'last_check',
    'last_check_result',
    'last_state_change',
    'name',
    'next_check',
    'state',
    'state_type',
]
_SERVICE_ATTRS = [
    'acknowledgement',
    'check_command',
    'display_name',
    'downtime_depth',
    'host_name',
    'last_check',
    'last_check_result',
    'last_state_change',
    'name',
    'next_check',
    'state',
    'state_type',
]
# Pull the host context along with each service so a service problem can be
# read without a second round trip.
_SERVICE_JOINS = ['host.display_name', 'host.name', 'host.state']


class Icinga2CoreError(Exception):
    """Base error for all Icinga 2 Core REST API interactions."""


class Icinga2CoreAuthError(Icinga2CoreError):
    """Authentication or authorization failed (HTTP 401 or 403)."""


class Icinga2CoreNotFoundError(Icinga2CoreError):
    """The requested object does not exist."""


class Icinga2CoreClient:
    """Access to one Icinga 2 Core REST API endpoint.

    Queries always use the read credentials. Actions (acknowledge, schedule
    or remove a downtime, reschedule a check) use the separate write
    credentials and are only possible when those are configured;
    `write_author` is the identity actions are attributed to.
    """

    def __init__(
        self,
        config: Icinga2CoreConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = str(config.url).rstrip('/')
        self._auth = (config.username, config.password.get_secret_value())
        # httpx `verify` accepts either a bool or a path to a CA bundle.
        self._verify: bool | str = (
            str(config.ca_bundle) if config.ca_bundle else config.verify_tls
        )
        self._timeout = config.timeout
        # Injectable transport is the test seam: production code passes None
        # and gets a real network transport.
        self._transport = transport

        if config.write_password is not None:
            author = config.write_username or config.username
            self._write_auth: tuple[str, str] | None = (
                author,
                config.write_password.get_secret_value(),
            )
            self.write_author: str | None = author
        else:
            self._write_auth = None
            self.write_author = None

    def query_hosts(
        self,
        *,
        filter: str | None = None,
        filter_vars: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw Host object-query results, with the curated attrs."""
        return self._query(
            'hosts', filter=filter, filter_vars=filter_vars, attrs=_HOST_ATTRS
        )

    def query_services(
        self,
        *,
        filter: str | None = None,
        filter_vars: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw Service object-query results, joined with their host."""
        return self._query(
            'services',
            filter=filter,
            filter_vars=filter_vars,
            attrs=_SERVICE_ATTRS,
            joins=_SERVICE_JOINS,
        )

    def run_action(self, action: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        """POST to `/v1/actions/<action>` with the write credentials.

        Returns the per-object `results` list (each item carries a `code` and
        a `status` message). Raises `Icinga2CoreNotFoundError` when the filter
        matches no object (HTTP 404).
        """
        if self._write_auth is None:
            raise Icinga2CoreError(
                'this instance has no write credentials configured; '
                'set write_username / write_password to enable actions'
            )
        url = f'{self._base_url}/v1/actions/{action}'
        response = self._post(
            url, self._write_auth, {'Accept': 'application/json'}, body
        )
        self._raise_for_status(response, url, missing_is_empty=False)
        return self._results(response, url)

    # -- low level ---------------------------------------------------------

    def _query(
        self,
        object_type: str,
        *,
        filter: str | None,
        filter_vars: dict[str, Any] | None,
        attrs: list[str],
        joins: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {'attrs': attrs}
        if filter is not None:
            body['filter'] = filter
        if filter_vars:
            body['filter_vars'] = filter_vars
        if joins:
            body['joins'] = joins

        url = f'{self._base_url}/v1/objects/{object_type}'
        headers = {
            'Accept': 'application/json',
            # GET requests carry no body, so override the method on a POST.
            'X-HTTP-Method-Override': 'GET',
        }
        response = self._post(url, self._auth, headers, body)
        # A filtered query that matches nothing returns 200 with an empty
        # results array; a 404 only happens when nothing matches at all, so
        # treat it the same as "no results" and let the caller decide.
        if self._raise_for_status(response, url, missing_is_empty=True):
            return []
        return self._results(response, url)

    def _post(
        self,
        url: str,
        auth: tuple[str, str],
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> httpx.Response:
        try:
            with httpx.Client(
                auth=auth,
                verify=self._verify,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                return client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise Icinga2CoreError(f'request to {url} failed: {exc}') from exc

    def _raise_for_status(
        self, response: httpx.Response, url: str, *, missing_is_empty: bool
    ) -> bool:
        """Map error status codes to exceptions.

        Returns `True` only when the response is a 404 and the caller treats a
        missing match as an empty result (queries); for actions a 404 means
        the filter matched no object and is raised as a not-found error.
        """
        if response.status_code in (401, 403):
            raise Icinga2CoreAuthError(
                f'authentication failed for {self._base_url} '
                f'(HTTP {response.status_code}); check the configured credentials '
                f'and the ApiUser permissions'
            )
        if response.status_code == 404:
            if missing_is_empty:
                return True
            raise Icinga2CoreNotFoundError(
                f'no object matched the request to {url}: {_error_detail(response)}'
            )
        if response.status_code >= 400:
            raise Icinga2CoreError(
                f'Icinga 2 Core API error {response.status_code} for {url}: '
                f'{_error_detail(response)}'
            )
        return False

    def _results(self, response: httpx.Response, url: str) -> list[dict[str, Any]]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise Icinga2CoreError(
                f'Icinga 2 Core API returned non-JSON response for {url}'
            ) from exc
        results = payload.get('results', [])
        if not isinstance(results, list):
            raise Icinga2CoreError(
                f'unexpected response shape from {url}: "results" is not a list'
            )
        return results


def _error_detail(response: httpx.Response) -> str:
    """Best-effort extraction of an Icinga error message from a response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200] if response.text else '<no body>'
    if isinstance(payload, dict):
        for key in ('status', 'error'):
            value = payload.get(key)
            if value:
                return str(value)
    return str(payload)[:200]


# ---------------------------------------------------------------------------
# Result summarisers
# ---------------------------------------------------------------------------


def _iso(timestamp: Any) -> str | None:
    """Render an Icinga unix timestamp as a UTC ISO 8601 string."""
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _decode(mapping: dict[int, str], value: Any) -> Any:
    """Translate a numeric state code to its label, passing through unknowns."""
    if value is None:
        return None
    try:
        return mapping.get(int(value), value)
    except (TypeError, ValueError):
        return value


def summarize_host(result: dict[str, Any]) -> dict[str, Any]:
    """Compact, LLM-friendly view of one Host object-query result."""
    attrs = result.get('attrs', {})
    check_result = attrs.get('last_check_result') or {}
    return {
        'name': result.get('name'),
        'display_name': attrs.get('display_name') or None,
        'address': attrs.get('address') or None,
        'address6': attrs.get('address6') or None,
        'state': _decode(HOST_STATES, attrs.get('state')),
        'state_type': _decode(STATE_TYPES, attrs.get('state_type')),
        'acknowledged': bool(attrs.get('acknowledgement')),
        'in_downtime': (attrs.get('downtime_depth') or 0) > 0,
        'output': check_result.get('output') or None,
        'performance_data': check_result.get('performance_data') or None,
        'last_check': _iso(attrs.get('last_check')),
        'next_check': _iso(attrs.get('next_check')),
        'last_state_change': _iso(attrs.get('last_state_change')),
    }


def summarize_service(result: dict[str, Any]) -> dict[str, Any]:
    """Compact, LLM-friendly view of one Service object-query result."""
    attrs = result.get('attrs', {})
    host = result.get('joins', {}).get('host', {})
    check_result = attrs.get('last_check_result') or {}
    return {
        'name': result.get('name'),
        'service': attrs.get('name'),
        'host': attrs.get('host_name'),
        'host_state': _decode(HOST_STATES, host.get('state')),
        'display_name': attrs.get('display_name') or None,
        'state': _decode(SERVICE_STATES, attrs.get('state')),
        'state_type': _decode(STATE_TYPES, attrs.get('state_type')),
        'check_command': attrs.get('check_command') or None,
        'acknowledged': bool(attrs.get('acknowledgement')),
        'in_downtime': (attrs.get('downtime_depth') or 0) > 0,
        'output': check_result.get('output') or None,
        'performance_data': check_result.get('performance_data') or None,
        'last_check': _iso(attrs.get('last_check')),
        'next_check': _iso(attrs.get('next_check')),
        'last_state_change': _iso(attrs.get('last_state_change')),
    }
