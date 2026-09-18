"""Pure text/HTML renderers. No imports of providers, clocks or persistence.

Tables preserve the full intraday board. Biotech Monitor entries always have
exactly five bullets. Both renderers consume the same immutable report model.
"""
from __future__ import annotations
from html import escape
import biotech
from diagnostics import safe_detail


def fmt(value, spec='.2f'):
    return 'unknown' if value is None else format(value,spec)


def _factor_wait(snapshot):
    """Describe the stored decision without computing another ranking."""
    shadow=snapshot.get('shadow') or {}
    rows=shadow.get('rows') or []
    if not rows or snapshot.get('status')=='UNAVAILABLE' or any(r.get('status')=='UNAVAILABLE' for r in rows):
        return 'UNEVALUATED / incomplete evidence; absence of candidates is not evidence of no market opportunities.'
    if any((shadow.get('h1') or {}).values()):
        return 'Factor-qualified research names lack exact entry-spread evidence.'
    return 'Evaluated factors did not clear the registered threshold or alignment gate.'


def _expanded_summary(intra):
    coverage = intra.get('research_coverage')
    if not coverage:
        return ''
    mode = coverage.get('mode', 'UNAVAILABLE')
    line = (f"TSX research: target {fmt(coverage.get('target'),'d')}; "
            f"eligible master {fmt(coverage.get('master_eligible'),'d')} "
            f"({coverage.get('master_status','UNAVAILABLE')}); "
            f"pool {fmt(coverage.get('pool_requested'),'d')} ({coverage.get('pool_status','UNAVAILABLE')}); "
            f"prepared technicals {fmt(coverage.get('technical_complete'),'d')}; "
            f"shortlisted {fmt(coverage.get('shortlisted'),'d')}; "
            f"assessed {fmt(coverage.get('assessed'),'d')}.")
    if mode == 'LEGACY_RESEARCH_FALLBACK':
        line += ' Legacy research fallback; expanded directory unavailable.'
    # Baseline names used to be DROPPED on a stale pre-open cache — the only
    # group with no live fallback, and the only group the report trades. They
    # are acquired live now; the reader is told, because a reuse gap means a
    # pre-open staging job did not run.
    reuse = (coverage.get('pool') or {}).get('cache_reuse_gaps') or {}
    if reuse:
        line += (f" Pre-open pool cache DEGRADED for {len(reuse)} name(s); "
                 "acquired live within the same budget, technicals unchanged.")
    sectors = coverage.get('sectors') or []
    if sectors:
        line += ' Sector assessed/pool: '+', '.join(
            f"{safe_detail(row['name'],60)} {row['assessed']}/{row['pool']}" for row in sectors)+'.'
    return line


def _expanded_detail(intra):
    coverage = intra.get('research_coverage')
    if not coverage:
        return []
    lines = ['', '### TSX industry research coverage — unadopted', _expanded_summary(intra),
             'Coverage allocation broadens research attention; it does not set trade-sector quotas or alter baseline selection or weights.',
             'Prepared technicals describe completed sessions. No live quote, alpha or execution approval follows from a coverage count.']
    pool = coverage.get('pool') or {}
    lines.append('Pool validation: '+safe_detail(pool.get('validation','unavailable'))+'.')
    for label, key in [('Sector', 'sectors'), ('Industry', 'industries')]:
        lines += ['', f'| {label} | Pool | Prepared technicals | Shortlisted | Assessed |',
                  '|---|---:|---:|---:|---:|']
        for row in coverage.get(key) or []:
            name = safe_detail(row.get('name','Unverified classification'),100).replace('|',' / ')
            lines.append(f"| {name} | {fmt(row.get('pool'),'d')} | {fmt(row.get('technical_complete'),'d')} | "
                         f"{fmt(row.get('shortlisted'),'d')} | {fmt(row.get('assessed'),'d')} |")
    master = coverage.get('master') or {}
    if master.get('candidates'):
        lines += ['', 'Dated directory observations — no complete-market liquidity-rank claim:',
                  '| Name | Sector / industry | Median daily close × volume, CAD | Reference date | Sources |',
                  '|---|---|---:|---|---|']
        for row in master['candidates']:
            sources = []
            for field, label in [('source_url','Security reference'), ('liquidity_source_url','Daily-bar endpoint')]:
                if row.get(field):
                    sources.append(f"[{label}]({row[field]})")
            for kind, url in (row.get('evidence') or {}).items():
                sources.append(f"[{safe_detail(kind,40)} evidence]({url})")
            classification = safe_detail(str(row.get('sector','Unverified'))+' / '+str(row.get('industry','Unverified')),160).replace('|',' / ')
            lines.append(f"| {safe_detail(row.get('ticker','unknown'),24)} | {classification} | "
                         f"{fmt(row.get('median_dollar_volume_20'),',.0f')} | {row.get('metadata_as_of','unknown')} | "+' · '.join(sources)+' |')
    for gap in coverage.get('gaps') or []:
        lines.append('Expanded research gap: '+safe_detail(gap,500))
    for ticker, reason in (pool.get('errors') or {}).items():
        lines.append(safe_detail(ticker,24)+' research history gap: '+safe_detail(reason,300))
    for key, label in [('master_exclusions','Directory exclusion'),('shortlist_exclusions','Shortlist exclusion')]:
        entries = coverage.get(key) or []
        if isinstance(entries, dict):
            entries = [{'ticker': key, 'reason': value} for key,value in entries.items()]
        for row in entries:
            if isinstance(row, dict):
                lines.append(label+' '+safe_detail(row.get('ticker','unidentified'),24)+': '+
                             safe_detail(row.get('reason') or row.get('reasons') or row.get('gaps') or row,400))
            else:
                lines.append(label+': '+safe_detail(row,400))
    source = coverage.get('source_coverage') or {}
    if source:
        import json
        lines.append('Directory source coverage: '+safe_detail(json.dumps(source,sort_keys=True),1600))
    for ticker, status in (coverage.get('news_status') or {}).items():
        if isinstance(status, dict):
            status = status.get('status', 'UNAVAILABLE')
        lines.append(safe_detail(ticker,24)+' news coverage: '+safe_detail(status,120)+'.')
    lines.append('News NO_CURRENT_NEWS means a completed source response found no current linked article; UNAVAILABLE means the evidence request or validation failed. Neither creates a neutral model prediction.')
    return lines


def _opening_detail(intra):
    context = intra.get('research_opening')
    if not context:
        return []
    lines = ['', '### Expanded opening context — shadow descriptive inputs',
             'Prepared opening context: '+safe_detail(context.get('status','UNAVAILABLE'))+'.',
             'Five-minute VWAP is a bar-based proxy; sector-relative returns and relative volume are descriptive, not adopted entry gates.',
             '| Name | Sector | Status | First 15m % | VWAP proxy | OR high | OR low | RVOL 15m | Sector-relative % | Quote status |',
             '|---|---|---|---:|---:|---:|---:|---:|---:|---|']
    for row in context.get('rows') or []:
        quote = row.get('quote') or {}
        lines.append(f"| {safe_detail(row.get('ticker','unknown'),24)} | {safe_detail(row.get('sector','unknown'),60)} | "
                     f"{safe_detail(row.get('status','UNAVAILABLE'),40)} | {fmt(row.get('opening_return_pct'),'+.3f')} | "
                     f"{fmt(row.get('vwap_5m_proxy'))} | {fmt(row.get('orb_high'))} | {fmt(row.get('orb_low'))} | "
                     f"{fmt(row.get('rvol_15m'))} | {fmt(row.get('sector_relative_return_pct'),'+.3f')} | "
                     f"{safe_detail(quote.get('status','UNAVAILABLE'),40)} |")
        lines.append(safe_detail(row.get('ticker','unknown'),24)+f" opening bar reference: {row.get('bar_reference_time','unavailable')}; "
                     f"RVOL completed-session count: {row.get('rvol_sessions','unknown')}; "
                     f"sector peers: {row.get('sector_peer_count','unknown')}/{row.get('sector_peer_target_count','unknown')}.")
        lines.append(f"09:45 bar reference {fmt(row.get('bar_reference_price'))}; "
                     f"exact quote time {quote.get('quote_time') or 'unavailable'}; "
                     f"bid {fmt(quote.get('bid'))} / ask {fmt(quote.get('ask'))}; "
                     f"spread {fmt(quote.get('spread_bps'))} bps. Bar reference is not an executable quote.")
        for gap in row.get('gaps') or []:
            lines.append(safe_detail(row.get('ticker','unknown'),24)+' opening context gap: '+safe_detail(gap,300))
    for gap in context.get('gaps') or []:
        lines.append('Opening context gap: '+safe_detail(gap,400))
    return lines


def _model_assessed_count(snapshot):
    """Display actual completed model rows without changing ranking counts."""
    grounding = snapshot.get('grounding') or {}
    records = grounding.get('per_ticker')
    return len(records) if isinstance(records, dict) else snapshot.get('covered', 0)


FAULTS = (
    ('FileNotFoundError', 'a staged input file was missing'),
    ('TimeoutExpired', 'the provider did not answer inside its budget'),
    ('RateLimit', 'the provider rate-limited us; remaining names were not requested'),
    ('ConnectionError', 'the provider connection failed'),
    ('HTTPError', 'the provider returned an error status'),
    ('ValueError', 'an input failed validation and was excluded'),
    ('KeyError', 'a provider response was missing an expected field'),
)


def plain_fault(err):
    """Name the fault in words, keeping the exception class for the record.

    An email that says "intraday: ValueError" tells the reader something broke
    and nothing about what it costs them. The exception class is kept — it is
    what makes two mornings comparable — but it is no longer the whole message."""
    raw = str((err or {}).get('error') or 'unknown')
    detail = str((err or {}).get('detail') or '')
    for needle, english in FAULTS:
        if needle in raw or needle in detail:
            return f"{english} ({needle})"
    return safe_detail(raw, 80)


def factor_reported(intra):
    """Does the unadopted factor layer have anything to SAY this morning?

    True when some assessment or coverage figure exists. False when the layer
    simply did not run — no staged snapshot and no coverage — in which case the
    concise email omits the section rather than printing several UNAVAILABLE
    lines about an experiment that produced nothing and changes no selection.
    The full report and `factor_note` still record the absence."""
    snap = intra.get('deepseek') or {}
    if snap.get('assessments') or (snap.get('covered') or 0):
        return True
    if snap.get('status') in ('READY', 'PARTIAL'):
        return True
    coverage = intra.get('research_coverage') or {}
    return bool(coverage.get('assessed') or coverage.get('technical_complete'))


def factor_note(intra):
    """One line for the gaps list when the section itself is omitted."""
    if 'deepseek' not in intra or factor_reported(intra):
        return ''
    snap = intra.get('deepseek') or {}
    reason = safe_detail((snap.get('gaps') or [snap.get('reason') or
                          'inputs were not prepared for this session'])[0], 160)
    return ('Factor research (shadow, unadopted): not evaluated — '+reason+
            ' No selection, size or threshold depends on it.')


def deepseek_summary(intra):
    """At most six concise lines over saved factors; older publications stay unchanged."""
    if 'deepseek' not in intra:
        return ['### TSX factor research — unadopted', _expanded_summary(intra)] if intra.get('research_coverage') else []
    snap=intra['deepseek'] or {}
    shadow=snap.get('shadow') or {}
    watch=snap.get('research_watchlist') or {}
    lines=['### DeepSeek factor research — unadopted',
           f"{safe_detail(snap.get('model') or 'Model unavailable',60)}: {snap.get('status','UNAVAILABLE')}; "
           f"{_model_assessed_count(snap)}/{snap.get('requested',0)} assessed. Contextual leans, not forecasts."]
    if watch and 'input_complete' in watch:
        lines[-1] += (f" Complete inputs: {fmt(watch.get('input_complete'),'d')}; "
                      f"usable assessments: {watch.get('evaluated',0)}.")
    if intra.get('research_coverage'):
        lines[-1] += ' '+_expanded_summary(intra)
    grounding=snap.get('grounding') or {}
    if grounding:
        lines[-1] += (f" {snap.get('covered',0)} accepted after grounding; "
                      f"grounding exclusions: {len(grounding.get('excluded') or {})}; technical statements generated by Python.")
    if watch.get('bulls') or watch.get('bears'):
        bulls=', '.join(safe_detail(r['ticker'],24) for r in watch.get('bulls',[])[:2]) or 'none'
        bears=', '.join(safe_detail(r['ticker'],24) for r in watch.get('bears',[])[:2]) or 'none'
        lines.append(f'SHADOW sentiment watchlist: BULL {bulls}; BEAR {bears}. Factor support only; entries unverified.')
    elif watch:
        line='Sentiment watchlist: '+safe_detail(watch.get('decision','UNAVAILABLE — not evaluated'),180)+'.'
        if watch.get('threshold_evaluated') is False:
            line += ' Threshold NOT EVALUATED.'
        lines.append(line)
    ranked=shadow.get('h2') or {}
    if any(ranked.values()) and snap.get('status') in ('READY','PARTIAL'):
        longs=', '.join(safe_detail(r['ticker'],24) for r in ranked.get('longs',[])[:2]) or 'none'
        shorts=', '.join(safe_detail(r['ticker'],24) for r in ranked.get('shorts',[])[:2]) or 'none'
        lines.append(f'H2 spread-ranked shadow: LONG {longs}; SHORT {shorts}. Research only; no executable recommendations.')
    elif any((shadow.get('h1') or {}).values()) and snap.get('status') in ('READY','PARTIAL'):
        ranked=shadow['h1']
        longs=', '.join(safe_detail(r['ticker'],24) for r in ranked.get('longs',[])[:2]) or 'none'
        shorts=', '.join(safe_detail(r['ticker'],24) for r in ranked.get('shorts',[])[:2]) or 'none'
        lines.append(f'H1 SHADOW factor candidates: LONG {longs}; SHORT {shorts}. COST EVIDENCE UNAVAILABLE — lack exact entry-spread evidence; research only.')
    else:
        reason=_factor_wait(snap)
        unevaluated=(reason.startswith('UNEVALUATED') or
                     str(shadow.get('decision','')).startswith('UNAVAILABLE'))
        unpriced=any((shadow.get('h1') or {}).values())
        prefix='UNAVAILABLE — ' if unevaluated else 'COST EVIDENCE UNAVAILABLE — ' if unpriced else 'NO EDGE - WAIT — '
        lines.append('Quantitative H1/H2: '+prefix+reason)
    gaps=list(snap.get('gaps') or [])+list(shadow.get('gaps') or [])
    if not gaps:
        # A per-name input failure can leave the top-level gap list empty.
        # Keep its actual cause visible instead of showing only UNAVAILABLE.
        for notes in (snap.get('candidate_gaps') or {}).values():
            gaps.extend(notes or [])
    if gaps:
        unique=list(dict.fromkeys(gaps))
        shown=[]
        for gap in unique[:2]:
            clean=safe_detail(gap,1000)
            shown.append(clean if len(clean)<=140 else clean[:137].rsplit(' ',1)[0]+'…')
        remainder=f' (+{len(unique)-len(shown)} other causes)' if len(unique)>len(shown) else ''
        lines.append('Factor gaps: '+'; '.join(shown)+remainder+'. Full evidence attached.')
    disclaimer='DESIGN scores are not calibrated probabilities; MDE and accuracy gain remain unestablished.'
    if len(lines)>=6:
        lines[-1]+=' '+disclaimer
    else:
        lines.append(disclaimer)
    return lines


def opportunities_reported(intra):
    """True when the model was actually asked and answered.

    An UNAVAILABLE ranking says nothing the gap list does not already say, and
    five consecutive UNAVAILABLE lines in a phone-sized email crowd out the
    board — the same mistake day-105 fixed for the factor section."""
    return (intra.get('opportunities') or {}).get('status') in ('READY', 'NO_OPPORTUNITY')


def opportunities_summary(intra):
    """The model's own top two per side, and whether the engine agreed.

    Confidence is restated as self-reported every time it is printed. A number
    between 0 and 1 beside a ticker reads as a probability unless it is told not
    to, and this one has never been scored against an outcome."""
    snap = intra.get('opportunities') or {}
    comparison = snap.get('comparison') or {}
    # Pre-open and after-the-bell are different instruments on the same inputs:
    # the second was formed with the morning already visible. Never print the
    # pre-open claim over a diagnostic run.
    when = ('asked AFTER the open — CURRENT-TIME DIAGNOSTIC, not evidence about the morning'
            if snap.get('diagnostic') else 'asked once pre-open')
    lines = ['### DeepSeek opportunities — the model’s own picks, unadopted',
             f"{safe_detail(snap.get('model') or 'Model unavailable', 60)}: {snap.get('status')}; "
             f"{when} over {snap.get('considered', 0)} names carrying complete technicals."]
    # What it was SHOWN, beside what it said. A ranking made on prices alone
    # and one made with the morning's headlines are different readings.
    ev = snap.get('evidence') or {}
    if ev.get('names_with_headlines') is not None:
        macro = ', '.join(ev.get('macro_fields') or []) or 'none staged'
        lines[-1] += (f" Evidence shown: {ev['names_with_headlines']} of "
                      f"{snap.get('considered', 0)} names with news; macro {macro}.")
    if snap.get('status') == 'NO_OPPORTUNITY':
        lines.append('The model returned NO OPPORTUNITY on both sides. A planted long and a '
                     'planted short are detected through this same path, so this is a reading '
                     'of the evidence, not a broken request.')
    for row in comparison.get('rows') or []:
        lines.append(f"{row['side']} {safe_detail(row['ticker'], 24)}: self-reported confidence "
                     f"{fmt(row['confidence'], '.2f')} — {safe_detail(row['verdict'], 60)}. "
                     f"{safe_detail(row.get('reason') or '', 160)}")
    if comparison.get('rows'):
        lines.append(f"Agreement with the engine: {comparison.get('agree', 0)} of "
                     f"{len(comparison['rows'])}; {comparison.get('oppose', 0)} opposed; "
                     f"{comparison.get('unseen', 0)} outside the engine universe.")
    lines.append('Self-reported confidence is NOT a calibrated win probability: no track record, '
                 'never scored against an outcome, never blended with the engine’s number. '
                 'Nothing here is adopted, sized or recorded as a position.')
    return lines


def jev_reported(intra):
    """True when Jev was actually asked and answered."""
    return (intra.get('jev') or {}).get('status') in ('READY', 'NO_OPPORTUNITY')


def jev_summary(intra):
    """Jev's own picks, and whether the two models agree.

    Probability and abstain-probability are restated as Jev's own numbers every
    time they are printed. Two numbers between 0 and 1 beside a ticker read as
    calibrated odds unless something says they are not."""
    snap = intra.get('jev') or {}
    versus = snap.get('versus_deepseek') or {}
    when = ('asked AFTER the open — CURRENT-TIME DIAGNOSTIC'
            if snap.get('diagnostic') else 'asked once pre-open')
    lines = ['### Jev opportunities — a second model, unadopted',
             f"{safe_detail(snap.get('model') or 'Model unavailable', 60)}: {snap.get('status')}; "
             f"{when} over {snap.get('considered', 0)} names."]
    ev = snap.get('evidence') or {}
    if ev.get('names_with_headlines') is not None:
        macro = ', '.join(ev.get('macro_fields') or []) or 'none staged'
        lines[-1] += (f" Evidence shown: {ev['names_with_headlines']} of "
                      f"{snap.get('considered', 0)} names with news; macro {macro}.")
    if snap.get('status') == 'NO_OPPORTUNITY':
        lines.append('Jev declined on BOTH sides: every name came out less likely than its own '
                     '"none of these" option. A planted long and short are both detected through '
                     'this path, so this is a reading of the evidence, not a broken request.')
    verdicts = {r['ticker']: r['verdict'] for r in versus.get('rows') or []}
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for row in snap.get(key) or []:
            lines.append(f"{side} {safe_detail(row['ticker'], 24)}: Jev probability "
                         f"{fmt(row.get('probability'), '.3f')} against "
                         f"{fmt(row.get('abstain_probability'), '.3f')} for doing nothing — "
                         f"{safe_detail(verdicts.get(row['ticker'], 'DeepSeek did not pick it'), 60)}.")
    if versus.get('rows'):
        lines.append(f"Cross-model: {versus.get('agree', 0)} agreed, {versus.get('oppose', 0)} "
                     f"contradicted, {versus.get('alone', 0)} picked by Jev alone.")
    lines.append('Jev\u2019s probabilities are its OWN, not calibrated win probabilities: no track '
                 'record, never scored against an outcome, never averaged with DeepSeek\u2019s '
                 'confidence or the engine\u2019s score. Nothing here is adopted or sized.')
    return lines


def _jev_detail(intra):
    if 'jev' not in intra:
        return []
    snap = intra['jev'] or {}
    if not jev_reported(intra):
        return ['', '### Jev opportunities — a second model, unadopted',
                safe_detail(snap.get('reason') or 'Not staged this session.', 240)]
    lines = ['', *jev_summary(intra)]
    for gap in list(dict.fromkeys(snap.get('gaps') or []))[:3]:
        lines.append('Jev gap: '+safe_detail(gap, 180))
    return lines


def _opportunities_detail(intra):
    if 'opportunities' not in intra:
        return []
    snap = intra['opportunities'] or {}
    if not opportunities_reported(intra):
        return ['', '### DeepSeek opportunities — the model’s own picks, unadopted',
                safe_detail(snap.get('reason') or 'Not staged this session.', 240)]
    lines = ['', *opportunities_summary(intra)]
    engine_only = (snap.get('comparison') or {}).get('engine_only') or []
    if engine_only:
        lines.append('Engine board today: '+', '.join(safe_detail(t, 24) for t in engine_only)
                     + ' — none picked by the model.')
    for gap in list(dict.fromkeys(snap.get('gaps') or []))[:3]:
        lines.append('Opportunity gap: '+safe_detail(gap, 180))
    return lines


def _deepseek_detail(intra):
    if 'deepseek' not in intra:
        return []
    snap=intra['deepseek'] or {}
    shadow=snap.get('shadow') or {}
    lines=['',*deepseek_summary(intra),
           'H1 tests factor abstention; H2 additionally ranks by observed entry spread. Neither changes baseline selections or allocation.',
           'An entry spread is not a measured round-trip cost. Unpriced H1 rows are not executable observations.',
           '', ('| Name | Model contextual lean | Sentiment | Evidence-linked opinion and Python context |'
                if snap.get('grounding') else '| Name | Model contextual lean | Sentiment | Model rationale — not verified fact |'),
           '|---|---|---:|---|']
    for row in snap.get('assessments') or []:
        rationale=safe_detail(row.get('factor_rationale','Unavailable'),280).replace('|',' / ')
        lines.append(f"| {row['ticker']} | {row['directional_lean']} | {fmt(row.get('sentiment_score'),'+.3f')} | {rationale} |")
    if not snap.get('assessments'):
        if snap.get('grounding') and _model_assessed_count(snap):
            lines.append('| No accepted assessment | — | unknown | Returned opinions failed the grounded response contract. |')
        else:
            lines.append('| Assessment unavailable | — | unknown | No model result was inferred. |')
    grounding=snap.get('grounding') or {}
    if grounding:
        lines += ['', 'Grounded response contract: '+safe_detail(grounding.get('version','unavailable'))+'.',
            'Evidence-quality registration: '+safe_detail(snap.get('grounding_registration','PREREGISTER_day102_evidence_quality.md'))+'.',
            'Remaining-session horizon through 15:59 ET; a later assessment is never backdated to 09:46.',
            'Evidence IDs verify supplied-item identity, not semantic truth, issuer materiality or predictive skill. Raw model prose remains in private audit receipts.']
        for ticker,record in (grounding.get('per_ticker') or {}).items():
            if record.get('issues'):
                lines.append(ticker+' grounding exclusion: '+safe_detail('; '.join(record['issues'])))
            for evidence_id,item in (record.get('evidence_catalog') or {}).items():
                lines.append(f"{ticker} {evidence_id}: {safe_detail(item.get('title') or item.get('tag') or 'Evidence',400)}; "
                    f"published {item.get('published_at','unknown')}. [Cited source]({item['source_url']})")
            for fact in record.get('technical_facts') or []:
                lines.append(f"{ticker} Python fact: {safe_detail(fact['statement'],120)}; "
                    f"as of {fact['as_of']}; {safe_detail(fact['scope'],160)}.")
    watch=snap.get('research_watchlist') or {}
    if watch:
        requested=watch.get('requested',snap.get('requested'))
        actual_assessed = _model_assessed_count(snap) if grounding else watch.get('assessed', 0)
        accepted_note = (f"{snap.get('covered',0)} accepted after grounding; "
                         if grounding and actual_assessed != snap.get('covered',0) else '')
        coverage=(f"Watchlist coverage: {fmt(requested,'d')} requested; "
                  f"{fmt(watch.get('input_complete'),'d')} complete inputs; "
                  f"{actual_assessed} model-assessed; "+accepted_note+
                  f"{watch.get('evaluated',0)} usable assessments.")
        threshold=(f"{watch.get('eligible',0)} of {watch.get('evaluated',0)} usable assessments clear "
                   f"absolute sentiment support {fmt(watch.get('threshold'),'.2f')}."
                   if watch.get('threshold_evaluated',bool(watch.get('evaluated')))
                   else 'Sentiment threshold NOT EVALUATED; no qualifying-count or opportunity conclusion.')
        lines += ['', 'Expanded sentiment watchlist: '+str(watch.get('decision','UNAVAILABLE'))+'.',
                  'This separate research view does not require a successful baseline scan or BBO; it assigns no quantitative probability, trade allocation or entry approval.',
                  coverage, threshold+' At most two BULL and two BEAR names; no forced quota.',
                  'Watchlist registration: '+str(watch.get('registration','not recorded'))+'. No demonstrated accuracy gain; independent forward evidence and uncertainty/MDE remain required.']
        for item in watch.get('excluded') or []:
            lines.append(f"{item['ticker']} watchlist exclusion: "+safe_detail(item.get('reason','Unavailable')))
    lines += ['', '| Name | Status | Research side | Quant score | Combined DESIGN score | Sided DESIGN score | Entry spread bps | Reason |',
              '|---|---|---|---:|---:|---:|---:|---|']
    for row in shadow.get('rows') or []:
        reason=safe_detail(row.get('reason') or 'Registered shadow candidate; unadopted').replace('|',' / ')
        lines.append(f"| {row['ticker']} | {row['status']} | {row.get('direction') or '—'} | "
                     f"{fmt(row.get('quant_probability'),'.3f')} | {fmt(row.get('combined_probability'),'.3f')} | "
                     f"{fmt(row.get('sided_score'),'.3f')} | {fmt(row.get('spread_bps'))} | {reason} |")
    for ticker,gaps in (snap.get('candidate_gaps') or {}).items():
        if gaps:
            lines.append(f"{ticker} factor evidence gaps: "+safe_detail('; '.join(gaps)))
    inputs=snap.get('inputs') or {}
    diagnostics=snap.get('candidate_diagnostics') or inputs.get('candidate_diagnostics') or {}
    for ticker,notes in diagnostics.items():
        if notes:
            lines.append(f"{ticker} factor input audit notes (advisory; current evidence validated separately): "+safe_detail('; '.join(notes)))
    for candidate in inputs.get('candidates') or []:
        ticker=candidate['ticker']
        if candidate.get('source_url'):
            lines.append(f"{ticker} Python technical inputs as of {candidate.get('technicals_as_of','unknown')}: "
                         f"{candidate.get('technicals_scope','scope unknown')}. [Data source]({candidate['source_url']})")
        for key,label,text_key in [('headlines','Headline','title'),('catalyst_tags','Catalyst tag','tag')]:
            for item in candidate.get(key) or []:
                lines.append(f"{ticker} {label}, {item['published_at']}: {safe_detail(item[text_key],400)} "
                             f"[Evidence source]({item['source_url']})")
                evidence=item.get('evidence_metadata') or {}
                if evidence:
                    lines.append(f"Title classification {evidence.get('classification','UNCLASSIFIED')}; "
                        f"title horizon {evidence.get('impact_horizon','UNSPECIFIED')}; issuer role and novelty unverified; "
                        'first disclosure unknown. Publication time alone does not establish a new event.')
    for name,item in (inputs.get('macro') or {}).items():
        lines.append(f"Macro {name}: {item['value']} as of {item['as_of']}. [Data source]({item['source_url']})")
        if item.get('change_status') == 'READY' and item.get('reference'):
            reference=item['reference']
            lines.append(f"Macro {name} measured change: {fmt(item.get('change_pct'),'+.3f')}%; "
                f"reference {reference['value']} at provider daily-bar timestamp {reference['bar_timestamp']}; "
                'previous observed daily-bar close, not an exact prior-session-close certification or executable quote.')
        elif 'change_status' in item:
            lines.append(f"Macro {name} change unavailable: "+safe_detail(item.get('change_gap','DAILY_REFERENCE_UNAVAILABLE'))+
                '; an absolute level does not establish trend.')
    mde=shadow.get('mde') or {}
    lines += ['Factor registration: '+str(shadow.get('registration') or 'not recorded'),
              'Factor MDE: '+str(mde.get('status') or 'UNAVAILABLE')+
              f"; minimum forward sessions {mde.get('minimum_forward_sessions','unknown')}; net bps {fmt(mde.get('net_bps'))}."]
    lines += [f"Prepared model: {safe_detail(snap.get('model') or 'unavailable',100)}; input receipt SHA-256: {safe_detail(snap.get('input_sha256') or 'unavailable',64)}; "
              f"snapshot receipt SHA-256: {safe_detail(snap.get('snapshot_sha256') or 'unavailable',64)}."]
    for batch in snap.get('batches') or []:
        lines.append(f"Model batch: {safe_detail(batch.get('status') or 'UNAVAILABLE',40)}; "
                     f"requested {safe_detail(batch.get('model') or 'unavailable',100)}; "
                     f"response {safe_detail(batch.get('response_model') or 'unavailable',100)}; "
                     f"inference mode {safe_detail(batch.get('inference_mode') or 'not recorded',40)}; "
                     f"input SHA-256 {safe_detail(batch.get('input_sha256') or 'unavailable',64)}.")
    return lines


def cache_lines(res):
    """Say out loud when the board was built on live acquisition.

    The pre-open cache is an acquisition optimisation — it does not enter
    features or rules — so a fallback yields the same board. It is still an
    operational fault worth naming: it means a pre-open job did not run."""
    degraded = (res or {}).get('cache_degraded')
    fallbacks = (res or {}).get('cache_fallbacks') or {}
    if not degraded and not fallbacks:
        return []
    reasons = sorted({safe_detail(why, 120) for why in fallbacks.values()}) or (
        [safe_detail(degraded, 120)] if degraded else [])
    return [f"Pre-open history cache DEGRADED: {len(fallbacks)} name(s) acquired live "
            f"instead of from cache ({'; '.join(reasons)}). The cache changes acquisition "
            "only, not features or selection rules, so the board is unaffected — but a "
            "pre-open staging job did not run and should be investigated."]


def record_gap_line(rec):
    """The record's own holes, rendered from the frozen computation.

    Printed BESIDE the hit rate, not in a diagnostics appendix: a rate computed
    over a record with four missing sessions is a rate over what survived, and
    the reader cannot discount it without being told."""
    import ledger
    gaps = (rec or {}).get('record_gaps')
    return ledger.record_gap_line(gaps) if gaps else ''


def _historical_record(rec):
    if rec.get('status')=='UNAVAILABLE':
        return ['Historical record UNAVAILABLE; hit rates and returns are unknown.']
    prefix=[f"Historical record PARTIAL: {rec.get('invalid_rows',0)} invalid source rows excluded; source records retained."] if rec.get('status')=='PARTIAL' else []
    gap=record_gap_line(rec)
    return prefix+[f"Historical baseline: {rec['hits']}/{rec['n']} gross hits ({fmt(rec['rate'],'.1%')}); "
                   f"mean capture {fmt(rec['mean'],'+.3f')}%.",
                   f"Net of stored spread: {fmt(rec.get('net_rate'),'.1%')} hits; "
                   f"mean {fmt(rec['net_mean'],'+.3f')}% on {rec['net_n']} legs; unpriced {rec['net_unpriced']}."]+(
                   [gap] if gap else [])


def _day_shape(rec, intra):
    """Render frozen empirical counts; never fit an independence model here."""
    risk = intra.get('risk_evidence', {})
    shape = risk.get('day_shape', {})
    rate = risk.get('rate', {})
    lines = ['', '### How reliable is the record?']
    if not risk:
        return lines + ['Risk diagnostics were not saved in this older publication.']
    ci = rate.get('ci95')
    lines += [f"Gross hit-rate interval, clustered by {rate['sessions']} sessions: "
              + (f"{ci[0]:.1%}–{ci[1]:.1%}." if ci else 'unavailable.'),
              f"Approximate MDE80: {fmt(rate.get('mde80_pp'))} percentage points. "
              'Small score differences are not established probability differences; serial dependence can widen uncertainty.']
    if shape.get('sessions'):
        lines.append(f"Observed {shape['legs']}-leg days: {shape['bad_days']}/{shape['sessions']} "
                     'had one or fewer gross hits. These are historical session counts, not a forecast for today.')
    else:
        lines.append('No fully scored historical sessions match this board size; bad-day frequency is unknown.')
    lines += ['Correlated legs can lose together. Gross hit counts do not measure loss size or profitability.',
              '', '| Historical analog-score band | Gross hits | Sessions | Observed hit rate |',
              '|---|---:|---:|---:|']
    for bucket in risk.get('calibration', []):
        lines.append(f"| {bucket['score_band']} | {bucket['hits']}/{bucket['n']} | "
                     f"{bucket['sessions']} | {fmt(bucket['rate'], '.1%')} |")
    return lines


def _concentration(intra):
    """Disclosure computed from the publication's own config and allocations."""
    risk = intra.get('risk_evidence', {})
    groups = risk.get('concentration', [])
    lines = ['', '### Common exposure'] if groups else []
    for group in groups:
        lines.append(f"- {', '.join(group['tickers'])}: {group['side']} {group['group']}; "
                     f"{fmt(group['gross_share'], '.1%')} of hypothetical gross allocation. "
                     + (f"{fmt(group['side_share'], '.1%')} of the {group['side']} side. "
                        if group.get('side_share') is not None else '') +
                     'Shared exposure; distinct names do not establish independent bets.')
    if groups:
        lines.append('A dollar-neutral book can retain sector and factor risk. The prior forced-diversification rejection remains in STRATEGY.md; no new sizing rule is adopted.')
    return lines + ['Risk evidence gap: ' + gap for gap in risk.get('gaps', [])]


def _leg_heading(intra):
    """Say what the legs below are, from their OWN statuses.

    2026-09-09 COST REAL MONEY HERE. All four legs were ABSTAIN because the
    quote endpoint was returning HTTP 406 all session, so no spread could be
    priced. The table still led with name, side, dollar allocation and share
    count, with ABSTAIN as the last column under a heading that said "shadow
    tracking" -- and it was read as an order sheet and traded. Three of the four
    went the wrong way.

    A status that has to be hunted for in the right-hand column is not a
    guardrail. The heading now states the count and the consequence FIRST,
    before any name, side or dollar figure appears.
    """
    legs = intra.get('legs') or []
    if not legs:
        if any(r.get('role') == 'pair' for r in intra.get('recorded_today', [])):
            return ['### Recorded baseline legs — no fresh entry validation',
                    'Preserved original names, sides and shares; hypothetical selections, not confirmed positions.']
        return ['### Selected baseline legs']
    ab = [l for l in legs if l.get('status') not in ('SHADOW', 'ELIGIBLE')]
    if len(ab) == len(legs):
        return ['### ⛔ DO NOT TRADE — every leg below ABSTAINED',
                f'All {len(legs)} legs failed an integrity check and are shown '
                'for the record only. The allocations are what the baseline '
                'WOULD have sized, not a recommendation. Acting on this table '
                'is acting on picks the engine itself declined.']
    if ab:
        return [f'### ⚠ PARTIAL — {len(ab)} of {len(legs)} legs ABSTAINED',
                f'{", ".join(l["ticker"] for l in ab)} failed an integrity '
                'check; their rows are record-only. The remainder are shadow '
                'observations, not orders.']
    return ['### Selected baseline legs — shadow tracking',
            'Shadow observations, not orders. The engine\'s live record is '
            'printed above and is a coin flip.']


def text(d):
    intra=d['intraday']; res=intra['res']; rec=intra['record']
    leg_count = len(intra['legs']) or sum(r.get('role')=='pair' for r in intra.get('recorded_today',[]))
    lines=[f"# RB Daily Report — {d['session']}",
           f"Signal snapshot {d['generated_at']} · {d['report_status']}",
           'Publication clock: '+d['clock']['status'],
           *([f"Dispatch checked {d['delivery']['checked_at']}: {d['delivery']['status']}. "
               + d['delivery']['note']] if d.get('delivery') else []),
           *(['', '## Replacement requested by the recipient',
              'INFORMATIONAL — original morning computation retained; no recovered or fresh entry signal is claimed.',
              *d['replacement']['notes'],
              'Review: '+d['replacement']['review_url']]
             if d.get('replacement') else []),
           '', '## Part 1 — Intraday Opportunities',
           intra['contract']+'. Signal reference: 09:45 completed bar; execution quote is separate.',
           intra['model_claim'],
           f"Execution-verified research observations: {sum(l.get('status') in ('SHADOW','ELIGIBLE') and l.get('quote',{}).get('status')=='OK' for l in intra['legs'])}/{leg_count} selected or recorded legs at publication. "
           'This count verifies data, not predictive accuracy.', '',
           *_historical_record(rec),rec['label'],rec['benchmark_label'],
           *_day_shape(rec, intra), *_concentration(intra),
           '', *_leg_heading(intra), '',
           '| Status | Name | Baseline side | Signal reference | 09:46 quote | Spread | Hypothetical allocation |',
           '|---|---|---|---:|---:|---:|---:|']
    for l in intra['legs']:
        # AN ABSTAINED LEG GETS NO SHARE COUNT AND NO DOLLAR FIGURE.
        #
        # 2026-09-09 and 2026-09-11 both printed ABSTAIN in the first column
        # and "CAD 11,787 / 138 shares" in the last one. A banner saying DO NOT
        # TRADE was added after the first of those and the table was still
        # acted on, because a row carrying a share count IS an order ticket
        # whatever the status column says. The words were never the problem.
        #
        # The size is not lost: it is the BASELINE's hypothetical figure and
        # stays in the JSON for scoring. It is simply not rendered next to a
        # pick the engine itself declined.
        alloc = ('—' if l['status'] == 'ABSTAIN'
                 else f"CAD {l['baseline_alloc']:,.0f} / {l['baseline_shares']} shares")
        lines.append(f"| {l['status']} | {l['ticker']} | {l['side']} | {l['signal_reference']:.2f} | "
                     f"{fmt(l['entry_reference'])} | {fmt(l['entry_spread_bps'])} bps | "
                     f"{alloc} |")
    if not intra['legs']:
        recorded=[r for r in intra.get('recorded_today',[]) if r.get('role')=='pair']
        for r in recorded:
            lines.append(f"| RECORDED — not a fresh entry | {r['ticker']} | {r['side']} | {r.get('p945','unknown')} | unverified | "
                         f"{r.get('spread_bps') or 'unknown'} bps stored proxy | {r.get('shares') or 'unknown'} recorded shares |")
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
              '| Name | Side | Analog score (not calibrated probability) | Density | First 15m | Gap | Volume ratio |',
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
    lines += cache_lines(res)
    provider = intra.get('historical_provider',{})
    if provider and provider.get('status') != 'NOT CONFIGURED':
        lines += ['', '### Additional historical data — not a live signal',
                  f"EODHD: {provider['status']}. Valid dated references: {provider['reference_count']}. "
                  f"Five-minute history: {provider['intraday_status']}.", provider['note']]
    for r in res.get('excluded',[]):
        lines.append(f"Excluded {r['t']}: {r.get('excluded_reason','peer conflict')}")
    lines += _deepseek_detail(intra)
    lines += _opportunities_detail(intra)
    lines += _jev_detail(intra)
    lines += _expanded_detail(intra)
    lines += _opening_detail(intra)
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
    lines += ['', ('## Original morning ledger snapshot — see replacement updates above'
                   if d.get('replacement') else '## Existing position marks'),
              book.get('verification','Recorded ledger; current holdings not independently verified.'),
              ('Position ledger UNAVAILABLE; current holdings are unknown.' if book.get('status')=='UNAVAILABLE' else
               f"{len(book['legs'])} readable recorded open positions; {book['stale']} unmarkable and excluded from live totals.")]
    lines += ['Position evidence gap: '+safe_detail(gap) for gap in book.get('gaps',[])]
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
    if book.get('recent_closed'):
        lines += ['', '### Recently closed — recorded, not brokerage-reconciled']
        for p in book['recent_closed']:
            lines.append(f"{p['ticker']} {p['side']}: {p['shares']:g} shares, entry {p['entry_px']:.2f}, "
                         f"exit {p['exit_px']:.2f} on {p['exit_date']}; gross P&L {p['pnl_usd']:+.2f} / {p['pnl_pct']:+.2f}% before costs.")
    if d.get('readiness',{}).get('gaps'):
        lines += ['', '## Readiness gaps']+d['readiness']['gaps']
    history = res.get('training_history', [])
    if history:
        lines += ['', '### Training-label validation',
                  'Only complete standard exchange sessions supply training outcomes; gaps need the immediately prior session close.']
        for item in history:
            lines.append(f"{item['ticker']}: {item['accepted_sessions']} complete sessions; "
                         f"{item['rejected_sessions']} excluded; {item['missing_previous_closes']} unavailable prior closes; "
                         f"{item['outside_session_bars']} outside-session bars ignored.")
            lines.extend(f"  {e['session']}: {e['reason']}" for e in item['exclusions'])
    if d['errors']:
        lines += ['', '## Data and delivery diagnostics']
        lines += [f"{e['layer']}: {e['error']} — {e['detail']}" for e in d['errors']]
    lines += ['', f"Research: {d['research']['registration']} — {d['research']['status']}. {d['research']['mde']}",
              'Code revision: '+str(d.get('provenance',{}).get('code_commit') or 'not saved in this publication'),
              'No order was placed. Hypothetical baseline allocation is for comparison; the strategy overlays are not adopted.']
    return '\n'.join(lines)


def html(d):
    return markdown_html(text(d))


def markdown_html(body):
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
    for line in body.splitlines():
        if not line.startswith('|') and table:
            rendered.append('</tbody></table></div>');table=False
        if not line.startswith('- ') and bullet:
            rendered.append('</ul>');bullet=False
        if line.startswith('|'):
            cells=[escape(x.strip()) for x in line.strip('|').split('|')]
            if all(re.fullmatch(r'[-:]+',x) for x in cells):
                continue
            if not table:
                rendered.append('<div style="overflow-x:auto"><table role="table" style="width:100%;border-collapse:collapse;background:#fff;font-size:13px"><tbody>')
                rendered.append('<tr>'+''.join('<th scope="col" style="padding:11px 9px;background:#e9f0f5;border-bottom:2px solid #b9cdda;text-align:left">'+x+'</th>' for x in cells)+'</tr>')
                table=True
            else:
                rendered.append('<tr>'+''.join('<td style="padding:10px 9px;border-bottom:1px solid #d9e2eb;text-align:left">'+x+'</td>' for x in cells)+'</tr>')
        elif line.startswith('- '):
            if not bullet:
                rendered.append('<ul>');bullet=True
            rendered.append('<li>'+inline(line[2:])+'</li>')
        elif line.startswith('#'):
            level=min(3,len(line)-len(line.lstrip('#')))
            style = {1:'margin:0 -24px 24px;padding:30px 24px;background:#12334b;color:#fff;font-size:27px',
                     2:'border-top:3px solid #267a85;padding-top:22px;margin-top:34px;font-size:22px;color:#12334b',
                     3:'margin-top:26px;font-size:18px;color:#245b6c'}[level]
            rendered.append(f'<h{level} style="{style}">'+escape(line.lstrip('# '))+f'</h{level}>')
        elif line:
            rendered.append('<p style="line-height:1.6;margin:12px 0">'+inline(line)+'</p>')
    if table: rendered.append('</tbody></table></div>')
    if bullet: rendered.append('</ul>')
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>RB Daily Report</title><style>body{font:15px system-ui,sans-serif;color:#182437;background:#f5f7fa;'
            'max-width:1180px;margin:32px auto;padding:0 24px}h1{color:#0a3658}h2{border-top:3px solid #23627e;'
            'padding-top:20px;margin-top:36px}table{width:100%;border-collapse:collapse;background:white;font-size:13px}'
            'td{padding:9px;border-bottom:1px solid #d9e2eb;text-align:left}tr:first-child{font-weight:700;background:#e9f0f5}'
            'p,li{line-height:1.55}li{margin-bottom:10px}h3{color:#315b70}</style></head><body style="font-family:Arial,sans-serif;color:#182437;background:#f5f7fa;max-width:1120px;margin:24px auto;padding:0 24px 24px">'
            +''.join(rendered)+'</body></html>')
