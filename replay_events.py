#!/usr/bin/env python3
"""Day-138 — positions taken before the news, held a few days.

Registered first: PREREGISTER_day138_events.md (4fb0885). The windows, the
sides, the placebo and the bar are fixed there; nothing here was tuned on a
result. Nothing is wired into the morning, a pick, a size or a record.

  E1  LONG every scheduled report: P0 close -> D1 + 2 close, against XIU.
  E2  the side of the name's previous surprise, same window.
  E3  the majority side of the peers' surprises already public, same window.
  E4  a model's read of an overnight release (day-122's cached answers) that
      the open had not priced: open -> close two sessions later.

None of the four reads the stock's own past moves; E1-E3 enter before the
report is out, E4 only where the open went against the model's side.

    python replay_events.py          # FMP bars from the caches; writes the summary

The raw FMP data stays in the gitignored caches (.rb-state/weeks_cache,
.rb-state/events_cache); only the summary is committed
(data/replay_day138_events.json).
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import replay_weeks as W

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'replay_day138_events.json'
CACHE = ROOT/'.rb-state'/'events_cache'
ANSWERS = ROOT/'.rb-state'/'replay'/'news'/'answers'
WIRE = ROOT/'data'/'newswire'
START = '2012-01-01'
SPLIT = '2020-01-01'
EXIT = 2                      # exit at the close of D1 + 2
EXTRA_EXITS = (0, 4)          # descriptive: the reaction alone, a week
PREV_MIN, PREV_MAX = 30, 200  # E2: the previous report, in days before D
PEER_DAYS, PEER_GAP, PEER_MIN = 30, 5, 3
SPAN, GAP = 250, 10
E4_SPAN, E4_HOLD = 120, 2
DRAWS, EXTRA_DRAWS = 2000, 300
PLANT, BAR, COST, BORROW_YR = 0.50, 3.0, 0.13, 0.5
SEED = 138
E4_FROM = '2025-11-01'


# ── shared statistics ───────────────────────────────────────────────────────

def week(day):
    y, w, _ = dt.date.fromisoformat(day).isocalendar()
    return '%d-%02d' % (y, w)


def tstat(excess, groups_list):
    """The registered t: the smaller |t| over the clusterings given."""
    mean = float(np.mean(excess))
    ses = [W.cluster_se(list(excess), g, seed=SEED + k) for k, g in enumerate(groups_list)]
    ses = [s for s in ses if s]
    if not ses:
        return mean, None, None, []
    ts = [mean / s for s in ses]
    return mean, max(ses), min(ts, key=abs), ts


def blocks(order, values, n=4):
    pairs = sorted(zip(order, values))
    size = len(pairs) / n
    return [float(np.mean([v for _, v in pairs[int(b * size):int((b + 1) * size)]]))
            for b in range(n)] if len(pairs) >= n else []


def verdict(s):
    if s.get('t') is None:
        return 'NOT COMPUTABLE'
    bl = s['blocks']
    if (s['excess'] > 0 and s['t'] >= BAR and s['placebo_p'] < 0.01
            and sum(b > 0 for b in bl) >= 3 and bl and bl[-1] > 0 and s['excess'] > s['cost']):
        return 'PASS'
    if s['excess'] < 0 and s['t'] <= -BAR:
        return 'OPPOSITE SIDE (reported, never traded without its own registration)'
    return 'NULL' if s['control_t'] >= BAR else 'UNDERPOWERED'


# ── E1-E3: the panel of reports ────────────────────────────────────────────

def ar_matrix(panel, length):
    """100 * (stock - XIU) over `length` sessions starting at each column."""
    out = np.full(panel.px.shape, np.nan)
    if length < len(panel.cal):
        out[:, :-length] = 100.0 * ((panel.px[:, length:] / panel.px[:, :-length] - 1.0)
                                    - (panel.mkt[length:] / panel.mkt[:-length] - 1.0))
    return out


def all_reports(panel, data, dropped):
    """Every report with an actual EPS, at any date (E2 and E3 look back
    before START); the tested events are the ones from START on."""
    out = {}
    last = panel.cal[-1]
    for t in panel.tickers:
        seen, rows = set(), []
        for r in data[t].get('earnings') or []:
            day = str(r.get('date') or '')[:10]
            a, e = W._num(r.get('epsActual')), W._num(r.get('epsEstimated'))
            if not day or day in seen or a is None or day >= last:
                continue
            seen.add(day)
            p0, d1 = panel.last_before(day), panel.first_after(day)
            if p0 is None or d1 is None:
                dropped['outside_calendar'] = dropped.get('outside_calendar', 0) + 1
                continue
            rows.append({'ticker': t, 'date': day, 'p0': p0, 'd1': d1, 'a': a, 'e': e,
                         'surprise': None if e is None else (a > e) - (a < e),
                         'size': None if e is None else abs(a - e) / max(abs(e), 0.01)})
        out[t] = sorted(rows, key=lambda r: r['date'])
    return out


def previous_side(rows, k):
    """E2: the latest report 30-200 days before this one; its surprise sign."""
    day = dt.date.fromisoformat(rows[k]['date'])
    for r in reversed(rows[:k]):
        gap = (day - dt.date.fromisoformat(r['date'])).days
        if gap < PREV_MIN:
            continue
        if gap > PREV_MAX or not r['surprise']:
            return None, None
        return r['surprise'], r['size']
    return None, None


def peer_side(panel, ev, peers, reports):
    """E3: the majority sign of same-industry surprises public by the entry."""
    floor = (dt.date.fromisoformat(ev['date']) - dt.timedelta(days=PEER_DAYS)).isoformat()
    votes = []
    for p in peers:
        for r in reports.get(p, ()):
            if r['date'] < floor or r['surprise'] is None:
                continue
            at = panel.on_or_after(r['date'])
            if at is not None and at <= ev['p0'] - PEER_GAP:
                votes.append(r['surprise'])
    s = sum(votes)
    return ((s > 0) - (s < 0)) or None, len(votes)


def events(panel, data, meta, dropped):
    reports = all_reports(panel, data, dropped)
    industry = {}
    for t in panel.tickers:
        industry.setdefault(meta[t].get('industry') or '', []).append(t)
    groups = {k: v for k, v in industry.items() if k and len(v) >= PEER_MIN}
    out = {'E1': [], 'E2': [], 'E3': []}
    n = len(panel.cal)
    for t, rows in reports.items():
        peers = [p for p in groups.get(meta[t].get('industry') or '', []) if p != t]
        for k, r in enumerate(rows):
            if r['date'] < START or r['d1'] + max(EXIT, *EXTRA_EXITS) >= n:
                continue
            base = {'ticker': t, 'date': r['date'], 'p0': r['p0'], 'd1': r['d1']}
            out['E1'].append({**base, 'side': 1})
            s, size = previous_side(rows, k)
            if s:
                out['E2'].append({**base, 'side': s, 'size': size})
            if peers:
                s, votes = peer_side(panel, base, peers, reports)
                if s:
                    out['E3'].append({**base, 'side': s, 'votes': votes})
    return out, reports


def near_reports(panel, reports):
    """Per name, the sessions within GAP of any of its reports' P0."""
    out = {}
    for t, rows in reports.items():
        mask = np.zeros(len(panel.cal), dtype=bool)
        for r in rows:
            mask[max(0, r['p0'] - GAP):r['p0'] + GAP + 1] = True
        out[t] = mask
    return out


def measure(panel, evs, exit_after, near, draws, *, groups=('name', 'week')):
    """y, the per-event placebo expectation and the draws' cross-event means.
    Each event keeps its name, side and window length; its placebo windows
    start within ±SPAN sessions and never within GAP of the name's reports."""
    rng = np.random.default_rng(SEED)
    lengths = {e['d1'] + exit_after - e['p0'] for e in evs}
    ar = {L: ar_matrix(panel, L) for L in lengths}
    rows, choices = [], []
    for e in evs:
        L = e['d1'] + exit_after - e['p0']
        k = panel.row[e['ticker']]
        y = ar[L][k, e['p0']]
        if np.isnan(y):
            continue
        lo, hi = max(0, e['p0'] - SPAN), min(len(panel.cal) - 1, e['p0'] + SPAN)
        ok = ~np.isnan(ar[L][k, lo:hi + 1]) & ~near[e['ticker']][lo:hi + 1]
        ok = np.nonzero(ok)[0] + lo
        if not len(ok):
            continue
        rows.append({**e, 'y': e['side'] * float(y), 'L': L, 'k': k})
        choices.append(ok)
    if not rows:
        return None
    side = np.array([r['side'] for r in rows], dtype=float)
    per_event = np.zeros(len(rows))
    cross = np.empty(draws)
    for d in range(draws):
        vals = np.array([ar[r['L']][r['k'], c[rng.integers(len(c))]] for r, c in zip(rows, choices)])
        vals = side * vals
        per_event += vals
        cross[d] = float(vals.mean())
    per_event /= draws
    for r, p in zip(rows, per_event):
        r['excess'] = r['y'] - float(p)
    return rows, cross


def summary(panel, rows, cross, meta, *, descriptive=False):
    ex = [r['excess'] for r in rows]
    ys = [r['y'] for r in rows]
    mean, se, t, ts = tstat(ex, [[r['ticker'] for r in rows], [week(panel.cal[r['p0']]) for r in rows]])
    short = sum(1 for r in rows if r['side'] < 0) / len(rows)
    hold = float(np.mean([r['L'] for r in rows]))
    s = {'n': len(rows), 'names': len({r['ticker'] for r in rows}),
         'long': sum(1 for r in rows if r['side'] > 0), 'short': sum(1 for r in rows if r['side'] < 0),
         'mean_y': float(np.mean(ys)), 'placebo_mean': float(np.mean(cross)),
         'excess': mean, 'median_excess': float(np.median(ex)), 'win': float(np.mean([y > 0 for y in ys])),
         'se': se, 't': t, 't_name': ts[0] if ts else None, 't_week': ts[1] if len(ts) > 1 else None,
         'placebo_p': float(np.mean(cross >= np.mean(ys))),
         'blocks': blocks([r['p0'] for r in rows], ex),
         'hold_sessions': hold, 'cost': COST + BORROW_YR * hold / 252.0 * short,
         'control_t': PLANT / se if se else 0.0, 'mde': (BAR + 0.84) * se if se else None,
         'first': panel.cal[min(r['p0'] for r in rows)], 'last': panel.cal[max(r['p0'] for r in rows)]}
    s['net_excess'] = s['excess'] - s['cost']
    s['verdict'] = None if descriptive else verdict(s)
    return s


def split(panel, rows, f):
    sub = [r for r in rows if f(r)]
    if len(sub) < 20:
        return {'n': len(sub)}
    ex = [r['excess'] for r in sub]
    mean, se, t, _ = tstat(ex, [[r['ticker'] for r in sub], [week(panel.cal[r['p0']]) for r in sub]])
    return {'n': len(sub), 'excess': mean, 't': t, 'win': float(np.mean([r['y'] > 0 for r in sub]))}


def sector(meta, t):
    s, ind = meta[t].get('sector'), str(meta[t].get('industry') or '')
    if s in ('Energy', 'Oil & Gas'):
        return 'energy'
    if s in ('Basic Materials', 'Mining') or 'Gold' in ind or 'Mining' in ind:
        return 'materials and mining'
    return {'Financial Services': 'financials', 'Technology': 'technology'}.get(s, 'the rest')


def splits(panel, rows, meta, key):
    liq = sorted(meta[t].get('median_dollar_volume_20') or 0 for t in panel.tickers)
    cut1, cut2 = liq[len(liq) // 3], liq[2 * len(liq) // 3]

    def tercile(t):
        v = meta[t].get('median_dollar_volume_20') or 0
        return 'low' if v < cut1 else 'mid' if v < cut2 else 'high'
    out = {'period': {'before 2020': split(panel, rows, lambda r: r['date'] < SPLIT),
                      '2020 on': split(panel, rows, lambda r: r['date'] >= SPLIT)},
           'liquidity': {k: split(panel, rows, lambda r, k=k: tercile(r['ticker']) == k) for k in ('low', 'mid', 'high')},
           'sector': {k: split(panel, rows, lambda r, k=k: sector(meta, r['ticker']) == k)
                      for k in ('energy', 'materials and mining', 'financials', 'technology', 'the rest')}}
    if key == 'E1':
        out['legs'] = None
    else:
        out['legs'] = {'long': split(panel, rows, lambda r: r['side'] > 0),
                       'short': split(panel, rows, lambda r: r['side'] < 0)}
    if key == 'E2':
        sizes = sorted(r['size'] for r in rows if r.get('size') is not None)
        mid = sizes[len(sizes) // 2] if sizes else None
        out['surprise size'] = {'above the median': split(panel, rows, lambda r: (r.get('size') or 0) > mid),
                                'at or below': split(panel, rows, lambda r: (r.get('size') or 0) <= mid)}
    if key == 'E3':
        out['peer votes'] = {'3 or more': split(panel, rows, lambda r: r.get('votes', 0) >= 3),
                             'fewer': split(panel, rows, lambda r: r.get('votes', 0) < 3)}
    return out


def date_check(panel, rows):
    """Where the report's volume spike falls against the entry: 'before' means
    the spike came at or before P0 (the report was out before the entry: a
    late FMP date). Descriptive only: volume after P0 is not known at P0."""
    out = {'before the entry': 0, 'inside the window': 0, 'after the exit': 0, 'no volume': 0}
    for r in rows:
        k = panel.row[r['ticker']]
        lo, hi = max(0, r['p0'] - 2), min(r['d1'] + EXIT + 2, panel.vol.shape[1] - 1)
        v = panel.vol[k, lo:hi + 1]
        if not np.any(v > 0):
            out['no volume'] += 1
            continue
        at = lo + int(np.nanargmax(v))
        out['before the entry' if at <= r['p0'] else 'after the exit' if at > r['d1'] + EXIT
            else 'inside the window'] += 1
    return out


def e1_checks(panel, rows, near):
    """Descriptive checks of E1, added AFTER its verdict (never a verdict):
    the same windows against the names not reporting then, against a market
    model, trimmed, by FMP date quality, by year, day by day, and as a daily
    hedged portfolio net of the measured cost."""
    rng = np.random.default_rng(SEED + 7)
    ar = {L: ar_matrix(panel, L) for L in {r['L'] for r in rows}}
    nearm = np.array([near[t] for t in panel.tickers])
    wk = [week(panel.cal[r['p0']]) for r in rows]
    names = [r['ticker'] for r in rows]

    def stat(vals, keep=None):
        keep = keep if keep is not None else [True] * len(vals)
        v = [x for x, k in zip(vals, keep) if k and x is not None and not np.isnan(x)]
        g1 = [n for n, x, k in zip(names, vals, keep) if k and x is not None and not np.isnan(x)]
        g2 = [w for w, x, k in zip(wk, vals, keep) if k and x is not None and not np.isnan(x)]
        if len(v) < 20:
            return {'n': len(v)}
        m, se, t, _ = tstat(v, [g1, g2])
        return {'n': len(v), 'mean': m, 't': t, 'median': float(np.median(v))}

    out = {}
    # 1. against the names that are not reporting in the same window
    cs = []
    for r in rows:
        col = ar[r['L']][:, r['p0']]
        ok = ~np.isnan(col) & ~nearm[:, r['p0']]
        ok[r['k']] = False
        cs.append(r['y'] - float(col[ok].mean()) if ok.sum() >= 20 else None)
    out['against non-reporters, same window'] = stat(cs)
    # 2. a market model: beta over the 250 sessions before P0
    ret = np.full(panel.px.shape, np.nan)
    ret[:, 1:] = panel.px[:, 1:] / panel.px[:, :-1] - 1.0
    mret = np.concatenate([[np.nan], panel.mkt[1:] / panel.mkt[:-1] - 1.0])
    beta_ex, betas = [], []
    for r in rows:
        lo = max(1, r['p0'] - 250)
        x, y = mret[lo:r['p0'] + 1], ret[r['k'], lo:r['p0'] + 1]
        ok = ~np.isnan(x) & ~np.isnan(y)
        if ok.sum() < 100:
            beta_ex.append(None)
            continue
        b = float(np.cov(y[ok], x[ok])[0, 1] / np.var(x[ok], ddof=1))
        betas.append(b)

        def abn(i):
            s = panel.px[r['k'], i + r['L']] / panel.px[r['k'], i] - 1.0 if i + r['L'] < len(panel.cal) else np.nan
            return 100.0 * (s - b * (panel.mkt[i + r['L']] / panel.mkt[i] - 1.0))
        lo2, hi2 = max(0, r['p0'] - SPAN), min(len(panel.cal) - r['L'] - 1, r['p0'] + SPAN)
        cand = [i for i in range(lo2, hi2 + 1) if not near[r['ticker']][i]]
        draws = [abn(i) for i in rng.choice(cand, size=min(100, len(cand)), replace=False)] if cand else []
        draws = [d for d in draws if not np.isnan(d)]
        e = abn(r['p0'])
        beta_ex.append(e - float(np.mean(draws)) if draws and not np.isnan(e) else None)
    out['market model (beta before P0), against its own placebo'] = stat(beta_ex)
    out['median beta'] = float(np.median(betas)) if betas else None
    # 3. trimmed at the 1st and 99th percentiles
    ex = np.array([r['excess'] for r in rows])
    lo, hi = np.percentile(ex, [1, 99])
    out['trimmed 1%/99%'] = stat(list(np.clip(ex, lo, hi)))
    # 4. by where the report's volume spike falls (FMP date quality)
    where = []
    for r in rows:
        lo3, hi3 = max(0, r['p0'] - 2), min(r['d1'] + EXIT + 2, panel.vol.shape[1] - 1)
        v = panel.vol[r['k'], lo3:hi3 + 1]
        if not np.any(v > 0):
            where.append(None)
            continue
        at = lo3 + int(np.nanargmax(v))
        where.append('before' if at <= r['p0'] else 'after' if at > r['d1'] + EXIT else 'inside')
    out['by FMP date quality'] = {k: stat(list(ex), [w == k for w in where]) for k in ('inside', 'before', 'after')}
    # 5. by year
    years = [panel.cal[r['p0']][:4] for r in rows]
    out['by year'] = {y: stat(list(ex), [yy == y for yy in years]) for y in sorted(set(years))}
    # 6. day by day around D1 (stock minus XIU, each day), against the same
    #    names' average day over the whole calendar
    daily = np.full(panel.px.shape, np.nan)
    daily[:, 1:] = 100.0 * ((panel.px[:, 1:] / panel.px[:, :-1] - 1.0) - (panel.mkt[1:] / panel.mkt[:-1] - 1.0))
    base = np.nanmean(daily, axis=1)
    path = {}
    for off in range(-6, 5):
        v = [daily[r['k'], r['d1'] + off] - base[r['k']] for r in rows
             if 0 <= r['d1'] + off < daily.shape[1] and not np.isnan(daily[r['k'], r['d1'] + off])]
        path['D1%+d' % off] = float(np.mean(v)) if v else None
    out['average day around D1 (D1+0 is the first session after the report date)'] = path
    # 7. a daily portfolio: every open window, equal weight, hedged with XIU,
    #    the measured round trip spread over the hold
    n = len(panel.cal)
    tot, cnt, cost = np.zeros(n), np.zeros(n), np.zeros(n)
    for r in rows:
        for j in range(r['p0'] + 1, r['p0'] + r['L'] + 1):
            v = daily[r['k'], j]
            if not np.isnan(v):
                tot[j] += v
                cnt[j] += 1
                cost[j] += COST / r['L']
    start = rows and min(r['p0'] for r in rows)
    days = np.arange(start + 1, max(r['p0'] + r['L'] for r in rows) + 1)
    gross = np.where(cnt[days] > 0, tot[days] / np.maximum(cnt[days], 1), 0.0)
    net = np.where(cnt[days] > 0, (tot[days] - cost[days]) / np.maximum(cnt[days], 1), 0.0)

    def perf(x):
        if len(x) < 2:
            return None
        eq = np.cumprod(1 + x / 100.0)
        dd = float(np.max(1 - eq / np.maximum.accumulate(eq)))
        return {'annual_pct': float(252 * x.mean()), 'vol_pct': float(np.sqrt(252) * x.std(ddof=1)),
                'sharpe': float(np.sqrt(252) * x.mean() / x.std(ddof=1)) if x.std() else None,
                'max_drawdown_pct': 100 * dd, 'total_pct': float(100 * (eq[-1] - 1))}
    yrs = {}
    for y in sorted({panel.cal[d][:4] for d in days}):
        m = np.array([panel.cal[d][:4] == y for d in days])
        yrs[y] = {'gross_pct': float(100 * (np.prod(1 + gross[m] / 100) - 1)),
                  'net_pct': float(100 * (np.prod(1 + net[m] / 100) - 1)),
                  'days_invested': int((cnt[days][m] > 0).sum())}
    out['daily portfolio (every window, equal weight, hedged)'] = {
        'gross': perf(gross), 'net': perf(net), 'days': len(days),
        'days_invested': int((cnt[days] > 0).sum()), 'mean_positions_when_invested': float(cnt[days][cnt[days] > 0].mean()),
        'by_year': yrs, 'note': 'returns are per unit of capital spread over the open windows; '
                                'no leverage, the XIU hedge costed at zero'}
    # 8. survivorship: the list is today's most traded names, so the winners
    #    of the period are over-represented. Split by each name's whole-period
    #    return against XIU: the premium among the period's LOSERS cannot come
    #    from names that grew on their reports.
    perf_name = {}
    for t, k in panel.row.items():
        s = panel.px[k]
        ok = np.nonzero(~np.isnan(s))[0]
        ok = ok[ok >= rows[0]['p0'] - 0] if len(ok) else ok
        first = next((i for i in ok if panel.cal[i] >= START), None)
        if first is None:
            continue
        lastv = ok[-1]
        perf_name[t] = (s[lastv] / s[first]) / (panel.mkt[lastv] / panel.mkt[first]) - 1.0
    ranked = sorted(perf_name, key=perf_name.get)
    third = len(ranked) // 3
    tier = {t: ('worst third' if i < third else 'middle third' if i < 2 * third else 'best third')
            for i, t in enumerate(ranked)}
    out['by the name\'s whole-period return against XIU'] = {
        k: stat(list(ex), [tier.get(r['ticker']) == k for r in rows]) for k in ('worst third', 'middle third', 'best third')}
    # 8b. the same split with the report windows taken out of the ranking: a
    #     whole-period return includes the report days themselves, so it sorts
    #     their premium mechanically even when none exists
    quiet = {}
    first_day = rows[0]['p0']
    for t, k in panel.row.items():
        v = daily[k, first_day:]
        keep = ~np.isnan(v) & ~near[t][first_day:]
        if keep.sum() > 250:
            quiet[t] = float(v[keep].mean())
    ranked = sorted(quiet, key=quiet.get)
    third = len(ranked) // 3
    tier2 = {t: ('worst third' if i < third else 'middle third' if i < 2 * third else 'best third')
             for i, t in enumerate(ranked)}
    out['by the name\'s return on its days away from reports'] = {
        k: stat(list(ex), [tier2.get(r['ticker']) == k for r in rows]) for k in ('worst third', 'middle third', 'best third')}
    # 9. a sized portfolio: 5% of capital a window, at most 100% open (scaled
    #    down when more than 20 windows are open), the rest in cash
    f, cap = 0.05, 1.0
    gross_s, net_s = np.zeros(len(days)), np.zeros(len(days))
    for n_i, j in enumerate(days):
        if cnt[j] == 0:
            continue
        w = min(f, cap / cnt[j])
        gross_s[n_i] = w * tot[j]
        net_s[n_i] = w * (tot[j] - cost[j])
    yrs_s = {}
    for y in sorted({panel.cal[d][:4] for d in days}):
        m = np.array([panel.cal[d][:4] == y for d in days])
        yrs_s[y] = {'gross_pct': float(100 * (np.prod(1 + gross_s[m] / 100) - 1)),
                    'net_pct': float(100 * (np.prod(1 + net_s[m] / 100) - 1))}
    early = np.array([panel.cal[d] < '2024-01-01' for d in days])
    out['sized portfolio (5% a window, at most 100% open, hedged)'] = {
        'gross': perf(gross_s), 'net': perf(net_s),
        'net 2012-2023': perf(net_s[early]), 'net 2024-2026': perf(net_s[~early]),
        'mean_exposure_when_invested': float(np.mean([min(f * cnt[j], cap) for j in days if cnt[j] > 0])),
        'by_year': yrs_s}
    return out


def run_reports(data, tickers, meta, rejected):
    panel = W.Panel(data, tickers)
    dropped = {}
    evs, reports = events(panel, data, meta, dropped)
    near = near_reports(panel, reports)
    out = {'registered': 'PREREGISTER_day138_events.md (4fb0885)',
           'names': len(panel.tickers), 'calendar': [panel.cal[0], panel.cal[-1]],
           'rejected_series': rejected, 'dropped': dropped, 'hypotheses': {}}
    for key in ('E1', 'E2', 'E3'):
        got = measure(panel, evs[key], EXIT, near, DRAWS)
        if not got:
            out['hypotheses'][key] = {'n': 0, 'verdict': 'NOT COMPUTABLE'}
            continue
        rows, cross = got
        res = summary(panel, rows, cross, meta)
        res['splits'] = splits(panel, rows, meta, key)
        res['date_check'] = date_check(panel, rows)
        if key == 'E1':
            res['checks_after_verdict'] = e1_checks(panel, rows, near)
        res['other_exits'] = {}
        for x in EXTRA_EXITS:
            g = measure(panel, evs[key], x, near, EXTRA_DRAWS)
            if g:
                res['other_exits']['D1 + %d' % x] = summary(panel, g[0], g[1], meta, descriptive=True)
        out['hypotheses'][key] = res
    return out


# ── E4: the model's read the open had not priced ──────────────────────────

def calls():
    """{(session, ticker): call} from day-122's cached FULL-arm answers."""
    out = {}
    for f in sorted(ANSWERS.glob('*_full.json')):
        for key, c in (json.loads(f.read_text()).get('calls') or {}).items():
            day, ticker = key.split(':', 1)
            if c.get('side') in ('LONG', 'SHORT'):
                out[(day, ticker)] = c
    return out


def bars(fetch, sym):
    """{date: (open, close)} dividend-adjusted, or None."""
    rows = fetch('historical-price-eod/dividend-adjusted', symbol=sym, **{'from': E4_FROM, 'to': '2026-10-14'})
    if rows is None:
        return None
    out = {}
    for r in rows:
        o, c = r.get('adjOpen'), r.get('adjClose')
        if isinstance(o, (int, float)) and isinstance(c, (int, float)) and o > 0 and c > 0:
            out[str(r['date'])[:10]] = (float(o), float(c))
    return out


def releases_by_ticker():
    out = {}
    for f in sorted(WIRE.glob('*.jsonl')):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            for t in r.get('tickers') or []:
                out.setdefault(t, set()).add(str(r.get('published_at') or '')[:10])
    return out


def run_e4(fetch):
    import concurrent.futures as cf
    cs = calls()
    tickers = sorted({t for _, t in cs})
    with cf.ThreadPoolExecutor(6) as pool:
        got = dict(zip(['XIU.TO'] + tickers, pool.map(lambda s: bars(fetch, s), ['XIU.TO'] + tickers)))
    mkt = got.pop('XIU.TO')
    if not mkt:
        return {'verdict': 'NOT COMPUTABLE', 'reason': 'XIU.TO bars unavailable'}
    cal = sorted(mkt)
    idx = {d: i for i, d in enumerate(cal)}
    rel = releases_by_ticker()
    missing = sorted(t for t in tickers if not got.get(t))

    def window(t, i):
        """(signed-later) gap and open -> close+2 return against XIU, raw."""
        b = got.get(t)
        if not b or i < 1 or i + E4_HOLD >= len(cal):
            return None
        d0, dp, dx = cal[i], cal[i - 1], cal[i + E4_HOLD]
        if d0 not in b or dp not in b or dx not in b:
            return None
        gap = (b[d0][0] / b[dp][1] - 1) - (mkt[d0][0] / mkt[dp][1] - 1)
        ret = (b[dx][1] / b[d0][0] - 1) - (mkt[dx][1] / mkt[d0][0] - 1)
        return 100 * gap, 100 * ret

    near = {}
    for t in tickers:
        mask = np.zeros(len(cal), dtype=bool)
        for d in rel.get(t, ()):
            j = bisect.bisect_left(cal, d)
            mask[max(0, j - GAP):j + GAP + 1] = True
        near[t] = mask

    rows, problems = [], {}
    for (day, t), c in sorted(cs.items()):
        i = idx.get(day)
        w = window(t, i) if i is not None else None
        if w is None:
            problems['no bars for the window'] = problems.get('no bars for the window', 0) + 1
            continue
        side = 1 if c['side'] == 'LONG' else -1
        rows.append({'session': day, 'ticker': t, 'side': side, 'i': i, 'material': bool(c.get('material')),
                     'gap': side * w[0], 'y': side * w[1]})

    def test(sub, label, *, conditioned_placebo=False, draws=DRAWS, registered=False):
        rng = np.random.default_rng(SEED)
        kept, choices = [], []
        for r in sub:
            lo, hi = max(1, r['i'] - E4_SPAN), min(len(cal) - E4_HOLD - 1, r['i'] + E4_SPAN)
            ok = []
            for j in range(lo, hi + 1):
                if near[r['ticker']][j]:
                    continue
                w = window(r['ticker'], j)
                if w is None:
                    continue
                if conditioned_placebo and r['side'] * w[0] > 0:
                    continue
                ok.append(r['side'] * w[1])
            if ok:
                kept.append(r)
                choices.append(np.array(ok))
        if len(kept) < 20:
            return {'label': label, 'n': len(kept), 'verdict': 'NOT COMPUTABLE' if registered else None}
        ys = np.array([r['y'] for r in kept])
        per_event = np.array([c.mean() for c in choices])
        cross = np.array([np.mean([c[rng.integers(len(c))] for c in choices]) for _ in range(draws)])
        ex = list(ys - per_event)
        mean, se, t, ts = tstat(ex, [[r['session'] for r in kept], [r['ticker'] for r in kept]])
        s = {'label': label, 'n': len(kept), 'sessions': len({r['session'] for r in kept}),
             'names': len({r['ticker'] for r in kept}),
             'long': int(sum(r['side'] > 0 for r in kept)), 'short': int(sum(r['side'] < 0 for r in kept)),
             'mean_y': float(ys.mean()), 'placebo_mean': float(cross.mean()), 'excess': mean,
             'median_excess': float(np.median(ex)), 'win': float(np.mean(ys > 0)),
             'se': se, 't': t, 't_session': ts[0] if ts else None, 't_name': ts[1] if len(ts) > 1 else None,
             'placebo_p': float(np.mean(cross >= ys.mean())),
             'blocks': blocks([r['i'] for r in kept], ex),
             'hold_sessions': E4_HOLD + 1,
             'cost': COST + BORROW_YR * (E4_HOLD + 1) / 252.0 * float(np.mean([r['side'] < 0 for r in kept])),
             'control_t': PLANT / se if se else 0.0, 'mde': (BAR + 0.84) * se if se else None,
             'first': kept[0]['session'] if kept else None}
        s['net_excess'] = s['excess'] - s['cost']
        s['verdict'] = verdict(s) if registered else None
        return s

    primary = [r for r in rows if r['material'] and r['gap'] <= 0]
    return {'calls': len(cs), 'tickers': len(tickers), 'tickers_without_bars': missing,
            'problems': problems, 'material_calls': sum(r['material'] for r in rows),
            'E4': test(primary, 'material, the open not its way (registered)', registered=True),
            'descriptive': {
                'same events, placebo windows whose open also went against the side':
                    test(primary, 'conditioned placebo', conditioned_placebo=True, draws=EXTRA_DRAWS),
                'all material calls': test([r for r in rows if r['material']], 'all material', draws=EXTRA_DRAWS),
                'material, the open already its way': test([r for r in rows if r['material'] and r['gap'] > 0],
                                                           'already priced', draws=EXTRA_DRAWS),
                'every call': test(rows, 'every call', draws=EXTRA_DRAWS)}}


# ── E1-US: the same rule on the S&P 500 as it stood (amendment 1) ─────────

US_CACHE = ROOT/'.rb-state'/'events_us_cache'
US_MARKET = 'SPY'
US_FROM, US_TO = '2010-06-01', '2026-10-14'


def sp500_membership(fetch):
    """{ticker: [(start, end)]}, end exclusive, rebuilt backwards from today's
    list through FMP's change history; glitches are counted, never guessed."""
    current = fetch('sp500-constituent') or []
    changes = fetch('historical-sp500-constituent') or []
    if not current or not changes:
        raise SystemExit('S&P 500 membership unavailable from FMP')
    open_end = {c['symbol']: '9999-12-31' for c in current}
    intervals, glitches = {}, {}
    for c in sorted(changes, key=lambda c: str(c.get('date') or ''), reverse=True):
        d = str(c.get('date') or '')[:10]
        a, r = (c.get('addedTicker') or '').strip(), (c.get('removedTicker') or '').strip()
        if a:
            end = open_end.pop(a, None)
            if end is None:
                glitches['added but not a member after'] = glitches.get('added but not a member after', 0) + 1
            else:
                intervals.setdefault(a, []).append((d, end))
        if r:
            if r in open_end:
                glitches['removed but already a member before'] = glitches.get('removed but already a member before', 0) + 1
            else:
                open_end[r] = d
    for t, end in open_end.items():
        intervals.setdefault(t, []).append(('1900-01-01', end))
    return intervals, glitches


def member(intervals, t, day):
    return any(a <= day < b for a, b in intervals.get(t, ()))


def run_us(fetch):
    import concurrent.futures as cf
    intervals, glitches = sp500_membership(fetch)
    tickers = sorted(t for t, iv in intervals.items() if any(b > START and a < US_TO for a, b in iv))

    def one(t):
        rows = fetch('historical-price-eod/dividend-adjusted', symbol=t, **{'from': US_FROM, 'to': US_TO})
        if not rows:
            return t, None
        adj = {str(r['date'])[:10]: float(r['adjClose']) for r in rows
               if isinstance(r.get('adjClose'), (int, float)) and r['adjClose'] > 0}
        vol = {str(r['date'])[:10]: float(r['volume']) for r in rows if isinstance(r.get('volume'), (int, float))}
        rec = {'adj': adj, 'vol': vol}
        if t != US_MARKET:
            rec['earnings'] = fetch('earnings', symbol=t, limit=400) or []
        return t, rec
    data, rejected = {}, {}
    with cf.ThreadPoolExecutor(8) as pool:
        for t, rec in pool.map(one, [US_MARKET] + tickers):
            if rec is None or not W.granular(rec['adj']):
                rejected[t] = 'NO_DAILY_BARS'
                continue
            data[t] = rec
    if US_MARKET not in data:
        raise SystemExit('SPY bars unavailable')
    saved = W.MARKET
    W.MARKET = US_MARKET
    try:
        panel = W.Panel(data, [t for t in tickers if t in data])
    finally:
        W.MARKET = saved
    dropped = {}
    reports = all_reports(panel, data, dropped)
    evs, not_member = [], 0
    for t, rows in reports.items():
        for r in rows:
            if r['date'] < START or r['d1'] + EXIT >= len(panel.cal):
                continue
            if not member(intervals, t, panel.cal[r['p0']]):
                not_member += 1
                continue
            evs.append({'ticker': t, 'date': r['date'], 'p0': r['p0'], 'd1': r['d1'], 'side': 1})
    near = near_reports(panel, reports)
    got = measure(panel, evs, EXIT, near, DRAWS)
    out = {'registered': 'PREREGISTER_day138_events.md, amendment 1',
           'members_2012_on': len(tickers), 'with_bars': len(panel.tickers),
           'without_bars': sorted(rejected), 'membership_glitches': glitches,
           'reports_outside_membership': not_member, 'dropped': dropped}
    if not got:
        out['E1-US'] = {'n': 0, 'verdict': 'NOT COMPUTABLE'}
        return out
    rows, cross = got
    meta = {t: {} for t in panel.tickers}
    out['E1-US'] = summary(panel, rows, cross, meta)
    still = {t for t, iv in intervals.items() if any(b == '9999-12-31' for _, b in iv)}
    ex = [r['excess'] for r in rows]

    def sub(f):
        return split(panel, rows, f)
    out['descriptive'] = {
        'still in the index today': sub(lambda r: r['ticker'] in still),
        'since removed from the index': sub(lambda r: r['ticker'] not in still),
        'before 2020': sub(lambda r: r['date'] < SPLIT), '2020 on': sub(lambda r: r['date'] >= SPLIT),
        'by year': {y: sub(lambda r, y=y: r['date'][:4] == y) for y in sorted({r['date'][:4] for r in rows})},
        'trimmed 1%/99% mean': float(np.mean(np.clip(ex, *np.percentile(ex, [1, 99]))))}
    return out


# ── reporting ──────────────────────────────────────────────────────────────

def _f(v, fmt='%+.3f'):
    return '—' if v is None else fmt % v


def table(out):
    lines = ['| Test | n | long/short | mean % | placebo % | excess % | t (a, b) | placebo p | blocks | net % | verdict |',
             '|---|---:|---|---:|---:|---:|---|---:|---|---:|---|']
    rows = ([(k, s) for k, s in out['reports']['hypotheses'].items()] + [('E4', out['e4']['E4'])]
            + ([('E1-US', out['us']['E1-US'])] if 'us' in out else []))
    for k, s in rows:
        if s.get('excess') is None:
            lines.append('| %s | %s | — | — | — | — | — | — | — | — | %s |' % (k, s.get('n'), s.get('verdict')))
            continue
        a, b = (s.get('t_session'), s.get('t_name')) if k == 'E4' else (s.get('t_name'), s.get('t_week'))
        lines.append('| %s | %d | %d/%d | %s | %s | %s | %s (%s, %s) | %s | %s | %s | %s |' % (
            k, s['n'], s['long'], s['short'], _f(s['mean_y']), _f(s['placebo_mean']), _f(s['excess']),
            _f(s['t'], '%+.2f'), _f(a, '%+.2f'), _f(b, '%+.2f'), _f(s['placebo_p'], '%.3f'),
            ' '.join('%+.2f' % x for x in s['blocks']), _f(s['net_excess']), s['verdict']))
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--out', default=str(OUT))
    p.add_argument('--only', choices=('reports', 'e4', 'us'))
    a = p.parse_args(argv)
    from replay_drift import Fetch
    out = {}
    if a.only in (None, 'reports'):
        fetch = W.robust(Fetch(W.CACHE))
        tickers, meta = W.names()
        data, rejected = W.collect(tickers, fetch)
        out['reports'] = run_reports(data, tickers, meta, rejected)
        out['reports']['fetch_failures'] = fetch.failures
    if a.only in (None, 'e4'):
        fetch = W.robust(Fetch(CACHE))
        out['e4'] = run_e4(fetch)
        out['e4']['fetch_failures'] = fetch.failures
    if a.only in (None, 'us'):
        fetch = W.robust(Fetch(US_CACHE))
        out['us'] = run_us(fetch)
        out['us']['fetch_failures'] = fetch.failures
    if a.only:
        print(json.dumps(out, indent=1, sort_keys=True, default=str)[:6000])
        return 0
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True))
    print(table(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
