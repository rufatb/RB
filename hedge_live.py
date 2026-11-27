"""Day-156 (PREREGISTER_day156_hedge_live.md): the sector-fund hedge on the live record.

Council lab item 18. Under every one-sided Top 2 the hedge line
(`top_picks.hedge_line`, day-148c) prints the live running record
(`execution_lab.hedge_record`: "the hedged pick made 0.23% a pick more than the
unhedged one and swung 21% less", 181 picks on 11-27) beside the replay's
failure (day-130 H2). The live sentence was never tested. This reads the
committed execution lab only, as pinned at registration: no network, no model,
no cost. One look.

The population (pinned at registration):
* `data/reviews/execution_lab.csv` as committed at 150a72c (sha256 begins
  eebb2b8bb207b99d): 624 rows, sessions 2026-09-17 -> 2026-11-26. The run reads
  that blob with `git show` and refuses any other;
* the hedge line's own rows, `execution_lab._model_picks` as committed: every
  source but the engine and the shadows it leaves out, no forced nominations,
  one row per (session, side, ticker), the first in file order (`_unique`);
* of those, the positions with both `r` and `r_vs_etf`: 181 over 44 sessions at
  registration, every one with a `beta`.

The measures, both from the 09:45 entry to the close and signed to the pick:
* d = (r_vs_etf - r) - 0.13% x |beta| per position: the hedge's gain net of
  its own leg, charged at the stock's measured round trip (day-132b); its mean
  session-clustered (`replay_fmp_analyst.clustered`, as day-153);
* the swing ratio sd(r) / sd(r_vs_etf) over positions (above 1: the hedged
  position swings less), with a session-block bootstrap (2,000 draws, seed
  156) for its 5th percentile.

The bar (registered, day-153's): CONFIRMED needs mean d >= -0.05% with t > -2;
the ratio >= 1.15 with the bootstrap 5th percentile above 1.0; both halves (in
session order, equal numbers of sessions) with a ratio above 1.0 and a mean d
>= -0.05%; and a planted 0.20% cost showing at t >= 3 (0.20 / se, never
(mean - 0.20) / se). Anything but CONFIRMED is rejection #73.

Fixed here, before the run, where the registration left a choice open (as
day-153's script fixed them):
* An odd number of sessions: the first n//2 and the last n//2; the middle
  session sits in neither half (it stays in the full test). 44 sessions at
  registration, so 22 and 22.
* Precedence: CONFIRMED (every leg and the control) > UNDERPOWERED (the control
  short of t = 3) > WORSE (mean d < -0.05% with t <= -2, or the ratio below 1.0)
  > NOT_CONFIRMED. WORSE and BETTER (mean d >= +0.05% with t >= 3, reported and
  never a verdict) are also printed as their own flags, so an UNDERPOWERED
  verdict cannot hide either.
* |beta| is charged: a hedge of negative beta is still a position of that size.
* "The share of positions the hedge improved" is the share with d > 0 (net),
  printed beside the share with r_vs_etf > r (gross).
"""
import argparse
import csv
import hashlib
import io
import json
import math
import random
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

from replay_fmp_analyst import clustered

LAB = 'data/reviews/execution_lab.csv'
COMMIT = '150a72c'
SHA256_PREFIX = 'eebb2b8bb207b99d'
OUT = Path('data/hedge_live_day156.json')
CUT = '2026-11-26'
COST = 0.13               # % per unit of hedge notional (day-132b's measured round trip)
MEAN_FLOOR = -0.05        # % a position
T_FLOOR = -2.0
RATIO_BAR = 1.15          # day-135c's bar for a size rule
BETTER_MEAN = 0.05
BETTER_T = 3.0
PLANTED = 0.20            # % a position
DRAWS = 2000
SEED = 156
# The hedge line's exclusions (`execution_lab._model_picks` at registration).
LINE_EXCLUDED = ('engine', 'top2count', 'top2memory', 'top2mover', 'top2wild', 'top2council',
                 'top2run', 'top2floor')
# Day-153's population, beside the verdict: its kinds, and the runner-up left out too.
D153_KINDS = ('selected', 'forced', 'pick', 'final')
D153_EXCLUDED = LINE_EXCLUDED + ('top2runner',)


def _f(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def pinned_rows(commit=COMMIT, path=LAB, sha_prefix=SHA256_PREFIX, show=None):
    """The lab as committed at `commit`, refused unless its sha256 begins with
    the registered prefix."""
    show = show or (lambda spec: subprocess.run(['git', 'show', spec], check=True,
                                                capture_output=True).stdout)
    blob = show(f'{commit}:{path}')
    digest = hashlib.sha256(blob).hexdigest()
    if not digest.startswith(sha_prefix):
        raise SystemExit(f'REFUSED: {path} at {commit} hashes {digest[:16]}, registered {sha_prefix}')
    return list(csv.DictReader(io.StringIO(blob.decode('utf-8')))), digest


def _position(r):
    a, b, beta = _f(r.get('r')), _f(r.get('r_vs_etf')), _f(r.get('beta'))
    if a is None or b is None:
        return None
    return {'session': r['session'], 'ticker': r['ticker'], 'side': r['side'],
            'model': r['model'], 'kind': r['kind'], 'etf': r.get('etf') or '',
            'r': a, 'r_vs_etf': b, 'beta': beta, 'g': b - a,
            'd': None if beta is None else b - a - COST * abs(beta)}


def line_positions(rows, *, cut=CUT):
    """The registered population: the hedge line's own rows (one per session,
    side and ticker, the first in file order, before any window is read), then
    those measured both ways. Returns (positions, counts)."""
    kept = [r for r in rows if r.get('session', '') <= cut and r.get('model') not in LINE_EXCLUDED
            and r.get('kind') != 'nominated']
    unique = {}
    for r in kept:
        unique.setdefault((r['session'], r['side'], r['ticker']), r)
    ps, missing, no_beta = [], 0, 0
    for r in unique.values():
        p = _position(r)
        if p is None:
            missing += 1
            continue
        no_beta += p['d'] is None
        ps.append(p)
    ps.sort(key=lambda p: (p['session'], p['ticker'], p['side']))
    return ps, {'rows_read': len(rows), 'line_rows': len(kept), 'unique': len(unique),
                'unique_missing_a_window': missing, 'positions': len(ps),
                'positions_without_beta': no_beta, 'sessions': len({p['session'] for p in ps})}


def day153_positions(rows, *, cut=CUT):
    """Day-153's rule with the hedge's window: its kinds, the runner-up left
    out, the first row in file order among those measured both ways."""
    seen = {}
    for r in rows:
        if (r.get('session', '') > cut or r.get('kind') not in D153_KINDS
                or r.get('model') in D153_EXCLUDED):
            continue
        p = _position(r)
        if p is not None:
            seen.setdefault((r['session'], r['ticker'], r['side']), p)
    return sorted(seen.values(), key=lambda p: (p['session'], p['ticker'], p['side']))


def sd(values):
    return statistics.stdev(values) if len(values) > 1 else None


def ratio(ps):
    a, b = sd([p['r'] for p in ps]), sd([p['r_vs_etf'] for p in ps])
    return a / b if a is not None and b else None


def mean_of(ps, key='d'):
    pairs = [(p['session'], p[key]) for p in ps if p.get(key) is not None]
    m, se, t = clustered(pairs)
    return {'n': len(pairs), 'sessions': len({s for s, _ in pairs}),
            'mean_pct': None if m is None else round(m, 4),
            'se': None if se is None else round(se, 4),
            't': None if t is None else round(t, 2)}


def summary(ps):
    x = ratio(ps)
    return {**mean_of(ps), 'gross': mean_of(ps, 'g'), 'ratio': None if x is None else round(x, 4)}


def bootstrap(ps, *, draws=DRAWS, seed=SEED):
    """Session-block bootstrap of the swing ratio: resample whole sessions."""
    by = defaultdict(list)
    for p in ps:
        by[p['session']].append(p)
    sessions = sorted(by)
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        sample = [p for s in (rng.choice(sessions) for _ in sessions) for p in by[s]]
        x = ratio(sample)
        if x is not None:
            out.append(x)
    out.sort()
    return out


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def halves(ps):
    """In session order, equal numbers of sessions; an odd middle sits out."""
    sessions = sorted({p['session'] for p in ps})
    h = len(sessions) // 2
    first, second = set(sessions[:h]), set(sessions[len(sessions) - h:])
    return ([p for p in ps if p['session'] in first], [p for p in ps if p['session'] in second],
            sessions[h] if len(sessions) % 2 else None)


def verdict(ps, *, draws=DRAWS, seed=SEED):
    full = summary(ps)
    boot = bootstrap(ps, draws=draws, seed=seed)
    p5 = percentile(boot, 0.05)
    a, b, middle = halves(ps)
    ha, hb = summary(a), summary(b)
    se = full['se']
    t_planted = PLANTED / se if se else None
    mde = 2.8 * se if se else None
    m, t, x = full['mean_pct'], full['t'], full['ratio']
    legs = {
        'mean': m is not None and m >= MEAN_FLOOR and t is not None and t > T_FLOOR,
        'swing': x is not None and x >= RATIO_BAR and p5 is not None and p5 > 1.0,
        'halves': all(h['ratio'] is not None and h['ratio'] > 1.0 and h['mean_pct'] is not None
                      and h['mean_pct'] >= MEAN_FLOOR for h in (ha, hb)),
        'control': t_planted is not None and t_planted >= 3,
    }
    worse = bool((m is not None and t is not None and m < MEAN_FLOOR and t <= T_FLOOR)
                 or (x is not None and x < 1.0))
    better = bool(m is not None and t is not None and m >= BETTER_MEAN and t >= BETTER_T)
    if all(legs.values()):
        label = 'CONFIRMED'
    elif not legs['control']:
        label = 'UNDERPOWERED'
    elif worse:
        label = 'WORSE'
    else:
        label = 'NOT_CONFIRMED'
    return {'verdict': label, 'legs': legs, 'worse': worse, 'better': better, 'full': full,
            'bootstrap': {'draws': len(boot), 'seed': seed,
                          'p5': None if p5 is None else round(p5, 4),
                          'p50': None if not boot else round(percentile(boot, 0.5), 4),
                          'p95': None if not boot else round(percentile(boot, 0.95), 4)},
            'halves': {'first': ha, 'second': hb, 'middle_session_out': middle},
            'control': {'planted_pct': PLANTED,
                        't_planted': None if t_planted is None else round(t_planted, 2),
                        'mde_pct': None if mde is None else round(mde, 4)}}


def one_sided_sessions(rows, *, cut=CUT):
    """Sessions whose Top 2 rows all stand on one side: the hedge line's occasion."""
    sides = defaultdict(set)
    for r in rows:
        if r.get('model') == 'top2' and r.get('session', '') <= cut:
            sides[r['session']].add(r['side'])
    return {s for s, v in sides.items() if len(v) == 1}


def describe(ps, rows, *, cut=CUT):
    """Beside the verdict, never a verdict."""
    out = {'gross': mean_of(ps, 'g')}
    out['day153_population'] = summary(day153_positions(rows, cut=cut))
    top2 = [p for p in ps if p['model'] == 'top2']
    one = one_sided_sessions(rows, cut=cut)
    out['top2'] = summary(top2)
    out['top2_one_sided_mornings'] = summary([p for p in top2 if p['session'] in one])
    for side in ('LONG', 'SHORT'):
        out[side.lower()] = summary([p for p in ps if p['side'] == side])
    out['xiu'] = summary([p for p in ps if p['etf'] == 'XIU.TO'])
    out['sector_fund'] = summary([p for p in ps if p['etf'] and p['etf'] != 'XIU.TO'])
    funds = defaultdict(list)
    for p in ps:
        funds[p['etf'] or '(none)'].append(p)
    out['by_fund'] = {f: summary(v) for f, v in sorted(funds.items())}
    netted = [p for p in ps if p['d'] is not None]
    out['improved_share'] = {
        'net': round(sum(p['d'] > 0 for p in netted) / len(netted), 3) if netted else None,
        'gross': round(sum(p['g'] > 0 for p in ps) / len(ps), 3) if ps else None}
    months = defaultdict(list)
    for p in ps:
        months[p['session'][:7]].append(p)
    out['by_month'] = {m: summary(v) for m, v in sorted(months.items())}
    out['unhedged'] = {'mean_pct': round(statistics.fmean([p['r'] for p in ps]), 4) if ps else None,
                       'sd': None if sd([p['r'] for p in ps]) is None else round(sd([p['r'] for p in ps]), 4)}
    out['hedged'] = {'mean_pct': round(statistics.fmean([p['r_vs_etf'] for p in ps]), 4) if ps else None,
                     'sd': None if sd([p['r_vs_etf'] for p in ps]) is None
                     else round(sd([p['r_vs_etf'] for p in ps]), 4)}
    return out


def run(rows, *, cut=CUT, draws=DRAWS, seed=SEED, digest=None):
    ps, counts = line_positions(rows, cut=cut)
    return {'registration': 'PREREGISTER_day156_hedge_live.md', 'lab': LAB, 'commit': COMMIT,
            'sha256': digest, 'cut': cut, 'cost_pct_per_beta': COST, 'population': counts,
            **verdict(ps, draws=draws, seed=seed), 'describe': describe(ps, rows, cut=cut)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', action='store_true', help='the registered run: one look')
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args(argv)
    if not args.run:
        ap.print_help()
        return 2
    rows, digest = pinned_rows()
    result = run(rows, digest=digest)
    Path(args.out).write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('population', 'verdict', 'legs', 'worse', 'better',
                                             'full', 'bootstrap', 'halves', 'control')}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
