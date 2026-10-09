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
    python council_flash.py --state-dir .rb-state --open-check 540  # day-127: is it still alive at 09:31?
    python council_flash.py --state-dir .rb-state --record-open --message-id <id>

DAY-127 (PREREGISTER_day127_dated.md): at 09:31 the flashed positions are
re-checked against FMP's live quote. The verdict is the day-120 E1 rule,
unchanged: VOID when the price is already past the position's "wrong if",
otherwise STILL VALID. Beside it are the open vs the prior close (signed to the
pick) and the sector ETF's move. A quote not stamped today after 09:30 is NOT
CHECKED. Nothing is recorded or scored.
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
OPEN_AT = dt.time(9, 31)     # the open check waits for a minute of trading
OPEN_SENT = 'open_sent.json'
SAT = ('READY', 'NO_CONSENSUS', 'NO_POSITIONS')


def _now(now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def subject(session, section):
    import council as K
    picks = (section or {}).get('picks') or []
    ru = (section or {}).get('runner_up')        # day-129: labelled, never a pick
    tail = (' · runner-up, %s: %s %s' % (K.runner_up_label(ru), ru['side'], ru['ticker'])
            if ru and len(picks) < 2 else '')
    if picks:
        what = ' · '.join('%s %s (%s)' % (p['side'], p['ticker'], p['agreement']) for p in picks) + tail
    elif tail:
        what = 'no consensus' + tail
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
        'Every reason above describes %s, the prior session, and the morning\'s pre-market prints. '
        'The open check at 09:31 says whether each position is still alive today.'
        % _prior(council),
        ('Preliminary. Decided from the previous session\'s data and not yet checked against the '
         'open: the 09:46 report drops a position already past its "wrong if", so check that level '
         'against your own quote first.'),
        'Research only, not an order. No share counts here; the full report sizes the desks.',
    ])
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div></td></tr>'
            % email_render.full.escape(subject(session, section).split(' — ', 2)[-1]))
    return subject(session, section), body, email_render.html_from_text(body, hero=hero)


def _prior(council):
    import deepseek_opportunities as O
    try:
        return O.prior_session(dt.date.fromisoformat(council['session'])).isoformat()
    except (KeyError, TypeError, ValueError):
        return 'the prior session'


def _marker_today(root, now, name):
    try:
        obj = json.loads((Path(root)/OUT_DIR/name).read_text())
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and obj.get('session') == _now(now).date().isoformat()


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


def record(state_dir, message_id, now=None, name=SENT):
    from build_biotech import write_atomic
    now = _now(now)
    (Path(state_dir)/OUT_DIR).mkdir(parents=True, exist_ok=True)
    write_atomic(Path(state_dir)/OUT_DIR/name, {'session': now.date().isoformat(),
                                                'message_id': message_id, 'sent_at': now.isoformat()})


# ── day-127: the open check ──────────────────────────────────────────────────

def fmp_quote(symbol, state_dir='.rb-state'):
    import fmp_client as F
    key = F.load_key(state_dir)
    rows = F.get('quote', key, symbol=symbol)
    return (rows or [None])[0]


def _live(q, now):
    """The quote's last price when it is stamped today at or after 09:30 ET, else None."""
    if not isinstance(q, dict) or not isinstance(q.get('price'), (int, float)):
        return None
    try:
        t = dt.datetime.fromtimestamp(float(q['timestamp']), ET)
    except (KeyError, TypeError, ValueError, OSError):
        return None
    if t.date() != now.date() or t.time() < dt.time(9, 30) or t > now + dt.timedelta(minutes=2):
        return None
    return t


def _pct(a, b):
    return 100.0 * (a / b - 1.0) if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b else None


def check_open(council, now, *, quote=None):
    """One row per council pick: the E1 verdict on today's live quote, and the facts."""
    import council as K
    import entry_checks
    import exposure
    quote = quote or fmp_quote
    rows = []
    sec = K.top_two(council)
    items = (sec.get('picks') or []) + ([sec['runner_up']] if sec.get('runner_up') else [])
    for p in items:                       # day-129: the runner-up is checked too, labelled
        sign = 1 if p['side'] == 'LONG' else -1
        x = exposure.position_exposure(p['ticker'])
        try:
            q = quote(p['ticker'])
        except Exception as exc:          # one name's failure is that name's NOT CHECKED
            q, why = None, str(exc)[:30] if str(exc).isupper() else type(exc).__name__
        else:
            why = None
        at = _live(q, now)
        try:
            e = quote(x['etf']) if x['etf'] else None
        except Exception:
            e = None
        etf_move = _pct(e.get('price'), e.get('previousClose')) if _live(e, now) else None
        if at is None:
            rows.append({**p, 'verdict': 'NOT CHECKED', 'why': why or 'no quote stamped today after 09:30',
                         'etf': x['etf'], 'etf_move': etf_move})
            continue
        verdict = entry_checks.check(p['side'], p.get('invalid_at'), q['price'])
        rows.append({**p, 'verdict': {'VOID': 'VOID', 'OK': 'STILL VALID'}.get(verdict, verdict),
                     'price': q['price'], 'at': at.strftime('%H:%M'),
                     'open': q.get('open'), 'prev_close': q.get('previousClose'),
                     'open_for_pick': (sign * _pct(q.get('open'), q.get('previousClose'))
                                       if _pct(q.get('open'), q.get('previousClose')) is not None else None),
                     'now_for_pick': (sign * _pct(q['price'], q.get('previousClose'))
                                      if _pct(q['price'], q.get('previousClose')) is not None else None),
                     'etf': x['etf'], 'etf_move': etf_move})
    return rows


def _fmt(v):
    return '—' if v is None else '%+.2f%%' % v


def compose_open(council, rows, now):
    import council as K
    import email_render
    session = council.get('session')
    if not rows:
        return None
    verdicts = ' · '.join('%s%s %s %s' % ('runner-up ' if r.get('runner_up') else '', r['side'],
                                         r['ticker'], r['verdict']) for r in rows)
    subj = 'RB Open Check — %s — %s' % (session, verdicts)
    lines = ['# RB Open Check — %s' % session,
             'Checked at %s ET against the live quote (FMP last trade). The full report follows at ~09:46.'
             % _now(now).strftime('%H:%M'), '',
             '| Pick | Verdict | Wrong if | Price now | Open vs prior close, for the pick | Now vs prior close, for the pick | Sector ETF since prior close |',
             '|---|---|---|---|---|---|---|']
    for r in rows:
        wrong = ('%s %g' % ('below' if r['side'] == 'LONG' else 'above', r['invalid_at'])
                 if isinstance(r.get('invalid_at'), (int, float)) else '—')
        price = ('%g at %s' % (r['price'], r['at'])) if r.get('price') is not None else r.get('why', '—')
        lines.append('| %s %s%s | %s | %s | %s | %s | %s | %s %s |' % (
            r['side'], r['ticker'],
            ' (runner-up, %s)' % K.runner_up_label(r) if r.get('runner_up') else '',
            r['verdict'], wrong, price, _fmt(r.get('open_for_pick')),
            _fmt(r.get('now_for_pick')), r.get('etf') or '—', _fmt(r.get('etf_move'))))
    lines += ['',
              'VOID means the price is already past the position\'s own "wrong if": the reason it was '
              'chosen is proven wrong today. STILL VALID means only that it is not; it is not a '
              'forecast. A positive "for the pick" figure is a move the pick\'s way.',
              'Research only, not an order.']
    body = '\n'.join(lines)
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div></td></tr>'
            % email_render.full.escape(verdicts))
    return subj, body, email_render.html_from_text(body, hero=hero)


def prepare_open(state_dir, now=None, *, quote=None):
    import council as K
    from build_biotech import write_atomic
    now = _now(now)
    root = Path(state_dir)
    if _marker_today(root, now, OPEN_SENT):
        return 'ALREADY_SENT', {}
    if now.time() >= LATEST:
        return 'TOO_LATE', {'reason': 'the full report is minutes away'}
    council = K.load(root, now)
    if council.get('status') not in SAT:
        return 'NOTHING', {'reason': 'no council today, so nothing to check'}
    sec = K.top_two(council)
    if not sec.get('picks') and not sec.get('runner_up'):
        return 'NOTHING', {'reason': 'the council chose no position, so nothing to check'}
    if now.time() < OPEN_AT:
        return 'WAITING', {}
    rows = check_open(council, now, quote=quote or (lambda sym: fmp_quote(sym, root)))
    subj, text, html = compose_open(council, rows, now)
    out = root/OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, content in (('open_subject.txt', subj), ('open_report.txt', text), ('open_report.html', html)):
        (out/name).write_text(content, encoding='utf-8')
    write_atomic(out/'open_plan.json', {'session': now.date().isoformat(), 'subject': subj,
                                        'rows': [{k: r.get(k) for k in ('ticker', 'side', 'verdict', 'price', 'at')}
                                                 for r in rows], 'prepared_at': now.isoformat()})
    return 'READY', {'subject_path': str(out/'open_subject.txt'), 'text_path': str(out/'open_report.txt'),
                     'html_path': str(out/'open_report.html'), 'subject': subj}


def wait_open(state_dir, seconds, *, now_fn=None, sleep=time.sleep, quote=None):
    """0 READY / 2 STILL_WAITING / 3 NOTHING or TOO_LATE / 4 ALREADY_SENT."""
    now_fn = now_fn or (lambda: dt.datetime.now(ET))
    deadline = time.monotonic() + seconds
    while True:
        status, info = prepare_open(state_dir, now_fn(), quote=quote)
        if status != 'WAITING':
            return {'READY': 0, 'ALREADY_SENT': 4}.get(status, 3), {'status': status, **info}
        if time.monotonic() >= deadline:
            return 2, {'status': 'STILL_WAITING'}
        sleep(5)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default='.rb-state')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--wait', type=int, metavar='SECONDS',
                   help='0 READY (send it), 2 STILL_WAITING, 3 NOTHING/TOO_LATE, 4 ALREADY_SENT')
    g.add_argument('--record', action='store_true', help='mark today\'s flash as sent')
    g.add_argument('--open-check', type=int, metavar='SECONDS',
                   help='day-127: wait for 09:31, re-check the flashed positions on the live quote')
    g.add_argument('--record-open', action='store_true', help='mark today\'s open check as sent')
    p.add_argument('--message-id')
    a = p.parse_args(argv)
    if a.record or a.record_open:
        if not a.message_id:
            p.error('--record needs --message-id')
        record(a.state_dir, a.message_id, name=OPEN_SENT if a.record_open else SENT)
        print(json.dumps({'status': 'RECORDED', 'message_id': a.message_id}))
        return 0
    if a.open_check is not None:
        try:
            code, info = wait_open(a.state_dir, a.open_check)
        except Exception as exc:      # the check must never cost the morning
            print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
            return 1
        print(json.dumps(info))
        return code
    try:
        code, info = wait(a.state_dir, a.wait)
    except Exception as exc:          # the flash must never cost the morning
        print(json.dumps({'status': 'FAILED', 'reason': type(exc).__name__}))
        return 1
    print(json.dumps(info))
    return code


if __name__ == '__main__':
    sys.exit(main())
