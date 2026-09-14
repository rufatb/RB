"""Opening descriptors use completed local receipts, never post-cutoff data."""
import copy
import datetime as dt
import hashlib
import json

import pytest

import research_opening as R

NOW = dt.datetime(2026, 9, 14, 9, 46, 20, tzinfo=R.ET)
SESSION = NOW.date().isoformat()


def receipt(ticker, session=SESSION, volumes=(100, 200, 300)):
    start = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(9, 30), R.ET)
    bars = [dict(start=(start+dt.timedelta(minutes=5*i)).isoformat(),
                 open=100+i, high=102+i, low=99+i, close=101+i, volume=v)
            for i, v in enumerate(volumes)]
    return dict(ticker=ticker, session=session, currency='CAD', exchange='TSX',
                interval='5m', provider='Test receipt', source_url='https://market.example/data/bars',
                observed_at=(start+dt.timedelta(minutes=15)).isoformat(),
                published_at=(start+dt.timedelta(minutes=15, seconds=1)).isoformat(),
                retrieved_at=(NOW-dt.timedelta(seconds=15)).isoformat(), bars=bars)


def candidate(ticker):
    row = receipt(ticker)
    row['history'] = [receipt(ticker, day, (100, 100, 100))
                      for day in R._prior_sessions(NOW.date())]
    row['quote'] = dict(symbol=ticker, currency='CAD', bid=103.10, ask=103.12,
                        bidAskTimestamp=(NOW-dt.timedelta(seconds=15)).timestamp())
    row['quote_retrieved_at'] = (NOW-dt.timedelta(seconds=12)).isoformat()
    return row


@pytest.fixture
def payload():
    return dict(schema_version=1, session=SESSION,
                prepared_at=(NOW-dt.timedelta(seconds=10)).isoformat(),
                rows=[candidate(t) for t in ('AAA.TO', 'BBB.TO', 'CCC.TO')])


@pytest.fixture
def universe():
    return dict(status='PARTIAL', session=SESSION, candidates=[
        dict(ticker=t, sector='Industrials') for t in ('AAA.TO', 'BBB.TO', 'CCC.TO')])


def save(tmp_path, payload):
    path = tmp_path/'research_opening_snapshot.json'
    path.write_text(json.dumps(payload))
    return path


def test_complete_local_receipts_use_exact_first_fifteen_minutes(tmp_path, payload, universe, monkeypatch):
    monkeypatch.setattr(R.quotes, 'market_client', lambda *a, **kw: pytest.fail('network factory called'))
    path = save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW, universe)
    assert result['status'] == 'READY'
    assert result['shadow'] and not result['adopted']
    assert result['input_hash'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['coverage'] == dict(requested=3, opening_valid=3, rvol_valid=3,
                                      sector_relative_valid=3, quotes_valid=3)
    row = result['rows'][0]
    assert row['opening_return_pct'] == pytest.approx(3)
    assert (row['orb_high'], row['orb_low']) == (104, 99)
    assert row['vwap_5m_proxy'] == pytest.approx(sum(((102+i+99+i+101+i)/3)*v for i, v in enumerate((100, 200, 300)))/600)
    assert row['rvol_15m'] == 2 and row['rvol_sessions'] == 20
    assert row['rvol_denominator_mean_15m_volume'] == 300
    assert row['sector_relative_return_pct'] == 0
    assert row['sector_peer_count'] == row['sector_peer_target_count'] == 2
    assert row['bar_reference_time'] == '2026-09-14T09:45:00-04:00'
    assert row['bar_reference_price'] == 103
    assert row['quote']['mark'] == pytest.approx(103.11)


@pytest.mark.parametrize('edit,reason', [
    (lambda p: p.update(session='2026-09-11'), 'WRONG_SNAPSHOT_SESSION'),
    (lambda p: p.update(prepared_at='2026-09-14T09:46:10'), 'INVALID_AWARE_CLOCK'),
    (lambda p: p.update(prepared_at='2026-09-14T09:47:00-04:00'), 'SNAPSHOT_CLOCK_OUTSIDE_0946_CUTOFF'),
    (lambda p: p.update(schema_version=2), 'INVALID_SNAPSHOT_SCHEMA'),
    (lambda p: p.update(schema_version=True), 'INVALID_SNAPSHOT_SCHEMA'),
    (lambda p: p.update(rows=p['rows']*51), 'INVALID_ROWS_OR_POOL_LIMIT'),
])
def test_document_failure_is_explicit(tmp_path, payload, universe, edit, reason):
    edit(payload)
    save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW, universe)
    assert result['status'] == 'UNAVAILABLE' and reason in result['gaps']
    assert result['rows'] == []


@pytest.mark.parametrize('field,value,reason', [
    ('currency', 'USD', 'BAR_IDENTITY_OR_SESSION_MISMATCH'),
    ('exchange', 'TSXV', 'BAR_IDENTITY_OR_SESSION_MISMATCH'),
    ('session', '2026-09-11', 'BAR_IDENTITY_OR_SESSION_MISMATCH'),
    ('interval', '1d', 'WRONG_BAR_INTERVAL'),
    ('observed_at', '2026-09-14T09:44:59-04:00', 'SOURCE_CLOCK_ORDER_OR_LOOKAHEAD'),
    ('published_at', '2026-09-14T09:46:30-04:00', 'SOURCE_CLOCK_ORDER_OR_LOOKAHEAD'),
    ('retrieved_at', '2026-09-14T09:46:11-04:00', 'SOURCE_CLOCK_ORDER_OR_LOOKAHEAD'),
    ('source_url', 'https://data.example/bars?api_key=private', 'INVALID_SOURCE_URL'),
])
def test_bad_row_preserves_healthy_siblings(tmp_path, payload, universe, field, value, reason):
    payload['rows'][0][field] = value
    save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW, universe)
    assert result['status'] == 'PARTIAL'
    assert result['coverage']['opening_valid'] == 2
    assert reason in result['rows'][0]['gaps']
    assert result['rows'][1]['opening_return_pct'] is not None


@pytest.mark.parametrize('start', ['2026-09-14T09:45:00-04:00', '2026-09-14T09:40:00', '2026-09-11T09:40:00-04:00'])
def test_last_bar_must_start_0940_aware_same_session(tmp_path, payload, universe, start):
    payload['rows'][0]['bars'][-1]['start'] = start
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['opening_return_pct'] is None
    assert first['gaps']


def test_0945_to_0950_bar_cannot_be_added_or_used(tmp_path, payload, universe):
    payload['rows'][0]['bars'].append(dict(start='2026-09-14T09:45:00-04:00', open=103, high=999, low=1, close=999, volume=99999))
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert 'INCOMPLETE_OPENING_GRID' in first['gaps']
    assert first['orb_high'] is None and first['bar_reference_price'] is None


@pytest.mark.parametrize('field,value', [('open', 0), ('high', 1), ('low', 500), ('close', float('nan')), ('volume', -1), ('volume', True)])
def test_invalid_ohlcv_never_becomes_an_indicator(tmp_path, payload, universe, field, value):
    payload['rows'][0]['bars'][0][field] = value
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['vwap_5m_proxy'] is None and first['opening_return_pct'] is None
    assert 'INVALID_OHLCV' in first['gaps']


@pytest.mark.parametrize('mutation,reason', [
    (lambda h: h.pop(), 'RVOL_REQUIRES_20_PRIOR_OPENING_RECEIPTS'),
    (lambda h: h.__setitem__(-1, copy.deepcopy(h[-2])), 'RVOL_NONCONSECUTIVE_OR_WRONG_SESSIONS'),
    (lambda h: h[-1].update(session='2026-09-12'), 'RVOL_NONCONSECUTIVE_OR_WRONG_SESSIONS'),
    (lambda h: h[-1].update(ticker='USD'), 'BAR_IDENTITY_OR_SESSION_MISMATCH'),
    (lambda h: h[-1].update(bars=[]), 'INCOMPLETE_OPENING_GRID'),
    (lambda h: [b.update(volume=0) for r in h for b in r['bars']], 'RVOL_ZERO_DENOMINATOR'),
])
def test_rvol_uses_exact_twenty_prior_exchange_openings(tmp_path, payload, universe, mutation, reason):
    mutation(payload['rows'][0]['history'])
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['opening_return_pct'] is not None
    assert first['rvol_15m'] is None and first['rvol_sessions'] == 0
    assert reason in first['gaps']


def test_daily_volume_is_not_rvol_denominator(tmp_path, payload, universe):
    for history in payload['rows'][0]['history']:
        history['daily_volume'] = 9000000
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['rvol_15m'] == 2
    assert first['rvol_denominator_mean_15m_volume'] == 300


def test_sector_relative_is_available_peer_mean_excluding_self(tmp_path, payload, universe):
    payload['rows'][0]['bars'][-1].update(close=104, high=104)
    universe['candidates'].append(dict(ticker='DDD.TO', sector='Industrials'))
    save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW, universe)
    first = result['rows'][0]
    assert first['sector_relative_return_pct'] == pytest.approx(1)
    assert first['sector_peer_count'] == 2 and first['sector_peer_target_count'] == 3


def test_one_peer_does_not_certify_sector_relative(tmp_path, payload, universe):
    payload['rows'].pop()
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['sector_relative_return_pct'] is None
    assert first['sector_peer_count'] == 1 and first['sector_peer_target_count'] == 2
    assert 'INSUFFICIENT_VALID_SECTOR_PEERS' in first['gaps']


def test_untrusted_sector_and_wrong_universe_session_are_not_used(tmp_path, payload, universe):
    for row in payload['rows']:
        row['sector'] = 'Fabricated sector'
    save(tmp_path, payload)
    universe['session'] = '2026-09-11'
    result = R.load_prepared(tmp_path, NOW, universe)
    assert result['status'] == 'PARTIAL'
    assert result['coverage']['opening_valid'] == 3
    assert all(r['sector'] is None and r['sector_relative_return_pct'] is None for r in result['rows'])


def test_missing_universe_retains_bars_but_cannot_infer_sector(tmp_path, payload):
    save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW)
    assert 'VALIDATED_SECTOR_UNIVERSE_UNAVAILABLE' in result['gaps']
    assert result['coverage']['opening_valid'] == 3


@pytest.mark.parametrize('ticker', ['AAA', 'AAA.V', 'aaa.TO', 'AA.TO/../../x', None])
def test_exact_tsx_symbol_required(tmp_path, payload, universe, ticker):
    payload['rows'][0]['ticker'] = ticker
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['ticker'] is None and 'INVALID_TSX_TICKER' in first['gaps']


def test_duplicate_symbol_does_not_create_duplicate_peers(tmp_path, payload, universe):
    payload['rows'][1] = copy.deepcopy(payload['rows'][0])
    save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW, universe)
    assert result['coverage']['opening_valid'] == 1
    assert result['rows'][0]['gaps'] == ['DUPLICATE_TICKER']
    assert result['rows'][2]['sector_peer_count'] == 0


@pytest.mark.parametrize('field,value,reason', [
    ('currency', 'USD', 'CURRENCY_MISMATCH'),
    ('symbol', 'AAA', 'SYMBOL_MISMATCH'),
    ('bidAskTimestamp', None, 'MISSING_BBO_TIMESTAMP'),
    ('bidAskTimestamp', (NOW-dt.timedelta(minutes=1)).timestamp(), 'QUOTE_NOT_EXACT_0946_OR_LOOKAHEAD'),
    ('bidAskTimestamp', (NOW+dt.timedelta(seconds=1)).timestamp(), 'STALE_QUOTE'),
    ('bid', 200, 'INVALID_BBO'),
])
def test_quote_reuses_shared_gate_and_requires_decision_minute(tmp_path, payload, universe, field, value, reason):
    payload['rows'][0]['quote'][field] = value
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['quote']['status'] == 'UNAVAILABLE' and first['quote']['mark'] is None
    assert reason in first['gaps']
    assert first['bar_reference_price'] == 103


def test_last_trade_and_bar_do_not_substitute_missing_bbo(tmp_path, payload, universe):
    payload['rows'][0]['quote'] = dict(symbol='AAA.TO', currency='CAD',
                                      regularMarketPrice=999, regularMarketTime=NOW.timestamp())
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['quote']['mark'] is None
    assert first['bar_reference_price'] == 103


def test_late_read_preserves_opening_snapshot_but_not_executable_quote(tmp_path, payload, universe):
    save(tmp_path, payload)
    result = R.load_prepared(tmp_path, NOW+dt.timedelta(minutes=30), universe)
    assert result['coverage']['opening_valid'] == 3
    assert result['coverage']['quotes_valid'] == 0
    assert 'OUTSIDE_0946_DECISION_MINUTE' in result['rows'][0]['gaps']


def test_no_publishing_before_0946_or_during_non_session(tmp_path, payload, universe):
    save(tmp_path, payload)
    assert R.load_prepared(tmp_path, NOW-dt.timedelta(minutes=1), universe)['gaps'] == ['0946_PUBLICATION_WINDOW_NOT_REACHED']
    holiday = dt.datetime(2026, 9, 7, 9, 46, 20, tzinfo=R.ET)
    payload.update(session=holiday.date().isoformat(), prepared_at=holiday.isoformat())
    save(tmp_path, payload)
    assert 'NON_TRADING_SESSION' in R.load_prepared(tmp_path, holiday, universe)['gaps']


def test_missing_invalid_large_file_and_naive_clock_are_explicit(tmp_path, payload, monkeypatch):
    assert R.load_prepared(tmp_path, NOW)['gaps'] == ['SNAPSHOT_UNAVAILABLE']
    assert R.load_prepared(tmp_path, NOW.replace(tzinfo=None))['gaps'] == ['INVALID_AWARE_CLOCK']
    path = tmp_path/'research_opening_snapshot.json'
    path.write_text('invalid json')
    assert R.load_prepared(tmp_path, NOW)['gaps'] == ['INVALID_SNAPSHOT_PAYLOAD']
    monkeypatch.setattr(R, 'MAX_BYTES', 16)
    save(tmp_path, payload)
    assert R.load_prepared(tmp_path, NOW)['gaps'] == ['SNAPSHOT_SIZE_LIMIT']
    assert R.load_prepared(tmp_path, NOW)['input_hash'] is None


def test_duplicate_json_keys_are_not_silently_overwritten(tmp_path):
    (tmp_path/'research_opening_snapshot.json').write_text('{"session":"2026-09-11","session":"2026-09-14"}')
    assert R.load_prepared(tmp_path, NOW)['gaps'] == ['DUPLICATE_JSON_KEY']


def test_quote_received_after_snapshot_is_unavailable(tmp_path, payload, universe):
    payload['rows'][0]['quote_retrieved_at'] = NOW.isoformat()
    save(tmp_path, payload)
    first = R.load_prepared(tmp_path, NOW, universe)['rows'][0]
    assert first['quote']['status'] == 'UNAVAILABLE'
    assert 'QUOTE_NOT_EXACT_0946_OR_LOOKAHEAD' in first['gaps']
    assert first['opening_return_pct'] is not None
