"""Day-154 (PREREGISTER_day154_floor_history.md): the day-150 quality floor,
applied to Claude's past council nominations.

Council lab item 16. `--pin` writes `data/floor_day154_positions.json` from the
record's nominations and the councils' final tallies; it reads no return.
`--run` is the one registered look (added in its own commit before it ran):
kept minus dropped by `fixpack.arm_a` at seed 154, the net condition, the
planted control, and the descriptive splits, into `data/floor_day154.json`.

The floor (`council.FLOOR`, the owner's rule of 2026-11-10): a pick of Claude's
stands when Claude rates it 0.50 or higher (`FLOOR_CONFIDENCE`), or when two or
more council members endorse it on the final tally, Claude's own ballot
included (`FLOOR_ENDORSE`).

Sources, read without any outcome column:
* the nominations and Claude's own confidence: `data/model_picks.csv`, rows
  `claude/nominated`, sessions 2026-10-14 → 2026-11-19;
* the final tallies: `data/veto_day148_positions.json` (pinned on day-148, from
  day-137's tables and the frozen reports) and, for sessions it does not
  cover, the frozen reports in `.rb-state/reports.sqlite3`
  (`intraday.council.tally.rows`).
"""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

LEDGER = Path('data/model_picks.csv')
VETO_PIN = Path('data/veto_day148_positions.json')
REPORTS = Path('.rb-state/reports.sqlite3')
PIN = Path('data/floor_day154_positions.json')
FIRST, LAST = '2026-10-14', '2026-11-19'

import council  # noqa: E402  (the live rule, never a copy of it)

FLOOR_CONFIDENCE = council.FLOOR_CONFIDENCE
FLOOR_ENDORSE = council.FLOOR_ENDORSE


def nominations(path=LEDGER, first=FIRST, last=LAST):
    """Claude's nominations, each (session, ticker, side) once; no outcome read."""
    seen = {}
    with open(path, newline='') as fh:
        for r in csv.DictReader(fh):
            if (r.get('model') != 'claude' or r.get('kind') != 'nominated'
                    or not first <= r.get('session', '') <= last):
                continue
            key = (r['session'], r['ticker'], r['side'])
            if key in seen:
                continue
            try:
                conf = float(r.get('confidence'))
            except (TypeError, ValueError):
                conf = None
            seen[key] = {'session': r['session'], 'ticker': r['ticker'], 'side': r['side'],
                         'confidence': conf}
    return [seen[k] for k in sorted(seen)]


def veto_tallies(path=VETO_PIN):
    """{session: {(ticker, side): (endorse, oppose, members)}} from the day-148 pin."""
    out = {}
    for p in json.loads(Path(path).read_text())['positions']:
        out.setdefault(p['session'], {})[(p['ticker'], p['side'])] = (
            int(p['endorse']), int(p['oppose']), int(p['members']))
    return out


def report_tallies(path=REPORTS, sessions=()):
    """The same, from the frozen reports' final council tallies."""
    out = {}
    if not Path(path).exists():
        return out
    con = sqlite3.connect(str(path))
    try:
        for session in sessions:
            row = con.execute('select body from reports where session = ?', (session,)).fetchone()
            if not row:
                continue
            council = ((json.loads(row[0]).get('intraday') or {}).get('council') or {})
            rows = (council.get('tally') or {}).get('rows')
            if not rows:
                continue
            seats = max((len(r.get('seats') or []) for r in rows), default=0)
            out[session] = {(r['ticker'], r['side']): (len(r.get('endorse') or []),
                                                       len(r.get('oppose') or []), seats)
                            for r in rows}
    finally:
        con.close()
    return out


def floor_kept(confidence, endorse):
    """The floor as live (`council.clears_floor`): the confidence leg, or two
    endorsements on the tally. A nomination that was not on the table has only
    the confidence leg."""
    return council.clears_floor({'confidence': confidence, 'endorsed': endorse})


def pin(ledger=LEDGER, veto=VETO_PIN, reports=REPORTS):
    noms = nominations(ledger)
    sessions = sorted({n['session'] for n in noms})
    tallies = veto_tallies(veto)
    from_pin = set(tallies)
    later = report_tallies(reports, [s for s in sessions if s not in tallies])
    tallies.update(later)
    positions, no_tally = [], []
    for n in noms:
        t = tallies.get(n['session'])
        if t is None:
            no_tally.append(n['session'])
            continue
        e, o, m = t.get((n['ticker'], n['side']), (None, None, None))
        positions.append({**n, 'on_table': e is not None, 'endorse': e, 'oppose': o,
                          'members': m, 'source': 'day148_pin' if n['session'] in from_pin
                          else 'frozen_report',
                          'kept': floor_kept(n['confidence'], e)})
    return {'registration': 'PREREGISTER_day154_floor_history.md',
            'rule': {'confidence': FLOOR_CONFIDENCE, 'endorse': FLOOR_ENDORSE},
            'note': 'No outcome was read to build this file.',
            'sessions_without_tally': sorted(set(no_tally)),
            'positions': positions}


# ── the registered run (one look) ───────────────────────────────────────────
#
# Choices fixed in code before the run, where the registration left them open:
# * the outcome is the r_pct of the same ledger row the pin took (the first
#   claude/nominated row of each position); a position with no r_pct there is
#   counted as unscored and left out;
# * the order of labels: SORTS, then REMOVES_WINNERS (named whatever the
#   control says, as the forward harm check would be), then UNDERPOWERED
#   (the planted 1.0% short of t = 3), then NULL. REMOVES_WINNERS is also
#   printed as its own flag;
# * se for the smallest detectable effect is the planted control's diff / t,
#   and the effect printed is 2.8 x se, as registered;
# * first-named / second-named is each position's order among Claude's
#   nominations on that session and side, in ledger order.

import fixpack  # noqa: E402

SEED = 154
PLANT = 1.0
MDE_Z = 2.8
HARM_T = 2.0
COST = fixpack.COST
SUMMARY = Path('data/floor_day154.json')
SHADOW_FIRST, SHADOW_LAST = '2026-11-11', '2026-11-19'


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def outcomes(path=LEDGER, first=FIRST, last=LAST):
    """{(session, ticker, side): (r_pct or None, rank)} from the first
    claude/nominated row of each position; rank is 1 for the first-named on
    that session and side."""
    out, seen_side = {}, {}
    with open(path, newline='') as fh:
        for r in csv.DictReader(fh):
            if (r.get('model') != 'claude' or r.get('kind') != 'nominated'
                    or not first <= r.get('session', '') <= last):
                continue
            key = (r['session'], r['ticker'], r['side'])
            if key in out:
                continue
            side_key = (r['session'], r['side'])
            seen_side[side_key] = seen_side.get(side_key, 0) + 1
            out[key] = (_num(r.get('r_pct')), seen_side[side_key])
    return out


def join(positions, outs):
    """The pinned positions with their outcome; (scored, unscored)."""
    scored, unscored = [], []
    for p in positions:
        y, rank = outs.get((p['session'], p['ticker'], p['side']), (None, None))
        (unscored if y is None else scored).append(dict(p, y=y, rank=rank))
    return scored, unscored


def triples(picks, key=lambda p: p['kept']):
    return [(p['session'], p['y'], bool(key(p))) for p in picks]


def control(picks):
    """House rule 10: each group centred on zero, PLANT added to every kept
    pick, then the same statistic (edge / se, never (mean + edge) / se)."""
    k = [p['y'] for p in picks if p['kept']]
    d = [p['y'] for p in picks if not p['kept']]
    if not k or not d:
        return None, None
    mk, md = sum(k) / len(k), sum(d) / len(d)
    planted = [(p['session'], p['y'] - mk + PLANT, True) if p['kept']
               else (p['session'], p['y'] - md, False) for p in picks]
    return fixpack.two_group(planted)


def verdict(picks, *, draws=fixpack.DRAWS, seed=SEED):
    got = fixpack.arm_a(triples(picks), draws=draws, seed=seed)
    c_diff, c_t = control(picks)
    se = (c_diff / c_t) if c_t else None
    detected = c_t is not None and c_t >= fixpack.BAR
    dm = got['dropped_mean']
    dropped_loses = dm is not None and dm < COST
    removes_winners = got['t'] is not None and got['t'] <= -HARM_T
    if got['status'] == 'PASS' and dropped_loses and detected:
        status = 'SORTS'
    elif removes_winners:
        status = 'REMOVES_WINNERS'
    elif not detected:
        status = 'UNDERPOWERED'
    else:
        status = 'NULL'
    return dict(got, arm_a_status=got['status'], status=status,
                removes_winners=removes_winners, dropped_loses_net=dropped_loses,
                control={'plant': PLANT, 'diff': c_diff, 't': c_t, 'detected': detected},
                se=se, mde80=(MDE_Z * se) if se else None,
                kept_net=None if got['kept_mean'] is None else got['kept_mean'] - COST,
                dropped_net=None if dm is None else dm - COST)


def _group(ys):
    if not ys:
        return {'n': 0, 'mean': None, 'right': 0}
    return {'n': len(ys), 'mean': sum(ys) / len(ys), 'right': sum(1 for y in ys if y > 0),
            'net': sum(ys) / len(ys) - COST}


def split(picks, key):
    diff, t = fixpack.two_group(triples(picks, key))
    return {'yes': _group([p['y'] for p in picks if key(p)]),
            'no': _group([p['y'] for p in picks if not key(p)]), 'diff': diff, 't': t}


def shadow(path=LEDGER, first=SHADOW_FIRST, last=SHADOW_LAST):
    """The live floor's drops (top2floor/pick) and what stood on that side."""
    rows = list(csv.DictReader(open(path, newline='')))
    stood = {(r['session'], r['side']): r for r in rows
             if r.get('model') == 'top2' and r.get('kind') == 'pick'}
    out = []
    for r in rows:
        if (r.get('model') == 'top2floor' and r.get('kind') == 'pick'
                and first <= r.get('session', '') <= last):
            s = stood.get((r['session'], r['side']))
            out.append({'session': r['session'], 'side': r['side'], 'ticker': r['ticker'],
                        'r_pct': _num(r.get('r_pct')),
                        'stood': s['ticker'] if s else None,
                        'stood_r_pct': _num(s.get('r_pct')) if s else None})
    return out


def run(pin_path=PIN, ledger=LEDGER):
    pinned = json.loads(Path(pin_path).read_text())
    picks, unscored = join(pinned['positions'], outcomes(ledger))
    v = verdict(picks)
    return {'registration': 'PREREGISTER_day154_floor_history.md', 'seed': SEED,
            'positions': len(pinned['positions']), 'scored': len(picks),
            'unscored': [{k: p[k] for k in ('session', 'ticker', 'side')} for p in unscored],
            'sessions': len({p['session'] for p in picks}),
            'verdict': v,
            'describe': {
                'confidence_leg': split(picks, lambda p: (p['confidence'] or 0) >= FLOOR_CONFIDENCE),
                'endorse_leg': split(picks, lambda p: (p['endorse'] or 0) >= FLOOR_ENDORSE),
                'long_kept_vs_dropped': split([p for p in picks if p['side'] == 'LONG'],
                                              lambda p: p['kept']),
                'short_kept_vs_dropped': split([p for p in picks if p['side'] == 'SHORT'],
                                               lambda p: p['kept']),
                'first_vs_second_named': split(picks, lambda p: p['rank'] == 1),
                'all': _group([p['y'] for p in picks]),
            },
            'shadow_top2floor': shadow(ledger)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--pin', action='store_true')
    ap.add_argument('--run', action='store_true', help='the one registered look')
    args = ap.parse_args(argv)
    if args.run:
        out = run()
        SUMMARY.write_text(json.dumps(out, indent=1) + '\n')
        print(json.dumps({'status': out['verdict']['status'], 'scored': out['scored'],
                          'sessions': out['sessions'], 'diff': out['verdict']['diff'],
                          't': out['verdict']['t'], 'control_t': out['verdict']['control']['t']},
                         indent=1))
        return 0
    if not args.pin:
        ap.error('give --pin or --run')
    out = pin()
    PIN.write_text(json.dumps(out, indent=1) + '\n')
    ps = out['positions']
    print(json.dumps({'positions': len(ps), 'sessions': len({p['session'] for p in ps}),
                      'kept': sum(p['kept'] for p in ps), 'dropped': sum(not p['kept'] for p in ps),
                      'not_on_table': sum(not p['on_table'] for p in ps),
                      'sessions_without_tally': out['sessions_without_tally']}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
