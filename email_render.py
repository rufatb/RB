"""Concise email views of the frozen computation; full evidence is attached."""
import daily_render as full
import biotech

fmt = full.fmt


def primary_lines(intra):
    """Part 1's headline: the primary source's picks, sized, and the leaderboard.

    Owner decision 2026-09-22 (see primary_board). Same share-count rule as the
    engine: an ABSTAIN leg shows no size, whatever else the row says."""
    p = intra.get('primary')
    if not p:
        return []
    out = ['', f"### Today's picks — {p.get('source', 'DeepSeek')} (primary source)"]
    if not p.get('legs'):
        out.append(f"No primary picks today: {full.safe_detail(p.get('reason') or 'unavailable', 200)}. "
                   'The baseline engine below is shown for comparison only.')
    else:
        sized = sum(l['status'] != 'ABSTAIN' for l in p['legs'])
        sizing = p.get('sizing') or {}
        out.append(f"{len(p['legs'])} picks; {sized} carry a size"
                   + (f" (equal split of {sizing['book']:,.0f}, {sizing['per_leg']:,.0f} per leg, "
                      "each in its listing's currency)" if sizing.get('per_leg') else '')
                   + '. Hypothetical, not orders.')
        out += ['', '| Status | Name / side | Shares | 09:46 price | Spread | Confidence | Wrong if |',
                '|---|---|---:|---:|---:|---:|---|']
        for l in p['legs']:
            shares = '—' if l['status'] == 'ABSTAIN' else l['baseline_shares']
            wrong = (f"{'below' if l['side'] == 'LONG' else 'above'} {fmt(l.get('invalid_at'))}"
                     if isinstance(l.get('invalid_at'), (int, float)) else '—')
            out.append(f"| {l['status']} | {l['ticker']} {l['side']} | {shares} | "
                       f"{fmt(l.get('entry_reference'))} {l.get('currency') or ''} | "
                       f"{fmt(l.get('entry_spread_bps'), '.1f')} bps | {fmt(l.get('confidence'))} | {wrong} |")
        why = sorted({r for l in p['legs'] for r in l.get('reasons') or []})
        if why:
            out.append('Not sized: ' + '; '.join(full.safe_detail(r, 120) for r in why))
        import exposure
        for g in p.get('exposure') or []:
            out.append('⚠ ' + exposure.line(g, p.get('source', 'DeepSeek')))
    board = p.get('leaderboard') or []
    if board:
        out += ['', 'Scored record, every source on one yardstick (09:45 bar to close, no costs):',
                '| Source | Right | Mean per pick | Sessions | 95% interval |', '|---|---:|---:|---:|---|']
        for r in board:
            if not r['picks']:
                out.append(f"| {r['source']} | — | — | 0 | not yet scored |")
                continue
            lo, hi = r['ci95']
            out.append(f"| {r['source']} | {r['hits']}/{r['picks']} ({r['rate']:.0%}) | "
                       f"{r['mean_r_pct']:+.2f}% | {r['sessions']} | {lo:.0%}–{hi:.0%} |")
        out.append('A handful of sessions resolves nothing: an interval that contains 50% is '
                   'a coin flip, whichever source it belongs to.')
    return out


def text(d):
    intra=d['intraday']; res=intra['res']; legs=intra.get('legs',[])
    recorded=[r for r in intra.get('recorded_today',[]) if r.get('role')=='pair']
    delivery=d.get('delivery',{})
    lines=[f"# RB Daily Report — {d['session']}", d['report_status'],
           f"Snapshot {d['generated_at'][11:19]} ET"+
           (f" · Dispatch {delivery['checked_at'][11:19]} ET" if delivery else ''),
           'Full board, sources and diagnostics: attached HTML report.']
    if d.get('report_status') != 'ON_TIME':
        lines.append('Informational; no fresh morning entry claim.')
    if d.get('replacement'):
        lines += ['','## Requested replacement',
                  'Original morning computation retained; no recovered or fresh entry signal is claimed.',
                  *d['replacement']['notes']]
    lines += ['', '## Part 1 — Intraday · 09:46–15:59 ET']
    lines += primary_lines(intra)
    if intra.get('primary'):
        lines += ['', '### Baseline engine (k-NN) — comparison only',
                  'No demonstrated edge: 809 walk-forward legs at 50.1%, live 48.6% over 107. '
                  'Kept on the record and on the leaderboard; no longer the headline.']
    if legs or recorded:
        valid=sum(l.get('status') in ('SHADOW','ELIGIBLE') and l.get('quote',{}).get('status')=='OK' for l in legs)
        lines += [f"{len(legs) or len(recorded)} baseline legs; {valid} execution-verified. Hypothetical selections, not orders."]
        if not valid:
            lines.append('ABSTAIN / RECORDED ONLY — entries are unverified.')
        lines += ['', '| Status | Name / side | Shares | 09:45 bar | 09:46 quote | Spread |',
                  '|---|---|---:|---:|---:|---:|']
        for l in legs:
            # No share count on an abstained leg. The email is what gets read
            # at 09:46 on a phone, and a row with a share count is an order
            # ticket no matter what the Status column says — twice now it was
            # acted on. See daily_render for the full note.
            shares = '—' if l['status'] == 'ABSTAIN' else l['baseline_shares']
            lines.append(f"| {l['status']} | {l['ticker']} {l['side']} | {shares} | "
                         f"{fmt(l.get('signal_reference'))} | {fmt(l.get('entry_reference'))} | {fmt(l.get('entry_spread_bps'))} bps |")
        if not legs:
            for r in recorded:
                lines.append(f"| RECORDED | {r['ticker']} {r['side']} | {r.get('shares') or 'unknown'} | "
                             f"{r.get('p945') or 'unknown'} | unverified | {r.get('spread_bps') or 'unknown'} proxy bps |")
        reasons=sorted({reason for leg in legs for reason in leg.get('reasons',[])})
        if reasons: lines.append('Entry gaps: '+'; '.join(reasons))
    elif res.get('coverage_fail') or res.get('clock_error') or not res.get('n_names'):
        lines += ['SCAN UNAVAILABLE — no validated new entries; the scan did not establish whether opportunities existed.']
    else:
        lines.append(f"Evaluated {res['n_names']} names; no qualifying baseline selections.")
    lines.append(f"Coverage: {res.get('n_names',0)} evaluated; {len(intra.get('recorded_today',[]))} recorded qualifiers.")
    groups = intra.get('risk_evidence', {}).get('concentration', [])
    for g in groups:
        lines.append(f"Common exposure: {', '.join(g['tickers'])} — {g['side']} {g['group']}; "
                     f"{fmt(g['gross_share'], '.0%')} of gross allocation"+
                     (f", {fmt(g['side_share'], '.0%')} of the {g['side']} side" if g.get('side_share') is not None else '')+
                     '. These names can lose together.')
    history = res.get('training_history', [])
    if history:
        lines.append(f"Training: {sum(h['accepted_sessions'] for h in history)} complete ticker-sessions; "
                     f"{sum(h['rejected_sessions'] for h in history)} excluded; audit attached.")
    # The concise email carries the FACTOR SECTION only when the factor layer
    # has something to say. It is shadow, unadopted, and changes no selection,
    # so with no staged snapshot it produced five consecutive UNAVAILABLE lines
    # describing an experiment that did not run — noise that crowded out the
    # board on a phone at 09:46. Nothing is swallowed: the attached full report
    # keeps every diagnostic verbatim, and `factor_note` states the absence in
    # one line among the gaps (house rule 1).
    if 'deepseek' in intra and full.factor_reported(intra):
        lines += ['',*full.deepseek_summary(intra, concise=True)]
    # Same rule for the model's own picks: carried when it answered, silent in
    # the concise email when it did not, and never reduced to an UNAVAILABLE
    # line. The absence still appears once in the attached full report.
    if full.opportunities_reported(intra):
        lines += ['',*full.opportunities_summary(intra, concise=True)]
    if full.jev_reported(intra):
        lines += ['',*full.jev_summary(intra, concise=True)]
    book=d['positions']
    lines += ['', '## Positions'+(' — original snapshot' if d.get('replacement') else '')]
    if book.get('status')=='UNAVAILABLE':
        lines.append('Position ledger UNAVAILABLE; current holdings are unknown.')
    elif book.get('status')=='PARTIAL':
        lines.append(f"Position ledger PARTIAL; {book.get('invalid_rows',0)} malformed rows excluded. Holdings may be incomplete.")
    elif not book['legs']:
        lines.append('No open positions recorded; current holdings are not independently reconciled.')
    if book.get('gaps'):
        lines.append('Position gap: '+full.safe_detail(book['gaps'][0],180))
    for p in book['legs']:
        lines.append(f"{p['ticker']} {p['side']}: {p['shares']:g} shares @ {p['entry_px']:.2f}; "
                     f"{p['days']} days in ledger; live mark {fmt(p.get('mark'))}; P&L {fmt(p.get('pnl_pct'),'+.2f')}%.")
        ref=p.get('reference',{})
        if ref.get('status')=='OK':
            lines.append(f"Prior-session reference: {ref['session']} close {ref['close']:.2f}; not live. [{ref.get('provider','Data source')}]({ref['source_url']})")
        if p.get('event_overdue'): lines.append('RECONCILE: recorded exit/event date has passed.')
    for p in book.get('recent_closed',[]):
        lines.append(f"Recorded CLOSED {p['ticker']}: {p['shares']:g} shares @ {p['exit_px']:.2f} on {p['exit_date']}; gross {p['pnl_usd']:+.2f} / {p['pnl_pct']:+.2f}% before costs.")
    bio=d['biotech']
    lines += ['', '## Part 2 — Biotech Monitor · 3–6 months',
              f"{len(bio['monitor'])}/2 certified Monitor issuers. Factual events; no directional call."]
    if not bio['monitor']:
        lines.append('Certification unavailable; see data gaps.' if bio['status']=='UNAVAILABLE' or not bio.get('screened_events')
                     else 'No Monitor result among the evaluated events; crowded and unverified events remain separate.')
    for e in bio['monitor']:
        lines += ['', '### '+e['ticker']]
        for i,(label,value) in enumerate(zip(biotech.LABELS,e['bullets'])):
            lines.append(f"- **{label}:** {value}"+(f" [Source]({e['source_url']})" if i==0 else ''))
    if bio['crowded']:
        lines += ['', '### Crowded / High-Expectations appendix',
                  '; '.join(e['ticker'] for e in bio['crowded'])+' — suppressed; indicators in attachment.']
    calendar=d.get('research_calendar',{}).get('events',[])
    if calendar:
        lines += ['', '### Upcoming calendar — unranked, uncertified']
        for e in calendar[:4]:
            lines.append(f"- **{e['ticker']} · {e['window_start']}–{e['window_end']}:** "
                         f"{e['asset']} / {e['stage']}, {e['kind']}. [Issuer/event source]({e['source_url']})")
        if len(calendar)>4:lines.append(f"{len(calendar)-4} further reviewed events in attachment.")
    rec=intra['record']; risk=intra.get('risk_evidence',{}); rate=risk.get('rate',{}); exact=intra['exact_record']
    lines += ['', '## Evidence & gaps']
    if rec.get('status')=='UNAVAILABLE':
        lines.append('Historical record UNAVAILABLE; hit rates and returns are unknown.')
    else:
        if rec.get('status')=='PARTIAL':
            lines.append(f"Historical record PARTIAL: {rec.get('invalid_rows',0)} invalid rows excluded; source records retained.")
        lines.append(f"Historical gross proxy: {rec['hits']}/{rec['n']} hits ({fmt(rec['rate'],'.1%')}); "
              f"mean {fmt(rec.get('mean'),'+.3f')}% per leg. "
              f"Net proxy {fmt(rec.get('net_rate'),'.1%')}, mean {fmt(rec.get('net_mean'),'+.3f')}% "
              f"on {rec['net_n']} legs, {rec['net_unpriced']} unpriced. "
              f"MDE80 {fmt(rate.get('mde80_pp'))} percentage points; scores are not calibrated win probabilities.")
    gap = full.record_gap_line(rec)
    if gap:
        lines.append(gap)
    lines += full.cache_lines(res)
    # Exact-window evidence begins at zero and stays there until collect_execution
    # has captured matched entry and exit BBOs. Saying "0 scored legs, net
    # unknown%, selection unknown%" every morning reads as a fault; it is a
    # study that has not started. Say that once, plainly.
    if exact['scored_legs']:
        lines.append(f"Exact net/index evidence: {exact['scored_legs']} scored legs / {exact['complete_sessions']} sessions; "
                     f"net {fmt(exact.get('mean_net_pct'),'+.3f')}%, selection versus index {fmt(exact.get('mean_selection_net_pct'),'+.3f')}%.")
    else:
        lines.append('Exact net/index evidence: not yet accumulating — matched 09:46/15:59 '
                     'execution quotes are required and none are recorded. The proxy record above is what exists.')
    note = full.factor_note(intra)
    if note:
        lines.append(note)
    errors=d.get('errors',[])
    if errors:
        from collections import Counter
        counts=Counter((e['layer'],full.plain_fault(e)) for e in errors)
        lines.append('Acquisition faults: '+'; '.join(f"{layer} — {fault}"+(f" (×{n})" if n>1 else '') for (layer,fault),n in counts.items())+'.')
    if bio.get('errors'):
        lines.append('Biotech coverage: '+full.plain_fault({'error':bio['errors'][0],'layer':'biotech'})+
                     ('' if len(bio['errors'])==1 else f" (+{len(bio['errors'])-1} more, attached)")+'.')
    provider=intra.get('historical_provider',{})
    if provider and provider.get('status')!='NOT CONFIGURED':
        lines.append(f"EODHD history: {provider['status']}; 5-minute history {provider['intraday_status']}. No live selection change.")
    lines += ['H1/H2 cost overlays and earlier exits: shadow. Overnight and opening-path research: unadopted.']
    # THE STANDING TERMS, ONCE, AT THE END. Each of these used to be appended to
    # its own section every morning, so the reader scrolled three paragraphs of
    # identical caveat to reach four tickers — which is how a disclosure stops
    # being read. Nothing is dropped: the attached full report still carries
    # each note inside its own section, where the record needs it.
    # EACH TERM IS KEYED ON THE SECTION THAT EARNED IT, exactly as the sections
    # themselves are. Printing all three unconditionally made an old
    # publication that never ran DeepSeek grow the words "never averaged with
    # DeepSeek's confidence" — a frozen report acquiring a mention of a model
    # it never called. Absence of the key means absence of the note.
    terms = ['Research only. Nothing here places, modifies or cancels an order, and no row is a '
             'recommendation. An ABSTAIN leg shows no share count and no dollar figure by design.']
    if full.opportunities_reported(intra):
        terms.append(full.OPPORTUNITIES_STANDING)
    if full.jev_reported(intra):
        terms.append(full.JEV_STANDING)
    if 'deepseek' in intra and full.factor_reported(intra):
        terms.append(full.FACTOR_STANDING)
    if full.opportunities_reported(intra) and full.jev_reported(intra):
        terms.append('The two models are never averaged, and agreement between them is a '
                     'recorded observation, not confirmation.')
    lines += ['', '## How to read this', *terms,
              'Code: '+str(d.get('provenance',{}).get('code_commit') or 'not recorded')[:12]]
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
    legs = ((intra.get('primary') or {}).get('legs') or []) or intra.get('legs') or []
    abstained = [l for l in legs if str(l.get('status')).upper() == 'ABSTAIN']
    if legs and len(abstained) == len(legs):
        head, sub = 'No actionable entry today', (
            f'All {len(legs)} selected legs abstained. They are shown below as a record of what '
            'the engine computed — not as entries, and with no share count.')
    elif legs and abstained:
        head, sub = (f'{len(legs) - len(abstained)} of {len(legs)} legs carry a verified entry',
                     f'{len(abstained)} abstained and show no share count.')
    elif legs:
        head, sub = f'{len(legs)} legs selected', 'Reference prices are executable only in the 09:46 minute.'
    else:
        head, sub = 'No legs selected', (
            'The scan did not establish that opportunities existed — that is not the same as '
            'establishing there were none.')
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

    for line in body.splitlines()[1:]:          # the H1 is the masthead
        if line.startswith('|'):
            cells = _cells(line)
            if all(re.fullmatch(r'[-:]+', c) for c in cells):
                continue
            table = (table or []) + [cells]
            continue
        flush()
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
    status = str(d.get('report_status') or '')
    stamp = f"Snapshot {str(d.get('generated_at') or '')[11:19]} ET"
    delivery = d.get('delivery') or {}
    if delivery.get('checked_at'):
        stamp += f" · Dispatch {delivery['checked_at'][11:19]} ET"
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
        f'text-transform:uppercase">Research record · not an entry</div>'
        f'<div style="font:600 27px/1.2 Georgia,serif;color:{INK};margin-top:8px">'
        f'{full.escape(head)}</div>'
        f'<div style="font:12px/1.5 Arial,sans-serif;color:{MUTED};margin-top:8px">'
        f'{full.escape(status)} &nbsp;·&nbsp; {full.escape(stamp)}</div></td></tr>'
        + _hero(d) +
        f'<tr><td style="padding:0 26px 26px">{_body_blocks(body)}</td></tr>'
        '</table></td></tr></table></body></html>')
