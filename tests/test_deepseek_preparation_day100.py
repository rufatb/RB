"""Bounded preparation recovery, with fake providers only."""
import json
import datetime as dt
from types import SimpleNamespace

import pytest

import prepare_deepseek as S
import factor_inputs as F
from test_factor_inputs import payload, NOW, CFG
from test_prepare_deepseek import pool, success


def test_public_refresh_uses_expanded_staged_roster_and_keeps_partial_success(tmp_path, monkeypatch):
    p = pool(17)
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(p))
    queried = []
    def acquire(jobs):
        if 'macro' in jobs:
            return {'macro': {'value': {'values': p['macro'], 'gaps': []}}}
        queried.extend(jobs)
        return {ticker: {'value': None, 'error': 'TimeoutExpired'} if ticker == 'X0' else
            {'value': {'headlines': p['candidates'][0]['headlines'], 'catalyst_tags': []}}
            for ticker in jobs}
    monkeypatch.setattr(S, 'acquire', acquire)
    gaps = S.refresh_public_inputs(tmp_path, CFG, NOW)
    assert queried == ['X'+str(i) for i in range(17)]
    assert CFG['scan']['universe'] == ['ABC.TO']
    saved = json.loads((tmp_path/'deepseek_news.json').read_text())
    assert len(saved) == 17 and 'X16' in saved
    assert saved['X0']['status'] == 'UNAVAILABLE' and saved['X0']['errorcode'] == 'TimeoutExpired'
    assert not saved['X0'].get('headlines')
    status = json.loads((tmp_path/'deepseek_public_status.json').read_text())
    assert status['queried'] == status['requested'] == 17
    assert status['unqueried_tickers'] == []
    assert any('X0' in gap for gap in gaps)


def test_public_refusal_stops_new_batches_without_erasing_current_success(tmp_path, monkeypatch):
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(pool(17)))
    queried = []
    def acquire(jobs):
        if 'macro' in jobs:
            return {'macro': {'value': {'values': payload()['macro'], 'gaps': []}}}
        queried.extend(jobs)
        return {ticker: {'value': {'status': 'UNAVAILABLE', 'errorcode': 'PROVIDER_RATE_LIMIT'}}
                if ticker == 'X0' else {'value': {'headlines': [], 'catalyst_tags': []}}
                for ticker in jobs}
    monkeypatch.setattr(S, 'acquire', acquire)
    S.refresh_public_inputs(tmp_path, CFG, NOW)
    assert len(queried) == S.P.PUBLIC_BATCH_SIZE
    saved = json.loads((tmp_path/'deepseek_news.json').read_text())
    assert len(saved) == S.P.PUBLIC_BATCH_SIZE
    assert saved['X0']['status'] == 'UNAVAILABLE'
    assert saved['X0']['errorcode'] == 'PROVIDER_RATE_LIMIT'
    assert not saved['X0'].get('headlines')
    status = json.loads((tmp_path/'deepseek_public_status.json').read_text())
    assert status['stop_reason'] == 'provider refusal'
    assert len(status['unqueried_tickers']) == 17-S.P.PUBLIC_BATCH_SIZE


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(as_of='2026-09-10T08:30:00-04:00'),
    lambda p: p['candidates'].append(p['candidates'][0]),
    lambda p: p['candidates'][0].update(ticker='private/value'),
])
def test_bad_staged_roster_never_falls_back_to_production_names(tmp_path, mutate):
    p = pool(2); mutate(p)
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(p))
    with pytest.raises((ValueError, KeyError, TypeError)):
        S.candidate_roster(tmp_path, CFG, NOW)


def test_parallel_model_receipts_are_matched_by_job_identity_and_preserve_success(tmp_path, monkeypatch):
    import analyst
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'offline-test-only')
    calls = []
    def evaluate(candidates, macro, as_of, **kwargs):
        calls.append(candidates[0]['ticker'])
        if candidates[0]['ticker'] == 'X0':
            return {'status': 'UNAVAILABLE', 'assessments': [], 'errorcode': 'TIMEOUT'}
        return success(candidates, macro, as_of, **kwargs)
    monkeypatch.setattr(analyst, 'analyze_factors', evaluate)
    waves = []
    def acquire(jobs):
        waves.append(len(jobs))
        assert len(jobs) <= S.P.MODEL_BATCH_CONCURRENCY
        # Completion order differs from input order, as real worker results do.
        return {key: {'value': jobs[key][0]()} for key in reversed(jobs)}
    monkeypatch.setattr(S, 'acquire', acquire)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(125))
    assert waves == [4, 1]
    assert result['covered'] == 100 and result['status'] == 'PARTIAL'
    assert [r['ticker'] for r in result['assessments']] == ['X'+str(i) for i in range(25, 125)]
    assert len(calls) == 5 and len(result['batches']) == 5
    before = list(calls)
    assert S.prepare(tmp_path, CFG, now=NOW, inputs=pool(125)) == result
    assert calls == before


def test_model_auth_failure_retains_already_started_success_and_stops_future_wave(tmp_path):
    calls = []
    def evaluator(candidates, macro, as_of, **kwargs):
        calls.append(candidates[0]['ticker'])
        if candidates[0]['ticker'] == 'X0':
            return {'status': 'UNAVAILABLE', 'assessments': [], 'errorcode': 'PROVIDER_AUTH'}
        return success(candidates, macro, as_of, **kwargs)
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=pool(125), evaluator=evaluator)
    assert calls == ['X0', 'X25', 'X50', 'X75']
    assert result['covered'] == 75 and result['requested'] == 125
    assert result['candidate_gaps']['X100']


def test_historical_exclusion_is_visible_without_invalidating_complete_current_inputs():
    p = payload()
    p['candidate_diagnostics'] = {'ABC.TO': ['HISTORICAL_SESSIONS_EXCLUDED:2']}
    result = F.validate_payload(p, NOW)
    assert result['coverage']['complete'] == 1
    assert result['candidate_gaps']['ABC.TO'] == []
    assert result['candidate_diagnostics']['ABC.TO'] == ['HISTORICAL_SESSIONS_EXCLUDED:2']
    p['candidates'][0]['technicals']['macd'] = None
    result = F.validate_payload(p, NOW)
    assert result['coverage']['complete'] == 0
    assert 'TECHNICAL_UNAVAILABLE:macd' in result['candidate_gaps']['ABC.TO']


def test_news_failure_records_http_class_without_body_or_key(monkeypatch):
    import requests
    error = requests.HTTPError('private provider response token=secret')
    error.response = SimpleNamespace(status_code=429)
    def get(*args, **kwargs):
        raise error
    monkeypatch.setattr(requests, 'get', get)
    result = S._news('ABC.TO', NOW)
    assert result['errorcode'] == 'PROVIDER_RATE_LIMIT'
    assert 'secret' not in json.dumps(result) and 'private' not in json.dumps(result)


def test_ticker_news_query_keeps_exact_symbol_linkage(monkeypatch):
    import requests
    observed = NOW+dt.timedelta(seconds=1)
    def get(url, **kwargs):
        params = kwargs['params']
        assert params['newsQueryId'] == 'news_cie_vespa'
        assert params['quotesQueryId'] == 'tss_match_phrase_query'
        assert params['enableFuzzyQuery'] is False
        story = {'providerPublishTime': observed.timestamp(), 'link': 'https://issuer.example/news',
                 'title': 'An issuer update', 'relatedTickers': ['ABC.TO']}
        return SimpleNamespace(raise_for_status=lambda: None,
            json=lambda: {'news': [story, {**story, 'relatedTickers': ['ABC']}, None,
                                   {**story, 'relatedTickers': None},
                                   {**story, 'relatedTickers': 'ABC.TO'}]})
    monkeypatch.setattr(requests, 'get', get)
    result = S._search_news('ABC.TO', NOW, clock=lambda: NOW+dt.timedelta(seconds=5))
    assert len(result['headlines']) == 1 and result['unusable_rows'] == 4
    assert S.stamp(result['retrieved_at']) == NOW+dt.timedelta(seconds=5)


def test_macro_keeps_actual_provider_timestamp_and_never_authenticates(monkeypatch):
    import requests
    from urllib.parse import unquote
    from quotes import YahooMarketData
    monkeypatch.setattr(YahooMarketData, 'get', lambda *a: pytest.fail('quote auth not allowed'))
    def get(url, **kwargs):
        ticker = unquote(url.rsplit('/', 1)[-1])
        timestamp = '2026-09-10T16:00:01-04:00'
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'chart': {'result': [
            {'meta': {'symbol': ticker, 'regularMarketPrice': 12.5,
                      'regularMarketTime': S.stamp(timestamp).timestamp()}}]}})
    monkeypatch.setattr(requests, 'get', get)
    result = S._macro({'correlated': {'crude': 'CL=F', 'cadusd': 'CADUSD=X',
                                    'tsx': '^GSPTSE', 'vix': '^VIX'}}, NOW)
    assert not result['gaps']
    for value in result['values'].values():
        assert S.stamp(value['as_of']) == S.stamp('2026-09-10T16:00:01-04:00')
        assert '/v8/finance/chart/' in value['source_url']


def test_later_public_overlay_has_a_real_assembly_clock_not_old_pool_clock(tmp_path):
    p = payload()
    (tmp_path/'deepseek_candidates.json').write_text(json.dumps(p))
    later = NOW+dt.timedelta(minutes=5)
    fresh = {name: {**item, 'as_of': later.isoformat()} for name, item in p['macro'].items()}
    (tmp_path/'deepseek_macro.json').write_text(json.dumps(fresh))
    result = F.build_from_state(tmp_path, CFG, later)
    assert result['coverage']['complete'] == 1
    assert result['as_of'] == later.isoformat()
    assert result['coverage']['pool_prepared_at'] == NOW.isoformat()
    assert result['candidates'][0]['technical_provenance']['computed_at'] == NOW.isoformat()
    assert p['as_of'] == NOW.isoformat()
    assert json.loads((tmp_path/'deepseek_candidates.json').read_text()) == p


def test_macro_observation_after_request_start_uses_actual_retrieval_clock(monkeypatch):
    import requests
    from urllib.parse import unquote
    later = NOW+dt.timedelta(seconds=5)
    def get(url, **kwargs):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'chart': {'result': [
            {'meta': {'symbol': unquote(url.rsplit('/', 1)[-1]), 'regularMarketPrice': 12.5,
                      'regularMarketTime': later.timestamp()}}]}})
    monkeypatch.setattr(requests, 'get', get)
    cfg = {'correlated': {'crude': 'CL=F', 'cadusd': 'CADUSD=X', 'tsx': '^GSPTSE', 'vix': '^VIX'}}
    result = S._macro(cfg, NOW, clock=lambda: later)
    assert not result['gaps']
    assert all(S.stamp(v['as_of']) == later for v in result['values'].values())
    rejected = S._macro(cfg, NOW, clock=lambda: NOW)
    assert all(v is None for v in rejected['values'].values())
