"""Explicit API checks; never overwrite a morning attempt or publication.

The default check is synthetic. --input exercises one real, validated public
batch at the actual current clock, outside the report path. Its diagnostic
receipt is deliberately not a loadable pre-open model snapshot.
"""
import argparse
import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from adapters.deepseek_adapter import evaluate_batch, MACRO_KEYS, parse_assessments
from build_biotech import write_atomic
from prepare_deepseek import load_private_key, load_private_model
from diagnostics import safe_detail
import deepseek_policy as P


def probe_real(state_dir, input_path, *, evaluator=evaluate_batch, clock=None):
    """Check at most one actual batch, retaining input gaps and exact outputs.

    No news/price fetching, backdating, production retries, fabricated inputs
    or rewriting of a failed morning snapshot. Incomplete names are not sent.
    A READY API response does not mean the entire requested pool was complete.
    """
    import hashlib
    from bounded import acquire
    from factor_inputs import _read, validate_payload, eligible_public_candidates
    from report_store import encode
    from deepseek_factors import research_watchlist
    clock = clock or (lambda: dt.datetime.now(ZoneInfo('America/New_York')))
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('AWARE_DIAGNOSTIC_CLOCK_REQUIRED')
    raw = _read(Path(input_path))
    if not isinstance(raw, dict) or not isinstance(raw.get('candidates'), list):
        raise ValueError('INVALID_DIAGNOSTIC_INPUT')
    if not 1 <= len(raw['candidates']) <= P.BATCH_SIZE:
        raise ValueError('REAL_DIAGNOSTIC_REQUIRES_ONE_BATCH_AT_MOST_25_NAMES')
    credential_failure = None
    try:
        key_ok = load_private_key(state_dir) or evaluator is not evaluate_batch
    except Exception as exc:
        key_ok = False
        credential_failure = type(exc).__name__
    # Reject private input before writing any diagnostic copy. Do not redact
    # private facts into a purported successful public-evidence request.
    encoded_raw = encode(raw)
    secrets = [value for name, value in os.environ.items() if len(value) >= 6
               and any(tag in name.upper() for tag in ('KEY', 'TOKEN', 'PASSWORD', 'SECRET'))]
    if (any(secret in encoded_raw for secret in secrets)
            or re.search(r'\bsk-[A-Za-z0-9_-]{12,}', encoded_raw)
            or re.search(r'(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}', encoded_raw)):
        raise ValueError('PRIVATE_DIAGNOSTIC_INPUT_REJECTED')
    clean = validate_payload(raw, now)
    candidates, eligibility_gaps = eligible_public_candidates(clean)
    for ticker, reasons in eligibility_gaps.items():
        if not clean['candidate_gaps'].get(ticker):
            clean['candidate_gaps'][ticker] = reasons
    directory = Path(state_dir)/'diagnostics'/('deepseek-real-'+now.strftime('%Y%m%dT%H%M%S%f'))
    directory.mkdir(parents=True, exist_ok=False)
    input_hash = hashlib.sha256(encode(clean).encode()).hexdigest()
    outcome_gaps = {ticker: list(notes) for ticker, notes in clean['candidate_gaps'].items()}
    write_atomic(directory/'inputs.json', clean)
    write_atomic(directory/'attempt.json', {'kind': 'REAL_INPUT_API_DIAGNOSTIC',
        'started_at': now.isoformat(), 'status': 'STARTED', 'input_sha256': input_hash,
        'morning_snapshot': False, 'prediction_evidence': False})
    started = time.monotonic()
    result = {'status': 'UNAVAILABLE', 'assessments': [],
              'errorcode': 'NO_COMPLETE_INPUTS', 'model': None}
    if candidates:
        try:
            model = load_private_model(state_dir)
            if not key_ok:
                result['errorcode'] = 'INVALID_PRIVATE_CREDENTIAL' if credential_failure else 'MISSING_API_KEY'
                result['details'] = credential_failure
            else:
                def request():
                    return evaluator(candidates, clean['macro'], clean['as_of'], model=model,
                                     timeout=P.REQUEST_TIMEOUT)
                if evaluator is evaluate_batch:
                    got = acquire({'deepseek_probe': (request, P.REQUEST_TIMEOUT)})['deepseek_probe']
                    result = got.get('value') or {'status': 'UNAVAILABLE', 'assessments': [],
                        'errorcode': 'BOUNDED_REQUEST_FAILURE', 'details': got.get('error'), 'model': model}
                else:
                    result = request()
                if result.get('status') in ('READY', 'PARTIAL') or result.get('grounding'):
                    from grounded_records import validate_result
                    rows, grounding, private = validate_result(result, candidates, clean['macro'], clean['as_of'])
                    result['assessments'] = rows
                    for ticker, issues in grounding['excluded'].items():
                        outcome_gaps.setdefault(ticker, []).extend('GROUNDING:'+code for code in issues)
                    write_atomic(directory/'private-grounding-receipt.json', private)
                else:
                    result['assessments'] = []
        except Exception as exc:
            result = {'status': 'UNAVAILABLE', 'assessments': [],
                      'errorcode': 'DIAGNOSTIC_FAILED', 'details': type(exc).__name__}
    finished = clock()
    rows = result.get('assessments', [])
    status = 'READY' if len(rows) == len(raw['candidates']) else 'PARTIAL' if rows else 'UNAVAILABLE'
    diagnostic = {'kind': 'REAL_INPUT_API_DIAGNOSTIC_NOT_MORNING_SNAPSHOT',
        'checked_at': now.isoformat(), 'finished_at': finished.isoformat(),
        'elapsed_seconds': round(time.monotonic()-started, 3),
        'status': status, 'api_status': result.get('status'),
        'requested': len(raw['candidates']), 'eligible': len(candidates), 'covered': len(rows),
        'inputs': clean, 'input_sha256': input_hash,
        'assessments': rows, 'candidate_gaps': outcome_gaps, 'gaps': clean['gaps'],
        'grounding': result.get('grounding'),
        'adopted': False, 'morning_snapshot': False, 'prediction_evidence': False,
        'api_receipt': {k: safe_detail(result[k]) if isinstance(result.get(k),str) else
            None if result.get(k) is None else 'INVALID_METADATA' for k in ('status', 'model', 'response_model', 'inference_mode',
            'request_id', 'response_id', 'input_sha256', 'errorcode', 'details')},
        'scope': 'Actual current-time public-input check; not a 09:46 replay, live entry or accuracy test.'}
    diagnostic['research_watchlist'] = research_watchlist(diagnostic)
    write_atomic(directory/'result.json', diagnostic)
    write_atomic(directory/'attempt.json', {'kind': 'REAL_INPUT_API_DIAGNOSTIC',
        'started_at': now.isoformat(), 'finished_at': finished.isoformat(), 'status': 'COMPLETED',
        'input_sha256': input_hash, 'morning_snapshot': False, 'prediction_evidence': False})
    return diagnostic, directory


def probe(state_dir, *, evaluator=evaluate_batch):
    now = dt.datetime.now(ZoneInfo('America/New_York'))
    # Deliberately fictitious symbols and explicitly synthetic public-looking
    # fixture URLs; no observed market fact or provider data receipt is asserted.
    rows = [{'ticker': 'TEST'+str(i), 'technicals': {'rsi': 50.0},
             'technicals_as_of': now.isoformat(), 'technicals_scope': 'SYNTHETIC CONTRACT FIXTURE',
             'technical_source': 'python', 'source_url': 'https://example.com/synthetic',
             'headlines': [{'title': 'Synthetic API contract fixture: no directional evidence; not a real issuer.',
                            'source_url': 'https://example.com/synthetic', 'published_at': now.isoformat()}],
             'catalyst_tags': []} for i in range(25)]
    macro = {name: {'value': 100.0, 'as_of': now.isoformat(),
                    'source_url': 'https://example.com/synthetic'} for name in MACRO_KEYS}
    load_private_key(state_dir)
    model = load_private_model(state_dir)
    started = time.monotonic()
    result = evaluator(rows, macro, now.isoformat(), model=model)
    if result.get('status') in ('READY', 'PARTIAL') or result.get('grounding'):
        from grounded_records import validate_result
        validate_result(result, rows, macro, now.isoformat())
    receipt = {'kind': 'SYNTHETIC_API_SCHEMA_PROBE_NOT_MARKET_DATA',
               'checked_at': now.isoformat(), 'elapsed_seconds': round(time.monotonic()-started, 3),
               'requested': 25, 'covered': len(result.get('assessments', [])),
               **{k: result.get(k) for k in ('status', 'model', 'response_model', 'inference_mode',
                    'request_id', 'response_id', 'input_sha256', 'errorcode', 'details')},
               'prediction_evidence': False, 'prompt_version': P.PROMPT_VERSION,
               'grounding_excluded': len((result.get('grounding') or {}).get('excluded', {}))}
    path = Path(state_dir)/'diagnostics'/('deepseek-contract-'+now.strftime('%Y%m%dT%H%M%S%f')+'.json')
    write_atomic(path, receipt)
    if result.get('private_grounding_receipt'):
        write_atomic(path.with_suffix('.private.json'), result)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--input', help='Current validated public inputs for one real diagnostic batch, at most 25 names.')
    args = parser.parse_args()
    if args.input:
        result, directory = probe_real(args.state_dir, args.input)
        print(json.dumps({key: result[key] for key in ('kind', 'status', 'api_status',
            'requested', 'eligible', 'covered', 'elapsed_seconds', 'api_receipt')}, indent=2))
        raise SystemExit(0 if result['api_status'] == 'READY' else 2)
    else:
        result = probe(args.state_dir)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['status'] == 'READY' else 2)
