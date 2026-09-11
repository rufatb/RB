"""Validate production training labels on the exchange's actual five-minute grid.

Pure, no acquisition or fitting. Retained research can still call the legacy
r945.session_rows extractor; these labels are explicitly regular-close proxies.
"""
from functools import lru_cache
import datetime as dt

import numpy as np
import pandas as pd

FIELDS = ['Open', 'High', 'Low', 'Close', 'Volume']


@lru_cache(maxsize=32)
def session_schedule(start, end, calendar='TSX'):
    import pandas_market_calendars as mcal
    return mcal.get_calendar(calendar).schedule(start_date=start, end_date=end)


def ohlcv_error(frame):
    """Return a bounded, credential-free data-contract reason."""
    if not set(FIELDS).issubset(frame.columns):
        return 'MISSING_OHLCV_FIELDS'
    try:
        values = frame[FIELDS].to_numpy(dtype=float)
    except (ValueError, TypeError):
        return 'NONNUMERIC_OHLCV'
    if not np.isfinite(values).all():
        return 'NONFINITE_OHLCV'
    o, h, l, c, v = values.T
    if (values[:, :4] <= 0).any() or (v < 0).any():
        return 'NONPOSITIVE_PRICE_OR_NEGATIVE_VOLUME'
    if ((h < np.maximum(o, c)) | (l > np.minimum(o, c)) | (h < l)).any():
        return 'INCONSISTENT_OHLC'
    return None


def completed_history(bars, ticker, now, calendar='TSX', timezone='America/New_York'):
    """Rows strictly before `now`'s local date, with immediate-session gaps.

    A full standard session has 78 start-labelled bars, 09:30 through 15:55.
    Count out-of-session observations; they never define the close or features.
    A missing/invalid session breaks the prior-close chain. A verified short
    session may supply its closing reference but is not a full-horizon label.
    """
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError('aware history cutoff required')
    now = now.tz_convert(timezone)
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError('history requires aware DatetimeIndex')
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('duplicate or unsorted history timestamps')
    if not set(FIELDS).issubset(bars.columns):
        raise ValueError('history missing OHLCV fields')
    frame = bars.copy()
    frame.index = frame.index.tz_convert(timezone)
    # No outcome from today is complete for a morning model, even when an
    # afternoon preview is invoked later. Future observations never enter X/y.
    frame = frame[[d < now.date() for d in frame.index.date]]
    audit = dict(ticker=ticker, raw_sessions=0, accepted_sessions=0,
                 rejected_sessions=0, missing_previous_closes=0,
                 outside_session_bars=0, exclusions=[],
                 label='Completed opening reference to final regular-bar close proxy')
    if frame.empty:
        return {'rows': [], 'prior_close': None, 'diagnostics': audit}
    grouped = {d: g for d, g in frame.groupby(frame.index.date)}
    audit['raw_sessions'] = len(grouped)
    first = min(grouped)
    cal = session_schedule(first.isoformat(), (now.date()-dt.timedelta(days=1)).isoformat(), calendar)
    trading_dates = {i.date() for i in cal.index}
    for d, g in grouped.items():
        if d not in trading_dates:
            audit['outside_session_bars'] += len(g)
            audit['exclusions'].append(dict(session=str(d), reason='NON_SESSION_DATE'))
    previous = None
    rows = []
    for date, session in cal.iterrows():
        day = grouped.get(date.date())
        grid = pd.date_range(session['market_open'], session['market_close'],
                             freq='5min', inclusive='left').tz_convert(timezone)
        reason = None
        if day is None:
            reason = 'MISSING_SESSION'
        else:
            regular = day[(day.index >= grid[0]) &
                          (day.index < session['market_close'])]
            audit['outside_session_bars'] += len(day)-len(regular)
            if not regular.index.equals(grid):
                reason = 'INCOMPLETE_OR_WRONG_INTERVAL'
            else:
                reason = ohlcv_error(regular)
        if reason:
            audit['rejected_sessions'] += 1
            audit['exclusions'].append(dict(session=str(date.date()), reason=reason))
            previous = None
            continue
        o = float(regular['Open'].iloc[0])
        c = float(regular['Close'].iloc[-1])
        if len(grid) != 78 or grid[0].time() != dt.time(9, 30) or grid[-1].time() != dt.time(15, 55):
            audit['rejected_sessions'] += 1
            audit['exclusions'].append(dict(session=str(date.date()), reason='SHORT_OR_NONSTANDARD_SESSION'))
            previous = c
            continue
        p945 = float(regular['Close'].iloc[2])
        after = regular.iloc[3:]
        if previous is None:
            audit['missing_previous_closes'] += 1
            audit['exclusions'].append(dict(session=str(date.date()), reason='PRIOR_SESSION_CLOSE_UNAVAILABLE'))
        rows.append(dict(t=ticker, date=str(date.date()),
                         gap=(o/previous-1)*100 if previous is not None else None,
                         r0=(p945/o-1)*100, v15=float(regular['Volume'].iloc[:3].sum()),
                         r1=(c/p945-1)*100,
                         mae_dn=(float(after['Low'].min())/p945-1)*100,
                         mae_up=(float(after['High'].max())/p945-1)*100))
        previous = c
        audit['accepted_sessions'] += 1
    return {'rows': rows, 'prior_close': previous, 'diagnostics': audit}
