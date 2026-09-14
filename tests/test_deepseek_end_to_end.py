"""Actual preparation, SDK parsing, sealing, loading, Digest and email boundaries.

Only provider I/O is substituted. These fixtures prove software behavior,
never market accuracy. The prepared loader and renderers are not mocked.
"""
import copy
import datetime as dt
import json
from types import SimpleNamespace

import pytest

import brief
import deepseek_factors as factors
import prepare_deepseek as preparation
import prepare_delivery
from adapters.deepseek_adapter import evaluate_batch
from diagnostic_context import create_context
from report_store import encode
from test_prepare_deepseek import pool, NOW, CFG
from test_daily_pipeline import services


def sdk_evaluator(calls, mode='success'):
    def create(**kwargs):
        payload = json.loads(kwargs['messages'][1]['content'])
        tickers = [row['ticker'] for row in payload['candidates']]
        calls.append(tickers)
        if mode == 'timeout':
            raise TimeoutError('synthetic provider timeout')
        rows = [{'ticker': ticker, 'directional_lean': 'BULL', 'sentiment_score': .7,
                 'factor_rationale': 'The supplied fixture update supports an unadopted contextual lean.'}
                for ticker in tickers]
        if mode == 'invalid':
            rows[0]['sentiment_score'] = 10
        return SimpleNamespace(id='fixture-response', model=kwargs['model'],
            choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                content=json.dumps({'assessments': rows}), refusal=None))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return lambda *args, **kwargs: evaluate_batch(*args, **kwargs, client=client)


def no_more_model(*args, **kwargs):
    pytest.fail('A saved-snapshot load or renderer tried another model request')


@pytest.mark.parametrize('mode', ['success', 'timeout', 'invalid'])
def test_preparation_to_real_loader_to_digest_to_email(tmp_path, monkeypatch, mode):
    monkeypatch.delenv('RB_DEEPSEEK_SNAPSHOT_JSON', raising=False)
    p = pool(3)
    p['candidates'] = [copy.deepcopy(row) for row in p['candidates']]
    p['candidates'][2]['technicals']['rsi'] = None
    calls = []
    prepared = preparation.prepare(tmp_path, CFG, now=NOW, inputs=p,
        evaluator=sdk_evaluator(calls, mode))
    assert calls == [['X0', 'X1']]
    assert (prepared['requested'], prepared['eligible'], prepared['submitted']) == (3, 2, 2)
    snapshot = tmp_path/'deepseek_snapshot.json'
    before = snapshot.read_bytes()
    monkeypatch.setattr('adapters.deepseek_adapter.evaluate_batch', no_more_model)
    at_report = NOW.replace(hour=9, minute=46)
    loaded = factors.load_prepared(tmp_path, at_report)
    assert loaded['requested'] == 3 and loaded['eligible'] == 2 and loaded['submitted'] == 2
    d = brief.build(now=at_report, state_dir=tmp_path, services=services())
    assert isinstance(d, brief.Digest)
    frozen = encode(d)
    mail = prepare_delivery.artifacts(d, tmp_path/'dispatch', at_report)
    bodies = [brief.render_text(d), brief.render_html(d), mail['text'], mail['html'],
              mail['attachments'][0]['content']]
    if mode == 'success':
        assert loaded['covered'] == d['intraday']['deepseek']['covered'] == 2
        assert loaded['research_watchlist']['evaluated'] == 2
        assert all('X0' in body and 'X1' in body for body in bodies)
        assert 'X2' in mail['attachments'][0]['content']
    else:
        assert loaded['covered'] == 0 and loaded['status'] == 'UNAVAILABLE'
        assert all('UNAVAILABLE' in body and 'NOT EVALUATED' in body for body in bodies)
        assert not loaded['research_watchlist']['threshold_evaluated']
    assert calls == [['X0', 'X1']] and snapshot.read_bytes() == before and encode(d) == frozen
    assert not (tmp_path/'reports.sqlite3').exists()
    again = preparation.prepare(tmp_path, CFG, now=NOW+dt.timedelta(minutes=5), evaluator=no_more_model)
    assert again == prepared


def test_diagnostic_snapshot_loads_only_in_explicit_unpublished_view(tmp_path, monkeypatch):
    monkeypatch.delenv('RB_DEEPSEEK_SNAPSHOT_JSON', raising=False)
    root = tmp_path/'diagnostic'
    current = NOW.replace(hour=12)
    create_context(root, now=current)
    p = pool(2)
    calls = []
    prepared = preparation.prepare_diagnostic(root, CFG, now=current, inputs=p,
        evaluator=sdk_evaluator(calls))
    assert prepared['prepared_at'] == current.isoformat()
    assert prepared['morning_snapshot'] is False
    assert factors.load_prepared(root, current)['status'] == 'UNAVAILABLE'
    diagnostic = factors.load_diagnostic(root, current, root/'deepseek_snapshot.json')
    assert diagnostic['covered'] == 2
    before = (root/'deepseek_snapshot.json').read_bytes()
    d = brief.build(now=current, no_net=True, state_dir=root, services=services(),
                    factor_diagnostic=root/'deepseek_snapshot.json')
    assert d['report_status'].startswith('CURRENT-TIME DEEPSEEK DIAGNOSTIC')
    assert not d['clock']['eligible'] and d['intraday']['deepseek']['covered'] == 2
    mail = prepare_delivery.artifacts(d, root/'dispatch', current)
    assert 'X0' in mail['text'] and 'CURRENT-TIME' in mail['html']
    assert (root/'deepseek_snapshot.json').read_bytes() == before
    assert not (root/'reports.sqlite3').exists()
    for kwargs in ({'publish': True, 'no_net': True}, {'publish': False, 'no_net': False}):
        with pytest.raises(ValueError, match='offline unpublished'):
            brief.build(now=current, state_dir=root, factor_diagnostic=root/'deepseek_snapshot.json', **kwargs)


def test_diagnostic_tag_is_rejected_even_with_valid_preopen_timestamps(tmp_path):
    root = tmp_path/'diagnostic'
    create_context(root, now=NOW)
    preparation.prepare_diagnostic(root, CFG, now=NOW, inputs=pool(1),
                                   evaluator=sdk_evaluator([]))
    loaded = factors.load_prepared(root, NOW.replace(hour=9, minute=46))
    assert loaded['status'] == 'UNAVAILABLE'
    assert 'diagnostic evidence is not a morning snapshot' in loaded['reason']
    with pytest.raises(ValueError, match='cannot become a production'):
        preparation.prepare(root, CFG, now=NOW, evaluator=no_more_model)
    d = brief.build(now=NOW, no_net=True, state_dir=root, services=services(),
                    factor_diagnostic=root/'deepseek_snapshot.json')
    mail = prepare_delivery.artifacts(d, root/'dispatch', NOW)
    assert 'CURRENT-TIME DEEPSEEK DIAGNOSTIC' in mail['text']


def test_production_finishing_after_preopen_deadline_cannot_report_ready(tmp_path, monkeypatch):
    clock = iter([NOW, NOW.replace(hour=9, minute=30, second=1)])
    class Clock:
        @staticmethod
        def now(tz=None):
            return next(clock)
    monkeypatch.setattr(preparation, 'dt', SimpleNamespace(datetime=Clock,time=dt.time))
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only-private-key')
    calls = []
    monkeypatch.setattr('analyst.analyze_factors', sdk_evaluator(calls))
    monkeypatch.setattr(preparation, 'acquire', lambda jobs: {
        name:{'value':func(),'error':None} for name,(func,_) in jobs.items()})
    result = preparation.prepare(tmp_path, CFG, inputs=pool(1))
    assert result['status'] == 'UNAVAILABLE' and result['covered'] == 1
    assert 'PREOPEN_DEADLINE_REACHED' in ' '.join(result['gaps'])
    loaded = factors.load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert loaded['status'] == 'UNAVAILABLE'


def test_raw_requested_count_survives_rejected_source_row(tmp_path):
    p = pool(2); p['candidates'].append({'ticker':'invalid ticker'})
    result = preparation.prepare(tmp_path, CFG, now=NOW, inputs=p,
                                 evaluator=sdk_evaluator([]))
    assert result['source_requested'] == 3 and result['requested'] == 2
    loaded = factors.load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert loaded['requested'] == 3 and loaded['covered'] == 2
    assert loaded['status'] == 'PARTIAL'
