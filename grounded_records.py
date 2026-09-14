"""Replay the bounded grounded contract before accepting or loading factors.

Model-written prose belongs only to the private sealed receipt. Public report
views receive the deterministic projection and its bounded verification notes.
No network, inference, selection or state mutation is performed here.
"""
from __future__ import annotations

import hashlib
import json
import re


class GroundingValidationError(ValueError):
    """Controlled credential-free rejection of a grounded receipt."""


def validate_result(response, candidates, macro, as_of):
    """Reconstruct a response from retained rows and verify every public field."""
    from adapters.deepseek_adapter import public_payload, parse_grounded_assessments
    from factor_grounding import VERSION, request_payload
    if not isinstance(response, dict):
        raise GroundingValidationError('GROUNDED_RESPONSE_REQUIRED')
    receipt = response.get('private_grounding_receipt')
    if (not isinstance(receipt, dict) or receipt.get('version') != VERSION
            or not isinstance(receipt.get('provider_rows'), list)
            or not isinstance(receipt.get('raw_response_sha256'), str)
            or not re.fullmatch('[a-f0-9]{64}', receipt['raw_response_sha256'])):
        raise GroundingValidationError('GROUNDED_RECEIPT_REQUIRED')
    enriched = request_payload(public_payload(candidates, macro, as_of))
    encoded = json.dumps(enriched, sort_keys=True, ensure_ascii=False, allow_nan=False)
    expected_hash = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
    if response.get('input_sha256') != expected_hash:
        raise GroundingValidationError('GROUNDED_REQUEST_IDENTITY_MISMATCH')
    rows, grounding, _ = parse_grounded_assessments(
        json.dumps({'assessments': receipt['provider_rows']}, allow_nan=False), enriched)
    status = 'READY' if len(rows) == len(candidates) else 'PARTIAL' if rows else 'UNAVAILABLE'
    if (response.get('assessments') != rows or response.get('grounding') != grounding
            or response.get('status') != status):
        raise GroundingValidationError('GROUNDED_PROJECTION_MISMATCH')
    # Do not replace the original byte hash with the reserialized-row hash.
    return rows, grounding, receipt


def merge_grounding(batches):
    """Union independent verified batch notes; duplicates are never accepted."""
    from factor_grounding import VERSION
    result = {'version': VERSION, 'per_ticker': {}, 'excluded': {}}
    for notes in batches:
        if not isinstance(notes, dict) or notes.get('version') != VERSION:
            raise GroundingValidationError('GROUNDING_VERSION_MISMATCH')
        for field in ('per_ticker', 'excluded'):
            entries = notes.get(field)
            if not isinstance(entries, dict) or set(entries) & set(result[field]):
                raise GroundingValidationError('GROUNDING_BATCH_IDENTITY_MISMATCH')
            result[field].update(entries)
    return result


def validate_snapshot(snapshot):
    """Recheck saved batch projections; return public notes without raw prose."""
    from adapters.deepseek_adapter import CANDIDATE_KEYS
    from factor_grounding import VERSION
    receipts = snapshot.get('private_grounding_receipts', [])
    batches = snapshot.get('batches', [])
    if not isinstance(receipts, list) or not isinstance(batches, list):
        raise GroundingValidationError('INVALID_GROUNDED_SNAPSHOT')
    for batch in batches:
        if not isinstance(batch, dict):
            raise GroundingValidationError('INVALID_GROUNDED_BATCH')
        if 'grounded_contract' in batch and batch['grounded_contract'] != VERSION:
            raise GroundingValidationError('GROUNDED_BATCH_VERSION_MISMATCH')
    inputs = snapshot['inputs']
    candidates = {c['ticker']: {key: c[key] for key in CANDIDATE_KEYS if key in c}
                  for c in inputs['candidates']}
    notes, rows, seen = [], [], set()
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise GroundingValidationError('INVALID_GROUNDED_SNAPSHOT_RECEIPT')
        index = receipt.get('batch_index')
        if type(index) is not int or not 0 <= index < len(batches) or index in seen:
            raise GroundingValidationError('GROUNDED_BATCH_INDEX_MISMATCH')
        seen.add(index)
        batch = batches[index]
        if (batch.get('status') != receipt.get('status')
                or batch.get('input_sha256') != receipt.get('input_sha256')):
            raise GroundingValidationError('GROUNDED_BATCH_METADATA_MISMATCH')
        requested = [candidates[ticker] for ticker in batch['tickers']]
        accepted, grounding, _ = validate_result(receipt, requested, inputs['macro'], inputs['as_of'])
        rows.extend(accepted)
        notes.append(grounding)
    if any((batch.get('status') in ('READY', 'PARTIAL')
            or batch.get('errorcode') == 'GROUNDING_EXCLUSIONS'
            or 'grounded_contract' in batch) and i not in seen
           for i, batch in enumerate(batches)):
        raise GroundingValidationError('GROUNDED_RECEIPT_REQUIRED')
    merged = merge_grounding(notes)
    if snapshot.get('assessments') != rows:
        raise GroundingValidationError('GROUNDED_ASSESSMENTS_MISMATCH')
    if (receipts or rows or 'grounding' in snapshot) and snapshot.get('grounding') != merged:
        raise GroundingValidationError('GROUNDED_NOTES_MISMATCH')
    return merged
