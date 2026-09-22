"""Real finance abbreviations must not invalidate a strict provider batch."""
import json

import pytest

from adapters.deepseek_adapter import parse_assessments, ResponseSchemaError


def row(ticker, rationale):
    return {'ticker': ticker, 'directional_lean': 'BULL', 'sentiment_score': .4,
            'factor_rationale': rationale}


@pytest.mark.parametrize('rationale', [
    'U.S. demand supports the disclosed capacity expansion.',
    'U.K. demand supports the disclosed expansion.',
    'U.S. FDA review remains an unresolved catalyst.',
    'U.S. Treasury yields provide mixed macro context.',
    'RBC Inc. announced a new customer program.',
    'The issuer Ltd. reported higher operating cash flow.',
    'The company Corp. expects a disclosed capacity addition.',
    'The issuer Inc. CEO described the disclosed expansion.',
    'The disclosed drivers, e.g. customer growth, support the supplied context.',
    'The disclosed driver, i.e. customer growth, supports the supplied context.',
    'Margins rose to 3.5% vs. 2.1% in the dated release.',
    'The change vs. Treasury yields gives mixed macro context.',
    'Reported earnings were $1.25 per share with 3.5% volume growth.',
])
def test_valid_abbreviated_single_sentence_is_preserved_exactly(rationale):
    original = row('RY.TO', rationale)
    actual = parse_assessments(json.dumps({'assessments': [original]}), ['RY.TO'])
    assert actual == [original]
    assert actual[0]['factor_rationale'] == rationale


@pytest.mark.parametrize('rationale, first', [
    ('The issuer announced expansion. Timing remains uncertain.', 'The issuer announced expansion.'),
    ('The issuer announced expansion! Timing remains uncertain.', 'The issuer announced expansion!'),
    ('Will margins improve? The supplied data cannot answer.', 'Will margins improve?'),
    ('Demand rose in the U.S. Earnings remained uncertain.', 'Demand rose in the U.S.'),
    ('The issuer acquired Company Inc. Management has not given guidance.', 'The issuer acquired Company Inc.'),
    ('The company sold Subsidiary Ltd. Another transaction remains uncertain.', 'The company sold Subsidiary Ltd.'),
])
def test_a_second_sentence_is_cut_not_a_reason_to_discard_the_batch(rationale, first):
    """2026-09-22: this raised, and one row's second sentence discarded every
    other row in its batch — 271 of 276 names assessed by nobody. The rule
    guards a DISPLAY field, so the repair is a strict subset of the model's
    own words, flagged on the row. The score and lean are untouched."""
    out = parse_assessments(json.dumps({'assessments': [row('RY.TO', rationale)]}), ['RY.TO'])
    assert out[0]['factor_rationale'] == first
    assert out[0]['rationale_truncated'] is True
    assert out[0]['sentiment_score'] == row('RY.TO', rationale)['sentiment_score']


def test_one_multi_sentence_row_no_longer_costs_its_batch():
    records = [row('X'+str(i), 'The supplied operating update supports the stated context.') for i in range(25)]
    records[7]['factor_rationale'] = 'Demand rose. Guidance is pending.'
    out = parse_assessments(json.dumps({'assessments': records}), ['X'+str(i) for i in range(25)])
    assert len(out) == 25
    assert [r.get('rationale_truncated') for r in out].count(True) == 1


@pytest.mark.parametrize('rationale', [
    'The issuer announced\nexpansion.',
    'The issuer announced\rexpansion.',
    'The issuer announced\texpansion.',
    'The issuer announced\x00expansion.',
])
def test_control_characters_are_still_rejected(rationale):
    with pytest.raises(ResponseSchemaError):
        parse_assessments(json.dumps({'assessments': [row('RY.TO', rationale)]}), ['RY.TO'])


def test_one_finance_abbreviation_no_longer_discards_other_valid_batch_rows():
    records = [row('X'+str(i), 'The supplied operating update supports the stated context.') for i in range(25)]
    records[12]['factor_rationale'] = 'U.S. demand supports the disclosed expansion.'
    assert parse_assessments(json.dumps({'assessments': records}), ['X'+str(i) for i in range(25)]) == records


def test_abbreviation_fix_does_not_relax_completeness_or_extra_fields():
    valid = row('RY.TO', 'U.S. demand supports the disclosed expansion.')
    with pytest.raises(ResponseSchemaError):
        parse_assessments(json.dumps({'assessments': [valid]}), ['RY.TO', 'TD.TO'])
    with pytest.raises(ResponseSchemaError):
        parse_assessments(json.dumps({'assessments': [{**valid, 'probability': .6}]}), ['RY.TO'])
