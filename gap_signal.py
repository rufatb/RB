#!/usr/bin/env python3
"""GAP SIGNAL — an extra section, run beside the desks (owner, 2026-09-29).

The rule is the one day-113 registered and rejected as #42 (t = 2.63 against a
registered 3.0): on the TSX-21, a stock whose opening gap is at least one
normal day's move (|gap| / sd of its last 20 daily returns >= 1) is bet to
CONTINUE in the gap's direction until the close. Nothing here is tuned.

Its ten-year record, stated per trade because that is what a position earns:
3,642 signals, right 48.7%, +0.03% per trade before costs (+0.14% when each
day's signals are averaged first — the figure day-113 reported). Last twelve
months: 311 signals, right 44%, −0.07%. That is NOT better than a coin flip per
trade, and the section says so every day. It runs because the owner is testing
every section in parallel, forward, from the email.

    python gap_signal.py --stage     # pre-open: each name's sd20 and prior close
    python gap_signal.py --score     # evening: fill today's results

The live check needs only the engine's own measured opening gap
(`factor_candidates`, 09:46) and the staged sd20. Recorded in
`data/gap_calls.csv` and scored two ways: from the 09:30 open (the study's
contract) and from the 09:45 bar close (what a reader of the 09:50 email can
still get).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'gap_calls.csv'
INPUTS = 'gap_inputs.json'
THRESHOLD = 1.0
SD_WINDOW = 20
FIELDS = ('session', 'ticker', 'side', 'gap_pct', 'g', 'sd20', 'p945',
          'open', 'close', 'entry_945', 'r_open_pct', 'r_945_pct', 'scored_at')
HISTORY = {'signals': 3642, 'hit': 0.487, 'mean_trade_pct': 0.033, 'mean_session_pct': 0.139,
           'years': 10, 'last12_signals': 311, 'last12_hit': 0.44, 'last12_mean_pct': -0.07}


def _universe():
    import yaml
    return list(yaml.safe_load((ROOT / 'config.yaml').read_text())['scan']['universe'])


def _daily(ticker):
    from adapters import YahooDirectAdapter
    a = YahooDirectAdapter(exchange_tz='America/Toronto')
    return a._bars_df(a._chart(ticker, '1d', '3mo')).dropna(subset=['Close'])


def inputs_for(frame, today):
    """sd20 of the last 20 close-to-close % returns and the last close, from
    sessions BEFORE `today` only. None when there are fewer than 21 closes."""
    closes = [float(c) for i, c in zip(frame.index, frame['Close']) if i.date() < today]
    if len(closes) < SD_WINDOW + 1:
        return None
    rets = [(b / a - 1) * 100 for a, b in zip(closes[-SD_WINDOW - 1:-1], closes[-SD_WINDOW:])]
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    last = [i.date() for i in frame.index if i.date() < today][-1]
    return {'sd20': sd, 'prior_close': closes[-1], 'prior_date': last.isoformat()}


def stage(state_dir, now=None, *, daily=_daily):
    now = now or dt.datetime.now(ET)
    names, failed = {}, {}
    for t in _universe():
        try:
            row = inputs_for(daily(t), now.date())
            if row:
                names[t] = row
            else:
                failed[t] = 'fewer than 21 daily closes'
        except Exception as exc:          # counted and shown, never swallowed
            failed[t] = type(exc).__name__
    out = {'session': now.date().isoformat(), 'staged_at': now.isoformat(),
           'names': names, 'failed': failed}
    path = Path(state_dir) / INPUTS
    path.write_text(json.dumps(out, indent=1))
    return out


def section(state_dir, now, res, path=LEDGER):
    """The section for today's report, from staged sd20 and the engine's gaps.
    Its record line is frozen into the section; renderers never read the ledger."""
    out = _section(state_dir, now, res)
    out['record'] = record_line(path)
    return out


def _section(state_dir, now, res):
    try:
        staged = json.loads((Path(state_dir) / INPUTS).read_text())
    except (OSError, ValueError):
        return {'status': 'UNAVAILABLE', 'reason': 'normal daily moves were not staged this morning',
                'picks': []}
    if staged.get('session') != now.date().isoformat():
        return {'status': 'UNAVAILABLE', 'reason': 'the staged daily moves are not today\'s', 'picks': []}
    cands = (res or {}).get('factor_candidates') or []
    if not cands:
        return {'status': 'UNAVAILABLE', 'picks': [],
                'reason': 'the engine measured no opening gaps this morning'}
    picks, checked = [], 0
    for c in cands:
        s = staged['names'].get(c.get('t'))
        gap = c.get('gap')
        if not s or not isinstance(gap, (int, float)) or not s['sd20']:
            continue
        checked += 1
        g = gap / s['sd20']
        if abs(g) >= THRESHOLD:
            picks.append({'ticker': c['t'], 'side': 'LONG' if g > 0 else 'SHORT',
                          'gap_pct': round(gap, 3), 'g': round(g, 2), 'sd20': round(s['sd20'], 3),
                          'p945': c.get('p945')})
    picks.sort(key=lambda p: -abs(p['g']))
    return {'status': 'READY', 'picks': picks, 'checked': checked,
            'reason': None if picks else f'no gap reached one normal day\'s move ({checked} names checked)'}


# ── record and score ────────────────────────────────────────────────────────

def read(path=LEDGER):
    path = Path(path)
    return list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []


def _write(rows, path):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore')
    w.writeheader()
    for r in sorted(rows, key=lambda r: (r['session'], r['ticker'])):
        w.writerow({k: '' if r.get(k) is None else r.get(k) for k in FIELDS})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(out.getvalue())


def record(report, path=LEDGER):
    """Append today's signals from a frozen report; never rewrites a row."""
    sec = (report.get('intraday') or {}).get('gap_signal') or {}
    rows = read(path)
    seen = {(r['session'], r['ticker']) for r in rows}
    new = [{'session': report['session'], **{k: p.get(k) for k in
            ('ticker', 'side', 'gap_pct', 'g', 'sd20', 'p945')}}
           for p in sec.get('picks') or [] if (report['session'], p['ticker']) not in seen]
    if new:
        _write(rows + new, path)
    return len(new)


def score_one(row, bars):
    """r from the first bar's open and from the 09:40 bar's close, to 15:55's close."""
    day = dt.date.fromisoformat(row['session'])
    f = bars[[i.date() == day for i in bars.index]]
    times = [i.time() for i in f.index]
    if dt.time(9, 30) not in times or dt.time(9, 40) not in times or dt.time(15, 55) not in times:
        return None
    o = float(f['Open'].iloc[times.index(dt.time(9, 30))])
    e = float(f['Close'].iloc[times.index(dt.time(9, 40))])
    c = float(f['Close'].iloc[times.index(dt.time(15, 55))])
    sign = 1 if row['side'] == 'LONG' else -1
    return {'open': round(o, 4), 'entry_945': round(e, 4), 'close': round(c, 4),
            'r_open_pct': round(sign * (c / o - 1) * 100, 4),
            'r_945_pct': round(sign * (c / e - 1) * 100, 4)}


def score(path=LEDGER, *, now=None, bars_for=None):
    import model_picks
    now = now or dt.datetime.now(ET)
    bars_for = bars_for or model_picks._yahoo_bars
    rows, cache, n = read(path), {}, 0
    for r in rows:
        if r.get('scored_at'):
            continue
        d = dt.date.fromisoformat(r['session'])
        if d > now.date() or (d == now.date() and now.time() < dt.time(16, 5)):
            continue
        if r['ticker'] not in cache:
            try:
                cache[r['ticker']] = bars_for(r['ticker'])
            except Exception:
                cache[r['ticker']] = None
        if cache[r['ticker']] is None:
            continue
        res = score_one(r, cache[r['ticker']])
        if res:
            r.update(res, scored_at=now.isoformat())
            n += 1
    if n:
        _write(rows, path)
    return n


def record_line(path=LEDGER):
    rows = [r for r in read(path) if r.get('scored_at')]
    hist = (f"10-year record: {HISTORY['signals']:,} signals, right {HISTORY['hit']:.1%}, "
            f"{HISTORY['mean_trade_pct']:+.2f}% per trade before costs; last 12 months "
            f"{HISTORY['last12_hit']:.0%}, {HISTORY['last12_mean_pct']:+.2f}%. "
            'Not better than a coin flip per trade.')
    if not rows:
        return hist + ' Live record: none scored yet (recording began 2026-09-29).'
    def stat(key):
        v = [float(r[key]) for r in rows if r.get(key) not in (None, '')]
        return (sum(x > 0 for x in v), len(v), sum(v) / len(v)) if v else (0, 0, 0.0)
    ho, no, mo = stat('r_open_pct')
    h9, n9, m9 = stat('r_945_pct')
    return (hist + f' Live: from the open {ho}/{no} right, {mo:+.2f}% per trade; '
            f'from 09:45 {h9}/{n9}, {m9:+.2f}%.')


def lines(sec, concise=False):
    """`concise` is the email (owner, 2026-10-03: no needless warnings or
    accuracy text there). The full report keeps the record line every day."""
    if not sec:
        return []
    if concise:
        out = ['', '## Part 3 — Gap signal (a separate test, not a desk)',
               'A TSX-21 stock that opened more than one normal day\'s move from its close; '
               'the bet is that it keeps going to the close.']
    else:
        out = ['', '## Part 3 — Gap signal (a separate test, not a desk)',
               'Rule: a TSX-21 stock that opens more than one normal day\'s move away from its '
               'close is bet to keep going until the close. Enter at the open; 09:46 prices shown.',
               sec.get('record') or '']
    if sec.get('status') != 'READY':
        return out + [f"Unavailable today — {sec.get('reason')}."]
    if not sec.get('picks'):
        return out + [f"No signal today: {sec.get('reason')}."]
    out += ['', '| Pick | Gap | Gap in normal days | 09:46 price |', '|---|---:|---:|---:|']
    for p in sec['picks']:
        px = f"{p['p945']:.2f}" if isinstance(p.get('p945'), (int, float)) else '—'
        out.append(f"| {p['side']} {p['ticker']} | {p['gap_pct']:+.2f}% | {p['g']:+.1f} | {px} |")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--stage', action='store_true')
    p.add_argument('--score', action='store_true')
    p.add_argument('--state-dir', default='.rb-state')
    a = p.parse_args(argv)
    if a.stage:
        out = stage(a.state_dir)
        print(json.dumps({'staged': len(out['names']), 'failed': out['failed']}))
        return 0 if out['names'] else 1
    if a.score:
        print(json.dumps({'scored': score()}))
        return 0
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
