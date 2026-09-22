#!/usr/bin/env python3
"""The models' track record: every pick recorded, every pick scored.

WHY THIS EXISTS. Every morning the report says of DeepSeek and Jev: "no track
record, never scored against an outcome". That was true, and it would have
stayed true forever, because nothing recorded their picks anywhere that
survived the container. Two models have been asked the owner's question every
day since 2026-09-17, and not one answer has ever been checked.

This keeps `data/model_picks.csv`, append-only, and scores each pick against
its own session from five-minute bars:

    entry  close of the bar stamped 09:40 — the completed 09:45 bar, the same
           reference the engine's own board uses
    exit   close of the bar stamped 15:55 — the session close
    r      signed: (exit/entry - 1) for a LONG, the negative for a SHORT
    hit    r > 0
    invalidated  for a pick carrying `invalid_at`: did the session trade
                 through its own stated level (below for LONG, above for SHORT)?

WHAT THIS IS NOT. It is a proxy — no spread, no fill, no cost — exactly like
the engine's legacy official-close proxy, and it is labelled that way wherever
it is printed. A handful of sessions resolves nothing: the scorecard prints its
own sample size and interval beside the rate, every time (house rule 8).

Forced Jev picks are recorded and scored SEPARATELY from selected ones. They
answer a different question, and pooling them would make the gate's abstentions
invisible in the record.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'model_picks.csv'
FIELDS = ('session', 'model', 'kind', 'side', 'ticker', 'confidence', 'abstain_probability',
          'invalid_at', 'prompt_version', 'source', 'entry', 'exit', 'r_pct', 'hit',
          'invalidated', 'scored_at')
KEY = ('session', 'model', 'kind', 'side', 'ticker')
ENTRY_BAR, EXIT_BAR = dt.time(9, 40), dt.time(15, 55)


# ── recording ───────────────────────────────────────────────────────────────

def rows_from_report(report, source='published_report'):
    """Every model pick in a frozen report, one row each. Pure."""
    session = report['session']
    intra = report.get('intraday') or {}
    out = []

    def add(model, kind, side, pick, **extra):
        if not isinstance(pick, dict) or not isinstance(pick.get('ticker'), str):
            return
        out.append({'session': session, 'model': model, 'kind': kind, 'side': side,
                    'ticker': pick['ticker'],
                    'confidence': pick.get('confidence', pick.get('probability')),
                    'abstain_probability': pick.get('abstain_probability',
                                                    pick.get('gated_abstain_probability')),
                    'invalid_at': pick.get('invalid_at'), 'source': source, **extra})

    # THE ENGINE ON THE SAME YARDSTICK. Its own ledger scores against the
    # official close; recording its board here too lets the leaderboard compare
    # every source with one scorer, one entry bar and one exit bar.
    for leg in intra.get('legs') or []:
        if leg.get('side') in ('LONG', 'SHORT'):
            add('engine', 'board', leg['side'], {'ticker': leg.get('ticker'),
                                                 'confidence': leg.get('p_sided')})
    ds = intra.get('opportunities') or {}
    if ds.get('status') in ('READY', 'NO_OPPORTUNITY'):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in ds.get(key) or []:
                add('deepseek', 'selected', side, pick, prompt_version=ds.get('prompt_version'))
    jev = intra.get('jev') or {}
    if jev.get('status') in ('READY', 'NO_OPPORTUNITY'):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in jev.get(key) or []:
                add('jev', 'selected', side, pick)
        for side in ('LONG', 'SHORT'):
            add('jev', 'forced', side, jev.get('forced_' + side.lower()))
    return out


def read(path=LEDGER):
    path = Path(path)
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text())))


def write(rows, path=LEDGER):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore')
    writer.writeheader()
    for row in sorted(rows, key=lambda r: tuple(str(r.get(k) or '') for k in KEY)):
        writer.writerow({k: _cell(row.get(k)) for k in FIELDS})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(out.getvalue())
    tmp.replace(path)


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float):
        return f'{value:.6g}'
    return str(value)


def _key(row):
    return tuple(str(row.get(k) or '') for k in KEY)


def append(new_rows, path=LEDGER):
    """Append-only. A recorded pick is never rewritten by a later record —
    a second publication of the same session cannot change what was picked."""
    existing = read(path)
    seen = {_key(r) for r in existing}
    added = [r for r in new_rows if _key(r) not in seen]
    if added:
        write(existing + added, path)
    return len(added)


# ── scoring ─────────────────────────────────────────────────────────────────

def _yahoo_bars(ticker):
    from adapters import YahooDirectAdapter
    adapter = YahooDirectAdapter(timeout=14)
    return adapter._bars_df(adapter._chart(ticker, '5m', '60d'))


def score_one(row, bars):
    """Score one pick against its session. Returns the fields to add, or None
    when the session's bars are not all there (never a partial score)."""
    day = dt.date.fromisoformat(row['session'])
    frame = bars[[ts.date() == day for ts in bars.index]]
    if frame.empty:
        return None
    local = frame.tz_convert(ET)
    times = [ts.time() for ts in local.index]
    if ENTRY_BAR not in times or EXIT_BAR not in times:
        return None
    entry = float(local['Close'].iloc[times.index(ENTRY_BAR)])
    exit_ = float(local['Close'].iloc[times.index(EXIT_BAR)])
    if not (math.isfinite(entry) and math.isfinite(exit_)) or entry <= 0:
        return None
    sign = 1 if row['side'] == 'LONG' else -1
    r = sign * (exit_ / entry - 1) * 100
    after = local[[ENTRY_BAR < t <= EXIT_BAR for t in times]]
    invalidated = None
    level = _float(row.get('invalid_at'))
    if level is not None and not after.empty:
        invalidated = (float(after['Low'].min()) < level if row['side'] == 'LONG'
                       else float(after['High'].max()) > level)
    return {'entry': round(entry, 4), 'exit': round(exit_, 4), 'r_pct': round(r, 4),
            'hit': r > 0, 'invalidated': invalidated}


def score(path=LEDGER, *, now=None, bars_for=None):
    """Score every unscored pick whose session has closed. Returns a count."""
    now = now or dt.datetime.now(ET)
    bars_for = bars_for or _yahoo_bars
    rows = read(path)
    cache, scored = {}, 0
    for row in rows:
        if row.get('scored_at'):
            continue
        session = dt.date.fromisoformat(row['session'])
        if session > now.date() or (session == now.date() and now.time() < dt.time(16, 5)):
            continue
        ticker = row['ticker']
        if ticker not in cache:
            try:
                cache[ticker] = bars_for(ticker)
            except Exception:
                cache[ticker] = None
        if cache[ticker] is None:
            continue
        result = score_one(row, cache[ticker])
        if result:
            row.update({k: _cell(v) for k, v in result.items()}, scored_at=now.isoformat())
            scored += 1
    if scored:
        write(rows, path)
    return scored


def _float(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ── the scorecard printed beside the picks ──────────────────────────────────

def scorecard(rows=None):
    """Per (model, kind): picks, hits, rate, mean r, sessions, 95% interval."""
    rows = read() if rows is None else rows
    out = {}
    for row in rows:
        if not row.get('scored_at'):
            continue
        key = f"{row['model']}_{row['kind']}"
        entry = out.setdefault(key, {'n': 0, 'hits': 0, 'r': [], 'sessions': set(),
                                     'invalid_n': 0, 'invalidated': 0})
        entry['n'] += 1
        entry['hits'] += row.get('hit') == '1'
        r = _float(row.get('r_pct'))
        if r is not None:
            entry['r'].append(r)
        entry['sessions'].add(row['session'])
        if row.get('invalidated') in ('0', '1'):
            entry['invalid_n'] += 1
            entry['invalidated'] += row['invalidated'] == '1'
    result = {}
    for key, e in out.items():
        n = e['n']
        rate = e['hits'] / n if n else None
        # Wilson interval: honest at small n, never outside [0, 1].
        z = 1.96
        lo = hi = None
        if n:
            centre = (rate + z*z/(2*n)) / (1 + z*z/n)
            half = z*math.sqrt(rate*(1-rate)/n + z*z/(4*n*n)) / (1 + z*z/n)
            lo, hi = max(0.0, centre-half), min(1.0, centre+half)
        result[key] = {'picks': n, 'hits': e['hits'], 'rate': rate,
                       'ci95': [lo, hi] if n else None,
                       'mean_r_pct': (sum(e['r'])/len(e['r'])) if e['r'] else None,
                       'sessions': len(e['sessions']),
                       'invalidation_checked': e['invalid_n'],
                       'invalidated': e['invalidated'],
                       'label': 'proxy: 09:45 bar close to session close; no spread, fill or cost'}
    return result


def scorecard_line(card, model_kind, name):
    c = (card or {}).get(model_kind)
    if not c or not c['picks']:
        return (f"{name} track record: no pick has been scored yet — recording began "
                "2026-09-22; the first scores arrive after the next close.")
    lo, hi = c['ci95']
    line = (f"{name} track record: {c['hits']}/{c['picks']} picks right ({c['rate']:.0%}) over "
            f"{c['sessions']} session(s), mean {c['mean_r_pct']:+.2f}% per pick; 95% interval "
            f"{lo:.0%}–{hi:.0%}")
    line += (' — contains 50%, so not distinguishable from a coin flip.' if lo <= 0.5 <= hi
             else ' — excludes 50%, on a sample this small still NOT evidence of skill.')
    if c['invalidation_checked']:
        line += (f" Its own invalidation level was hit on {c['invalidated']} of "
                 f"{c['invalidation_checked']}.")
    return line + ' Proxy: 09:45 bar to session close, no costs.'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--record-report', metavar='REPORT_JSON',
                   help='append every model pick in this frozen report')
    p.add_argument('--source', default='published_report')
    p.add_argument('--score', action='store_true', help='score every closed, unscored pick')
    p.add_argument('--ledger', default=str(LEDGER))
    a = p.parse_args(argv)
    out = {}
    if a.record_report:
        report = json.loads(Path(a.record_report).read_text())
        out['recorded'] = append(rows_from_report(report, a.source), a.ledger)
    if a.score:
        out['scored'] = score(a.ledger)
    out['scorecard'] = scorecard(read(a.ledger))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
