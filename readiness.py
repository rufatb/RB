"""Pure section-level readiness. Successful email delivery is not data readiness."""
def assess(report):
    gaps = []
    res = report['intraday']['res']
    if res.get('coverage_fail') or not res.get('n_names'):
        gaps.append('Intraday scan not fully evaluated; preserve any recorded board separately.')
    if report['intraday']['benchmark']['status'] != 'OK':
        gaps.append('Matched executable index/BBO data unavailable.')
    invalid = [l['ticker'] for l in report['intraday'].get('legs', [])
               if l.get('status') not in ('SHADOW', 'ELIGIBLE')
               or l.get('quote', {}).get('status') != 'OK']
    if invalid:
        gaps.append('Selected legs without valid execution observations: ' + ', '.join(invalid) + '.')
    if report['biotech']['status'] == 'UNAVAILABLE':
        gaps.append('Strict biotech universe/ranking unavailable; calendar is not a Top-2 substitute.')
    if not report.get('research_calendar',{}).get('events'):
        gaps.append('No current source-reviewed catalyst calendar has been prepared.')
    if report['positions']['legs']:
        gaps.append('Recorded holdings require brokerage/user reconciliation.')
    if report['positions']['stale']:
        gaps.append('One or more holdings have no live mark; dated references are not live P&L.')
    if report['positions'].get('status') in ('UNAVAILABLE','PARTIAL'):
        gaps.extend(report['positions'].get('gaps') or ['Position ledger unavailable or incomplete; holdings are unknown.'])
    if report['intraday']['record'].get('status') in ('UNAVAILABLE','PARTIAL'):
        gaps.append('Historical ledger evidence unavailable or incomplete; do not interpret displayed counts as full coverage.')
    factor=report['intraday'].get('deepseek')
    if factor is not None and factor.get('status')!='READY':
        gaps.append('Optional DeepSeek factor coverage incomplete; baseline sections remain independent and factor research is unadopted.')
    gaps=list(dict.fromkeys(gaps))
    return {'status':'PARTIAL' if gaps else 'READY', 'gaps':gaps}
