"""Concise email views of the frozen computation; full evidence is attached."""
import daily_render as full
import biotech

fmt = full.fmt


ARTIFACT_URL = 'https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9'

# THE EMAIL IS THE PICKS (day-114b). The owner, 2026-09-23: "there are warnings
# and fluff in the email body". It carried a dispatch disclaimer, the engine's
# historical record, MDE, cache and provider faults, the shadow factor layer's
# UNAVAILABLE lines, a record-hole warning, five standing disclosures and a code
# hash — around four tickers. Every one of those facts is still in the full
# report (brief.render_text / the artifact page); the email now carries what a
# portfolio manager reads at 09:50: each desk's sized picks and why, the
# scoreboard, the engine as one comparison table, biotech, one footer line.


def _reason_lines(snap):
    out = []
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for pick in snap.get(key) or []:
            reason = full.safe_detail(pick.get('reason') or '', 170)
            out.append(f"- {side} {pick['ticker']}" + (f": {reason}" if reason else ''))
    return out


def _jev_lines(snap):
    """Jev's selection, and — when it declined — its ranking and forced pick,
    each labelled for what it is. Never sized, never merged into a selection."""
    out = []
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for pick in snap.get(key) or []:
            out.append(f"- {side} {pick['ticker']}: probability {fmt(pick.get('probability'))} "
                       f"vs {fmt(pick.get('abstain_probability'))} for choosing nothing")
    if snap.get('longs') or snap.get('shorts'):
        return out
    ranked = []
    for side, key in (('LONG', 'long_ranked'), ('SHORT', 'short_ranked')):
        top = (snap.get(key) or [None])[0]
        if top:
            ranked.append(f"{side} {top['ticker']} {fmt(top.get('probability'))} "
                          f"vs none {fmt(top.get('abstain_probability'))}")
    if ranked:
        out.append('Jev selected nothing: every name ranked below its own "none". '
                   'Top-ranked (not selections): ' + '; '.join(ranked) + '.')
    forced = []
    for side, key in (('LONG', 'forced_long'), ('SHORT', 'forced_short')):
        f = snap.get(key)
        if f:
            forced.append(f"{side} {f['ticker']} {fmt(f.get('probability'))}"
                          + ('' if f.get('cleared_gated_abstain') else ' (below its "none")'))
    if forced:
        out.append('If forced to pick: ' + '; '.join(forced) + '. Not selections; never sized.')
    return out


def desk_sections(intra):
    """Part 1's three desks — Claude, DeepSeek, Jev — each in its own section.

    Every desk prints EVERY day, answered or not: the owner reads them side by
    side, and a desk that silently vanished would look like one that had nothing
    to say. Nothing is averaged across desks."""
    desks = intra.get('desks') or []
    if not desks:
        return []
    out = []
    for n, desk in enumerate(desks, 1):
        snap = intra.get(desk.get('evidence_key')) or {}
        out += ['', f"### {n} · {desk.get('source')}"]
        if desk.get('legs'):
            # The table only: the sizing sentence is in the footer and the
            # reason for a missing size is said once, just below.
            out += [l for l in full.desk_lines(desk)[2:] if not l.startswith('Not sized:')]
            why = sorted({r for l in desk['legs'] for r in l.get('reasons') or []})
            if why:
                out.append('No share count: ' + '; '.join(full.safe_detail(r, 90) for r in why) + '.')
        elif snap.get('status') == 'NO_OPPORTUNITY' and desk.get('id') != 'jev':
            out.append('No pick today: the model found nothing worth a position on either side.')
        elif desk.get('id') != 'jev' or snap.get('status') not in ('READY', 'NO_OPPORTUNITY'):
            out.append(f"Unavailable today — {full.safe_detail(desk.get('reason') or 'no answer', 160).rstrip('.')}.")
        out += _jev_lines(snap) if desk.get('id') == 'jev' else _reason_lines(snap)
        if snap.get('independence'):
            out.append('Sealed ' + full.safe_detail(snap['independence'], 120)
                       .replace('sealed at ', '') + '.')
    return out + _scoreboard(intra.get('scoreboard'))


def _scoreboard(board):
    if not board:
        return []
    out = ['', '### Scoreboard', '| Source | Right | Mean per pick | Sessions | 95% range |',
           '|---|---:|---:|---:|---|']
    for r in board:
        if not r['picks']:
            out.append(f"| {r['source']} | — | — | 0 | not yet scored |")
            continue
        lo, hi = r['ci95']
        out.append(f"| {r['source']} | {r['hits']}/{r['picks']} ({r['rate']:.0%}) | "
                   f"{r['mean_r_pct']:+.2f}% | {r['sessions']} | {lo:.0%}–{hi:.0%} |")
    out.append('09:45 price to the close, no costs. A range that contains 50% is a coin flip.')
    return out


def _engine_lines(intra):
    legs = intra.get('legs') or []
    recorded = [r for r in intra.get('recorded_today', []) if r.get('role') == 'pair']
    out = ['', '### Baseline engine (k-NN) — comparison only']
    if legs:
        out += ['| Status | Name / side | Shares | 09:45 bar |', '|---|---|---:|---:|']
        for l in legs:
            # No share count on an abstained leg: a row with a size is an order
            # ticket whatever its status says (acted on twice, day-98).
            shares = '—' if l['status'] == 'ABSTAIN' else l['baseline_shares']
            out.append(f"| {l['status']} | {l['ticker']} {l['side']} | {shares} | "
                       f"{fmt(l.get('signal_reference'))} |")
    elif recorded:
        out.append('Recorded board: ' + ', '.join(f"{r['ticker']} {r['side']}" for r in recorded) + '.')
    else:
        res = intra.get('res') or {}
        out.append('No selection today.' if res.get('n_names') and not res.get('coverage_fail')
                   else 'SCAN UNAVAILABLE — not evaluated today; that is not a finding of '
                        'no opportunities.')
    for g in (intra.get('risk_evidence') or {}).get('concentration', []):
        out.append(f"{' and '.join(g['tickers'])} are one {str(g['group']).replace('_', ' ')} bet, "
                   f"not {len(g['tickers'])}.")
    return out


def _factor_lines(intra):
    """The factor layer only when it produced a lean. It is shadow research;
    an UNAVAILABLE or all-neutral day belongs in the full report, not here."""
    rows = [r for r in (intra.get('deepseek') or {}).get('assessments') or []
            if r.get('directional_lean') in ('BULL', 'BEAR')]
    if not rows:
        return []
    out = ['', '### Headline sentiment — DeepSeek factor layer (research only)']
    for r in sorted(rows, key=lambda r: -abs(r.get('sentiment_score') or 0))[:4]:
        out.append(f"- {r['directional_lean']} {r['ticker']} {fmt(r.get('sentiment_score'), '+.2f')}: "
                   f"{full.safe_detail(r.get('factor_rationale') or '', 150)}")
    return out


def _biotech_lines(d):
    bio = d.get('biotech') or {}
    out = ['', '## Part 2 — Biotech catalysts · 3–6 months',
           'Factual scheduled events; no directional call.']
    for e in bio.get('monitor') or []:
        out += ['', '### ' + e['ticker']]
        for i, (label, value) in enumerate(zip(biotech.LABELS, e['bullets'])):
            out.append(f"- **{label}:** {value}" + (f" [Source]({e['source_url']})" if i == 0 else ''))
    calendar = (d.get('research_calendar') or {}).get('events') or []
    if calendar:
        out += ['', '### Upcoming calendar — unranked, uncertified']
    for e in calendar[:4]:
        out.append(f"- {e['ticker']} · {e['window_start']}–{e['window_end']}: "
                   f"{e['asset']} / {e['stage']}, {e['kind']}. [Source]({e['source_url']})")
    if not bio.get('monitor') and not calendar:
        n = bio.get('universe_n')
        out.append('No reviewed catalyst event in the window today'
                   + (f" across {n} certified names." if n else '.'))
    return out


def _positions_lines(d):
    book = d.get('positions') or {}
    broken = book.get('status') in ('UNAVAILABLE', 'PARTIAL')
    if not book.get('legs') and not book.get('recent_closed') and not broken:
        return []
    out = ['', '## Positions']
    # A ledger that could not be read is NOT an empty book: say so, or an
    # absence of rows reads as "no positions" (house rule 2).
    if book.get('status') == 'UNAVAILABLE':
        out.append('Position ledger UNAVAILABLE; current holdings are unknown.')
    elif book.get('status') == 'PARTIAL':
        out.append(f"Position ledger PARTIAL; {book.get('invalid_rows', 0)} malformed rows "
                   'excluded. Holdings may be incomplete.')
    for p in book.get('legs') or []:
        out.append(f"- {p['ticker']} {p['side']}: {p['shares']:g} @ {p['entry_px']:.2f}; "
                   f"mark {fmt(p.get('mark'))}; P&L {fmt(p.get('pnl_pct'), '+.2f')}%"
                   + ('; RECONCILE — exit date passed' if p.get('event_overdue') else ''))
    for p in book.get('recent_closed') or []:
        out.append(f"- Recorded CLOSED {p['ticker']}: {p['shares']:g} @ {p['exit_px']:.2f} on "
                   f"{p['exit_date']}, {p['pnl_pct']:+.2f}% before costs")
    return out


def text(d):
    intra = d['intraday']
    delivery = d.get('delivery') or {}
    status = str(d.get('report_status') or '')
    lines = [f"# RB Daily Report — {d['session']}",
             delivery.get('note') or f"Published {str(d.get('generated_at') or '')[11:16]} ET."]
    # A late, offline or diagnostic board says so in the body, not only the
    # subject — the day-95 rule, kept. An on-time board carries no label.
    if status and not status.startswith('ON_TIME'):
        lines.insert(1, status)
    if d.get('replacement'):
        lines += ['', '## Requested replacement',
                  'Original morning computation retained; no recovered or fresh entry signal is claimed.',
                  *d['replacement']['notes']]
    lines += ['', '## Part 1 — Intraday picks · enter 09:46, exit 15:59 ET']
    if intra.get('desks'):
        lines += desk_sections(intra)
        lines += _engine_lines(intra)
    else:
        # A publication from before the desks: the engine board, then the two
        # model sections exactly as they were printed at the time.
        lines += _engine_lines(intra)[2:]
        if full.opportunities_reported(intra):
            lines += ['', *full.opportunities_summary(intra, concise=True)]
        if full.jev_reported(intra):
            lines += ['', *full.jev_summary(intra, concise=True)]
    lines += _factor_lines(intra)
    lines += _biotech_lines(d)
    lines += _positions_lines(d)
    sizing = next((dk.get('sizing') for dk in intra.get('desks') or [] if dk.get('sizing')), None)
    lines += ['', '---',
              'Research only: share counts are hypothetical'
              + (f" (an equal split of {sizing['book']:,.0f} per desk)" if sizing else '')
              + ', not orders. Confidences are each model\'s own number and are never averaged.',
              f'Full report, sources and history: {ARTIFACT_URL}']
    return '\n'.join(lines)


# ── the newsletter view ──────────────────────────────────────────────────────
#
# The email was `markdown_html(text(d))`: the plain-text report with tags
# wrapped round it. Every line became a paragraph of the same weight, so the
# board, the two model sections and the standing terms all looked equally
# urgent and the whole thing read as a wall of warnings. This renders the SAME
# lines as a newsletter — a hero stating the one decision, then cards, then the
# terms once at the end, small.
#
# It renders from `text(d)`, deliberately: a second renderer reading `d` again
# would be a second implementation of every number in the email, and this repo
# has been bitten by exactly that (`subject_state`, the staged cache, the
# credential loader). One computation, two views.
#
# EMAIL-SAFE ONLY. Gmail strips <style> blocks, CSS variables, @media and
# class selectors, so every rule here is an inline attribute on its own
# element. No web fonts, no flexbox, no grid.

INK, MUTED, RULE = '#17212b', '#5c6b7a', '#dde4ea'
CARD, WASH, ACCENT = '#ffffff', '#f4f7f9', '#1f5c66'
BADGES = {'ABSTAIN': ('#6b7280', '#eef0f2'), 'RECORDED': ('#6b7280', '#eef0f2'),
          'SHADOW': ('#1f5c66', '#e4f0f1'), 'ELIGIBLE': ('#1f5c66', '#e4f0f1')}


def _badge(value):
    colour, wash = BADGES.get(value.strip().upper(), (INK, WASH))
    return (f'<span style="display:inline-block;padding:3px 9px;border-radius:3px;'
            f'background:{wash};color:{colour};font:600 11px/1.4 Arial,sans-serif;'
            f'letter-spacing:.07em;text-transform:uppercase">{full.escape(value)}</span>')


def _hero(d):
    """The one thing the reader needs before scrolling: is there anything to do.

    Derived from the legs, not from prose, and it says ABSTAINED when they are
    abstained. A neutral hero over a board nobody should act on is the same
    failure `subject_state` exists to prevent, one surface along."""
    intra = d.get('intraday') or {}
    from primary_board import headline_legs
    legs = headline_legs(intra)
    abstained = [l for l in legs if str(l.get('status')).upper() == 'ABSTAIN']
    why = sorted({r for l in abstained for r in l.get('reasons') or []})
    if legs and len(abstained) == len(legs):
        head = 'No sized pick today'
        sub = (f'All {len(legs)} picks are shown below without share counts'
               + (f' — {why[0]}.' if len(why) == 1 else '.'))
    elif legs and abstained:
        head = f'{len(legs) - len(abstained)} of {len(legs)} picks carry a share count'
        sub = f'{len(abstained)} are shown without one; the reason is under each desk.'
    elif legs:
        head, sub = f'{len(legs)} picks sized', 'Share counts use the 09:46 ET prices.'
    else:
        head, sub = 'No picks today', 'Each desk below says why.'
    return (f'<tr><td style="padding:22px 26px;background:{WASH};border-bottom:1px solid {RULE}">'
            f'<div style="font:600 19px/1.35 Georgia,serif;color:{INK}">{full.escape(head)}</div>'
            f'<div style="font:14px/1.55 Arial,sans-serif;color:{MUTED};margin-top:7px">'
            f'{full.escape(sub)}</div></td></tr>')


def _cells(line):
    return [c.strip() for c in line.strip('|').split('|')]


def _table(rows, first):
    """`first` is the header row. The Status column becomes a badge; everything
    else is escaped text."""
    out = [f'<table role="table" width="100%" cellpadding="0" cellspacing="0" '
           f'style="width:100%;border-collapse:collapse;font:13px/1.45 Arial,sans-serif;'
           f'margin:14px 0">'
           '<tr>' + ''.join(
               f'<th align="left" style="padding:8px 10px;border-bottom:2px solid {RULE};'
               f'color:{MUTED};font:600 11px/1.4 Arial,sans-serif;letter-spacing:.07em;'
               f'text-transform:uppercase">{full.escape(c)}</th>' for c in first) + '</tr>']
    for row in rows:
        cells = []
        for n, cell in enumerate(row):
            body = (_badge(cell) if n == 0 and cell.strip().upper() in BADGES
                    else full.escape(cell))
            cells.append(f'<td style="padding:9px 10px;border-bottom:1px solid {RULE};'
                         f'color:{INK};vertical-align:top">{body}</td>')
        out.append('<tr>' + ''.join(cells) + '</tr>')
    return ''.join(out) + '</table>'


def _body_blocks(body):
    """Walk the concise report's own lines and emit newsletter blocks."""
    import re
    out, table, small = [], None, False

    def flush():
        nonlocal table
        if table:
            out.append(_table(table[1:], table[0]))
            table = None

    for line in body.splitlines()[2:]:          # the H1 and send line are the masthead
        if line.startswith('|'):
            cells = _cells(line)
            if all(re.fullmatch(r'[-:]+', c) for c in cells):
                continue
            table = (table or []) + [cells]
            continue
        flush()
        if line == '---':
            small = True
            out.append(f'<div style="height:1px;background:{RULE};margin:22px 0 8px"></div>')
            continue
        if line.startswith('## '):
            title = line[3:]
            # The terms section is the one block that is deliberately quiet.
            small = title.startswith('How to read')
            out.append(f'</td></tr><tr><td style="padding:24px 26px 6px">'
                       f'<div style="font:600 12px/1.4 Arial,sans-serif;color:{ACCENT};'
                       f'letter-spacing:.11em;text-transform:uppercase">{full.escape(title)}</div>'
                       f'<div style="height:2px;background:{ACCENT};width:34px;margin:9px 0 4px"></div>')
        elif line.startswith('### '):
            out.append(f'<div style="font:600 15px/1.4 Georgia,serif;color:{INK};'
                       f'margin:20px 0 2px">{full.escape(line[4:])}</div>')
        elif line.startswith('- ') or line.startswith('  '):
            out.append(f'<div style="font:13px/1.55 Arial,sans-serif;color:{INK};'
                       f'margin:3px 0 3px 14px;padding-left:10px;'
                       f'border-left:2px solid {RULE}">{full.escape(line.strip("- ").strip())}</div>')
        elif line:
            size, colour = ('12px', MUTED) if small else ('14px', INK)
            out.append(f'<p style="font:{size}/1.6 Arial,sans-serif;color:{colour};'
                       f'margin:9px 0">{full.escape(line)}</p>')
    flush()
    return ''.join(out)


def html(d):
    body = text(d)
    head = body.splitlines()[0].lstrip('# ')
    stamp = body.splitlines()[1] if len(body.splitlines()) > 1 else ''
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>RB Daily Report</title></head>'
        f'<body style="margin:0;padding:0;background:{WASH}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{WASH};padding:20px 0"><tr><td align="center">'
        f'<table role="presentation" width="640" cellpadding="0" cellspacing="0" '
        f'style="width:640px;max-width:100%;background:{CARD};border:1px solid {RULE}">'
        f'<tr><td style="padding:26px 26px 20px;border-bottom:3px solid {INK}">'
        f'<div style="font:600 11px/1.4 Arial,sans-serif;color:{ACCENT};letter-spacing:.14em;'
        f'text-transform:uppercase">Morning research note · not an order</div>'
        f'<div style="font:600 27px/1.2 Georgia,serif;color:{INK};margin-top:8px">'
        f'{full.escape(head)}</div>'
        f'<div style="font:12px/1.5 Arial,sans-serif;color:{MUTED};margin-top:8px">'
        f'{full.escape(stamp)}</div></td></tr>'
        + _hero(d) +
        f'<tr><td style="padding:0 26px 26px">{_body_blocks(body)}</td></tr>'
        '</table></td></tr></table></body></html>')
