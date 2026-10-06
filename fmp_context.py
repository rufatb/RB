#!/usr/bin/env python3
"""FMP CONTEXT — what FMP adds to every model's morning brief (day-125).

Registered in PREREGISTER_day125_fmp.md. Staged before Claude's brief:

    python fmp_context.py --stage --state-dir .rb-state

Per name in the pool (one row each for Claude, DeepSeek, Gemini, Jev, the
debate and the council — the shared `deepseek_opportunities._row`):
  analyst_30d        rating CHANGES in the last 30 days, "date firm action from→to"
  analyst_consensus  "buy N / hold N / sell N" today
  last_report, eps_surprise_pct, next_report
Once per morning, in the macro block: events_today — Canada/US releases
08:00–16:00 ET, High or Medium impact.

The registered test (replay_fmp_analyst.py) found rating changes PRICED BY THE
OPEN; the prompt says so. Nothing here is a rule, a filter or a size. A failed
fetch costs these fields only, and the gaps say which.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import fmp_client as F

ET = ZoneInfo('America/New_York')
UTC = dt.timezone.utc
SNAPSHOT = 'fmp_context.json'
SCHEMA = 'day125-fmp-v1'
ANALYST_DAYS = 30
MAX_ACTIONS = 3
WORKERS = 8
EVENT_COUNTRIES = ('CA', 'US')
EVENT_IMPACT = ('High', 'Medium')
MAX_EVENTS = 12


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def analyst_fields(grades, consensus, today):
    out = {}
    since = (today - dt.timedelta(days=ANALYST_DAYS)).isoformat()
    changes = [g for g in grades or [] if isinstance(g, dict)
               and g.get('action') in ('upgrade', 'downgrade') and since <= str(g.get('date', '')) <= today.isoformat()]
    changes.sort(key=lambda g: g['date'], reverse=True)
    if changes:
        out['analyst_30d'] = ['%s %s %s %s→%s' % (g['date'], str(g.get('gradingCompany') or '?')[:28],
                                                 g['action'], str(g.get('previousGrade') or '?')[:20],
                                                 str(g.get('newGrade') or '?')[:20])
                              for g in changes[:MAX_ACTIONS]]
    c = (consensus or [None])[0] if isinstance(consensus, list) else None
    if isinstance(c, dict):
        buy = (c.get('strongBuy') or 0) + (c.get('buy') or 0)
        sell = (c.get('strongSell') or 0) + (c.get('sell') or 0)
        hold = c.get('hold') or 0
        if buy + hold + sell:
            out['analyst_consensus'] = 'buy %d / hold %d / sell %d' % (buy, hold, sell)
    return out


def earnings_fields(rows, today):
    out = {}
    rows = [r for r in rows or [] if isinstance(r, dict) and r.get('date')]
    done = sorted((r for r in rows if _num(r.get('epsActual')) and r['date'] <= today.isoformat()),
                  key=lambda r: r['date'], reverse=True)
    ahead = sorted((r for r in rows if r.get('epsActual') is None and r['date'] >= today.isoformat()),
                   key=lambda r: r['date'])
    if done:
        r = done[0]
        out['last_report'] = r['date']
        est = r.get('epsEstimated')
        if _num(est) and abs(est) >= 0.01:
            out['eps_surprise_pct'] = round(100 * (r['epsActual'] - est) / abs(est), 1)
    if ahead:
        out['next_report'] = ahead[0]['date']
    return out


def events_today(rows, today):
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or r.get('country') not in EVENT_COUNTRIES:
            continue
        if r.get('impact') not in EVENT_IMPACT:
            continue
        try:
            at = dt.datetime.strptime(str(r['date']), '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC).astimezone(ET)
        except (KeyError, ValueError):
            continue
        if at.date() != today or not dt.time(8, 0) <= at.time() <= dt.time(16, 0):
            continue
        est = r.get('estimate')
        prev = r.get('previous')
        out.append((at, '%s %s %s (%s)%s%s' % (
            at.strftime('%H:%M'), r['country'], str(r.get('event') or '?')[:60], r['impact'],
            ' est %s' % est if est is not None else '', ' prev %s' % prev if prev is not None else '')))
    return [s for _, s in sorted(out)][:MAX_EVENTS]


RATE_PER_SECOND = 9          # Premium allows 750 a minute; stay well under it


def _pool(root, now):
    """Exactly the names the brief will carry: the validated staged pool,
    filtered by the same `usable_candidates` every desk uses."""
    import yaml
    import deepseek_opportunities as O
    from factor_inputs import build_from_state
    cfg = yaml.safe_load(Path(__file__).with_name('config.yaml').read_text())
    payload = build_from_state(root, cfg, now)
    if not payload.get('candidates'):
        try:                     # the late-picks fallback stages a diagnostic pool
            payload = build_from_state(root, cfg, now, diagnostic=True)
        except Exception:        # not a diagnostic context: the empty pool stands
            pass
    return sorted({c['ticker'] for c in O.usable_candidates(payload.get('candidates') or [])})


def _throttled(get, per_second=RATE_PER_SECOND):
    import threading
    import time
    lock, last = threading.Lock(), [0.0]

    def call(path, **params):
        with lock:
            wait = last[0] + 1.0 / per_second - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            last[0] = time.monotonic()
        return get(path, **params)
    return call


def stage(state_dir, *, now=None, get=None, tickers=None):
    """Fetch, shape and seal fmp_context.json. Never raises past its own failures."""
    from build_biotech import write_atomic
    now = (now or dt.datetime.now(ET)).astimezone(ET)
    root = Path(state_dir)
    today = now.date()
    gaps, names = [], {}
    if get is None:
        try:
            key = F.load_key(root)
        except ValueError as exc:
            key = None
            gaps.append('FMP credential rejected (%s)' % exc)
        if not key:
            gaps.append('No FMP credential is staged; the brief carries no FMP fields.')
            out = {'schema': SCHEMA, 'session': today.isoformat(), 'prepared_at': now.isoformat(),
                   'status': 'UNAVAILABLE', 'names': {}, 'events_today': [], 'gaps': gaps}
            write_atomic(root/SNAPSHOT, out)
            return out
        get = _throttled(lambda path, **p: F.get(path, key, **p))
    try:
        tickers = tickers if tickers is not None else _pool(root, now)
    except Exception as exc:            # named below; the brief then carries no FMP fields
        tickers = []
        gaps.append('The candidate pool was not readable (%s).' % type(exc).__name__)
    failures = {}

    def one(t):
        fields = {}
        for name, call in (('grades', lambda: get('grades', symbol=t)),
                           ('consensus', lambda: get('grades-consensus', symbol=t)),
                           ('earnings', lambda: get('earnings', symbol=t, limit=8))):
            try:
                fields[name] = call()
            except Exception as exc:          # counted per name and endpoint
                failures.setdefault(str(exc)[:40] if isinstance(exc, ValueError) else type(exc).__name__, []).append(t)
                fields[name] = None
        row = {**analyst_fields(fields['grades'], fields['consensus'], today),
               **earnings_fields(fields['earnings'], today)}
        return t, row

    with cf.ThreadPoolExecutor(WORKERS) as pool:
        for t, row in pool.map(one, tickers):
            if row:
                names[t] = row
    for why, ts in sorted(failures.items()):
        gaps.append('FMP %s on %d call(s), e.g. %s' % (why, len(ts), ', '.join(sorted(set(ts))[:4])))
    try:
        events = events_today(get('economic-calendar', **{'from': (today - dt.timedelta(days=1)).isoformat(),
                                                           'to': (today + dt.timedelta(days=1)).isoformat()}),
                              today)
    except Exception as exc:
        events = []
        gaps.append('FMP economic calendar failed (%s).' % (str(exc)[:40] if isinstance(exc, ValueError)
                                                           else type(exc).__name__))
    out = {'schema': SCHEMA, 'session': today.isoformat(), 'prepared_at': now.isoformat(),
           'status': 'READY' if names or events else 'UNAVAILABLE', 'pool': len(tickers),
           'names': names, 'events_today': events, 'gaps': gaps,
           'counts': {'with_analyst_changes': sum(1 for r in names.values() if 'analyst_30d' in r),
                      'with_consensus': sum(1 for r in names.values() if 'analyst_consensus' in r),
                      'with_last_report': sum(1 for r in names.values() if 'last_report' in r),
                      'with_next_report': sum(1 for r in names.values() if 'next_report' in r),
                      'events_today': len(events)}}
    write_atomic(root/SNAPSHOT, out)
    return out


ROW_KEYS = ('analyst_30d', 'analyst_consensus', 'last_report', 'eps_surprise_pct', 'next_report')


def load(state_dir, now):
    """Today's context, revalidated; None when absent, stale or malformed."""
    try:
        obj = json.loads((Path(state_dir)/SNAPSHOT).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict) or obj.get('schema') != SCHEMA:
        return None
    if obj.get('session') != now.astimezone(ET).date().isoformat():
        return None
    names = {}
    for t, row in (obj.get('names') or {}).items():
        if not isinstance(row, dict):
            continue
        clean = {}
        for k in ROW_KEYS:
            v = row.get(k)
            if k == 'analyst_30d' and isinstance(v, list):
                clean[k] = [str(x)[:120] for x in v[:MAX_ACTIONS]]
            elif k == 'eps_surprise_pct' and _num(v):
                clean[k] = round(float(v), 1)
            elif isinstance(v, str):
                clean[k] = v[:40]
        if clean:
            names[str(t)] = clean
    events = [str(e)[:140] for e in (obj.get('events_today') or [])[:MAX_EVENTS]]
    return {'names': names, 'events_today': events, 'gaps': [str(g)[:160] for g in obj.get('gaps') or []]}


def attach(output, state_dir, now):
    """Put each name's FMP fields on its candidate (key 'fmp') and today's events
    at output['fmp_events']. The factor layer whitelists candidate keys and the
    macro block, so neither field can reach a strict validator."""
    ctx = load(state_dir, now)
    if ctx is None:
        return output
    for item in output.get('candidates') or []:
        if isinstance(item, dict) and item.get('ticker') in ctx['names']:
            item['fmp'] = ctx['names'][item['ticker']]
    output['fmp_events'] = ctx['events_today']
    return output


def with_events(payload):
    """The macro block a desk is asked with: the validated macro plus today's
    scheduled releases. A copy — the validated macro is never changed."""
    macro = dict(payload.get('macro') or {})
    if payload.get('fmp_events'):
        macro['events_today'] = list(payload['fmp_events'])
    return macro


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default=os.environ.get('RB_STATE_DIR', '.rb-state'))
    p.add_argument('--stage', action='store_true', required=True)
    a = p.parse_args(argv)
    out = stage(a.state_dir)
    print(json.dumps({k: out.get(k) for k in ('status', 'pool', 'counts', 'events_today', 'gaps')}, indent=1))
    return 0 if out['status'] == 'READY' else 2


if __name__ == '__main__':
    sys.exit(main())
