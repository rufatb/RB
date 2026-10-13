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
    # amendment 2: the whole nomination is kept, so it can be shown and scored
    assert out['nomination_picks'] == {'deepseek': {
        'longs': [{'ticker': 'AC.TO', 'confidence': 0.56, 'reason': 'rows say so', 'basis': 'technical'}],
        'shorts': [{'ticker': 'SU.TO', 'confidence': 0.53, 'reason': 'rows say so', 'basis': 'technical'}]}}
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


# ── amendment 2 (owner, 2026-10-13): shown on a no-pick day, scored apart ────

def sat_council():
    """10-13's shape: the council picked LONG ATZ.TO and SHORT CCA.TO, both
    Claude nominations; DeepSeek nominated the other side of ATZ.TO."""
    def pos(i, side, t, *who):
        return {'id': 'P%d' % i, 'side': side, 'ticker': t, 'lead': 'Claude', 'reason': 'r',
                'invalid_at': None, 'proposers': [{'model': m, 'how': h, 'confidence': 0.5, 'reason': 'r'}
                                                  for m, h in who]}
    positions = [pos(1, 'LONG', 'ATZ.TO', ('claude', 'nominated'), ('jev', 'forced')),
                 pos(2, 'SHORT', 'ATZ.TO', ('deepseek', 'nominated')),
                 pos(3, 'SHORT', 'CCA.TO', ('claude', 'nominated'), ('gemini', 'nominated'))]
    votes = lambda e, o: {m: {'stance': 'ENDORSE' if m in e else 'OPPOSE' if m in o else 'ABSTAIN',
                              'conviction': 0.6 if m in e + o else None, 'argument': 'a'}
                          for m in ('Claude', 'DeepSeek', 'Gemini', 'Jev')}
    rows = [{'id': 'P1', 'ticker': 'ATZ.TO', 'side': 'LONG', 'endorse': ['Claude', 'DeepSeek', 'Gemini'],
             'oppose': [], 'seats': [], 'weakest': 0.6, 'consensus': True,
             'votes': votes(['Claude', 'DeepSeek', 'Gemini'], [])},
            {'id': 'P2', 'ticker': 'ATZ.TO', 'side': 'SHORT', 'endorse': [],
             'oppose': ['Claude', 'DeepSeek', 'Gemini'], 'seats': [], 'weakest': 0.0, 'consensus': False,
             'votes': votes([], ['Claude', 'DeepSeek', 'Gemini'])},
            {'id': 'P3', 'ticker': 'CCA.TO', 'side': 'SHORT', 'endorse': ['Claude', 'DeepSeek', 'Gemini', 'Jev'],
             'oppose': [], 'seats': [], 'weakest': 0.6, 'consensus': True,
             'votes': votes(['Claude', 'DeepSeek', 'Gemini', 'Jev'], [])}]
    return {'session': '2026-10-13', 'status': 'READY', 'picks': ['P1', 'P3'], 'positions': positions,
            'table_version': N.VERSION,
            'tally': {'members': ['Claude', 'DeepSeek', 'Gemini', 'Jev'], 'absent': [], 'rows': rows},
            'nomination_picks': {
                'claude': {'longs': [nom('ATZ.TO', 0.42, inv=141.86), nom('SHOP.TO', 0.38)],
                           'shorts': [nom('CCA.TO', 0.40), nom('ZZZ.TO', 0.35)]},
                'deepseek': {'longs': [], 'shorts': [nom('ATZ.TO', 0.50)]}}}


def test_each_nomination_carries_what_the_council_did_with_it():
    got = {(r['side'], r['ticker']): r['council'] for r in K.nominee_rows(sat_council(), 'claude')}
    assert got == {('LONG', 'ATZ.TO'): "the council's pick", ('LONG', 'SHOP.TO'): 'not on the table (16-position cap)',
                   ('SHORT', 'CCA.TO'): "the council's pick", ('SHORT', 'ZZZ.TO'): 'not on the table (16-position cap)'}
    assert [r['council'] for r in K.nominee_rows(sat_council(), 'deepseek')] == ['0 of 4 endorse, 3 object']
    assert K.nominee_rows(sat_council(), 'gemini') == [] and K.nominee_rows(None, 'claude') == []
    assert K.nominee_rows({'status': 'UNAVAILABLE'}, 'claude') == []      # an old or missing council


def test_the_council_section_names_only_its_own_splits():
    """10-13: the counted rule listed ATZ.TO as split while the council PICKED it."""
    counted = {'picks': [], 'split': ['ATZ.TO'], 'status': 'NO_AGREEMENT'}
    sec = K.top_two(sat_council(), counted, previous={})
    assert [p['ticker'] for p in sec['picks']] == ['ATZ.TO', 'CCA.TO'] and 'split' not in sec
    both = sat_council()
    both['tally']['rows'][1].update(consensus=False, split=True)          # both sides agreed
    both['tally']['rows'][0].update(consensus=False, split=True)
    both['picks'] = ['P3']
    assert K.top_two(both, counted, previous={})['split'] == ['ATZ.TO']


def desk_report(council_snap, legs=()):
    def desk(i, name, key):
        return {'id': i, 'source': name, 'evidence_key': key, 'legs': list(legs) if i == 'gemini' else []}
    return {'desks': [desk('claude', 'Claude', 'claude'), desk('deepseek', 'DeepSeek', 'opportunities'),
                      desk('gemini', 'Gemini', 'gemini')],
            'claude': {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []},
            'opportunities': {'status': 'UNAVAILABLE', 'reason': 'HTTP 503'},
            'gemini': {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': []},
            'council': council_snap}


def test_a_desk_that_selects_nothing_shows_its_nominations_in_the_email():
    import email_render as E
    text = '\n'.join(E.desk_sections(desk_report(sat_council())))
    claude = text.split('### 2')[0]
    assert 'No pick today' in claude and 'not a selection, not sized' in claude
    assert "| LONG ATZ.TO | 0.42 | below 141.86 | the council's pick |" in claude
    deepseek = text.split('### 2')[1].split('### 3')[0]
    assert 'Unavailable today' in deepseek and '| SHORT ATZ.TO | 0.50 | — | 0 of 4 endorse, 3 object |' in deepseek
    assert 'nominations' not in text.split('### 3')[1]                    # Gemini nominated nothing
    leg = {'status': 'SHADOW', 'side': 'LONG', 'ticker': 'AC.TO', 'baseline_shares': 10,
           'entry_reference': 10.0, 'confidence': 0.6, 'reason': 'r'}
    picked = desk_report(sat_council(), legs=[leg])
    picked['council']['nomination_picks']['gemini'] = {'longs': [nom('AC.TO')], 'shorts': []}
    assert 'nominations' not in '\n'.join(E.desk_sections(picked)).split('### 3')[1]   # it selected


def test_the_page_shows_them_too_labelled_forced():
    import report_page as R
    html = R._desk_sections(desk_report(sat_council()))
    assert html.count('Its nominations to the council') == 2
    assert 'not a selection, never sized' in html and 'ATZ.TO' in html


def test_every_nomination_is_recorded_apart_and_scored_on_its_own_row():
    import model_picks as M
    import primary_board as P
    rows = M.rows_from_report({'session': '2026-10-13', 'intraday': {'council': sat_council()}})
    got = sorted((r['model'], r['kind'], r['side'], r['ticker']) for r in rows)
    assert got == sorted([('claude', 'nominated', 'LONG', 'ATZ.TO'), ('claude', 'nominated', 'LONG', 'SHOP.TO'),
                          ('claude', 'nominated', 'SHORT', 'CCA.TO'), ('claude', 'nominated', 'SHORT', 'ZZZ.TO'),
                          ('deepseek', 'nominated', 'SHORT', 'ATZ.TO')])
    assert {r['prompt_version'] for r in rows} == {N.VERSION}
    assert next(r for r in rows if r['ticker'] == 'ATZ.TO' and r['side'] == 'LONG')['invalid_at'] == 141.86
    board = [r['source'] for r in P.leaderboard({})]
    assert not any('nominated' in s for s in board)                       # shown only once scored
    card = {'claude_nominated': {'picks': 4, 'hits': 2, 'rate': 0.5, 'mean_r_pct': 0.1, 'sessions': 1,
                                 'ci95': (0.15, 0.85)}}
    assert 'Claude (nominated, forced)' in [r['source'] for r in P.leaderboard(card)]


def test_the_review_scores_them_apart_and_the_lab_leaves_them_out():
    import daily_review as D
    import execution_lab as X
    picks = D.picks_of({'intraday': {'council': sat_council()}})
    assert {p['section'] for p in picks} == {'Nominated (forced)'} and len(picks) == 5
    row = {k: '' for k in X.FIELDS}
    rows = [{**row, 'session': '2026-10-13', 'model': 'claude', 'kind': 'nominated', 'side': 'LONG',
             'ticker': 'ATZ.TO', 'r': '1.0'},
            {**row, 'session': '2026-10-13', 'model': 'gemini', 'kind': 'selected', 'side': 'LONG',
             'ticker': 'AC.TO', 'r': '-0.5'}]
    text = '\n'.join(X.table(rows))
    assert '1 picks over 1 sessions' in text
