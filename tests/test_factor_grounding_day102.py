"""Synthetic protocol regressions, not a claim of predictive improvement."""
import copy
import json
from types import SimpleNamespace

import pytest

from adapters import deepseek_adapter as D
import factor_grounding as G
from test_deepseek_adapter import AS_OF, candidate, macro


def payload():
    names = [candidate(ticker) for ticker in ('ENB.TO', 'TRP.TO', 'TD.TO')]
    names[0]['technicals'].update(gap=.419662)
    names[1]['technicals'].update(macd_hist=.177746)
    for item in names:
        item['technicals_scope'] = 'previous_completed_session; daily RSI/MACD from consecutive full sessions'
    return G.request_payload(D.public_payload(names, macro(), AS_OF))


def rows(request):
    return [{'ticker': c['ticker'], 'directional_lean': 'BULL', 'sentiment_score': .3,
             'factor_rationale': 'The disclosed agreement provides contextual support, with uncertain short-run impact.',
             'evidence_ids': [c['headlines'][0]['evidence_id']],
             'forecast_horizon': G.FORECAST_HORIZON} for c in request['candidates']]


def parse(request, output):
    return D.parse_grounded_assessments(json.dumps({'assessments': output}), request)


def test_actual_gap_and_macd_false_prose_exclude_scores_but_keep_healthy_sibling():
    request = payload()
    output = rows(request)
    output[0]['factor_rationale'] = 'A 0.42% gap down supports the supplied bullish catalyst context.'
    output[1]['factor_rationale'] = 'The negative MACD histogram offsets the supplied issuer update.'
    accepted, grounding, private = parse(request, output)
    assert [row['ticker'] for row in accepted] == ['TD.TO']
    assert grounding['excluded'] == {
        'ENB.TO': ['TECHNICAL_PROSE_PROHIBITED'],
        'TRP.TO': ['TECHNICAL_PROSE_PROHIBITED'],
    }
    assert private['provider_rows'] == output
    assert 'gap down' not in json.dumps(accepted)+json.dumps(grounding)
    assert 'negative MACD' not in json.dumps(accepted)+json.dumps(grounding)
    assert parse(request, private['provider_rows'])[:2] == (accepted, grounding)


def test_python_facts_preserve_percent_units_exact_positive_sign_and_old_session():
    request = payload()
    accepted, grounding, _ = parse(request, rows(request))
    enb = grounding['per_ticker']['ENB.TO']['technical_facts']
    gap = next(item for item in enb if item['field'] == 'gap')
    assert gap['value'] == .419662 and gap['sign'] == 'POSITIVE'
    assert gap['unit'] == 'percent' and '+0.419662%' in gap['statement']
    assert gap['as_of'] == '2026-09-10T16:00:00-04:00'
    assert 'prior session' in accepted[0]['factor_rationale']
    assert '0.419662%' in accepted[0]['factor_rationale']
    trp = grounding['per_ticker']['TRP.TO']['technical_facts']
    hist = next(item for item in trp if item['field'] == 'macd_hist')
    assert hist['value'] == .177746 and hist['sign'] == 'POSITIVE'
    assert hist['unit'] == 'quote_currency'
    assert all('disclosed agreement' not in item['factor_rationale'] for item in accepted)


def test_null_zero_and_negative_facts_never_invert_or_invent_values():
    item = candidate()
    item['technicals'] = {'gap': None, 'macd_hist': -.000001, 'r0': 0.0}
    facts = {fact['field']: fact for fact in G.technical_facts(item)}
    assert facts['gap']['value'] is None and facts['gap']['sign'] == 'UNKNOWN'
    assert 'unavailable' in facts['gap']['statement']
    assert facts['macd_hist']['sign'] == 'NEGATIVE'
    assert facts['r0']['sign'] == 'ZERO'


@pytest.mark.parametrize('prose', [
    'The macd_hist field is negative.',
    'An orb_high breakout supports the company.',
    'The vp reading is strong.',
    'VWAP supports the issuer agreement.',
    'The opening-range breakout supports the supplied catalyst.',
])
def test_known_technical_field_aliases_are_prohibited_in_model_prose(prose):
    request = payload(); output = rows(request)
    output[0]['factor_rationale'] = prose
    accepted, grounding, _ = parse(request, output)
    assert len(accepted) == 2
    assert grounding['excluded']['ENB.TO'] == ['TECHNICAL_PROSE_PROHIBITED']


def test_custom_current_scope_does_not_claim_full_session_rvol_denominator():
    item = candidate(); item['technicals_scope'] = 'current_session'
    item['technicals'] = {'rvol': 2.5}
    fact = G.technical_facts(item)[0]
    assert fact['scope'] == 'current_session'
    assert 'not independently certified' in fact['definition']
    assert 'mean volume of 20' not in fact['definition']


@pytest.mark.parametrize('field,value,code', [
    ('evidence_ids', ['E0000000000000000'], 'UNKNOWN_OR_OTHER_TICKER_EVIDENCE_ID'),
    ('evidence_ids', [], 'MISSING_EVIDENCE_SUPPORT'),
    ('forecast_horizon', 'next_year', 'FORECAST_HORIZON_MISMATCH'),
])
def test_semantic_exclusion_is_replayable_and_does_not_erase_siblings(field, value, code):
    request = payload(); output = rows(request)
    output[0][field] = value
    accepted, grounding, private = parse(request, output)
    assert [row['ticker'] for row in accepted] == ['TRP.TO', 'TD.TO']
    assert code in grounding['excluded']['ENB.TO']
    assert parse(request, private['provider_rows'])[:2] == (accepted, grounding)


def test_evidence_ids_are_ticker_bound_deterministic_and_not_semantic_verification():
    request = payload(); output = rows(request)
    assert payload() == request
    assert request['candidates'][0]['headlines'][0]['evidence_id'] != request['candidates'][1]['headlines'][0]['evidence_id']
    output[0]['evidence_ids'] = output[1]['evidence_ids']
    accepted, grounding, _ = parse(request, output)
    assert len(accepted) == 2
    assert grounding['excluded']['ENB.TO'] == ['UNKNOWN_OR_OTHER_TICKER_EVIDENCE_ID']
    assert 'no semantic truth' in grounding['per_ticker']['TD.TO']['verification_scope']
    source = grounding['per_ticker']['TD.TO']['evidence_catalog'][output[2]['evidence_ids'][0]]
    assert source['source_url'] == 'https://issuer.example/news/agreement'
    assert source['title'] == 'Issuer reports a new capacity agreement'


def test_request_adds_horizon_and_units_without_modifying_input_or_claiming_macro_trend():
    inputs = [candidate()]; values = macro(); before = copy.deepcopy((inputs, values))
    request = G.request_payload(D.public_payload(inputs, values, AS_OF))
    assert (inputs, values) == before
    assert request['forecast']['horizon'] == G.FORECAST_HORIZON
    assert 'Actual assessment completion' in request['forecast']['start_rule']
    assert all('change_pct' not in item and item['change_status'] == 'UNAVAILABLE'
               for item in request['macro'].values())
    metadata = request['candidates'][0]['headlines'][0]['evidence_metadata']
    assert metadata['issuer_role'] == metadata['novelty'] == 'UNVERIFIED'
    assert metadata['first_disclosed_at'] is None


@pytest.mark.parametrize('title', [
    'Top Canadian dividend stocks to buy and hold for decades',
    'Bank announces a five-year financing commitment',
])
def test_explicit_commentary_or_multiyear_title_cannot_support_directional_intraday_assessment(title):
    item = candidate(); item['headlines'][0]['title'] = title
    request = G.request_payload(D.public_payload([item], macro(), AS_OF))
    output = rows(request)
    accepted, grounding, private = parse(request, output)
    assert accepted == []
    assert grounding['excluded']['TRP.TO'] == ['NO_INTRADAY_EVENT_SUPPORT']
    assert private['provider_rows'] == output
    output[0].update(directional_lean='NO_EDGE', sentiment_score=0)
    accepted, grounding, _ = parse(request, output)
    assert len(accepted) == 1 and grounding['excluded'] == {}


def test_unclassified_news_is_not_mislabeled_verified_or_automatically_excluded():
    request = payload(); accepted, grounding, _ = parse(request, rows(request))
    assert len(accepted) == 3
    source = next(iter(grounding['per_ticker']['ENB.TO']['evidence_catalog'].values()))
    assert source['evidence_metadata']['classification'] == 'UNCLASSIFIED'
    assert source['evidence_metadata']['primary_source_verified'] is False


@pytest.mark.parametrize('field', ['technicals_scope', 'headline', 'source_url'])
def test_known_credentials_are_rejected_before_transport_even_outside_key_shape(monkeypatch, field):
    monkeypatch.setenv('TEST_GROUNDING_SECRET', 'secret-value-in-a-different-format')
    item = candidate()
    if field == 'headline':
        item['headlines'][0]['title'] += ' secret-value-in-a-different-format'
    elif field == 'source_url':
        item['source_url'] += '/secret-value-in-a-different-format'
    else:
        item[field] += ' secret-value-in-a-different-format'
    with pytest.raises(D.InputValidationError):
        D.public_payload([item], macro(), AS_OF)


def test_duplicate_ids_are_an_explicit_grounding_exclusion():
    request = payload(); output = rows(request)
    output[0]['evidence_ids'] *= 2
    accepted, grounding, _ = parse(request, output)
    assert len(accepted) == 2
    assert grounding['excluded']['ENB.TO'] == ['INVALID_EVIDENCE_IDS']


@pytest.mark.parametrize('mutate', [
    lambda output: output[0].pop('evidence_ids'),
    lambda output: output[0].update(shares=10),
    lambda output: output[0].update(evidence_ids=['https://private.example/key']),
    lambda output: output[0].update(factor_rationale='secret=never-store-this'),
    lambda output: output[0].update(ticker='INVENTED.TO'),
    lambda output: output.pop(),
])
def test_invalid_schema_or_credentials_do_not_create_partial_fabricated_receipts(mutate):
    request = payload(); output = rows(request); mutate(output)
    with pytest.raises(D.ResponseSchemaError):
        parse(request, output)


def test_legacy_four_field_parser_preserves_archived_rationale_without_rewriting():
    row = {'ticker': 'ENB.TO', 'directional_lean': 'BULL', 'sentiment_score': .4,
           'factor_rationale': 'The gap down is described in this old audit record.'}
    assert D.parse_assessments(json.dumps({'assessments': [row]}), ['ENB.TO']) == [row]


def test_evaluate_defaults_to_grounded_contract_and_one_call_partial_status():
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        request = json.loads(kwargs['messages'][1]['content'])
        output = rows(request)
        output[0]['factor_rationale'] = 'A negative MACD histogram supports this opinion.'
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps({'assessments': output}), tool_calls=None, refusal=None))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result = D.evaluate_batch([candidate('ENB.TO'), candidate('TD.TO')], macro(), AS_OF,
                              client=client, model='deepseek-flash')
    assert result['status'] == 'PARTIAL' and result['errorcode'] == 'GROUNDING_EXCLUSIONS'
    assert [row['ticker'] for row in result['assessments']] == ['TD.TO']
    assert len(calls) == 1 and calls[0]['model'] == 'deepseek-flash'
    assert calls[0]['extra_body']['thinking']['type'] == 'disabled'
    assert 'forecast.horizon' in calls[0]['messages'][0]['content']


def test_matching_evidence_id_is_not_claimed_to_validate_arbitrary_natural_language():
    request = payload(); output = rows(request)
    output[0]['factor_rationale'] = 'An unverified narrative could still be wrong.'
    accepted, grounding, private = parse(request, output)
    assert len(accepted) == 3
    assert 'could still be wrong' not in accepted[0]['factor_rationale']
    assert 'could still be wrong' in private['provider_rows'][0]['factor_rationale']
    assert 'no semantic truth' in grounding['per_ticker']['ENB.TO']['verification_scope']
