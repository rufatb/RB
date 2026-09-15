"""A genuine pre-model failure keeps its cause through local loading/rendering."""
import hashlib
import json

import pytest

import deepseek_factors as D
import prepare_deepseek as S
from report_store import encode
from test_deepseek_factors import PREP, NOW, assessment


CAUSE = 'Prior DeepSeek preparation is incomplete or ambiguous; no automatic retry.'


def failure():
    return S._seal(S._failure_snapshot(PREP, CAUSE))


def save(tmp_path, obj, *, reseal=True):
    obj = S._seal(obj) if reseal else obj
    path = tmp_path/'deepseek_snapshot.json'
    path.write_text(json.dumps(obj))
    return path


def test_pre_model_failure_keeps_exact_safe_cause_and_remains_read_only(tmp_path, monkeypatch):
    import adapters.deepseek_adapter as adapter
    monkeypatch.setattr(adapter, 'evaluate_batch', lambda *a, **k: pytest.fail('loader called API'))
    path = save(tmp_path, failure())
    before = path.read_bytes()
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE' and result['model'] is None
    assert result['assessments'] == result['batches'] == []
    assert result['requested'] == result['covered'] == 0
    assert result['reason'] == CAUSE and result['gaps'][0] == CAUSE
    assert result['snapshot_sha256'] == json.loads(before)['snapshot_sha256']
    assert result['research_watchlist']['status'] == 'UNAVAILABLE'
    assert path.read_bytes() == before


def test_failure_reason_reaches_existing_concise_and_full_renderers(tmp_path):
    import brief
    import daily_render
    import email_render
    from test_deepseek_render import report
    save(tmp_path, failure())
    result = D.load_prepared(tmp_path, NOW)
    digest = report()
    digest['intraday']['deepseek'] = result
    before = encode(digest)
    for body in (brief.render_text(digest), brief.render_html(digest),
                 email_render.text(digest), '\n'.join(daily_render.deepseek_summary(digest['intraday']))):
        assert CAUSE in body
        assert 'invalid model identifier' not in body
    assert encode(digest) == before


@pytest.mark.parametrize('mutate', [
    lambda obj: obj.update(status='READY'),
    lambda obj: obj.update(status='PARTIAL'),
    lambda obj: obj.update(assessments=[assessment()]),
    lambda obj: obj.update(batches=[{'status': 'UNAVAILABLE', 'errorcode': 'TIMEOUT'}]),
    lambda obj: obj.update(batches=[{}]),
    lambda obj: obj.update(batches=None),
    lambda obj: obj.update(assessments=None),
])
def test_missing_model_never_qualifies_success_or_any_provider_record(tmp_path, mutate):
    obj = failure(); mutate(obj); save(tmp_path, obj)
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert 'snapshot rejected' in result['reason']
    assert 'invalid model identifier' in result['reason']
    assert result['assessments'] == []


@pytest.mark.parametrize('mutate', [
    lambda obj: obj.update(session='2026-09-10'),
    lambda obj: obj.update(prepared_at='2026-09-11T09:30:00-04:00'),
    lambda obj: obj.update(prepared_at='2026-09-11T09:47:00-04:00'),
    lambda obj: obj.update(input_sha256='0'*64),
    lambda obj: obj['inputs'].update(as_of='2026-09-11T08:34:00-04:00'),
])
def test_failure_exception_keeps_time_and_input_identity_validation(tmp_path, mutate):
    obj = failure(); mutate(obj); save(tmp_path, obj)
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'].startswith('DeepSeek snapshot rejected:')
    assert result['reason'] != CAUSE


def test_failure_exception_does_not_ignore_a_broken_seal(tmp_path):
    obj = failure(); obj['gaps'] = ['Changed cause without updating the seal.']
    save(tmp_path, obj, reseal=False)
    result = D.load_prepared(tmp_path, NOW)
    assert 'snapshot integrity mismatch' in result['reason']


def test_preserved_failure_notes_are_redacted_before_rendering(tmp_path, monkeypatch):
    secret = 'private-fixture-credential-never-print'
    monkeypatch.setenv('DEEPSEEK_API_KEY', secret)
    obj = failure(); obj['gaps'] = ['Preparation failed with '+secret]
    save(tmp_path, obj)
    result = D.load_prepared(tmp_path, NOW)
    assert secret not in encode(result)
    assert 'Preparation failed' in result['reason']


def test_invalid_model_does_not_erase_actual_candidate_coverage(tmp_path):
    from test_deepseek_factors import public_inputs
    obj = failure()
    obj['inputs'] = public_inputs(('TRP.TO', 'ENB.TO'))
    obj['input_sha256'] = hashlib.sha256(encode(obj['inputs']).encode()).hexdigest()
    obj['requested'] = 2
    obj['gaps'] = ['INVALID_MODEL: no DeepSeek request attempted.']
    save(tmp_path, obj)
    result = D.load_prepared(tmp_path, NOW)
    assert result['requested'] == 2 and result['covered'] == 0
    assert result['model'] is None and result['status'] == 'UNAVAILABLE'
    assert result['reason'] == obj['gaps'][0]
    assert all('MODEL_ASSESSMENT_UNAVAILABLE' in notes for notes in result['candidate_gaps'].values())
