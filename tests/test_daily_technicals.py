"""Daily-bar technicals: the fix for "the same tickers every single day".

MEASURED, 2026-09-18. The pool derived daily indicators from a five-minute
panel, MACD needs 35 contiguous complete sessions, and Yahoo serves ~41
sessions of 5-minute history. Result: 130 requested, 77 acquired, 38 complete —
and the SAME 38 as the previous session, 38 of 38 overlap. Both models were
choosing from a set that never moved.

The risk this module carries is house rule 9: Yahoo answers `interval=1d` with
WEEKLY or MONTHLY bars and no error, and a weekly series passes every other
check here — it has closes, it has volumes, it computes an RSI, and it is wrong
by a factor of five. So granularity is asserted against what actually arrived.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

import daily_technicals as D

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 9, 18, 9, 5, tzinfo=ET)


def series(n=120, *, step_days=1, close=100.0, volume=1_000_000, end=None):
    """Bars ENDING the session before NOW, walking backwards.

    Building forward from a fixed start put a weekly fixture's tail beyond
    today, so the point-in-time cutoff truncated it and it failed on LENGTH
    before the granularity assertion ever saw it — the test would have passed
    for the wrong reason. Closes oscillate because a strictly monotonic series
    has no down moves, which makes RSI degenerate."""
    end = end or (NOW.date() - dt.timedelta(days=1))
    dates, closes, volumes = [], [], []
    day = end
    for i in range(n):
        dates.append(day.isoformat())
        closes.append(close + (i % 7)*0.8 - (i % 3)*0.5)
        volumes.append(volume)
        day -= dt.timedelta(days=step_days)
    return list(reversed(dates)), list(reversed(closes)), list(reversed(volumes))


# ── house rule 9: verify the data you GOT ────────────────────────────────────

def test_a_weekly_series_is_rejected_not_scored():
    """The day-72 failure, exactly: a 'daily' request answered with weekly bars
    and no error, and it shipped for four days."""
    dates, closes, volumes = series(80, step_days=7)
    with pytest.raises(D.GranularityError):
        D.from_series(dates, closes, volumes, now=NOW)


def test_a_monthly_series_is_rejected():
    dates, closes, volumes = series(70, step_days=30)
    with pytest.raises(D.GranularityError):
        D.from_series(dates, closes, volumes, now=NOW)


def test_a_genuine_daily_series_passes_the_granularity_assertion():
    dates, closes, volumes = series(120)
    out = D.from_series(dates, closes, volumes, now=NOW)
    assert out['rsi'] is not None and out['macd_hist'] is not None


def test_weekend_gaps_do_not_look_like_a_weekly_series():
    """Real daily bars skip weekends; that must not read as weekly."""
    dates, closes, volumes = [], [], []
    day, i = NOW.date() - dt.timedelta(days=1), 0
    while len(dates) < 120:
        if day.weekday() < 5:
            dates.append(day.isoformat())
            closes.append(100 + (i % 7)*0.8 - (i % 3)*0.5)
            volumes.append(900_000); i += 1
        day -= dt.timedelta(days=1)
    dates, closes, volumes = list(reversed(dates)), list(reversed(closes)), list(reversed(volumes))
    assert D.from_series(dates, closes, volumes, now=NOW)['rsi'] is not None


def test_assert_daily_refuses_bars_out_of_order():
    """`from_series` sorts before asserting, which is fair normalisation, so
    the ordering guarantee belongs to `assert_daily` and is tested there."""
    dates, _, _ = series(120)
    with pytest.raises(D.GranularityError):
        D.assert_daily(list(reversed(dates)))


# ── the point-in-time boundary ───────────────────────────────────────────────

def test_todays_partial_bar_is_dropped():
    """A session in progress has a 'close' that is really the last trade.
    Folding it in makes every indicator peek at the day it precedes."""
    dates, closes, volumes = series(120)
    dates.append(NOW.date().isoformat()); closes.append(999.0); volumes.append(5_000_000)
    out = D.from_series(dates, closes, volumes, now=NOW)
    assert out['last'] != 999.0


def test_a_future_dated_bar_is_dropped():
    dates, closes, volumes = series(120)
    dates.append((NOW.date()+dt.timedelta(days=3)).isoformat())
    closes.append(888.0); volumes.append(1)
    assert D.from_series(dates, closes, volumes, now=NOW)['last'] != 888.0


def test_too_little_history_is_refused_rather_than_half_warm():
    dates, closes, volumes = series(D.MIN_SESSIONS - 1)
    with pytest.raises(ValueError, match='DAILY_HISTORY_TOO_SHORT'):
        D.from_series(dates, closes, volumes, now=NOW)


def test_the_floor_clears_what_macd_and_rvol_actually_need():
    """MACD(12,26,9) needs 26+9; RVOL compares against 20 prior sessions."""
    assert D.MIN_SESSIONS > 26 + 9 and D.MIN_SESSIONS > D.RVOL_WINDOW + 1


def test_nonfinite_and_nonpositive_closes_are_excluded():
    dates, closes, volumes = series(130)
    closes[5] = float('nan'); closes[6] = 0.0; closes[7] = -3.0
    out = D.from_series(dates, closes, volumes, now=NOW)
    assert out['daily_sessions'] == 127


def test_rvol_is_the_last_session_over_twenty_priors():
    dates, closes, volumes = series(120, volume=1_000_000)
    volumes[-1] = 2_500_000
    assert D.from_series(dates, closes, volumes, now=NOW)['rvol'] == pytest.approx(2.5, rel=1e-6)


def test_rvol_is_absent_rather_than_wrong_when_a_volume_is_missing():
    dates, closes, volumes = series(120)
    volumes[-5] = None
    out = D.from_series(dates, closes, volumes, now=NOW)
    assert 'rvol' not in out or out['rvol'] is not None


def test_the_scope_line_states_the_session_count_and_the_assertion():
    text = D.scope(251)
    assert '251' in text and 'DAILY' in text and 'granularity asserted' in text


# ── biotech, from bars already on disk ───────────────────────────────────────

def snapshot(as_of=None, n=120, ticker='ABEO'):
    dates, closes, volumes = series(n)
    return {'as_of': (as_of or (NOW - dt.timedelta(hours=2))).isoformat(),
            'securities': [{'ticker': ticker, 'currency': 'USD', 'exchange': 'NMS',
                            'daily_bars': [{'date': d, 'adjusted_close': c, 'volume': v}
                                           for d, c, v in zip(dates, closes, volumes)]}]}


def test_biotech_candidates_come_from_staged_bars_with_no_fetching():
    rows, gaps = D.from_biotech_snapshot(snapshot(), NOW)
    assert len(rows) == 1 and rows[0]['ticker'] == 'ABEO'
    assert rows[0]['technicals']['rsi'] is not None


def test_every_biotech_row_is_tagged_as_a_different_market():
    """These are US, USD, and the baseline engine neither scores nor prices
    them. Untagged, a biotech name reads as a TSX board leg."""
    rows, _ = D.from_biotech_snapshot(snapshot(), NOW)
    assert rows[0]['market'] == 'US' and rows[0]['currency'] == 'USD'
    assert rows[0]['sector'] == 'Biotechnology'


def test_a_stale_biotech_snapshot_is_refused():
    """A three-day-old snapshot prices a different week."""
    with pytest.raises(ValueError, match='BIOTECH_SNAPSHOT_STALE'):
        D.from_biotech_snapshot(snapshot(as_of=NOW - dt.timedelta(days=3)), NOW)


def test_a_future_dated_biotech_snapshot_is_refused():
    with pytest.raises(ValueError, match='BIOTECH_SNAPSHOT_STALE'):
        D.from_biotech_snapshot(snapshot(as_of=NOW + dt.timedelta(hours=2)), NOW)


def test_an_undated_biotech_snapshot_is_refused():
    with pytest.raises(ValueError, match='BIOTECH_SNAPSHOT_UNDATED'):
        D.from_biotech_snapshot({'securities': []}, NOW)


def test_a_naive_biotech_clock_is_refused():
    snap = snapshot()
    snap['as_of'] = '2026-09-18T07:00:00'
    with pytest.raises(ValueError, match='BIOTECH_SNAPSHOT_NAIVE_CLOCK'):
        D.from_biotech_snapshot(snap, NOW)


def test_a_biotech_name_with_too_little_history_is_a_named_gap_not_a_silent_drop():
    rows, gaps = D.from_biotech_snapshot(snapshot(n=10), NOW)
    assert rows == [] and gaps['ABEO'].startswith('BIOTECH_')


def test_a_weekly_biotech_series_is_rejected_too():
    snap = snapshot()
    bars = snap['securities'][0]['daily_bars']
    day = dt.date(2026, 1, 5)
    for bar in bars:
        bar['date'] = day.isoformat(); day += dt.timedelta(days=7)
    rows, gaps = D.from_biotech_snapshot(snap, NOW)
    assert rows == [] and 'ABEO' in gaps


def test_a_mostly_daily_series_riddled_with_holes_is_rejected():
    """The median gap catches a WEEKLY series. It does not catch a series that
    is daily for stretches and then jumps a fortnight — a thinly traded name
    that simply does not print every session. Its median gap is still 1.0 day
    while a quarter of its history is missing, so RSI and MACD would be
    computed across holes as though the sessions were adjacent."""
    dates, closes, volumes = [], [], []
    day = NOW.date() - dt.timedelta(days=1)
    for i in range(120):
        dates.append(day.isoformat())
        closes.append(100 + (i % 7)*0.8 - (i % 3)*0.5)
        volumes.append(800_000)
        day -= dt.timedelta(days=1 if i % 4 else 21)   # median still 1 day
    dates, closes, volumes = list(reversed(dates)), list(reversed(closes)), list(reversed(volumes))
    import pandas as pd
    gaps = pd.to_datetime(pd.Series(dates)).diff().dt.days.dropna()
    assert gaps.median() == 1.0, 'the median must stay daily or this proves nothing'
    with pytest.raises(D.GranularityError):
        D.from_series(dates, closes, volumes, now=NOW)
