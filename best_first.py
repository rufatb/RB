"""Day-145 (council lab item 5, PREREGISTER_day145_best_first.md): does a
model's first-named nomination beat its second-named, per model and side?

Every model names two longs and two shorts for the council, best first
(day-129). Day-144's Top 2 takes Claude's first-named long and short on the
assumption that the first is its best. This reads the record only:
`data/model_picks.csv` (kind `nominated`) for the scored results, and the
frozen reports (`.rb-state/reports.sqlite3`), else the evening reviews
(`data/reviews/DATE.json`), for the order. No API call of any kind.

    python best_first.py --out data/best_first_day145.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVIEWS = ROOT / 'data' / 'reviews'
DB = ROOT / '.rb-state' / 'reports.sqlite3'
MODELS = ('claude', 'deepseek', 'gemini')
SIDES = ('LONG', 'SHORT')
FIRST, LAST = '2026-10-14', '2026-11-03'     # the registered window; it does not move
SECTION = 'Nominated (forced)'
SEED = 145
DRAWS = 10000
PLANT = 1.0                                   # % added to every first-named pick
BAR_T = 3.0
BAR_P = 0.01


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _cost():
    import primary_board
    return primary_board.COST_PER_PICK_PCT


def frozen_orders(db=DB):
    """{(session, model, side): [ticker, ticker]} from the frozen reports,
    best first, for every session the database holds."""
    out = {}
    if not db or not Path(db).exists():
        return out
    con = sqlite3.connect(str(db))
    try:
        for session, body in con.execute('select session, body from reports'):
            noms = ((json.loads(body).get('intraday') or {}).get('council') or {}).get('nomination_picks') or {}
            for model in MODELS:
                got = noms.get(model) or {}
                for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
                    tickers = [p.get('ticker') for p in got.get(key) or [] if isinstance(p, dict)]
                    if tickers:
                        out[(session, model, side)] = tickers
    finally:
        con.close()
    return out


def review_order(session, model, side, reviews=REVIEWS):
    """The nominations that evening's review scored, in the nomination order.
    The review keeps only scored names, so a side is fully ordered only when
    both of its names are here."""
    f = Path(reviews) / ('%s.json' % session)
    if not f.exists():
        return []
    return [r.get('ticker') for r in json.loads(f.read_text()).get('rows') or []
            if r.get('section') == SECTION and r.get('model') == model and r.get('side') == side]


def pairs(rows, *, db=DB, reviews=REVIEWS, first=FIRST, last=LAST):
    """([pair …], left_out, agreement). A pair is one (session, model, side)
    with both nominations scored and their order known; d is the first-named
    pick's result minus the second-named's."""
    noms = {}
    for r in rows:
        if r.get('kind') != 'nominated' or r.get('model') not in MODELS or r.get('side') not in SIDES:
            continue
        if not (first <= (r.get('session') or '') <= last):
            continue
        key = (r['session'], r['model'], r['side'])
        noms.setdefault(key, {})[r['ticker']] = (_num(r.get('r_pct')), _num(r.get('confidence')))
    frozen = frozen_orders(db)
    out, left = [], {'not two recorded': 0, 'not scored': 0, 'order unknown': 0}
    agreement = {'both sources': 0, 'agree': 0}
    for key in sorted(noms):
        have = noms[key]
        if len(have) != 2:
            left['not two recorded'] += 1
            continue
        if any(y is None for y, _ in have.values()):
            left['not scored'] += 1
            continue
        session, model, side = key
        from_db = frozen.get(key)
        from_review = review_order(session, model, side, reviews)
        if from_db and len(from_review) == 2:
            agreement['both sources'] += 1
            agreement['agree'] += from_db == from_review
        if from_db and set(from_db) == set(have) and len(from_db) == 2:
            order, source = from_db, 'frozen'
        elif set(from_review) == set(have) and len(from_review) == 2:
            order, source = from_review, 'review'
        else:
            left['order unknown'] += 1
            continue
        (y1, c1), (y2, c2) = have[order[0]], have[order[1]]
        out.append({'session': session, 'model': model, 'side': side, 'first': order[0],
                    'second': order[1], 'y1': y1, 'y2': y2, 'c1': c1, 'c2': c2,
                    'd': y1 - y2, 'source': source})
    return out, left, agreement


def session_means(prs, key='d'):
    """[(session, mean of the session's pairs)] in session order."""
    by = {}
    for p in prs:
        by.setdefault(p['session'], []).append(p[key])
    return [(s, st.mean(v)) for s, v in sorted(by.items())]


def t_stat(ds):
    """Day-144's paired t over session means (`claude_leads._t`)."""
    if len(ds) < 3 or not st.stdev(ds):
        return None
    return st.mean(ds) / (st.stdev(ds) / math.sqrt(len(ds)))


def placebo(ds, *, tail='upper', draws=DRAWS, seed=SEED):
    """One-sided sign-flip p: each session's D flipped as a unit. 'upper' is
    the share of draws with t at or above the real one; 'lower' at or below."""
    t0 = t_stat(ds)
    if t0 is None:
        return None
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        t = t_stat([d if rng.random() < 0.5 else -d for d in ds])
        if t is None:
            continue
        if (t >= t0) if tail == 'upper' else (t <= t0):
            hits += 1
    return (1 + hits) / (1 + draws)


def control(prs):
    """House rule 10: every d centred on zero, then PLANT added to every
    first-named pick, and the same t taken over session means."""
    mean_d = st.mean(p['d'] for p in prs)
    planted = [dict(p, d=p['d'] - mean_d + PLANT) for p in prs]
    ds = [d for _, d in session_means(planted)]
    t = t_stat(ds)
    return {'planted_pct': PLANT, 't': None if t is None else round(t, 2),
            'detected': t is not None and t >= BAR_T}


def verdict(prs, *, draws=DRAWS, seed=SEED):
    """The registered decision over the session means of d."""
    days = session_means(prs)
    ds = [d for _, d in days]
    n = len(ds)
    t = t_stat(ds)
    half = n // 2
    halves = [st.mean(ds[:half]), st.mean(ds[half:])] if half else []
    p_up = placebo(ds, tail='upper', draws=draws, seed=seed)
    p_down = placebo(ds, tail='lower', draws=draws, seed=seed)
    ctl = control(prs) if prs else {'detected': False, 't': None, 'planted_pct': PLANT}
    sd = st.stdev(ds) if n > 1 else None
    first_better = (t is not None and st.mean(ds) > 0 and t >= BAR_T and p_up is not None
                    and p_up < BAR_P and halves and all(h > 0 for h in halves))
    second_better = (t is not None and t <= -BAR_T and p_down is not None and p_down < BAR_P
                     and halves and all(h < 0 for h in halves))
    status = ('FIRST_BETTER' if first_better else 'SECOND_BETTER' if second_better else
              'UNDERPOWERED' if not ctl['detected'] else 'NULL')
    return {'status': status, 'sessions': n, 'pairs': len(prs),
            'mean_d': round(st.mean(ds), 3) if ds else None,
            't': None if t is None else round(t, 2),
            'placebo_p_upper': None if p_up is None else round(p_up, 4),
            'placebo_p_lower': None if p_down is None else round(p_down, 4),
            'halves': [round(h, 3) for h in halves],
            'control': ctl,
            # the difference t = 3 can see with 80% power, at this spread
            'mde': round((BAR_T + 0.84) * sd / math.sqrt(n), 3) if sd else None,
            'by_session': [{'session': s, 'd': round(d, 3)} for s, d in days]}


def _arm(ys):
    ys = [y for y in ys if y is not None]
    if not ys:
        return {'picks': 0}
    return {'picks': len(ys), 'right': sum(y > 0 for y in ys), 'gross': round(st.mean(ys), 3),
            'net': round(st.mean(ys) - _cost(), 3)}


def _split(prs):
    ds = [d for _, d in session_means(prs)]
    t = t_stat(ds)
    return {'pairs': len(prs), 'sessions': len(ds), 'mean_d': round(st.mean(ds), 3) if ds else None,
            't': None if t is None else round(t, 2)}


def describe(prs):
    """Beside the verdict, never part of it."""
    out = {'by_model': {m: _split([p for p in prs if p['model'] == m]) for m in MODELS},
           'by_side': {s: _split([p for p in prs if p['side'] == s]) for s in SIDES},
           'first_named': _arm([p['y1'] for p in prs]),
           'second_named': _arm([p['y2'] for p in prs]),
           'arms_by_model': {m: {'first_named': _arm([p['y1'] for p in prs if p['model'] == m]),
                                 'second_named': _arm([p['y2'] for p in prs if p['model'] == m])}
                             for m in MODELS}}
    # The live rule's arm: Claude's first-named long and short against its
    # second-named pair, per session, net (the cost cancels in the difference).
    out['live_rule_claude'] = _split([p for p in prs if p['model'] == 'claude'])
    gaps = [p for p in prs if p['c1'] is not None and p['c2'] is not None]
    if gaps:
        med = st.median(p['c1'] - p['c2'] for p in gaps)
        wide = [p for p in gaps if p['c1'] - p['c2'] > med]
        narrow = [p for p in gaps if p['c1'] - p['c2'] <= med]
        out['confidence_gap'] = {
            'median_gap': round(med, 3),
            'first_higher': sum(p['c1'] > p['c2'] for p in gaps),
            'equal': sum(p['c1'] == p['c2'] for p in gaps),
            'first_lower': sum(p['c1'] < p['c2'] for p in gaps),
            'wide_gap': {'pairs': len(wide), 'mean_d': round(st.mean(p['d'] for p in wide), 3) if wide else None},
            'narrow_gap': {'pairs': len(narrow),
                           'mean_d': round(st.mean(p['d'] for p in narrow), 3) if narrow else None}}
    return out


def run(rows=None, *, db=DB, reviews=REVIEWS, draws=DRAWS, seed=SEED):
    import model_picks as M
    rows = M.read() if rows is None else rows
    prs, left, agreement = pairs(rows, db=db, reviews=reviews)
    return {'registration': 'PREREGISTER_day145_best_first.md', 'window': [FIRST, LAST],
            'seed': seed, 'draws': draws, 'cost_pct': _cost(),
            'verdict': verdict(prs, draws=draws, seed=seed) if prs else {'status': 'NO_DATA'},
            'order_source': {s: sum(p['source'] == s for p in prs) for s in ('frozen', 'review')},
            'sources_agree': agreement, 'left_out': left,
            'describe': describe(prs) if prs else {},
            'pairs': prs}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--out', help='write the summary here')
    p.add_argument('--db', default=str(DB))
    a = p.parse_args(argv)
    got = run(db=a.db)
    text = json.dumps(got, indent=1, sort_keys=False)
    if a.out:
        Path(a.out).write_text(text + '\n')
    shown = {k: v for k, v in got.items() if k != 'pairs'}
    print(json.dumps(shown, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
