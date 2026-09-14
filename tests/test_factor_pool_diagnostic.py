"""The diagnostic shares acquisition/validation without impersonating pre-open."""
import datetime as dt
import json
import math
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import prepare_factor_pool as F
from bar_cache import inspect_cache, key
from diagnostic_context import SNAPSHOT_KIND, create_context
from intraday_history import session_schedule

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 11, 13, 15, tzinfo=ET)
PREOPEN = NOW.replace(hour=8, minute=5)
CFG = {'scan': {'universe': ['ABC.TO']}, 'exchange_tz': str(ET),
       'data_sources': {'primary': 'yahoo_direct'}}


@pytest.fixture
def encoded_history():
    frames = []
    for n, date in enumerate(session_schedule('2026-07-01', '2026-09-10').index):
        ix = pd.date_range(str(date.date())+' 09:30', periods=78, freq='5min', tz=ET)
        prices = [100+math.sin(n/3)+i/1000 for i in range(78)]
        frames.append(pd.DataFrame({'Open': prices, 'High': [p+.1 for p in prices],
            'Low': [p-.1 for p in prices], 'Close': prices,
            'Volume': [100+i for i in range(78)]}, index=ix))
    bars = pd.concat(frames)
    return json.dumps({'columns': list(bars.columns),
        'index': [i.isoformat() for i in bars.index], 'data': bars.to_numpy().tolist()})


def baseline(root, frame):
    directory = root/'intraday_cache'
    directory.mkdir()
    (directory/'manifest.json').write_text(json.dumps({'session': NOW.date().isoformat(),
        'source': 'yahoo_direct', 'tickers': ['ABC.TO'], 'complete': True,
        'prepared_at': PREOPEN.isoformat()}))
    (directory/key('ABC.TO')).write_text(json.dumps({'ticker': 'ABC.TO',
        'session': NOW.date().isoformat(), 'frame': frame}))
    return {p.name: p.read_bytes() for p in directory.iterdir()}


def acquire(tasks):
    return {t: {'status': 'OK', 'value': call()} for t, (call, _) in tasks.items()}


def fake_history(frame, clock):
    return lambda ticker, now: {'ticker': ticker, 'session': now.date().isoformat(),
        'frame': frame, 'receipt': {'meta': {'symbol': ticker}},
        'retrieved_at': clock.isoformat()}


def test_production_still_refuses_postopen_even_with_diagnostic_marker(tmp_path):
    root = tmp_path/'diagnostic'
    create_context(root, now=NOW)
    with pytest.raises(ValueError, match='RESEARCH_POOL_PREOPEN_ONLY'):
        F.prepare(root, CFG, now=NOW, acquire_fn=lambda _: pytest.fail('network'))
    assert sorted(p.name for p in root.iterdir()) == ['diagnostic_context.json']


def test_diagnostic_requires_isolation_before_writing_or_acquiring(tmp_path):
    with pytest.raises(ValueError, match='EXPLICIT_ISOLATED_DIAGNOSTIC_CONTEXT_REQUIRED'):
        F.prepare_diagnostic(tmp_path, CFG, now=NOW,
                             acquire_fn=lambda _: pytest.fail('network'))
    assert list(tmp_path.iterdir()) == []
    root = tmp_path/'diagnostic'
    create_context(root, now=NOW)
    (root/'reports.sqlite3').write_bytes(b'preserved canonical history')
    with pytest.raises(ValueError, match='DIAGNOSTIC_REQUIRES_ISOLATED_NONPUBLICATION_STATE'):
        F.prepare_diagnostic(root, CFG, now=NOW,
                             acquire_fn=lambda _: pytest.fail('network'))
    assert (root/'reports.sqlite3').read_bytes() == b'preserved canonical history'
    assert not (root/'factor_pool_history').exists()


def test_diagnostic_uses_actual_clock_and_same_python_technicals(tmp_path, monkeypatch,
                                                              encoded_history):
    monkeypatch.setattr(F.P, 'TICKERS', ('ABC.TO', 'NA.TO'))
    root = tmp_path/'diagnostic'
    create_context(root, now=NOW)
    original_baseline = baseline(root, encoded_history)
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(F, 'dt', SimpleNamespace(datetime=Clock, time=dt.time))
    observed = []
    fetcher = fake_history(encoded_history, NOW)
    def capture(ticker, now):
        observed.append((ticker, now))
        return fetcher(ticker, now)
    result = F.prepare_diagnostic(root, CFG, fetcher=capture, acquire_fn=acquire)
    assert observed == [('NA.TO', NOW)]
    assert result['status'] == 'READY'
    assert result['requested'] == result['verified'] == result['complete_technicals'] == 2
    assert result['reused_baseline'] == 1
    assert result['started_at'] == result['completed_at'] == NOW.isoformat()
    for path in [root/'deepseek_candidates.json', root/'factor_pool_status.json',
                 root/'factor_pool_history'/str(NOW.date())/'attempt.json',
                 root/'factor_pool_history'/str(NOW.date())/'candidates.json',
                 root/'factor_pool_cache'/'manifest.json']:
        payload = json.loads(path.read_text())
        assert payload['kind'] == SNAPSHOT_KIND
        assert payload['morning_snapshot'] is False
    candidates = json.loads((root/'deepseek_candidates.json').read_text())
    assert candidates['as_of'] == NOW.isoformat()
    assert [c['technical_provenance']['computed_at'] for c in candidates['candidates']] == [NOW.isoformat()]*2
    assert all(c['technicals_as_of'] == '2026-09-10T16:00:00-04:00'
               for c in candidates['candidates'])
    assert {p.name: p.read_bytes() for p in (root/'intraday_cache').iterdir()} == original_baseline
    receipt = json.loads((root/'factor_pool_cache'/(key('NA.TO')+'.receipt')).read_text())
    assert receipt['retrieved_at'] == NOW.isoformat()
    with pytest.raises(ValueError, match='DIAGNOSTIC_CACHE_NOT_PREOPEN'):
        F._cached('NA.TO', root/'factor_pool_cache', CFG, NOW)
    assert inspect_cache(CFG, root/'factor_pool_cache', NOW)['status'] == 'NOT READY'
    assert F.prepare_diagnostic(root, CFG, acquire_fn=lambda _: pytest.fail('retry')) == result

    production = tmp_path/'production'
    production.mkdir()
    baseline(production, encoded_history)
    prepared = F.prepare(production, CFG, now=PREOPEN,
                         fetcher=fake_history(encoded_history, PREOPEN), acquire_fn=acquire)
    assert prepared['status'] == result['status']
    original = json.loads((production/'deepseek_candidates.json').read_text())
    assert [c['technicals'] for c in candidates['candidates']] == [c['technicals'] for c in original['candidates']]
    assert 'kind' not in original and 'morning_snapshot' not in original


def test_diagnostic_cache_cannot_impersonate_preopen_even_if_clock_is_early(tmp_path,
                                                                        monkeypatch):
    directory = tmp_path/'cache'
    directory.mkdir()
    (directory/'manifest.json').write_text(json.dumps({'prepared_at': PREOPEN.isoformat(),
        'session': str(NOW.date()), 'source': 'yahoo_direct', 'tickers': ['NA.TO'],
        'kind': SNAPSHOT_KIND, 'morning_snapshot': False}))
    monkeypatch.setattr(F, '_from_cache', lambda *a: pytest.fail('accepted diagnostic as preopen'))
    with pytest.raises(ValueError, match='DIAGNOSTIC_CACHE_NOT_PREOPEN'):
        F._cached('NA.TO', directory, CFG, PREOPEN)


def test_diagnostic_outage_keeps_once_only_checkpoint_and_request_budget(tmp_path, monkeypatch):
    root = tmp_path/'diagnostic'
    create_context(root, now=NOW)
    monkeypatch.setattr(F.P, 'TICKERS', tuple('NEW'+str(i)+'.TO' for i in range(10)))
    batches = []
    def unavailable(tasks):
        batches.append(tasks)
        return {t: {'status': 'UNAVAILABLE', 'error': 'ChartRateLimitError'} for t in tasks}
    result = F.prepare_diagnostic(root, CFG, now=NOW, acquire_fn=unavailable)
    assert len(batches) == 1 and len(batches[0]) == F.P.WORKERS == 8
    assert all(0 < seconds <= F.P.REQUEST_SECONDS == 18 for _, seconds in batches[0].values())
    assert result['errors']['provider'] == 'PROVIDER_OUTAGE_FURTHER_REQUESTS_SKIPPED'
    assert result['requested'] == 10 and result['verified'] == 0
    assert result['morning_snapshot'] is False
    assert F.prepare_diagnostic(root, CFG, now=NOW,
        acquire_fn=lambda _: pytest.fail('retry after failure')) == result
    candidates = json.loads((root/'deepseek_candidates.json').read_text())
    assert len(candidates['candidates']) == 10
