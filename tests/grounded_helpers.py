"""Offline model fixtures that satisfy the same new response contract as live calls."""
import hashlib
import json

from adapters.deepseek_adapter import public_payload, parse_grounded_assessments, CANDIDATE_KEYS
from factor_grounding import request_payload, FORECAST_HORIZON
import deepseek_policy as P


def response(candidates, macro, as_of, *, assessments=None, model=None):
    candidates = [{key: c[key] for key in CANDIDATE_KEYS if key in c} for c in candidates]
    payload = request_payload(public_payload(candidates, macro, as_of))
    expected = {c['ticker']: c for c in payload['candidates']}
    if assessments is None:
        assessments = [{'ticker': c['ticker'], 'directional_lean': 'NO_EDGE', 'sentiment_score': 0.,
            'factor_rationale': 'The supplied issuer evidence does not establish directional support.'}
            for c in candidates]
    raw = []
    for row in assessments:
        candidate = expected[row['ticker']]
        evidence = candidate['headlines'] + candidate['catalyst_tags']
        raw.append({**row, 'evidence_ids': [evidence[0]['evidence_id']] if evidence else [],
            'forecast_horizon': FORECAST_HORIZON})
    rows, grounding, private = parse_grounded_assessments(json.dumps({'assessments': raw}), payload)
    return {'status': 'READY' if len(rows) == len(candidates) else 'PARTIAL' if rows else 'UNAVAILABLE',
        'model': model or P.DEFAULT_MODEL, 'prompt_version': P.PROMPT_VERSION,
        'schema_version': P.SCHEMA_VERSION, 'assessments': rows, 'grounding': grounding,
        'private_grounding_receipt': private, 'errorcode': None,
        'input_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
            allow_nan=False).encode()).hexdigest()}


def snapshot_receipt(snapshot):
    """Attach a real replayable offline receipt to a valid newly constructed fixture."""
    names = {row['ticker'] for row in snapshot['assessments']}
    candidates = [c for c in snapshot['inputs']['candidates'] if c['ticker'] in names]
    if not candidates:
        return snapshot
    from grounded_records import merge_grounding
    original = {row['ticker']: row for row in snapshot['assessments']}
    old_batches = snapshot.get('batches') or [{}]
    snapshot['batches'], snapshot['assessments'], snapshot['private_grounding_receipts'] = [], [], []
    notes = []
    for i, start in enumerate(range(0, len(candidates), P.BATCH_SIZE)):
        batch = candidates[start:start+P.BATCH_SIZE]
        fixture_rows = [{**original[c['ticker']],
            'factor_rationale': 'The supplied issuer update supports the stated contextual opinion.'} for c in batch]
        result = response(batch, snapshot['inputs']['macro'], snapshot['inputs']['as_of'],
            assessments=fixture_rows, model=snapshot['model'])
        old_batch = old_batches[i] if i < len(old_batches) else old_batches[0]
        snapshot['batches'].append({**old_batch, 'tickers': [c['ticker'] for c in batch],
            'status': result['status'], 'input_sha256': result['input_sha256']})
        snapshot['assessments'].extend(result['assessments'])
        notes.append(result['grounding'])
        snapshot['private_grounding_receipts'].append({'batch_index': i, **{k: result[k] for k in
            ('status', 'input_sha256', 'assessments', 'grounding', 'private_grounding_receipt')}})
    snapshot['grounding'] = merge_grounding(notes)
    return snapshot
