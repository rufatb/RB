"""Day-154 (PREREGISTER_day154_floor_history.md): the day-150 quality floor,
applied to Claude's past council nominations.

Council lab item 16. This commit carries the population pin only: `--pin`
writes `data/floor_day154_positions.json` from the record's nominations and the
councils' final tallies. It reads no return. The run code is added in its own
commit, before it runs, next weekday.

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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--pin', action='store_true')
    args = ap.parse_args(argv)
    if not args.pin:
        ap.error('only --pin exists in this commit; the run code follows in its own commit')
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
