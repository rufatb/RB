"""A real-input diagnostic cannot become a retrospective morning publication."""
import datetime as dt
import json

import pytest

import probe_deepseek as P
import deepseek_factors
from test_factor_inputs import payload, NOW
from test_prepare_deepseek import pool, success


def inputs(tmp_path, value=None):
    p = tmp_path/'supplied-inputs.json'
    p.write_text(json.dumps(payload() if value is None else value))
    return p


def test_real_probe_checks_complete_names_and_preserves_original_attempt(tmp_path):
    old = tmp_path/'deepseek_history'/str(NOW.date())
    old.mkdir(parents=True)
    original = {'deepseek_snapshot.json': b'original frozen failure',
                'reports.sqlite3': b'existing opaque publication',
                'operations.json': b'prior operations'}
    for name, value in original.items(): (tmp_path/name).write_bytes(value)
    (old/'attempt.json').write_bytes(b'original morning attempt')
    p = pool(2); p['candidates'][1]['headlines'] = []
    seen = []
    def evaluate(candidates, macro, as_of, **kwargs):
        seen.extend(c['ticker'] for c in candidates)
        assert all('technical_provenance' not in c for c in candidates)
        return success(candidates, macro, as_of, **kwargs)
    result, directory = P.probe_real(tmp_path, inputs(tmp_path,p), evaluator=evaluate,
        clock=lambda: NOW+dt.timedelta(hours=3))
    assert seen == ['X0']
    assert result['status'] == 'PARTIAL' and result['api_status'] == 'READY'
    assert (result['requested'], result['eligible'], result['covered']) == (2,1,1)
    assert result['candidate_gaps']['X1'] == ['NO_CURRENT_CATALYST_EVIDENCE']
    assert not result['morning_snapshot'] and not result['prediction_evidence']
    assert json.loads((directory/'attempt.json').read_text())['status'] == 'COMPLETED'
    for name, value in original.items(): assert (tmp_path/name).read_bytes() == value
    assert (old/'attempt.json').read_bytes() == b'original morning attempt'
    # Even if somebody supplies this path to the production reader, it rejects
    # the diagnostic rather than claiming a pre-open assessment.
    rejected = deepseek_factors.load_prepared(tmp_path,NOW+dt.timedelta(hours=3),path=directory/'result.json')
    assert rejected['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('mutation', ['macro','technicals','future','no_news'])
def test_incomplete_real_input_never_triggers_a_model_call(tmp_path,mutation):
    p=payload()
    if mutation=='macro':p['macro'].pop('vix')
    elif mutation=='technicals':p['candidates'][0]['technicals']['macd']=None
    elif mutation=='future':p['as_of']=(NOW+dt.timedelta(days=1)).isoformat()
    else:p['candidates'][0]['headlines']=[]
    def forbidden(*a,**k):pytest.fail('incomplete input reached model')
    result,_=P.probe_real(tmp_path,inputs(tmp_path,p),evaluator=forbidden,clock=lambda:NOW)
    assert result['covered']==result['eligible']==0
    assert result['status']=='UNAVAILABLE' and result['api_receipt']['errorcode']=='NO_COMPLETE_INPUTS'


def test_real_probe_does_not_silently_sample_oversized_pool(tmp_path):
    with pytest.raises(ValueError,match='AT_MOST_25'):
        P.probe_real(tmp_path,inputs(tmp_path,pool(26)),evaluator=success,clock=lambda:NOW)
    assert not (tmp_path/'diagnostics').exists()


def test_real_probe_transport_error_is_explicit_without_secret_or_retries(tmp_path):
    called=[]
    def fail(*a,**k):
        called.append(True)
        raise TimeoutError('private key should never be in diagnostics')
    result,directory=P.probe_real(tmp_path,inputs(tmp_path),evaluator=fail,clock=lambda:NOW)
    assert called==[True]
    assert result['covered']==0 and result['api_receipt']['details']=='TimeoutError'
    assert 'private key' not in (directory/'result.json').read_text()


def test_real_probe_missing_or_duplicate_assessment_stays_unavailable(tmp_path):
    def missing(*a,**k): return {'status':'READY','assessments':[]}
    result,_=P.probe_real(tmp_path,inputs(tmp_path),evaluator=missing,clock=lambda:NOW)
    assert result['covered']==0 and result['api_receipt']['details']=='ResponseSchemaError'


@pytest.mark.parametrize('field',['headline','scope','computation','url'])
def test_private_input_is_rejected_before_any_diagnostic_copy_or_api_call(tmp_path,monkeypatch,field):
    secret='fixture-private-credential-never-persist'
    monkeypatch.setenv('DEEPSEEK_API_KEY',secret)
    p=payload(); c=p['candidates'][0]
    if field=='headline':c['headlines'][0]['title']='Operating update '+secret
    elif field=='scope':c['technicals_scope']='previous_completed_session; '+secret
    elif field=='computation':c['technical_provenance']['computation']=secret
    else:c['headlines'][0]['source_url']='https://issuer.example/'+secret
    def no_call(*a,**k):pytest.fail('private input reached evaluator')
    with pytest.raises(ValueError,match='PRIVATE_DIAGNOSTIC_INPUT_REJECTED'):
        P.probe_real(tmp_path,inputs(tmp_path,p),evaluator=no_call,clock=lambda:NOW)
    assert not (tmp_path/'diagnostics').exists()


def test_provider_receipt_free_text_is_redacted(tmp_path,monkeypatch):
    secret='fixture-private-receipt-value'
    monkeypatch.setenv('DEEPSEEK_API_KEY',secret)
    def fail(*a,**k):
        return {'status':'UNAVAILABLE','assessments':[], 'errorcode':'TIMEOUT','details':secret}
    result,path=P.probe_real(tmp_path,inputs(tmp_path),evaluator=fail,clock=lambda:NOW)
    assert result['api_receipt']['details']=='[REDACTED]'
    assert secret not in (path/'result.json').read_text()
