#!/usr/bin/env python3
"""Day-135b — do TSX names drift for weeks after earnings and rating changes?

Registered first: PREREGISTER_day135_weeks.md (3e0e8bc). The bar, the
signals, the entries and the estimator are fixed there; nothing here was
tuned on a result. Nothing is wired into the morning, a pick, a size or a
record.

Four signals on the 150 names of the TSX list, market-adjusted against XIU.TO:
  W1  the EPS surprise against consensus, scaled by the prior close;
  W2  the announcement reaction (P0 close -> D1 close, against XIU);
  W3  W1 and W2 on the same side;
  W4  an analyst rating change (net upgrades minus downgrades that day).
Entry at the first close where the event is public; exit after H = 5, 10
(primary) or 20 sessions.

    python replay_weeks.py           # fetch (cached under .rb-state) and run

Raw FMP data stays in the gitignored cache; only the summary is committed
(data/replay_day135_weeks.json).
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import math
import statistics as st
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'replay_day135_weeks.json'
CACHE = ROOT/'.rb-state'/'weeks_cache'
UNIVERSE = ROOT/'.rb-state'/'tsx_universe.json'
MARKET = 'XIU.TO'
CHUNKS = (('2001-01-01', '2006-12-31'), ('2007-01-01', '2026-10-14'))
HORIZONS = (5, 10, 20)
PRIMARY = 10
HIGH, LOW = 0.70, 0.30
WINDOW_DAYS = 365
BURN_IN = 100
BOOT, PLACEBO_DRAWS, SEED = 2000, 1000, 135
PLACEBO_SPAN, PLACEBO_GAP = 250, 10
PLANT, BAR, Z80 = 0.50, 3.0, 0.84
COST_RT, BORROW_YR = 0.13, 0.5
SPLIT_YEAR = '2012-01-01'
BUSY = 10
SIGNALS = ('W1', 'W2', 'W3', 'W4')
FAMILY = {'W1': 'earnings', 'W2': 'earnings', 'W3': 'earnings', 'W4': 'grades'}


# ── data ────────────────────────────────────────────────────────────────────

def names(path=UNIVERSE):
    rows = json.loads(Path(path).read_text())['candidates']
    return [r['ticker'] for r in rows], {r['ticker']: r for r in rows}


def robust(fetch, tries=3):
    """A transfer the proxy cuts off (IncompleteRead, a reset) is retried, then
    COUNTED in the fetcher's failures and returned as None (rule 1). The shared
    `Fetch` only catches FMP's own errors; on 10-15 one cut-off 800 KB response
    stopped the whole run."""
    import http.client

    def call(path, **params):
        last = None
        for _ in range(tries):
            try:
                return fetch(path, **params)
            except (http.client.HTTPException, OSError) as exc:
                last = exc
        with fetch.lock:
            name = type(last).__name__
            fetch.failures[name] = fetch.failures.get(name, 0) + 1
        return None
    call.lock, call.failures = fetch.lock, fetch.failures
    return call


def daily(fetch, sym, path, field):
    """{date: value > 0} over both chunks (one FMP call returns at most 5,000
    days), or None when a chunk failed: a half-fetched series is never used."""
    out = {}
    for a, b in CHUNKS:
        rows = fetch(path, symbol=sym, **{'from': a, 'to': b})
        if rows is None:
            return None
        for r in rows:
            v = r.get(field)
            if isinstance(v, (int, float)) and v > 0 and isinstance(r.get('date'), str):
                out[r['date'][:10]] = float(v)
    return out


def granular(series):
    """Rule 9: a daily series, not weekly or monthly bars answered without error."""
    ds = sorted(series)
    if len(ds) < 60:
        return False
    gaps = [(dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days for a, b in zip(ds, ds[1:])]
    return st.median(gaps) <= 3


def collect(tickers, fetch, workers=6):
    """Everything the study reads, with every rejection counted. Names are
    fetched in parallel; `fetch` keeps the shared rate limit."""
    import concurrent.futures as cf

    def one(t):
        rec = {'adj': daily(fetch, t, 'historical-price-eod/dividend-adjusted', 'adjClose'),
               'raw': daily(fetch, t, 'historical-price-eod/full', 'close'),
               'vol': daily(fetch, t, 'historical-price-eod/dividend-adjusted', 'volume')}
        if t != MARKET:
            rec['earnings'] = fetch('earnings', symbol=t, limit=400) or []
            rec['grades'] = fetch('grades', symbol=t) or []
        return t, rec
    data, rejected = {}, {}
    with cf.ThreadPoolExecutor(workers) as pool:
        for t, rec in pool.map(one, [MARKET] + list(tickers)):
            if rec['adj'] is None or rec['raw'] is None:
                rejected[t] = 'FETCH_FAILED'
                continue
            if not granular(rec['adj']):
                rejected[t] = 'ADJUSTED_SERIES_NOT_DAILY_OR_EMPTY'
                continue
            data[t] = rec
    if MARKET not in data:
        raise SystemExit('the market series (%s) could not be fetched: %s' % (MARKET, rejected.get(MARKET)))
    return data, rejected


# ── panel ───────────────────────────────────────────────────────────────────

class Panel:
    """Adjusted closes on XIU.TO's session calendar, and H-session abnormal returns."""

    def __init__(self, data, tickers):
        self.cal = sorted(data[MARKET]['adj'])
        self.idx = {d: i for i, d in enumerate(self.cal)}
        self.tickers = [t for t in tickers if t in data]
        self.row = {t: k for k, t in enumerate(self.tickers)}
        n = len(self.cal)
        self.px = np.full((len(self.tickers), n), np.nan)
        for t, k in self.row.items():
            for d, v in data[t]['adj'].items():
                i = self.idx.get(d)
                if i is not None:
                    self.px[k, i] = v
        self.vol = np.full(self.px.shape, np.nan)
        for t, k in self.row.items():
            for d, v in (data[t].get('vol') or {}).items():
                i = self.idx.get(d)
                if i is not None:
                    self.vol[k, i] = v
        self.mkt = np.array([data[MARKET]['adj'][d] for d in self.cal])
        self.ar = {h: self._abnormal(h) for h in HORIZONS}

    def _abnormal(self, h):
        out = np.full(self.px.shape, np.nan)
        if h < len(self.cal):
            stock = self.px[:, h:] / self.px[:, :-h] - 1.0
            market = self.mkt[h:] / self.mkt[:-h] - 1.0
            out[:, :-h] = 100.0 * (stock - market)
        return out

    def first_after(self, day):
        i = bisect.bisect_right(self.cal, day)
        return i if i < len(self.cal) else None

    def last_before(self, day):
        i = bisect.bisect_left(self.cal, day) - 1
        return i if i >= 0 else None

    def on_or_after(self, day):
        i = bisect.bisect_left(self.cal, day)
        return i if i < len(self.cal) else None

    def close(self, t, i):
        v = self.px[self.row[t], i]
        return None if np.isnan(v) else float(v)


def _num(v):
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def earnings_events(panel, data, dropped):
    """One row per report: P0, D1 (the entry), SUE and EAR. Causal at D1's close."""
    out = []
    last = panel.cal[-1]
    for t in panel.tickers:
        seen = set()
        for r in data[t].get('earnings') or []:
            day = str(r.get('date') or '')[:10]
            a, e = _num(r.get('epsActual')), _num(r.get('epsEstimated'))
            if not day or day in seen or day >= last or a is None:
                continue
            seen.add(day)
            p0, d1 = panel.last_before(day), panel.first_after(day)
            if p0 is None or d1 is None:
                dropped['earnings_outside_calendar'] = dropped.get('earnings_outside_calendar', 0) + 1
                continue
            c0, c1 = panel.close(t, p0), panel.close(t, d1)
            if c0 is None or c1 is None:
                dropped['earnings_missing_bar'] = dropped.get('earnings_missing_bar', 0) + 1
                continue
            raw0 = data[t]['raw'].get(panel.cal[p0])
            sue = (a - e) / raw0 if e is not None and raw0 else None
            ear = 100.0 * ((c1 / c0 - 1.0) - (panel.mkt[d1] / panel.mkt[p0] - 1.0))
            ra, re_ = _num(r.get('revenueActual')), _num(r.get('revenueEstimated'))
            out.append({'ticker': t, 'report': day, 'p0': p0, 'entry': d1, 'sue': sue, 'ear': ear,
                        'rev': (None if ra is None or re_ is None else (ra > re_) - (ra < re_))})
    return out


def grade_events(panel, data, dropped):
    """One row per (name, D0): the net of that day's upgrades and downgrades."""
    out = []
    for t in panel.tickers:
        net = {}
        for g in data[t].get('grades') or []:
            act, day = g.get('action'), str(g.get('date') or '')[:10]
            if act not in ('upgrade', 'downgrade') or not day:
                continue
            d0 = panel.on_or_after(day)
            if d0 is None:
                continue
            net[d0] = net.get(d0, 0) + (1 if act == 'upgrade' else -1)
        for d0, n in sorted(net.items()):
            if n == 0:
                dropped['grades_net_zero'] = dropped.get('grades_net_zero', 0) + 1
                continue
            if panel.close(t, d0) is None:
                dropped['grades_missing_bar'] = dropped.get('grades_missing_bar', 0) + 1
                continue
            out.append({'ticker': t, 'entry': d0, 'side': 1 if n > 0 else -1})
    return out


def rolling_sides(events, key, cal):
    """Long above the 70th, short below the 30th percentile of the same
    quantity over every event entered in the 365 days strictly before this
    one; None in the middle or in the burn-in. Same-day events never see
    each other."""
    rows = sorted((e for e in events if e.get(key) is not None), key=lambda e: e['entry'])
    window, lo = [], 0
    side = {}
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j]['entry'] == rows[i]['entry']:
            j += 1
        today = dt.date.fromisoformat(cal[rows[i]['entry']])
        start = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
        while lo < i and cal[rows[lo]['entry']] < start:
            window.pop(bisect.bisect_left(window, rows[lo][key]))
            lo += 1
        for e in rows[i:j]:
            if len(window) >= BURN_IN:
                rank = bisect.bisect_left(window, e[key]) / len(window)
                side[id(e)] = 1 if rank > HIGH else -1 if rank < LOW else 0
        for e in rows[i:j]:
            bisect.insort(window, e[key])
        i = j
    return side


def signal_events(panel, data, dropped):
    """{signal: [{'ticker', 'entry', 'side', ...}]} as registered."""
    earn = earnings_events(panel, data, dropped)
    s1 = rolling_sides(earn, 'sue', panel.cal)
    s2 = rolling_sides(earn, 'ear', panel.cal)
    out = {k: [] for k in SIGNALS}
    for e in earn:
        a, b = s1.get(id(e)), s2.get(id(e))
        if a:
            out['W1'].append({**e, 'side': a})
        if b:
            out['W2'].append({**e, 'side': b})
        if a and b and a == b:
            out['W3'].append({**e, 'side': a})
    out['W4'] = grade_events(panel, data, dropped)
    return out, earn


# ── statistics ──────────────────────────────────────────────────────────────

def outcomes(panel, events, h):
    """y in % per trade, signed; events whose exit bar is missing are dropped."""
    rows = []
    for e in events:
        v = panel.ar[h][panel.row[e['ticker']], e['entry']]
        if not np.isnan(v):
            rows.append({**e, 'y': e['side'] * float(v)})
    return rows


def cluster_se(values, groups, draws=BOOT, seed=SEED):
    """Bootstrap se of the mean, resampling whole groups."""
    keys = sorted(set(groups))
    if len(keys) < 2:
        return None
    pos = {g: k for k, g in enumerate(keys)}
    sums, counts = np.zeros(len(keys)), np.zeros(len(keys))
    for v, g in zip(values, groups):
        sums[pos[g]] += v
        counts[pos[g]] += 1
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(keys), size=(draws, len(keys)))
    means = sums[pick].sum(axis=1) / np.maximum(counts[pick].sum(axis=1), 1)
    return float(means.std(ddof=1))


def conservative_t(rows, h):
    ys = [r['y'] for r in rows]
    mean = float(np.mean(ys))
    se_name = cluster_se(ys, [r['ticker'] for r in rows])
    se_block = cluster_se(ys, [r['entry'] // h for r in rows], seed=SEED + 1)
    ts = [mean / s for s in (se_name, se_block) if s]
    t = min(ts, key=abs) if ts else None
    se = max(s for s in (se_name, se_block) if s) if ts else None
    return mean, se, t, se_name, se_block


def placebo(panel, events, rows, h, family_entries, draws=PLACEBO_DRAWS, seed=SEED):
    """Each event keeps its name and sign and moves to a random session within
    ±250 of its own entry, never within 10 sessions of a real event of its
    family on that name, and only where the H-session return exists."""
    rng = np.random.default_rng(seed)
    ar = panel.ar[h]
    near = {}                     # per name: sessions within PLACEBO_GAP of a real event
    for t, real in family_entries.items():
        mask = np.zeros(ar.shape[1], dtype=bool)
        for i in real:
            mask[max(0, i - PLACEBO_GAP):i + PLACEBO_GAP + 1] = True
        near[t] = mask
    choices, signs, rws = [], [], []
    for e in events:
        k = panel.row[e['ticker']]
        lo, hi = max(0, e['entry'] - PLACEBO_SPAN), min(ar.shape[1] - 1, e['entry'] + PLACEBO_SPAN)
        ok = ~np.isnan(ar[k, lo:hi + 1])
        if e['ticker'] in near:
            ok &= ~near[e['ticker']][lo:hi + 1]
        ok = np.nonzero(ok)[0] + lo
        if len(ok):
            choices.append(ok)
            signs.append(e['side'])
            rws.append(k)
    if not choices:
        return None, []
    signs, rws = np.array(signs, dtype=float), np.array(rws)
    lens = np.array([len(c) for c in choices])
    flat = np.concatenate(choices)
    offs = np.concatenate([[0], np.cumsum(lens)[:-1]])
    means = np.empty(draws)
    for d in range(draws):
        cols = flat[offs + rng.integers(0, lens)]
        means[d] = float(np.mean(signs * ar[rws, cols]))
    obs = float(np.mean([r['y'] for r in rows]))
    return float(np.mean(np.abs(means) >= abs(obs))), means


def blocks(rows, n=4):
    ordered = sorted(rows, key=lambda r: r['entry'])
    size = len(ordered) / n
    return [float(np.mean([r['y'] for r in ordered[int(b * size):int((b + 1) * size)]]))
            for b in range(n)] if len(ordered) >= n else []


def cost(h, rows):
    short = sum(1 for r in rows if r['side'] < 0) / len(rows) if rows else 0.0
    return COST_RT + BORROW_YR * h / 252.0 * short


def verdict(s):
    m, t, p, bl, med, net = s['mean'], s['t'], s['placebo_p'], s['blocks'], s['median'], s['net_mean']
    if t is None or p is None:
        return 'NOT COMPUTABLE'
    if m > 0 and t >= BAR and p < 0.01 and sum(b > 0 for b in bl) >= 3 and med > 0 and net > 0:
        return 'DRIFT'
    if m < 0 and t <= -BAR and p < 0.01 and sum(b < 0 for b in bl) >= 3 and med < 0:
        return 'REVERSAL'
    return 'NULL' if s['control_t'] >= BAR else 'UNDERPOWERED'


def summarize(panel, events, h, family_entries, *, with_placebo=True):
    rows = outcomes(panel, events, h)
    if len(rows) < 20:
        return {'n': len(rows), 'verdict': 'NOT COMPUTABLE'}
    mean, se, t, se_name, se_block = conservative_t(rows, h)
    p, _ = placebo(panel, events, rows, h, family_entries) if with_placebo else (None, None)
    ys = [r['y'] for r in rows]
    s = {'n': len(rows), 'names': len({r['ticker'] for r in rows}),
         'long': sum(1 for r in rows if r['side'] > 0), 'short': sum(1 for r in rows if r['side'] < 0),
         'mean': mean, 'median': float(np.median(ys)), 'win': float(np.mean([y > 0 for y in ys])),
         'se': se, 't': t, 't_name': mean / se_name if se_name else None,
         't_block': mean / se_block if se_block else None, 'placebo_p': p,
         'blocks': blocks(rows), 'cost': cost(h, rows), 'net_mean': mean - cost(h, rows),
         'control_t': PLANT / se if se else 0.0, 'mde': (BAR + Z80) * se if se else None,
         'first': panel.cal[min(r['entry'] for r in rows)], 'last': panel.cal[max(r['entry'] for r in rows)]}
    s['verdict'] = verdict(s) if with_placebo else None
    return s


def split_stat(rows, h):
    if len(rows) < 20:
        return {'n': len(rows)}
    mean, se, t, _, _ = conservative_t(rows, h)
    return {'n': len(rows), 'mean': mean, 't': t, 'median': float(np.median([r['y'] for r in rows]))}


def splits(panel, events, h, meta, earn):
    """Descriptive only (registered list): never a verdict, never a rule."""
    rows = outcomes(panel, events, h)
    if not rows:
        return {}
    liq = sorted(meta[t].get('median_dollar_volume_20') or 0 for t in panel.tickers)
    cut1, cut2 = liq[len(liq) // 3], liq[2 * len(liq) // 3]

    def tercile(t):
        v = meta[t].get('median_dollar_volume_20') or 0
        return 'low' if v < cut1 else 'mid' if v < cut2 else 'high'

    def sector(t):
        # The list carries TMX's sector labels ('Oil & Gas', 'Mining', ...), with
        # FMP's ('Energy', 'Basic Materials', ...) where TMX had none.
        s, ind = meta[t].get('sector'), str(meta[t].get('industry') or '')
        if s in ('Energy', 'Oil & Gas'):
            return 'energy'
        if s in ('Basic Materials', 'Mining') or 'Gold' in ind or 'Mining' in ind:
            return 'materials and mining'
        return {'Financial Services': 'financials', 'Technology': 'technology'}.get(s, 'the rest')

    m50 = {}

    def regime(i):
        if i not in m50:
            m50[i] = None if i < 50 else bool(panel.mkt[i] > panel.mkt[i - 50:i].mean())
        return m50[i]

    out = {'legs': {'long': split_stat([r for r in rows if r['side'] > 0], h),
                    'short': split_stat([r for r in rows if r['side'] < 0], h)},
           'period': {'before 2012': split_stat([r for r in rows if panel.cal[r['entry']] < SPLIT_YEAR], h),
                      '2012 on': split_stat([r for r in rows if panel.cal[r['entry']] >= SPLIT_YEAR], h)},
           'liquidity': {k: split_stat([r for r in rows if tercile(r['ticker']) == k], h)
                         for k in ('low', 'mid', 'high')},
           'sector': {k: split_stat([r for r in rows if sector(r['ticker']) == k], h)
                      for k in ('energy', 'materials and mining', 'financials', 'technology', 'the rest')},
           'market at entry': {'XIU above its 50-session average':
                               split_stat([r for r in rows if regime(r['entry']) is True], h),
                               'below': split_stat([r for r in rows if regime(r['entry']) is False], h)}}
    if 'report' in rows[0]:
        per_day = {}
        for e in earn:
            per_day[e['report']] = per_day.get(e['report'], 0) + 1
        out['busy days'] = {'10+ names reporting': split_stat([r for r in rows if per_day.get(r['report'], 0) >= BUSY], h),
                            'fewer': split_stat([r for r in rows if per_day.get(r['report'], 0) < BUSY], h)}
        out['revenue surprise'] = {'same side': split_stat([r for r in rows if r.get('rev') == r['side']], h),
                                   'not': split_stat([r for r in rows if r.get('rev') != r['side']], h)}
    else:
        after = {}
        for e in earn:
            # the report's own session (P0 + 1) and the two after it
            after.setdefault(e['ticker'], set()).update(range(e['p0'] + 1, e['p0'] + 4))
        out['after an earnings report'] = {
            'within 2 sessions': split_stat([r for r in rows if r['entry'] in after.get(r['ticker'], ())], h),
            'the rest': split_stat([r for r in rows if r['entry'] not in after.get(r['ticker'], ())], h)}
    return out


def volume_peak(panel, e):
    """'on' when the report's volume spike falls on its own session or D1 (the
    date is right and the entry follows the reaction), 'after' when it falls in
    the three sessions after the entry (FMP's date is early: the entry came
    BEFORE the market reacted). None without volume."""
    k = panel.row[e['ticker']]
    lo, hi = e['p0'] + 1, min(e['entry'] + 3, panel.vol.shape[1] - 1)
    v = panel.vol[k, lo:hi + 1]
    if not np.any(v > 0):
        return None
    return 'after' if lo + int(np.nanargmax(v)) > e['entry'] else 'on'


def date_check(panel, events, earn):
    """A validity check of the registered premise ("everything is known at the
    entry close"), added after the first run showed the W1 gain sits in the
    two sessions after entry. Not a hypothesis and never a trading rule: the
    volume after the entry is not known at the entry."""
    ret1 = np.full(panel.px.shape, np.nan)
    ret1[:, 1:] = 100 * ((panel.px[:, 1:] / panel.px[:, :-1] - 1) - (panel.mkt[1:] / panel.mkt[:-1] - 1))
    periods = (('before 2012', lambda e: panel.cal[e['entry']] < SPLIT_YEAR),
               ('2012 on', lambda e: panel.cal[e['entry']] >= SPLIT_YEAR))
    out = {'reports_volume_peak_after_entry': {}, 'w1_daily_path': {}, 'w1_h10_by_date': {}}
    for per, f in periods:
        w = [x for x in (volume_peak(panel, e) for e in earn if f(e)) if x]
        out['reports_volume_peak_after_entry'][per] = {'n': len(w), 'share': float(np.mean([x == 'after' for x in w])) if w else None}
        path = {}
        for d in range(-1, 11):
            vals = [e['side'] * ret1[panel.row[e['ticker']], e['entry'] + d] for e in events['W1']
                    if f(e) and e['entry'] + d < ret1.shape[1]]
            vals = [v for v in vals if not np.isnan(v)]
            path[str(d)] = float(np.mean(vals)) if vals else None
        out['w1_daily_path'][per] = path
    for label, want in (('date confirmed by volume', 'on'), ('volume peak after the entry', 'after')):
        rows = outcomes(panel, [e for e in events['W1'] if volume_peak(panel, e) == want], PRIMARY)
        out['w1_h10_by_date'][label] = {per: split_stat([r for r in rows if f(r)], PRIMARY) for per, f in periods}
    return out


def run(data, tickers, meta, rejected):
    panel = Panel(data, tickers)
    dropped = {}
    events, earn = signal_events(panel, data, dropped)
    # The placebo keeps clear of EVERY report and rating change on the name,
    # traded or not: a report that landed in the middle tercile is still news.
    fam = {'earnings': {}, 'grades': {}}
    for e in earn:
        fam['earnings'].setdefault(e['ticker'], set()).add(e['entry'])
    for e in events['W4']:
        fam['grades'].setdefault(e['ticker'], set()).add(e['entry'])
    fam = {k: {t: sorted(v) for t, v in d.items()} for k, d in fam.items()}
    out = {'registered': 'PREREGISTER_day135_weeks.md (3e0e8bc)',
           'names': len(panel.tickers), 'sessions': len(panel.cal),
           'calendar': [panel.cal[0], panel.cal[-1]], 'rejected_series': rejected,
           'dropped': dropped, 'earnings_reports': len(earn), 'signals': {}}
    for k in SIGNALS:
        res = {}
        for h in HORIZONS:
            res[str(h)] = summarize(panel, events[k], h, fam[FAMILY[k]])
        res['splits_h10'] = splits(panel, events[k], PRIMARY, meta, earn)
        out['signals'][k] = res
    out['date_check'] = date_check(panel, events, earn)
    return out


# ── reporting ───────────────────────────────────────────────────────────────

def _f(v, fmt='%+.3f'):
    return '—' if v is None else fmt % v


def table(out):
    lines = ['| Signal | H | n | long/short | mean % | median % | win | t (name, block) | placebo p | blocks | net % | verdict |',
             '|---|---:|---:|---|---:|---:|---:|---|---:|---|---:|---|']
    for k, res in out['signals'].items():
        for h in HORIZONS:
            s = res[str(h)]
            if s.get('mean') is None:
                lines.append('| %s | %d | %d | — | — | — | — | — | — | — | — | %s |' % (k, h, s['n'], s['verdict']))
                continue
            lines.append('| %s | %d | %d | %d/%d | %s | %s | %.1f%% | %s (%s, %s) | %s | %s | %s | %s |' % (
                k, h, s['n'], s['long'], s['short'], _f(s['mean']), _f(s['median']), 100 * s['win'],
                _f(s['t'], '%+.2f'), _f(s['t_name'], '%+.2f'), _f(s['t_block'], '%+.2f'),
                _f(s['placebo_p'], '%.3f'), ' '.join('%+.2f' % b for b in s['blocks']),
                _f(s['net_mean']), s['verdict'] if h == PRIMARY else (s['verdict'] or '') + ' (secondary)'))
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--out', default=str(OUT))
    a = p.parse_args(argv)
    from replay_drift import Fetch
    fetch = robust(Fetch(CACHE))
    tickers, meta = names()
    data, rejected = collect(tickers, fetch)
    out = run(data, tickers, meta, rejected)
    out['fetch_failures'] = fetch.failures
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True))
    print(table(out))
    print(json.dumps({k: out[k] for k in ('names', 'sessions', 'calendar', 'earnings_reports',
                                          'dropped', 'rejected_series', 'fetch_failures')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
