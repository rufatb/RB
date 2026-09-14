"""Auth bootstrap can be staged without caching or weakening market quotes."""
import copy
import datetime as dt
import http.cookiejar
import io
import json
import stat
import urllib.error

import pytest

import prepare_yahoo_auth as prep
import quotes
import yahoo_auth_cache as auth

NOW = dt.datetime(2026, 9, 15, 9, 40, tzinfo=auth.ET)
SECRET = 'PRIVATE_COOKIE_VALUE'
CRUMB = 'PRIVATE_CRUMB_VALUE'


def jar(expiry=None):
    out = http.cookiejar.CookieJar()
    out.set_cookie(http.cookiejar.Cookie(
        version=0, name='A3', value=SECRET, port=None, port_specified=False,
        domain='.yahoo.com', domain_specified=True, domain_initial_dot=True,
        path='/', path_specified=True, secure=True, expires=expiry,
        discard=expiry is None, comment=None, comment_url=None, rest={}, rfc2109=False))
    return out


def saved(tmp_path, *, when=NOW, expiry=None):
    document = auth.document(jar(expiry), CRUMB, when)
    auth.save(tmp_path, document, when)
    return document


def test_private_roundtrip_and_safe_preflight(tmp_path):
    saved(tmp_path)
    loaded, public = auth.load(tmp_path, NOW + dt.timedelta(minutes=6))
    assert loaded[1] == CRUMB and next(iter(loaded[0])).value == SECRET
    assert public['status'] == 'READY' and public['cookie_count'] == 1
    assert auth.inspect(tmp_path, NOW) == auth.load(tmp_path, NOW)[1]
    assert SECRET not in json.dumps(public) and CRUMB not in json.dumps(public)
    assert 'prices' not in public and public['note'].startswith('Authentication only')
    path = tmp_path / 'secrets' / auth.CACHE_NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize('offset,reason', [
    (-1, 'FUTURE_AUTH_CACHE'), (900, 'EXPIRED_AUTH_CACHE'),
    (901, 'EXPIRED_AUTH_CACHE'), (86400, 'WRONG_AUTH_SESSION'),
])
def test_short_ttl_and_exact_session(tmp_path, offset, reason):
    saved(tmp_path)
    private, public = auth.load(tmp_path, NOW + dt.timedelta(seconds=offset))
    assert private is None and public['reason_code'] == reason


def test_cookie_expiry_shortens_cache_lifetime(tmp_path):
    expiry = int((NOW + dt.timedelta(minutes=5)).timestamp())
    document = saved(tmp_path, expiry=expiry)
    assert auth._aware(document['expires_at']).timestamp() == expiry
    assert auth.load(tmp_path, NOW + dt.timedelta(minutes=5))[0] is None


@pytest.mark.parametrize('domain', ['yahoo.com.evil.test', '.evil.test', 'evil-yahoo.com',
                                    'yahoo.com/', '..yahoo.com', '.YAHOO.COM'])
def test_cookie_domain_boundary(tmp_path, domain):
    document = saved(tmp_path)
    document['cookies'][0]['domain'] = domain
    auth.private_atomic(tmp_path / 'secrets' / auth.CACHE_NAME, document)
    private, public = auth.load(tmp_path, NOW)
    assert private is None and public['reason_code'] == 'INVALID_COOKIE_DOMAIN'
    assert domain not in json.dumps(public)


@pytest.mark.parametrize('mutation', [
    lambda d: d.update(prices={'TRP.TO': 100}),
    lambda d: d.update(crumb=CRUMB + '\nBAD'),
    lambda d: d.update(expires_at=(NOW + dt.timedelta(minutes=16)).isoformat()),
    lambda d: d['cookies'][0].update(expires=True),
    lambda d: d['cookies'][0].update(secure='yes'),
    lambda d: d['cookies'].append(copy.deepcopy(d['cookies'][0])),
    lambda d: d.update(cookies=[]),
    lambda d: d.update(schema_version=True),
])
def test_invalid_cache_never_supplies_credentials(tmp_path, mutation):
    document = saved(tmp_path)
    mutation(document)
    auth.private_atomic(tmp_path / 'secrets' / auth.CACHE_NAME, document)
    private, public = auth.load(tmp_path, NOW)
    assert private is None and public['status'] == 'INVALID'
    assert SECRET not in json.dumps(public) and CRUMB not in json.dumps(public)


def test_truncated_duplicate_and_oversized_cache(tmp_path):
    path = tmp_path / 'secrets' / auth.CACHE_NAME
    saved(tmp_path)
    for raw in ['{"crumb":', '{"crumb":"one","crumb":"two"}', 'x' * (auth.MAX_BYTES + 1)]:
        path.write_text(raw)
        private, public = auth.load(tmp_path, NOW)
        assert private is None and public['status'] == 'INVALID'
        assert 'one' not in json.dumps(public)


def test_unsafe_mode_and_symlink_are_refused(tmp_path):
    document = saved(tmp_path)
    path = tmp_path / 'secrets' / auth.CACHE_NAME
    path.chmod(0o644)
    assert auth.load(tmp_path, NOW)[1]['reason_code'] == 'UNSAFE_AUTH_PERMISSIONS'
    # Re-preparation writes privately even after archive extraction lost mode.
    auth.save(tmp_path, document, NOW)
    assert auth.inspect(tmp_path, NOW)['status'] == 'READY'
    original = tmp_path / 'original.json'
    path.rename(original)
    path.symlink_to(original)
    assert auth.load(tmp_path, NOW)[1]['reason_code'] == 'UNSAFE_AUTH_PATH'
    with pytest.raises(auth.AuthCacheError, match='UNSAFE_AUTH_PATH'):
        auth.save(tmp_path, document, NOW)


def test_warmed_client_still_fetches_original_current_quotes(tmp_path):
    saved(tmp_path)
    client = quotes.YahooMarketData(auth_state_dir=tmp_path, auth_now=NOW + dt.timedelta(minutes=6))
    observed = int((NOW + dt.timedelta(minutes=6)).timestamp())
    raw = {'quoteResponse': {'result': [{'symbol': 'XIU.TO', 'regularMarketTime': observed,
                                       'regularMarketPrice': 50, 'currency': 'CAD'}]}}
    requests = []

    class Opener:
        def open(self, request, timeout):
            assert request.host == 'query2.finance.yahoo.com'
            assert '/v7/finance/quote?' in request.full_url
            requests.append(request)
            return io.BytesIO(json.dumps(raw).encode())

    client.op = Opener()
    got = quotes.acquire_equities_raw(client, ['XIU.TO'])
    assert len(requests) == 1
    assert got['XIU.TO']['regularMarketTime'] == observed
    validated = quotes.validate_equities(got, ['XIU.TO'], NOW + dt.timedelta(minutes=6))['XIU.TO']
    assert validated['status'] != 'OK'  # Auth did not invent a timestamped BBO.
    assert 'regularMarketPrice' not in (tmp_path / 'secrets' / auth.CACHE_NAME).read_text()


def test_cache_expiring_after_client_creation_uses_existing_auth_path(tmp_path, monkeypatch):
    saved(tmp_path)
    client = quotes.YahooMarketData(auth_state_dir=tmp_path, auth_now=NOW)
    client._auth_now = NOW + dt.timedelta(minutes=15)
    calls = []
    monkeypatch.setattr(client, '_get', lambda url, **kw: calls.append(url) or b'new-test-crumb')
    client.auth()
    assert len(calls) == 2 and client.crumb == 'new-test-crumb'
    assert client.auth_cache_status['status'] == 'STALE'
    assert not list(client.cookie_jar)


@pytest.mark.parametrize('status', [401, 403, 429])
def test_warmed_provider_denial_does_not_reauthenticate(tmp_path, status):
    saved(tmp_path)
    client = quotes.YahooMarketData(auth_state_dir=tmp_path, auth_now=NOW)
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            raise urllib.error.HTTPError('', status, SECRET, {}, None)

    client.op = Opener()
    with pytest.raises(urllib.error.HTTPError):
        quotes.acquire_equities_raw(client, ['XIU.TO'])
    assert len(calls) == 1
    assert '/v7/finance/quote?' in calls[0].full_url


def test_market_client_loads_state_and_keeps_snapshot_override(tmp_path, monkeypatch):
    saved(tmp_path, when=dt.datetime.now(auth.ET))
    monkeypatch.setenv('RB_STATE_DIR', str(tmp_path))
    monkeypatch.delenv('RB_QUOTES_JSON', raising=False)
    assert quotes.market_client().auth_cache_status['status'] == 'READY'
    snapshot = tmp_path / 'external.json'
    snapshot.write_text('{"quotes": {}}')
    monkeypatch.setenv('RB_QUOTES_JSON', str(snapshot))
    assert isinstance(quotes.market_client(), quotes.SnapshotMarketData)


def test_prepare_only_authenticates_and_returns_safe_receipt(tmp_path, monkeypatch):
    calls = []

    def auth_only(client):
        calls.append('auth')
        client.cookie_jar = jar()
        client.crumb = CRUMB

    monkeypatch.setattr(quotes.YahooMarketData, 'auth', auth_only)
    monkeypatch.setattr(quotes.YahooMarketData, 'get', lambda *a: pytest.fail('prices fetched'))
    monkeypatch.setattr(quotes.YahooMarketData, 'chain', lambda *a: pytest.fail('options fetched'))

    def worker(tasks):
        fn, budget = tasks['yahoo_auth']
        assert budget == 35
        return {'yahoo_auth': {'value': fn(), 'error': None}}

    result = prep.prepare(tmp_path, now=NOW, clock=lambda: NOW, worker=worker)
    assert calls == ['auth'] and result['status'] == 'READY'
    assert SECRET not in json.dumps(result) and CRUMB not in json.dumps(result)
    assert not (tmp_path / 'reports.sqlite3').exists()
    receipt = (tmp_path / 'yahoo_auth_status.json').read_text()
    assert SECRET not in receipt and CRUMB not in receipt
    result = prep.prepare(tmp_path, now=NOW, clock=lambda: NOW,
                          worker=lambda *a: pytest.fail('valid authentication fetched again'))
    assert result['status'] == 'READY' and result['reused']


def test_auth_failure_is_bounded_and_retains_old_success(tmp_path):
    saved(tmp_path, when=NOW - dt.timedelta(minutes=16))
    path = tmp_path / 'secrets' / auth.CACHE_NAME
    before = path.read_bytes()

    def worker(tasks):
        assert list(tasks) == ['yahoo_auth']
        return {'yahoo_auth': {'error': 'TimeoutExpired', 'value': None,
                               'progress': [{'stage': 'yahoo_cookie_started'}]}}

    result = prep.prepare(tmp_path, now=NOW, clock=lambda: NOW, worker=worker)
    assert result['reason_code'] == 'AUTH_PREPARATION_TIMEOUT'
    assert result['stages'] == ['yahoo_cookie_started']
    assert path.read_bytes() == before
    assert len(list((tmp_path / 'diagnostics' / 'yahoo_auth').glob('*.json'))) == 1
    inspected = auth.inspect(tmp_path, NOW)
    assert inspected['status'] == 'STALE'
    assert inspected['last_attempt']['reason_code'] == 'AUTH_PREPARATION_TIMEOUT'


def test_rate_limit_receipt_contains_only_safe_identity(tmp_path):
    def worker(tasks):
        return {'yahoo_auth': {'error': 'HTTPError', 'reason_code': 'RATE_LIMITED',
                               'http_status': 429, 'detail': SECRET, 'value': CRUMB}}

    result = prep.prepare(tmp_path, now=NOW, clock=lambda: NOW, worker=worker)
    assert result['reason_code'] == 'RATE_LIMITED' and result['http_status'] == 429
    assert SECRET not in json.dumps(result) and CRUMB not in json.dumps(result)
    assert not (tmp_path / 'secrets' / auth.CACHE_NAME).exists()


def test_authentication_worker_checks_one_shared_deadline(monkeypatch):
    ticks = [0.0]
    monkeypatch.setattr(prep.time, 'monotonic', lambda: ticks[0])

    def slow(client):
        assert client._quote_deadline == 30
        client.cookie_jar, client.crumb = jar(), CRUMB
        ticks[0] = 31

    monkeypatch.setattr(quotes.YahooMarketData, 'auth', slow)
    with pytest.raises(TimeoutError):
        prep._authenticate(NOW, clock=lambda: NOW)


def test_preflight_does_not_trust_provider_text_in_status_receipt(tmp_path):
    auth.private_atomic(tmp_path / 'yahoo_auth_status.json', {
        'checked_at': NOW.isoformat(), 'status': 'UNAVAILABLE',
        'reason_code': 'RATE_LIMITED', 'http_status': 429,
        'detail': SECRET, 'crumb': CRUMB, 'stages': [SECRET, 'yahoo_cookie_started']})
    public = auth.inspect(tmp_path, NOW)
    assert public['last_attempt']['reason_code'] == 'RATE_LIMITED'
    assert public['last_attempt']['stages'] == ['yahoo_cookie_started']
    assert SECRET not in json.dumps(public) and CRUMB not in json.dumps(public)


def test_public_receipt_with_arbitrary_reason_is_quarantined(tmp_path):
    auth.private_atomic(tmp_path / 'yahoo_auth_status.json', {
        'checked_at': NOW.isoformat(), 'status': 'UNAVAILABLE', 'reason_code': SECRET})
    public = auth.inspect(tmp_path, NOW)
    assert public['last_attempt']['reason_code'] == 'INVALID_AUTH_RECEIPT'
    assert SECRET not in json.dumps(public)
