"""The nomination round (day-129, PREREGISTER_day129_nominations.md): every
model names its best two per side for the council to argue over. A different
question from the desks', never a selection."""
import datetime as dt
import json

import pytest

import council as K
import deepseek_opportunities as O
import nominations as N

ET = K.ET
NOW = dt.datetime(2026, 10, 9, 8, 59, tzinfo=ET)


def nom(t, c=0.55, reason='rows say so', basis='technical', inv=None):
    out = {'ticker': t, 'confidence': c, 'reason': reason, 'basis': basis}
    if inv is not None:
        out['invalid_at'] = inv
    return out


def rows_for(*tickers):
    return [{'ticker': t, 'last': 10.0, 'prev_low': 9.5, 'prev_high': 10.5, 'atr_pct': 2.0}
            for t in tickers]


def test_the_prompt_is_the_desks_field_documentation_then_the_nomination_rules():
    text = N.prompt()
    head = O.SYSTEM_PROMPT.partition(N.SPLIT)[0]
    assert text.startswith(head) and text == head + N.NOMINATION_RULES      # byte for byte
    # the desks' own rules are NOT carried: this question may not abstain
    assert 'FEWER IS CORRECT WHEN THE EVIDENCE' not in text
    assert 'You MUST nominate exactly two per side' in text
    assert 'the committee, not you,\ndecides whether any of them is worth doing' in text


def test_the_registration_quotes_the_rules_it_registered():
    reg = open('PREREGISTER_day129_nominations.md').read()
    assert 'exactly TWO longs and TWO shorts, best first' in reg
    assert N.VERSION in reg


def test_a_missing_split_refuses_rather_than_sending_the_desk_rules(monkeypatch):
    monkeypatch.setattr(O, 'SYSTEM_PROMPT', 'a prompt with no rules section')
    with pytest.raises(ValueError, match='NOMINATION_PROMPT_SPLIT_MISSING'):
        N.prompt()


def test_clean_is_the_desks_validator_plus_one_rule():
    allowed = {'AC.TO', 'SU.TO', 'TD.TO', 'CNQ.TO', 'RY.TO'}
    answer = {'longs': [nom('AC.TO', 0.6), nom('TD.TO', 0.52), nom('RY.TO', 0.51)],     # a third
              'shorts': [nom('TD.TO', 0.55), nom('NVDA', 0.9)]}                         # an outsider
    longs, shorts, gaps = N.clean(answer, allowed, rows_for(*allowed))
    # two per side at most; a name on both sides is dropped from both; never invented
    assert [p['ticker'] for p in longs] == ['AC.TO'] and shorts == []
    assert 'nominated on both sides, dropped from both: TD.TO' in gaps
    assert 'NVDA outside the supplied universe' in gaps
    assert all(p['nominated'] for p in longs)
    assert N.clean('not json', allowed, []) == ([], [], ['the reply was not a JSON object'])


def test_a_wrong_side_level_is_dropped_like_a_desks():
    allowed = {'AC.TO', 'SU.TO'}
    longs, shorts, gaps = N.clean({'longs': [nom('AC.TO', inv=10.4)], 'shorts': [nom('SU.TO', inv=9.0)]},
                                  allowed, rows_for('AC.TO', 'SU.TO'))
    # a LONG "wrong if below 10.4" sits ABOVE the 10.0 close: the same check_levels a desk gets
    assert 'invalid_at' not in longs[0] and 'invalid_at' not in shorts[0]
    assert len(gaps) == 2


def test_collect_asks_each_model_once_and_a_failure_costs_only_that_model():
    seen = []

    def good(system, user):
        seen.append((system, json.loads(user)))
        return {'longs': [nom('AC.TO')], 'shorts': [nom('SU.TO')]}

    def down(system, user):
        raise RuntimeError('HTTP_503')
    payload = {'session': '2026-10-09', 'candidates': rows_for('AC.TO', 'SU.TO')}
    out, errors = N.collect(payload, {'AC.TO', 'SU.TO'}, ask={'deepseek': good, 'gemini': down})
    assert set(out) == {'deepseek'} and errors == {'nominations gemini': 'HTTP_503'}
    assert [p['ticker'] for p in out['deepseek']['longs']] == ['AC.TO']
    assert seen[0][0] == N.prompt() and seen[0][1] == payload        # the desks' brief, as is


def test_the_table_holds_selections_then_nominations_then_jev_labelled():
    desk = {'status': 'READY', 'longs': [{'ticker': 'AC.TO', 'confidence': 0.6, 'reason': 'selected'}],
            'shorts': []}
    off = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []}
    jev = {**off, 'forced_long_top': [{'ticker': 'CNQ.TO', 'probability': 0.4},
                                      {'ticker': 'AC.TO', 'probability': 0.3}],
           'forced_short_top': [{'ticker': 'SU.TO', 'probability': 0.5}]}
    noms = {'deepseek': {'longs': [{'ticker': 'AC.TO', 'confidence': 0.55, 'reason': 'nominated'}],
                         'shorts': [{'ticker': 'SU.TO', 'confidence': 0.52, 'reason': 'ds short'}]},
            'claude': {'longs': [], 'shorts': [{'ticker': 'TD.TO', 'confidence': 0.51, 'reason': 'c'}]}}
    table = K.positions(off, desk, off, jev, '2026-10-09', nominations=noms)
    got = {(p['side'], p['ticker']): [(x['model'], x['how']) for x in p['proposers']] for p in table}
    assert got[('LONG', 'AC.TO')] == [('deepseek', 'selected'), ('jev', 'forced')]   # first label kept
    assert got[('SHORT', 'SU.TO')] == [('deepseek', 'nominated'), ('jev', 'forced')]
    assert got[('SHORT', 'TD.TO')] == [('claude', 'nominated')]
    assert got[('LONG', 'CNQ.TO')] == [('jev', 'forced')]
    lead = {(p['side'], p['ticker']): (p['lead'], p['reason']) for p in table}
    assert lead[('LONG', 'AC.TO')] == ('DeepSeek', 'selected')       # a selection leads a nomination
    assert lead[('SHORT', 'SU.TO')] == ('DeepSeek', 'ds short')      # Jev, no reasons, is last


def test_the_table_is_capped_at_sixteen_keeping_selections_first():
    off = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []}
    desk = {'status': 'READY', 'longs': [], 'shorts': [{'ticker': 'ZZZ.TO', 'confidence': 0.6, 'reason': 'z'}]}
    names = ['N%02d.TO' % i for i in range(20)]
    noms = {'deepseek': {'longs': [{'ticker': t, 'confidence': 0.5, 'reason': 'r'} for t in names[:10]],
                         'shorts': []},
            'gemini': {'longs': [{'ticker': t, 'confidence': 0.5, 'reason': 'r'} for t in names[8:20]],
                       'shorts': []}}
    table = K.positions(off, off, desk, off, '2026-10-09', nominations=noms)
    assert len(table) == K.MAX_POSITIONS == 16
    kept = {p['ticker'] for p in table}
    assert 'ZZZ.TO' in kept                                       # what a desk SELECTED stays
    assert {'N08.TO', 'N09.TO'} <= kept                           # then the most-proposed
    assert [p['id'] for p in table] == ['P%d' % i for i in range(1, 17)]


def test_the_control_is_clean_only_with_both_planted_names_on_their_own_sides():
    def right(system, user):
        return {'longs': [nom(O.CONTROL_LONG, 0.7), nom('NOIS1.TO', 0.5)],
                'shorts': [nom(O.CONTROL_SHORT, 0.65), nom('NOIS2.TO', 0.5)]}

    def swapped(system, user):
        return {'longs': [nom(O.CONTROL_SHORT, 0.6), nom('NOIS1.TO', 0.5)],
                'shorts': [nom(O.CONTROL_LONG, 0.6), nom('NOIS2.TO', 0.5)]}
    assert [r['clean'] for r in N.control('deepseek', right, runs=2)] == [True, True]
    assert [r['clean'] for r in N.control('deepseek', swapped, runs=1)] == [False]


def test_stage_asks_for_nominations_before_the_table_and_names_a_failure(tmp_path, monkeypatch):
    import claude_opportunities as C
    import gemini_opportunities as G
    import jev_opportunities as J
    from test_council import FakeDeepSeek, FakeGemini, b
    off = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []}
    for mod in (C, O, G, J):
        monkeypatch.setattr(mod, 'load_prepared', lambda root, now, **kw: off)
    monkeypatch.setattr(K, 'evidence_rows', lambda root, now, tickers: [
        {'ticker': t, 'r0': 1.0} for t in sorted(tickers)])
    brief = {'payload': {'session': '2026-10-09', 'candidates': rows_for('AC.TO', 'SU.TO')},
             'universe': ['AC.TO', 'SU.TO']}
    monkeypatch.setattr(C, 'read_brief', lambda root, now: brief)

    def ds_nominates(system, user):
        return {'longs': [nom('AC.TO', 0.56)], 'shorts': [nom('SU.TO', 0.53)]}

    def gm_nominates(system, user):
        raise RuntimeError('HTTP_429')
    # every desk abstained: without nominations the table would be empty
    ds = FakeDeepSeek([b('ENDORSE 0.6', 'ABSTAIN'), b('ENDORSE 0.6', 'ABSTAIN')])
    gm = FakeGemini([b('ENDORSE 0.6', 'OPPOSE 0.6'), b('ENDORSE 0.6', 'OPPOSE 0.6')])
    out = K.stage(tmp_path, now=NOW, clients={'deepseek': ds, 'gemini': gm}, wait=False,
                  nominate={'deepseek': ds_nominates, 'gemini': gm_nominates}, clock=lambda: NOW,
                  jev_poster=lambda body, key, timeout: {'answers': {'best': {'probabilities': {'NONE': 1.0}}}},
                  scout_fn=lambda tickers, now: ({}, []))
    assert [(p['side'], p['ticker']) for p in out['positions']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert {x['how'] for p in out['positions'] for x in p['proposers']} == {'nominated'}
    assert out['table_version'] == N.VERSION
    assert out['nominations'] == {'deepseek': {'longs': ['AC.TO'], 'shorts': ['SU.TO'], 'gaps': []}}
    assert out['errors']['nominations gemini'] == 'HTTP_429'
    assert out['status'] == 'READY' and out['picks'] == ['P1']           # the rule is unchanged


def test_a_missing_brief_costs_the_nominations_only(tmp_path, monkeypatch):
    import claude_opportunities as C
    import gemini_opportunities as G
    import jev_opportunities as J
    off = {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []}
    for mod in (C, O, G, J):
        monkeypatch.setattr(mod, 'load_prepared', lambda root, now, **kw: off)
    out = K.stage(tmp_path, now=NOW, clients={'deepseek': None, 'gemini': None}, wait=False,
                  nominate={'deepseek': lambda s, u: {}}, clock=lambda: NOW)
    assert out['status'] == 'NO_POSITIONS' and out['errors'] == {'nominations': 'CLAUDE_BRIEF_NOT_STAGED'}
