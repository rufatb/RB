"""THE COUNCIL FLASH — the Top 2 the moment the council decides (owner, 2026-10-06).

The council sits before the open (08:58 ET on 2026-10-06), but its decision
reached the inbox only with the full report at ~09:46. The owner asked for a
short preliminary email as soon as the consensus exists, ahead of the report.

This changes WHEN the council's decision is delivered, never WHAT it is:
* the positions, votes and "wrong if" levels are read from the sealed
  `council.json`, through the same `council.top_two` and `top_picks.table` the
  report uses;
* nothing new is recorded or scored (the report records the Top 2 as before);
* the flash is sent before the 09:46 entry check (day-120 E1), so it says so
  and prints each position's "wrong if" for the reader to check against the
  open themselves.

The subject never contains "RB Daily Report — <date>": every sender searches
for that phrase to decide whether the report already went out, and a flash
must not stop the report being sent.

    python council_flash.py --state-dir .rb-state --wait 100   # 0 READY / 2 STILL_WAITING / 3 NOTHING / 4 ALREADY_SENT
    python council_flash.py --state-dir .rb-state --record --message-id <id>
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
OUT_DIR = 'flash'
SENT = 'sent.json'
LATEST = dt.time(9, 44)      # past this the full report is minutes away; no flash
SAT = ('READY', 'NO_CONSENSUS', 'NO_POSITIONS')


def _now(now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def subject(session, section):
    picks = (section or {}).get('picks') or []
    if picks:
        what = ' · '.join('%s %s (%s)' % (p['side'], p['ticker'], p['agreement']) for p in picks)
    elif (section or {}).get('no_positions'):
        what = 'no model proposed a position'
    else:
        what = 'no consensus — nothing to act on'
    return 'RB Council Flash — %s — %s' % (session, what)


def compose(council, now):
    """(subject, text, html) for a council that sat today, else None."""
    import council as K
    import email_render
    import top_picks
    if not isinstance(council, dict) or council.get('status') not in SAT:
        return None
    session = council.get('session')
    decided = council.get('finished_at') or council.get('asked_at') or ''
    at = decided[11:16] if len(decided) >= 16 else '?'
    if council.get('status') == 'NO_POSITIONS':
        section = {'picks': [], 'no_positions': True}
        lines = ['## Top 2 — the council\'s decision', '',
                 'No model proposed a position today, so the council had nothing to decide.']
    else:
        section = K.top_two(council)
        lines = top_picks.table(section, concise=True)
    pre_open = at < '09:30'
    body = '\n'.join([
        '# RB Council Flash — %s' % session,
        'The council decided at %s ET%s; sent %s ET. The full report follows at ~09:46.'
        % (at, ' (before the open)' if pre_open else '', _now(now).strftime('%H:%M')),
        '',
        *lines,
        '',
        '---',
        ('Preliminary. Decided from the previous session\'s data and not yet checked against the '
         'open: the 09:46 report drops a position already past its "wrong if", so check that level '
         'against your own quote first.'),
        'Research only, not an order. No share counts here; the full report sizes the desks.',
    ])
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div></td></tr>'
            % email_render.full.escape(subject(session, section).split(' — ', 2)[-1]))
    return subject(session, section), body, email_render.html_from_text(body, hero=hero)


def sent_today(root, now):
    try:
        obj = json.loads((Path(root)/OUT_DIR/SENT).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get('session') == _now(now).date().isoformat()


def prepare(state_dir, now=None):
    """Write the flash files when today's council has sat. Returns (status, info)."""
    import council as K
    from build_biotech import write_atomic
    now = _now(now)
    root = Path(state_dir)
    if sent_today(root, now):
        return 'ALREADY_SENT', {}
    council = K.load(root, now)
    if council.get('status') == 'UNAVAILABLE' and 'not staged' in str(council.get('reason')):
        return 'WAITING', {}
    if council.get('status') == 'UNAVAILABLE' and 'not today' in str(council.get('reason')):
        return 'WAITING', {}
    made = compose(council, now)
    if made is None:
        return 'NOTHING', {'reason': 'the council did not sit (%s); the report\'s counted rule '
                           'decides the Top 2' % (council.get('reason') or council.get('status'))}
    subj, text, html = made
    out = root/OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, content in (('subject.txt', subj), ('report.txt', text), ('report.html', html)):
        (out/name).write_text(content, encoding='utf-8')
    write_atomic(out/'plan.json', {'session': now.date().isoformat(), 'subject': subj,
                                   'council_status': council.get('status'),
                                   'prepared_at': now.isoformat()})
    return 'READY', {'subject_path': str(out/'subject.txt'), 'text_path': str(out/'report.txt'),
                     'html_path': str(out/'report.html'), 'subject': subj}


def wait(state_dir, seconds, *, now_fn=None, sleep=time.sleep):
    """Block until the flash is ready (0), the wait ends (2), there is nothing to
    flash (3: no council, or too close to the report) or it was already sent (4)."""
    now_fn = now_fn or (lambda: dt.datetime.now(ET))
    deadline = time.monotonic() + seconds
    while True:
        now = _now(now_fn())
        status, info = prepare(state_dir, now)
        if status == 'ALREADY_SENT':
            return 4, {'status': status}
        if status == 'READY':
            if now.time() >= LATEST:
                return 3, {'status': 'TOO_LATE', 'reason': 'the full report is minutes away'}
            return 0, {'status': status, **info}
        if status == 'NOTHING':
            return 3, {'status': status, **info}
        if now.time() >= LATEST:
            return 3, {'status': 'TOO_LATE', 'reason': 'the council had not sealed by 09:44'}
        if time.monotonic() >= deadline:
            return 2, {'status': 'STILL_WAITING'}
        sleep(5)


def record(state_dir, message_id, now=None):
    from build_biotech import write_atomic
    now = _now(now)
    write_atomic(Path(state_dir)/OUT_DIR/SENT, {'session': now.date().isoformat(),
                                                'message_id': message_id, 'sent_at': now.isoformat()})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--wait', type=int, metavar='SECONDS',
                   help='0 READY (send it), 2 STILL_WAITING, 3 NOTHING/TOO_LATE, 4 ALREADY_SENT')
    g.add_argument('--record', action='store_true', help='mark today\'s flash as sent')
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
    except Exception as exc:          # the flash must never cost the morning
        print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
        return 1
    print(json.dumps(info))
    return code


if __name__ == '__main__':
    sys.exit(main())
