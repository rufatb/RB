#!/usr/bin/env python3
"""Day-135c — can the Top 2's bad days be made smaller? Two direction-blind rules.

Registered first: PREREGISTER_day135c_risk.md. SIZE, not direction: day-132
(rejection #47) already found that a move of >= 1 ATR neither continues nor
recovers after 09:45.

  R1  one position per side: the swing of two same-side picks against a
      long/short pair (and a single pick);
  R2  skip yesterday's big movers: the next session's swing after a
      |move_atr| >= 1 move against the rest, with the signed mean required
      to stay null.

Data: the day-135b cache of FMP dividend-adjusted daily bars for the 150
names (.rb-state/weeks_cache), 2016-01-04 -> 2026-10-14. The trade proxy is
the session's open -> close; daily bars cannot see 09:45.

    python risk_rules.py        # writes data/risk_day135c.json
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

import replay_weeks as W

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'risk_day135c.json'
PICKS = ROOT/'data'/'model_picks.csv'
START, END = '2016-01-04', '2026-10-14'
MOVER = 1.0
ATR_N = 14
PAIRS, SEED = 20000, 135
BAR = 1.15
LIVE_FROM = '2026-10-05'


def bars(fetch, sym):
    """{date: (open, high, low, close)} adjusted, from the cached chunks."""
    out = {}
    for a, b in W.CHUNKS:
        for r in fetch('historical-price-eod/dividend-adjusted', symbol=sym, **{'from': a, 'to': b}) or []:
            vals = [r.get(k) for k in ('adjOpen', 'adjHigh', 'adjLow', 'adjClose')]
            if all(isinstance(v, (int, float)) and v > 0 for v in vals) and vals[1] >= vals[2]:
                out[str(r['date'])[:10]] = tuple(float(v) for v in vals)
    return out


class Daily:
    """Open, high, low and close on XIU.TO's calendar; the open -> close
    return and the prior session's move in ATR units, as daily_technicals."""

    def __init__(self, fetch, tickers):
        mkt = bars(fetch, W.MARKET)
        self.cal = [d for d in sorted(mkt) if START <= d <= END]
        idx = {d: i for i, d in enumerate(self.cal)}
        self.tickers = list(tickers)
        n, k = len(self.cal), len(self.tickers)
        o, h, l, c = (np.full((k, n), np.nan) for _ in range(4))
        for j, t in enumerate(self.tickers):
            for d, (a, b, e, f) in bars(fetch, t).items():
                i = idx.get(d)
                if i is not None:
                    o[j, i], h[j, i], l[j, i], c[j, i] = a, b, e, f
        mo = np.array([mkt[d][0] for d in self.cal])
        mc = np.array([mkt[d][3] for d in self.cal])
        self.r = 100 * (c / o - 1)                       # raw open -> close, % of the open
        self.mr = 100 * (mc / mo - 1)
        self.adj = self.r - self.mr                      # against XIU over the same session
        prior = np.roll(c, 1, axis=1)
        prior[:, 0] = np.nan
        tr = np.fmax(h - l, np.fmax(np.abs(h - prior), np.abs(l - prior)))
        atr = np.full(tr.shape, np.nan)
        for i in range(ATR_N, n):
            w = tr[:, i - ATR_N + 1:i + 1]
            ok = ~np.isnan(w).any(axis=1)
            atr[ok, i] = w[ok].mean(axis=1)
        with np.errstate(invalid='ignore', divide='ignore'):
            move = (c - prior) / atr                     # the session's own move, in its ATRs
        self.m = np.full(move.shape, np.nan)             # the PRIOR session's move, seen at D
        self.m[:, 1:] = move[:, :-1]
        self.idx = idx


def sample_pairs(d, rng, n=PAIRS):
    """n random (session, name a, name b) with both returns present."""
    k, s = d.r.shape
    out = []
    while len(out) < n:
        i = rng.integers(0, s, size=n)
        a = rng.integers(0, k, size=n)
        b = rng.integers(0, k, size=n)
        ok = (a != b) & ~np.isnan(d.r[a, i]) & ~np.isnan(d.r[b, i])
        out.extend(zip(i[ok], a[ok], b[ok]))
    return np.array(out[:n])


def r1(d):
    rng = np.random.default_rng(SEED)
    p = sample_pairs(d, rng)
    ra, rb = d.r[p[:, 1], p[:, 0]], d.r[p[:, 2], p[:, 0]]
    rho = float(np.corrcoef(ra, rb)[0, 1])
    same, pair, single = ra + rb, ra - rb, ra
    sd = {k: float(np.std(v, ddof=1)) for k, v in (('same side, two picks', same),
                                                   ('long and short, two picks', pair),
                                                   ('one pick', single))}
    worst = {k: float(np.percentile(v, 5)) for k, v in (('same side, two picks', same),
                                                        ('long and short, two picks', pair),
                                                        ('one pick', single))}
    ratio = sd['same side, two picks'] / sd['long and short, two picks']
    # Days the market itself moved 1%+: the days a one-sided book is hurt.
    big = np.abs(d.mr[p[:, 0]]) >= 1.0
    rho_big = float(np.corrcoef(ra[big], rb[big])[0, 1]) if big.sum() > 100 else None
    return {'pairs': len(p), 'rho': rho, 'rho_on_market_days_1pct': rho_big, 'sd': sd,
            'worst_5pct': worst, 'ratio_same_to_long_short': ratio,
            'verdict': 'PASS' if ratio >= BAR else 'FAIL'}


def clustered_t(values, groups):
    values, groups = np.asarray(values), np.asarray(groups)
    mean = float(values.mean())
    sums = {}
    for g, v in zip(groups, values - mean):
        sums[g] = sums.get(g, 0.0) + v
    G, n = len(sums), len(values)
    se = math.sqrt(sum(s * s for s in sums.values()) / n ** 2 * G / (G - 1)) if G > 1 else None
    return mean, se, (mean / se if se else None)


def r2(d):
    m, r, adj = d.m, d.r, d.adj
    ok = ~np.isnan(m) & ~np.isnan(r)
    mover = ok & (np.abs(m) >= MOVER)
    calm = ok & (np.abs(m) < MOVER)
    stats = {}
    for name, mask in (('movers (|move| >= 1 ATR)', mover), ('the rest', calm)):
        stats[name] = {'n': int(mask.sum()), 'sd_raw': float(np.std(r[mask], ddof=1)),
                       'sd_vs_xiu': float(np.std(adj[mask], ddof=1)),
                       'share_moving_3pct': float(np.mean(np.abs(r[mask]) > 3.0)),
                       'worst_1pct_raw': float(np.percentile(r[mask], 1)),
                       'best_99pct_raw': float(np.percentile(r[mask], 99))}
    rows, cols = np.nonzero(mover)
    y = np.sign(m[rows, cols]) * adj[rows, cols]          # continuation positive, against XIU
    mean, se, t = clustered_t(y, cols)
    ratio = stats['movers (|move| >= 1 ATR)']['sd_raw'] / stats['the rest']['sd_raw']
    passed = ratio >= BAR and t is not None and abs(t) < 2
    # By the name's own normal day (ATR %), so the share of the ratio that is
    # simply "volatile names move more" is visible.
    return {'groups': stats, 'ratio_sd_movers_to_rest': ratio,
            'signed_mean_movers': {'mean': mean, 'se': se, 't': t, 'n': int(len(y)),
                                   'reading': 'continuation positive, open -> close against XIU'},
            'verdict': 'PASS' if passed else 'FAIL'}


def describe(d):
    """Descriptive only, added AFTER the registered verdicts (no verdict here):
    is R2's wider swing the same name after its own move, or just volatile
    names; does it hold every year; and does a big fall bounce (the owner's
    "unless it's a recovery")?"""
    m, r, adj = d.m, d.r, d.adj
    ok = ~np.isnan(m) & ~np.isnan(r)
    ratios = []
    for j in range(len(d.tickers)):
        a, b = ok[j] & (np.abs(m[j]) >= MOVER), ok[j] & (np.abs(m[j]) < MOVER)
        if a.sum() >= 30 and b.sum() >= 30:
            ratios.append(np.std(r[j, a], ddof=1) / np.std(r[j, b], ddof=1))
    ratios = np.array(ratios)
    years = np.array([int(x[:4]) for x in d.cal])
    by_year = {}
    for y in sorted(set(years.tolist())):
        cols = years == y
        a = ok[:, cols] & (np.abs(m[:, cols]) >= MOVER)
        b = ok[:, cols] & (np.abs(m[:, cols]) < MOVER)
        by_year[str(y)] = float(np.std(r[:, cols][a], ddof=1) / np.std(r[:, cols][b], ddof=1))
    after = {}
    for name, mask in (('fall of 1+ ATR', ok & (m <= -MOVER)), ('rise of 1+ ATR', ok & (m >= MOVER)),
                       ('fall of 2+ ATR', ok & (m <= -2 * MOVER)), ('rise of 2+ ATR', ok & (m >= 2 * MOVER)),
                       ('the rest', ok & (np.abs(m) < MOVER))):
        rows, cols = np.nonzero(mask)
        mean, se, t = clustered_t(adj[rows, cols], cols)
        after[name] = {'n': int(len(rows)), 'mean_vs_xiu': mean, 't': t,
                       'sd_raw': float(np.std(r[rows, cols], ddof=1)),
                       'worst_5pct_raw': float(np.percentile(r[rows, cols], 5))}
    calm = np.std(r[ok & (np.abs(m) < MOVER)], ddof=1)
    share = [float(np.mean(np.abs(m[ok[:, i], i]) >= MOVER)) for i in range(m.shape[1]) if ok[:, i].sum() > 50]
    # House rules 4 and 10: R2's null signed mean needs a control. A planted
    # continuation of 0.10% (day-132's) shows at edge / se, never (mean + edge) / se.
    rows, cols = np.nonzero(ok & (np.abs(m) >= MOVER))
    _, se, _ = clustered_t(np.sign(m[rows, cols]) * adj[rows, cols], cols)
    return {'note': 'descriptive, added after the registered verdicts; no verdict',
            'signed_mean_control': {'planted_pct': 0.10, 't_planted': 0.10 / se,
                                    'mde80_at_t2_pct': (2.0 + 0.84) * se},
            'within_name': {'names': len(ratios), 'median_ratio': float(np.median(ratios)),
                            'share_above_1': float(np.mean(ratios > 1)),
                            'p25': float(np.percentile(ratios, 25)), 'p75': float(np.percentile(ratios, 75))},
            'ratio_by_year': by_year,
            'next_session_after': {**after, 'reading': 'open -> close against XIU, up positive'},
            'ratio_2atr': float(np.std(r[ok & (np.abs(m) >= 2 * MOVER)], ddof=1) / calm),
            'movers_share_of_a_session': {'median': float(np.median(share)),
                                          'p90': float(np.percentile(share, 90))}}


def live(d, path=PICKS):
    """The council-era Top 2, read against both rules (descriptive)."""
    rows = [r for r in csv.DictReader(open(path))
            if r.get('model') == 'top2' and r.get('kind') == 'pick' and r.get('session', '') >= LIVE_FROM]
    row_of = {t: k for k, t in enumerate(d.tickers)}
    out = []
    by_session = {}
    for r in rows:
        k, i = row_of.get(r['ticker']), d.idx.get(r['session'])
        m = float(d.m[k, i]) if k is not None and i is not None and not np.isnan(d.m[k, i]) else None
        rp = float(r['r_pct']) if (r.get('r_pct') or '').strip() else None
        e = {'session': r['session'], 'ticker': r['ticker'], 'side': r['side'], 'move_atr': m,
             'r_pct': rp, 'mover': None if m is None else abs(m) >= MOVER}
        out.append(e)
        by_session.setdefault(r['session'], []).append(e)
    same_side = [s for s, es in by_session.items() if len(es) == 2 and es[0]['side'] == es[1]['side']]
    kept = [e for e in out if e['mover'] is False and e['r_pct'] is not None]
    dropped = [e for e in out if e['mover'] is True and e['r_pct'] is not None]
    return {'picks': out, 'sessions': len(by_session), 'same_side_sessions': sorted(same_side),
            'movers': sum(1 for e in out if e['mover']), 'unknown_move': sum(1 for e in out if e['mover'] is None),
            'r2_would_drop': {'n': len(dropped), 'mean': float(np.mean([e['r_pct'] for e in dropped])) if dropped else None,
                              'right': sum(1 for e in dropped if e['r_pct'] > 0)},
            'r2_would_keep': {'n': len(kept), 'mean': float(np.mean([e['r_pct'] for e in kept])) if kept else None,
                              'right': sum(1 for e in kept if e['r_pct'] > 0)}}


def main():
    from replay_drift import Fetch
    fetch = W.robust(Fetch(W.CACHE))
    tickers, _ = W.names()
    d = Daily(fetch, tickers)
    out = {'registered': 'PREREGISTER_day135c_risk.md', 'window': [d.cal[0], d.cal[-1]],
           'sessions': len(d.cal), 'names': len(d.tickers),
           'name_days': int((~np.isnan(d.r)).sum()), 'fetch_failures': fetch.failures,
           'R1': r1(d), 'R2': r2(d), 'R2_described': describe(d), 'live_top2': live(d)}
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps({k: out[k] for k in ('window', 'sessions', 'names', 'name_days', 'R1', 'R2')}, indent=1))
    lv = out['live_top2']
    print(json.dumps({k: lv[k] for k in lv if k != 'picks'}, indent=1))
    for e in lv['picks']:
        print(e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
