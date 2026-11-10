#!/usr/bin/env python3
"""Day-149b — the commodity nowcast against consensus, on history
(PREREGISTER_day149_nowcast.md; council lab item 13). ONE LOOK.

For each corroborated quarter of the 19 gold and silver producers that also
trade in New York: the nowcast's side against consensus, and the Toronto
listing's move from the close before FMP's report date to the close three
sessions after it, against XGD.TO. FMP only; raw answers are cached in
.rb-state/nowcast_cache so a rerun reads the same bytes.

    python nowcast_history.py        writes data/nowcast_day149.json
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

import nowcast as N

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'nowcast_day149.json'
NAMES = ('AAUC.TO', 'ABX.TO', 'AEM.TO', 'AG.TO', 'AGI.TO', 'ARIS.TO', 'AYA.TO', 'BTO.TO', 'CG.TO',
         'ELD.TO', 'EQX.TO', 'FNV.TO', 'FVI.TO', 'IMG.TO', 'K.TO', 'OGC.TO', 'PAAS.TO', 'SSRM.TO',
         'WPM.TO')
START, END = '2012-01-01', '2026-11-09'
BENCH = 'XGD.TO'
HOLD, PRE = 3, 20                 # sessions after FMP's date; sessions before the entry (descriptive)
AGREE, MATCH_DAYS = 0.03, 3       # the two listings' surprises; their dates
BAR, PLACEBO_P, DRAWS, SEED = 3.0, 0.01, 2000, 149
COST, PLANT = 0.13, 1.0           # % a report
REGISTRATION = 'PREREGISTER_day149_nowcast.md'


# ── data ────────────────────────────────────────────────────────────────────

class Cache:
    """FMP answers kept as they came, one file per question."""
    def __init__(self, root, get=None):
        self.root, self.get, self.failures = Path(root), get, {}
        self.root.mkdir(parents=True, exist_ok=True)

    def __call__(self, name, path, **params):
        file = self.root/(name + '.json')
        if file.is_file():
            return json.loads(file.read_text())
        if self.get is None:
            import fmp_client as F
            self.get = lambda p, **kw: F.get(p, retries=2, **kw)        # noqa: E731
        try:
            data = self.get(path, **params)
        except Exception as exc:                  # a code, never the URL
            code = str(exc) if str(exc).isupper() and ' ' not in str(exc) else type(exc).__name__
            self.failures[code] = self.failures.get(code, 0) + 1
            return None
        file.write_text(json.dumps(data))
        return data


def closes(rows):
    """(dates, adjusted closes), oldest first, from FMP dividend-adjusted rows."""
    by = {}
    for r in rows or []:
        c = r.get('adjClose')
        if isinstance(c, (int, float)) and c > 0:
            by[str(r.get('date'))[:10]] = float(c)
    dates = sorted(by)
    return dates, [by[d] for d in dates]


def window(dates, day, hold=HOLD, pre=PRE):
    """(entry, exit, pre) indexes for a report dated `day`: the last close
    before it, the close `hold` sessions after it, and `pre` sessions before
    the entry. None when the prices do not cover it."""
    i = bisect.bisect_left(dates, day)             # the report's session, or the next one
    if i == 0 or i + hold >= len(dates):
        return None
    return i - 1, i + hold, (i - 1 - pre if i - 1 - pre >= 0 else None)


def surprise(row):
    a, e = row.get('revenueActual'), row.get('revenueEstimated')
    return a / e - 1 if isinstance(a, (int, float)) and isinstance(e, (int, float)) and e > 0 else None


def quarters(us_rows, to_rows, avgs):
    """The New York listing's quarters with a nowcast and a consensus since
    START, each flagged `agree` when the Toronto row within MATCH_DAYS gives a
    surprise within AGREE of it."""
    other = []
    for r in to_rows if isinstance(to_rows, list) else []:
        s = surprise(r)
        if s is not None:
            other.append((dt.date.fromisoformat(str(r['date'])[:10]), s))
    out = []
    for h in N.history(us_rows, avgs):
        if not START <= h['date'] <= END or h['gap'] is None or not h['consensus']:
            continue
        d = dt.date.fromisoformat(h['date'])
        s_us = h['actual'] / h['consensus'] - 1
        near = [s for day, s in other if abs((day - d).days) <= MATCH_DAYS]
        out.append({**h, 'surprise': s_us, 'agree': bool(near) and abs(near[0] - s_us) <= AGREE})
    return out


# ── statistics ──────────────────────────────────────────────────────────────

def clustered(rows):
    """(mean, t) of y over rows, clustered by `week`."""
    v = [r['y'] for r in rows]
    if not v:
        return None, None
    m = sum(v) / len(v)
    by = {}
    for r in rows:
        by.setdefault(r['week'], []).append(r['y'] - m)
    if len(by) < 3:
        return m, None
    ss = sum(sum(xs) ** 2 for xs in by.values())
    var = (len(by) / (len(by) - 1)) * ss / (len(v) ** 2)
    return m, (m / math.sqrt(var) if var > 0 else None)


def bar(rows, *, draws=DRAWS, seed=SEED):
    """The registered bar on sided rows ({'y', 'week', 'date', 'side', 'dev'})."""
    rows = sorted(rows, key=lambda r: r['date'])
    if len(rows) < 10:
        return {'n': len(rows), 'verdict': 'UNDERPOWERED', 'reason': 'fewer than 10 sided quarters'}
    m, t = clustered(rows)
    half = len(rows) // 2
    halves = [clustered(rows[:half])[0], clustered(rows[half:])[0]]
    rng = random.Random(seed)
    sides = [1 if r['side'] == 'LONG' else -1 for r in rows]
    devs = [r['dev'] for r in rows]
    hits = 0
    for _ in range(draws):
        rng.shuffle(sides)
        if sum(s * d for s, d in zip(sides, devs)) / len(devs) >= m:
            hits += 1
    p = (hits + 1) / (draws + 1)
    _, t_plant = clustered([{**r, 'y': r['y'] - m + PLANT} for r in rows])
    se = abs(m / t) if t else None
    passed = (t is not None and t >= BAR and p < PLACEBO_P and all(h > 0 for h in halves) and m > COST)
    powered = t_plant is not None and t_plant >= BAR
    return {'n': len(rows), 'weeks': len({r['week'] for r in rows}), 'mean_pct': round(m, 4),
            't': None if t is None else round(t, 2), 'placebo_p': round(p, 4),
            'halves_pct': [round(h, 4) for h in halves], 'net_pct': round(m - COST, 4),
            'right': sum(1 for r in rows if r['y'] > 0),
            'control_t_planted_1pct': None if t_plant is None else round(t_plant, 2),
            'mde_pct': None if se is None else round((BAR + 1.28) * se, 2),
            'verdict': 'NOWCAST_SORTS' if passed else 'NULL' if powered else 'UNDERPOWERED'}


def hit_rate(rows):
    """How often the nowcast's side matched the revenue surprise's sign, and
    its clustered t against a half."""
    marks = [{'y': (1.0 if (r['surprise'] > 0) == (r['side'] == 'LONG') else 0.0) - 0.5, 'week': r['week']}
             for r in rows if r['surprise'] != 0]
    m, t = clustered(marks)
    return {'n': len(marks), 'matched': sum(1 for x in marks if x['y'] > 0),
            'rate': None if m is None else round(m + 0.5, 4), 't_against_half': None if t is None else round(t, 2)}


def describe(rows, key='y'):
    v = [r[key] for r in rows if r.get(key) is not None]
    if len(v) < 3:
        return {'n': len(v)}
    m, t = clustered([{'y': x, 'week': r['week']} for r, x in
                      zip([r for r in rows if r.get(key) is not None], v)])
    return {'n': len(v), 'mean_pct': round(m, 4), 't': None if t is None else round(t, 2),
            'right': sum(1 for x in v if x > 0)}


# ── the run ─────────────────────────────────────────────────────────────────

def events(fetch, twins):
    """Every quarter with its reaction: ({rows}, counts)."""
    avgs = {s: N.averages(fetch(s, 'historical-price-eod/light', symbol=s, **{'from': '2009-01-01', 'to': END}))
            for s in set(N.METALS.values())}
    bd, bc = closes(fetch('px_' + BENCH.replace('.', '_'), 'historical-price-eod/dividend-adjusted',
                          symbol=BENCH, **{'from': '2011-10-01', 'to': END}))
    bench = dict(zip(bd, bc))
    counts = {'quarters': 0, 'agree': 0, 'no_prices': 0, 'window_incomplete': 0}
    rows = []
    for t in NAMES:
        us = twins[t]['us']
        qs = quarters(fetch('earnings_' + us, 'earnings', symbol=us, limit=120),
                      fetch('earnings_' + t.replace('.', '_'), 'earnings', symbol=t, limit=120),
                      avgs[N.metal_for(t)])
        dates, px = closes(fetch('px_' + t.replace('.', '_'), 'historical-price-eod/dividend-adjusted',
                                 symbol=t, **{'from': '2011-10-01', 'to': END}))
        for q in qs:
            counts['quarters'] += 1
            counts['agree'] += q['agree']
            if not dates:
                counts['no_prices'] += 1
                continue
            w = window(dates, q['date'])
            if not w or dates[w[0]] not in bench or dates[w[1]] not in bench:
                counts['window_incomplete'] += 1
                continue
            entry, exit_, pre = w
            r = 100 * ((px[exit_] / px[entry] - 1) - (bench[dates[exit_]] / bench[dates[entry]] - 1))
            before = None
            if pre is not None and dates[pre] in bench:
                before = 100 * ((px[entry] / px[pre] - 1) - (bench[dates[entry]] / bench[dates[pre]] - 1))
            iso = dt.date.fromisoformat(q['date']).isocalendar()
            rows.append({'ticker': t, 'date': q['date'], 'quarter': q['quarter'], 'gap': q['gap'],
                         'side': q['side'], 'agree': q['agree'], 'surprise': q['surprise'],
                         'r': r, 'before': before, 'week': '%d-W%02d' % (iso[0], iso[1])})
    return rows, counts


def signed(rows):
    """The sided rows with y = side x (r - the mean r of every row given)."""
    if not rows:
        return []
    mean = st.mean(r['r'] for r in rows)
    pre = [r['before'] for r in rows if r['before'] is not None]
    mean_pre = st.mean(pre) if pre else 0.0
    out = []
    for r in rows:
        if r['side']:
            s = 1 if r['side'] == 'LONG' else -1
            out.append({**r, 'dev': r['r'] - mean, 'y': s * (r['r'] - mean),
                        'y_before': None if r['before'] is None else s * (r['before'] - mean_pre)})
    return out


def run(fetch, twins):
    rows, counts = events(fetch, twins)
    good = [r for r in rows if r['agree']]
    sided = signed(good)
    everything = signed(rows)
    out = {'registration': REGISTRATION, 'names': len(NAMES), 'counts': {
               **counts, 'priced': len(rows), 'priced_and_agree': len(good), 'sided': len(sided),
               'long': sum(1 for r in sided if r['side'] == 'LONG'),
               'short': sum(1 for r in sided if r['side'] == 'SHORT'),
               'from': min((r['date'] for r in good), default=None),
               'to': max((r['date'] for r in good), default=None)},
           'reaction_sd_pct': round(st.pstdev([r['r'] for r in good]), 3) if len(good) > 1 else None,
           'verdict': bar(sided),
           'information': hit_rate(sided),
           'descriptive': {
               'all_quarters_uncorroborated_consensus': {**bar(everything), 'information': hit_rate(everything)},
               'long': describe([r for r in sided if r['side'] == 'LONG']),
               'short': describe([r for r in sided if r['side'] == 'SHORT']),
               'gap_10pct_or_more': describe([r for r in sided if abs(r['gap']) >= 0.10]),
               'gap_under_10pct': describe([r for r in sided if abs(r['gap']) < 0.10]),
               '2012_2021': describe([r for r in sided if r['date'] < '2022-01-01']),
               '2022_2026': describe([r for r in sided if r['date'] >= '2022-01-01']),
               'twenty_sessions_before_entry': describe(sided, 'y_before'),
               'sided_by_surprise_instead': describe(
                   [{**r, 'y': (1 if r['surprise'] > 0 else -1) * r['dev']} for r in sided if r['surprise'] != 0])},
           'failures': dict(getattr(fetch, 'failures', {}))}
    return out


def main():
    import us_preopen
    fetch = Cache(ROOT/'.rb-state'/'nowcast_cache')
    out = run(fetch, us_preopen.load_twins())
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    v = out['verdict']
    print(json.dumps({'verdict': v.get('verdict'), 'n': v.get('n'), 'mean_pct': v.get('mean_pct'), 't': v.get('t'),
                      'placebo_p': v.get('placebo_p'), 'control_t': v.get('control_t_planted_1pct'),
                      'mde_pct': v.get('mde_pct'), 'information': out['information'],
                      'counts': out['counts'], 'failures': out['failures']}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
