"""Day-134b: the OpenRouter replay harness is honest before it is run."""
import pytest

import replay_or_models as M

ACTUAL = {t: {d: 100.0 for d in M.PROBE_DATES} | {M.NAIVE_DATE: 80.0} for t in M.PROBE_NAMES}


def test_a_model_that_knows_the_closes_is_contaminated_and_one_that_guesses_is_not():
    knows = {t: {d: 101.0 for d in M.PROBE_DATES} for t in M.PROBE_NAMES}
    assert M.contamination(knows, ACTUAL)['contaminated']
    guesses = {t: {d: 81.0 for d in M.PROBE_DATES} for t in M.PROBE_NAMES}   # its older memory
    assert not M.contamination(guesses, ACTUAL)['contaminated']
    silent = {t: {d: None for d in M.PROBE_DATES} for t in M.PROBE_NAMES}
    out = M.contamination(silent, ACTUAL)
    assert out['answered'] == 0 and not out['contaminated']


def test_the_budget_stops_calls_before_the_cap():
    ledger = M.Ledger(cap=1.0, spent=0.95)
    with pytest.raises(M.BudgetExceeded):
        ledger.check()
    ledger = M.Ledger(cap=1.0)
    ledger.add({'usage': {'cost': 0.25}})
    assert ledger.spent == 0.25 and ledger.calls == 1


def test_json_only_keeps_the_object_from_a_fenced_or_prefaced_reply():
    assert M.json_only('```json\n{"longs": []}\n```') == '{"longs": []}'
    assert M.json_only('Here is my answer: {"a": 1} thanks') == '{"a": 1}'


def test_the_client_drops_deepseeks_thinking_switch_and_keeps_json_mode():
    sent = []

    def post(body):
        sent.append(body)
        return {'model': body['model'], 'usage': {'cost': 0.01},
                'choices': [{'finish_reason': 'stop', 'message': {'content': '{"longs": [], "shorts": []}'}}]}
    client = M.ORClient('deepseek/deepseek-r1-0528', post, M.Ledger())
    r = client.chat.completions.create(model='deepseek-v4-pro', messages=[{'role': 'user', 'content': 'x'}],
                                       response_format={'type': 'json_object'}, max_tokens=32768,
                                       extra_body={'thinking': {'type': 'disabled'}}, timeout=150)
    assert 'thinking' not in sent[0] and 'extra_body' not in sent[0]
    assert sent[0]['model'] == 'deepseek/deepseek-r1-0528' and sent[0]['response_format'] == {'type': 'json_object'}
    assert sent[0]['usage'] == {'include': True}
    assert r.choices[0].finish_reason == 'stop' and r.choices[0].message.content.startswith('{')
