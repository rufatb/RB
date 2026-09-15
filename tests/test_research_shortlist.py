"""Fixed pre-news shortlist coverage and real saved-response boundaries."""
import copy
import datetime as dt
import json

import pytest

import factor_inputs as F
import prepare_deepseek as S
from deepseek_factors import load_prepared
from report_store import encode
from research_shortlist import MODE, select, validate_saved
from test_factor_inputs import payload, NOW, CFG
from test_prepare_deepseek import success
from test_factor_pool_day101 import history


def expanded_pool(count=60):
    out = payload()
    original = out['candidates'][0]
    out['candidates'] = []
    metadata = []
    for i in range(count):
        ticker = f'X{i:03}.TO'
        out['candidates'].append(dict(copy.deepcopy(original), ticker=ticker))
        metadata.append({'ticker': ticker, 'issuer_id': 'issuer-'+str(i),
            'sector': ['Energy', 'Financials', 'Industrials'][i % 3],
            'industry': 'Verified fixture industry', 'security_type': 'COMMON_STOCK',
            'median_dollar_volume_20': 20_000_000+i*1000})
    out['research_universe'] = {'mode': MODE, 'session': NOW.date().isoformat(),
        'target': 150, 'status': 'PARTIAL', 'candidates': metadata}
    return out


def test_fixed_sector_rounds_liquidity_order_and_fifty_cap_are_pure():
    p = expanded_pool(150)
    before = encode(p)
    clean = F.validate_payload(p, NOW)
    receipt = clean['research_shortlist']
    assert receipt['selected_count'] == 50
    assert receipt['source_requested'] == receipt['technical_complete'] == 150
    assert receipt['tickers'][:6] == ['X147.TO', 'X148.TO', 'X149.TO', 'X144.TO', 'X145.TO', 'X146.TO']
    assert len(receipt['exclusions']) == 100 and not receipt['gaps']
    assert encode(p) == before
    assert validate_saved(receipt, clean, p['research_universe'], str(NOW.date())) == receipt


def test_ties_use_ticker_and_news_never_changes_pre_news_selection():
    p = expanded_pool()
    for row in p['research_universe']['candidates']:
        row['median_dollar_volume_20'] = 20_000_000
    receipt = F.validate_payload(p, NOW)['research_shortlist']
    assert receipt['tickers'][:3] == ['X000.TO', 'X001.TO', 'X002.TO']
    p['macro'] = {}
    for row in p['candidates']:
        row['headlines'] = []
    assert F.validate_payload(p, NOW)['research_shortlist'] == receipt


@pytest.mark.parametrize('defect', ['technicals', 'liquidity', 'industry', 'security_type', 'duplicate_issuer'])
def test_invalid_candidate_exclusion_is_explicit_and_never_padded(defect):
    p = expanded_pool(3)
    if defect == 'technicals':
        p['candidates'][0]['technicals']['rsi'] = None
    elif defect == 'duplicate_issuer':
        p['research_universe']['candidates'][0]['issuer_id'] = 'issuer-1'
    else:
        field, value = {'liquidity': ('median_dollar_volume_20', 9_999_999),
                        'industry': ('industry', None), 'security_type': ('security_type', 'ETF')}[defect]
        p['research_universe']['candidates'][0][field] = value
    clean = F.validate_payload(p, NOW)
    receipt = clean['research_shortlist']
    assert receipt['selected_count'] < 3
    assert 'X000.TO' not in receipt['tickers']
    assert 'SHORTLIST_BELOW_30_COMPLETE_NAMES' in receipt['gaps']
    assert any(row['ticker'] == 'X000.TO' and row['reasons'] for row in receipt['exclusions'])


def test_changed_metadata_or_shortlist_cannot_be_accepted_after_receipt():
    p = expanded_pool()
    p['research_shortlist'] = F.validate_payload(p, NOW)['research_shortlist']
    p['research_universe']['candidates'][0]['median_dollar_volume_20'] += 1
    clean = F.validate_payload(p, NOW)
    assert clean['research_shortlist'] is None
    assert not F.eligible_public_candidates(clean)[0]
    assert 'RESEARCH_SHORTLIST_INVALID_OR_CHANGED' in clean['gaps']


def test_legacy_pool_is_not_silently_subject_to_research_shortlist():
    p = expanded_pool()
    p['research_universe']['mode'] = 'LEGACY_RESEARCH_FALLBACK'
    clean = F.validate_payload(p, NOW)
    assert 'research_shortlist' not in clean
    assert len(F.eligible_public_candidates(clean)[0]) == 60


def test_target_capacity_cannot_inflate_observed_source_coverage():
    p = expanded_pool(3)
    p['coverage'] = {'requested': 150}
    clean = F.validate_payload(p, NOW)
    assert clean['coverage']['requested'] == clean['research_shortlist']['source_requested'] == 3


def test_rejected_source_identity_preserves_original_count_after_sealed_load(tmp_path):
    p = expanded_pool(3)
    p['candidates'].append({'ticker': 'invalid ticker'})
    prepared = S.prepare(tmp_path, CFG, now=NOW, inputs=p, evaluator=success)
    loaded = load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert prepared['source_requested'] == loaded['requested'] == 4
    assert loaded['source_accepted'] == loaded['shortlist_count'] == loaded['covered'] == 3
    assert loaded['research_shortlist']['source_requested'] == 4


def test_news_requests_use_frozen_shortlist_and_never_backfill_failures(tmp_path, monkeypatch):
    p = expanded_pool()
    headlines = copy.deepcopy(p['candidates'][0]['headlines'])
    for row in p['candidates']:
        row['headlines'] = []
    (tmp_path/'deepseek_candidates.json').write_text(encode(p))
    expected = F.validate_payload(p, NOW)['research_shortlist']
    first = expected['tickers'][0]
    queried, submitted = [], []
    monkeypatch.setattr(S, 'acquire', lambda jobs: {
        key: {'value': fn(), 'error': None} for key, (fn, _) in jobs.items()})
    monkeypatch.setattr(S, '_macro', lambda *a, **k: {'values': p['macro'], 'gaps': []})
    def news(ticker, *args, **kwargs):
        queried.append(ticker)
        return ({'status': 'READY', 'headlines': headlines, 'catalyst_tags': []} if ticker == first else
                {'status': 'UNAVAILABLE', 'errorcode': 'TRANSPORT_TIMEOUT'})
    monkeypatch.setattr(S, '_news', news)
    def evaluate(candidates, macro, as_of, **kwargs):
        submitted.extend(row['ticker'] for row in candidates)
        assert all('research_universe' not in row and 'sector' not in row for row in candidates)
        return success(candidates, macro, as_of, **kwargs)
    result = S.prepare(tmp_path, CFG, now=NOW, refresh=True, evaluator=evaluate)
    assert queried and set(queried) <= set(expected['tickers'])
    assert submitted == [first]
    assert result['shortlist_count'] == 50 and result['source_requested'] == 60
    assert result['submitted'] == result['covered'] == 1
    assert json.loads((tmp_path/'deepseek_shortlist.json').read_text()) == expected
    loaded = load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert loaded['covered'] == 1 and loaded['research_shortlist'] == expected
    assert loaded['news_status'][expected['tickers'][1]] == 'UNAVAILABLE'
    again = S.prepare(tmp_path, CFG, now=NOW+dt.timedelta(minutes=5), evaluator=lambda *a, **k: pytest.fail('retry'))
    assert again == result and submitted == [first]


def test_partial_model_batch_retains_all_denominators_and_saved_selection(tmp_path):
    p = expanded_pool(150)
    called = []
    def evaluate(candidates, macro, as_of, **kwargs):
        called.append([c['ticker'] for c in candidates])
        return (success(candidates, macro, as_of, **kwargs) if len(called) == 1 else
                {'status': 'UNAVAILABLE', 'assessments': [], 'errorcode': 'TRANSPORT_TIMEOUT'})
    result = S.prepare(tmp_path, CFG, now=NOW, inputs=p, evaluator=evaluate)
    assert [len(rows) for rows in called] == [25, 25]
    assert (result['source_requested'], result['source_accepted'], result['shortlist_count'],
            result['eligible'], result['submitted'], result['covered']) == (150, 150, 50, 50, 50, 25)
    loaded = load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert loaded['requested'] == 150 and loaded['covered'] == 25
    assert loaded['research_watchlist']['evaluated'] == 25
    assert loaded['shortlist_count'] == 50
    assert len(loaded['research_shortlist']['rows']) == 50
    assert not loaded['research_watchlist']['eligible']


def test_successful_no_current_news_is_distinct_from_request_failure(tmp_path, monkeypatch):
    p = expanded_pool(2)
    for row in p['candidates']:
        row['headlines'] = []
    (tmp_path/'deepseek_candidates.json').write_text(encode(p))
    monkeypatch.setattr(S, 'acquire', lambda jobs: {k: {'value': f(), 'error': None} for k, (f, _) in jobs.items()})
    monkeypatch.setattr(S, '_macro', lambda *a, **k: {'values': p['macro'], 'gaps': []})
    monkeypatch.setattr(S, '_news', lambda ticker, *a, **k: (
        {'status': 'NO_CURRENT_NEWS', 'headlines': [], 'catalyst_tags': []} if ticker == 'X000.TO' else
        {'status': 'UNAVAILABLE', 'errorcode': 'PROVIDER_AUTH'}))
    result = S.prepare(tmp_path, CFG, now=NOW, refresh=True,
        evaluator=lambda *a, **k: pytest.fail('Empty evidence is not a neutral model assessment'))
    loaded = load_prepared(tmp_path, NOW.replace(hour=9, minute=46))
    assert loaded['news_status'] == {'X000.TO': 'NO_CURRENT_NEWS', 'X001.TO': 'UNAVAILABLE'}
    assert not result['assessments'] and result['submitted'] == 0


def test_changed_same_session_pool_cannot_reselect_news_roster(tmp_path):
    p = expanded_pool()
    path = tmp_path/'deepseek_candidates.json'
    path.write_text(encode(p))
    original = S.candidate_roster(tmp_path, CFG, NOW)
    p['research_universe']['candidates'][0]['median_dollar_volume_20'] *= 20
    path.write_text(encode(p))
    with pytest.raises(ValueError, match='FROZEN'):
        S.candidate_roster(tmp_path, CFG, NOW)
    assert json.loads((tmp_path/'deepseek_shortlist.json').read_text())['tickers'] == original


def test_actual_history_pool_to_shortlist_to_model_loader_and_digest(tmp_path, monkeypatch, history):
    """Real stage functions/technicals/receipt parsers; substitute provider I/O only."""
    import brief
    import prepare_delivery
    import prepare_factor_pool
    import test_factor_pool_day101 as pool_fixture
    from test_daily_pipeline import services
    now = pool_fixture.NOW
    meta = [pool_fixture.metadata('AC.TO'), pool_fixture.metadata('NA.TO', 'Financials'),
            pool_fixture.metadata('GWO.TO', 'Financials')]
    for row in meta:
        row['security_type'] = 'COMMON_STOCK'
    pool_fixture.source(monkeypatch, meta)
    pool_fixture.cache(tmp_path, ['AC.TO'], history)
    staged = prepare_factor_pool.prepare(tmp_path, pool_fixture.CFG, now=now,
        fetcher=pool_fixture.fetch(history), acquire_fn=pool_fixture.acquire)
    assert staged['complete_technicals'] == 3
    monkeypatch.setattr(S, 'acquire', lambda jobs: {k: {'value': f(), 'error': None} for k, (f, _) in jobs.items()})
    macro = {name: {'value': 10, 'as_of': now.isoformat(),
        'source_url': 'https://provider.example/data/'+name} for name in F.policy.MACRO_KEYS}
    monkeypatch.setattr(S, '_macro', lambda *a, **k: {'values': macro, 'gaps': []})
    monkeypatch.setattr(S, '_news', lambda *a, **k: {'status': 'READY', 'catalyst_tags': [],
        'headlines': [{'title': 'Dated issuer fixture update', 'published_at': now.isoformat(),
                      'source_url': 'https://issuer.example/news'}]})
    calls = []
    def evaluator(rows, macro, as_of, **kwargs):
        calls.extend(row['ticker'] for row in rows)
        return success(rows, macro, as_of, **kwargs)
    prepared = S.prepare(tmp_path, pool_fixture.CFG, now=now, refresh=True, evaluator=evaluator)
    assert prepared['covered'] == prepared['shortlist_count'] == 3
    assert calls == ['GWO.TO', 'AC.TO', 'NA.TO']
    clock = now.replace(hour=9, minute=46)
    d = brief.build(now=clock, state_dir=tmp_path, services=services())
    loaded = d['intraday']['deepseek']
    assert loaded['covered'] == loaded['shortlist_count'] == 3
    assert d['intraday']['research_coverage']['technical_complete'] == 3
    assert loaded['research_shortlist']['rows'][0]['sector'] == 'Financials'
    mail = prepare_delivery.artifacts(d, tmp_path/'dispatch', clock)
    assert 'GWO.TO' in mail['attachments'][0]['content']
    assert all('3/3 assessed' in body for body in (mail['text'], mail['html']))
    assert 'prepared technicals 3' in mail['text']
    assert not (tmp_path/'reports.sqlite3').exists()


def test_expanded_diagnostic_unavailable_never_falls_back_or_calls_model(tmp_path, monkeypatch):
    import diagnose_deepseek_pipeline as diagnostic
    import prepare_tsx_universe
    import prepare_factor_pool
    from report_store import Store
    from adapters import deepseek_adapter
    source = tmp_path/'canonical'
    store = Store(source)
    store.publish('2026-09-11', {'session': '2026-09-11', 'immutable': 'original report'})
    store.claim_delivery('2026-09-11', 'actual-fixture-gmail-id')
    store.finish_delivery('2026-09-11', 'unknown', 'Retain pending Sent reconciliation')
    (source/'operations.json').write_text('{"preserve":"delivery claims"}')
    before = diagnostic.fingerprints(source)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'fixture-only-private-key')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    seen = []
    def unavailable(state, **kwargs):
        seen.append(kwargs)
        assert (state/'diagnostic_context.json').exists()
        assert not (state/'reports.sqlite3').exists()
        return {'status': 'UNAVAILABLE', 'session': '2026-09-14', 'target': 150,
                'candidates': [], 'reason': 'Directory provider unavailable'}
    def forbidden(*args, **kwargs):
        pytest.fail('Unavailable expanded directory must not call the legacy pool or an LLM')
    monkeypatch.setattr(prepare_tsx_universe, 'prepare', unavailable)
    monkeypatch.setattr(prepare_factor_pool, 'prepare_diagnostic', forbidden)
    monkeypatch.setattr(S, 'prepare_diagnostic', forbidden)
    monkeypatch.setattr(deepseek_adapter, 'evaluate_batch', forbidden)
    result = diagnostic.run(source, tmp_path/'diagnostic', expanded=True)
    assert len(seen) == 1 and seen[0]['diagnostic'] is True
    assert result['status'] == 'UNAVAILABLE'
    assert result['failure_reason'] == 'EXPANDED_UNIVERSE_UNAVAILABLE_NO_MODEL_REQUEST'
    assert result['stages']['universe']['eligible'] == 0
    assert 'pool' not in result['stages'] and 'preparation' not in result['stages']
    assert result['model'] == 'deepseek-flash'
    assert result['canonical_state_unchanged'] and diagnostic.fingerprints(source) == before
    assert result['sent_email'] is result['published_report'] is False
    assert store.delivery('2026-09-11')['state'] == 'unknown'
