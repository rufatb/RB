"""Return context from existing chart bars with explicit reference semantics.

The daily source timestamp is a BAR timestamp, not an invented close time.
The previous returned bar is not certified as the immediate prior exchange
session. No quote, entitlement, executable price or signal is produced here.
"""
from __future__ import annotations

import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from quotes import number, stamp

_GAPS = frozenset(('DAILY_GRANULARITY_UNVERIFIED', 'INVALID_DAILY_REFERENCE_ARRAY',
    'DAILY_REFERENCE_MISSING', 'INVALID_DAILY_REFERENCE_TIMESTAMP',
    'DAILY_TIMESTAMPS_NOT_STRICTLY_INCREASING', 'DUPLICATE_DAILY_REFERENCE_DATE',
    'OBSERVATION_DATE_BAR_MISSING', 'FUTURE_DAILY_REFERENCE',
    'INVALID_DAILY_REFERENCE_VALUE', 'INVALID_MACRO_VALUE', 'NONFINITE_MACRO_CHANGE'))


def daily_change_context(chart, value, observed, source_url):
    """Derive a percent change only from a validated previous observed bar.

    Absolute levels survive any failure here. In particular, the provider's
    chartPreviousClose (range start for a five-day request) is never consulted.
    A bar on the actual observation date must exist to anchor the predecessor.
    """
    unavailable = {'change_status': 'UNAVAILABLE', 'change_scope': None,
                   'reference': None}
    try:
        meta = chart['meta']
        if meta.get('dataGranularity') != '1d':
            raise ValueError('DAILY_GRANULARITY_UNVERIFIED')
        zone = ZoneInfo(meta['exchangeTimezoneName'])
        raw_times = chart['timestamp']
        quotes = chart['indicators']['quote']
        if not isinstance(quotes, list) or len(quotes) != 1:
            raise ValueError('INVALID_DAILY_REFERENCE_ARRAY')
        closes = quotes[0]['close']
        if (not isinstance(raw_times, list) or not isinstance(closes, list)
                or len(raw_times) != len(closes) or len(raw_times) < 2):
            raise ValueError('DAILY_REFERENCE_MISSING')
        # Numeric epochs are the chart endpoint's contract; strings/bools do
        # not acquire authenticity merely because another parser accepts them.
        if any(type(raw) not in (int, float) for raw in raw_times):
            raise ValueError('INVALID_DAILY_REFERENCE_TIMESTAMP')
        times = [stamp(raw) for raw in raw_times]
        if any(a >= b for a, b in zip(times, times[1:])):
            raise ValueError('DAILY_TIMESTAMPS_NOT_STRICTLY_INCREASING')
        dates = [ts.astimezone(zone).date() for ts in times]
        # AN EMPTY PLACEHOLDER IS NOT A DUPLICATE. Measured 2026-09-22: Yahoo's
        # FX series (CADUSD=X, London) serves TODAY twice — a 00:00 bar whose
        # close is None and the live bar beside it — so `cadusd` read
        # UNAVAILABLE every morning. Only a None-close bar that shares its date
        # with a valued bar is dropped; two VALUED bars on one date are still
        # an ambiguity and still refused.
        valued = {d for d, c in zip(dates, closes) if c is not None}
        keep = [i for i, (d, c) in enumerate(zip(dates, closes))
                if not (c is None and d in valued and dates.count(d) > 1)]
        if len(keep) != len(dates):
            times = [times[i] for i in keep]
            closes = [closes[i] for i in keep]
            dates = [dates[i] for i in keep]
        if len(set(dates)) != len(dates):
            raise ValueError('DUPLICATE_DAILY_REFERENCE_DATE')
        observation = stamp(observed)
        if any(ts > observation for ts in times):
            raise ValueError('FUTURE_DAILY_REFERENCE')
        observed_day = observation.astimezone(zone).date()
        if observed_day not in dates:
            raise ValueError('OBSERVATION_DATE_BAR_MISSING')
        index = dates.index(observed_day)
        if index == 0:
            raise ValueError('DAILY_REFERENCE_MISSING')
        reference_time = times[index-1]
        if times[index] > observation or reference_time >= observation:
            raise ValueError('FUTURE_DAILY_REFERENCE')
        reference = number(closes[index-1], positive=True)
        if reference is None or type(closes[index-1]) not in (int, float):
            raise ValueError('INVALID_DAILY_REFERENCE_VALUE')
        current = number(value, positive=True)
        if current is None:
            raise ValueError('INVALID_MACRO_VALUE')
        change = (current/reference-1)*100
        if not math.isfinite(change):
            raise ValueError('NONFINITE_MACRO_CHANGE')
        # This denominator is the immediately preceding returned daily bar;
        # missing dates are disclosed by scope, never bridged into a one-day
        # exchange-session return claim.
        return {'change_status': 'READY',
                'change_pct': change,
                'change_scope': 'observed_level_vs_previous_daily_bar_close',
                'reference': {'value': reference,
                    'bar_timestamp': reference_time.isoformat(),
                    'source_url': source_url,
                    'scope': 'previous_observed_daily_bar_close', 'interval': '1d'}}
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, OSError,
            ZoneInfoNotFoundError) as exc:
        reason = (str(exc) if type(exc) is ValueError and str(exc) in _GAPS
                  else 'DAILY_REFERENCE_METADATA_UNAVAILABLE')
        return {**unavailable, 'change_gap': reason[:80]}
