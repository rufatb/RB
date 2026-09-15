"""A missing pre-open cache must cost latency, not the day's board.

2026-09-14 and 2026-09-15 both published a board with ZERO names evaluated and
emailed "SCAN UNAVAILABLE — the scan did not establish whether opportunities
existed". The feed was healthy on both mornings: the whole TSX-21 fetched live
in 4.1-5.1 seconds against a 22-second budget with no errors. The cause was a
guard — `require_cache` — added after the 2026-09-10 timeout, which RAISED when
no cache directory was staged.

The budget the guard protects is real. Refusing to run was not the way to
protect it, and CLAUDE.md already says why the substitution is safe: pre-open
caching "changes acquisition only, not baseline features or rules", so the live
path produces the same board.

House rule 1 still governs: the fallback is counted, named per ticker, carried
in the frozen computation, and printed in the email.
"""
import datetime as dt
import json

import pandas as pd
import pytest

import bar_cache


NOW = dt.datetime(2026, 9, 15, 9, 46, tzinfo=dt.timezone(dt.timedelta(hours=-4)))


class Adapter:
    name = 'fixture'
    exchange_tz = 'America/New_York'

    def __init__(self):
        self.charts = []

    def _chart(self, ticker, interval, rng):
        self.charts.append(rng)
        idx = pd.DatetimeIndex(['2026-09-14T09:30:00-04:00', '2026-09-15T09:30:00-04:00']
                               ).tz_convert('America/New_York')
        frame = pd.DataFrame({'Open': [10., 11.], 'High': [12., 13.], 'Low': [9., 10.],
                              'Close': [11., 12.], 'Volume': [100., 200.]}, index=idx)
        return frame if rng == '60d' else frame.iloc[1:]

    def _bars_df(self, value):
        return value


def manifest(tmp_path, **over):
    body = {'complete': True, 'session': NOW.date().isoformat(),
            'source': 'fixture', 'tickers': ['A']}
    body.update(over)
    (tmp_path/'manifest.json').write_text(json.dumps(body))
    (tmp_path/bar_cache.key('A')).write_text(json.dumps(
        {'ticker': 'A', 'session': NOW.date().isoformat(),
         'frame': Adapter()._chart('A', '5m', '60d').iloc[:1].to_json(
             orient='split', date_format='iso', double_precision=15)}))
    return body


# ── cache_ready answers the question that actually matters ────────────────

def test_the_variable_being_set_is_not_the_question(tmp_path, monkeypatch):
    """2026-09-15: the variable WAS exported and the board was still empty,
    because the manifest was staged for 2026-09-11."""
    manifest(tmp_path, session='2026-09-11')
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    ok, why = bar_cache.cache_ready(Adapter(), NOW)
    assert ok is False
    assert '2026-09-11' in why and '2026-09-15' in why, why


def test_a_cache_from_another_source_cannot_serve(tmp_path, monkeypatch):
    manifest(tmp_path, source='someone_else')
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    ok, why = bar_cache.cache_ready(Adapter(), NOW)
    assert ok is False and 'someone_else' in why


def test_a_usable_cache_reports_ready(tmp_path, monkeypatch):
    manifest(tmp_path)
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    assert bar_cache.cache_ready(Adapter(), NOW) == (True, None)


def test_an_unreadable_manifest_is_a_miss_not_a_crash(tmp_path, monkeypatch):
    (tmp_path/'manifest.json').write_text('{not json')
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    ok, why = bar_cache.cache_ready(Adapter(), NOW)
    assert ok is False and 'unreadable' in why


# ── the fallback itself ───────────────────────────────────────────────────

def test_a_stale_cache_falls_back_and_says_which_names(tmp_path, monkeypatch):
    manifest(tmp_path, session='2026-09-11')
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    adapter = Adapter()
    told = []
    bars = bar_cache.get_bars(adapter, 'A', NOW, on_fallback=lambda t, why: told.append((t, why)))
    assert not bars.empty
    assert adapter.charts == ['60d'], 'the fallback must fetch full history, not the cached slice'
    assert told == [('A', told[0][1])] and 'session' in told[0][1]


@pytest.mark.parametrize('broken', [
    {'session': '2026-09-11'},          # staged for another session
    {'source': 'someone_else'},         # staged from another provider
    {'complete': False},                # staging did not finish
    {'tickers': []},                    # name outside the staged universe
])
def test_every_way_a_cache_can_miss_is_reported(tmp_path, monkeypatch, broken):
    """House rule 1, behaviourally rather than by grepping the source — a
    source assertion here would fire on this module's own docstring, which is
    the trap `test_morning.code()` and `test_deploy_units.directives()` exist
    to avoid. Each route must serve bars AND name its reason."""
    manifest(tmp_path, **broken)
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    adapter = Adapter()
    told = []
    bars = bar_cache.get_bars(adapter, 'A', NOW, on_fallback=lambda t, w: told.append(w))
    assert not bars.empty, 'a cache miss must not cost the board'
    assert adapter.charts == ['60d']
    assert told and told[0].strip(), f'silent fallback for {broken}'


def test_a_leaking_cache_is_discarded_rather_than_trusted(tmp_path, monkeypatch):
    """A pre-open cache holding TODAY's bars would put the future into the
    training window. Falling back to live is the safe answer, not a lenient
    one — and it is reported, which is how it gets noticed."""
    (tmp_path/'manifest.json').write_text(json.dumps(
        {'complete': True, 'session': NOW.date().isoformat(),
         'source': 'fixture', 'tickers': ['A']}))
    leaking = Adapter()._chart('A', '5m', '60d')          # includes today
    (tmp_path/bar_cache.key('A')).write_text(json.dumps(
        {'ticker': 'A', 'session': NOW.date().isoformat(),
         'frame': leaking.to_json(orient='split', date_format='iso', double_precision=15)}))
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    told = []
    bar_cache.get_bars(Adapter(), 'A', NOW, on_fallback=lambda t, w: told.append(w))
    assert told and 'today/future' in told[0]


def test_no_cache_configured_still_serves_history(monkeypatch):
    monkeypatch.delenv('RB_INTRADAY_CACHE_DIR', raising=False)
    adapter = Adapter()
    told = []
    bars = bar_cache.get_bars(adapter, 'A', NOW, on_fallback=lambda t, w: told.append(w))
    assert not bars.empty and adapter.charts == ['60d']
    assert told == ['no cache directory configured']


def test_a_usable_cache_is_still_preferred(tmp_path, monkeypatch):
    """The fallback must not quietly replace the fast path — that would undo
    the 2026-09-10 fix and put 60 days per name back on the 22s budget."""
    manifest(tmp_path)
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR', str(tmp_path))
    adapter = Adapter()
    told = []
    bar_cache.get_bars(adapter, 'A', NOW, on_fallback=lambda t, w: told.append(w))
    assert adapter.charts == ['1d'], 'a good cache must not trigger a 60-day fetch'
    assert told == []


# ── it has to reach the reader ────────────────────────────────────────────

def test_the_email_reports_the_degradation():
    import daily_render
    import email_render
    res = {'cache_degraded': 'no prepared cache directory configured',
           'cache_fallbacks': {'A.TO': 'cache staged for session 2026-09-11, not 2026-09-15'}}
    line = '\n'.join(daily_render.cache_lines(res))
    assert 'DEGRADED' in line and '1 name' in line
    assert 'not features or selection rules' in line, \
        'the reader must be told the board itself is unaffected'
    assert 'pre-open staging job did not run' in line
    assert daily_render.cache_lines({}) == [], 'a healthy cache says nothing'
    assert email_render.full.cache_lines(res), 'the concise email lost it'
