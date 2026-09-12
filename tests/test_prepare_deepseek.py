import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import prepare_deepseek as S
from test_factor_inputs import payload, NOW, CFG


def pool(count):
    p = payload(); row = p['candidates'][0]
    p['candidates'] = [dict(row, ticker='X'+str(i)) for i in range(count)]
    return p


def success(candidates, macro, as_of, **kwargs):
    return {'status': 'READY', 'assessments': [{'ticker': c['ticker'],
        'directional_lean': 'NO_EDGE', 'sentiment_score': 0.,
        'factor_rationale': 'The staged evidence does not establish a directional advantage.'}
        for c in candidates], 'model': kwargs['model'], 'errorcode': None}


def test_500_candidates_are_batched_once_and_same_day_replay_never_calls_again(tmp_path):
    calls = []
    def evaluate(candidates, macro, as_of, **kwargs):
        calls.append(len(candidates))
        assert set(macro) == set(S.P.MACRO_KEYS)
        assert all('technical_provenance' not in c for c in candidates)
        assert kwargs['timeout'] <= S.P.REQUEST_TIMEOUT
        return success(candidates, macro, as_of, **kwargs)
    first = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(500), evaluator=evaluate)
    assert first['status'] == 'READY'
    assert first['covered'] == first['requested'] == 500
    assert calls == [25]*20
    again = S.prepare(tmp_path, CFG, now=NOW+dt.timedelta(minutes=10), inputs=pool(1),
                      evaluator=lambda *a, **k: pytest.fail('same-day duplicate API call'))
    assert again == first
    assert (tmp_path/'deepseek_history'/str(NOW.date())/'attempt.json').exists()


def test_partial_candidate_contract_does_not_block_valid_independent_batch(tmp_path):
    p = pool(2); p['candidates'][0].pop('technical_source')
    called = []
    def evaluate(candidates, macro, as_of, **kwargs):
        called.extend(c['ticker'] for c in candidates)
        return success(candidates, macro, as_of, **kwargs)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=p, evaluator=evaluate)
    assert called == ['X1']
    assert result['covered'] == 1 and result['requested'] == 2 and result['status'] == 'PARTIAL'
    assert result['candidate_gaps']['X0']


def test_missing_macro_is_explicit_null_for_provider_and_never_ready(tmp_path):
    p = pool(1); p['macro'].pop('vix')
    def evaluate(candidates, macro, as_of, **kwargs):
        assert macro['vix'] is None
        return success(candidates, macro, as_of, **kwargs)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=p, evaluator=evaluate)
    assert result['status'] == 'PARTIAL'
    assert 'INCOMPLETE_MACRO' in result['candidate_gaps']['X0']


def test_missing_unstructured_evidence_skips_model_without_fake_no_edge(tmp_path):
    p = pool(1); p['candidates'][0]['headlines'] = []
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=p,
        evaluator=lambda *a, **k: pytest.fail('missing evidence must not call model'))
    assert result['covered'] == 0 and not result['assessments']
    assert result['status'] == 'UNAVAILABLE'


def test_failure_stops_remaining_batches_and_saves_same_day_failure(tmp_path):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        return {'status': 'UNAVAILABLE', 'assessments': [], 'errorcode': 'TIMEOUT'}
    first = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(50), evaluator=fail)
    assert calls == [1] and first['covered'] == 0
    again = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(50), evaluator=fail)
    assert again == first and calls == [1]
    assert len(first['candidate_gaps']) == 50


def test_provider_exception_is_visible_bounded_and_secret_free(tmp_path):
    secret = 'sk-test-private-should-never-appear'
    def fail(*a, **k):
        raise TimeoutError('https://provider.example/?token='+secret)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1), evaluator=fail)
    assert result['status'] == 'UNAVAILABLE'
    assert 'TimeoutError' in ' '.join(result['gaps'])
    assert secret not in json.dumps(result)
    assert secret not in (tmp_path/'deepseek_snapshot.json').read_text()


def test_corrupt_assessment_or_receipt_replay_never_retries_or_overwrites_history(tmp_path):
    S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1), evaluator=success)
    prior = tmp_path/'deepseek_history'/str(NOW.date())/'snapshot.json'
    obj = json.loads(prior.read_text()); obj['assessments'][0]['sentiment_score'] = .9
    prior.write_text(json.dumps(obj)); corrupted = prior.read_bytes()
    result = S.prepare(tmp_path, CFG, now=NOW, evaluator=lambda *a, **k: pytest.fail('blind retry'))
    assert result['status'] == 'UNAVAILABLE'
    assert 'integrity' in result['gaps'][0]
    assert prior.read_bytes() == corrupted


def test_interrupted_attempt_blocks_retry_without_resetting_attempt(tmp_path):
    history = tmp_path/'deepseek_history'/str(NOW.date()); history.mkdir(parents=True)
    attempt = history/'attempt.json'; attempt.write_text('{"status":"STARTED"}')
    result = S.prepare(tmp_path, CFG, now=NOW, evaluator=lambda *a, **k: pytest.fail('blind retry'))
    assert result['status'] == 'UNAVAILABLE'
    assert 'ambiguous' in result['gaps'][0]
    assert attempt.read_text() == '{"status":"STARTED"}'


def test_pre_open_gate_precedes_any_state_or_network_work(tmp_path):
    with pytest.raises(ValueError, match='pre-open'):
        S.prepare(tmp_path, CFG, now=NOW.replace(hour=9, minute=30), evaluator=success)
    assert list(tmp_path.iterdir()) == []


def test_deadline_exhaustion_never_calls_model(tmp_path, monkeypatch):
    clock = iter([0., S.P.PREP_BUDGET_SECONDS+1])
    monkeypatch.setattr(S.time, 'monotonic', lambda: next(clock))
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1),
                       evaluator=lambda *a, **k: pytest.fail('budget exceeded'))
    assert result['covered'] == 0
    assert 'DeepSeek preparation deadline reached.' in result['gaps']


def test_private_key_read_failure_is_a_durable_visible_snapshot(tmp_path, monkeypatch):
    def fail(*a):
        raise PermissionError('private-secret-path')
    monkeypatch.setattr(S, 'load_private_key', fail)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1))
    assert result['status'] == 'UNAVAILABLE'
    assert 'PermissionError' in ' '.join(result['gaps'])
    assert 'private-secret-path' not in json.dumps(result)
    again = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1))
    assert again == result


def test_live_path_calls_analyst_delegate_inside_killable_budget(tmp_path, monkeypatch):
    import analyst
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-offline-test-credential')
    calls = []
    def evaluate(*a, **kw):
        calls.append(kw['timeout']); return success(*a, **kw)
    monkeypatch.setattr(analyst, 'analyze_factors', evaluate)
    def acquire(jobs):
        assert list(jobs) == ['deepseek']
        fn, budget = jobs['deepseek']; assert 0 < budget <= S.P.REQUEST_TIMEOUT
        return {'deepseek': {'value': fn(), 'error': None}}
    monkeypatch.setattr(S, 'acquire', acquire)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1))
    assert result['status'] == 'READY' and len(calls) == 1


def test_partial_macro_refresh_preserves_previous_valid_fields(tmp_path, monkeypatch):
    old = payload()['macro']; (tmp_path/'deepseek_macro.json').write_text(json.dumps(old))
    fresh = {**old, 'wti': {**old['wti'], 'value': 11.}, 'vix': None}
    def acquire(jobs):
        if 'macro' in jobs:
            return {'macro': {'value': {'values': fresh, 'gaps': ['vix acquisition failed']}, 'error': None}}
        return {key: {'value': None, 'error': 'TIMEOUT'} for key in jobs}
    monkeypatch.setattr(S, 'acquire', acquire)
    gaps = S.refresh_public_inputs(tmp_path, CFG, NOW)
    saved = json.loads((tmp_path/'deepseek_macro.json').read_text())
    assert saved['wti']['value'] == 11. and saved['vix'] == old['vix']
    assert 'vix acquisition failed' in gaps


def test_duplicate_existing_macro_file_is_preserved_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path/'deepseek_macro.json'; path.write_text('{"vix":1,"vix":2}')
    def acquire(jobs):
        if 'macro' in jobs:
            return {'macro': {'value': {'values': payload()['macro'], 'gaps': []}, 'error': None}}
        return {key: {'value': None, 'error': 'TIMEOUT'} for key in jobs}
    monkeypatch.setattr(S, 'acquire', acquire)
    gaps = S.refresh_public_inputs(tmp_path, CFG, NOW)
    assert path.read_text() == '{"vix":1,"vix":2}'
    assert any('unreadable' in gap for gap in gaps)


def test_news_failure_stops_subsequent_batches_and_retains_reviewed_tags(tmp_path, monkeypatch):
    prior = {'X0': {'headlines': [], 'catalyst_tags': [{'tag': 'reviewed-tag'}]}}
    (tmp_path/'deepseek_news.json').write_text(json.dumps(prior))
    cfg = {**CFG, 'scan': {'universe': ['X'+str(i) for i in range(8)]}}
    calls = []
    def acquire(jobs):
        calls.append(list(jobs))
        if 'macro' in jobs:
            return {'macro': {'value': {'values': payload()['macro'], 'gaps': []}, 'error': None}}
        return {key: {'value': {'headlines': [], 'catalyst_tags': []} if key == 'X0' else None,
                      'error': 'TIMEOUT'} for key in jobs}
    monkeypatch.setattr(S, 'acquire', acquire)
    S.refresh_public_inputs(tmp_path, cfg, NOW)
    saved = json.loads((tmp_path/'deepseek_news.json').read_text())
    assert saved['X0']['catalyst_tags'] == prior['X0']['catalyst_tags']
    assert len(calls) == 2 and calls[-1] == ['X0', 'X1', 'X2', 'X3']


@pytest.mark.parametrize('raw', ['{"candidates":[],"candidates":[]}', '{"value":NaN}'])
def test_cli_parser_rejects_duplicate_keys_and_nonfinite_values(tmp_path, raw):
    path = tmp_path/'input.json'; path.write_text(raw)
    with pytest.raises(ValueError):
        S._read_json(path)


def test_cli_parser_enforces_input_byte_cap(tmp_path, monkeypatch):
    import factor_inputs
    monkeypatch.setattr(factor_inputs.policy, 'MAX_INPUT_BYTES', 5)
    path = tmp_path/'input.json'; path.write_text('{"candidates":[]}')
    with pytest.raises(ValueError, match='SIZE_LIMIT'):
        S._read_json(path)


def test_explicit_private_account_model_is_loaded_without_implicit_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_MODEL', raising=False)
    (tmp_path/'deepseek_model.txt').write_text('deepseek-flash\n')
    seen = []
    def evaluate(*args, **kwargs):
        seen.append(kwargs['model']); return success(*args, **kwargs)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1), evaluator=evaluate)
    assert result['model'] == 'deepseek-flash' and seen == ['deepseek-flash']
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-reasoner')
    assert S.load_private_model(tmp_path) == 'deepseek-reasoner'


def test_private_model_with_credential_or_invalid_bytes_never_echoes_or_calls_model(tmp_path, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_MODEL', raising=False)
    secret = 'sk-private-credential-in-wrong-file'
    (tmp_path/'deepseek_model.txt').write_text(secret)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(1),
        evaluator=lambda *a, **k: pytest.fail('invalid model cannot call API'))
    assert result['status'] == 'UNAVAILABLE' and result['model'] is None
    assert secret not in json.dumps(result)


@pytest.mark.parametrize(('observed', 'valid'), [
    ('2026-09-10T16:00:00-04:00', True),
    ('2026-09-09T16:00:00-04:00', False),
    ('2026-09-11T08:11:00-04:00', False),
])
def test_public_macro_collector_enforces_same_session_reference_contract(monkeypatch, observed, valid):
    import quotes
    now = NOW.replace(hour=8, minute=10)
    symbols = {'crude': 'CL=F', 'cadusd': 'CADUSD=X', 'tsx': '^GSPTSE', 'vix': '^VIX'}
    raw = {symbol: {'symbol': symbol, 'regularMarketPrice': 10.,
                    'regularMarketTime': dt.datetime.fromisoformat(observed).timestamp()}
           for symbol in symbols.values()}
    monkeypatch.setattr(quotes.YahooMarketData, 'get', lambda self, tickers: raw)
    result = S._macro({'correlated': symbols}, now)
    assert all(value is not None for value in result['values'].values()) is valid
    assert bool(result['gaps']) is not valid
    assert 'Dated macro references' in result['label']
