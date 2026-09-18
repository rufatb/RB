"""The daily-bar pass and the biotech fold-in must actually RUN.

THE DEFECT THIS FILE EXISTS FOR. Both passes were gated on `fetcher is None`
to keep injected (deterministic) runs hermetic. But `_prepare` does
`fetcher = fetcher or fetch_history` near the top, so by the time the gate was
evaluated `fetcher` was never None and BOTH PASSES WERE DEAD CODE. The live run
reported `status: PARTIAL, daily_filled: 0, biotech_added: 0` and 38 complete
technicals — the same 38 as before the change — while every unit test passed,
because nothing asserted the passes did any work.

A feature that silently does nothing is the failure mode this repo keeps
finding (report_page invoked by nothing; prepare_factor_pool never staged;
cache_degraded computed and dropped). So these tests assert WORK DONE, not
merely that the call returned.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

ET = ZoneInfo('America/New_York')

import prepare_factor_pool as F
from test_factor_pool_day101 import CFG, NOW, acquire, fetch, history, metadata, source  # noqa: F401
from test_daily_technicals import series


def daily_fetcher(fail=()):
    """Stands in for the real daily-bar request; records what it was asked."""
    calls = []

    def fetch_daily(ticker):
        calls.append(ticker)
        if ticker in fail:
            raise ValueError('DAILY_HISTORY_TOO_SHORT')
        return ({'rsi': 55.0, 'macd': 0.2, 'macd_signal': 0.1, 'macd_hist': 0.1,
                 'rvol': 1.3, 'last': 42.0, 'daily_sessions': 251},
                {'currency': 'CAD', 'exchange': 'TOR'})
    fetch_daily.calls = calls
    return fetch_daily


def biotech_snapshot(now, tickers=('ABEO', 'ABUS')):
    dates, closes, volumes = series(120)
    return {'as_of': (now - dt.timedelta(hours=2)).isoformat(),
            'securities': [{'ticker': t, 'currency': 'USD', 'exchange': 'NMS',
                            'daily_bars': [{'date': d, 'adjusted_close': c, 'volume': v}
                                           for d, c, v in zip(dates, closes, volumes)]}
                           for t in tickers]}


def run(tmp_path, monkeypatch, history, *, names=('NA.TO', 'GWO.TO'), lose=('NA.TO',), **kw):
    """`lose` names fail FIVE-MINUTE acquisition, which is the whole point.

    The daily pass deliberately skips a name that already has rsi/macd_hist/
    rvol — there is nothing to fill. So a fixture with a complete 5m panel for
    every name proves nothing about the pass. These tests make the 5m path lose
    a name the way it loses 53 of 130 in production, and assert the daily pass
    recovers it."""
    source(monkeypatch, [metadata(t) for t in names])

    def partial(tasks):
        result = acquire(tasks)
        for ticker in lose:
            if ticker in result:
                result[ticker] = {'status': 'UNAVAILABLE', 'error': 'ChartTimeoutError'}
        return result
    return F.prepare(tmp_path, CFG, now=NOW, fetcher=fetch(history),
                     acquire_fn=partial, **kw)


# ── the pass must do work, not merely return ─────────────────────────────────

def test_the_daily_pass_actually_fills_names(tmp_path, monkeypatch, history):
    """The assertion the original change lacked. `daily_filled` was 0 on a live
    run while every test passed, because none of them looked."""
    fetch_daily = daily_fetcher()
    result = run(tmp_path, monkeypatch, history, daily_fetcher=fetch_daily)
    assert result['daily_filled'] > 0, 'the daily pass did no work'
    assert fetch_daily.calls, 'the daily fetcher was never called'


def test_a_daily_filled_name_carries_the_indicators_it_was_missing(tmp_path, monkeypatch, history):
    run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher())
    pool = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    filled = [c for c in pool['candidates']
              if (c.get('technicals') or {}).get('rsi') is not None]
    assert filled, 'no candidate ended up with daily indicators'
    assert all(c['technicals'].get('macd_hist') is not None for c in filled)


def short_history():
    """Enough sessions for VWAP and the opening range, too few for MACD.

    This is the PARTIAL case and it is the one that matters: a name the
    five-minute path covered intraday but could not warm up. A fixture where
    every name is either complete or wholly absent never exercises the merge —
    a mutation replacing it with `dict(daily)` passed this whole file."""
    import math
    import pandas as pd
    from intraday_history import session_schedule
    frames = []
    for n, day in enumerate(session_schedule('2026-09-01', '2026-09-14').index):
        ix = pd.date_range(str(day.date()) + ' 09:30', periods=78, freq='5min', tz=ET)
        prices = [100 + math.sin(n / 3) + i / 1000 for i in range(78)]
        frames.append(pd.DataFrame(
            {'Open': prices, 'High': [x + .1 for x in prices],
             'Low': [x - .1 for x in prices], 'Close': prices,
             'Volume': [100 + i for i in range(78)]}, index=ix))
    bars = pd.concat(frames)
    return json.dumps({'columns': list(bars.columns),
                       'index': [i.isoformat() for i in bars.index],
                       'data': bars.to_numpy().tolist()})


def test_five_minute_values_win_where_both_exist(tmp_path, monkeypatch):
    """Daily fills what the warm-up could not produce; it must not overwrite an
    intraday fact with a daily one. VWAP is a session quantity and a daily
    close is not the 09:45 print."""
    run(tmp_path, monkeypatch, short_history(), lose=(), daily_fetcher=daily_fetcher())
    pool = json.loads((tmp_path / 'deepseek_candidates.json').read_text())
    merged = [c for c in pool['candidates']
              if (c.get('technicals') or {}).get('vwap') is not None
              and (c.get('technicals') or {}).get('macd_hist') is not None]
    assert merged, 'no candidate exercised the merge: the fixture proves nothing'
    for c in merged:
        t = c['technicals']
        assert t['last'] != 42.0, 'the daily close overwrote the intraday last'
        assert t['macd_hist'] == 0.1, 'the daily MACD should have filled the gap'


def test_a_daily_failure_is_a_named_gap_not_a_crash(tmp_path, monkeypatch, history):
    result = run(tmp_path, monkeypatch, history,
                 daily_fetcher=daily_fetcher(fail=('NA.TO',)))
    assert result['status'] in ('PARTIAL', 'UNAVAILABLE', 'READY')
    assert any('DAILY' in str(v) for v in result['daily_errors'].values())


def test_every_tsx_row_is_tagged_as_the_canadian_market(tmp_path, monkeypatch, history):
    run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher())
    pool = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    assert all(c.get('market') == 'CA' for c in pool['candidates'])


# ── biotech ──────────────────────────────────────────────────────────────────

def test_biotech_names_are_added_to_the_pool(tmp_path, monkeypatch, history):
    result = run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher(),
                 biotech_snapshot=biotech_snapshot(NOW))
    assert result['biotech_added'] == 2
    pool = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    tickers = {c['ticker'] for c in pool['candidates']}
    assert {'ABEO', 'ABUS'} <= tickers


def test_a_biotech_name_is_tagged_us_so_it_cannot_read_as_a_tsx_leg(tmp_path, monkeypatch, history):
    run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher(),
        biotech_snapshot=biotech_snapshot(NOW))
    pool = json.loads((tmp_path/'deepseek_candidates.json').read_text())
    bio = [c for c in pool['candidates'] if c['ticker'] == 'ABEO'][0]
    assert bio['market'] == 'US' and bio['currency'] == 'USD'


def test_a_stale_biotech_snapshot_adds_nothing_and_says_why(tmp_path, monkeypatch, history):
    result = run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher(),
                 biotech_snapshot=biotech_snapshot(NOW - dt.timedelta(days=3)))
    assert result['biotech_added'] == 0
    assert result.get('biotech_error') == 'BIOTECH_SNAPSHOT_STALE'


def test_the_requested_count_reflects_the_widened_pool(tmp_path, monkeypatch, history):
    """`requested` is what the page reports as the population. It must grow
    with the biotech names or the page understates what was considered."""
    base = run(tmp_path, monkeypatch, history, daily_fetcher=daily_fetcher())
    wide = run(tmp_path/'b', monkeypatch, history, daily_fetcher=daily_fetcher(),
               biotech_snapshot=biotech_snapshot(NOW))
    assert wide['requested'] > base['requested']


# ── the gate itself ──────────────────────────────────────────────────────────

def test_injection_is_detected_before_the_default_overwrites_it():
    """THE BUG. `fetcher = fetcher or fetch_history` runs near the top, so a
    gate reading `fetcher is None` afterwards is always False and the passes
    never run."""
    import inspect
    src = inspect.getsource(F._prepare)
    assert 'injected = fetcher is not None or acquire_fn is not None' in src
    assert (src.index('injected = fetcher is not None') <
            src.index('fetcher = fetcher or fetch_history'))
    assert 'daily_fetcher is None and fetcher is None' not in src
    assert 'biotech_snapshot is None and fetcher is None' not in src


def test_an_injected_run_never_reaches_the_network_by_itself(tmp_path, monkeypatch, history):
    """A caller that injects is running deterministically; the daily pass must
    not quietly open a socket behind its mock."""
    monkeypatch.setattr(F, 'ROOT', tmp_path/'no-such-root')
    result = run(tmp_path, monkeypatch, history)          # no daily_fetcher supplied
    assert result['daily_filled'] == 0
    assert result['biotech_added'] == 0


def test_injecting_only_the_acquirer_still_counts_as_deterministic(tmp_path, monkeypatch):
    """Several existing tests inject `acquire_fn` and NOT `fetcher`. Keying the
    gate on the fetcher alone let the daily pass open real sockets behind their
    mock and fill the very names they assert were not acquired."""
    source(monkeypatch, [metadata(t) for t in ('NA.TO', 'GWO.TO', 'IFC.TO')])
    monkeypatch.setattr(F.P, 'WORKERS', 2)
    monkeypatch.setattr(F, 'ROOT', tmp_path/'no-such-root')

    def unavailable(tasks):
        return {t: {'status': 'UNAVAILABLE', 'error': 'ChartRateLimitError'} for t in tasks}
    result = F.prepare(tmp_path, CFG, now=NOW, acquire_fn=unavailable)
    assert result['daily_filled'] == 0, 'the daily pass reached the network behind a mock'
    assert result['errors']['IFC.TO'] == 'NOT_ACQUIRED' 
