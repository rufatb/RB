#!/usr/bin/env python3
"""THE EVENING NOTE (day-148c) — what is scheduled for the next three sessions,
and how far each reporting name usually moves.

The owner, 2026-11-09, to "a note like this each evening, with the next three
sessions' events and each name's typical move": "Yes". It is sent on the
evening before a trading day, from FMP alone:

* the US and Canadian releases of High or Medium impact, with consensus;
* the names on the morning's list that FMP dates a report for, each with its
  typical move on a report day (the median move against XIU over its last
  reports) and its last four report days.

SIZES AND TIMING, NEVER DIRECTION. On this project's record nothing known
before a report says which way it goes (rejections #46, #50, #56), the gap
does not keep going after the open, and a US inflation print is priced at the
open. The note says so every evening. It names no pick, sizes nothing and
records nothing in a ledger; `evening_note/sent.json` only stops a second send.

    python events_note.py --state-dir .rb-state --build     0 READY, 3 NOTHING, 4 ALREADY_SENT, 1 FAILED
    python events_note.py --state-dir .rb-state --record --message-id ID

FMP's report dates run early for about a third of reports (day-135b), so every
date is labelled as FMP's. A failure is a code, never the URL (the key travels
in it).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import statistics as st
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
UTC = ZoneInfo('UTC')
OUT_DIR = 'evening_note'
SENT = 'sent.json'
SESSIONS = 3                     # trading sessions ahead
COUNTRIES = ('US', 'CA')
IMPACT = ('High', 'Medium')
BENCH = 'XIU.TO'
HISTORY_DAYS = 1700              # calendar days of daily bars: about 17 quarterly reports
REPORTS = 17                     # past reports a typical move is taken over
MIN_REPORTS = 6                  # fewer than this and no typical move is printed
MAX_ROWS = 30
WORKERS = 8
SUBJECT = 'RB Evening Note'
LABEL = 'Evening research note · not an order'

# Measured 2026-11-09 (CLAUDE.md, Day148b). Descriptive: sizes, never a verdict.
REPORT_FACTS = ('What past reports on these names say (measured 2026-11-09): the earnings surprise '
                'matched the direction of the move 61% of the time (2,472 reports); after the open '
                'the gap did not keep going (-0.01% over 927 report days); and the two sessions '
                'after showed no drift (+0.09%, right half the time). A typical move is a size, '
                'not a direction.')
CPI_TABLE = ['US inflation days since 2016 (128 days, measured 2026-11-09), by the print against '
             'consensus:',
             '',
             '| Print vs consensus | Days | XIU at the open | Gold miners (XGD) at the open | '
             'Tech (XIT) at the open | XIU, open to close |',
             '|---|---:|---:|---:|---:|---:|',
             '| Hotter | 48 | -0.15% | -0.06% | -0.32% | +0.11% |',
             '| In line | 21 | +0.08% | +0.07% | +0.06% | +0.09% |',
             '| Cooler | 57 | +0.19% | +0.77% | +0.34% | -0.09% |',
             'The surprise is priced at the open. After it, following the opening direction made '
             '-0.04% and was right 45% of the time.']
CPI_EVENTS = ('Inflation Rate MoM', 'Core Inflation Rate MoM')
INDEX_LEVELS = ('CPI s.a', 'Inflation Rate (', 'CPI (')      # the index level beside its own change: dropped


def _now(now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def _trading(day):
    import dashboard
    return dashboard.is_trading_day(day)


def sessions(today, n=SESSIONS, is_trading=None):
    """The next `n` trading dates after `today`, or [] when tomorrow is not one
    (the note belongs to the evening before a session)."""
    is_trading = is_trading or _trading
    if not is_trading(today + dt.timedelta(days=1)):
        return []
    out, day = [], today
    while len(out) < n and (day - today).days < 21:
        day += dt.timedelta(days=1)
        if is_trading(day):
            out.append(day)
    return out


def universe(root):
    """{ticker: industry} for the morning's list: the staged 150, else the names
    the desks read. Raises NO_LIST_STAGED when neither is on disk."""
    root = Path(root)
    try:
        rows = json.loads((root/'tsx_universe.json').read_text()).get('candidates') or []
        got = {r['ticker']: r.get('industry') for r in rows if isinstance(r, dict) and r.get('ticker')}
        if got:
            return got
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        pass
    try:
        rows = json.loads((root/'claude_brief.json').read_text())['payload']['candidates']
        got = {r['ticker']: None for r in rows if isinstance(r, dict) and r.get('ticker')}
        if got:
            return got
    except (OSError, ValueError, KeyError, TypeError):
        pass
    raise ValueError('NO_LIST_STAGED')


class Reader:
    """FMP GETs, throttled, in memory only: every call here asks about today or
    later, so nothing is worth keeping on disk. Failures are counted by code."""

    def __init__(self, get=None, per_second=9.0):
        import threading
        import time
        if get is None:
            import fmp_client as F
            get = lambda path, **p: F.get(path, retries=1, **p)        # noqa: E731
        self.get, self.failures = get, {}
        self._lock, self._next, self._gap, self._time = threading.Lock(), 0.0, 1.0 / per_second, time

    def __call__(self, path, **params):
        with self._lock:
            wait = self._next - self._time.monotonic()
            self._next = max(self._next, self._time.monotonic()) + self._gap
        if wait > 0:
            self._time.sleep(wait)
        try:
            return self.get(path, **params)
        except Exception as exc:              # a code, never the URL
            msg = str(exc)
            code = msg if (msg.isupper() and ' ' not in msg and len(msg) <= 60) else type(exc).__name__
            with self._lock:
                self.failures[code] = self.failures.get(code, 0) + 1
            return None


# ── the macro calendar ──────────────────────────────────────────────────────

def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def macro(rows, days):
    """{date: {'high': [text], 'medium': [text], 'speakers': [text], 'cpi': 'HH:MM' or None}}
    for the sessions, in ET (FMP stamps UTC)."""
    out = {d: {'high': [], 'medium': [], 'speakers': [], 'cpi': None} for d in days}
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict) or r.get('country') not in COUNTRIES or r.get('impact') not in IMPACT:
            continue
        try:
            at = dt.datetime.strptime(str(r['date']), '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC).astimezone(ET)
        except (KeyError, ValueError):
            continue
        day = out.get(at.date())
        name = ' '.join(str(r.get('event') or '').split())[:70]
        if day is None or not name or (at, r['country'], name) in seen or name.startswith(INDEX_LEVELS):
            continue
        seen.add((at, r['country'], name))
        if name.startswith(CPI_EVENTS) and r['country'] == 'US':
            day['cpi'] = at.strftime('%H:%M')
        if name.startswith('Fed ') and name.endswith('Speech'):
            day['speakers'].append((at, '%s %s' % (at.strftime('%H:%M'), name[4:-7])))
            continue
        est, prev = _num(r.get('estimate')), _num(r.get('previous'))
        text = '%s %s %s%s' % (at.strftime('%H:%M'), r['country'], name,
                               ''.join(' — %s' % x for x in (
                                   ('consensus %g' % est) if est is not None else None,
                                   ('previous %g' % prev) if prev is not None else None) if x))
        day['high' if r['impact'] == 'High' else 'medium'].append((at, text))
    for day in out.values():
        for k in ('high', 'medium', 'speakers'):
            day[k] = [t for _, t in sorted(day[k])]
    return out


# ── the reports ─────────────────────────────────────────────────────────────

def _bars(rows):
    out = {}
    for r in rows or []:
        d = str(r.get('date') or '')[:10]
        if d and all(_num(r.get(k)) is not None and r[k] > 0 for k in ('open', 'close')):
            out[d] = {'open': float(r['open']), 'close': float(r['close']),
                      'volume': float(_num(r.get('volume')) or 0)}
    return dict(sorted(out.items()))


def reactions(reports, bars, bench, today):
    """Each past report's move against the benchmark, close to close, on its
    reaction day: the busier of the report date's session and the next one
    (volume against its own 20-session median), because FMP's dates run early.
    A size measure only: the day is chosen with hindsight."""
    dates = list(bars)
    out = []
    for r in reports or []:
        rd = str(r.get('date') or '')[:10]
        if not rd or rd >= today or _num(r.get('epsActual')) is None:
            continue
        after = [i for i, d in enumerate(dates) if d >= rd]
        if not after or after[0] < 21 or after[0] + 1 >= len(dates):
            continue
        i0 = after[0]

        def busy(i):
            med = st.median(bars[dates[j]]['volume'] for j in range(i - 20, i)) or 1.0
            return bars[dates[i]]['volume'] / med
        i = i0 if busy(i0) >= busy(i0 + 1) else i0 + 1
        day, prev = dates[i], dates[i - 1]
        if day not in bench or prev not in bench:
            continue
        out.append((rd, 100 * ((bars[day]['close'] / bars[prev]['close'] - 1)
                               - (bench[day]['close'] / bench[prev]['close'] - 1))))
    return [x for _, x in sorted(out)]


def typical(moves):
    """(median absolute move or None, the last four, how many) over the last REPORTS."""
    last = moves[-REPORTS:]
    return (st.median(abs(x) for x in last) if len(last) >= MIN_REPORTS else None, last[-4:], len(last))


def reporters(calendar, names, today, days):
    """[(fmp date, ticker)] for the list's names FMP dates a report for on one
    of the sessions, or today with no result posted yet (out after the close)."""
    want = {d.isoformat() for d in days}
    out = set()
    for r in calendar or []:
        if not isinstance(r, dict) or r.get('symbol') not in names:
            continue
        d = str(r.get('date') or '')[:10]
        if d in want or (d == today.isoformat() and _num(r.get('epsActual')) is None):
            out.add((d, r['symbol']))
    return sorted(out)


def _when(d, today):
    day = dt.date.fromisoformat(d)
    return 'Tonight or before the open' if day == today else day.strftime('%a %m-%d')


def report_rows(read, due, today):
    """One row per reporter: its typical move and last four report days."""
    start = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    span = {'from': start, 'to': today.isoformat()}
    bench = _bars(read('historical-price-eod/full', symbol=BENCH, **span))

    def one(item):
        d, t = item
        moves = reactions(read('earnings', symbol=t, limit=24),
                          _bars(read('historical-price-eod/full', symbol=t, **span)), bench, today.isoformat())
        size, last, n = typical(moves)
        return {'date': d, 'ticker': t, 'typical': size, 'last': last, 'reports': n}
    if not due:
        return []
    with cf.ThreadPoolExecutor(max(1, min(WORKERS, len(due)))) as pool:
        rows = list(pool.map(one, due))
    return sorted(rows, key=lambda r: (r['date'], -(r['typical'] or 0), r['ticker']))


# ── the note ────────────────────────────────────────────────────────────────

def compose(today, days, cal, rows, industries, failures, now):
    first = days[0]
    lines = ['# %s — %s' % (SUBJECT, today.isoformat()),
             'For %s and the two sessions after it; built %s ET from FMP. Sizes and timing, not direction.'
             % (first.strftime('%a %m-%d'), _now(now).strftime('%H:%M')),
             '', '## Scheduled (ET)']
    any_cpi = False
    for d in days:
        c = cal.get(d) or {}
        any_cpi = any_cpi or bool(c.get('cpi'))
        items = (c.get('high') or []) + (c.get('medium') or [])
        if c.get('speakers'):
            items.append('Fed speakers: ' + ', '.join(c['speakers']))
        lines.append('### %s' % d.strftime('%a %m-%d'))
        lines += ['- ' + x for x in items] or ['- Nothing of High or Medium impact on the calendar.']
    if any_cpi:
        lines += ['', *CPI_TABLE]
    lines += ['', '## Reports on the list (FMP\'s dates)']
    if rows is None:
        lines.append('Unavailable today: the earnings calendar could not be read.')
    elif not rows:
        lines.append('FMP dates no report on the list for these sessions.')
    else:
        lines += ['', '| Name | FMP\'s date | Typical move | Last four report days | Industry |',
                  '|---|---|---:|---|---|']
        for r in rows[:MAX_ROWS]:
            lines.append('| %s | %s | %s | %s | %s |' % (
                r['ticker'], _when(r['date'], today),
                ('%.1f%%' % r['typical']) if r['typical'] is not None else '—',
                ', '.join('%+.1f%%' % x for x in r['last']) or '—',
                str(industries.get(r['ticker']) or '—').replace('|', '/')[:34]))
        if len(rows) > MAX_ROWS:
            lines.append('And %d more with smaller typical moves.' % (len(rows) - MAX_ROWS))
        lines += ['Typical move is the median move against XIU on the report day over the last %d '
                  'reports or fewer; the day is the busier of FMP\'s date and the next session. '
                  'FMP\'s dates run early for about a third of reports, so check the company\'s '
                  'own notice before relying on one.' % REPORTS,
                  REPORT_FACTS]
    if failures:
        lines.append('Not read from FMP: %s.' % ', '.join('%s ×%d' % kv for kv in sorted(failures.items())))
    lines += ['', '---',
              'Research only, not an order. Nothing here is a pick: the morning\'s Top 2 comes from '
              'the usual process, and every source on its record is still a coin flip.']
    body = '\n'.join(lines)
    c0 = cal.get(first) or {}
    lead = ('US inflation %s' % c0['cpi'] if c0.get('cpi') else
            (c0.get('high') or c0.get('medium') or ['no release of High or Medium impact'])[0])
    dated = sum(1 for r in rows or [] if r['date'] <= first.isoformat())
    head = '%s: %s%s' % (first.strftime('%a %m-%d'), lead.split(' — ')[0],
                         ' · %d report%s on the list by then' % (dated, '' if dated == 1 else 's') if dated else '')
    subject = '%s — %s — for %s' % (SUBJECT, today.isoformat(), head)
    import email_render
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div></td></tr>'
            % email_render.full.escape(head))
    return subject, body, email_render.html_from_text(body, hero=hero, label=LABEL)


def sent_today(root, now):
    try:
        obj = json.loads((Path(root)/OUT_DIR/SENT).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get('session') == now.date().isoformat()


def build(state_dir, now=None, *, read=None, is_trading=None):
    """(status, info). READY writes subject.txt, report.txt and report.html."""
    now = _now(now)
    root, today = Path(state_dir), now.date()
    if sent_today(root, now):
        return 'ALREADY_SENT', {}
    days = sessions(today, is_trading=is_trading)
    if not days:
        return 'NOTHING', {'reason': 'tomorrow is not a trading day'}
    read = read or Reader()
    span = {'from': today.isoformat(), 'to': days[-1].isoformat()}
    events = read('economic-calendar', **span)
    try:
        industries = universe(root)
    except ValueError as exc:
        industries, list_error = {}, str(exc)
    else:
        list_error = None
    calendar = read('earnings-calendar', **span) if industries else None
    if events is None and calendar is None:
        return 'FAILED', {'reason': list_error or ', '.join(sorted(read.failures)) or 'NO_DATA'}
    rows = None if calendar is None else report_rows(read, reporters(calendar, set(industries), today, days), today)
    failures = dict(read.failures)
    if list_error:
        failures[list_error] = 1
    subject, body, html = compose(today, days, macro(events, days), rows, industries, failures, now)
    out = root/OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out/'subject.txt').write_text(subject, encoding='utf-8')
    (out/'report.txt').write_text(body, encoding='utf-8')
    (out/'report.html').write_text(html, encoding='utf-8')
    return 'READY', {'subject': subject, 'subject_path': str(out/'subject.txt'),
                     'text_path': str(out/'report.txt'), 'html_path': str(out/'report.html'),
                     'sessions': [d.isoformat() for d in days], 'reports': len(rows or [])}


def record(state_dir, message_id, now=None):
    from build_biotech import write_atomic
    now = _now(now)
    (Path(state_dir)/OUT_DIR).mkdir(parents=True, exist_ok=True)
    write_atomic(Path(state_dir)/OUT_DIR/SENT, {'session': now.date().isoformat(),
                                                'message_id': message_id, 'sent_at': now.isoformat()})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--build', action='store_true')
    g.add_argument('--record', action='store_true')
    p.add_argument('--message-id')
    a = p.parse_args(argv)
    if a.record:
        if not a.message_id:
            p.error('--record needs --message-id')
        record(a.state_dir, a.message_id)
        print(json.dumps({'status': 'RECORDED', 'message_id': a.message_id}))
        return 0
    try:
        status, info = build(a.state_dir)
    except Exception as exc:              # the note must never cost the evening job
        print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
        return 1
    print(json.dumps({'status': status, **info}))
    return {'READY': 0, 'NOTHING': 3, 'ALREADY_SENT': 4}.get(status, 1)


if __name__ == '__main__':
    sys.exit(main())
