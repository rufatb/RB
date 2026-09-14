"""Local-only staged factors and registered shadow rankings, never order routing."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import deepseek_policy as P
from diagnostics import safe_detail
from quotes import stamp

ET = ZoneInfo('America/New_York')
TICKER = re.compile(r'[A-Z0-9][A-Z0-9.\-]{0,19}\Z')
# Day100 DESIGN display policy, separately registered from the day99 H1/H2
# quantitative study. These thresholds are not fitted success probabilities.
RESEARCH_SENTIMENT_THRESHOLD = 0.5
RESEARCH_MAX_PER_LEAN = 2
RESEARCH_REGISTRATION = 'PREREGISTER_day100_deepseek_reliability.md'


class SnapshotValidationError(ValueError):
    """Controlled persisted-input rejection, without echoing rejected values."""


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise SnapshotValidationError('duplicate JSON key')
        out[key] = value
    return out


def _finite(value, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return (math.isfinite(value) and (low is None or value >= low)
                and (high is None or value <= high))
    except (OverflowError, TypeError):
        return False


def _notes(items):
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise SnapshotValidationError('invalid diagnostic list')
    return list(dict.fromkeys(safe_detail(item) for item in items))


def _model(value):
    if (not isinstance(value, str) or value.startswith('sk-')
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,99}', value) is None):
        raise SnapshotValidationError('invalid model identifier')
    if safe_detail(value, 100) != value:
        raise SnapshotValidationError('private model identifier')
    return value


def _batches(items, model):
    """Keep request provenance while discarding arbitrary stored payload fields."""
    if not isinstance(items, list):
        raise SnapshotValidationError('invalid batch provenance')
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise SnapshotValidationError('invalid batch provenance')
        clean = {}
        if 'tickers' in item:
            names = item['tickers']
            if (not isinstance(names, list) or not 1 <= len(names) <= P.BATCH_SIZE
                    or any(not isinstance(t, str) or not TICKER.fullmatch(t) for t in names)
                    or len(names) != len(set(names))):
                raise SnapshotValidationError('invalid batch ticker provenance')
            clean['tickers'] = list(names)
        for key in ('status', 'errorcode', 'details', 'close_warning'):
            value = item.get(key)
            if value is not None:
                if not isinstance(value, str):
                    raise SnapshotValidationError('invalid batch diagnostics')
                clean[key] = safe_detail(value)
        if item.get('model') is not None:
            clean['model'] = _model(item['model'])
            if clean['model'] != model:
                raise SnapshotValidationError('batch model differs from snapshot')
        if item.get('response_model') is not None:
            clean['response_model'] = _model(item['response_model'])
        if 'inference_mode' in item:
            if item['inference_mode'] not in ('thinking_disabled', 'model_default'):
                raise SnapshotValidationError('invalid batch inference mode')
            clean['inference_mode'] = item['inference_mode']
        for key, pattern in (('request_id', r'[A-Za-z0-9_-]{1,120}'),
                             ('response_id', r'[A-Za-z0-9_-]{1,120}'),
                             ('input_sha256', r'[a-f0-9]{64}')):
            value = item.get(key)
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(pattern, value) or safe_detail(value) != value:
                    raise SnapshotValidationError('invalid batch request provenance')
                clean[key] = value
        if item.get('prompt_version') is not None:
            if item['prompt_version'] != P.PROMPT_VERSION:
                raise SnapshotValidationError('batch prompt version mismatch')
            clean['prompt_version'] = P.PROMPT_VERSION
        if item.get('schema_version') is not None:
            if type(item['schema_version']) is not int or item['schema_version'] != P.SCHEMA_VERSION:
                raise SnapshotValidationError('batch schema version mismatch')
            clean['schema_version'] = P.SCHEMA_VERSION
        out.append(clean)
    return out


def _safe_evidence(checked):
    """Redact free text; retain validator-approved public URLs and numerics."""
    for candidate in checked['candidates']:
        if 'technicals_scope' in candidate:
            candidate['technicals_scope'] = safe_detail(candidate['technicals_scope'], P.MAX_TITLE_CHARS)
        if candidate.get('technical_provenance'):
            candidate['technical_provenance']['computation'] = safe_detail(
                candidate['technical_provenance']['computation'], 120)
        for field, key in (('headlines', 'title'), ('catalyst_tags', 'tag')):
            for item in candidate.get(field, []):
                item[key] = safe_detail(item[key], P.MAX_TITLE_CHARS)
    return checked


def unavailable(reason, *, requested=0):
    result = {'status': 'UNAVAILABLE', 'reason': safe_detail(reason),
            'requested': requested, 'covered': 0, 'assessments': [],
            'candidate_gaps': {}, 'gaps': [safe_detail(reason)],
            'adopted': False, 'model': None, 'input_sha256': None}
    result['research_watchlist'] = research_watchlist(result)
    return result


def research_watchlist(snapshot):
    """Pure contextual research selection, independent of scans and BBO.

    Consume only assessments whose public inputs passed the saved validator.
    No quantitative score, execution direction, allocation or win probability
    is assigned to expanded names. No replacement of the baseline or H1/H2.
    """
    out = {'status': 'UNAVAILABLE', 'decision': 'UNAVAILABLE — factors not assessed',
           'bulls': [], 'bears': [], 'assessed': 0, 'evaluated': 0, 'eligible': 0,
           'requested': None, 'input_complete': None, 'threshold_evaluated': False,
           'excluded': [], 'threshold': RESEARCH_SENTIMENT_THRESHOLD,
           'registration': RESEARCH_REGISTRATION, 'adopted': False,
           'label': 'SHADOW sentiment watchlist; factor support, not probability or entry recommendation.'}
    if not isinstance(snapshot, dict):
        return out
    # Preserve the original pool denominator even when no model request ran.
    # Complete public inputs, actual assessments, usable assessments and
    # threshold passes are different populations, not interchangeable counts.
    requested = snapshot.get('requested')
    if type(requested) is int and 0 <= requested <= P.MAX_CANDIDATES:
        out['requested'] = requested
    inputs = snapshot.get('inputs')
    coverage = inputs.get('coverage') if isinstance(inputs, dict) else None
    complete = coverage.get('complete') if isinstance(coverage, dict) else None
    if (type(complete) is int and 0 <= complete <= P.MAX_CANDIDATES
            and (out['requested'] is None or complete <= out['requested'])):
        out['input_complete'] = complete
    if snapshot.get('status') not in ('READY', 'PARTIAL'):
        return out
    try:
        from adapters.deepseek_adapter import parse_assessments
        raw = snapshot.get('assessments')
        if not isinstance(raw, list) or not raw:
            return out
        assessments = parse_assessments(json.dumps({'assessments': raw}), [r['ticker'] for r in raw])
        inputs = snapshot.get('inputs') or {}
        candidates = inputs.get('candidates')
        if not isinstance(candidates, list):
            raise SnapshotValidationError('validated public candidates unavailable')
        counts = Counter(c['ticker'] for c in candidates)
        gaps = snapshot.get('candidate_gaps') or {}
        if not isinstance(gaps, dict):
            raise SnapshotValidationError('invalid candidate diagnostics')
        gaps = {ticker: _notes(notes) for ticker, notes in gaps.items()}
    except (ValueError, TypeError, KeyError, AttributeError):
        out['decision'] = 'UNAVAILABLE — factor watchlist input schema invalid'
        return out
    out['assessed'] = len(assessments)
    by_lean = {'BULL': [], 'BEAR': []}
    for assessment in assessments:
        ticker = assessment['ticker']
        reason = None
        if counts[ticker] != 1:
            reason = 'Validated public candidate missing or duplicated.'
        elif gaps.get(ticker):
            reason = '; '.join(gaps[ticker])
        elif (inputs.get('coverage') or {}).get('macro_complete') is not True:
            reason = 'INCOMPLETE_MACRO'
        if reason:
            out['excluded'].append({'ticker': ticker, 'reason': safe_detail(reason)})
            continue
        out['evaluated'] += 1
        lean, score = assessment['directional_lean'], assessment['sentiment_score']
        if lean == 'NO_EDGE':
            reason = 'Model assessed NO_EDGE.'
        elif (lean == 'BULL' and score <= 0) or (lean == 'BEAR' and score >= 0):
            reason = 'Directional lean and sentiment sign disagree.'
        elif abs(score) < RESEARCH_SENTIMENT_THRESHOLD:
            reason = 'Sentiment support below the registered display threshold.'
        if reason:
            out['excluded'].append({'ticker': ticker, 'reason': reason})
            continue
        by_lean[lean].append({**assessment, 'factor_rationale': safe_detail(
            assessment['factor_rationale'], P.MAX_RATIONALE_CHARS)})
    out['eligible'] = sum(len(rows) for rows in by_lean.values())
    for lean, key in [('BULL', 'bulls'), ('BEAR', 'bears')]:
        out[key] = sorted(by_lean[lean], key=lambda r: (-abs(r['sentiment_score']), r['ticker']))[:RESEARCH_MAX_PER_LEAN]
    if not out['evaluated']:
        out['decision'] = 'UNAVAILABLE — assessed names lack complete validated evidence'
        return out
    out['threshold_evaluated'] = True
    partial = (snapshot.get('status') != 'READY' or out['evaluated'] != len(assessments)
               or bool(snapshot.get('gaps')))
    out['status'] = 'PARTIAL' if partial else 'READY'
    if out['eligible']:
        out['decision'] = 'SHADOW SENTIMENT WATCHLIST — unadopted; execution evidence separate'
    elif partial:
        out['decision'] = 'PARTIAL — evaluated names abstain; remaining names unavailable'
    else:
        out['decision'] = 'NO EDGE - WAIT'
    return out


def load_prepared(state_dir, now, path=None):
    """Revalidate the snapshot; no SDK call, provider request or state mutation."""
    return _load_snapshot(state_dir, now, path=path)


def load_diagnostic(state_dir, now, path):
    """Explicit diagnostic view only; production never accepts these snapshots."""
    from diagnostic_context import require_context
    require_context(state_dir)
    return _load_snapshot(state_dir, now, path=path, diagnostic=True)


def _load_snapshot(state_dir, now, path=None, *, diagnostic=False):
    try:
        now = stamp(now).astimezone(ET)
        path = Path(path or os.getenv('RB_DEEPSEEK_SNAPSHOT_JSON') or
                    Path(state_dir)/'deepseek_snapshot.json')
        if not path.exists():
            return unavailable('DeepSeek inputs have not been prepared for this session.')
        if path.stat().st_size > P.MAX_INPUT_BYTES:
            raise ValueError('oversized DeepSeek snapshot')
        from adapters.deepseek_adapter import parse_assessments
        from factor_inputs import validate_payload
        from report_store import encode
        obj = json.loads(path.read_text(), object_pairs_hook=_object,
                         parse_constant=lambda s: (_ for _ in ()).throw(SnapshotValidationError('nonfinite JSON')))
        if not isinstance(obj, dict):
            raise SnapshotValidationError('snapshot is not an object')
        seal = obj.get('snapshot_sha256')
        if not isinstance(seal, str) or re.fullmatch(r'[a-f0-9]{64}', seal) is None:
            raise SnapshotValidationError('missing or malformed snapshot integrity seal')
        unsigned = {key: value for key, value in obj.items() if key != 'snapshot_sha256'}
        if hashlib.sha256(encode(unsigned).encode()).hexdigest() != seal:
            raise SnapshotValidationError('snapshot integrity mismatch')
        diagnostic_snapshot = (obj.get('kind') == 'CURRENT_TIME_DIAGNOSTIC'
                               and obj.get('morning_snapshot') is False
                               and obj.get('prediction_evidence') is False)
        if diagnostic and not diagnostic_snapshot:
            raise SnapshotValidationError('explicit current-time diagnostic snapshot required')
        if not diagnostic and (obj.get('morning_snapshot') is False or obj.get('kind') is not None):
            raise SnapshotValidationError('diagnostic evidence is not a morning snapshot')
        # Preparation can fail before an account model is selected. Such a
        # sealed failure must retain its actual cause, without inventing a
        # model or granting an exception to any provider assessment/receipt.
        model_absent_failure = (obj['model'] is None and obj.get('status') == 'UNAVAILABLE'
                                and obj.get('assessments') == [] and obj.get('batches') == [])
        model = None if model_absent_failure else _model(obj['model'])
        batches = _batches(obj.get('batches', []), model)
        prepared, as_of = stamp(obj['prepared_at']), stamp(obj['as_of'])
        if (type(obj.get('schema_version')) is not int
                or obj.get('schema_version') != P.SCHEMA_VERSION
                or obj.get('prompt_version') != P.PROMPT_VERSION
                or obj.get('adopted') is not False
                or obj['session'] != now.date().isoformat()
                or prepared.astimezone(ET).date() != now.date()
                or as_of.astimezone(ET).date() != now.date()
                or (not diagnostic and prepared.astimezone(ET).time() >= dt.time(9, 30))
                or not as_of <= prepared <= now
                or (now-prepared).total_seconds() > P.MAX_SNAPSHOT_AGE_HOURS*3600):
            raise SnapshotValidationError('stale, future or mismatched DeepSeek snapshot')
        # Recheck public evidence as of the real decision; an input cannot stay
        # fresh merely because its file was copied or an LLM request completed.
        inputs = obj['inputs']
        if (not isinstance(inputs, dict) or stamp(inputs['as_of']) != as_of
                or not isinstance(obj['input_sha256'], str)
                or re.fullmatch(r'[a-f0-9]{64}', obj['input_sha256']) is None):
            raise SnapshotValidationError('invalid snapshot input identity')
        if hashlib.sha256(encode(inputs).encode()).hexdigest() != obj['input_sha256']:
            raise SnapshotValidationError('DeepSeek input hash mismatch')
        checked = validate_payload(inputs, now)
        by_t = {c['ticker']: c for c in checked['candidates']}
        saved = obj['assessments']
        if not isinstance(saved, list):
            raise SnapshotValidationError('invalid assessment list')
        tickers = [r['ticker'] for r in saved]
        if not set(tickers) <= set(by_t):
            raise SnapshotValidationError('DeepSeek output outside validated candidate pool')
        assessments = parse_assessments(json.dumps({'assessments': saved}), tickers) if saved else []
        input_count = len(inputs.get('candidates', []))
        source_requested = obj.get('source_requested', input_count)
        if type(source_requested) is not int or not input_count <= source_requested <= P.MAX_CANDIDATES:
            raise SnapshotValidationError('snapshot coverage differs from saved records')
        if obj.get('coverage_version') == 1 and (obj.get('requested') != input_count
                or obj.get('covered') != len(assessments)):
            raise SnapshotValidationError('snapshot coverage differs from saved records')
        eligible, submitted = obj.get('eligible'), obj.get('submitted')
        if eligible is not None or submitted is not None:
            if (type(eligible) is not int or type(submitted) is not int
                    or not len(assessments) <= submitted <= eligible <= input_count):
                raise SnapshotValidationError('invalid preparation coverage counts')
            submitted_names = [ticker for batch in batches for ticker in batch.get('tickers', [])]
            if (len(submitted_names) != submitted or len(submitted_names) != len(set(submitted_names))
                    or not set(submitted_names) <= set(by_t) or not set(tickers) <= set(submitted_names)):
                raise SnapshotValidationError('batch coverage does not match submitted candidates')
        for assessment in assessments:
            assessment['factor_rationale'] = safe_detail(assessment['factor_rationale'], P.MAX_RATIONALE_CHARS)
        gaps = _notes(checked.get('gaps', [])) + _notes(obj.get('gaps', []))
        candidate_gaps = {t: _notes(v) for t, v in checked.get('candidate_gaps', {}).items()}
        candidate_diagnostics = {t: _notes(v) for t, v in checked.get('candidate_diagnostics', {}).items()}
        previous_gaps = obj.get('candidate_gaps', {})
        if not isinstance(previous_gaps, dict):
            raise SnapshotValidationError('invalid per-candidate diagnostics')
        for ticker, notes in previous_gaps.items():
            if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
                raise SnapshotValidationError('invalid diagnostic ticker')
            for note in _notes(notes):
                if re.fullmatch(r'HISTORICAL_SESSIONS_EXCLUDED:[0-9]+', note):
                    candidate_diagnostics.setdefault(ticker, []).append(note)
                else:
                    candidate_gaps.setdefault(ticker, []).append(note)
        for ticker in by_t:
            if ticker not in tickers:
                candidate_gaps.setdefault(ticker, []).append('MODEL_ASSESSMENT_UNAVAILABLE')
        candidate_gaps = {ticker: list(dict.fromkeys(notes))
                          for ticker, notes in candidate_gaps.items()}
        # A partial successful batch is useful evidence, but it never fills an
        # uncovered ticker with an invented NO_EDGE assessment.
        requested = source_requested
        complete = (assessments and not gaps and not any(candidate_gaps.values())
                    and len(assessments) == requested
                    and checked['coverage']['complete'] == requested)
        status = 'READY' if complete else 'PARTIAL' if assessments else 'UNAVAILABLE'
        reported_gaps = (list(dict.fromkeys(_notes(obj.get('gaps', []))+gaps))
                         if model_absent_failure else sorted(set(gaps)))
        result = {'schema_version': P.SCHEMA_VERSION, 'prompt_version': P.PROMPT_VERSION,
                'session': obj['session'], 'as_of': as_of.isoformat(),
                'prepared_at': prepared.isoformat(), 'model': model,
                'status': status, 'assessments': assessments, 'inputs': _safe_evidence(checked),
                'batches': batches,
                'candidate_gaps': candidate_gaps, 'gaps': reported_gaps,
                'candidate_diagnostics': {t: sorted(set(notes)) for t, notes in candidate_diagnostics.items()},
                'input_sha256': obj['input_sha256'],
                'snapshot_sha256': seal,
                'requested': requested, 'covered': len(assessments), 'adopted': False,
                'eligible': eligible, 'submitted': submitted,
                'registration': P.DESIGN_PROVENANCE['registration']}
        if diagnostic:
            result.update(kind='CURRENT_TIME_DIAGNOSTIC', morning_snapshot=False,
                          prediction_evidence=False)
        if model_absent_failure:
            reasons = _notes(obj.get('gaps', []))
            result['reason'] = (reasons[0] if reasons else
                                'No model was selected and no assessment was produced.')
        result['research_watchlist'] = research_watchlist(result)
        return result
    except Exception as exc:
        # Never echo library timestamp/JSON exceptions or raw stored text.
        detail = str(exc) if isinstance(exc, SnapshotValidationError) else type(exc).__name__
        return unavailable('DeepSeek snapshot rejected: '+safe_detail(detail))


def combined_probability(quant, sentiment):
    """Registered DESIGN combination; deliberately not a calibrated win rate."""
    from dashboard import clamp_probability
    if not _finite(quant) or not _finite(sentiment):
        raise ValueError('finite numeric quantitative score and sentiment required')
    if not 0 <= quant <= 1 or not -1 <= sentiment <= 1:
        raise ValueError('score outside input domain')
    return clamp_probability(P.QUANT_WEIGHT*quant + P.SENTIMENT_WEIGHT*(
        0.5 + P.SENTIMENT_PROBABILITY_SPAN*sentiment))


def exact_spread(quote, ticker, now):
    """Observed entry spread only; never label it known round-trip cost."""
    if not isinstance(quote, dict) or quote.get('status') != 'OK' or quote.get('ticker') != ticker:
        return None, 'authenticated BBO unavailable'
    if not isinstance(ticker, str) or not ticker.endswith('.TO'):
        return None, 'exact TSX CAD execution coverage unavailable'
    if quote.get('currency') != 'CAD':
        return None, 'quote currency mismatch'
    try:
        qtime = stamp(quote['quote_time']).astimezone(ET)
        now = stamp(now).astimezone(ET)
        spread = quote['spread_bps']
        if (qtime.date() != now.date() or qtime.strftime('%H:%M') != '09:46'
                or now.strftime('%H:%M') != '09:46' or not 0 <= (now-qtime).total_seconds() <= 120
                or not _finite(spread, 0)):
            return None, 'entry spread lacks an exact 09:46 observation'
        from intraday_history import session_schedule
        if session_schedule(now.date().isoformat(), now.date().isoformat()).empty:
            return None, 'not a TSX exchange session'
        # Reuse the single pure quote validator; a saved OK label or a forged
        # zero spread cannot substitute for positive uncrossed bid and ask.
        from quotes import validate_equity
        valid = validate_equity({'symbol': ticker, 'currency': 'CAD',
            'bid': quote['bid'], 'ask': quote['ask'], 'quoteTime': quote['quote_time']},
            ticker, now, currency='CAD')
        if valid['status'] != 'OK' or not math.isclose(spread, valid['spread_bps'], rel_tol=1e-9, abs_tol=1e-9):
            return None, 'entry spread inconsistent with validated BBO'
        return valid['spread_bps'], None
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None, 'invalid entry spread observation'


def rank_shadow(candidates, snapshot, quotes, now, *, min_sided_p, scan_available=True):
    """Pure, no mutation or forced pair. H1/H2 never replace baseline rows."""
    out = {'status': 'SHADOW — no strategy adoption', 'adopted': False,
           'decision': 'UNAVAILABLE — shadow arms not evaluated', 'evaluation_status': 'UNAVAILABLE',
           'rows': [],
           'h1': {'longs': [], 'shorts': []}, 'h2': {'longs': [], 'shorts': []},
           'gaps': [],
           'registration': 'PREREGISTER_day99_deepseek.md',
           'mde': {'status': 'UNAVAILABLE — forward matched execution study required',
                   'minimum_forward_sessions': P.MIN_FORWARD_SESSIONS, 'net_bps': None},
           'label': 'DESIGN factor combination, not calibrated probability; entry spread is a cost proxy.'}
    if not _finite(min_sided_p, .5, .65) or min_sided_p == .5:
        out['gaps'].append('Invalid preregistered edge threshold.'); return out
    if not scan_available:
        out['gaps'].append('Quantitative scan unavailable; shadow arms not evaluated.'); return out
    if not isinstance(snapshot, dict):
        out['gaps'].append('Prepared factors unavailable.'); return out
    try:
        out['gaps'] = _notes(snapshot.get('gaps', []))
        if snapshot.get('status') not in ('READY', 'PARTIAL'):
            out['gaps'].append('Prepared factor assessments unavailable.'); return out
        from adapters.deepseek_adapter import parse_assessments
        raw = snapshot.get('assessments')
        expected = [row['ticker'] for row in raw]
        assessments = parse_assessments(json.dumps({'assessments': raw}), expected)
        by_t = {row['ticker']: row for row in assessments}
        saved_gaps = snapshot.get('candidate_gaps', {})
        if not isinstance(saved_gaps, dict):
            raise SnapshotValidationError('invalid candidate diagnostics')
        saved_gaps = {ticker: _notes(items) for ticker, items in saved_gaps.items()}
    except (ValueError, TypeError, KeyError, AttributeError):
        out['gaps'].append('Prepared factor schema invalid.'); return out
    if not isinstance(candidates, list):
        out['gaps'].append('Quantitative candidate list unavailable.'); return out
    if not candidates:
        out['gaps'].append('No freshly evaluated candidate scores; recorded board remains separate.'); return out
    quotes = quotes if isinstance(quotes, dict) else {}
    counts = Counter(c.get('t', c.get('ticker')) for c in candidates
                     if isinstance(c, dict) and isinstance(c.get('t', c.get('ticker')), str))
    seen = set()
    for c in candidates:
        if not isinstance(c, dict):
            out['gaps'].append('Invalid quantitative candidate.'); continue
        ticker = c.get('t', c.get('ticker'))
        if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
            out['gaps'].append('Invalid quantitative ticker.'); continue
        if ticker in seen:
            continue
        seen.add(ticker)
        a = by_t.get(ticker)
        quant = c.get('p_up', c.get('probability'))
        row = {'ticker': ticker, 'status': 'UNAVAILABLE', 'decision': 'UNAVAILABLE — not evaluated',
               'direction': None, 'quant_probability': float(quant) if _finite(quant, 0, 1) else None,
               'combined_probability': None, 'sided_score': None, 'spread_bps': None,
               'factor': a, 'reason': None}
        out['rows'].append(row)
        if counts[ticker] > 1:
            row['reason'] = 'Duplicate quantitative candidate; neither row is eligible.'
            out['gaps'].append(ticker+': duplicate quantitative candidate.'); continue
        gaps = saved_gaps.get(ticker, [])
        if not a or gaps:
            row['reason'] = safe_detail('; '.join(gaps) if gaps else 'DeepSeek assessment unavailable')
            continue
        if row['quant_probability'] is None:
            row['reason'] = 'Quantitative score missing, nonfinite or outside its domain.'; continue
        try:
            p = combined_probability(row['quant_probability'], a['sentiment_score'])
        except (ValueError, TypeError, KeyError) as exc:
            row['reason'] = 'Invalid factor combination: '+type(exc).__name__; continue
        row.update(combined_probability=p, sided_score=max(p, 1-p), status='ABSTAIN',
                   decision='NO EDGE - WAIT')
        lean = a['directional_lean']
        side = 'LONG' if p > 0.5 else 'SHORT' if p < 0.5 else None
        if (row['sided_score'] < min_sided_p or not side or lean == 'NO_EDGE'
                or (side=='LONG' and (lean!='BULL' or a['sentiment_score']<=0))
                or (side=='SHORT' and (lean!='BEAR' or a['sentiment_score']>=0))):
            row['reason'] = 'Combined score below threshold or factor disagreement.'; continue
        row.update(status='CANDIDATE', direction=side, decision='SHADOW CANDIDATE — not adopted')
        spread, gap = exact_spread(quotes.get(ticker), ticker, now)
        row.update(spread_bps=spread, reason=gap)
    for side, key in [('LONG', 'longs'), ('SHORT', 'shorts')]:
        eligible = [r for r in out['rows'] if r['status']=='CANDIDATE' and r['direction']==side]
        out['h1'][key] = sorted(eligible, key=lambda r: (-r['sided_score'], r['ticker']))[:P.MAX_PER_SIDE]
        out['h2'][key] = sorted((r for r in eligible if r['spread_bps'] is not None),
                               key=lambda r: (r['spread_bps'], -r['sided_score'], r['ticker']))[:P.MAX_PER_SIDE]
    if any(out['h2'].values()):
        out['decision'] = 'SHADOW CANDIDATES — not adopted'
    elif any(out['h1'].values()):
        out['decision'] = 'SHADOW FACTOR CANDIDATES — exact entry costs unavailable'
        out['gaps'].append('Factor-qualified shadow names lack exact entry-cost evidence.')
    else:
        evaluated = [row for row in out['rows'] if row['status'] != 'UNAVAILABLE']
        if evaluated and len(evaluated) == len(out['rows']) and not out['gaps']:
            out['decision'] = 'NO EDGE - WAIT'
        elif evaluated:
            out['decision'] = 'PARTIAL — evaluated names abstain; remaining names unavailable'
    if any(row['status'] != 'UNAVAILABLE' for row in out['rows']):
        out['evaluation_status'] = ('PARTIAL' if out['gaps'] or any(
            row['status'] == 'UNAVAILABLE' for row in out['rows']) else 'READY')
    out['gaps'] = list(dict.fromkeys(out['gaps']))
    return out
