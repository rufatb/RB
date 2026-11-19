"""Day-153 (PREREGISTER_day153_noon_exit_live.md): the noon exit on the live record.

Council lab item 15. Every Top 2 section prints day-130's note that leaving at
12:00 ET "was no worse than holding to the close and swung 15% less"; that came
from the day-117 replay (H3) and was never checked on the live picks. This reads
the committed execution lab only (`data/reviews/execution_lab.csv`): no network,
no model, no cost. One look.

The population (pinned at registration):
* the pooled card's kinds present in the lab (`selected`, `forced`, `pick`,
  `final`) from the live sources; the engine, every shadow and late picks are
  left out (`model_picks.POOLED_EXCLUDED` plus `engine`);
* sessions through 2026-11-17 (rows the evening job adds later are not read);
* each (session, ticker, side) once, the first row in file order, as the
  pooled card does: 179 positions over 37 sessions at registration.

The measures, both from the 09:45 entry and signed to the pick (the lab's own):
* d = r_noon - r per position (the cost of leaving at noon), its mean
  session-clustered (`replay_fmp_analyst.clustered`, day-137's);
* the swing ratio sd(r) / sd(r_noon) over positions (above 1: noon swings less),
  with a session-block bootstrap (2,000 draws, seed 153) for its 5th percentile.

The bar (registered): CONFIRMED needs mean d >= -0.05% with t > -2; the ratio
>= 1.15 with the bootstrap 5th percentile above 1.0; both halves (in session
order, equal numbers of sessions) with a ratio above 1.0 and a mean d >= -0.05%;
and a planted 0.20% cost showing at t >= 3 (0.20 / se, never (mean - 0.20) / se).

Fixed here, before the run, where the registration left a choice open:
* "Equal numbers of sessions" with an odd count: the first n//2 sessions and the
  last n//2; the middle session sits in neither half (it stays in the full test).
* Precedence: CONFIRMED (every leg and the control) > UNDERPOWERED (the control
  short of t = 3) > WORSE (mean d < -0.05% with t <= -2, or the ratio below 1.0)
  > NOT_CONFIRMED. The WORSE condition is also printed as its own flag, so an
  UNDERPOWERED verdict cannot hide it. Anything but CONFIRMED is rejection #68.
"""
import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

from replay_fmp_analyst import clustered

LAB = Path('data/reviews/execution_lab.csv')
OUT = Path('data/noon_exit_live_day153.json')
CUT = '2026-11-17'
KINDS = ('selected', 'forced', 'pick', 'final')
EXCLUDED = ('engine', 'top2count', 'top2memory', 'top2runner', 'top2mover', 'top2wild',
            'top2council', 'top2run', 'top2floor')
MEAN_FLOOR = -0.05        # day-130 H3's own bar, % a position
T_FLOOR = -2.0
RATIO_BAR = 1.15          # day-135c's bar for a size rule
PLANTED = 0.20            # % a position
DRAWS = 2000
SEED = 153
OTHER_EXITS = (('r_stop_wrongif', "the pick's own wrong-if stop"),
               ('r_stop_half_atr', 'a 0.5 ATR stop'),
               ('r_stop_1atr', 'a 1 ATR stop'),
               ('r_vs_etf', 'hedged with its sector fund'))


def _f(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def positions(rows, *, cut=CUT):
    """The registered population: each (session, ticker, side) once, first row
    in file order, with both windows present. Returns (positions, counts)."""
    seen, kept_rows, missing = {}, 0, 0
    for r in rows:
        if (r.get('session', '') > cut or r.get('kind') not in KINDS
                or r.get('model') in EXCLUDED):
            continue
        r0, rn = _f(r.get('r')), _f(r.get('r_noon'))
        if r0 is None or rn is None:
            missing += 1
            continue
        kept_rows += 1
        key = (r['session'], r['ticker'], r['side'])
        if key not in seen:
            seen[key] = {'session': r['session'], 'ticker': r['ticker'], 'side': r['side'],
                         'models': [], 'r': r0, 'r_noon': rn, 'd': rn - r0,
                         **{k: _f(r.get(k)) for k, _ in OTHER_EXITS}}
        seen[key]['models'].append(r['model'])
    out = sorted(seen.values(), key=lambda p: (p['session'], p['ticker'], p['side']))
    return out, {'rows': kept_rows, 'rows_missing_a_window': missing, 'positions': len(out),
                 'sessions': len({p['session'] for p in out})}


def sd(values):
    return statistics.stdev(values) if len(values) > 1 else None


def ratio(ps):
    a, b = sd([p['r'] for p in ps]), sd([p['r_noon'] for p in ps])
    return a / b if a is not None and b else None


def mean_d(ps, key='d'):
    pairs = [(p['session'], p[key]) for p in ps if p.get(key) is not None]
    m, se, t = clustered(pairs)
    return {'n': len(pairs), 'sessions': len({s for s, _ in pairs}),
            'mean_pct': None if m is None else round(m, 4),
            'se': None if se is None else round(se, 4),
            't': None if t is None else round(t, 2)}


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


def summary(ps):
    m = mean_d(ps)
    x = ratio(ps)
    return {**m, 'ratio': None if x is None else round(x, 4)}


def verdict(ps, *, draws=DRAWS, seed=SEED):
    full = summary(ps)
    boot = bootstrap(ps, draws=draws, seed=seed)
    p5 = percentile(boot, 0.05)
    a, b, middle = halves(ps)
    ha, hb = summary(a), summary(b)
    se = full['se']
    t_planted = PLANTED / se if se else None
    mde = 2.8 * se if se else None
    legs = {
        'mean': full['mean_pct'] is not None and full['mean_pct'] >= MEAN_FLOOR
                and full['t'] is not None and full['t'] > T_FLOOR,
        'swing': full['ratio'] is not None and full['ratio'] >= RATIO_BAR
                 and p5 is not None and p5 > 1.0,
        'halves': all(h['ratio'] is not None and h['ratio'] > 1.0 and h['mean_pct'] is not None
                      and h['mean_pct'] >= MEAN_FLOOR for h in (ha, hb)),
        'control': t_planted is not None and t_planted >= 3,
    }
    worse = bool((full['mean_pct'] is not None and full['t'] is not None
                  and full['mean_pct'] < MEAN_FLOOR and full['t'] <= T_FLOOR)
                 or (full['ratio'] is not None and full['ratio'] < 1.0))
    if all(legs.values()):
        label = 'CONFIRMED'
    elif not legs['control']:
        label = 'UNDERPOWERED'
    elif worse:
        label = 'WORSE'
    else:
        label = 'NOT_CONFIRMED'
    return {'verdict': label, 'legs': legs, 'worse': worse, 'full': full,
            'bootstrap': {'draws': len(boot), 'seed': seed,
                          'p5': None if p5 is None else round(p5, 4),
                          'p50': None if not boot else round(percentile(boot, 0.5), 4),
                          'p95': None if not boot else round(percentile(boot, 0.95), 4)},
            'halves': {'first': ha, 'second': hb, 'middle_session_out': middle},
            'control': {'planted_pct': PLANTED,
                        't_planted': None if t_planted is None else round(t_planted, 2),
                        'mde_pct': None if mde is None else round(mde, 4)}}


def describe(ps):
    """Beside the verdict, never a verdict."""
    out = {}
    top2 = [p for p in ps if 'top2' in p['models']]
    out['top2'] = summary(top2)
    for side in ('LONG', 'SHORT'):
        out[side.lower()] = summary([p for p in ps if p['side'] == side])
    aft = [{**p, 'aft': p['r'] - p['r_noon']} for p in ps]
    out['afternoon'] = mean_d(aft, key='aft')
    out['noon_better_share'] = round(sum(p['d'] > 0 for p in ps) / len(ps), 3) if ps else None
    out['hold_to_close'] = {'mean_pct': round(statistics.fmean([p['r'] for p in ps]), 4) if ps else None,
                            'sd': None if sd([p['r'] for p in ps]) is None else round(sd([p['r'] for p in ps]), 4)}
    out['exit_at_noon'] = {'mean_pct': round(statistics.fmean([p['r_noon'] for p in ps]), 4) if ps else None,
                           'sd': None if sd([p['r_noon'] for p in ps]) is None else round(sd([p['r_noon'] for p in ps]), 4)}
    others = {}
    for key, label in OTHER_EXITS:
        sub = [p for p in ps if p.get(key) is not None]
        diff = [{**p, 'x': p[key] - p['r']} for p in sub]
        s_close, s_exit = sd([p['r'] for p in sub]), sd([p[key] for p in sub])
        others[key] = {'label': label, **mean_d(diff, key='x'),
                       'ratio': None if not (s_close and s_exit) else round(s_close / s_exit, 4)}
    out['other_exits_minus_close'] = others
    months = defaultdict(list)
    for p in ps:
        months[p['session'][:7]].append(p)
    out['by_month'] = {m: summary(v) for m, v in sorted(months.items())}
    return out


def run(lab=LAB, *, cut=CUT, draws=DRAWS, seed=SEED):
    with open(lab, newline='') as fh:
        rows = list(csv.DictReader(fh))
    ps, counts = positions(rows, cut=cut)
    return {'registration': 'PREREGISTER_day153_noon_exit_live.md', 'lab': str(lab), 'cut': cut,
            'population': counts, **verdict(ps, draws=draws, seed=seed), 'describe': describe(ps)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--lab', default=str(LAB))
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args(argv)
    result = run(Path(args.lab))
    Path(args.out).write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({k: result[k] for k in ('population', 'verdict', 'legs', 'worse', 'full',
                                             'bootstrap', 'halves', 'control')}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
