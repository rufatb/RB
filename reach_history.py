#!/usr/bin/env python3
"""DAY-141 — A STOP WITHIN REACH, TESTED ON THE RECORD (council lab item 1).

PREREGISTER_day141_reach_history.md. Every scored desk pick of Claude,
DeepSeek and Gemini (kinds selected and nominated) from 2026-09-17 to
2026-10-23 is KEPT when its own "wrong if" is within council_flash.REACH_ATR
normal days of its 09:45 entry, and DROPPED otherwise (no level, a level out
of reach, or one already crossed at the entry). Kept against dropped is
judged on the record's r_pct by day-140's arm-A test (fixpack.arm_a) at seed
141; 2026-10-15, the day that suggested the rule, is left out of the verdict
and reported beside it.

Research only: nothing live reads this file, and no pick, size, prompt or
rule changes with its result.

    python reach_history.py        # writes data/reach_day141.json
"""
from __future__ import annotations

import argparse
import collections
import functools
import json
import math
import sys
from pathlib import Path

import fixpack

ROOT = Path(__file__).resolve().parent
SUMMARY = ROOT / 'data' / 'reach_day141.json'
FIRST, LAST = '2026-09-17', '2026-10-23'
HELD_OUT = '2026-10-15'          # the day that suggested the rule (day-135)
MODELS = ('claude', 'deepseek', 'gemini')
KINDS = ('selected', 'nominated')
SEED = 141
DRAWS = fixpack.DRAWS            # 2,000, as registered
BAR = fixpack.BAR                # t >= 3.0
PLANT = 1.0                      # the planted control, % a kept pick
POWER_Z = 0.8416                 # 80% power


# ── the population and its labels (pure) ────────────────────────────────────

def population(rows):
    """The registered picks: the three desks that state levels, selected and
    nominated, scored, in FIRST..LAST."""
    out = []
    for r in rows:
        y = fixpack._num(r.get('r_pct'))
        if (r.get('model') in MODELS and r.get('kind') in KINDS and y is not None
                and FIRST <= (r.get('session') or '') <= LAST):
            out.append({'session': r['session'], 'model': r['model'], 'kind': r['kind'],
                        'ticker': r['ticker'], 'side': r['side'],
                        'invalid_at': fixpack._num(r.get('invalid_at')),
                        'entry': fixpack._num(r.get('entry')), 'y': y})
    return out


def label(picks, atr):
    """Each pick with its gate, by fixpack.gate (the open check's rule).
    atr(ticker, session) -> ATR % or None. A pick the gate cannot judge (a
    level with no ATR, or no entry) is excluded and returned apart."""
    judged, excluded = [], []
    for p in picks:
        a = atr(p['ticker'], p['session']) if p['invalid_at'] else None
        gate, reason, days = fixpack.gate(p['side'], p['invalid_at'], p['entry'], a)
        q = dict(p, atr_pct=a, gate=gate, reason=reason, reach_atr=days)
        (judged if gate in ('kept', 'dropped') else excluded).append(q)
    return judged, excluded


def triples(picks, key=lambda p: p['gate'] == 'kept'):
    return [(p['session'], p['y'], key(p)) for p in picks]


def control(picks):
    """House rule 10: each group centred on zero, PLANT added to every kept
    pick, then the same statistic. Returns (diff, t)."""
    k = [p['y'] for p in picks if p['gate'] == 'kept']
    d = [p['y'] for p in picks if p['gate'] != 'kept']
    if not k or not d:
        return None, None
    mk, md = fixpack._mean(k), fixpack._mean(d)
    planted = [(p['session'], p['y'] - mk + PLANT, True) if p['gate'] == 'kept'
               else (p['session'], p['y'] - md, False) for p in picks]
    return fixpack.two_group(planted)


def verdict(picks):
    """The registered decision on the primary picks."""
    got = fixpack.arm_a(triples(picks), draws=DRAWS, seed=SEED)
    status = got['status'] if got['status'] in ('PASS', 'FAIL') else 'NULL'
    c_diff, c_t = control(picks)
    got['control'] = {'plant': PLANT, 'diff': c_diff, 't': c_t,
                      'detected': c_t is not None and c_t >= BAR}
    if status == 'NULL' and not got['control']['detected']:
        status = 'UNDERPOWERED'
    got['mde80'] = ((BAR + POWER_Z) * PLANT / c_t) if c_t else None
    got['kept_net_mean'] = (None if got['kept_mean'] is None
                            else got['kept_mean'] - fixpack.COST)
    got['status'] = status
    return got


# ── descriptive, never a verdict ────────────────────────────────────────────

def _split(picks, key):
    diff, t = fixpack.two_group(triples(picks, key))
    yes = [p['y'] for p in picks if key(p)]
    no = [p['y'] for p in picks if not key(p)]
    return {'diff': diff, 't': t, 'yes': len(yes), 'no': len(no),
            'yes_mean': fixpack._mean(yes), 'no_mean': fixpack._mean(no),
            'yes_right': sum(1 for y in yes if y > 0), 'no_right': sum(1 for y in no if y > 0),
            'sessions': len({p['session'] for p in picks})}


def positions(picks):
    """One row per (session, ticker, side): kept when any proposer's level is
    within reach. The outcome is the record's, the same for every proposer."""
    by = collections.OrderedDict()
    for p in picks:
        k = (p['session'], p['ticker'], p['side'])
        q = by.setdefault(k, dict(p, gate='dropped', proposers=0, spread=0.0))
        q['proposers'] += 1
        q['spread'] = max(q['spread'], abs(p['y'] - q['y']))
        if p['gate'] == 'kept':
            q['gate'] = 'kept'
    return list(by.values())


def describe(judged, excluded, everything):
    primary = [p for p in judged if p['session'] != HELD_OUT]
    kept = lambda p: p['gate'] == 'kept'
    out = {
        'with_held_out_day': fixpack.arm_a(triples(judged), draws=DRAWS, seed=SEED),
        'held_out_day': [{k: p[k] for k in ('model', 'kind', 'ticker', 'side', 'gate',
                                            'reason', 'reach_atr', 'y')}
                         for p in judged if p['session'] == HELD_OUT],
        'unique_positions': _split(positions(primary), kept),
        'by_model': {m: _split([p for p in primary if p['model'] == m], kept) for m in MODELS},
        'by_kind': {k: _split([p for p in primary if p['kind'] == k], kept) for k in KINDS},
        'any_level': _split([p for p in everything if p['session'] != HELD_OUT],
                            lambda p: p['invalid_at'] is not None),
        'dropped_reasons': dict(collections.Counter(
            'out of reach' if 'normal days away' in p['reason'] else p['reason']
            for p in primary if p['gate'] == 'dropped')),
        'excluded': [{k: p[k] for k in ('session', 'model', 'ticker', 'side', 'reason')}
                     for p in excluded],
    }
    out['unique_positions']['max_outcome_spread'] = max(
        (q['spread'] for q in positions(primary)), default=0.0)
    return out


# ── the run ─────────────────────────────────────────────────────────────────

def bars_atr(chart=None):
    """atr(ticker, session) from Yahoo daily bars cut before the session (the
    brief's own computation, fixpack._bars_atr); one chart per ticker."""
    import news_desk
    fetch = functools.lru_cache(maxsize=None)(chart or news_desk.daily_chart)
    return functools.lru_cache(maxsize=None)(
        lambda ticker, session: fixpack._bars_atr(ticker, session, chart=fetch))


def run(rows=None, atr=None):
    import model_picks as M
    picks = population(M.read() if rows is None else rows)
    judged, excluded = label(picks, atr or bars_atr())
    primary = [p for p in judged if p['session'] != HELD_OUT]
    return {'registration': 'PREREGISTER_day141_reach_history.md',
            'population': {'picks': len(picks), 'with_level': sum(1 for p in picks if p['invalid_at']),
                           'sessions': len({p['session'] for p in picks}),
                           'judged': len(judged), 'excluded_no_atr': len(excluded),
                           'primary_picks': len(primary),
                           'primary_sessions': len({p['session'] for p in primary})},
            'verdict': verdict(primary),
            'descriptive': describe(judged, excluded, picks)}


def _pct(v):
    return '—' if v is None else '%+.2f%%' % v


def digest(s):
    v, d = s['verdict'], s['descriptive']
    t = lambda x: '—' if x is None else '%.2f' % x
    lines = [
        'Day-141, a stop within reach on the record: %s.' % v['status'],
        'Kept %d picks %s, dropped %d %s: difference %s, t = %s, placebo p = %s, halves %s, '
        '%d sessions.' % (v['kept'], _pct(v['kept_mean']), v['dropped'], _pct(v['dropped_mean']),
                          _pct(v['diff']), t(v['t']), t(v['placebo_p']),
                          ' / '.join(_pct(h) for h in v['halves']), v['sessions']),
        'Planted %.1f%%: t = %s (%s); smallest detectable effect %s a pick.' % (
            PLANT, t(v['control']['t']), 'detected' if v['control']['detected'] else 'NOT detected',
            _pct(v['mde80'])),
        'Kept picks net of the 0.13%% round trip: %s.' % _pct(v['kept_net_mean']),
        'With 10-15: difference %s, t = %s.' % (_pct(d['with_held_out_day']['diff']),
                                                 t(d['with_held_out_day']['t'])),
        'Unique positions: kept %d %s, dropped %d %s, t = %s.' % (
            d['unique_positions']['yes'], _pct(d['unique_positions']['yes_mean']),
            d['unique_positions']['no'], _pct(d['unique_positions']['no_mean']),
            t(d['unique_positions']['t'])),
        'Any level against none: %d %s against %d %s, t = %s.' % (
            d['any_level']['yes'], _pct(d['any_level']['yes_mean']), d['any_level']['no'],
            _pct(d['any_level']['no_mean']), t(d['any_level']['t'])),
        'Excluded for want of an ATR: %d.' % len(d['excluded']),
    ]
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--out', default=str(SUMMARY))
    a = p.parse_args(argv)
    summary = run()
    Path(a.out).write_text(json.dumps(summary, indent=1, default=str) + '\n')
    print(digest(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
