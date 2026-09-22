"""RSI, MACD and RVOL from TRUE DAILY BARS, so coverage stops being the gate.

THE PROBLEM THIS SOLVES, measured 2026-09-18. The research pool derived its
daily indicators from a five-minute panel: it took the 15:55 bar of each
session as that day's close. Yahoo serves roughly 41 sessions of 5-minute
history, MACD needs 35 CONTIGUOUS complete sessions to warm up, and any
excluded session truncates the usable tail. The result, on a 130-name roster:

    130 requested -> 77 acquired -> 38 with complete technicals

and — the part that matters — **the same 38 names every single day**. Comparing
the 09-17 and 09-18 pools, the eligible set overlapped 38 of 38. The owner saw
the same handful of tickers recur every morning and was right about the cause
being upstream of the models; both models were choosing from a set that never
moved.

Widening the roster does NOT fix this. Day-109 already measured that: 60 -> 130
names moved assessed coverage 23 -> 29, because the binding constraint is the
warm-up, not the roster. Adding names adds names that fail the same gate.

A daily-bar request returns ~250 sessions of a year, so the 35-session warm-up
is met with two hundred sessions to spare, and it is a far smaller response
than a 60-day five-minute panel so it fails acquisition less often. Probed on
names that currently fail outright and names that currently lack MACD, every
one returned 251-252 clean daily bars.

WHAT THIS DOES NOT CHANGE. The baseline 21-name board is computed by `r945` on
its own path and is untouched. This module feeds the RESEARCH POOL only — the
population the shadow model sections choose from. No baseline feature, rule,
selection, size or threshold moves because of anything here.

HOUSE RULE 9 IS THE WHOLE RISK. Yahoo answers `interval=1d` with WEEKLY,
MONTHLY or QUARTERLY bars and no error — day-72 shipped a "3-day event window"
that was three months on some names for four days. Granularity is asserted
against the returned index here, every time, and a frame that is not daily is
REJECTED rather than silently used.
"""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

import pandas as pd

from metrics import macd, rsi

ET = ZoneInfo('America/New_York')

# MACD(12,26,9) needs 26 + 9 to be defined at all; RVOL compares the last
# session with the mean of 20 before it. Ask for a year and require a floor
# well above both, so a short-listed or recently-listed name is EXCLUDED and
# said to be excluded rather than scored on a half-warm indicator.
MIN_SESSIONS = 60
MAX_MEDIAN_GAP_DAYS = 4.0       # a genuine daily series over weekends
MAX_LONG_GAP_SHARE = 0.10       # tolerate holidays, reject a weekly series
RVOL_WINDOW = 20


class GranularityError(ValueError):
    """The provider returned something other than daily bars."""


def assert_daily(index):
    """Reject a frame whose spacing is not daily. House rule 9, verbatim.

    A weekly series passes every other check in this module — it has closes, it
    has volumes, it computes an RSI — and is wrong by a factor of five. The
    only defence is to measure the spacing of what actually arrived."""
    stamps = pd.to_datetime(pd.Series(list(index)))
    if len(stamps) < 2:
        raise GranularityError('DAILY_GRANULARITY_UNVERIFIABLE')
    gaps = stamps.diff().dt.total_seconds().dropna()/86400.0
    if gaps.empty or not float(gaps.median()) or float(gaps.median()) > MAX_MEDIAN_GAP_DAYS:
        raise GranularityError('NOT_DAILY_BARS')
    if float((gaps > 6.0).mean()) > MAX_LONG_GAP_SHARE:
        raise GranularityError('NOT_DAILY_BARS')
    if not stamps.is_monotonic_increasing:
        raise GranularityError('DAILY_BARS_OUT_OF_ORDER')
    return True


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def from_series(dates, closes, volumes, *, now, opens=None, highs=None, lows=None):
    """Daily indicators from completed sessions only.

    `now` is used to DROP today's partial bar. A session in progress has a
    close that is really the last trade, and folding it in would make every
    indicator peek at the day it is supposed to precede.
    """
    frame = pd.DataFrame({'date': pd.to_datetime(pd.Series(list(dates))),
                          'close': [ _finite(c) for c in closes ],
                          'volume': [ _finite(v) for v in volumes ]})
    if opens is not None:
        frame['open'] = [ _finite(o) for o in opens ]
    if highs is not None and lows is not None:
        frame['high'] = [ _finite(h) for h in highs ]
        frame['low'] = [ _finite(l) for l in lows ]
    frame = frame.dropna(subset=['date', 'close'])
    frame = frame[frame['close'] > 0]
    cutoff = pd.Timestamp(now.astimezone(ET).date())
    frame = frame[frame['date'].dt.tz_localize(None).dt.normalize() < cutoff]
    frame = frame.sort_values('date').drop_duplicates(subset='date', keep='last')
    if len(frame) < MIN_SESSIONS:
        raise ValueError('DAILY_HISTORY_TOO_SHORT')
    assert_daily(frame['date'])

    closes = frame['close'].astype(float).reset_index(drop=True)
    momentum = macd(closes)
    volumes = frame['volume'].astype(float).reset_index(drop=True)
    prior = volumes.iloc[-(RVOL_WINDOW+1):-1]
    mean_prior = float(prior.mean()) if len(prior) == RVOL_WINDOW else None
    rvol = (float(volumes.iloc[-1])/mean_prior
            if mean_prior and mean_prior > 0 and _finite(volumes.iloc[-1]) else None)
    last = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    out = {'rsi': rsi(closes), 'macd': momentum['macd'], 'macd_signal': momentum['signal'],
           'macd_hist': momentum['hist'], 'rvol': rvol, 'last': last,
           'volume': _finite(volumes.iloc[-1]),
           'daily_sessions': int(len(frame)),
           'daily_close_prev': previous}
    if 'open' in frame.columns and _finite(frame['open'].iloc[-1]):
        session_open = float(frame['open'].iloc[-1])
        out['open'] = session_open
        out['gap'] = 100.0*(session_open-previous)/previous if previous else None
    out.update(context(frame, closes, last, previous))
    return {k: v for k, v in out.items() if v is not None}


# ── CONTEXT: scale and location, from bars already fetched ──────────────────
# Day-113 review, item 1. The models were handed RAW percentages and compared
# a +0.85% gap on one name with a +1.99% gap on another as if they were the
# same size of event. They are not: size is only meaningful against what the
# name normally does. Everything here is arithmetic over the ~250 completed
# sessions this module already has — no new request — and every value
# describes the LAST COMPLETED SESSION, never today (see `now` above).
CONTEXT_KEYS = ('atr_pct', 'gap_atr', 'move_atr', 'sma50_pct', 'sma200_pct',
                'range52_pos', 'prev_high', 'prev_low', 'prev_close')
ATR_WINDOW = 14


def context(frame, closes, last, previous):
    out = {'prev_close': last}
    n = len(closes)
    for window, key in ((50, 'sma50_pct'), (200, 'sma200_pct')):
        if n >= window:
            sma = float(closes.iloc[-window:].mean())
            out[key] = 100.0*(last/sma - 1) if sma > 0 else None
    tail = closes.iloc[-252:]
    hi, lo = float(tail.max()), float(tail.min())
    out['range52_pos'] = (last-lo)/(hi-lo) if hi > lo else None
    if 'high' in frame.columns and 'low' in frame.columns:
        highs = frame['high'].astype(float).reset_index(drop=True)
        lows = frame['low'].astype(float).reset_index(drop=True)
        if _finite(highs.iloc[-1]) and _finite(lows.iloc[-1]) and highs.iloc[-1] >= lows.iloc[-1] > 0:
            out['prev_high'], out['prev_low'] = float(highs.iloc[-1]), float(lows.iloc[-1])
        prior = closes.shift(1)
        tr = pd.concat([highs-lows, (highs-prior).abs(), (lows-prior).abs()], axis=1).max(axis=1)
        window = tr.iloc[-ATR_WINDOW:]
        if len(window) == ATR_WINDOW and window.notna().all():
            atr = float(window.mean())
            if atr > 0:
                out['atr_pct'] = 100.0*atr/last
                out['move_atr'] = (last-previous)/atr
                if 'open' in frame.columns and _finite(frame['open'].iloc[-1]):
                    out['gap_atr'] = (float(frame['open'].iloc[-1])-previous)/atr
    return out


def scope(sessions):
    """The provenance line that travels with these numbers."""
    return ('previous_completed_session; daily RSI/MACD/RVOL from %d completed DAILY bars '
            '(granularity asserted)' % sessions)


def from_yahoo(ticker, adapter, now, *, interval='1d', window='1y'):
    """Fetch and validate one name's daily bars. Identity is checked, not assumed."""
    raw = adapter._chart(ticker, interval, window)
    meta = raw.get('meta') or {}
    if meta.get('symbol') != ticker or meta.get('instrumentType') != 'EQUITY':
        raise ValueError('DAILY_IDENTITY_NOT_VERIFIED')
    frame = adapter._bars_df(raw)
    if frame.empty:
        raise ValueError('DAILY_HISTORY_EMPTY')
    has = lambda c: frame[c] if c in frame.columns else None
    technicals = from_series(frame.index, frame['Close'], frame['Volume'], now=now,
                             opens=has('Open'), highs=has('High'), lows=has('Low'))
    return technicals, {'currency': meta.get('currency'),
                        'exchange': meta.get('exchangeName')}


def from_biotech_snapshot(snapshot, now, *, max_age_hours=30, limit=None):
    """Candidates from the ALREADY-STAGED biotech daily bars — no new fetching.

    `build_biotech.py` stages US biotech securities with `daily_bars` attached,
    which is exactly the input these indicators need. Folding them in widens the
    population the models choose from at zero acquisition cost.

    THESE ARE A DIFFERENT MARKET. US exchanges, USD, and the baseline engine
    neither scores nor prices them. Every row is tagged `market` and `currency`
    so a biotech name can never be read as a TSX board leg, and the tag travels
    all the way to the page.
    """
    if not isinstance(snapshot, dict):
        raise ValueError('BIOTECH_SNAPSHOT_INVALID')
    staged = snapshot.get('as_of')
    try:
        observed = dt.datetime.fromisoformat(staged)
    except (TypeError, ValueError):
        raise ValueError('BIOTECH_SNAPSHOT_UNDATED') from None
    if observed.tzinfo is None:
        raise ValueError('BIOTECH_SNAPSHOT_NAIVE_CLOCK')
    age = (now - observed).total_seconds()/3600.0
    if age < 0 or age > max_age_hours:
        raise ValueError('BIOTECH_SNAPSHOT_STALE')
    out, gaps = [], {}
    for security in (snapshot.get('securities') or []):
        ticker = security.get('ticker') if isinstance(security, dict) else None
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        bars = security.get('daily_bars')
        if not isinstance(bars, list) or len(bars) < MIN_SESSIONS:
            gaps[ticker] = 'BIOTECH_DAILY_HISTORY_TOO_SHORT'
            continue
        try:
            technicals = from_series([b.get('date') for b in bars],
                                     [b.get('adjusted_close') for b in bars],
                                     [b.get('volume') for b in bars], now=now)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            gaps[ticker] = ('BIOTECH_' + (str(exc) if isinstance(exc, ValueError)
                                          and str(exc).isupper() else type(exc).__name__))
            continue
        out.append({'ticker': ticker, 'technicals': technicals,
                    'technicals_as_of': observed.isoformat(),
                    'technicals_scope': scope(technicals['daily_sessions']),
                    'technical_source': 'python',
                    'market': 'US', 'currency': security.get('currency') or 'USD',
                    'sector': 'Biotechnology',
                    'source_url': 'https://query1.finance.yahoo.com/v8/finance/chart/'+ticker})
        if limit and len(out) >= limit:
            break
    return out, gaps
