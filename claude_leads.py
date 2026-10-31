"""Day-144 (owner, 2026-10-30): the Top 2 led by Claude's picks, against the
council's own choice, on the record. PREREGISTER_day144_claude_leads.md.

The owner: "Claude picks are doing much better than council. I want council to
be led by Claude picks." From 2026-11-02 the Top 2 is Claude's first-named long
and first-named short from its council nominations (`council.CLAUDE_LEADS`),
recorded as `top2/pick` with `council.CLAUDE_RULE`. The council's own decision
is recorded beside it as the shadow `top2council/pick`. This module compares
the two on the record's yardstick (09:45 → close), net of the measured round
trip. It decides nothing: the owner does.

    python claude_leads.py                      # the running readout
    python claude_leads.py --verdict            # the registered decision (at 40 sessions)
    python claude_leads.py --before DB          # the sessions before the change (descriptive)
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
REVIEWS = ROOT / 'data' / 'reviews'
DECISION = 40              # sessions: the registered look
HARM = 20                  # sessions: the early harm check
SEED = 144
DRAWS = 10000


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _cost():
    import primary_board
    return primary_board.COST_PER_PICK_PCT


def _net(rets):
    """An arm's net return for a session: the mean of (r_pct − cost) over its
    picks, 0 when it stood aside (no trade, no cost)."""
    return st.mean(r - _cost() for r in rets) if rets else 0.0


def led_sessions(rows):
    """{session: {'claude': [r_pct …], 'council': [r_pct …]}} for every session
    whose printed Top 2 was Claude-led, with None for a pick not yet scored."""
    import council
    out = {}
    for r in rows:
        if (r.get('model') == 'top2' and r.get('kind') == 'pick'
                and str(r.get('prompt_version') or '').startswith(council.CLAUDE_RULE)):
            out.setdefault(r['session'], {'claude': [], 'council': []})['claude'].append(_num(r.get('r_pct')))
    for r in rows:
        if r.get('model') == 'top2council' and r.get('kind') == 'pick' and r.get('session') in out:
            out[r['session']]['council'].append(_num(r.get('r_pct')))
    return out


def paired(rows):
    """[(session, d, claude, council)] over the Claude-led sessions whose picks
    are all scored, in session order. d = Claude-led net − the council's own
    net; the council's own is 0 on a day it chose nothing."""
    out = []
    for s, arms in sorted(led_sessions(rows).items()):
        if any(v is None for v in arms['claude'] + arms['council']):
            continue
        out.append((s, _net(arms['claude']) - _net(arms['council']), arms['claude'], arms['council']))
    return out


def _t(ds):
    if len(ds) < 3 or not st.stdev(ds):
        return None
    return st.mean(ds) / (st.stdev(ds) / math.sqrt(len(ds)))


def _arm(rets):
    rets = [r for r in rets if r is not None]
    if not rets:
        return {'picks': 0, 'right': 0, 'mean': None, 'net': None}
    return {'picks': len(rets), 'right': sum(r > 0 for r in rets), 'mean': round(st.mean(rets), 3),
            'net': round(st.mean(rets) - _cost(), 3)}


def readout(rows=None):
    """The running comparison: each arm's picks, and the paired difference."""
    import model_picks as M
    rows = M.read() if rows is None else rows
    days = paired(rows)
    ds = [d for _, d, *_ in days]
    t = _t(ds)
    return {'sessions': len(days), 'pending': len(led_sessions(rows)) - len(days),
            'claude': _arm([r for _, _, c, _ in days for r in c]),
            'council': _arm([r for *_, k in days for r in k]),
            'council_stood_aside': sum(1 for *_, k in days if not k),
            'mean_d': round(st.mean(ds), 3) if ds else None,
            't': None if t is None else round(t, 2)}


def placebo(ds, draws=DRAWS, seed=SEED):
    """One-sided sign-flip p: the share of random sign patterns with a t at
    least the observed one (each session's difference is flipped as a unit)."""
    t0 = _t(ds)
    if t0 is None:
        return None
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        t = _t([d if rng.random() < 0.5 else -d for d in ds])
        if t is not None and t >= t0:
            hits += 1
    return (1 + hits) / (1 + draws)


def verdict(rows=None, *, draws=DRAWS, seed=SEED):
    """The registered decision (PREREGISTER_day144_claude_leads.md).
    NOT_DUE before 20 sessions; HARM or RUNNING between 20 and 40; at the 40th
    scored Claude-led session CLAUDE_BETTER, COUNCIL_BETTER or NO_DIFFERENCE.
    Each goes to the owner; nothing is switched by it."""
    import model_picks as M
    rows = M.read() if rows is None else rows
    days = paired(rows)
    if len(days) < HARM:
        return {'status': 'NOT_DUE', 'sessions': len(days)}
    if len(days) < DECISION:
        ds = [d for _, d, *_ in days[:HARM]]
        t = _t(ds)
        return {'status': 'HARM' if t is not None and t <= -2 else 'RUNNING', 'sessions': len(days),
                'look': HARM, 'mean_d': round(st.mean(ds), 3), 't': None if t is None else round(t, 2)}
    ds = [d for _, d, *_ in days[:DECISION]]
    t = _t(ds)
    p = placebo(ds, draws=draws, seed=seed)
    half = DECISION // 2
    halves = [st.mean(ds[:half]), st.mean(ds[half:])]
    sd = st.stdev(ds)
    status = ('CLAUDE_BETTER' if t is not None and t >= 3 and p is not None and p < 0.01
              and all(h > 0 for h in halves) else
              'COUNCIL_BETTER' if t is not None and t <= -2 else 'NO_DIFFERENCE')
    return {'status': status, 'sessions': len(days), 'look': DECISION,
            'mean_d': round(st.mean(ds), 3), 't': None if t is None else round(t, 2),
            'placebo_p': None if p is None else round(p, 4),
            'halves': [round(h, 3) for h in halves],
            # the difference t = 3 needs with 80% power, at this spread
            'mde': round((3 + 0.84) * sd / math.sqrt(len(ds)), 3) if sd else None}


def lines(session=None, rows=None):
    """The evening review's section."""
    out = ['## Claude-led Top 2 against the council\'s own choice (day-144)',
           'From 2026-11-02 the Top 2 is Claude\'s first-named long and short (the owner\'s decision); '
           'the council\'s own choice is recorded beside it. Net of the %.2f%% round trip; a day the '
           'council chose nothing counts 0 for it. Verdict at %d sessions '
           '(PREREGISTER_day144_claude_leads.md).' % (_cost(), DECISION)]
    r = readout(rows)
    if not r['sessions']:
        out.append('Record: no scored Claude-led session yet%s.'
                   % (' (%d waiting for scores)' % r['pending'] if r['pending'] else ''))
        return out
    c, k = r['claude'], r['council']
    out.append('Record: %d sessions. Claude-led %d picks, %d right, %s gross; the council\'s own %d '
               'picks, %d right, %s gross (it chose nothing on %d). Claude-led − council %+.2f%% a '
               'session net%s.'
               % (r['sessions'], c['picks'], c['right'], '—' if c['mean'] is None else '%+.2f%%' % c['mean'],
                  k['picks'], k['right'], '—' if k['mean'] is None else '%+.2f%%' % k['mean'],
                  r['council_stood_aside'], r['mean_d'],
                  '' if r['t'] is None else ', t = %.2f' % r['t']))
    return out


# ── before the change: descriptive, never part of the test ──────────────────

def _frozen_orders(db):
    """{session: {'LONG': [...], 'SHORT': [...]}} of Claude's nominations, best
    first, from the frozen reports."""
    import sqlite3
    out = {}
    if not db or not Path(db).exists():
        return out
    con = sqlite3.connect(db)
    for session, body in con.execute('select session, body from reports'):
        noms = ((json.loads(body).get('intraday') or {}).get('council') or {}).get('nomination_picks') or {}
        got = noms.get('claude') or {}
        out[session] = {side: [p.get('ticker') for p in got.get(key) or []]
                        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts'))}
    return out


def _review_order(session, side, reviews):
    f = Path(reviews) / ('%s.json' % session)
    if not f.exists():
        return []
    return [r['ticker'] for r in json.loads(f.read_text()).get('rows') or []
            if r.get('section') == 'Nominated (forced)' and r.get('model') == 'claude'
            and r.get('side') == side]


def before(rows=None, *, db=None, reviews=REVIEWS):
    """The Claude-led Top 2 as it would have been on each session with recorded
    nominations, against the Top 2 as printed. The order of Claude's
    nominations comes from the frozen report when `db` holds the session, else
    from that day's review, which keeps only the names it scored: the order is
    known there only when every one of Claude's nominations on that side was
    scored, and a side whose order is unknown is left out and counted."""
    import model_picks as M
    rows = M.read() if rows is None else rows
    noms, printed = {}, {}
    for r in rows:
        if r.get('model') == 'claude' and r.get('kind') == 'nominated':
            noms.setdefault(r['session'], {}).setdefault(r['side'], {})[r['ticker']] = _num(r.get('r_pct'))
        if r.get('model') == 'top2' and r.get('kind') == 'pick':
            printed.setdefault(r['session'], []).append(_num(r.get('r_pct')))
    frozen = _frozen_orders(db)
    days, unknown, source = [], [], {}
    for s in sorted(noms):
        picks = []
        for side in ('LONG', 'SHORT'):
            have = noms[s].get(side) or {}
            if not have:
                continue
            order = (frozen.get(s) or {}).get(side)
            if order:
                source[s] = 'frozen report'
            else:
                order = _review_order(s, side, reviews)
                if set(order) != set(have):
                    unknown.append('%s %s' % (s, side))
                    continue
                source.setdefault(s, 'review')
            picks.append(have.get(order[0]))
        council_ = printed.get(s, [])
        if not picks or any(v is None for v in picks + council_):
            continue
        days.append((s, _net(picks) - _net(council_), picks, council_))
    ds = [d for _, d, *_ in days]
    t = _t(ds)
    return {'sessions': len(days), 'first': days[0][0] if days else None,
            'last': days[-1][0] if days else None,
            'claude_first_named': _arm([r for _, _, c, _ in days for r in c]),
            'top2_printed': _arm([r for *_, k in days for r in k]),
            'printed_stood_aside': sum(1 for *_, k in days if not k),
            'mean_d': round(st.mean(ds), 3) if ds else None, 't': None if t is None else round(t, 2),
            'order_unknown': unknown,
            'order_source': {k: sum(1 for v in source.values() if v == k) for k in ('frozen report', 'review')},
            'rows': [{'session': s, 'd': round(d, 3), 'claude': c, 'printed': k} for s, d, c, k in days]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = p.add_mutually_exclusive_group()
    g.add_argument('--verdict', action='store_true')
    g.add_argument('--before', metavar='DB', help='the frozen reports (reports.sqlite3)')
    p.add_argument('--out', help='write the --before summary here')
    a = p.parse_args(argv)
    if a.verdict:
        print(json.dumps(verdict(), indent=1))
    elif a.before:
        got = before(db=a.before)
        if a.out:
            Path(a.out).write_text(json.dumps(got, indent=1) + '\n')
        print(json.dumps({k: v for k, v in got.items() if k != 'rows'}, indent=1))
    else:
        print('\n'.join(lines()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
