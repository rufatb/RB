"""The late-picks fallback: same checks as the seal, labelled late, never sized."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

import late_picks as L

NOW = dt.datetime(2026, 9, 24, 10, 12, tzinfo=ZoneInfo('America/New_York'))


@pytest.fixture
def root(tmp_path):
    rows = [{'ticker': 'AAA.TO', 'market': 'CA', 'currency': 'CAD', 'last': 100.0, 'atr_pct': 2.0,
             'prev_low': 98.0, 'prev_high': 102.0},
            {'ticker': 'BBB.TO', 'market': 'CA', 'currency': 'CAD', 'last': 50.0, 'atr_pct': 3.0,
             'prev_low': 49.0, 'prev_high': 51.0}]
    brief = {'session': '2026-09-24', 'prepared_at': NOW.isoformat(), 'considered': 2,
             'universe': ['AAA.TO', 'BBB.TO'], 'evidence': {},
             'payload': {'candidates': rows}}
    (tmp_path / L.BRIEF_JSON).write_text(json.dumps(brief))
    return tmp_path


def test_check_refuses_an_invented_ticker_and_a_level_on_the_wrong_side(root):
    answer = {'longs': [{'ticker': 'ZZZ.TO', 'confidence': 0.6, 'reason': 'x'},
                        {'ticker': 'AAA.TO', 'confidence': 0.55, 'reason': 'x', 'invalid_at': 101.0}],
              'shorts': []}
    problems = L.check(root, answer)
    assert any('outside the supplied universe' in p for p in problems)
    assert any('AAA.TO' in p and 'wrong side' in p for p in problems)


def test_compose_is_labelled_late_and_never_sized(root, monkeypatch):
    import deepseek_opportunities as O
    import jev_opportunities as J
    monkeypatch.setattr(O, 'load_diagnostic', lambda r, n: {
        'status': 'READY', 'longs': [{'ticker': 'BBB.TO', 'confidence': 0.6, 'reason': 'r', 'invalid_at': 49.0}],
        'shorts': []})
    monkeypatch.setattr(J, 'load_diagnostic', lambda r, n: {
        'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
        'forced_long': {'ticker': 'AAA.TO', 'probability': 0.3, 'gated_abstain_probability': 0.6,
                        'cleared_gated_abstain': False}})
    monkeypatch.setattr(L, '_biotech', lambda now: [])
    out = L.compose(root, {'longs': [{'ticker': 'AAA.TO', 'confidence': 0.55, 'reason': 'why',
                                       'invalid_at': 98.0}], 'shorts': []}, now=NOW, reason='test')
    text = open(out['text_path']).read()
    assert 'LATE PICKS' in out['subject'] and '2026-09-24' in out['subject']
    assert 'AFTER the open' in text and 'not sized' in text and 'scored separately' in text
    assert 'LONG AAA.TO' in text and 'LONG BBB.TO' in text
    assert 'would rather have done nothing' in text and 'never a selection' in text
    assert 'shares' not in text.lower() and '$' not in text


def test_late_rows_are_their_own_kind_and_enter_at_the_bar_they_were_sent(root, monkeypatch):
    import deepseek_opportunities as O
    import jev_opportunities as J
    monkeypatch.setattr(O, 'load_diagnostic', lambda r, n: {
        'status': 'READY', 'longs': [{'ticker': 'BBB.TO', 'confidence': 0.6, 'basis': 'news'}], 'shorts': []})
    monkeypatch.setattr(J, 'load_diagnostic', lambda r, n: {
        'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
        'forced_short': {'ticker': 'AAA.TO', 'probability': 0.2, 'gated_abstain_probability': 0.5}})
    rows = L.late_rows(root, {'longs': [{'ticker': 'AAA.TO', 'confidence': 0.55, 'reason': 'r',
                                          'basis': 'technical'}], 'shorts': []}, now=NOW)
    kinds = sorted((r['model'], r['kind']) for r in rows)
    assert kinds == [('claude', 'late'), ('deepseek', 'late'), ('jev', 'late_forced')]
    assert {r['entry_time'] for r in rows} == {'10:10'}          # asked 10:12 -> the 10:10 bar
    assert {r['source'] for r in rows} == {'late_picks'}
    assert next(r for r in rows if r['model'] == 'claude')['basis'] == 'technical'
