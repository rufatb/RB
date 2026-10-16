#!/usr/bin/env python3
"""THE NOON CHECK (day-130) — where the council's picks stand at 12:00 ET.

Registered in PREREGISTER_day130_learning.md (H3). On 379 replay picks,
closing at noon was no worse than holding to 15:55 and swung 15% less: the
afternoon added nothing. This email lets the owner apply that at noon. Each
council pick (and the labelled runner-up) gets:
* its move since the 09:45 entry the record scores from;
* whether its own "wrong if" was crossed since entry;
* its sector ETF's move over the same window.

It changes nothing: the record keeps scoring 09:45 -> 15:55, and no pick, size
or rule moves.

    python noon_check.py --state-dir .rb-state --wait 600   0 READY, 2 STILL_WAITING,
                                                            3 NOTHING/TOO_LATE, 4 ALREADY_SENT
    python noon_check.py --state-dir .rb-state --record --message-id ID

One email a day (noon/sent.json), between 12:00 and 13:30 ET. A name whose
bars fail reads NOT CHECKED. The check never costs anything else.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
OUT_DIR = 'noon'
SENT = 'sent.json'
NOON_AT = dt.time(12, 0)
LATEST = dt.time(13, 30)
ENTRY = dt.time(9, 40)        # the 09:40 bar's close: the 09:45 entry the record uses


def _now(now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def section(root, now):
    """Today's Top 2 as the morning email printed it (frozen report), else the
    sealed council without the 09:46 entry check. None when neither is today's."""
    import council as K
    today = now.date().isoformat()
    try:
        report = json.loads((Path(root)/'latest'/'report.json').read_text())
        sec = (report.get('intraday') or {}).get('top_two')
        if report.get('session') == today and isinstance(sec, dict) and sec.get('council'):
            return sec, 'the 09:46 report'
    except (OSError, ValueError):
        pass
    council = K.load(root, now)
    if council.get('status') in ('READY', 'NO_CONSENSUS'):
        return K.top_two(council), 'the sealed council (the report was not read)'
    return None, None


def _bars_today(bars, now):
    """[(time, high, low, close)] of today's COMPLETE 5-minute bars, in ET."""
    local = bars.tz_convert(ET)
    out = []
    for ts, row in local.iterrows():
        if ts.date() != now.date() or ts + dt.timedelta(minutes=5) > now:
            continue
        if any(row.get(k) is None for k in ('High', 'Low', 'Close')):
            continue
        out.append((ts.time(), float(row['High']), float(row['Low']), float(row['Close'])))
    return out


def measure(item, now, bars_for):
    """One pick at noon. Missing bars give NOT CHECKED, with the reason."""
    import exposure
    s = 1 if item['side'] == 'LONG' else -1
    etf = exposure.position_exposure(item['ticker'])['etf']
    out = {**item, 'etf': etf}
    try:
        today = _bars_today(bars_for(item['ticker']), now)
    except Exception as exc:              # that name's NOT CHECKED, never silent
        return {**out, 'status': 'NOT CHECKED', 'why': type(exc).__name__}
    entry = next((c for t, _, _, c in today if t == ENTRY), None)
    after = [b for b in today if b[0] > ENTRY]
    if entry is None or not after:
        return {**out, 'status': 'NOT CHECKED', 'why': 'no 09:45 bar today'}
    last_t, _, _, last = after[-1]
    level = item.get('invalid_at')
    crossed = None
    if isinstance(level, (int, float)):
        crossed = (min(b[2] for b in after) < level) if s > 0 else (max(b[1] for b in after) > level)
    etf_move = None
    if etf and etf != item['ticker']:
        try:
            eb = _bars_today(bars_for(etf), now)
            # a thin ETF may not trade in the 09:40 bar: its last trade at or before it
            e0 = next((c for t, _, _, c in reversed(eb) if t <= ENTRY), None)
            e1 = [c for t, _, _, c in eb if t > ENTRY]
            if e0 and e1:
                etf_move = (e1[-1] / e0 - 1) * 100
        except Exception:                 # the ETF is context; its failure shows as a dash
            etf_move = None
    return {**out, 'status': 'CHECKED', 'entry': entry, 'last': last,
            'at': (dt.datetime.combine(now.date(), last_t) + dt.timedelta(minutes=5)).strftime('%H:%M'),
            'since_entry': s * (last / entry - 1) * 100, 'crossed': crossed, 'etf_move': etf_move}


def _fmt(v):
    return '—' if v is None else '%+.2f%%' % v


def compose(session, rows, source, now):
    import email_render
    import execution_lab
    if not rows:
        return None
    bits = []
    for r in rows:
        label = '%s %s' % (r['side'], r['ticker'])
        if r.get('runner_up'):
            label = 'runner-up ' + label
        if r['status'] != 'CHECKED':
            bits.append('%s NOT CHECKED' % label)
        else:
            bits.append('%s %s%s' % (label, _fmt(r['since_entry']),
                                     ' (wrong if crossed)' if r.get('crossed') else ''))
    if all(r.get('runner_up') for r in rows):   # no council pick: never read as one
        bits.insert(0, 'no council pick')
    subj = 'RB Noon Check — %s — %s' % (session, ' · '.join(bits))
    lines = ['# RB Noon Check — %s' % session,
             'Measured at %s ET from 5-minute bars, from the 09:45 entry the record scores. Picks '
             'from %s.' % (now.strftime('%H:%M'), source), '',
             '| Pick | Since 09:45 | Wrong if | Crossed since entry | Sector ETF since 09:45 |',
             '|---|---|---|---|---|']
    for r in rows:
        wrong = ('%s %g' % ('below' if r['side'] == 'LONG' else 'above', r['invalid_at'])
                 if isinstance(r.get('invalid_at'), (int, float)) else '—')
        name = '%s %s%s' % (r['side'], r['ticker'], ' (runner-up, not a pick)' if r.get('runner_up') else '')
        if r['status'] != 'CHECKED':
            lines.append('| %s | NOT CHECKED (%s) | %s | — | — |' % (name, r.get('why'), wrong))
            continue
        crossed = '—' if r['crossed'] is None else ('YES' if r['crossed'] else 'no')
        lines.append('| %s | %s (%g at %s) | %s | %s | %s %s |' % (
            name, _fmt(r['since_entry']), r['last'], r['at'], wrong, crossed,
            r.get('etf') or '—', _fmt(r.get('etf_move'))))
    picks = {'picks': [r for r in rows if not r.get('runner_up')]}
    import top_picks
    direction = top_picks.direction_line(picks)          # day-135: one side, one bet
    lines += [direction] if direction else []
    lines += ['', execution_lab.NOON_NOTE,
              'A crossed "wrong if" means the reason the pick was chosen is proven wrong today.',
              'Research only, not an order. The record keeps scoring 09:45 → 15:55; nothing here changes it.']
    body = '\n'.join(lines)
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div>%s</td></tr>'
            % (email_render.full.escape(subj.split(' — ', 2)[-1]), email_render.direction_html(picks)))
    return subj, body, email_render.html_from_text(body, hero=hero)


def sent_today(root, now):
    try:
        obj = json.loads((Path(root)/OUT_DIR/SENT).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get('session') == now.date().isoformat()


def prepare(state_dir, now=None, *, bars_for=None):
    from build_biotech import write_atomic
    import model_picks
    now = _now(now)
    root = Path(state_dir)
    if sent_today(root, now):
        return 'ALREADY_SENT', {}
    if now.time() > LATEST:
        return 'TOO_LATE', {'reason': 'past 13:30 ET'}
    sec, source = section(root, now)
    items = ((sec or {}).get('picks') or []) + ([sec['runner_up']] if (sec or {}).get('runner_up') else [])
    if not items:
        return 'NOTHING', {'reason': 'no council pick today, so nothing to check'}
    if now.time() < NOON_AT:
        return 'WAITING', {}
    bars_for = bars_for or model_picks._yahoo_bars
    rows = [measure(x, now, bars_for) for x in items]
    out = compose(now.date().isoformat(), rows, source, now)
    d = root/OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d/'subject.txt').write_text(out[0])
    (d/'report.txt').write_text(out[1])
    (d/'report.html').write_text(out[2])
    write_atomic(d/'rows.json', {'session': now.date().isoformat(), 'rows': rows})
    return 'READY', {'subject': out[0], 'subject_path': str(d/'subject.txt'),
                     'text_path': str(d/'report.txt'), 'html_path': str(d/'report.html')}


def wait(state_dir, seconds, *, now_fn=None, sleep=time.sleep, bars_for=None):
    now_fn = now_fn or (lambda: dt.datetime.now(ET))
    deadline = time.monotonic() + seconds
    while True:
        status, info = prepare(state_dir, now_fn(), bars_for=bars_for)
        if status != 'WAITING':
            return {'READY': 0, 'ALREADY_SENT': 4}.get(status, 3), {'status': status, **info}
        if time.monotonic() >= deadline:
            return 2, {'status': 'STILL_WAITING'}
        sleep(15)


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
    g.add_argument('--wait', type=int, metavar='SECONDS')
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
        code, info = wait(a.state_dir, a.wait)
    except Exception as exc:              # the check must never cost anything else
        print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
        return 1
    print(json.dumps(info))
    return code


if __name__ == '__main__':
    sys.exit(main())
