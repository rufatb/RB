#!/usr/bin/env python3
"""THE COMMODITY NOWCAST (day-149b; council lab item 13).

A gold or silver producer sells what it mines at about the quarter's average
price, and that average is public the day the quarter ends, weeks before the
company reports. So

    nowcast = last quarter's revenue x (this quarter's average metal price
                                        / last quarter's average)

is an estimate nobody had to forecast. It is the nearest thing this record has
to the "independent estimate" the owner's pasted engine asks for and names no
source for (2026-11-09). That evening Equinox showed the stronger form: ounces
it had already announced x the quarter's average gold price gave US$1,068M
against a consensus of US$987M and a reported US$1,050M, and the shares did
not move. Ounces are in no feed, so this module carries last quarter's revenue.

It knows nothing about ounces. A mine opened, sold or merged makes it wrong, so
a gap wider than GUARD against consensus is called structural and takes no
side. Whether the gap predicts the reaction is a registered history test
(PREREGISTER_day149_nowcast.md, nowcast_history.py). Nothing here picks, sizes
or records anything.

    python nowcast.py EQX.TO 2026-11-09        the figures for one report (FMP)
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECTORS = ROOT/'data'/'tsx_sectors.json'
METALS = {'Gold': 'GCUSD', 'Silver': 'SIUSD'}       # the sector map's industry -> FMP's price series
LAG_DAYS = 14          # a report covers the last quarter that ended at least this long before it
MIN_PRICES = 55        # daily prices a quarter's average needs
THETA = 0.03           # a gap smaller than this takes no side
GUARD = 0.25           # a gap wider than this is a change in ounces, not in price
FX_TOLERANCE = 0.03    # how far the two listings' consensus may sit from the spot rate


def quarter_end(y, q):
    return dt.date(y + (q == 4), 3 * q % 12 + 1, 1) - dt.timedelta(days=1)


def quarter(day):
    """(year, q) of the last calendar quarter that ended at least LAG_DAYS before `day`."""
    cut = day - dt.timedelta(days=LAG_DAYS)
    yq = cut.year, (cut.month - 1) // 3 + 1
    return yq if cut >= quarter_end(*yq) else previous(yq)


def previous(yq):
    y, q = yq
    return (y, q - 1) if q > 1 else (y - 1, 4)


def averages(rows):
    """{(year, q): the mean daily price} for every quarter with MIN_PRICES prices.
    `rows` are FMP's light daily rows ({'date', 'price'})."""
    by = {}
    for r in rows or []:
        try:
            d = dt.date.fromisoformat(str(r.get('date'))[:10])
            p = float(r.get('price') if r.get('price') is not None else r.get('close'))
        except (TypeError, ValueError):
            continue
        if p > 0:
            by.setdefault((d.year, (d.month - 1) // 3 + 1), []).append(p)
    return {k: st.mean(v) for k, v in by.items() if len(v) >= MIN_PRICES}


def estimate(prev_revenue, avgs, yq):
    """Last quarter's revenue carried to this quarter's average price, or None."""
    a, b = avgs.get(yq), avgs.get(previous(yq))
    if not (prev_revenue and prev_revenue > 0 and a and b):
        return None
    return prev_revenue * a / b


def gap(nowcast, consensus):
    return None if not (nowcast and consensus and consensus > 0) else nowcast / consensus - 1


def side(g):
    """LONG when the nowcast stands at least THETA above consensus, SHORT when
    as far below, None inside THETA or beyond GUARD."""
    if g is None or abs(g) < THETA or abs(g) > GUARD:
        return None
    return 'LONG' if g > 0 else 'SHORT'


def metal_for(ticker, sectors=None):
    """FMP's price series for a gold or silver producer, else None."""
    if sectors is None:
        try:
            sectors = json.loads(SECTORS.read_text()).get('sectors') or {}
        except (OSError, ValueError):
            sectors = {}
    return METALS.get((sectors.get(ticker) or {}).get('industry'))


def _rows(earnings):
    out = []
    for r in earnings if isinstance(earnings, list) else []:
        try:
            d = dt.date.fromisoformat(str(r.get('date'))[:10])
        except (TypeError, ValueError):
            continue
        out.append((d, r))
    return sorted(out, key=lambda x: x[0])


def history(earnings, avgs):
    """One record per reported quarter of one listing's FMP earnings rows:
    {'date', 'quarter', 'actual', 'consensus', 'prev', 'nowcast', 'gap', 'side'}.
    Two rows that map to one quarter are both left out (a misdated report)."""
    by = {}
    for d, r in _rows(earnings):
        a = r.get('revenueActual')
        if isinstance(a, (int, float)) and a > 0:
            by.setdefault(quarter(d), []).append((d, r))
    out = []
    for yq, rows in sorted(by.items()):
        prev = by.get(previous(yq))
        if len(rows) != 1 or not prev or len(prev) != 1:
            continue
        d, r = rows[0]
        e = r.get('revenueEstimated')
        n = estimate(prev[0][1]['revenueActual'], avgs, yq)
        g = gap(n, e if isinstance(e, (int, float)) else None)
        out.append({'date': d.isoformat(), 'quarter': '%dQ%d' % yq, 'actual': r['revenueActual'],
                    'consensus': e if isinstance(e, (int, float)) and e > 0 else None,
                    'prev': prev[0][1]['revenueActual'], 'nowcast': n, 'gap': g, 'side': side(g)})
    return out


def for_report(ticker, report_date, read, *, twins=None, sectors=None, today=None):
    """The nowcast for one coming report of a gold or silver producer that also
    trades in New York, from FMP: its US rows are in US dollars as reported.
    Returns None when the name is not one, and a dict with `reason` when a
    figure is missing. `consensus_checked` is False when the two listings'
    consensus do not sit at the spot exchange rate (FMP's revenue estimates
    disagree between listings on about half of past quarters)."""
    series = metal_for(ticker, sectors)
    if not series:
        return None
    if twins is None:
        import us_preopen
        twins = us_preopen.load_twins()
    twin = twins.get(ticker)
    if not twin:
        return {'ticker': ticker, 'reason': 'no New York listing: its rows are converted, not as reported'}
    today = today or dt.date.today()
    yq = quarter(report_date)
    start = dt.date(previous(yq)[0], 3 * (previous(yq)[1] - 1) + 1, 1)
    avgs = averages(read('historical-price-eod/light', symbol=series,
                         **{'from': start.isoformat(), 'to': today.isoformat()}))
    rows = _rows(read('earnings', symbol=twin['us'], limit=12))
    coming = [r for d, r in rows if abs((d - report_date).days) <= 5]
    prev = [r for d, r in rows if quarter(d) == previous(yq)
            and isinstance(r.get('revenueActual'), (int, float))]
    out = {'ticker': ticker, 'us': twin['us'], 'metal': series[:2] == 'GC' and 'gold' or 'silver',
           'quarter': '%dQ%d' % yq, 'currency': 'USD'}
    if not coming or not prev:
        return {**out, 'reason': 'no row for this report or for the quarter before it'}
    e = coming[-1].get('revenueEstimated')
    n = estimate(prev[-1]['revenueActual'], avgs, yq)
    if not n:
        return {**out, 'reason': 'the quarter\'s average price is not complete'}
    g = gap(n, e if isinstance(e, (int, float)) else None)
    out.update(prev_revenue=prev[-1]['revenueActual'], nowcast=round(n), consensus=e,
               gap_pct=None if g is None else round(100 * g, 1), side=side(g),
               price_change_pct=round(100 * (avgs[yq] / avgs[previous(yq)] - 1), 1),
               structural=bool(g is not None and abs(g) > GUARD))
    # The other listing's consensus, converted by FMP, should sit at the spot rate.
    checked = None
    try:
        other = [r for d, r in _rows(read('earnings', symbol=ticker, limit=12))
                 if abs((d - report_date).days) <= 5]
        fx = read('historical-price-eod/light', symbol='USDCAD',
                  **{'from': (today - dt.timedelta(days=7)).isoformat(), 'to': today.isoformat()})
        spot = max(fx, key=lambda r: r['date'])['price'] if fx else None
        eo = other[-1].get('revenueEstimated') if other else None
        if e and eo and spot:
            checked = abs(eo / e / spot - 1) <= FX_TOLERANCE
    except Exception:
        checked = None
    out['consensus_checked'] = checked
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    from events_note import Reader
    read = Reader()
    out = for_report(argv[0], dt.date.fromisoformat(argv[1]), read)
    print(json.dumps({'result': out, 'failures': read.failures}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
