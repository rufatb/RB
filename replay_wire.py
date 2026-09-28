#!/usr/bin/env python3
"""Day-118 replay: do the desks read a DIRECTION from the issuer's own release?

Registered in PREREGISTER_day118_wire.md before anything here was run. The
day-117 pools (`replay_models`, cached) are reused unchanged; each candidate
gains the wire releases the live staging would have shown it at 08:55
(`newswire.headlines`, through the production validator), and the live
prompts are asked once per session. Scored by the production scorer.

    python replay_wire.py --run        # ask DeepSeek and Jev, cached per session
    python replay_wire.py --analyse    # the registered statistics, controls first
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import time

import newswire
import replay_models as R

ET = R.ET
CACHE = R.CACHE/'wire'
SHOWN_AT = dt.time(8, 55)
MIN_EVENT_PICKS = 30


def with_wire(session, pool):
    """The cached pool with each name's wire releases as its headlines (72h
    before 08:55, as live), and the registered EVENT set: names a release named
    in `newswire.window(session)`."""
    import factor_inputs as F
    now = dt.datetime.combine(session, SHOWN_AT, tzinfo=ET)
    stamp = F._stamp(now)
    start, end = newswire.window(session)
    candidates, events, shown = [], [], 0
    for c in pool['candidates']:
        t = c['ticker']
        raw = newswire.headlines(t, now)
        gaps = []
        heads = F._evidence(raw, 'headlines', stamp, gaps, stamp, t) if raw else []
        shown += bool(heads)
        candidates.append({**c, 'headlines': heads})
        if newswire.releases_for(t, start, end):
            events.append(t)
    return {**pool, 'candidates': candidates, 'events': events, 'names_shown_a_release': shown}


def ask(session, pool):
    path = CACHE/'answers'/f'{session}.json'
    if path.exists():
        return json.loads(path.read_text())
    import deepseek_opportunities as O
    import jev_opportunities as J
    now = dt.datetime.combine(session, dt.time(9, 0), tzinfo=ET)
    started = time.monotonic()
    ds = O.rank(pool['candidates'], macro=pool['macro'] or None, now=now)
    seconds = time.monotonic() - started
    jev = J.rank(pool['candidates'], macro=pool['macro'] or None, now=now)
    out = {'session': session.isoformat(), 'deepseek': ds, 'jev': jev,
           'deepseek_seconds': round(seconds, 1), 'prompt_version': O.PROMPT_VERSION,
           'events': pool['events'], 'names_shown_a_release': pool['names_shown_a_release']}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=str))
    return out


# ── the registered statistics ────────────────────────────────────────────────

def direction_test(flat, *, draws=2000, seed=118):
    """`flat`: [(session, side, r)] for one group, r signed to the pick's side.

    H1's bar: clustered t >= 2.0 on per-session means; hit rate beats a
    SIDE-FLIP placebo (each pick a random side, same names) at p < 0.05; same
    sign in both halves by date. Fewer than MIN_EVENT_PICKS is UNDERPOWERED."""
    rng = random.Random(seed)
    by = {}
    for s, _side, r in flat:
        by.setdefault(s, []).append(r)
    c = R.clustered(by)
    n = len(flat)
    hits = sum(r > 0 for _, _, r in flat)
    null = []
    for _ in range(draws):
        null.append(sum((r if rng.random() < .5 else -r) > 0 for _, _, r in flat) / n if n else 0)
    rate = hits / n if n else None
    p = sum(x >= rate for x in null) / len(null) if n else None
    ordered = sorted(by)
    half = len(ordered) // 2
    halves = [R.clustered({s: by[s] for s in part})['mean'] for part in (ordered[:half], ordered[half:])]
    mde = (2.8 * c['sd'] / math.sqrt(c['sessions'])) if c.get('sd') and c['sessions'] else None
    passed = bool(n >= MIN_EVENT_PICKS and c['t'] is not None and c['t'] >= 2.0 and p < 0.05
                  and all(h is not None and h > 0 for h in halves))
    verdict = ('PASS' if passed else 'UNDERPOWERED' if n < MIN_EVENT_PICKS else 'FAIL')
    return {'picks': n, 'hits': hits, 'hit_rate': rate,
            'mean_r_pct': sum(r for _, _, r in flat) / n if n else None,
            'clustered': c, 'side_flip_p': p, 'halves': halves, 'mde80_pct': mde,
            'verdict': verdict}


def moves_more(pools, events):
    """H3: per session, mean |r| of event names minus mean |r| of the rest."""
    diffs = {}
    for s, names in pools.items():
        ev = [abs(r) for t, r in names.items() if t in events.get(s, ())]
        rest = [abs(r) for t, r in names.items() if t not in events.get(s, ())]
        if ev and rest:
            diffs[s] = [sum(ev)/len(ev) - sum(rest)/len(rest)]
    c = R.clustered(diffs)
    return {**c, 'passes': bool(c['t'] is not None and c['t'] >= 2.0),
            'event_name_days': sum(len([t for t in names if t in events.get(s, ())])
                                   for s, names in pools.items())}


def controls(pools, events, seed=1181):
    """The statistic must PASS planted picks that take the realized sign on
    every event name, and FAIL random sides on the same names."""
    rng = random.Random(seed)
    planted, coin = [], []
    for s, names in pools.items():
        for t in events.get(s, ()):
            if t in names:
                planted.append((s, 'X', abs(names[t])))
                coin.append((s, 'X', names[t] if rng.random() < .5 else -names[t]))
    return {'planted': direction_test(planted)['verdict'],
            'coin': direction_test(coin)['verdict'], 'event_name_days': len(planted)}


def analyse(days):
    import deepseek_opportunities as O
    cache, pools, events, groups, detail = {}, {}, {}, {}, []
    shown = {}
    for d in days:
        path = CACHE/'answers'/f'{d}.json'
        pool_path = R.CACHE/'pools'/f'{d}.json'
        if not path.exists() or not pool_path.exists():
            continue
        s = d.isoformat()
        ans = json.loads(path.read_text())
        pl = json.loads(pool_path.read_text())
        events[s] = set(ans['events'])
        shown[s] = ans['names_shown_a_release']
        pools[s] = {}
        for c in O.usable_candidates(pl['candidates']):
            sc = R.realized(s, c['ticker'], 'LONG', cache)
            if sc:
                pools[s][c['ticker']] = sc['r_pct']
        for group, side, pick in R.picks_of(ans):
            sc = R.realized(s, pick['ticker'], side, cache)
            if not sc:
                continue
            ev = pick['ticker'] in events[s]
            groups.setdefault(group + '_all', []).append((s, side, sc['r_pct']))
            if ev:
                groups.setdefault(group + '_event', []).append((s, side, sc['r_pct']))
            detail.append({'session': s, 'group': group, 'side': side, 'ticker': pick['ticker'],
                           'event': ev, 'basis': pick.get('basis'), 'r_pct': sc['r_pct'],
                           'confidence': pick.get('confidence', pick.get('probability'))})
    ctl = controls(pools, events)
    out = {'sessions': len(pools), 'controls': ctl,
           'event_name_days': sum(len(v) for v in events.values()),
           'names_shown_a_release': sum(shown.values()),
           'oracle': R.oracle(pools)}
    if ctl['planted'] != 'PASS' or ctl['coin'] == 'PASS':
        out['verdict'] = 'CONTROLS FAILED — nothing below is reported'
        return out
    out['H1_deepseek_event'] = direction_test(groups.get('deepseek_selected_event', []))
    out['H2_jev_forced_event'] = direction_test(groups.get('jev_forced_event', []))
    out['H3_event_names_move_more'] = moves_more(pools, events)
    out['descriptive'] = {g: direction_test(v) for g, v in groups.items()}
    out['picks'] = detail
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--run', action='store_true')
    p.add_argument('--analyse', action='store_true')
    a = p.parse_args(argv)
    days = R.sessions()
    if a.run:
        from prepare_deepseek import load_private_key
        import jev_opportunities as J
        os.environ.setdefault('DEEPSEEK_MODEL', 'deepseek-flash')
        load_private_key(R.ROOT/'.rb-state')
        J.load_private_key(R.ROOT/'.rb-state')
        cfg = R._cfg()
        for d in days:
            pl = with_wire(d, R.pool(d, cfg))
            ans = ask(d, pl)
            print(d, 'events', len(pl['events']), 'shown', pl['names_shown_a_release'],
                  'deepseek', (ans['deepseek'] or {}).get('status'), flush=True)
    if a.analyse:
        report = analyse(days)
        (CACHE/'analysis.json').write_text(json.dumps(report, indent=1, default=str))
        print(json.dumps({k: v for k, v in report.items() if k != 'picks'}, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
