#!/usr/bin/env python3
"""Day-148 — a council veto: do the positions two members object to do worse?

Council lab item 11, registered in `PREREGISTER_day148_veto.md` before any
two-objection split was computed. This script reads the pinned tallies
(`data/veto_day148_positions.json`, no returns in it) and FMP five-minute bars,
and gets ONE look. No model call, no OpenRouter.

    y = side × (the position's return − XIU.TO's), in %, from the close of the
        09:40 bar (the 09:45 price) to the close of the 15:55 bar
    D = per session, mean y of the rest − mean y of the vetoed (≥ 2 objections)

VETO_SORTS needs: mean D > 0 with t ≥ 3 over the session means, a sign-flip
placebo p < 0.01 (seed 148), both halves positive, and the vetoed positions'
own mean of session means below zero after the 0.13% round trip.
OBJECTIONS_BACKWARDS is the mirror. A planted 1.0% on centred D must show at
t ≥ 3, else UNDERPOWERED. Anything but VETO_SORTS is rejection #64.

    python council_veto.py --run          the registered look; writes data/veto_day148.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIN = ROOT / 'data' / 'veto_day148_positions.json'
SUMMARY = ROOT / 'data' / 'veto_day148.json'
CACHE = ROOT / '.rb-state' / 'veto_day148_cache'
BENCH = 'XIU.TO'
ENTRY, EXIT = '09:40:00', '15:55:00'
VETO_AT = 2
SEED = 148
DRAWS = 10000
PLANT = 1.0
BAR_T = 3.0
BAR_P = 0.01
COST = 0.13


def _fetch(symbol, session, *, cache=CACHE, get=None):
    """FMP five-minute bars for one session, cached by (symbol, session)."""
    cache = Path(cache)
    f = cache / ('%s_%s.json' % (symbol.replace('/', '_'), session))
    if f.exists():
        return json.loads(f.read_text())
    if get is None:
        import fmp_client
        get = fmp_client.get
    rows = get('historical-chart/5min', symbol=symbol, **{'from': session, 'to': session}) or []
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows))
    return rows


def window(bars, session):
    """(entry, exit) — the 09:40 and 15:55 bars' closes — or None."""
    at = {b['date'].split(' ')[1]: b for b in bars or [] if str(b.get('date', '')).startswith(session)}
    if ENTRY not in at or EXIT not in at:
        return None
    a, b = at[ENTRY].get('close'), at[EXIT].get('close')
    if not a or not b:
        return None
    return float(a), float(b)


def pct(a, b):
    return 100.0 * (b / a - 1.0)


def score(positions, fetch=_fetch):
    """Each position with y, or left out and counted."""
    bench, out, missing = {}, [], []
    for p in positions:
        s = p['session']
        if s not in bench:
            w = window(fetch(BENCH, s), s)
            bench[s] = pct(*w) if w else None
        w = window(fetch(p['ticker'], s), s)
        if w is None or bench[s] is None:
            missing.append({'session': s, 'ticker': p['ticker'], 'side': p['side'],
                            'why': 'no bars' if w is None else 'no XIU bars'})
            continue
        sign = 1.0 if p['side'] == 'LONG' else -1.0
        out.append({**p, 'raw': sign * pct(*w), 'y': sign * (pct(*w) - bench[s]),
                    'vetoed': int(p['oppose']) >= VETO_AT})
    return out, missing


def t_stat(ds):
    if len(ds) < 3 or not st.stdev(ds):
        return None
    return st.mean(ds) / (st.stdev(ds) / math.sqrt(len(ds)))


def placebo(ds, *, tail='upper', draws=DRAWS, seed=SEED):
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


def session_d(rows, split=lambda r: r['vetoed'], key='y'):
    """[(session, D = rest − flagged, flagged mean, rest mean)] for sessions with both groups."""
    by = {}
    for r in rows:
        by.setdefault(r['session'], ([], []))[1 if split(r) else 0].append(r[key])
    out = []
    for s, (rest, flagged) in sorted(by.items()):
        if rest and flagged:
            out.append((s, st.mean(rest) - st.mean(flagged), st.mean(flagged), st.mean(rest)))
    return out


def control(ds):
    """House rule 10: D centred on zero, then PLANT added; same t."""
    if not ds:
        return {'planted_pct': PLANT, 't': None, 'detected': False}
    m = st.mean(ds)
    t = t_stat([d - m + PLANT for d in ds])
    return {'planted_pct': PLANT, 't': None if t is None else round(t, 2),
            'detected': t is not None and t >= BAR_T}


def verdict(rows, *, draws=DRAWS, seed=SEED):
    days = session_d(rows)
    ds = [d for _, d, _, _ in days]
    n = len(ds)
    t = t_stat(ds)
    half = n // 2
    halves = [st.mean(ds[:half]), st.mean(ds[half:])] if half else []
    p_up = placebo(ds, tail='upper', draws=draws, seed=seed)
    p_down = placebo(ds, tail='lower', draws=draws, seed=seed)
    vetoed_mean = st.mean(f for _, _, f, _ in days) if days else None
    ctl = control(ds)
    sd = st.stdev(ds) if n > 1 else None
    sorts = (t is not None and st.mean(ds) > 0 and t >= BAR_T and p_up is not None and p_up < BAR_P
             and halves and all(h > 0 for h in halves)
             and vetoed_mean is not None and vetoed_mean - COST < 0)
    backwards = (t is not None and t <= -BAR_T and p_down is not None and p_down < BAR_P
                 and halves and all(h < 0 for h in halves))
    status = ('VETO_SORTS' if sorts else 'OBJECTIONS_BACKWARDS' if backwards else
              'UNDERPOWERED' if not ctl['detected'] else 'NULL')
    return {'status': status, 'sessions': n,
            'positions': len(rows), 'vetoed': sum(r['vetoed'] for r in rows),
            'mean_d': round(st.mean(ds), 3) if ds else None,
            't': None if t is None else round(t, 2),
            'placebo_p_upper': None if p_up is None else round(p_up, 4),
            'placebo_p_lower': None if p_down is None else round(p_down, 4),
            'halves': [round(h, 3) for h in halves],
            'vetoed_mean_of_sessions': None if vetoed_mean is None else round(vetoed_mean, 3),
            'vetoed_net': None if vetoed_mean is None else round(vetoed_mean - COST, 3),
            'control': ctl,
            'mde': round((BAR_T + 0.84) * sd / math.sqrt(n), 3) if sd else None,
            'by_session': [{'session': s, 'd': round(d, 3), 'vetoed': round(f, 3), 'rest': round(r, 3)}
                           for s, d, f, r in days]}


def _split(rows, split, key='y'):
    days = session_d(rows, split, key)
    ds = [d for _, d, _, _ in days]
    t = t_stat(ds)
    flagged = [r for r in rows if split(r)]
    return {'sessions': len(ds), 'flagged': len(flagged), 'rest': len(rows) - len(flagged),
            'mean_d_rest_minus_flagged': round(st.mean(ds), 3) if ds else None,
            't': None if t is None else round(t, 2),
            'flagged_mean': round(st.mean(r[key] for r in flagged), 3) if flagged else None,
            'flagged_right': sum(r[key] > 0 for r in flagged)}


def describe(rows):
    """Beside the verdict, never part of it."""
    out = {
        'one_objection_or_more': _split(rows, lambda r: int(r['oppose']) >= 1),
        'every_member_endorsed': _split(rows, lambda r: int(r['endorse']) >= int(r['members'] or 0) > 0),
        'raw_not_against_xiu': _split(rows, lambda r: r['vetoed'], key='raw'),
    }
    for side in ('LONG', 'SHORT'):
        out['side_' + side] = _split([r for r in rows if r['side'] == side], lambda r: r['vetoed'])
    for src in sorted({r.get('source') for r in rows}):
        out['source_' + str(src)] = _split([r for r in rows if r.get('source') == src],
                                           lambda r: r['vetoed'])
    claude = [r for r in rows if r.get('claude')]
    out['claude_proposals'] = {'positions': len(claude), 'vetoed': sum(r['vetoed'] for r in claude),
                               'vetoed_mean': round(st.mean(r['y'] for r in claude if r['vetoed']), 3)
                               if any(r['vetoed'] for r in claude) else None,
                               'rest_mean': round(st.mean(r['y'] for r in claude if not r['vetoed']), 3)
                               if any(not r['vetoed'] for r in claude) else None}
    top2 = [r for r in rows if r.get('top2')]
    out['printed_top2'] = {'positions': len(top2), 'vetoed': sum(r['vetoed'] for r in top2),
                           'rows': [{'session': r['session'], 'ticker': r['ticker'], 'side': r['side'],
                                     'oppose': r['oppose'], 'y': round(r['y'], 3)} for r in top2]}
    return out


def run(pin=PIN, fetch=_fetch, *, draws=DRAWS, seed=SEED):
    data = json.loads(Path(pin).read_text())
    positions = data['positions']
    rows, missing = score(positions, fetch)
    return {'registration': 'PREREGISTER_day148_veto.md', 'pin': str(Path(pin).name),
            'population': len(positions), 'scored': len(rows), 'missing': missing,
            'verdict': verdict(rows, draws=draws, seed=seed), 'describe': describe(rows),
            'measure': 'side x (09:45 -> 15:55 close, less XIU.TO), FMP five-minute bars'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--run', action='store_true', help='the registered look')
    p.add_argument('--out', default=str(SUMMARY))
    a = p.parse_args(argv)
    if not a.run:
        p.print_help()
        return 2
    out = run()
    Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: out[k] for k in ('population', 'scored')} | {'missing': len(out['missing'])}
                     | {'verdict': {k: v for k, v in out['verdict'].items() if k != 'by_session'}}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
