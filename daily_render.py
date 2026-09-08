"""Pure text/HTML renderers. No imports of providers, clocks or persistence.

Tables preserve the full intraday board. Biotech Monitor entries always have
exactly five bullets. Both renderers consume the same immutable report model.
"""
from __future__ import annotations
from html import escape
import biotech


def fmt(value, spec='.2f'):
    return 'unknown' if value is None else format(value,spec)


def text(d):
    intra=d['intraday']; res=intra['res']; rec=intra['record']
    lines=[f"# RB Daily Report — {d['session']}",
           f"As of {d['generated_at']} · {d['report_status']} · {d['clock']['status']}",
           '', '## Part 1 — Intraday Opportunities',
           intra['contract']+'. Signal reference: 09:45 completed bar; execution quote is separate.',
           intra['model_claim'], '',
           f"Historical baseline: {rec['hits']}/{rec['n']} gross hits ({fmt(rec['rate'],'.1%')}); "
           f"mean capture {fmt(rec['mean'],'+.3f')}%.",
           f"Net of stored spread: {fmt(rec.get('net_rate'),'.1%')} hits; "
           f"mean {fmt(rec['net_mean'],'+.3f')}% on {rec['net_n']} legs; "
           f"unpriced {rec['net_unpriced']}.",rec['label'],rec['benchmark_label'],
           '', '### Selected baseline legs — shadow tracking', '',
           '| Name | Side | Signal reference | 09:46 quote | Spread | Baseline allocation | Status |',
           '|---|---|---:|---:|---:|---:|---|']
    for l in intra['legs']:
        lines.append(f"| {l['ticker']} | {l['side']} | {l['signal_reference']:.2f} | "
                     f"{fmt(l['entry_reference'])} | {fmt(l['entry_spread_bps'])} bps | "
                     f"${l['baseline_alloc']:,.0f} / {l['baseline_shares']} shares | {l['status']} |")
    if not intra['legs']:
        recorded=[r for r in intra.get('recorded_today',[]) if r.get('role')=='pair']
        for r in recorded:
            lines.append(f"| {r['ticker']} | {r['side']} | {r.get('p945','unknown')} | unverified | "
                         f"{r.get('spread_bps') or 'unknown'} bps stored proxy | {r.get('shares') or 'unknown'} recorded shares | RECORDED — not a fresh entry |")
        if not recorded:
            unavailable=res.get('coverage_fail') or not res.get('n_names')
            lines.append('| '+('Scan not evaluated' if unavailable else 'No qualifying baseline legs')+
                         ' | — | — | — | — | — | '+('DATA UNAVAILABLE' if unavailable else 'NO TRADE')+' |')
    if intra.get('recorded_today'):
        lines += ['', '### Already recorded session board',
                  'Preserved published baseline selections; not new entries, confirmed holdings, or exact 09:46 fills.', '',
                  '| Name | Side | Role | Recorded signal reference | Recorded shares | Stored spread proxy |',
                  '|---|---|---|---:|---:|---:|']
        for r in intra['recorded_today']:
            lines.append(f"| {r['ticker']} | {r['side']} | {r.get('role','')} / {r.get('leg','')} | "
                         f"{r.get('p945','unknown')} | {r.get('shares') or 'not allocated'} | {r.get('spread_bps') or 'unknown'} bps |")
    for l in intra['legs']:
        lines += ['', f"{l['ticker']}: {l['role']}, density {l['density_tag']}; diagnostic sided-P "
                  f"{l['p_sided']:.3f}. Fill bound {l['fill_bound']:.2f}; quote as of "
                  f"{l['entry_time'] or 'unknown'}. " + ('; '.join(l['reasons']) or 'Shadow observation only.'),
                  f"Research only: spread/vol {fmt(l['spread_density'],'.1%')}; "
                  f"H1 {'keep' if l['h1_keep'] else 'abstain'}; H2 allocation multiplier {l['h2_scale']:.3f}."]
    lines += ['', '### Full intraday opportunity board', '',
              '| Name | Side | Sided-P (diagnostic) | Density | First 15m | Gap | Volume ratio |',
              '|---|---|---:|---|---:|---:|---:|']
    for side in ('longs','shorts'):
        for p in res.get(side,[]):
            prob=p['p_up'] if side=='longs' else 1-p['p_up']
            lines.append(f"| {p['t']} | {'LONG' if side=='longs' else 'SHORT'} | {prob:.3f} | "
                         f"{p.get('confidence','unknown')} | {fmt(p.get('r0'),'+.2f')}% | "
                         f"{fmt(p.get('gap'),'+.2f')}% | {fmt(p.get('vp'))} |")
    if not res.get('longs') and not res.get('shorts'):
        for r in intra.get('recorded_today',[]):
            lines.append(f"| {r['ticker']} | {r['side']} | {r.get('p_sided') or 'unknown'} | "
                         f"{r.get('confidence') or 'unknown'} | not stored | not stored | not stored |")
    if res.get('coverage_fail'):
        lines += ['', 'Coverage: '+res['coverage_fail']]
    lines += ['', f"Freshly evaluated names: {res.get('n_names',0)}. Recorded qualifiers: {len(intra.get('recorded_today',[]))}. Source: {res.get('source','unavailable')}."]
    for r in res.get('excluded',[]):
        lines.append(f"Excluded {r['t']}: {r.get('excluded_reason','peer conflict')}")
    exact=intra['exact_record']
    lines += ['', '### Execution evidence',
              f"Independent benchmark: {intra['benchmark_symbol']} — {intra['benchmark']['status']}. "
              'Exact net/index scoring requires matched entry and exit BBOs; no index-relative win claim without them.',
              f"Exact-window record: {exact['scored_legs']} scored legs / {exact['complete_sessions']} complete sessions; net hit {fmt(exact['net_hit_rate'],'.1%')}; decisive net hit {fmt(exact['decisive_net_hit_rate'],'.1%')}.",
              f"Mean net {fmt(exact['mean_net_pct'],'+.3f')}%; tide {fmt(exact['mean_tide_pct'],'+.3f')}%; selection net {fmt(exact['mean_selection_net_pct'],'+.3f')}%. Unscored legs: {exact['unscored_legs']}.",
              'Gross = tide + selection; net = gross − spread − fees − slippage. '
              'Long-minus-short and net exposure are evaluated separately on original capacity.',
              '09:46→15:30 and 09:46→15:45 remain shadow experiments. Overnight remains unadopted.',
              '', biotech.render(d['biotech'])]
    calendar=d.get('research_calendar',{})
    lines += ['', '## Daily / weekly catalyst calendar',
              calendar.get('label','Unranked research calendar — not certified Monitor picks.')]
    for event in calendar.get('events',[]):
        lines += ['', f"### {event['ticker']} — {event['horizon']}",
                  f"{event['kind']}: {event['window_start']} to {event['window_end']}; {event['asset']} / {event['indication']} / {event['stage']}.",
                  'New information: '+event['new_information'], 'Known: '+event['known_data'],
                  '3–6 month read-through: '+event['read_throughs'],
                  f"Source: {event['source_url']}"]
    if not calendar.get('events'):
        lines.append('No current reviewed calendar supplied — research coverage gap, not absence of catalysts.')
    for gap in calendar.get('gaps',[]): lines.append('Calendar evidence gap: '+gap)
    book=d['positions']
    lines += ['', '## Existing position marks',
              book.get('verification','Recorded ledger; current holdings not independently verified.'),
              f"{len(book['legs'])} recorded open positions; {book['stale']} unmarkable and excluded from live totals."]
    for l in book['legs']:
        lines.append(f"{l['ticker']} {l['side']}: {l['shares']:g} recorded shares, entry {l['entry_px']:.2f} "
                     f"on {l.get('entry_date','unknown')}, {l['days']} days held in ledger; live mark {fmt(l.get('mark'))}; "
                     f"live P&L {fmt(l.get('pnl_pct'),'+.2f')}%; recorded exit: {l.get('exit_condition','unspecified')}.")
        if l.get('event_overdue'):
            lines.append('RECONCILE: recorded event/exit date has passed; no exit fill or continued holding verified.')
        ref=l.get('reference',{})
        if ref.get('status')=='OK':
            lines.append(f"Dated reference only: {ref['session']} close {ref['close']:.2f}; "
                         f"reference P&L {ref['pnl_pct']:+.2f}% / {ref['pnl_usd']:+.2f}, assuming unchanged recorded holding. "
                         f"Not included in live totals. Source: {ref['source_url']}")
        elif l.get('stale'):
            lines.append('Price evidence gap: '+l.get('quote_reason','No validated live quote.'))
    if d.get('readiness',{}).get('gaps'):
        lines += ['', '## Readiness gaps']+d['readiness']['gaps']
    if d['errors']:
        lines += ['', '## Data and delivery diagnostics']
        lines += [f"{e['layer']}: {e['error']} — {e['detail']}" for e in d['errors']]
    lines += ['', f"Research: {d['research']['registration']} — {d['research']['status']}. {d['research']['mde']}",
              'No order was placed. Hypothetical baseline allocation is for comparison; the strategy overlays are not adopted.']
    return '\n'.join(lines)


def html(d):
    # Small renderer for our controlled Markdown subset; escape ALL source
    # content. No raw HTML/script from filings, symbols or issuer notes survives.
    import re
    def inline(value):
        parts=[];last=0
        for match in re.finditer(r'\[([^\]]+)\]\((https://[^\s)]+)\)',value):
            parts.append(escape(value[last:match.start()]))
            url=match.group(2)
            parts.append('<a href="'+escape(url,quote=True)+'">'+escape(match.group(1))+'</a>'
                         if biotech.evidence_url(url) else escape(match.group(0)))
            last=match.end()
        parts.append(escape(value[last:]))
        return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',''.join(parts))
    rendered=[]; table=False; bullet=False
    for line in text(d).splitlines():
        if not line.startswith('|') and table:
            rendered.append('</tbody></table>');table=False
        if not line.startswith('- ') and bullet:
            rendered.append('</ul>');bullet=False
        if line.startswith('|'):
            cells=[escape(x.strip()) for x in line.strip('|').split('|')]
            if all(re.fullmatch(r'[-:]+',x) for x in cells):
                continue
            if not table:
                rendered.append('<table><tbody>');table=True
            rendered.append('<tr>'+''.join('<td>'+x+'</td>' for x in cells)+'</tr>')
        elif line.startswith('- '):
            if not bullet:
                rendered.append('<ul>');bullet=True
            rendered.append('<li>'+inline(line[2:])+'</li>')
        elif line.startswith('#'):
            level=min(3,len(line)-len(line.lstrip('#')))
            rendered.append(f'<h{level}>'+escape(line.lstrip('# '))+f'</h{level}>')
        elif line:
            rendered.append('<p>'+escape(line)+'</p>')
    if table: rendered.append('</tbody></table>')
    if bullet: rendered.append('</ul>')
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>RB Daily Report</title><style>body{font:15px system-ui,sans-serif;color:#182437;background:#f5f7fa;'
            'max-width:1180px;margin:32px auto;padding:0 24px}h1{color:#0a3658}h2{border-top:3px solid #23627e;'
            'padding-top:20px;margin-top:36px}table{width:100%;border-collapse:collapse;background:white;font-size:13px}'
            'td{padding:9px;border-bottom:1px solid #d9e2eb;text-align:left}tr:first-child{font-weight:700;background:#e9f0f5}'
            'p,li{line-height:1.55}li{margin-bottom:10px}h3{color:#315b70}</style></head><body>'
            +''.join(rendered)+'</body></html>')
