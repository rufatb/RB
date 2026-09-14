"""Raw quote acquisition shares one budget and retains safe outage identity."""
import io
import json
import time
import urllib.error

import pytest

import brief
import bounded
import quotes as Q
from test_daily_pipeline import NOW, market_row, res


def test_raw_quote_deadline_covers_cookie_crumb_and_data(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(Q.time, 'monotonic', lambda: clock[0])
    client = Q.YahooMarketData(timeout=8)
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append(timeout)
            if len(seen) == 1:
                clock[0] += 3
                raise urllib.error.HTTPError('', 404, '', {}, None)
            if len(seen) == 2:
                clock[0] += 3
                return io.BytesIO(b'local-test-crumb')
            clock[0] += timeout
            raise TimeoutError('PRIVATE_PROVIDER_DATA')

    client.op = Opener()
    with pytest.raises(TimeoutError) as caught:
        Q.acquire_equities_raw(client, ['XIU.TO'])
    assert seen == [8, 5, 2]
    assert caught.value.acquisition_reason_code == 'TRANSPORT_TIMEOUT'
    assert client._quote_deadline is None and client.timeout == 8


def test_successful_raw_rows_and_timestamps_are_not_revalidated(monkeypatch):
    source = {'XIU.TO': market_row('XIU.TO'), 'BAD.TO': None}
    client = Q.YahooMarketData()
    monkeypatch.setattr(client, 'get', lambda tickers: source)
    out = Q.acquire_equities_raw(client, ['XIU.TO', 'BAD.TO'])
    assert out is source
    assert out['XIU.TO']['regularMarketTime'] == NOW.timestamp()
    assert 'status' not in out['XIU.TO']
    assert Q.validate_equities(out, out, NOW)['XIU.TO']['status'] == 'OK'


@pytest.mark.parametrize('status,reason', [
    (403, 'AUTHENTICATION_ERROR'), (429, 'RATE_LIMITED'),
    (502, 'TRANSPORT_ERROR'),
])
def test_only_expected_cookie_404_allows_crumb_request(status, reason):
    client = Q.YahooMarketData()
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(1)
            raise urllib.error.HTTPError('', status, 'PRIVATE_PROVIDER_DATA', {}, None)

    client.op = Opener()
    with pytest.raises(urllib.error.HTTPError) as caught:
        Q.acquire_equities_raw(client, ['XIU.TO'], max_attempts=1)
    assert len(requests) == 1
    assert caught.value.acquisition_reason_code == reason
    assert caught.value.acquisition_http_status == status
    assert client._quote_deadline is None


def test_invalid_json_restores_existing_deadline_without_retry():
    client = Q.YahooMarketData()
    previous = time.monotonic() + 30
    client._quote_deadline = previous
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(timeout)
            if request.host == 'fc.yahoo.com':
                return io.BytesIO(b'')
            if 'getcrumb' in request.full_url:
                return io.BytesIO(b'PRIVATE_TEST_CRUMB')
            return io.BytesIO(b'PRIVATE_INVALID_JSON')

    client.op = Opener()
    with pytest.raises(ValueError) as caught:
        Q.acquire_equities_raw(client, ['XIU.TO'])
    assert len(requests) == 3
    assert max(requests) <= 8
    assert caught.value.acquisition_reason_code == 'INVALID_PAYLOAD'
    assert client._quote_deadline == previous
    assert client.cache == {}


def test_wrapped_socket_timeout_keeps_timeout_category():
    failure = urllib.error.URLError(TimeoutError('PRIVATE_PROVIDER_DATA'))
    quote = Q.quote_failure('XIU.TO', failure, currency='CAD')
    assert quote['reason_code'] == 'TRANSPORT_TIMEOUT'
    assert 'PRIVATE_PROVIDER_DATA' not in json.dumps(quote)


def test_fixed_quote_stages_survive_worker_timeout():
    def acquire():
        client = Q.YahooMarketData()

        class Opener:
            def open(self, request, timeout):
                if request.host == 'fc.yahoo.com':
                    raise urllib.error.HTTPError('', 404, '', {}, None)
                if 'getcrumb' in request.full_url:
                    return io.BytesIO(b'PRIVATE_TEST_CRUMB')
                time.sleep(2)
                return io.BytesIO(b'{}')

        client.op = Opener()
        return Q.acquire_equities_raw(client, ['XIU.TO'])

    out = bounded.acquire({'quotes': (acquire, .2)})['quotes']
    assert out['error'] == 'TimeoutExpired'
    assert out['progress'][-1]['stage'] == 'yahoo_data_started'
    assert 'PRIVATE_TEST_CRUMB' not in json.dumps(out)


def test_brief_quote_timeout_retains_cause_and_completed_intraday(monkeypatch, tmp_path):
    calls = []

    class Market:
        def get(self, tickers):
            pytest.fail('brief bypassed the raw acquisition boundary')

    def raw(client, tickers, **kwargs):
        calls.append(kwargs)
        raise TimeoutError('PRIVATE_PROVIDER_DATA')

    def acquire(tasks):
        out = {}
        for name, (fn, budget) in tasks.items():
            try:
                out[name] = dict(value=fn(), status='OK', error=None, seconds=.01)
            except TimeoutError:
                out[name] = dict(value=None, status='UNAVAILABLE',
                                 error='TimeoutExpired', seconds=budget)
        return out

    monkeypatch.setattr(brief, 'market_client', Market)
    monkeypatch.setattr(Q, 'acquire_equities_raw', raw)
    monkeypatch.setattr(bounded, 'acquire', acquire)
    monkeypatch.setattr(brief.ledger, 'load', lambda: [])
    monkeypatch.setattr(brief.positions, 'load', lambda: [])
    monkeypatch.setattr('r945.run', lambda *a, **k: res())
    monkeypatch.setattr(brief.biotech, 'load_inputs', lambda: (
        {'universe_complete': False, 'errors': ['fixture outage']}, []))
    report = brief.compute(now=NOW, state_dir=tmp_path)
    assert calls == [{'budget_seconds': 8}]
    assert report['sections']['intraday']['status'] == 'OK'
    assert report['intraday']['res']['longs'][0]['t'] == 'AAA.TO'
    quote = report['intraday']['benchmark']
    assert quote['reason_code'] == 'TRANSPORT_TIMEOUT'
    assert quote['error_class'] == 'TimeoutExpired'
    assert quote['mark'] is None
    assert len([e for e in report['errors'] if e['layer'] == 'equity_quotes']) == 1
    assert 'PRIVATE_PROVIDER_DATA' not in json.dumps(report)


def test_section_failure_keeps_provider_category_without_provider_text():
    result = {'error': 'HTTPError', 'reason_code': 'RATE_LIMITED',
              'http_status': 429, 'detail': 'PRIVATE_PROVIDER_DATA'}
    quote = Q.section_quote_failure('XIU.TO', result, currency='CAD')
    assert quote['reason_code'] == 'RATE_LIMITED'
    assert quote['error_class'] == 'HTTPError'
    assert quote['currency'] == 'CAD'
    assert 'PRIVATE_PROVIDER_DATA' not in json.dumps(quote)


def test_worker_preserves_http_status_and_category_without_provider_text():
    def acquire():
        class Market:
            def get(self, tickers):
                raise urllib.error.HTTPError('', 429, 'PRIVATE_PROVIDER_DATA', {}, None)

        return Q.acquire_equities_raw(Market(), ['XIU.TO'])

    result = bounded.acquire({'quotes': (acquire, 1)})['quotes']
    assert result['error'] == 'HTTPError'
    assert result['http_status'] == 429
    assert result['reason_code'] == 'RATE_LIMITED'
    assert 'PRIVATE_PROVIDER_DATA' not in json.dumps(result)
