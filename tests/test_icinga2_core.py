# SPDX-License-Identifier: Unlicense

"""Tests for the Icinga 2 Core REST API client and the read-only tools.

No real Icinga is contacted: an `httpx.MockTransport` intercepts every
request, lets the test assert on what the client sent and returns canned
object-query results.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from mcp_server_icinga.config import Icinga2CoreConfig
from mcp_server_icinga.icinga2_core import (
    Icinga2CoreAuthError,
    Icinga2CoreClient,
    Icinga2CoreError,
    Icinga2CoreNotFoundError,
    summarize_host,
    summarize_service,
)
from mcp_server_icinga.server import (
    _acknowledge_payload,
    _action_result,
    _get_host_payload,
    _get_problems_payload,
    _get_service_payload,
    _list_hosts_payload,
    _list_services_payload,
    _object_target,
    _remove_downtime_payload,
    _reschedule_check_payload,
    _schedule_downtime_payload,
)

# Fake credential, irrelevant to the assertions. # nosec keeps bandit quiet.
_FAKE_PASSWORD = 'linuxfabrik'  # nosec B105

Handler = Callable[[httpx.Request], httpx.Response]


def _make_client(handler: Handler) -> Icinga2CoreClient:
    config = Icinga2CoreConfig.model_validate(
        {
            'url': 'https://icinga.example.com:5665',
            'username': 'mcp',
            'password': _FAKE_PASSWORD,
        }
    )
    return Icinga2CoreClient(config, transport=httpx.MockTransport(handler))


def _make_write_client(handler: Handler) -> Icinga2CoreClient:
    config = Icinga2CoreConfig.model_validate(
        {
            'url': 'https://icinga.example.com:5665',
            'username': 'ro',
            'password': _FAKE_PASSWORD,
            'write_username': 'rw',
            'write_password': _FAKE_PASSWORD,
        }
    )
    return Icinga2CoreClient(config, transport=httpx.MockTransport(handler))


def _results(*rows: dict) -> httpx.Response:
    return httpx.Response(200, json={'results': list(rows)})


def _capture_action(store: dict) -> Icinga2CoreClient:
    def handler(request: httpx.Request) -> httpx.Response:
        store['action'] = str(request.url).rsplit('/', 1)[-1]
        store['body'] = json.loads(request.content)
        return httpx.Response(200, json={'results': [{'code': 200.0, 'status': 'ok'}]})

    return _make_write_client(handler)


def _host_row(name: str, state: int = 0, **attrs) -> dict:
    base = {
        'state': state,
        'state_type': 1,
        'display_name': name,
        'address': '192.0.2.10',
        'last_check_result': {'output': 'PING OK', 'performance_data': ['rta=1ms']},
        'last_check': 1_700_000_000,
        'next_check': 1_700_000_300,
        'last_state_change': 1_699_000_000,
        'acknowledgement': 0,
        'downtime_depth': 0,
    }
    base.update(attrs)
    return {'name': name, 'type': 'Host', 'attrs': base, 'joins': {}, 'meta': {}}


def _service_row(host: str, service: str, state: int = 0, **attrs) -> dict:
    base = {
        'name': service,
        'host_name': host,
        'state': state,
        'state_type': 1,
        'display_name': service,
        'check_command': 'cmd-check-disk-usage',
        'last_check_result': {'output': 'DISK OK', 'performance_data': []},
        'last_check': 1_700_000_000,
        'next_check': 1_700_000_300,
        'last_state_change': 1_699_000_000,
        'acknowledgement': 0,
        'downtime_depth': 0,
    }
    base.update(attrs)
    return {
        'name': f'{host}!{service}',
        'type': 'Service',
        'attrs': base,
        'joins': {'host': {'name': host, 'state': 0, 'display_name': host}},
        'meta': {},
    }


# ---------------------------------------------------------------------------
# Client: request shape
# ---------------------------------------------------------------------------


def test_query_hosts_uses_method_override_post_and_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['method'] = request.method
        captured['url'] = str(request.url)
        captured['override'] = request.headers.get('X-HTTP-Method-Override')
        captured['body'] = json.loads(request.content)
        return _results(_host_row('web01'))

    client = _make_client(handler)
    client.query_hosts(filter='host.state==s', filter_vars={'s': 1})

    assert captured['method'] == 'POST'
    assert captured['url'] == 'https://icinga.example.com:5665/v1/objects/hosts'
    assert captured['override'] == 'GET'
    assert captured['body']['filter'] == 'host.state==s'
    assert captured['body']['filter_vars'] == {'s': 1}
    # A curated attribute list keeps the response small and stable.
    assert 'state' in captured['body']['attrs']
    assert 'last_check_result' in captured['body']['attrs']


def test_query_services_requests_host_join() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['body'] = json.loads(request.content)
        return _results()

    client = _make_client(handler)
    client.query_services()

    assert 'host.state' in captured['body']['joins']


def test_query_omits_filter_when_none() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['body'] = json.loads(request.content)
        return _results()

    client = _make_client(handler)
    client.query_hosts()

    assert 'filter' not in captured['body']
    assert 'filter_vars' not in captured['body']


# ---------------------------------------------------------------------------
# Client: error handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('status', [401, 403])
def test_auth_error(status: int) -> None:
    client = _make_client(lambda request: httpx.Response(status, json={}))
    with pytest.raises(Icinga2CoreAuthError):
        client.query_hosts()


def test_server_error_raises_with_detail() -> None:
    client = _make_client(lambda request: httpx.Response(500, json={'status': 'boom'}))
    with pytest.raises(Icinga2CoreError, match='boom'):
        client.query_hosts()


def test_404_is_treated_as_empty() -> None:
    client = _make_client(lambda request: httpx.Response(404, json={}))
    assert client.query_hosts() == []


def test_network_error_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('refused')

    client = _make_client(handler)
    with pytest.raises(Icinga2CoreError, match='failed'):
        client.query_hosts()


# ---------------------------------------------------------------------------
# Summarisers
# ---------------------------------------------------------------------------


def test_summarize_host_decodes_state() -> None:
    summary = summarize_host(_host_row('web01', state=1, downtime_depth=2))
    assert summary['name'] == 'web01'
    assert summary['state'] == 'DOWN'
    assert summary['state_type'] == 'HARD'
    assert summary['in_downtime'] is True
    assert summary['acknowledged'] is False
    assert summary['output'] == 'PING OK'
    assert summary['last_check'].startswith('2023-')


def test_summarize_service_decodes_state_and_host_context() -> None:
    row = _service_row('web01', 'disk', state=2, acknowledgement=1)
    summary = summarize_service(row)
    assert summary['name'] == 'web01!disk'
    assert summary['service'] == 'disk'
    assert summary['host'] == 'web01'
    assert summary['host_state'] == 'UP'
    assert summary['state'] == 'CRITICAL'
    assert summary['acknowledged'] is True
    assert summary['check_command'] == 'cmd-check-disk-usage'


def test_summarize_handles_unknown_state_code() -> None:
    # An out-of-range code passes through untranslated rather than raising.
    assert summarize_host(_host_row('h', state=99))['state'] == 99


# ---------------------------------------------------------------------------
# Server tool helpers
# ---------------------------------------------------------------------------


def test_list_hosts_payload_filters_and_sorts() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['body'] = json.loads(request.content)
        return _results(_host_row('web02', state=1), _host_row('web01', state=1))

    client = _make_client(handler)
    rows = _list_hosts_payload(client, state='down', name_contains='web')

    body = captured['body']
    assert 'host.state==host_state' in body['filter']
    assert body['filter_vars']['host_state'] == 1
    assert body['filter_vars']['pattern'] == '*web*'
    assert [r['name'] for r in rows] == ['web01', 'web02']


def test_list_hosts_payload_rejects_invalid_state() -> None:
    client = _make_client(lambda request: _results())
    with pytest.raises(ValueError, match='invalid host state'):
        _list_hosts_payload(client, state='bogus')


def test_list_services_payload_host_filter() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['body'] = json.loads(request.content)
        return _results(_service_row('web01', 'disk', state=2))

    client = _make_client(handler)
    rows = _list_services_payload(client, host='web01', state='critical')

    body = captured['body']
    assert 'service.host_name==host_name' in body['filter']
    assert body['filter_vars']['host_name'] == 'web01'
    assert body['filter_vars']['service_state'] == 2
    assert rows[0]['state'] == 'CRITICAL'


def test_get_host_payload_found() -> None:
    client = _make_client(lambda request: _results(_host_row('web01')))
    assert _get_host_payload(client, 'web01')['name'] == 'web01'


def test_get_host_payload_not_found() -> None:
    client = _make_client(lambda request: _results())
    with pytest.raises(Icinga2CoreNotFoundError):
        _get_host_payload(client, 'ghost')


def test_get_service_payload_not_found() -> None:
    client = _make_client(lambda request: _results())
    with pytest.raises(Icinga2CoreNotFoundError):
        _get_service_payload(client, 'web01', 'ghost')


def test_get_problems_payload_aggregates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith('/hosts'):
            return _results(_host_row('web01', state=1))
        return _results(
            _service_row('web01', 'disk', state=2),
            _service_row('web02', 'cpu', state=1),
        )

    client = _make_client(handler)
    problems = _get_problems_payload(client)

    assert problems['host_problem_count'] == 1
    assert problems['service_problem_count'] == 2
    assert [s['name'] for s in problems['services']] == ['web01!disk', 'web02!cpu']


# ---------------------------------------------------------------------------
# Client: actions (write)
# ---------------------------------------------------------------------------


def test_run_action_without_write_credentials_raises() -> None:
    client = _make_client(lambda request: _results())
    with pytest.raises(Icinga2CoreError, match='no write credentials'):
        client.run_action('acknowledge-problem', {})


def test_write_author_exposed() -> None:
    assert _make_write_client(lambda request: _results()).write_author == 'rw'
    assert _make_client(lambda request: _results()).write_author is None


def test_run_action_posts_to_actions_with_write_auth() -> None:
    import base64

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['url'] = str(request.url)
        captured['auth'] = request.headers.get('Authorization')
        return httpx.Response(200, json={'results': [{'code': 200.0, 'status': 'ok'}]})

    client = _make_write_client(handler)
    results = client.run_action('acknowledge-problem', {'type': 'Host'})

    assert captured['url'].endswith('/v1/actions/acknowledge-problem')
    decoded = base64.b64decode(captured['auth'].split()[1]).decode()
    assert decoded == f'rw:{_FAKE_PASSWORD}'
    assert results[0]['status'] == 'ok'


def test_run_action_404_is_not_found() -> None:
    client = _make_write_client(lambda request: httpx.Response(404, json={}))
    with pytest.raises(Icinga2CoreNotFoundError):
        client.run_action('reschedule-check', {})


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------


def test_object_target_host_and_service() -> None:
    assert _object_target('web01', None)[0] == 'Host'
    object_type, _filter, filter_vars = _object_target('web01', 'disk')
    assert object_type == 'Service'
    assert filter_vars == {'host_name': 'web01', 'service_name': 'disk'}


def test_action_result_ok_with_downtime_name() -> None:
    result = _action_result([{'code': 200.0, 'status': 'ok', 'name': 'dt-1'}])
    assert result['ok'] is True
    assert result['count'] == 1
    assert result['results'][0]['name'] == 'dt-1'


def test_action_result_not_ok_on_error_code() -> None:
    assert _action_result([{'code': 500.0, 'status': 'boom'}])['ok'] is False


def test_action_result_empty_is_not_ok() -> None:
    assert _action_result([])['ok'] is False


def test_acknowledge_payload_builds_body() -> None:
    captured: dict = {}
    client = _capture_action(captured)
    _acknowledge_payload(client, 'web01', 'disk', 'fixing it', sticky=True, notify=True)
    assert captured['action'] == 'acknowledge-problem'
    body = captured['body']
    assert body['type'] == 'Service'
    assert body['author'] == 'rw'
    assert body['comment'] == 'fixing it'
    assert body['sticky'] is True
    assert body['notify'] is True
    assert body['filter_vars'] == {'host_name': 'web01', 'service_name': 'disk'}


def test_acknowledge_payload_expiry() -> None:
    captured: dict = {}
    client = _capture_action(captured)
    _acknowledge_payload(client, 'web01', None, 'temp', expiry_hours=1)
    assert 'expiry' in captured['body']
    assert captured['body']['type'] == 'Host'


def test_schedule_downtime_payload_window_and_fixed() -> None:
    captured: dict = {}
    client = _capture_action(captured)
    _schedule_downtime_payload(
        client, 'web01', None, 'maintenance', hours=3, all_services=True
    )
    assert captured['action'] == 'schedule-downtime'
    body = captured['body']
    assert body['type'] == 'Host'
    assert body['fixed'] is True
    assert body['all_services'] is True
    assert body['end_time'] - body['start_time'] == (3 * 3600)


def test_schedule_downtime_payload_service_ignores_all_services() -> None:
    captured: dict = {}
    client = _capture_action(captured)
    _schedule_downtime_payload(client, 'web01', 'disk', 'm', all_services=True)
    assert 'all_services' not in captured['body']


def test_remove_downtime_payload() -> None:
    captured: dict = {}
    client = _capture_action(captured)
    _remove_downtime_payload(client, 'web01', None)
    assert captured['action'] == 'remove-downtime'
    assert captured['body']['type'] == 'Host'


def test_reschedule_check_payload_force() -> None:
    captured: dict = {}
    client = _capture_action(captured)
    _reschedule_check_payload(client, 'web01', 'disk', force=True)
    assert captured['action'] == 'reschedule-check'
    assert captured['body']['force'] is True
    assert captured['body']['type'] == 'Service'
