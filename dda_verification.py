"""Bounded paid-FMP verification for the proposed DDA cases, never a replay.

Dates without times cannot prove that same-day actuals were known pre-open.
Current provider observations are labelled explicitly; no historical PIT claim.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import math
import time

from dda_protocol import stamp, words


def verify(cases, root, now, *, get=None, seconds=18, clock=time.monotonic):
    import fmp_client as F
    if not cases:
        return []
    until = clock()+max(0, seconds)
    if get is None:
        key = F.load_key(root)
        def get(path, **params):
            return F.get(path, key, timeout=max(.1, min(5, until-clock())), retries=0, **params)
    today = stamp(now).date().isoformat()
    def one(case):
        ticker = case['ticker']
        receipt = {'ticker': ticker, 'provider': 'FMP', 'observed_at': stamp(now).isoformat(),
                   'source_url': 'https://financialmodelingprep.com/stable/earnings',
                   'parameters': {'symbol': ticker, 'limit': 8}, 'earnings': [],
                   'limitations': ['Provider observation, not historical point-in-time consensus.',
                       'Same-day actuals excluded: this endpoint supplies a date, not the disclosure time.',
                       'Currency not supplied; do not compare to another currency or fiscal period.']}
        try:
            if clock() >= until:
                raise ValueError('DDA_FMP_BUDGET')
            rows = get('earnings', symbol=ticker, limit=8)
            if not isinstance(rows, list):
                raise ValueError('DDA_FMP_RESPONSE')
            for row in rows[:16]:
                date = words(row.get('date'), 10)
                try:
                    dt.date.fromisoformat(date)
                except ValueError:
                    continue
                if date >= today:  # Upcoming schedules only; never today's actuals.
                    receipt.setdefault('scheduled_dates', []).append(date)
                    continue
                clean = {'date': date}
                for field in ('epsActual', 'epsEstimated', 'revenueActual', 'revenueEstimated'):
                    value = row.get(field)
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        clean[field] = value
                receipt['earnings'].append(clean)
            receipt['status'] = 'AVAILABLE' if receipt['earnings'] else 'NO_PRIOR_ACTUALS'
        except Exception as exc:
            receipt['status'] = 'UNAVAILABLE'
            receipt['error'] = type(exc).__name__  # Never echo a keyed URL/body.
        return receipt
    # Every request is bounded; no futures left running after the cutoff.
    with ThreadPoolExecutor(max_workers=3) as workers:
        return list(workers.map(one, cases[:6]))
