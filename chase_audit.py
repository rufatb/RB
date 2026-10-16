#!/usr/bin/env python3
"""Day-135d, descriptive: where does the habit of following the last session's
big move enter? Desks, nominations, the council's table, its consensus and the
Top 2, against the base rate of the list, on the live record from 2026-10-05.

A pick FOLLOWS (chases) when its name moved >= 1 ATR in the last session and
the pick takes that direction; it FADES when it takes the other one. The base
rate is what a random name and side would give: half the list's big movers.
Moves come from FMP daily bars, exactly as daily_technicals.context computes
move_atr. No verdict: a handful of sessions, printed so the owner can see it.

    python chase_audit.py        # writes data/chase_audit_day135d.json
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import replay_weeks as W
from replay_chasing import move_atr, reduce_eod
from replay_drift import Fetch

ROOT = Path(__file__).resolve().parent
PICKS = ROOT/'data'/'model_picks.csv'
OUT = ROOT/'data'/'chase_audit_day135d.json'
CACHE = ROOT/'.rb-state'/'chase_audit_cache'
FROM, TO = '2026-10-05', '2026-10-16'
EOD_FROM = '2026-07-15'
MOVER = 1.0
STAGES = (('desk selections', lambda r: r['kind'] == 'selected'),
          ('nominations (forced, from 10-14)', lambda r: r['kind'] == 'nominated'),
          ('Jev forced', lambda r: r['kind'] == 'forced'),
          ('the council Top 2', lambda r: r['model'] == 'top2' and r['kind'] == 'pick'),
          ('the counted rule (shadow)', lambda r: r['model'] == 'top2count'),
          ('the memory council (shadow)', lambda r: r['model'] == 'top2memory'))


def prior_move(eod, session):
    before = [i for i, r in enumerate(eod) if r[0] < session]
    return move_atr(eod, before[-1]) if before else None


def kind_of(side, m):
    if m is None:
        return 'unknown'
    if abs(m) < MOVER:
        return 'calm'
    return 'follows' if (m > 0) == (side == 'LONG') else 'fades'


def audit(fetch, rows, universe, council=None):
    tickers = sorted({r['ticker'] for r in rows} | set(universe))
    eod = {t: reduce_eod(fetch('historical-price-eod/full', symbol=t, **{'from': EOD_FROM, 'to': TO}))
           for t in tickers}
    sessions = sorted({r['session'] for r in rows})
    base = {}
    for s in sessions:
        ms = [prior_move(eod[t], s) for t in universe]
        ms = [m for m in ms if m is not None]
        base[s] = {'names': len(ms), 'movers': sum(abs(m) >= MOVER for m in ms)}
    out = {'sessions': sessions,
           'base': {s: {**b, 'share_moving': round(b['movers'] / b['names'], 3) if b['names'] else None}
                    for s, b in base.items()}}
    stages = {}
    for label, keep in STAGES:
        group = [r for r in rows if keep(r)]
        picks = []
        for r in group:
            m = prior_move(eod.get(r['ticker']) or [], r['session'])
            picks.append({'session': r['session'], 'model': r['model'], 'side': r['side'],
                          'ticker': r['ticker'], 'move_atr': None if m is None else round(m, 2),
                          'kind': kind_of(r['side'], m),
                          'r_pct': float(r['r_pct']) if (r.get('r_pct') or '').strip() else None})
        known = [p for p in picks if p['kind'] != 'unknown']
        ss = sorted({p['session'] for p in known})
        movers = sum(base[s]['movers'] for s in ss for p in known if p['session'] == s)
        names = sum(base[s]['names'] for s in ss for p in known if p['session'] == s)
        b = movers / (2 * names) if names else None          # a random name and side
        n = len(known)
        stages[label] = {
            'picks': len(picks), 'known': n,
            'follows': sum(p['kind'] == 'follows' for p in known),
            'fades': sum(p['kind'] == 'fades' for p in known),
            'calm': sum(p['kind'] == 'calm' for p in known),
            'follow_share': round(sum(p['kind'] == 'follows' for p in known) / n, 3) if n else None,
            'base_follow_share': round(b, 3) if b else None,
            'times_chance': round((sum(p['kind'] == 'follows' for p in known) / n) / b, 1) if n and b else None,
            'scored': {k: _rate([p['r_pct'] for p in known if p['kind'] == k and p['r_pct'] is not None])
                       for k in ('follows', 'fades', 'calm')},
            'rows': picks}
    out['stages'] = stages
    top = [p for p in stages['the council Top 2']['rows']]
    by = {}
    for p in top:
        by.setdefault(p['session'], []).append(p)
    out['top2_sessions'] = {s: {'picks': ['%s %s (%s, %s)' % (p['side'], p['ticker'], p['move_atr'], p['kind'])
                                          for p in v],
                                'same_side': len(v) == 2 and v[0]['side'] == v[1]['side']}
                            for s, v in sorted(by.items())}
    if council:
        out['council_table_today'] = table(council, eod)
    return out


def table(council, eod):
    """Today's council: the share of its table, its consensus and its picks
    that follow a big move."""
    session = council['session']
    rows = {r['id']: r for r in (council.get('tally') or {}).get('rows') or []}
    out = []
    for p in council.get('positions') or []:
        m = prior_move(eod.get(p['ticker']) or [], session)
        r = rows.get(p['id']) or {}
        out.append({'id': p['id'], 'side': p['side'], 'ticker': p['ticker'],
                    'move_atr': None if m is None else round(m, 2), 'kind': kind_of(p['side'], m),
                    'endorse': len(r.get('endorse') or []), 'oppose': len(r.get('oppose') or []),
                    'consensus': bool(r.get('consensus')), 'pick': p['id'] in (council.get('picks') or [])})
    def share(xs):
        return '%d of %d follow' % (sum(x['kind'] == 'follows' for x in xs), len(xs))
    return {'session': session, 'positions': out,
            'table': share(out), 'consensus': share([x for x in out if x['consensus']]),
            'picks': share([x for x in out if x['pick']])}


def _rate(xs):
    if not xs:
        return {'n': 0}
    return {'n': len(xs), 'right': sum(x > 0 for x in xs), 'mean_pct': round(sum(xs) / len(xs), 3)}


def main():
    with open(PICKS, newline='') as f:
        rows = [r for r in csv.DictReader(f) if FROM <= r['session'] <= TO and r['side'] in ('LONG', 'SHORT')]
    universe, _ = W.names()
    fetch = W.robust(Fetch(CACHE))
    council = None
    try:
        council = json.loads((ROOT/'.rb-state'/'council.json').read_text())
    except (OSError, ValueError):
        pass
    out = audit(fetch, rows, universe, council)
    out['fetch_failures'] = fetch.failures
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True))
    brief = {k: v for k, v in out.items() if k not in ('stages',)}
    brief['stages'] = {k: {kk: vv for kk, vv in v.items() if kk != 'rows'} for k, v in out['stages'].items()}
    print(json.dumps(brief, indent=1, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
