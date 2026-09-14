"""Expanded staging consumes verified membership and persisted source bytes."""
import datetime as dt
import hashlib
import json
import math
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import prepare_factor_pool as F
from bar_cache import key
from intraday_history import session_schedule

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 15, 8, 15, tzinfo=ET)
EARLIER = NOW.replace(minute=5)
CFG = {'scan': {'universe': ['AC.TO']}, 'exchange_tz': str(ET)}


@pytest.fixture
def history():
    frames = []
    for n, day in enumerate(session_schedule('2026-07-01', '2026-09-14').index):
        ix = pd.date_range(str(day.date())+' 09:30', periods=78, freq='5min', tz=ET)
        prices = [100+math.sin(n/3)+i/1000 for i in range(78)]
        frames.append(pd.DataFrame({'Open': prices, 'High': [p+.1 for p in prices],
            'Low': [p-.1 for p in prices], 'Close': prices, 'Volume': [100+i for i in range(78)]},
            index=ix))
    bars = pd.concat(frames)
    return json.dumps({'columns': list(bars.columns), 'index': [i.isoformat() for i in bars.index],
                       'data': bars.to_numpy().tolist()})


def metadata(ticker, sector='Industrials'):
    return {'ticker': ticker, 'issuer_id': 'issuer-'+ticker, 'sector': sector,
            'industry': 'Verified industry', 'security_type': 'COMMON_STOCK',
            'median_dollar_volume_20': 20_000_000,
            'source_url': 'https://www.tsx.com/listings/'+ticker}


def source(monkeypatch, default_candidates, **changes):
    # Scale the legacy roster in small producer fixtures so a three-row master
    # remains an expansion. Production still compares against its real60 names.
    monkeypatch.setattr(F.P, 'TICKERS', tuple('LEGACY'+str(i)+'.TO'
        for i in range(max(0, min(2, len(default_candidates)-1)))))
    master = {'status': 'PARTIAL', 'session': str(NOW.date()), 'target': 150,
              'candidates': default_candidates, 'exclusions': [{'ticker': 'OTHER.TO', 'reason': 'MISSING_INDUSTRY'}],
              'source_coverage': {'complete': False, 'received': 211}}
    master.update(changes)
    monkeypatch.setitem(sys.modules, 'tsx_universe', SimpleNamespace(load_prepared=lambda *a, **kw: master))
    return master


def item(ticker, frame, now=NOW):
    return {'ticker': ticker, 'session': str(now.date()), 'frame': frame}


def receipt(ticker):
    return {'meta': {'symbol': ticker, 'currency': 'CAD', 'exchangeName': 'TOR',
                     'instrumentType': 'EQUITY'}}


def cache(root, tickers, frame, *, session=NOW, research=False):
    directory = root/('factor_pool_cache' if research else 'intraday_cache')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'manifest.json').write_text(json.dumps({'session': str(session.date()),
        'prepared_at': session.replace(minute=5).isoformat(), 'source': 'yahoo_direct',
        'tickers': tickers, 'complete': True}))
    for ticker in tickers:
        path = directory/key(ticker)
        path.write_text(json.dumps(item(ticker, frame, session)))
        if research:
            (directory/(key(ticker)+'.receipt')).write_text(json.dumps({
                'retrieved_at': session.replace(minute=5).isoformat(), 'response': receipt(ticker),
                'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))
    return directory


def fetch(frame):
    return lambda ticker, now: {**item(ticker, frame, now), 'receipt': receipt(ticker),
                               'retrieved_at': now.isoformat()}


def acquire(tasks):
    return {ticker: {'status': 'OK', 'value': call()} for ticker, (call, _) in tasks.items()}


def test_verified_expansion_keeps_metadata_actual_counts_and_baseline(tmp_path, monkeypatch, history):
    candidates = [metadata('AC.TO'), metadata('NA.TO', 'Financials'), metadata('GWO.TO', 'Financials')]
    master = source(monkeypatch, candidates)
    baseline = cache(tmp_path, ['AC.TO'], history)
    original = {p.name: p.read_bytes() for p in baseline.iterdir()}
    tasks_seen = []
    def captured(tasks):
        tasks_seen.extend(tasks)
        assert all(0 < seconds <= 18 for _, seconds in tasks.values())
        return acquire(tasks)
    result = F.prepare(tmp_path, CFG, now=NOW, fetcher=fetch(history), acquire_fn=captured)
    assert result['requested'] == result['complete_technicals'] == result['verified'] == 3
    assert result['status'] == 'READY' and result['budget_seconds'] == 240
    assert result['started_at'] == result['completed_at'] == NOW.isoformat()
    assert result['reused_baseline'] == 1 and tasks_seen == ['NA.TO', 'GWO.TO']
    assert result['research_universe']['expanded_status'] == 'PARTIAL'
    payload = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    assert payload['research_universe']['candidates'] == candidates
    assert payload['research_universe']['source_coverage'] == master['source_coverage']
    assert payload['research_universe']['exclusions'] == master['exclusions']
    assert payload['research_universe']['mode'] == 'EXPANDED_TSX_RESEARCH'
    assert [r['ticker'] for r in payload['candidates']] == [r['ticker'] for r in candidates]
    assert all('sector' not in r for r in payload['candidates'])
    assert {p.name: p.read_bytes() for p in baseline.iterdir()} == original
    assert CFG['scan']['universe'] == ['AC.TO']


@pytest.mark.parametrize('changes', [
    {'status': 'UNAVAILABLE'}, {'session': '2026-09-14'}, {'candidates': []},
    {'candidates': [metadata('NA.TO'), metadata('NA.TO')]},
])
def test_failed_master_keeps_explicit_legacy_fallback(tmp_path, monkeypatch, history, changes):
    source(monkeypatch, [metadata('NA.TO')], **changes)
    monkeypatch.setattr(F.P, 'TICKERS', ('NA.TO', 'GWO.TO'))
    result = F.prepare(tmp_path, CFG, now=NOW, fetcher=fetch(history), acquire_fn=acquire)
    assert result['requested'] == 2 and result['budget_seconds'] == 120
    assert result['status'] == 'READY'  # Complete legacy inputs, never 150 certified names.
    assert result['research_universe']['mode'] == 'LEGACY_RESEARCH_FALLBACK'
    assert result['research_universe']['expanded_status'] == 'UNAVAILABLE'
    assert result['research_universe']['target'] == 150
    assert result['research_universe']['selected_count'] == 2


@pytest.mark.parametrize('count,expanded', [(10, False), (60, False), (61, True)])
def test_valid_but_smaller_master_never_shrinks_existing_research_pool(tmp_path, monkeypatch, count, expanded):
    candidates = [metadata('SEC'+str(i)+'.TO', 'Real Estate') for i in range(count)]
    master = source(monkeypatch, candidates)
    legacy = tuple('LEGACY'+str(i)+'.TO' for i in range(60))
    monkeypatch.setattr(F.P, 'TICKERS', legacy)
    tickers, universe = F._research_universe(tmp_path, NOW)
    assert universe['candidates'] == candidates and universe['exclusions'] == master['exclusions']
    if expanded:
        assert universe['mode'] == 'EXPANDED_TSX_RESEARCH' and len(tickers) == 61
    else:
        assert tickers == legacy and universe['mode'] == 'LEGACY_RESEARCH_FALLBACK'
        assert universe['fallback_reason'] == 'EXPANDED_POOL_NOT_BROADER_THAN_LEGACY'
        assert universe['expanded_status'] == 'UNAVAILABLE'


def test_valid_research_bytes_are_reused_without_network(tmp_path, monkeypatch, history):
    source(monkeypatch, [metadata('NA.TO')])
    directory = cache(tmp_path, ['NA.TO'], history, research=True)
    original = (directory/key('NA.TO')).read_bytes()
    result = F.prepare(tmp_path, CFG, now=NOW,
                       acquire_fn=lambda _: pytest.fail('Validated research cache was fetched again'))
    assert result['reused_research'] == result['complete_technicals'] == 1
    assert result['cache_reuse_gaps'] == {}
    assert (directory/key('NA.TO')).read_bytes() == original


def test_production_cannot_consume_diagnostic_root_even_before_open(tmp_path):
    from diagnostic_context import create_context
    root = tmp_path/'diagnostic'
    create_context(root, now=NOW)
    with pytest.raises(ValueError, match='DIAGNOSTIC_CONTEXT_REQUIRES_EXPLICIT_RUN'):
        F.prepare(root, CFG, now=NOW, acquire_fn=lambda _: pytest.fail('network'))
    assert [p.name for p in root.iterdir()] == ['diagnostic_context.json']


@pytest.mark.parametrize('damage', ['missing_file', 'bad_hash', 'wrong_source', 'wrong_session', 'missing_prior', 'bad_receipt'])
def test_manifest_cannot_hide_invalid_cached_inputs(tmp_path, monkeypatch, history, damage):
    source(monkeypatch, [metadata('NA.TO')])
    directory = cache(tmp_path, ['NA.TO'], history, research=True)
    path = directory/key('NA.TO')
    receipt_path = directory/(key('NA.TO')+'.receipt')
    if damage == 'missing_file':
        path.unlink()
    elif damage == 'bad_hash':
        path.write_text(path.read_text()+' ')
    elif damage == 'wrong_source':
        raw = json.loads(receipt_path.read_text())
        raw['response']['meta']['currency'] = 'USD'
        receipt_path.write_text(json.dumps(raw))
    elif damage == 'wrong_session':
        manifest = json.loads((directory/'manifest.json').read_text())
        manifest['session'] = '2026-09-14'
        (directory/'manifest.json').write_text(json.dumps(manifest))
    elif damage == 'bad_receipt':
        raw = json.loads(receipt_path.read_text())
        raw['response']['meta'] = []
        receipt_path.write_text(json.dumps(raw))
    else:
        raw = json.loads(path.read_text())
        frame = json.loads(raw['frame'])
        frame['index'], frame['data'] = frame['index'][:-1], frame['data'][:-1]
        raw['frame'] = json.dumps(frame)
        path.write_text(json.dumps(raw))
        raw_receipt = json.loads(receipt_path.read_text())
        raw_receipt['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(raw_receipt))
    calls = []
    def unavailable(tasks):
        calls.extend(tasks)
        return {ticker: {'status': 'UNAVAILABLE', 'error': 'ChartRateLimitError'} for ticker in tasks}
    result = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=unavailable)
    assert calls == ['NA.TO'] and result['reused_research'] == result['verified'] == 0
    assert result['status'] == 'UNAVAILABLE'
    assert 'NA.TO' in result['cache_reuse_gaps']
    payload = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    assert payload['candidates'] == [{'ticker': 'NA.TO'}]
    assert payload['candidate_diagnostics']['NA.TO'] == ['ChartRateLimitError']


def test_one_failed_symbol_does_not_cancel_healthy_later_wave(tmp_path, monkeypatch, history):
    source(monkeypatch, [metadata(t) for t in ('NA.TO', 'GWO.TO', 'IFC.TO')])
    monkeypatch.setattr(F.P, 'WORKERS', 2)
    batches = []
    def partial(tasks):
        batches.append(list(tasks))
        result = acquire(tasks)
        if 'NA.TO' in result:
            result['NA.TO'] = {'status': 'UNAVAILABLE', 'error': 'ChartTimeoutError'}
        return result
    result = F.prepare(tmp_path, CFG, now=NOW, fetcher=fetch(history), acquire_fn=partial)
    assert batches == [['NA.TO', 'GWO.TO'], ['IFC.TO']]
    assert result['verified'] == 2 and result['requested'] == 3
    assert result['errors']['NA.TO'] == 'ChartTimeoutError'


def test_missing_recent_session_does_not_bridge_momentum_warmup(tmp_path, monkeypatch, history):
    source(monkeypatch, [metadata('NA.TO')])
    encoded = json.loads(history)
    retained = [(stamp, row) for stamp, row in zip(encoded['index'], encoded['data'])
                if not stamp.startswith('2026-09-09')]
    encoded['index'] = [stamp for stamp, _ in retained]
    encoded['data'] = [row for _, row in retained]
    result = F.prepare(tmp_path, CFG, now=NOW,
        fetcher=fetch(json.dumps(encoded)), acquire_fn=acquire)
    assert result['status'] == 'PARTIAL' and result['verified'] == 1
    assert result['complete_technicals'] == 0
    payload = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    technicals = payload['candidates'][0]['technicals']
    assert technicals['rsi'] is None and technicals['macd'] is None
    assert technicals['rvol'] is None


@pytest.mark.parametrize('failure', ['ChartRateLimitError', 'ChartAuthenticationError', 'ChartTimeoutError'])
def test_provider_refusal_or_whole_wave_outage_stops_and_keeps_every_name(tmp_path, monkeypatch, failure):
    tickers = ('NA.TO', 'GWO.TO', 'IFC.TO')
    source(monkeypatch, [metadata(t) for t in tickers])
    monkeypatch.setattr(F.P, 'WORKERS', 2)
    batches = []
    def unavailable(tasks):
        batches.append(list(tasks))
        return {ticker: {'status': 'UNAVAILABLE', 'error': failure} for ticker in tasks}
    result = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=unavailable)
    assert batches == [['NA.TO', 'GWO.TO']]
    assert result['errors']['IFC.TO'] == 'NOT_ACQUIRED'
    assert result['errors']['provider'] == 'PROVIDER_OUTAGE_FURTHER_REQUESTS_SKIPPED'
    payload = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    assert [r['ticker'] for r in payload['candidates']] == list(tickers)
    assert len(payload['candidate_diagnostics']) == 3
    # Adding a better master after an outage never authorizes a same-session retry.
    source(monkeypatch, [metadata('BMO.TO')], status='READY')
    assert F.prepare(tmp_path, CFG, now=NOW, acquire_fn=lambda _: pytest.fail('retry')) == result
    (tmp_path/'deepseek_candidates.json').write_text('{}')
    replay = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=lambda _: pytest.fail('retry changed artifact'))
    assert replay['replay_gap'] == 'PREPARED_POOL_MISSING_OR_CHANGED_NO_RETRY'
