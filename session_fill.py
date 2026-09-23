"""Rebuild a daily bar the provider served as a NULL PLACEHOLDER, from its hourly bars.

MEASURED 2026-09-23 17:00 ET. Yahoo's daily series for 2026-09-22 is a
placeholder on many names — a timestamp with `close: null, volume: null` — a
full day after the session closed: SHOP.TO, RY.TO, ALLO, OTLK, ROIV, but not
SPY, AAPL or INO. `yfinance` and `_bars_df` drop the null row, so the series
simply skips a session. Two things then went wrong without an error:

  * `build_biotech` correctly refused every such name ("ADV20 history missing
    exchange sessions") — 371 of 971 — so the universe could not certify and
    Part 2 would have had no universe the next morning;
  * `daily_technicals` computed the "last session's move" and its true range
    against the close TWO sessions back, labelled as one.

The same session's 60-minute bars are complete (09:30 … 15:30, seven bars).
A rebuilt bar is open of the first, high/low over all, close of the last,
volume summed. What that bar is and is not:

  * its CLOSE is the last regular-session trade before 16:00, not the official
    close — measured within 0.02–0.5% of it on sessions that have both;
  * its VOLUME IS A LOWER BOUND: hourly bars exclude the closing auction and
    some off-exchange prints — measured at 41–99% of the daily figure (SPY
    ~0.85, AAPL 0.41–0.73, INO 0.59–0.99). One such session in a 20-session
    ADV lowers it by at most a few percent, and it is disclosed on the row.

Only a session the PROVIDER itself stamped (or the exchange calendar lists)
is filled, only from a regular session with both its 09:30 and 15:30 bars,
and at most MAX_FILLED per name. Anything else stays a hole and the caller's own refusal stands
(house rule 2: absence of data is not absence of movement).
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd

FIRST_BAR = dt.time(9, 30)
LAST_BAR = dt.time(15, 30)
# The BOOKENDS are required, not all seven hours: an illiquid name with no
# print between 14:30 and 15:30 has no bar for that hour (DRMA, QNRX on
# 2026-09-22), and its volume for that hour is zero, not missing.
MIN_BARS = 2
MAX_FILLED = 2


def placeholder_dates(raw, tz):
    """Sessions the provider stamped with a NULL close, as exchange-local dates."""
    ts = raw.get('timestamp') or []
    quote = ((raw.get('indicators') or {}).get('quote') or [{}])[0]
    closes = quote.get('close') or []
    out = []
    for i, stamp in enumerate(ts):
        close = closes[i] if i < len(closes) else None
        if close is None or (isinstance(close, float) and not math.isfinite(close)):
            out.append(pd.Timestamp(stamp, unit='s', tz='UTC').tz_convert(tz).date())
    return out


def session_bar(hourly, day):
    """One complete regular session from 60-minute bars, or None."""
    if hourly is None or hourly.empty:
        return None
    rows = hourly[[i.date() == day for i in hourly.index]]
    if len(rows) < MIN_BARS:
        return None
    times = [i.time() for i in rows.index]
    if times[0] != FIRST_BAR or times[-1] != LAST_BAR:
        return None
    values = rows[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)
    if not values.map(math.isfinite).all().all() or (values[['Open', 'High', 'Low', 'Close']] <= 0).any().any():
        return None
    return {'Open': float(values['Open'].iloc[0]), 'High': float(values['High'].max()),
            'Low': float(values['Low'].min()), 'Close': float(values['Close'].iloc[-1]),
            'Volume': float(values['Volume'].sum())}


def fill(daily, hourly, days):
    """Insert rebuilt bars for `days` missing from `daily`. Returns (frame, filled dates)."""
    have = {i.date() for i in daily.index}
    filled, rows = [], {}
    for day in sorted(set(days) - have)[-MAX_FILLED:]:
        bar = session_bar(hourly, day)
        if bar is None:
            continue
        stamp = (daily.index[0] if len(daily) else hourly.index[0])
        when = pd.Timestamp(dt.datetime.combine(day, stamp.time()), tz=stamp.tz)
        rows[when] = bar
        filled.append(day)
    if not rows:
        return daily, []
    extra = pd.DataFrame.from_dict(rows, orient='index')
    frame = pd.concat([daily, extra[[c for c in daily.columns if c in extra.columns]]])
    return frame.sort_index(), filled
