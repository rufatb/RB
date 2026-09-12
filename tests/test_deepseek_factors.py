"""Saved factor integrity and fixed shadow comparisons, entirely offline."""
import copy
import datetime as dt
import hashlib
import json
from zoneinfo import ZoneInfo

import pytest

import deepseek_factors as D
import deepseek_policy as P
from factor_inputs import validate_payload
from report_store import encode

ET = ZoneInfo('America/New_York')
PREP = dt.datetime(2026, 9, 11, 8, 35, tzinfo=ET)
NOW = dt.datetime(2026, 9, 11, 9, 46, 30, tzinfo=ET)


def assessment(ticker='TRP.TO', lean='BULL', score=.5):
    return {'ticker': ticker, 'directional_lean': lean, 'sentiment_score': score,
            'factor_rationale': 'The supplied issuer update supports a positive contextual lean.'}


def public_inputs(tickers=('TRP.TO', 'ENB.TO')):
    source = 'https://query1.finance.yahoo.com/v8/finance/chart/TRP.TO'
    candidates = []
    for ticker in tickers:
        candidates.append({'ticker': ticker, 'technical_source': 'python',
            'technical_provenance': {'input_sha256': 'a'*64, 'computation': 'upstream.indicators.v1',
                'computed_at': PREP.isoformat(), 'source_url': source},
            'technicals': {'vwap': 100., 'rsi': 50., 'macd': .1, 'macd_signal': .05,
                           'macd_hist': .05, 'orb_high': 101., 'orb_low': 99., 'rvol': 1.1},
            'technicals_scope': 'previous_completed_session',
            'technicals_as_of': '2026-09-10T16:00:00-04:00', 'source_url': source,
            'headlines': [{'title': 'Issuer publishes operating update',
                          'source_url': 'https://issuer.example/news/update',
                          'published_at': PREP.isoformat()}], 'catalyst_tags': []})
    return {'as_of': PREP.isoformat(), 'candidates': candidates,
            'macro': {name: {'value': 10., 'as_of': PREP.isoformat(),
                            'source_url': 'https://provider.example/data/'+name}
                      for name in P.MACRO_KEYS}}


def snapshot(tickers=('TRP.TO', 'ENB.TO')):
    inputs = validate_payload(public_inputs(tickers), PREP)
    return {'schema_version': P.SCHEMA_VERSION, 'prompt_version': P.PROMPT_VERSION,
            'session': PREP.date().isoformat(), 'as_of': PREP.isoformat(),
            'prepared_at': PREP.isoformat(), 'model': P.DEFAULT_MODEL,
            'status': 'READY', 'adopted': False, 'inputs': inputs,
            'input_sha256': hashlib.sha256(encode(inputs).encode()).hexdigest(),
            'assessments': [assessment(ticker) for ticker in tickers],
            'candidate_gaps': {ticker: [] for ticker in tickers}, 'gaps': [],
            'requested': len(tickers), 'covered': len(tickers),
            'batches': [{'status': 'READY', 'model': P.DEFAULT_MODEL, 'request_id': 'req_123',
                         'prompt_version': P.PROMPT_VERSION, 'schema_version': P.SCHEMA_VERSION,
                         'input_sha256': 'b'*64}],
            'registration': 'PREREGISTER_day99_deepseek.md'}


def save(root, obj):
    path = root/'deepseek_snapshot.json'
    sealed = {key: value for key, value in obj.items() if key != 'snapshot_sha256'}
    sealed['snapshot_sha256'] = hashlib.sha256(encode(sealed).encode()).hexdigest()
    path.write_text(json.dumps(sealed))
    return path


def rehash(obj):
    obj['input_sha256'] = hashlib.sha256(encode(obj['inputs']).encode()).hexdigest()


def quote(ticker='TRP.TO', *, width=.02, now=NOW):
    from quotes import validate_equity
    return validate_equity({'symbol': ticker, 'currency': 'CAD', 'bid': 100., 'ask': 100.+width,
                            'quoteTime': (now-dt.timedelta(seconds=15)).isoformat()},
                           ticker, now, currency='CAD')


def rank(candidates=None, staged=None, quotes=None, **kwargs):
    candidates = [{'t': 'TRP.TO', 'p_up': .6}] if candidates is None else candidates
    staged = snapshot(('TRP.TO',)) if staged is None else staged
    quotes = {'TRP.TO': quote()} if quotes is None else quotes
    return D.rank_shadow(candidates, staged, quotes, NOW, min_sided_p=.55, **kwargs)


def test_valid_snapshot_is_local_read_only_and_has_request_provenance(tmp_path, monkeypatch):
    original = snapshot()
    path = save(tmp_path, original)
    before = path.read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError('loader must not call SDK')
    monkeypatch.setattr('adapters.deepseek_adapter.evaluate_batch', forbidden)
    loaded = D.load_prepared(tmp_path, NOW)
    assert loaded['status'] == 'READY'
    assert loaded['covered'] == loaded['requested'] == 2
    assert loaded['batches'][0]['request_id'] == 'req_123'
    assert loaded['adopted'] is False
    assert path.read_bytes() == before


def test_partial_success_preserves_assessment_and_missing_candidate_gap(tmp_path):
    obj = snapshot()
    obj['assessments'] = obj['assessments'][:1]
    obj['gaps'] = ['Second batch timed out.']
    obj['candidate_gaps']['ENB.TO'] = ['TIMEOUT']
    obj['covered'] = 999
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    assert loaded['status'] == 'PARTIAL'
    assert loaded['covered'] == 1 and loaded['requested'] == 2
    assert [row['ticker'] for row in loaded['assessments']] == ['TRP.TO']
    assert loaded['candidate_gaps']['ENB.TO'] == ['TIMEOUT', 'MODEL_ASSESSMENT_UNAVAILABLE']
    assert not loaded['candidate_gaps']['TRP.TO']
    ranked = rank([{'t': 'TRP.TO', 'p_up': .6}, {'t': 'ENB.TO', 'p_up': .6}], loaded)
    assert ranked['h2']['longs'][0]['ticker'] == 'TRP.TO'
    assert ranked['rows'][1]['status'] == 'UNAVAILABLE'
    assert ranked['rows'][1]['factor'] is None


def test_candidate_data_gap_cannot_be_cleared_by_forged_ready_label(tmp_path):
    obj = snapshot()
    obj['inputs']['candidates'][1]['headlines'] = []
    obj['candidate_gaps'] = {}
    rehash(obj)
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    assert loaded['status'] == 'PARTIAL'
    assert 'NO_CURRENT_CATALYST_EVIDENCE' in loaded['candidate_gaps']['ENB.TO']
    result = rank([{'t': 'ENB.TO', 'p_up': .65}], loaded, {'ENB.TO': quote('ENB.TO')})
    assert not result['h1']['longs']
    assert result['rows'][0]['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('mutation', [
    lambda x: x.update(schema_version=True),
    lambda x: x.update(schema_version=99),
    lambda x: x.update(prompt_version='unknown'),
    lambda x: x.update(adopted=True),
    lambda x: x.update(session='2026-09-10'),
    lambda x: x.update(prepared_at='2026-09-11T09:30:00-04:00'),
    lambda x: x.update(prepared_at='2026-09-11T09:47:00-04:00'),
    lambda x: x.update(prepared_at='2026-09-11T08:35:00'),
    lambda x: x.update(prepared_at='private-secret-value'),
    lambda x: x.update(as_of='2026-09-11T08:36:00-04:00'),
    lambda x: x.update(as_of='2026-09-10T23:59:00-04:00'),
    lambda x: x.update(input_sha256='a'*64),
    lambda x: x['inputs']['candidates'][0]['technicals'].update(rsi=99.),
    lambda x: x.update(model='sk-private-secret-value'),
    lambda x: x.update(model='https://host?api_key=private-secret-value'),
    lambda x: x['batches'][0].update(model='different-model'),
    lambda x: x['batches'][0].update(prompt_version='unregistered'),
    lambda x: x['batches'][0].update(schema_version=True),
    lambda x: x['assessments'][0].update(ticker='MADEUP.TO'),
    lambda x: x['assessments'][0].update(sentiment_score=True),
    lambda x: x['assessments'][0].update(shares=100),
    lambda x: x.update(assessments=[x['assessments'][0], x['assessments'][0]]),
    lambda x: x.update(candidate_gaps={'TRP.TO': 'not a list'}),
])
def test_invalid_persisted_snapshot_is_typed_and_cannot_echo_input(tmp_path, mutation):
    obj = snapshot()
    mutation(obj)
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    assert loaded['status'] == 'UNAVAILABLE'
    assert loaded['assessments'] == []
    assert 'private-secret-value' not in json.dumps(loaded)
    assert 'NO EDGE' not in json.dumps(loaded)


def test_missing_and_stale_snapshots_remain_unevaluated(tmp_path):
    missing = D.load_prepared(tmp_path, NOW)
    assert missing['status'] == 'UNAVAILABLE'
    obj = snapshot()
    save(tmp_path, obj)
    stale = D.load_prepared(tmp_path, NOW+dt.timedelta(hours=6))
    assert stale['status'] == 'UNAVAILABLE'
    for loaded in (missing, stale):
        result = rank(staged=loaded)
        assert result['decision'].startswith('UNAVAILABLE')
        assert result['evaluation_status'] == 'UNAVAILABLE'
        assert not result['h1']['longs'] and not result['h2']['longs']


def test_duplicate_json_keys_are_rejected_at_any_depth(tmp_path):
    obj = snapshot()
    raw = json.dumps(obj).replace('"sentiment_score": 0.5', '"sentiment_score": 0.5, "sentiment_score": 0.9')
    (tmp_path/'deepseek_snapshot.json').write_text(raw)
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert 'duplicate JSON key' in result['reason']


def test_valid_schema_assessment_tamper_invalidates_complete_snapshot_receipt(tmp_path):
    path = save(tmp_path, snapshot())
    sealed = json.loads(path.read_text())
    sealed['assessments'][0]['sentiment_score'] = .1
    path.write_text(json.dumps(sealed))
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert 'snapshot integrity mismatch' in result['reason']
    assert result['assessments'] == []


def test_stripping_seal_cannot_bypass_receipt_integrity(tmp_path):
    path = save(tmp_path, snapshot())
    sealed = json.loads(path.read_text())
    sealed.pop('snapshot_sha256')
    path.write_text(json.dumps(sealed))
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert 'snapshot integrity seal' in result['reason']


def test_nonstandard_nan_in_persisted_receipt_is_rejected_before_use(tmp_path):
    path = save(tmp_path, snapshot())
    invalid = json.loads(path.read_text())
    invalid['assessments'][0]['sentiment_score'] = float('nan')
    path.write_text(json.dumps(invalid))
    result = D.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert 'nonfinite JSON' in result['reason']


def test_snapshot_diagnostics_and_extras_are_sanitized(tmp_path, monkeypatch):
    obj = snapshot()
    monkeypatch.setenv('PRIVATE_TEST_SECRET', 'private-never-reveal-value')
    obj['gaps'] = ['https://example.test/?api_key=private-never-reveal-value']
    obj['candidate_gaps']['ENB.TO'] = ['private-never-reveal-value']
    obj['password'] = 'private-never-reveal-value'
    obj['batches'][0]['raw_provider_response'] = 'private-never-reveal-value'
    obj['batches'][0]['details'] = 'private-never-reveal-value'
    obj['inputs']['candidates'][0]['headlines'][0]['title'] = 'Update private-never-reveal-value'
    rehash(obj)
    save(tmp_path, obj)
    loaded = D.load_prepared(tmp_path, NOW)
    assert loaded['status'] == 'PARTIAL'
    assert 'private-never-reveal-value' not in json.dumps(loaded)
    assert 'password' not in loaded
    assert 'raw_provider_response' not in loaded['batches'][0]


@pytest.mark.parametrize('quant, sentiment, expected', [(0, -1, .35), (1, 1, .65),
                                                       (.5, 0, .5), (.6, .5, .595)])
def test_combination_reuses_clamp_and_never_claims_unbounded_probability(monkeypatch, quant, sentiment, expected):
    import dashboard
    original, seen = dashboard.clamp_probability, []
    def spy(value):
        seen.append(value)
        return original(value)
    monkeypatch.setattr(dashboard, 'clamp_probability', spy)
    assert D.combined_probability(quant, sentiment) == pytest.approx(expected)
    assert seen == [pytest.approx(.8*quant+.2*(.5+.15*sentiment))]


@pytest.mark.parametrize('quant, sentiment', [(True, 0), (.5, True), (float('nan'), 0),
                                             (.5, float('inf')), ('0.6', .5),
                                             (1.1, 0), (-.1, 0), (.5, 1.1), (.5, -1.1)])
def test_invalid_scores_cannot_be_repaired_by_clamping(quant, sentiment):
    with pytest.raises(ValueError):
        D.combined_probability(quant, sentiment)


@pytest.mark.parametrize('quant, lean, sentiment', [(.53, 'BULL', .1), (.6, 'BEAR', -.5),
                                                  (.4, 'BULL', .5), (.6, 'NO_EDGE', 0),
                                                  (.6, 'BULL', 0), (.4, 'BEAR', 0)])
def test_threshold_and_alignment_abstain_without_forcing_names(quant, lean, sentiment):
    obj = snapshot(('TRP.TO',)); obj['assessments'] = [assessment(lean=lean, score=sentiment)]
    result = rank([{'t': 'TRP.TO', 'p_up': quant}], obj)
    assert result['rows'][0]['status'] == 'ABSTAIN'
    assert result['rows'][0]['decision'] == result['decision'] == 'NO EDGE - WAIT'
    assert not any(result['h1'].values()) and not any(result['h2'].values())


def test_h2_orders_by_validated_spread_before_strength_and_has_at_most_two_per_side():
    tickers = ['AAA.TO', 'BBB.TO', 'CCC.TO', 'DDD.TO', 'EEE.TO', 'FFF.TO']
    obj = snapshot(tuple(tickers))
    obj['assessments'] = [assessment(ticker, 'BULL' if i < 3 else 'BEAR', .5 if i < 3 else -.5)
                          for i, ticker in enumerate(tickers)]
    candidates = [{'t': ticker, 'p_up': q, 'shares': 123}
                  for ticker, q in zip(tickers, [.65, .6, .6, .35, .4, .4])]
    quotes = {ticker: quote(ticker, width=.2 if ticker in ('AAA.TO', 'DDD.TO') else .02)
              for ticker in tickers}
    before = copy.deepcopy((candidates, obj, quotes))
    result = rank(candidates, obj, quotes)
    assert [row['ticker'] for row in result['h1']['longs']] == ['AAA.TO', 'BBB.TO']
    assert [row['ticker'] for row in result['h2']['longs']] == ['BBB.TO', 'CCC.TO']
    assert [row['ticker'] for row in result['h2']['shorts']] == ['EEE.TO', 'FFF.TO']
    assert (candidates, obj, quotes) == before
    assert result['adopted'] is False
    assert 'shares' not in json.dumps(result)
    assert result['mde']['net_bps'] is None


@pytest.mark.parametrize('mutation', [
    lambda x: x.update(status='CORROBORATED'), lambda x: x.update(currency='USD'),
    lambda x: x.update(ticker='ENB.TO'), lambda x: x.update(quote_time=None),
    lambda x: x.update(quote_time='2026-09-11T09:45:59-04:00'),
    lambda x: x.update(quote_time='2026-09-11T09:46:31-04:00'),
    lambda x: x.update(quote_time='2026-09-10T09:46:15-04:00'),
    lambda x: x.update(quote_time='2026-09-11T09:46:15'),
    lambda x: x.update(bid=0), lambda x: x.update(bid=True),
    lambda x: x.update(ask=99), lambda x: x.pop('bid'),
    lambda x: x.update(spread_bps=0), lambda x: x.update(spread_bps=float('nan')),
])
def test_bad_or_inexact_quotes_never_enter_cost_rank(mutation):
    observed = quote(); mutation(observed)
    result = rank(quotes={'TRP.TO': observed})
    assert len(result['h1']['longs']) == 1
    assert result['h2']['longs'] == []
    assert result['rows'][0]['spread_bps'] is None
    assert 'exact entry costs unavailable' in result['decision']


def test_late_non_session_and_us_quotes_do_not_pass_tsx_execution_contract():
    assert D.exact_spread(quote(), 'TRP.TO', NOW+dt.timedelta(minutes=1))[0] is None
    saturday = NOW+dt.timedelta(days=1)
    assert D.exact_spread(quote(now=saturday), 'TRP.TO', saturday)[0] is None
    observed = quote('TRP'); observed['currency'] = 'USD'
    assert D.exact_spread(observed, 'TRP', NOW)[0] is None


def test_missing_scan_is_unavailable_and_does_not_reuse_recorded_shares():
    result = rank([{'t': 'TRP.TO', 'p_up': .65, 'shares': 123}], scan_available=False)
    assert result['decision'].startswith('UNAVAILABLE')
    assert not result['rows']
    assert not any(result['h1'].values())


def test_duplicate_quantitative_candidates_cannot_win_by_first_row_order():
    result = rank([{'t': 'TRP.TO', 'p_up': .65}, {'t': 'TRP.TO', 'p_up': .2}])
    assert result['rows'][0]['status'] == 'UNAVAILABLE'
    assert not any(result['h1'].values())


@pytest.mark.parametrize('value', [None, True, float('nan'), float('inf'), -1, 2])
def test_invalid_quantitative_values_stay_unavailable_and_json_serializable(value):
    result = rank([{'t': 'TRP.TO', 'p_up': value}])
    assert result['rows'][0]['quant_probability'] is None
    assert result['rows'][0]['status'] == 'UNAVAILABLE'
    json.dumps(result, allow_nan=False)


def test_malformed_factor_object_never_crashes_optional_shadow_view():
    obj = snapshot(('TRP.TO',)); obj['assessments'][0]['sentiment_score'] = float('nan')
    result = rank(staged=obj)
    assert result['decision'].startswith('UNAVAILABLE')
    assert result['rows'] == []


def test_partial_evaluation_does_not_claim_whole_pool_has_no_edge():
    obj = snapshot()
    obj['assessments'][0] = assessment(lean='NO_EDGE', score=0)
    obj['candidate_gaps']['ENB.TO'] = ['NO_CURRENT_CATALYST_EVIDENCE']
    result = rank([{'t': 'TRP.TO', 'p_up': .6}, {'t': 'ENB.TO', 'p_up': .6}], obj)
    assert result['decision'].startswith('PARTIAL')
    assert result['evaluation_status'] == 'PARTIAL'
