#!/usr/bin/env python3
"""POST-EARNINGS DRIFT — an extra section, run beside the desks (owner, 2026-09-29).

Post-earnings-announcement drift is one of the most documented patterns in
equity research: after a results surprise, prices tend to keep moving the same
way for days. It has NOT been shown here. On the three months of wire archive
available on 2026-09-29 the rule below produced 24 signals, right 50%: nothing
either way. This is a FORWARD test, registered in PREREGISTER_day119_extra.md.

The rule, fixed now:
  event     a results release on the Canadian wire (data/newswire, newswire.py)
            naming a TSX name in the pool, the TSX-21 or the configured universe
  reaction  the first session that could trade it (released before 09:30 → that
            session; otherwise the next one): close vs the prior close
  signal    |reaction| ≥ one normal day's move (sd of the 20 prior daily returns)
  bet       the reaction's direction, entered the NEXT session at the 09:45 bar
            close (the email's time), held five sessions, out at the fifth close

    python pead.py --stage    # pre-open: today's new signals; appends data/pead_calls.csv
    python pead.py --score    # evening: fill every position whose five sessions are done
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'pead_calls.csv'
SIGNALS = 'pead_signals.json'
HOLD = 5
THRESHOLD = 1.0
LOOKBACK_DAYS = 7
FIELDS = ('entry_session', 'ticker', 'side', 'react_pct', 'g', 'reaction_session',
          'release_at', 'release_url', 'title', 'entry', 'exit_session', 'exit', 'r_pct',
          'scored_at')

RESULTS = re.compile(
    r'\b(reports?|reported|announces?|delivers?|posts?|releases?)\b.{0,80}'
    r'\b(results|earnings)\b', re.I)
NOTICE = re.compile(
    r'\b(to (report|release|announce|host|issue|be announced)|will (report|release|announce|host)'
    r'|notice of|conference call|webcast|media advisory|timing|voting results|annual (general )?'
    r'meeting|shareholder meeting|preferred share|pre-announces|production|catastrophe)\b', re.I)


def is_results(title):
    return bool(RESULTS.search(title or '')) and not NOTICE.search(title or '')


def _universe():
    import yaml
    import factor_pool_policy as P
    return set(P.TICKERS) | set(yaml.safe_load((ROOT / 'config.yaml').read_text())['scan']['universe'])


def _daily(ticker):
    from adapters import YahooDirectAdapter
    a = YahooDirectAdapter(exchange_tz='America/Toronto')
    return a._bars_df(a._chart(ticker, '1d', '3mo')).dropna(subset=['Close'])


def reaction(frame, release_at, today):
    """(reaction session, reaction %, g) from daily bars before `today`, or None."""
    days = [i.date() for i in frame.index if i.date() < today]
    closes = [float(c) for i, c in zip(frame.index, frame['Close']) if i.date() < today]
    at = release_at.astimezone(ET)
    later = [k for k, d in enumerate(days)
             if d > at.date() or (d == at.date() and at.time() < dt.time(9, 30))]
    if not later:
        return None
    k = later[0]
    if k < 21:
        return None
    rets = [(b / a - 1) * 100 for a, b in zip(closes[k - 21:k - 1], closes[k - 20:k])]
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    react = (closes[k] / closes[k - 1] - 1) * 100
    return days[k], react, (react / sd if sd else 0.0)


def stage(state_dir, now=None, *, daily=_daily, archive=None, path=LEDGER):
    """Today's NEW signals: events whose reaction session was the last session
    before today. Appended to the ledger (never rewritten); the section also
    lists positions still inside their five sessions."""
    import newswire
    now = now or dt.datetime.now(ET)
    uni = _universe()
    since = now - dt.timedelta(days=LOOKBACK_DAYS)
    events, failed, new = [], {}, []
    for r in newswire.read(archive, since=since.date()):
        names = [t for t in r.get('tickers') or [] if t in uni]
        if not names or not is_results(r['title']):
            continue
        events.append((names[0], r))
    cache = {}
    for t, r in events:
        try:
            if t not in cache:
                cache[t] = daily(t)
            f = cache[t]
            got = reaction(f, dt.datetime.fromisoformat(r['published_at']), now.date())
        except Exception as exc:          # counted and shown
            failed[t] = type(exc).__name__
            continue
        if not got:
            continue
        session, react, g = got
        last = max(i.date() for i in f.index if i.date() < now.date())
        if session != last or abs(g) < THRESHOLD:
            continue
        new.append({'entry_session': now.date().isoformat(), 'ticker': t,
                    'side': 'LONG' if react > 0 else 'SHORT', 'react_pct': round(react, 3),
                    'g': round(g, 2), 'reaction_session': session.isoformat(),
                    'release_at': r['published_at'], 'release_url': r['url'],
                    'title': r['title'][:200]})
    rows = read(path)
    seen = {(x['entry_session'], x['ticker']) for x in rows}
    added = [x for x in new if (x['entry_session'], x['ticker']) not in seen]
    if added:
        _write(rows + added, path)
    out = {'session': now.date().isoformat(), 'staged_at': now.isoformat(),
           'events_checked': len(events), 'new': new, 'failed': failed}
    (Path(state_dir) / SIGNALS).write_text(json.dumps(out, indent=1))
    return out


def section(state_dir, now, path=LEDGER):
    """New signals staged this morning, plus positions still being held."""
    try:
        staged = json.loads((Path(state_dir) / SIGNALS).read_text())
    except (OSError, ValueError):
        staged = None
    fresh = staged if staged and staged.get('session') == now.date().isoformat() else None
    held = [r for r in read(path) if not r.get('scored_at')
            and r['entry_session'] < now.date().isoformat()]
    return {'status': 'READY' if fresh else 'UNAVAILABLE', 'record': record_line(path),
            'reason': None if fresh else 'today\'s earnings events were not staged this morning',
            'new': (fresh or {}).get('new') or [], 'events_checked': (fresh or {}).get('events_checked'),
            'held': [{k: r.get(k) for k in ('entry_session', 'ticker', 'side', 'react_pct', 'title')}
                     for r in held]}


# ── record and score ────────────────────────────────────────────────────────

def read(path=LEDGER):
    path = Path(path)
    return list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []


def _write(rows, path):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore')
    w.writeheader()
    for r in sorted(rows, key=lambda r: (r['entry_session'], r['ticker'])):
        w.writerow({k: '' if r.get(k) is None else r.get(k) for k in FIELDS})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(out.getvalue())


def score_one(row, bars5, daily):
    """Entry: the 09:40 bar close on the entry session. Exit: the daily close of
    the HOLD-th session counting the entry session as the first."""
    day = dt.date.fromisoformat(row['entry_session'])
    f = bars5[[i.date() == day for i in bars5.index]]
    times = [i.time() for i in f.index]
    if dt.time(9, 40) not in times:
        return None
    entry = float(f['Close'].iloc[times.index(dt.time(9, 40))])
    days = [i.date() for i in daily.index if i.date() >= day]
    if len(days) < HOLD:
        return None
    exit_day = days[HOLD - 1]
    exit_ = float(daily['Close'].iloc[[i.date() for i in daily.index].index(exit_day)])
    sign = 1 if row['side'] == 'LONG' else -1
    return {'entry': round(entry, 4), 'exit_session': exit_day.isoformat(), 'exit': round(exit_, 4),
            'r_pct': round(sign * (exit_ / entry - 1) * 100, 4)}


def score(path=LEDGER, *, now=None, bars_for=None, daily=_daily):
    import model_picks
    now = now or dt.datetime.now(ET)
    bars_for = bars_for or model_picks._yahoo_bars
    rows, n = read(path), 0
    for r in rows:
        if r.get('scored_at'):
            continue
        try:
            res = score_one(r, bars_for(r['ticker']), daily(r['ticker']))
        except Exception:
            res = None
        if res and (res['exit_session'] < now.date().isoformat()
                    or (res['exit_session'] == now.date().isoformat() and now.time() >= dt.time(16, 5))):
            r.update(res, scored_at=now.isoformat())
            n += 1
    if n:
        _write(rows, path)
    return n


def record_line(path=LEDGER):
    done = [r for r in read(path) if r.get('scored_at')]
    base = ('Backtest on the 3 months of archive: 24 signals, right 50% — too few to say '
            'anything. Documented elsewhere, unproven here; a forward test.')
    if not done:
        return base + ' Live record: none completed yet (recording began 2026-09-29).'
    v = [float(r['r_pct']) for r in done]
    return base + f' Live: {sum(x > 0 for x in v)}/{len(v)} right, {sum(v)/len(v):+.2f}% per 5-day hold.'


def lines(sec):
    if not sec:
        return []
    out = ['', '## Part 4 — Post-earnings drift (a separate test, 5-day hold)',
           'Rule: after a company\'s results release, if the stock moved more than one normal '
           'day in reaction, bet it keeps going: enter at today\'s 09:45 price, hold five sessions.',
           sec.get('record') or '']
    if sec.get('status') != 'READY':
        out.append(f"Unavailable today — {sec.get('reason')}.")
    elif sec.get('new'):
        out += ['', '| New today | Reaction | In normal days | Release |', '|---|---:|---:|---|']
        for p in sec['new']:
            out.append(f"| {p['side']} {p['ticker']} | {p['react_pct']:+.2f}% | {p['g']:+.1f} | "
                       f"{str(p['title'])[:90].replace('|', '/')} |")
    else:
        out.append(f"No new signal today ({sec.get('events_checked') or 0} results releases in the "
                   'last week checked).')
    if sec.get('held'):
        out.append('Still holding: ' + ', '.join(f"{h['side']} {h['ticker']} (since {h['entry_session']})"
                                                 for h in sec['held']) + '.')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--stage', action='store_true')
    p.add_argument('--score', action='store_true')
    p.add_argument('--state-dir', default='.rb-state')
    a = p.parse_args(argv)
    if a.stage:
        out = stage(a.state_dir)
        print(json.dumps({'events_checked': out['events_checked'], 'new': len(out['new']),
                          'failed': out['failed']}))
        return 0
    if a.score:
        print(json.dumps({'scored': score()}))
        return 0
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
