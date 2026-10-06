#!/usr/bin/env python3
"""Day-126 registered replay: DeepSeek single-shot vs DeepSeek with the research
round, on the 59 cached day-117 pools (PREREGISTER_day126_research.md).

    python replay_research.py        # resumable; answers cached per session and arm

Both arms: today's prompt, the same pool, asked as of 09:00 on the session.
Scored on FMP 5-minute bars, 09:40-bar close → 15:55-bar close, signed.
Bar (registered, point estimate): research mean − single-shot mean ≥ −0.30%.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import deepseek_opportunities as O
import fmp_client as F
import replay_fmp_analyst as R

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
POOLS = ROOT/'.rb-state'/'replay'/'pools'
OUT_DIR = ROOT/'.rb-state'/'replay'/'research'
SUMMARY = ROOT/'data'/'replay_day126_research.json'
BAR = -0.30


def answer(session, arm):
    path = OUT_DIR/f'{session}_{arm}.json'
    if path.exists():
        return json.loads(path.read_text())
    p = json.loads((POOLS/f'{session}.json').read_text())
    now = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(9, 0), tzinfo=ET)
    out = O.rank(p['candidates'], macro=p['macro'] or None, now=now,
                 research='replay' if arm == 'research' else False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=str))
    return out


_bars = {}


def realized(session, ticker, side):
    key = (ticker, session)
    if key not in _bars:
        try:
            s = R.sessions(F.get('historical-chart/5min', symbol=ticker, **{'from': session, 'to': session}))
            _bars[key] = s.get(session)
        except Exception:
            _bars[key] = None
    b = _bars[key]
    if not b:
        return None
    r = 100 * (b['close'] / b['c0945'] - 1)
    return r if side == 'LONG' else -r


def picks(ans):
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for p in ans.get(key) or []:
            yield side, p['ticker']


def clustered_mean(rows):
    """rows: [(session, value)] → (mean, se)."""
    n = len(rows)
    if n < 2:
        return (rows[0][1] if rows else None), None
    m = sum(v for _, v in rows) / n
    g = {}
    for s, v in rows:
        g[s] = g.get(s, 0.0) + (v - m)
    G = len(g)
    var = sum(x * x for x in g.values()) / n ** 2 * (G / (G - 1) if G > 1 else 1)
    return m, math.sqrt(var)


def main():
    F.load_key()
    import prepare_deepseek
    prepare_deepseek.load_private_key(ROOT/'.rb-state')
    sessions = sorted(p.stem for p in POOLS.glob('*.json'))
    jobs = [(s, arm) for s in sessions for arm in ('single', 'research')]
    with cf.ThreadPoolExecutor(6) as pool:
        answers = dict(zip(jobs, pool.map(lambda j: answer(*j), jobs)))
    arms = {'single': [], 'research': []}
    calls, failed, unavailable = [], 0, {'single': 0, 'research': 0}
    for (s, arm), ans in answers.items():
        if ans.get('status') == 'UNAVAILABLE':
            unavailable[arm] += 1
            continue
        if arm == 'research':
            meta = ans.get('research') or {}
            calls.append(meta.get('calls', 0))
            failed += bool(meta.get('failed'))
        for side, t in picks(ans):
            r = realized(s, t, side)
            if r is not None:
                arms[arm].append((s, r))
    res = {}
    for arm, rows in arms.items():
        m, se = clustered_mean(rows)
        res[arm] = {'picks': len(rows), 'sessions_with_picks': len({s for s, _ in rows}),
                    'mean_pct': None if m is None else round(m, 4),
                    'se': None if se is None else round(se, 4),
                    'hit': round(sum(1 for _, v in rows if v > 0) / len(rows), 3) if rows else None}
    diff = res['research']['mean_pct'] - res['single']['mean_pct']
    se = math.sqrt(res['research']['se'] ** 2 + res['single']['se'] ** 2)
    summary = {'registration': 'PREREGISTER_day126_research.md', 'sessions': len(sessions),
               'single': res['single'], 'research': res['research'],
               'difference_pct': round(diff, 4),
               'difference_95ci': [round(diff - 1.96 * se, 3), round(diff + 1.96 * se, 3)],
               'bar': BAR, 'verdict': 'PASS (no worse)' if diff >= BAR else 'FAIL',
               'research_calls_mean': round(sum(calls) / len(calls), 2) if calls else 0,
               'research_failed_sessions': failed, 'unavailable': unavailable}
    SUMMARY.write_text(json.dumps(summary, indent=1) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    sys.exit(main())
