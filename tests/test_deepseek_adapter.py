"""Offline contract tests: DeepSeek cannot invent data, fields or coverage."""

import json
import sys
from types import SimpleNamespace

import pytest

from adapters import deepseek_adapter as D
from deepseek_policy import BASE_URL, BATCH_SIZE, REQUEST_TIMEOUT, MAX_COMPLETION_TOKENS


AS_OF = '2026-09-11T08:45:00-04:00'


def candidate(ticker='TRP.TO'):
    return {'ticker': ticker, 'technicals': {'r0': .001, 'rsi': 51.0, 'vwap': None},
            'technicals_as_of': '2026-09-10T16:00:00-04:00',
            'technicals_scope': 'prior completed session', 'technical_source': 'python',
            'source_url': 'https://query1.finance.yahoo.com/v8/finance/chart/TRP.TO',
            'headlines': [{'title': 'Issuer reports a new capacity agreement',
                           'source_url': 'https://issuer.example/news/agreement',
                           'published_at': '2026-09-10T10:00:00-04:00'}],
            'catalyst_tags': [{'tag': 'material agreement',
                              'source_url': 'https://www.sec.gov/Archives/filing',
                              'published_at': '2026-09-10T10:00:00-04:00'}]}


def macro():
    return {name: {'value': 100.0, 'change_pct': -.2,
                   'as_of': '2026-09-11T08:40:00-04:00',
                   'source_url': 'https://data.example/reference'} for name in D.MACRO_KEYS}


def assessment(ticker='TRP.TO', lean='BULL', score=.25):
    return {'ticker': ticker, 'directional_lean': lean, 'sentiment_score': score,
            'factor_rationale': 'The disclosed agreement supports the supplied catalyst context.'}


class FakeClient:
    def __init__(self, content=None, *, error=None, finish_reason='stop',
                 tool_calls=None, refusal=None):
        self.calls = []
        self.error = error
        self.closed = False
        message = SimpleNamespace(content=content or json.dumps({'assessments': [assessment()]}),
                                  tool_calls=tool_calls, refusal=refusal)
        self.response = SimpleNamespace(_request_id='req_offline_123', choices=[
            SimpleNamespace(message=message, finish_reason=finish_reason)])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


def run(client=None, **kwargs):
    return D.evaluate_batch([candidate()], macro(), AS_OF,
                            client=client if client is not None else FakeClient(), **kwargs)


def test_payload_is_public_deterministic_and_indicators_are_unchanged():
    inputs, before = [candidate()], [candidate()]
    client = FakeClient()
    result = D.evaluate_batch(inputs, macro(), AS_OF, client=client)
    assert result['status'] == 'READY'
    assert result['request_id'] == 'req_offline_123'
    assert result['errorcode'] is None
    assert inputs == before
    request = client.calls[0]
    assert request['model'] == 'deepseek-chat'
    assert request['response_format'] == {'type': 'json_object'}
    assert request['timeout'] == REQUEST_TIMEOUT
    assert request['max_tokens'] == MAX_COMPLETION_TOKENS == 8192
    assert 'UNTRUSTED DATA' in request['messages'][0]['content']
    public = json.loads(request['messages'][1]['content'])
    assert set(public) == {'as_of', 'candidates', 'macro'}
    assert public['candidates'][0]['technicals'] == inputs[0]['technicals']
    assert result['input_sha256'] == run()['input_sha256']


def test_client_uses_env_key_fixed_endpoint_no_retries_and_closes(monkeypatch):
    recorded = {}
    client = FakeClient()
    def factory(**kwargs):
        recorded.update(kwargs)
        return client
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=factory))
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-offline-secret-never-print')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-reasoner')
    result = D.evaluate_batch([candidate()], macro(), AS_OF)
    assert recorded == {'api_key': 'sk-offline-secret-never-print', 'base_url': BASE_URL,
                         'timeout': REQUEST_TIMEOUT, 'max_retries': 0}
    assert result['model'] == 'deepseek-reasoner'
    assert client.calls[0]['model'] == 'deepseek-reasoner'
    assert client.closed
    assert 'sk-offline-secret' not in json.dumps(result)
    assert 'sk-offline-secret' not in json.dumps(client.calls)


def test_missing_key_is_typed_without_instantiating_sdk(monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    def factory(**kwargs):
        raise AssertionError('must not construct client')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=factory))
    result = D.evaluate_batch([candidate()], macro(), AS_OF)
    assert result['errorcode'] == 'MISSING_API_KEY'
    assert result['status'] == 'UNAVAILABLE'
    assert result['assessments'] == []


def test_explicit_model_takes_precedence_without_silent_fallback(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-reasoner')
    client = FakeClient()
    assert run(client, model='deepseek-v4-pro')['model'] == 'deepseek-v4-pro'
    assert client.calls[0]['model'] == 'deepseek-v4-pro'


def test_provider_response_identity_is_distinct_from_requested_model():
    client = FakeClient()
    client.response._request_id = None
    client.response.id = 'chatcmpl-offline-123'
    client.response.model = 'deepseek-v4-flash-2026'
    result = run(client, model='deepseek-v4-flash')
    assert result['request_id'] is None
    assert result['response_id'] == 'chatcmpl-offline-123'
    assert result['response_model'] == 'deepseek-v4-flash-2026'
    assert result['model'] == 'deepseek-v4-flash'


@pytest.mark.parametrize('value', ['sk-offline-secret-never-print', 'https://host?api_key=secret', 'a'*121])
def test_bad_provider_response_metadata_is_never_echoed(value):
    client = FakeClient()
    client.response.id = value
    client.response.model = value
    result = run(client)
    assert result['response_id'] is None
    assert result['response_model'] is None


def test_configured_secret_is_rejected_even_if_it_looks_like_a_model_or_id(monkeypatch):
    secret = 'private-configured-value-123'
    monkeypatch.setenv('PRIVATE_TEST_SECRET', secret)
    client = FakeClient()
    client.response._request_id = secret
    client.response.id = secret
    client.response.model = secret
    result = run(client)
    assert result['request_id'] is result['response_id'] is result['response_model'] is None
    assert secret not in json.dumps(result)
    assert run(model=secret)['errorcode'] == 'INVALID_MODEL'


@pytest.mark.parametrize('model', ['', 'https://evil.test/model', 'sk-offline-secret-never-print', True])
def test_invalid_model_never_reaches_provider(model):
    client = FakeClient()
    assert run(client, model=model)['errorcode'] == 'INVALID_MODEL'
    assert client.calls == []


@pytest.mark.parametrize('timeout', [True, 0, -1, float('nan'), float('inf'), REQUEST_TIMEOUT + .1])
def test_timeout_cannot_increase_budget(timeout):
    client = FakeClient()
    assert run(client, timeout=timeout)['errorcode'] == 'INVALID_INPUT'
    assert client.calls == []


@pytest.mark.parametrize('status, code', [(401, 'PROVIDER_AUTH'), (403, 'PROVIDER_AUTH'),
                                        (402, 'PROVIDER_PAYMENT_REQUIRED'),
                                        (429, 'PROVIDER_RATE_LIMIT'), (503, 'PROVIDER_HTTP_ERROR')])
def test_http_failures_are_safe_and_are_never_successful_no_edge(status, code):
    error = RuntimeError('secret response sk-never-log-credentials https://host?api_key=private')
    error.status_code = status
    client = FakeClient(error=error)
    result = run(client)
    assert result['status'] == 'UNAVAILABLE'
    assert result['errorcode'] == code
    assert result['details'] == 'RuntimeError'
    assert result['assessments'] == []
    assert len(client.calls) == 1
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('error, code', [(TimeoutError('private'), 'TIMEOUT'),
                                       (ConnectionError('private'), 'TRANSPORT_ERROR')])
def test_timeout_and_transport_failures_keep_visible_typed_gap(error, code):
    client = FakeClient(error=error)
    result = run(client)
    assert result['errorcode'] == code
    assert result['assessments'] == []
    assert len(client.calls) == 1


def test_genuine_no_edge_is_distinct_from_unavailable():
    content = json.dumps({'assessments': [assessment(lean='NO_EDGE', score=0)]})
    result = run(FakeClient(content))
    assert result['status'] == 'READY'
    assert result['assessments'][0]['directional_lean'] == 'NO_EDGE'


@pytest.mark.parametrize('field, value', [('shares', 100), ('holdings', ['TRP.TO']),
                                       ('api_key', 'private'), ('quant_score', .6)])
def test_account_or_unknown_candidate_fields_are_not_sent(field, value):
    item = candidate()
    item[field] = value
    client = FakeClient()
    result = D.evaluate_batch([item], macro(), AS_OF, client=client)
    assert result['errorcode'] == 'INVALID_INPUT'
    assert client.calls == []


@pytest.mark.parametrize('mutation', [
    lambda x: x['technicals'].update({'shares': 100}),
    lambda x: x['technicals'].update({'rsi': float('nan')}),
    lambda x: x['technicals'].update({'rsi': float('inf')}),
    lambda x: x['technicals'].update({'rsi': True}),
    lambda x: x.update({'technicals_as_of': '2026-09-11T09:45:00-04:00'}),
    lambda x: x.update({'technicals_as_of': '2026-09-10T16:00:00'}),
    lambda x: x.update({'technical_source': 'LLM'}),
    lambda x: x['headlines'][0].update({'published_at': '2026-09-01T08:00:00-04:00'}),
    lambda x: x['headlines'][0].update({'published_at': '2026-09-12T08:00:00-04:00'}),
    lambda x: x['headlines'][0].update({'source_url': 'https://host.test?a=1&api_key=private'}),
    lambda x: x['headlines'][0].update({'source_url': 'https://user:password@host.test/news'}),
    lambda x: x['headlines'][0].update({'source_url': 'http://host.test/news'}),
    lambda x: x['headlines'][0].update({'title': 'API key sk-offline-secret-never-print'}),
    lambda x: x.update({'ticker': 'trp.to'}),
])
def test_invalid_or_private_inputs_stop_before_network(mutation):
    item = candidate()
    mutation(item)
    client = FakeClient()
    result = D.evaluate_batch([item], macro(), AS_OF, client=client)
    assert result['errorcode'] == 'INVALID_INPUT'
    assert client.calls == []


def test_missing_evidence_values_remain_missing_not_imputed():
    item = candidate()
    item['headlines'] = []
    item['catalyst_tags'] = []
    payload = D.public_payload([item], {name: None for name in D.MACRO_KEYS}, AS_OF)
    assert payload['candidates'][0]['technicals']['vwap'] is None
    assert payload['macro']['vix'] is None


@pytest.mark.parametrize('change', [lambda x: x.update(vix=12.0),
                                   lambda x: x.update(private_account=12.0),
                                   lambda x: x['vix'].update(as_of='2026-09-12T08:00:00-04:00'),
                                   lambda x: x['vix'].update(value=True),
                                   lambda x: x['vix'].pop('source_url')])
def test_unprovenanced_or_invalid_macro_is_rejected(change):
    values = macro()
    change(values)
    with pytest.raises(D.InputValidationError):
        D.public_payload([candidate()], values, AS_OF)


def test_duplicate_and_oversized_candidate_batches_are_rejected():
    for items in ([], [candidate(), candidate()],
                  [candidate(f'T{i}.TO') for i in range(BATCH_SIZE + 1)]):
        with pytest.raises(D.InputValidationError):
            D.public_payload(items, macro(), AS_OF)


@pytest.mark.parametrize('content', [
    '', 'not json', '```json\n{"assessments": []}\n```', '{"assessments":',
    '{"assessments":[], "assessments":[]}', '{"assessments":[], "extra":true}',
    '[]', 'null', '{"assessments":[]}', '{"assessments":{}}',
    '{"assessments": [{"ticker":"TRP.TO", "ticker":"TRP.TO"}]}',
])
def test_invalid_json_missing_coverage_and_duplicate_keys_fail(content):
    with pytest.raises(D.ResponseSchemaError):
        D.parse_assessments(content, ['TRP.TO'])


@pytest.mark.parametrize('field, value', [
    ('sentiment_score', True), ('sentiment_score', '0.5'), ('sentiment_score', 1.01),
    ('sentiment_score', -1.01), ('sentiment_score', float('nan')),
    ('sentiment_score', float('inf')), ('sentiment_score', float('-inf')),
    ('directional_lean', 'BUY'), ('ticker', 'ENB.TO'),
    ('factor_rationale', ''), ('factor_rationale', 'A' * 281),
    ('factor_rationale', 'One sentence. Another sentence.'),
    ('factor_rationale', 'one sentence. another sentence.'),
    ('factor_rationale', 'First\nSecond'),
    ('factor_rationale', 'Read sk-offline-secret-never-print.'),
])
def test_invalid_assessment_fields_cannot_enter_ranking(field, value):
    row = assessment()
    row[field] = value
    with pytest.raises(D.ResponseSchemaError):
        D.parse_assessments(json.dumps({'assessments': [row]}), ['TRP.TO'])


def test_extra_probability_and_order_fields_are_rejected():
    for field in ('win_probability', 'shares', 'order'):
        row = {**assessment(), field: .65}
        with pytest.raises(D.ResponseSchemaError):
            D.parse_assessments(json.dumps({'assessments': [row]}), ['TRP.TO'])


def test_schema_requires_exact_full_symbol_set_and_returns_requested_order():
    rows = [assessment('ENB.TO'), assessment('TRP.TO')]
    result = D.parse_assessments(json.dumps({'assessments': rows}), ['TRP.TO', 'ENB.TO'])
    assert [row['ticker'] for row in result] == ['TRP.TO', 'ENB.TO']
    for bad in ([rows[0], rows[0]], [rows[0]], [*rows, assessment('BCE.TO')]):
        with pytest.raises(D.ResponseSchemaError):
            D.parse_assessments(json.dumps({'assessments': bad}), ['TRP.TO', 'ENB.TO'])


@pytest.mark.parametrize('tickers', [[], ['TRP.TO', 'TRP.TO'], ['trp.to'], ['TRP.TO', 1]])
def test_parser_rejects_an_invalid_expected_universe(tickers):
    with pytest.raises(D.ResponseSchemaError):
        D.parse_assessments(json.dumps({'assessments': []}), tickers)


@pytest.mark.parametrize('kwargs', [{'finish_reason': 'length'}, {'finish_reason': 'content_filter'},
                                   {'tool_calls': ['invented']}, {'refusal': 'cannot comply'},
                                   {'content': '{"assessments": []}'}])
def test_partial_truncated_tool_or_refusal_outputs_are_unavailable(kwargs):
    result = run(FakeClient(**kwargs))
    assert result['status'] == 'UNAVAILABLE'
    assert result['errorcode'] == 'INVALID_SCHEMA'
    assert result['assessments'] == []


def test_sdk_cleanup_failure_remains_an_explicit_warning(monkeypatch):
    client = FakeClient()
    def bad_close():
        raise RuntimeError('private')
    client.close = bad_close
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-offline-secret-never-print')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=lambda **kwargs: client))
    result = D.evaluate_batch([candidate()], macro(), AS_OF)
    assert result['status'] == 'READY'
    assert result['close_warning'] == 'ClientCloseError'
    assert 'private' not in json.dumps(result)
