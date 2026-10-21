#!/usr/bin/env python3
"""Day-137, descriptive: what the council takes, against what it passes over.

The owner (2026-10-21): "the council is not selecting the best picks — identify
what it is." Every position on every frozen council table (from 2026-10-05, the
publications in reports.sqlite3) is scored on the record's yardstick — the
09:45 bar's close to the 15:55 bar's close, FMP five-minute bars — beside what
the rows said about the name that morning (factor_pool_history) and its sector
fund's move over the same window (exposure.position_exposure, beta 1).

Nothing here is a verdict: a dozen sessions resolve nothing. It shows what the
council's choices have in common, so the registered test can ask whether that
trait carries anything on the long history.

    python council_audit.py        # writes data/council_audit_day137.json
"""
from __future__ import annotations

import json
import sqlite3
import statistics as st
from pathlib import Path

import exposure
from replay_drift import Fetch

ROOT = Path(__file__).resolve().parent
DB = ROOT/'.rb-state'/'reports.sqlite3'
POOLS = ROOT/'.rb-state'/'factor_pool_history'
CACHE = ROOT/'.rb-state'/'council_audit_cache'
OUT = ROOT/'data'/'council_audit_day137.json'
FROM = '2026-10-05'
ENTRY, NOON, EXIT, OPEN = '09:40:00', '11:55:00', '15:55:00', '09:30:00'
MOVER = 1.0


def councils(db=DB, start=FROM):
    """[(session, frozen council)] with a tally, oldest first."""
    con = sqlite3.connect(db)
    out = []
    for session, body in con.execute('select session, body from reports order by session'):
        c = (json.loads(body).get('intraday') or {}).get('council')
        if session >= start and isinstance(c, dict) and (c.get('tally') or {}).get('rows'):
            out.append((session, c))
    return out


def rows_of(session, pools=POOLS):
    f = pools/session/'candidates.json'
    if not f.exists():
        return {}
    return {r['ticker']: r.get('technicals') or {} for r in json.loads(f.read_text())['candidates']}


def prices(fetch, ticker, session):
    """{'open', 'entry', 'noon', 'exit'} for one session, or None."""
    bars = fetch('historical-chart/5min', symbol=ticker, **{'from': session, 'to': session}) or []
    at = {b['date'].split(' ')[1]: b for b in bars if b.get('date', '').startswith(session)}
    if not all(t in at for t in (OPEN, ENTRY, NOON, EXIT)):
        return None
    return {'open': at[OPEN]['open'], 'entry': at[ENTRY]['close'], 'noon': at[NOON]['close'],
            'exit': at[EXIT]['close']}


def pct(a, b):
    return 100 * (b / a - 1)


def table(fetch, session, council, sectors):
    """Every position on one table, scored and described."""
    tech = rows_of(session)
    picks = set(council.get('picks') or [])
    by_id = {p['id']: p for p in council.get('positions') or []}
    tally = council['tally']['rows']
    out = []
    for rank, r in enumerate(tally, 1):
        p = by_id.get(r['id']) or {}
        sign = 1 if r['side'] == 'LONG' else -1
        x = prices(fetch, r['ticker'], session)
        etf = exposure.position_exposure(r['ticker'], sectors)['etf']
        e = prices(fetch, etf, session)
        m = prices(fetch, 'XIU.TO', session)
        t = tech.get(r['ticker']) or {}
        row = {'session': session, 'id': r['id'], 'ticker': r['ticker'], 'side': r['side'],
               'rank': rank, 'picked': r['id'] in picks, 'consensus': bool(r.get('consensus')),
               'endorse': len(r['endorse']), 'oppose': len(r['oppose']), 'seats': len(r['seats']),
               'members': len(council['tally'].get('members') or []),
               'proposers': [q['model'] + '/' + q['how'] for q in p.get('proposers') or []],
               'selected_by': sum(q['how'] == 'selected' for q in p.get('proposers') or []),
               'etf': etf}
        for k in ('atr_pct', 'move_atr', 'gap_atr', 'rsi', 'rel_sector_pct', 'sector_move_pct',
                  'range52_pos', 'sma50_pct', 'days_to_earnings', 'r0', 'rvol'):
            v = t.get(k)
            row[k] = round(float(v), 4) if isinstance(v, (int, float)) else None
        if x:
            row['r'] = round(sign * pct(x['entry'], x['exit']), 4)
            row['r_noon'] = round(sign * pct(x['entry'], x['noon']), 4)
            row['r_open_entry'] = round(sign * pct(x['open'], x['exit']), 4)
            if e:
                row['etf_part'] = round(sign * pct(e['entry'], e['exit']), 4)
                row['r_vs_etf'] = round(row['r'] - row['etf_part'], 4)
            if m:
                row['market_part'] = round(sign * pct(m['entry'], m['exit']), 4)
        out.append(row)
    return out


def traits(row):
    """What a position leans on, from the morning's rows (None when unknown)."""
    sign = 1 if row['side'] == 'LONG' else -1
    m, rel, rsi = row.get('move_atr'), row.get('rel_sector_pct'), row.get('rsi')
    return {
        'follows_big_move': None if m is None else abs(m) >= MOVER and sign * m > 0,
        'follows_rel_sector': None if rel is None else sign * rel > 0,
        'follows_last_move': None if m is None else sign * m > 0,
        'rsi_extreme': None if rsi is None else (rsi >= 70 or rsi <= 30),
        'earnings_within_5': (None if row.get('days_to_earnings') is None
                              else 0 <= row['days_to_earnings'] <= 5),
    }


def group(rows):
    def mean(k):
        xs = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        return round(st.mean(xs), 3) if xs else None
    scored = [r for r in rows if isinstance(r.get('r'), (int, float))]
    out = {'n': len(rows), 'scored': len(scored),
           'right': sum(r['r'] > 0 for r in scored),
           'mean_r': mean('r'), 'mean_r_noon': mean('r_noon'), 'mean_r_open_entry': mean('r_open_entry'),
           'mean_vs_etf': mean('r_vs_etf'), 'mean_etf_part': mean('etf_part'),
           'mean_abs_r': round(st.mean(abs(r['r']) for r in scored), 3) if scored else None,
           'mean_atr_pct': mean('atr_pct'),
           'mean_abs_move_atr': (round(st.mean(abs(r['move_atr']) for r in rows if r.get('move_atr') is not None), 3)
                                 if any(r.get('move_atr') is not None for r in rows) else None)}
    for k in ('follows_big_move', 'follows_rel_sector', 'follows_last_move', 'rsi_extreme',
              'earnings_within_5'):
        xs = [traits(r)[k] for r in rows if traits(r)[k] is not None]
        out['share_' + k] = round(sum(xs) / len(xs), 3) if xs else None
    return out


def main():
    fetch = Fetch(CACHE)
    sectors = exposure.load_sectors()
    every = []
    for session, council in councils():
        every += table(fetch, session, council, sectors)
    groups = {
        'all positions on the tables': every,
        'the council\'s picks (before the big-mover rule)': [r for r in every if r['picked']],
        'agreed (consensus) but not picked': [r for r in every if r['consensus'] and not r['picked']],
        'not agreed': [r for r in every if not r['consensus']],
        'endorsed by every member present': [r for r in every if r['endorse'] == r['members']],
        'objected to by at least one': [r for r in every if r['oppose'] >= 1],
    }
    summary = {k: group(v) for k, v in groups.items()}
    paired = []
    for s in sorted({r['session'] for r in every}):
        t = [r for r in every if r['session'] == s and isinstance(r.get('r'), (int, float))]
        p = [r for r in t if r['picked']]
        if p and len(t) > len(p):
            paired.append({'session': s, 'picked': round(st.mean(r['r'] for r in p), 3),
                           'table': round(st.mean(r['r'] for r in t), 3),
                           'best_on_table': max(t, key=lambda r: r['r'])['ticker']})
    out = {'sessions': sorted({r['session'] for r in every}), 'positions': every,
           'groups': summary, 'paired': paired, 'fetch_failures': fetch.failures}
    OUT.write_text(json.dumps(out, indent=1))
    for k, g in summary.items():
        print('%-48s %s' % (k, json.dumps(g)))
    for p in paired:
        print(p)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
