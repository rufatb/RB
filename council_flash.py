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

DAY-150 (owner, 2026-11-10; PREREGISTER_day150_morning_decision.md): with
`COMBINED` on, the 09:00 email is "RB Morning Decision": the decision on top
(what stands on each side after the quality floor, or why nothing does), then
one table of Claude's picks and the pre-open desk's release reads with the New
York price just before the email. The 09:31 email gives each pick KEEP, DROP
or CAUTION by fixed rules, shows where each release read opened, and records
the verdicts in `data/reviews/open_checks.csv`. Same commands as below.

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
# Day-150 (owner, 2026-11-10; PREREGISTER_day150_morning_decision.md): one
# decision at 09:00 and one check at 09:31. On, the 09:00 email carries the
# decision on top and one table of Claude's picks and the pre-open desk's
# release reads, and the 09:31 email gives each pick KEEP / DROP / CAUTION.
# Off, both emails are as they were on 2026-11-10.
COMBINED = True


def _now(now=None):
    now = now or dt.datetime.now(ET)
    if now.tzinfo is None:
        raise ValueError('AWARE_CLOCK_REQUIRED')
    return now.astimezone(ET)


def passed_words(section):
    """'a big mover', 'big movers', 'a high-volatility name' … for the subject."""
    m, w = len(section.get('passed_movers') or []), len(section.get('passed_wild') or [])
    r = len(section.get('passed_run') or [])     # day-146
    parts = ([('big movers' if m > 1 else 'a big mover')] if m else []) + (
        [('high-volatility names' if w > 1 else 'a high-volatility name')] if w else []) + (
        [('three-day runs' if r > 1 else 'a three-day run')] if r else [])
    return ' and '.join(parts)


def subject(session, section):
    import council as K
    picks = (section or {}).get('picks') or []
    ru = (section or {}).get('runner_up')        # day-129: labelled, never a pick
    tail = (' · runner-up, %s: %s %s' % (K.runner_up_label(ru), ru['side'], ru['ticker'])
            if ru and len(picks) < 2 else '')
    if picks:
        what = ' · '.join('%s %s (%s)' % (p['side'], p['ticker'], p['agreement']) for p in picks) + tail
    elif ((section or {}).get('passed_movers') or (section or {}).get('passed_wild')   # day-135c, day-137
          or (section or {}).get('passed_run')):                                         # day-146
        what = ('%s passed over — %s' % (passed_words(section),
                                          'no council pick' if tail else 'nothing to act on') + tail)
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
        section = top_picks.with_hedge(K.top_two(council))    # day-148c: display only
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
         'against your own quote first.' if _entry_void() else
         'Preliminary. Decided from the previous session\'s data and not yet checked against the '
         'open: check each "wrong if" against your own quote first.'),
        'Research only, not an order. No share counts here; the full report sizes the desks.',
    ])
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div>%s</td></tr>'
            % (email_render.full.escape(subject(session, section).split(' — ', 2)[-1]),
               email_render.direction_html(section)          # day-135: one side, one bet
               + email_render.hedge_html(section)            # day-148c: one side only, its hedge
               + email_render.mover_html(section)))          # day-135c: the last session's big movers
    return subject(session, section), body, email_render.html_from_text(body, hero=hero)


# ── day-150: one decision at 09:00 ───────────────────────────────────────────
DECISION_SUBJECT = 'RB Morning Decision'
READS_ALONE_AT = dt.time(9, 20)      # no council by now: the release reads go alone
MAX_READS = 8
PRICE_WAIT = 25                      # seconds for the New York prices; late ones are left out


def reads_today(now, path=None):
    """(material, routine): today's pre-open desk calls from its ledger, the
    most confident first. A third party's notice is never shown (amendment 1).
    Never raises: a ledger that cannot be read gives no reads."""
    try:
        import us_preopen as U
        rows = [U._typed(r) for r in U.read_ledger(path or U.LEDGER)
                if r.get('session') == _now(now).date().isoformat()]
        rows = [r for r in rows if r.get('side') in ('LONG', 'SHORT') and not U.notice(r.get('title'))]
    except Exception:
        return [], []
    rows.sort(key=lambda r: (-(r.get('confidence') or 0), r['ticker']))
    return [r for r in rows if r['material']], [r for r in rows if not r['material']]


def new_york_prices(symbols, now, read=None):
    """{US symbol: snapshot} read just before the email, pre-market only. One
    name's failure costs that name's price; the whole read is bounded."""
    now = _now(now)
    symbols = sorted(set(s for s in symbols if s))
    if not symbols or now.time() >= dt.time(9, 30):
        return {}
    import concurrent.futures as cf
    try:
        import us_preopen as U
        read = read or U._reader()
    except Exception:
        return {}
    out = {}
    pool = cf.ThreadPoolExecutor(8)
    jobs = {pool.submit(U.snapshot, read, s, now): s for s in symbols}
    try:
        for job in cf.as_completed(jobs, timeout=PRICE_WAIT):
            try:
                out[jobs[job]] = job.result()
            except Exception:
                continue
    except cf.TimeoutError:
        pass
    pool.shutdown(wait=False, cancel_futures=True)
    return out


def _ny_cell(us, snap, recorded=None):
    """'ARIS 16.14 at 08:58, -3.0% since the US close', or the price at the read."""
    if not us:
        return '—'
    px, at, prev, tag = None, None, None, ''
    if isinstance(snap, dict) and snap.get('px'):
        px, at, prev = snap['px'], str(snap.get('at') or '')[11:16], snap.get('prev_close')
    elif isinstance(recorded, dict) and recorded.get('us_px'):
        px, at, prev = recorded['us_px'], str(recorded.get('us_px_at') or '')[11:16], recorded.get('us_prev_close')
        tag = ' (at the read)'
    if not px:
        return '%s: no fresh pre-market price' % us
    move = ', %+.1f%% since the US close' % (100 * (px / prev - 1)) if prev else ''
    return '%s %.2f at %s%s%s' % (us, px, at or '?', tag, move)


def _wrong(p):
    return ('%s %g' % ('below' if p['side'] == 'LONG' else 'above', p['invalid_at'])
            if isinstance(p.get('invalid_at'), (int, float)) else '—')


def _release_cell(r):
    try:
        at = dt.datetime.fromisoformat(r.get('last_at') or r['first_at']).astimezone(ET).strftime('%a %H:%M')
    except (KeyError, TypeError, ValueError):
        at = ''
    return ('%s %s' % (at, str(r.get('title') or '').replace('|', '/')[:100])).strip() or '—'


def _council_on(council, ticker, side):
    """The council's vote on a position that was on its table, else None."""
    import council as K
    try:
        tally = (council or {}).get('tally') or {}
        rows = {r['id']: r for r in tally.get('rows') or []}
        for p in (council or {}).get('positions') or []:
            if (p['ticker'], p['side']) == (ticker, side) and p['id'] in rows:
                return K._shape(p, rows[p['id']], tally.get('members') or [], None)['verdict'].split(';')[0]
    except Exception:
        return None
    return None


def _claude_named(council, ticker, side):
    """Claude's own confidence when it nominated that position, else None."""
    got = (((council or {}).get('nomination_picks') or {}).get('claude') or {})
    for nom in got.get('longs' if side == 'LONG' else 'shorts') or []:
        if isinstance(nom, dict) and nom.get('ticker') == ticker and isinstance(nom.get('confidence'), (int, float)):
            return nom['confidence']
    return None


def decision_lines(section, reads, why=None):
    """The decision on top: what stands on each side, or why nothing does."""
    import council as K
    out = []
    section = section or {}
    picks = section.get('picks') or []
    if why:
        out.append('- ' + why)
    elif section.get('claude_leads'):
        dropped = section.get('passed_floor') or []
        ran = section.get('passed_run') or []
        for p in picks:                           # what stands first, then why a side is empty
            level = _wrong(p)
            out.append('- %s %s stands: %s. Wrong if: %s.' % (
                p['side'], p['ticker'], p['agreement'], level if level != '—' else 'none given'))
        for side, word in (('LONG', 'long'), ('SHORT', 'short')):
            if any(x['side'] == side for x in picks):
                continue
            d = next((x for x in dropped if x['side'] == side), None)
            if d:
                out.append("- No %s today: Claude's %s %s was below the quality floor (%s)."
                           % (word, side, d['ticker'], K.floor_words(d)))
            elif any(x['side'] == side for x in ran):
                out.append("- No %s today: Claude's %s nominations followed three-day runs, passed over."
                           % (word, word))
            else:
                out.append('- No %s today: Claude named none.' % word)
    elif section.get('no_positions'):
        out.append('- No model proposed a position today, so there is nothing to decide.')
    elif picks:
        who = "the council's pick" if section.get('council') else 'two models agree'
        out += ['- %s %s stands: %s (%s). Wrong if: %s.' % (
            p['side'], p['ticker'], who, p.get('agreement') or '', _wrong(p) if _wrong(p) != '—' else 'none given')
            for p in picks]
    else:
        head = K.passed_head(section)
        out.append('- No pick today: %s.' % (head or 'no position won the council'))
    if reads:
        out.append('- Overnight releases with a call (a separate read; its entry is the New York listing '
                   'before the bell): ' + ' · '.join('%s %s' % (r['side'], r['ticker']) for r in reads) + '.')
    return out


def decision_head(section, reads, why=None):
    """The subject's tail and the hero line."""
    section = section or {}
    picks = section.get('picks') or []
    parts = ['%s %s (%s)' % (p['side'], p['ticker'], p.get('agreement') or '') for p in picks]
    if why:
        parts = ['no council decision yet']
    elif section.get('claude_leads'):
        have = {p['side'] for p in picks}
        parts += ['no %s' % w for s_, w in (('LONG', 'long'), ('SHORT', 'short')) if s_ not in have]
        if not picks:
            parts = ['no pick today']
    elif not picks:
        parts = ['no pick today']
    tail = (' · %d overnight release read%s' % (len(reads), '' if len(reads) == 1 else 's')) if reads else ''
    return ' · '.join(parts) + tail


def _read_rows(council, reads, prices, shown):
    """The table rows of the release reads not already shown beside a pick."""
    rows = []
    for r in reads[:MAX_READS]:
        if (r['ticker'], r['side']) in shown:
            continue
        named = _claude_named(council, r['ticker'], r['side'])
        vote = _council_on(council, r['ticker'], r['side']) or 'not on its table'
        rows.append('| Release read | %s %s (read %.2f) | %s | %s | %s | %s | — | DeepSeek: %s |' % (
            r['side'], r['ticker'], r.get('confidence') or 0,
            ('%.2f' % named) if named is not None else '—', vote, _release_cell(r),
            _ny_cell(r.get('us'), (prices or {}).get(r.get('us')), r),
            str(r.get('reason') or '—').replace('|', '/')[:200]))
    return rows


TABLE_HEAD = ['| What | Name | Claude\'s conf. | Council vote | Overnight release | New York before the bell | Wrong if | Why |',
              '|---|---|---:|---|---|---|---|---|']
READS_NOTE = ('A release read is DeepSeek\'s side on an overnight company release, read from its title and the '
              'feed\'s summary. It is a separate test with no record yet: its entry is the New York listing '
              'before the bell and its registered exit is the 09:30 open. From the open on, the record '
              'shows nothing left (asked the same way, +0.09% from the open to the close, which is noise).')


def compose_decision(council, now, *, reads=None, routine=None, prices=None, twins=None, why=None,
                     record=None):
    """Day-150: (subject, text, html) of the one 09:00 email. `council` None
    (with `why`) is the morning the council has not sat: the reads go alone.
    None when there is neither a council that sat nor a release read."""
    import council as K
    import email_render
    import execution_lab
    import top_picks
    reads, routine, prices, twins = reads or [], routine or [], prices or {}, twins or {}
    sat = isinstance(council, dict) and council.get('status') in SAT
    if not sat and not reads:
        return None
    now = _now(now)
    session = council.get('session') if sat else now.date().isoformat()
    if not sat:
        section = {}
        why = why or 'The council has not sat yet; its decision comes with the 09:46 report.'
    elif council.get('status') == 'NO_POSITIONS':
        section = {'picks': [], 'no_positions': True}
    else:
        section = top_picks.with_hedge(K.top_two(council))
    picks = section.get('picks') or []
    by_read = {r['ticker']: r for r in reads}
    lines = ['## Today\'s decision'] + decision_lines(section, reads, why)
    after = []
    if section.get('claude_leads'):
        dropped = section.get('passed_floor') or []
        lines += ['', '## The picks and the overnight releases'] + TABLE_HEAD
        shown = set()
        for what, group in (('PICK', picks), ('No pick: below the floor', dropped)):
            for p in group:
                r = by_read.get(p['ticker'])
                same = bool(r) and r['side'] == p['side']
                if same:
                    shown.add((r['ticker'], r['side']))
                us = (twins.get(p['ticker']) or {}).get('us')
                conf = '%.2f' % p['confidence'] if isinstance(p.get('confidence'), (int, float)) else '—'
                lines.append('| %s | %s %s | %s | %s | %s | %s | %s | Claude: %s |' % (
                    what, p['side'], p['ticker'], conf,
                    str(p.get('council_vote') or '—').replace('|', '/'),
                    (_release_cell(r) + (' (read: %s %.2f)' % (r['side'], r.get('confidence') or 0))) if r else '—',
                    _ny_cell(us, prices.get(us), r if same else None), _wrong(p),
                    str(p.get('reason') or '—').replace('|', '/')[:200]))
        lines += _read_rows(council, reads, prices, shown)
        after = [x for x in (top_picks.hedge_line(section), top_picks.mover_line(section)) if x]
        after += K.council_lines(section, concise=True) + K.council_lines({'picks': dropped}, concise=True)
        own = K.claude_own_line(section)
        if own:
            after.append(own)
        try:
            import exposure
            line = exposure.exposure_line(picks)
        except Exception:
            line = None
        if line:
            after.append(line)
        if picks:
            after.append(execution_lab.NOON_NOTE)
        after += [x for x in (K.repeat_line(p) for p in picks) if x]
        after += top_picks._notes(section)
    else:
        if sat:
            lines += [''] + top_picks.table(section, concise=True)
        rows = _read_rows(council if sat else None, reads, prices, set())
        if rows:
            lines += ['', '## Overnight releases with a call'] + TABLE_HEAD + rows
    if routine:
        after.append('Routine releases, no call: ' + ' · '.join(
            '%s (%s)' % (r['ticker'], str(r.get('title') or '')[:60]) for r in routine[:8]) + '.')
    if reads:
        after += ['', '## How to read the release reads', READS_NOTE]
        if record:
            after.append(record)
    decided = ((council.get('finished_at') or council.get('asked_at') or '') if sat else '')
    at = decided[11:16] if len(decided) >= 16 else None
    stamp = ('The council decided at %s ET%s; sent %s ET.' % (at, ' (before the open)' if at < '09:30' else '',
                                                              now.strftime('%H:%M'))
             if at else 'Sent %s ET.' % now.strftime('%H:%M'))
    body = '\n'.join([
        '# %s — %s' % (DECISION_SUBJECT, session),
        stamp + ' One more email at 09:31 checks each pick against the open; the full report follows at ~09:46.',
        '',
        *lines,
        *after,
        '',
        '---',
        'Every reason above describes %s, the prior session, and the morning\'s pre-market prints. The '
        '09:31 email gives each pick KEEP, DROP or CAUTION from where it opened.'
        % (_prior(council) if sat else 'the prior session'),
        'Research only, not an order. No share counts here; the full report sizes the desks. No pick is '
        'a prediction: every source on the record is still a coin flip.',
    ])
    head = decision_head(section, reads, why if not sat else None)
    subj = '%s — %s — %s' % (DECISION_SUBJECT, session, head)
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div>%s</td></tr>'
            % (email_render.full.escape(head),
               email_render.direction_html(section) + email_render.hedge_html(section)
               + email_render.mover_html(section)))
    return subj, body, email_render.html_from_text(body, hero=hero)


def _decision(root, council, now, why=None):
    """compose_decision with today's reads, the New York prices and the map."""
    reads, routine = reads_today(now)
    try:
        import us_preopen as U
        twins, record = U.load_twins(), U.record_line(U.LEDGER)
    except Exception:
        twins, record = {}, None
    sat = isinstance(council, dict) and council.get('status') in SAT
    picked = []
    if sat and council.get('status') != 'NO_POSITIONS':
        try:
            import council as K
            sec = K.top_two(council)
            picked = [p['ticker'] for p in (sec.get('picks') or []) + (sec.get('passed_floor') or [])]
        except Exception:
            picked = []
    symbols = [r.get('us') for r in reads[:MAX_READS]] + [(twins.get(t) or {}).get('us') for t in picked]
    try:
        prices = new_york_prices(symbols, now)
    except Exception:
        prices = {}
    return compose_decision(council if sat else None, now, reads=reads, routine=routine, prices=prices,
                            twins=twins, why=why, record=record)


def _entry_void():
    """Whether the 09:46 report still drops a pick past its \"wrong if\" (day-144: off)."""
    import entry_checks
    return entry_checks.VOID_TOP2


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
    waiting = (council.get('status') == 'UNAVAILABLE'
               and any(w in str(council.get('reason')) for w in ('not staged', 'not today')))
    kind = 'council'
    fallback = None
    if waiting:
        # Day-150: with no council by 09:20 the release reads go alone, and say so.
        if not (COMBINED and now.time() >= READS_ALONE_AT and reads_today(now)[0]):
            return 'WAITING', {}
        try:
            made, kind = _decision(root, None, now), 'reads_only'
        except Exception:                 # nothing to fall back on: keep waiting for the council
            return 'WAITING', {}
    elif COMBINED:
        try:
            made = _decision(root, council, now, why=(
                None if council.get('status') in SAT else
                'The council did not sit today (%s); the 09:46 report decides the Top 2 by the counted '
                'rule.' % str(council.get('reason') or council.get('status'))[:120]))
            kind = 'council' if council.get('status') in SAT else 'reads_only'
        except Exception as exc:          # the new email must never cost the one it replaced
            made, fallback = compose(council, now), type(exc).__name__
    else:
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
                                   'council_status': council.get('status'), 'kind': kind,
                                   **({'fell_back_to_the_flash': fallback} if fallback else {}),
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


# ── day-135 (owner, 2026-10-15): a stop that cannot be reached is no stop ────
# That morning the open check said STILL VALID for SHORT CLS.TO and SHORT CCO.TO,
# and both lost. It could not have said anything else: their "wrong if" levels,
# set from the prior session's chart, sat 12.0% and 7.9% above the 09:31 price,
# 1.8 and 2.0 normal days (ATR) away. The verdict (day-120 E1) is unchanged; the
# check now says how far the level is and whether an ordinary day could reach
# it, and how much of the move the open had already made before any entry.
# Display only: nothing is recorded, voided or sized differently.
REACH_ATR = 1.0


def reach(side, level, price, atr_pct):
    """How far `price` must move to reach the position's own "wrong if":
    {'pct', 'days' (in ATR, None when the ATR is unknown), 'out_of_reach' (more
    than REACH_ATR normal days; None when unknown)}. None without a level or a
    price, or when the level is already crossed (that is E1's VOID)."""
    if not all(isinstance(v, (int, float)) and v > 0 for v in (level, price)):
        return None
    pct = 100.0 * ((level / price - 1.0) if side == 'SHORT' else (1.0 - level / price))
    if pct <= 0:
        return None
    days = pct / atr_pct if isinstance(atr_pct, (int, float)) and atr_pct > 0 else None
    return {'pct': pct, 'days': days, 'out_of_reach': None if days is None else days > REACH_ATR}


def atr_map(root, now, tickers):
    """{ticker: ATR as % of the prior close} from today's brief, the rows every
    model saw. Display only: a missing or stale brief gives {}, and then each
    distance prints in % with no reach call."""
    import claude_opportunities as C
    try:
        rows = C.read_brief(root, now)['payload']['candidates']
    except Exception:
        return {}
    return {r['ticker']: float(r['atr_pct']) for r in rows
            if r.get('ticker') in tickers and isinstance(r.get('atr_pct'), (int, float))
            and r['atr_pct'] > 0}


def check_open(council, now, *, quote=None, atr=None):
    """One row per council pick: the E1 verdict on today's live quote, and the facts."""
    import council as K
    import entry_checks
    import exposure
    quote = quote or fmp_quote
    atr = atr or {}
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
        gap = _pct(q.get('open'), q.get('previousClose'))
        a = atr.get(p['ticker'])
        rows.append({**p, 'verdict': {'VOID': 'VOID', 'OK': 'STILL VALID'}.get(verdict, verdict),
                     'price': q['price'], 'at': at.strftime('%H:%M'),
                     'open': q.get('open'), 'prev_close': q.get('previousClose'),
                     'open_for_pick': sign * gap if gap is not None else None,
                     'open_days': sign * gap / a if gap is not None and a else None,
                     'now_for_pick': (sign * _pct(q['price'], q.get('previousClose'))
                                      if _pct(q['price'], q.get('previousClose')) is not None else None),
                     'atr_pct': a, 'reach': reach(p['side'], p.get('invalid_at'), q['price'], a),
                     'etf': x['etf'], 'etf_move': etf_move})
        moved = rows[-1]['now_for_pick']          # day-150: the verdict's two facts
        rows[-1]['now_days'] = moved / a if moved is not None and a else None
        rows[-1]['vs_sector'] = (moved - sign * etf_move if moved is not None and etf_move is not None
                                 and x['etf'] else None)
    return rows


# ── day-150: KEEP / DROP / CAUTION at 09:31 ──────────────────────────────────
# The owner, 2026-11-10: "another at 9:31 because it would look at the data
# points and technicals at market open to adjust if needed in case it already
# spiked or tanked". Fixed rules on the live quote, registered before the
# first use; not a forecast, and nothing is voided (day-144).
MOVED_ATR = 1.0
OPEN_LEDGER = Path(__file__).resolve().parent/'data'/'reviews'/'open_checks.csv'
OPEN_FIELDS = ('session', 'ticker', 'side', 'decision', 'why', 'e1', 'price', 'at', 'prev_close', 'open',
               'open_for_pick', 'now_for_pick', 'open_days', 'now_days', 'atr_pct', 'invalid_at',
               'etf', 'etf_move', 'vs_sector', 'checked_at')


def open_decision(r):
    """('KEEP' | 'DROP' | 'CAUTION', why) for one checked pick, in the
    registered order: no live quote; past its own \"wrong if\"; already one
    normal day or more from the prior close, either way; otherwise KEEP."""
    if r.get('price') is None:
        return 'CAUTION', 'not checked: %s' % (r.get('why') or 'no live quote')
    if r.get('verdict') == 'VOID':
        return 'DROP', 'already past its own "wrong if"'
    d = r.get('now_days')
    if d is not None and d <= -MOVED_ATR:
        return 'CAUTION', 'already %s against it' % _days(d)
    if d is not None and d >= MOVED_ATR:
        return 'CAUTION', 'already %s its way; an entry now does not get that part' % _days(d)
    if d is None:
        return 'KEEP', 'not past its "wrong if"; its normal range is unknown'
    return 'KEEP', 'nothing at the open contradicts it'


def reads_at_open(reads, now, *, quote, atr=None):
    """Where the Toronto listing of each release read opened, signed to the read."""
    rows = []
    for r in (reads or [])[:MAX_READS]:
        sign = 1 if r['side'] == 'LONG' else -1
        try:
            q = quote(r['ticker'])
        except Exception:
            q = None
        at = _live(q, now)
        row = {'ticker': r['ticker'], 'side': r['side'], 'us': r.get('us'), 'title': r.get('title')}
        if at is not None:
            gap, moved = _pct(q.get('open'), q.get('previousClose')), _pct(q['price'], q.get('previousClose'))
            a = (atr or {}).get(r['ticker'])
            row.update(price=q['price'], at=at.strftime('%H:%M'),
                       open_for_read=sign * gap if gap is not None else None,
                       now_for_read=sign * moved if moved is not None else None,
                       now_days=sign * moved / a if moved is not None and a else None)
        rows.append(row)
    return rows


def read_words(x):
    """What the open says about a release read. No verdict: its window ended at the open."""
    if x.get('price') is None:
        return 'not checked: no live quote'
    d, m = x.get('now_days'), x.get('now_for_read')
    if d is not None and d >= MOVED_ATR:
        return 'moved its way by %s: the news is in the price' % _days(d)
    if d is not None and d <= -MOVED_ATR:
        return 'moved against the read by %s' % _days(d)
    if m is None:
        return 'no prior close to compare'
    return ('little reaction so far' if abs(m) < 0.5 else
            'moved its way, less than a normal day' if m > 0 else 'moved against the read, less than a normal day')


def record_open_checks(rows, now, path=None):
    """One row per checked pick in `data/reviews/open_checks.csv`, once a day.
    Atomic; a row already there for the session and name is never rewritten."""
    import csv
    import io
    import os
    path = Path(path or OPEN_LEDGER)
    now = _now(now)
    session = now.date().isoformat()
    old = list(csv.DictReader(io.StringIO(path.read_text()))) if path.is_file() else []
    have = {(r.get('session'), r.get('ticker'), r.get('side')) for r in old}
    new = []
    for r in rows:
        if r.get('runner_up') or (session, r['ticker'], r['side']) in have:
            continue
        word, why = open_decision(r)
        new.append({'session': session, 'ticker': r['ticker'], 'side': r['side'], 'decision': word,
                    'why': why, 'e1': r.get('verdict'), 'price': r.get('price'), 'at': r.get('at'),
                    'prev_close': r.get('prev_close'), 'open': r.get('open'),
                    'open_for_pick': r.get('open_for_pick'), 'now_for_pick': r.get('now_for_pick'),
                    'open_days': r.get('open_days'), 'now_days': r.get('now_days'),
                    'atr_pct': r.get('atr_pct'), 'invalid_at': r.get('invalid_at'), 'etf': r.get('etf'),
                    'etf_move': r.get('etf_move'), 'vs_sector': r.get('vs_sector'),
                    'checked_at': now.isoformat(timespec='seconds')})
    if not new:
        return 0
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=OPEN_FIELDS, extrasaction='ignore', lineterminator='\n')
    w.writeheader()
    for r in old + new:
        w.writerow({k: ('' if r.get(k) is None else ('%.4f' % r[k]).rstrip('0').rstrip('.')
                        if isinstance(r.get(k), float) else r[k]) for k in OPEN_FIELDS})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'w') as f:
        f.write(out.getvalue())
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    return len(new)


def compose_open_decision(council, rows, now, section=None, reads=None):
    """Day-150: the 09:31 email — one verdict per pick, and where each release
    read opened. None when there is neither a pick nor a read to check."""
    import council as K
    import email_render
    import top_picks
    reads = reads or []
    if not rows and not reads:
        return None
    now = _now(now)
    session = (council or {}).get('session') or now.date().isoformat()
    for r in rows:
        r['decision'], r['decision_why'] = open_decision(r)
    verdicts = ' · '.join('%s%s %s %s' % ('runner-up ' if r.get('runner_up') else '', r['decision'],
                                           r['side'], r['ticker']) for r in rows)
    if not rows:
        verdicts = 'no pick today · %d release read%s at the open' % (len(reads), '' if len(reads) == 1 else 's')
    elif all(r.get('runner_up') for r in rows):
        verdicts = 'no council pick · ' + verdicts
    subj = 'RB Open Check — %s — %s' % (session, verdicts)
    lines = ['# RB Open Check — %s' % session,
             'Checked at %s ET against the live quote (FMP last trade). The full report follows at ~09:46.'
             % now.strftime('%H:%M')]
    if rows:
        lines += ['', '## The 09:00 picks at the open',
                  '| Pick | Verdict | Why | Price now | Open vs prior close, for the pick | Now vs prior close, for the pick | Against its sector fund | Wrong if | Wrong if, from here |',
                  '|---|---|---|---|---|---|---|---|---|']
        for r in rows:
            price = ('%g at %s' % (r['price'], r['at'])) if r.get('price') is not None else '—'
            now_cell = _fmt(r.get('now_for_pick')) + (
                ' (%s)' % _days(r['now_days']) if r.get('now_days') is not None else '')
            sector = ('%s vs %s' % (_fmt(r.get('vs_sector')), r['etf']) if r.get('vs_sector') is not None
                      else '—')
            lines.append('| %s %s%s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
                r['side'], r['ticker'],
                ' (runner-up, %s)' % K.runner_up_label(r) if r.get('runner_up') else '',
                r['decision'], r['decision_why'], price, _opened(r), now_cell, sector, _wrong(r),
                _distance(r) if r.get('price') is not None else '—'))
        picks = top_picks.with_hedge({'picks': [r for r in rows if not r.get('runner_up')]})
        for line in (top_picks.direction_line(picks), top_picks.hedge_line(picks)):
            if line:
                lines.append(line)
    else:
        picks = {}
        why = K.passed_head(section) if section else None
        lines += ['', 'No pick stood at 09:00%s, so there is no verdict to give.' % ((': ' + why) if why else '')]
    if reads:
        lines += ['', '## The overnight releases at the open (Toronto listing)',
                  '| Read | Price now | Open vs prior close, for the read | Now vs prior close, for the read | What the open says |',
                  '|---|---|---|---|---|']
        for x in reads:
            price = ('%g at %s' % (x['price'], x['at'])) if x.get('price') is not None else '—'
            now_cell = _fmt(x.get('now_for_read')) + (
                ' (%s)' % _days(x['now_days']) if x.get('now_days') is not None else '')
            lines.append('| %s %s | %s | %s | %s | %s |' % (x['side'], x['ticker'], price,
                                                          _fmt(x.get('open_for_read')), now_cell, read_words(x)))
        lines.append('No verdict is given on a release read: its own window ended at the open. Asked the '
                     'same way on 419 past releases, the read made +0.09% from the open to the close, '
                     'which is noise.')
    lines += ['',
              '## How to read it',
              'KEEP, DROP and CAUTION are fixed rules on where the price is, not a forecast. DROP: the '
              'price is already past the pick\'s own "wrong if", so the reason it was chosen is proven '
              'wrong today. CAUTION: it has already moved one normal day (ATR) or more from the prior '
              'close, either way, or it could not be checked. KEEP: neither. On this record a move '
              'already made is a reason in neither direction (day-132).',
              'A "wrong if" more than one normal day from the price is OUT OF REACH: an ordinary day '
              'would not touch it, so it does not limit a loss. A positive "for the pick" figure is a '
              'move the pick\'s way. The 09:46 report keeps every pick the 09:00 email named: the '
              'verdict is for you to weigh.',
              'Research only, not an order.']
    body = '\n'.join(lines)
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div>%s</td></tr>'
            % (email_render.full.escape(verdicts),
               email_render.direction_html(picks) + email_render.hedge_html(picks)))
    return subj, body, email_render.html_from_text(body, hero=hero)


def _fmt(v):
    return '—' if v is None else '%+.2f%%' % v


def _days(v):
    return '%.1f normal day%s' % (abs(v), '' if round(abs(v), 1) == 1.0 else 's')


def _distance(r):
    """The "Wrong if, from here" cell (day-135)."""
    if not isinstance(r.get('invalid_at'), (int, float)):
        return 'no "wrong if" given: no stop at all'
    x = r.get('reach')
    if x is None:
        return '—'
    if x['days'] is None:
        return '%.1f%% away (normal range unknown)' % x['pct']
    return ('%.1f%% away = %s%s' % (x['pct'], _days(x['days']),
                                   ': OUT OF REACH, not a usable stop' if x['out_of_reach'] else ''))


def _opened(r):
    v = _fmt(r.get('open_for_pick'))
    return v if r.get('open_days') is None else '%s (%s)' % (v, _days(r['open_days']))


def _verdict_text(r):
    out = '%s%s %s %s' % ('runner-up ' if r.get('runner_up') else '', r['side'], r['ticker'], r['verdict'])
    if r['verdict'] == 'STILL VALID' and (r.get('reach') or {}).get('out_of_reach'):
        out += ', stop out of reach'
    return out


def compose_open(council, rows, now, section=None):
    import council as K
    import email_render
    import top_picks
    session = council.get('session')
    if not rows:
        return None
    verdicts = ' · '.join(_verdict_text(r) for r in rows)
    # Only the runner-up is left (no consensus, or day-135c's big-mover rule
    # took the picks): the subject must not read like a pick to trade.
    only_runner = all(r.get('runner_up') for r in rows)
    if only_runner:
        verdicts = 'no council pick · ' + verdicts
    why = K.passed_head(section) if section else None
    subj = 'RB Open Check — %s — %s' % (session, verdicts)
    lines = ['# RB Open Check — %s' % session,
             'Checked at %s ET against the live quote (FMP last trade). The full report follows at ~09:46.'
             % _now(now).strftime('%H:%M')]
    if only_runner:
        lines.append('No council pick today%s. The runner-up is checked because it is shown; it is not '
                     'a pick.' % ((': ' + why) if why else ''))
    lines += ['',
             '| Pick | Verdict | Wrong if | Wrong if, from here | Price now | Open vs prior close, for the pick | Now vs prior close, for the pick | Sector ETF since prior close |',
             '|---|---|---|---|---|---|---|---|']
    for r in rows:
        wrong = ('%s %g' % ('below' if r['side'] == 'LONG' else 'above', r['invalid_at'])
                 if isinstance(r.get('invalid_at'), (int, float)) else '—')
        price = ('%g at %s' % (r['price'], r['at'])) if r.get('price') is not None else r.get('why', '—')
        lines.append('| %s %s%s | %s | %s | %s | %s | %s | %s | %s %s |' % (
            r['side'], r['ticker'],
            ' (runner-up, %s)' % K.runner_up_label(r) if r.get('runner_up') else '',
            r['verdict'], wrong, _distance(r) if r.get('price') is not None else '—', price,
            _opened(r), _fmt(r.get('now_for_pick')), r.get('etf') or '—', _fmt(r.get('etf_move'))))
    picks = top_picks.with_hedge({'picks': [r for r in rows if not r.get('runner_up')]})
    direction = top_picks.direction_line(picks)
    if direction:
        lines.append(direction)
    hedged = top_picks.hedge_line(picks)          # day-148c: one side only, its hedge
    if hedged:
        lines.append(hedged)
    moved = ['%s %s %s %s' % (r['side'], r['ticker'],
                              'opened %.1f%% its way' % r['open_for_pick'] if r['open_for_pick'] >= 0
                              else 'opened %.1f%% against it' % -r['open_for_pick'],
                              '(%s)' % _days(r['open_days']) if r.get('open_days') is not None else '')
             for r in rows if r.get('open_for_pick') is not None]
    if moved:
        lines.append('Already moved at the open, before any entry: %s. An entry now does not get that '
                     'part of the move. On this record a move already made is a reason in neither '
                     'direction (day-132).' % '; '.join(m.strip() for m in moved))
    lines += ['',
              'VOID means the price is already past the position\'s own "wrong if": the reason it was '
              'chosen is proven wrong today. STILL VALID means only that it is not; it is not a '
              'forecast. A "wrong if" more than one normal day\'s move (ATR) from the price is OUT OF '
              'REACH: an ordinary day would not touch it, so it does not limit a loss. A positive '
              '"for the pick" figure is a move the pick\'s way.'
              + ('' if _entry_void() else ' The 09:46 report no longer drops a VOID pick (day-144): '
                 'the verdict is for you to weigh.'),
              'Research only, not an order.']
    body = '\n'.join(lines)
    hero = ('<tr><td style="padding:22px 26px;background:#f4f7f9;border-bottom:1px solid #dde4ea">'
            '<div style="font:600 15px/1.45 Arial,sans-serif;color:#17212b">%s</div>%s</td></tr>'
            % (email_render.full.escape(verdicts),
               email_render.direction_html(picks) + email_render.hedge_html(picks)))
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
    reads = reads_today(now)[0] if COMBINED else []        # day-150: the release reads are checked too
    sat = council.get('status') in SAT
    if not sat and not reads:
        return 'NOTHING', {'reason': 'no council today, so nothing to check'}
    sec = K.top_two(council) if sat and council.get('status') != 'NO_POSITIONS' else {}
    if not sec.get('picks') and not sec.get('runner_up') and not reads:
        return 'NOTHING', {'reason': 'the council chose no position, so nothing to check'}
    if now.time() < OPEN_AT:
        return 'WAITING', {}
    items = (sec.get('picks') or []) + ([sec['runner_up']] if sec.get('runner_up') else [])
    quote = quote or (lambda sym: fmp_quote(sym, root))
    atr = atr_map(root, now, {p['ticker'] for p in items} | {r['ticker'] for r in reads})
    rows = check_open(council, now, quote=quote, atr=atr) if items else []
    made = None
    if COMBINED:
        try:
            made = compose_open_decision(council if sat else None, rows, now, section=sec,
                                         reads=reads_at_open(reads, now, quote=quote, atr=atr))
        except Exception:                     # the new email must never cost the one it replaced
            made = None
        try:                                  # the record never costs the email
            record_open_checks(rows, now)
        except Exception:
            pass
    if made is None:
        if not rows:
            return 'NOTHING', {'reason': 'nothing could be checked'}
        made = compose_open(council, rows, now, section=sec)
    subj, text, html = made
    out = root/OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    for name, content in (('open_subject.txt', subj), ('open_report.txt', text), ('open_report.html', html)):
        (out/name).write_text(content, encoding='utf-8')
    write_atomic(out/'open_plan.json', {'session': now.date().isoformat(), 'subject': subj,
                                        'rows': [{k: r.get(k) for k in ('ticker', 'side', 'verdict', 'price',
                                                                        'at', 'atr_pct', 'reach', 'open_days',
                                                                        'decision', 'decision_why', 'now_days')}
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
            if code == 0:
                try:
                    import dda_hooks
                    dda_hooks.start(a.state_dir, 'open-check')
                except Exception:
                    pass  # No change to the existing email or its schedule.
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
