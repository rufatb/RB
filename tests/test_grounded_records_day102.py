"""Receipts bind accepted factors to their actual inputs and private response."""
import copy
import hashlib
import json

import pytest

from grounded_records import GroundingValidationError, validate_snapshot
from grounded_helpers import response
from test_deepseek_factors import snapshot
from test_prepare_deepseek import pool, CFG, NOW


@pytest.mark.parametrize('field', ['receipt', 'score', 'input', 'notes'])
def test_outer_reseal_cannot_repair_broken_request_projection(field):
    obj = snapshot()
    if field == 'receipt':
        obj['private_grounding_receipts'] = []
    elif field == 'score':
        obj['assessments'][0]['sentiment_score'] = .9
    elif field == 'input':
        obj['inputs']['candidates'][0]['technicals']['macd_hist'] = -.5
    else:
        obj['grounding']['per_ticker']['TRP.TO']['forecast_horizon'] = 'next_year'
    with pytest.raises(GroundingValidationError):
        validate_snapshot(obj)


def test_private_prose_is_not_returned_by_snapshot_validation():
    obj = snapshot()
    before = copy.deepcopy(obj)
    notes = validate_snapshot(obj)
    raw = obj['private_grounding_receipts'][0]['private_grounding_receipt']['provider_rows'][0]['factor_rationale']
    assert raw not in json.dumps(notes)
    assert obj == before


def test_semantic_exclusions_do_not_stop_later_independent_batches(tmp_path):
    import prepare_deepseek as S
    called = []
    def evaluate(candidates, macro, as_of, **kwargs):
        called.append(len(candidates))
        # The entire first two-batch wave violates the prose contract. The
        # provider still worked; the third batch must be assessed normally.
        rows = [{'ticker': c['ticker'], 'directional_lean': 'BULL', 'sentiment_score': .5,
                 'factor_rationale': 'A negative MACD histogram supports this lean.'}
                for c in candidates] if len(called) <= 2 else None
        return response(candidates, macro, as_of, assessments=rows, model=kwargs['model'])
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(51), evaluator=evaluate)
    assert called == [25, 25, 1]
    assert result['status'] == 'PARTIAL' and result['covered'] == 1
    assert result['assessments'][0]['ticker'] == 'X50'
    assert len(result['grounding']['excluded']) == 50
    assert len(validate_snapshot(result)['excluded']) == 50


@pytest.mark.parametrize('marker', ['flag', 'errorcode'])
def test_all_excluded_batch_cannot_lose_receipt_when_unavailable(tmp_path, marker):
    import prepare_deepseek as S
    from factor_grounding import VERSION
    from grounded_records import merge_grounding
    def evaluate(candidates, macro, as_of, **kwargs):
        rows = [{'ticker': c['ticker'], 'directional_lean': 'BULL', 'sentiment_score': .5,
                 'factor_rationale': 'A negative MACD histogram supports this lean.'}
                for c in candidates]
        return response(candidates, macro, as_of, assessments=rows, model=kwargs['model'])
    obj = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1), evaluator=evaluate)
    assert obj['status'] == 'UNAVAILABLE' and obj['covered'] == 0
    assert obj['batches'][0]['grounded_contract'] == VERSION
    assert len(validate_snapshot(obj)['excluded']) == 1
    if marker == 'errorcode':
        obj['batches'][0].pop('grounded_contract')
        obj['batches'][0]['errorcode'] = 'GROUNDING_EXCLUSIONS'
    obj['private_grounding_receipts'] = []
    obj['grounding'] = merge_grounding([])
    with pytest.raises(GroundingValidationError, match='GROUNDED_RECEIPT_REQUIRED'):
        validate_snapshot(obj)


def test_invalid_explicit_grounded_batch_version_cannot_pass_with_valid_receipt():
    obj = snapshot()
    obj['batches'][0]['grounded_contract'] = 'unregistered-version'
    with pytest.raises(GroundingValidationError, match='GROUNDED_BATCH_VERSION_MISMATCH'):
        validate_snapshot(obj)


def test_probe_grounding_gaps_do_not_mutate_hashed_inputs(tmp_path):
    import probe_deepseek as P
    from test_deepseek_real_probe import inputs
    def evaluate(candidates, macro, as_of, **kwargs):
        rows = [{'ticker': c['ticker'], 'directional_lean': 'BULL', 'sentiment_score': .5,
                 'factor_rationale': 'A negative MACD histogram supports this lean.'}
                for c in candidates]
        return response(candidates, macro, as_of, assessments=rows, model=kwargs['model'])
    result, directory = P.probe_real(tmp_path, inputs(tmp_path, pool(1)),
                                   evaluator=evaluate, clock=lambda: NOW)
    saved = json.loads((directory/'inputs.json').read_text())
    from report_store import encode
    assert hashlib.sha256(encode(saved).encode()).hexdigest() == result['input_sha256']
    assert result['candidate_gaps']['X0'] == ['GROUNDING:TECHNICAL_PROSE_PROHIBITED']
    assert saved['candidate_gaps']['X0'] == []
