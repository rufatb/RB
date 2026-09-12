"""Concise email views of the frozen computation; full evidence is attached."""
import daily_render as full
import biotech

fmt = full.fmt


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
    if 'deepseek' in intra:
        lines += ['',*full.deepseek_summary(intra)]
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
    lines.append(f"Exact net/index evidence: {exact['scored_legs']} scored legs / {exact['complete_sessions']} sessions; "
                 f"net {fmt(exact.get('mean_net_pct'),'+.3f')}%, selection versus index {fmt(exact.get('mean_selection_net_pct'),'+.3f')}%.")
    errors=d.get('errors',[])
    if errors:
        from collections import Counter
        counts=Counter((e['layer'],e['error']) for e in errors)
        lines.append('Acquisition: '+'; '.join(f"{layer}: {error}"+(f" ({n})" if n>1 else '') for (layer,error),n in counts.items()))
    if bio.get('errors'):lines.append('Biotech coverage: '+bio['errors'][0][:180]+('… Details attached.' if len(bio['errors'][0])>180 or len(bio['errors'])>1 else ''))
    provider=intra.get('historical_provider',{})
    if provider and provider.get('status')!='NOT CONFIGURED':
        lines.append(f"EODHD history: {provider['status']}; 5-minute history {provider['intraday_status']}. No live selection change.")
    lines += ['H1/H2 cost overlays and earlier exits: shadow. Overnight and opening-path research: unadopted.',
              'Code: '+str(d.get('provenance',{}).get('code_commit') or 'not recorded')[:12]]
    return '\n'.join(lines)


def html(d):
    return full.markdown_html(text(d))
