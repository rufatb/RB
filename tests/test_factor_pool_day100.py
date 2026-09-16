import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
import prepare_factor_pool as F
from factor_pool_policy import TICKERS

NOW = dt.datetime(2026, 9, 15, 8, 15, tzinfo=ZoneInfo('America/New_York'))
CFG = {'scan': {'universe': ['AC.TO']}, 'exchange_tz': 'America/Toronto'}


def test_the_research_roster_is_separate_from_the_traded_universe():
    """The size of the roster is a tuning choice; its SEPARATION is not.

    This asserted `len(TICKERS) == 60`, which pinned a number rather than the
    invariant and failed the moment the roster was widened on request. What
    must hold is that research coverage is strictly broader than the universe
    the engine actually trades, that the traded names are all covered, and that
    widening research can never widen trading."""
    from dashboard import load_config
    cfg = load_config('config.yaml')
    traded = cfg['scan']['universe']
    assert len(TICKERS) == len(set(TICKERS)), 'duplicate names inflate the coverage count'
    assert all(t.endswith('.TO') for t in TICKERS), 'the roster is TSX-only'
    assert set(traded) <= set(TICKERS), 'every traded name must be researched'
    assert len(TICKERS) > len(traded), 'research must be broader than what is traded'
    assert len(traded) == 21, 'the traded universe is unchanged by any roster widening'


@pytest.mark.parametrize('clock', [NOW.replace(hour=9, minute=30), NOW.replace(tzinfo=None)])
def test_no_postopen_or_naive_preparation(tmp_path, clock):
    with pytest.raises(ValueError):
        F.prepare(tmp_path, CFG, now=clock)
    assert not list(tmp_path.iterdir())


def test_once_only_partial_checkpoint_preserves_coverage_and_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(F.P, 'TICKERS', ('AC.TO', 'NA.TO', 'GWO.TO', 'IFC.TO'))
    monkeypatch.setattr(F.P, 'WORKERS', 2)
    monkeypatch.setattr(F, '_cached', lambda ticker, *a: ({'ticker': ticker, 'technicals': {'rsi': 50}}, []))
    batches = []
    def acquire(tasks):
        batches.append(list(tasks))
        return {t: {'status': 'UNAVAILABLE', 'error': 'ChartRateLimitError'} for t in tasks}
    before = dict(CFG['scan'])
    result = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=acquire)
    assert batches == [['NA.TO', 'GWO.TO']]
    assert result['verified'] == result['reused_baseline'] == 1
    assert result['errors']['IFC.TO'] == 'NOT_ACQUIRED'
    payload = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    assert [r['ticker'] for r in payload['candidates']] == list(F.P.TICKERS)
    assert not (tmp_path/'intraday_cache').exists()
    assert CFG['scan'] == before
    assert F.prepare(tmp_path, CFG, now=NOW, acquire_fn=lambda _: pytest.fail('retry')) == result
    (tmp_path/'deepseek_candidates.json').write_text('{}')
    replay = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=lambda _: pytest.fail('retry'))
    assert replay['status'] == 'UNAVAILABLE'
    assert replay['replay_gap'] == 'PREPARED_POOL_MISSING_OR_CHANGED_NO_RETRY'


def test_success_and_failure_are_both_retained(tmp_path, monkeypatch):
    monkeypatch.setattr(F.P, 'TICKERS', ('NA.TO', 'GWO.TO'))
    monkeypatch.setattr(F, '_cached', lambda ticker, *a: ({'ticker': ticker, 'technicals': {'rsi': 50}}, []))
    def acquire(tasks):
        return {'NA.TO': {'status': 'OK', 'value': {'ticker': 'NA.TO',
                'session': NOW.date().isoformat(), 'frame': '{}', 'receipt': {'meta': {}},
                'retrieved_at': NOW.isoformat()}},
                'GWO.TO': {'status': 'UNAVAILABLE', 'error': 'ValueError'}}
    result = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=acquire)
    assert result['verified'] == 1 and result['requested'] == 2
    assert result['status'] == 'PARTIAL'
    assert result['errors']['GWO.TO'] == 'ValueError'
    assert len(list((tmp_path/'factor_pool_cache').glob('*.receipt'))) == 1
    assert result['complete_technicals'] == 0  # A staged RSI alone is insufficient.


def test_requests_are_capped_at_preopen_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(F.P, 'TICKERS', ('NA.TO',))
    observed = []
    def acquire(tasks):
        observed.extend(budget for _, budget in tasks.values())
        return {t: {'status': 'UNAVAILABLE', 'error': 'TimeoutExpired'} for t in tasks}
    F.prepare(tmp_path, CFG, now=NOW.replace(hour=9, minute=29, second=55), acquire_fn=acquire)
    assert len(observed) == 1 and 0 < observed[0] <= 5


def test_concurrent_preparation_never_waits_indefinitely(tmp_path):
    import fcntl
    history = tmp_path/'factor_pool_history'/NOW.date().isoformat()
    history.mkdir(parents=True)
    with (history/'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = F.prepare(tmp_path, CFG, now=NOW)
    assert result['reason'] == 'PREPARATION_IN_PROGRESS_NO_RETRY'
    assert not (tmp_path/'deepseek_candidates.json').exists()


@pytest.mark.parametrize('mutation', [{'symbol': 'NA'}, {'currency': 'USD'},
                                      {'exchangeName': 'NMS'}, {'instrumentType': 'ETF'}])
def test_wrong_market_identity_never_becomes_canadian_technicals(monkeypatch, mutation):
    from adapters import YahooDirectAdapter
    meta = {'symbol': 'NA.TO', 'currency': 'CAD', 'exchangeName': 'TOR', 'instrumentType': 'EQUITY'}
    meta.update(mutation)
    monkeypatch.setattr(YahooDirectAdapter, '_chart', lambda *a: {'meta': meta})
    with pytest.raises(ValueError, match='IDENTITY_NOT_VERIFIED'):
        F.fetch_history('NA.TO', NOW)
