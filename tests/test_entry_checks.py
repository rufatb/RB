"""Day-120 entry checks (PREREGISTER_day120_entry_checks.md): E1 void at entry,
E2 conflict — on the Top 2 and the debate's final only."""
import debate
import entry_checks as E
import top_picks


def test_check_is_directional_and_never_guesses():
    assert E.check('LONG', 10.0, 9.9) == 'VOID' and E.check('LONG', 10.0, 10.1) == 'OK'
    assert E.check('SHORT', 26.63, 26.78) == 'VOID' and E.check('SHORT', 26.63, 26.5) == 'OK'
    assert E.check('LONG', None, 9.0) == 'NOT CHECKED'
    assert E.check('LONG', 10.0, None) == 'NOT CHECKED'


def test_marks_use_only_validated_quotes():
    q = {'A.TO': {'status': 'CORROBORATED', 'mark': 1.5}, 'B.TO': {'status': 'OK', 'mark': 2},
         'C.TO': {'status': 'STALE', 'mark': 3}, 'D.TO': {'status': 'OK', 'mark': None}}
    assert E.marks(q) == {'A.TO': 1.5, 'B.TO': 2.0}


def test_conflicted():
    assert E.conflicted([('A', 'LONG'), ('A', 'SHORT'), ('B', 'LONG')]) == {'A'}


def snap(longs=(), shorts=()):
    return {'status': 'READY', 'longs': list(longs), 'shorts': list(shorts)}


CLAUDE = snap(longs=[{'ticker': 'BCE.TO', 'confidence': 0.52}],
              shorts=[{'ticker': 'AC.TO', 'confidence': 0.60, 'invalid_at': 26.63}])
DEEPSEEK = snap(longs=[{'ticker': 'HBM.TO', 'confidence': 0.52, 'invalid_at': 35.78},
                       {'ticker': 'RY.TO', 'confidence': 0.55}],
                shorts=[{'ticker': 'BCE.TO', 'confidence': 0.52, 'invalid_at': 29.69}])


def test_top2_passes_over_a_void_pick_and_says_so():
    claude = snap(longs=[{'ticker': 'HBM.TO', 'confidence': 0.6}],
                  shorts=[{'ticker': 'AC.TO', 'confidence': 0.60, 'invalid_at': 26.63}])
    deepseek = snap(longs=[{'ticker': 'HBM.TO', 'confidence': 0.52, 'invalid_at': 35.78}],
                    shorts=[{'ticker': 'AC.TO', 'confidence': 0.55, 'invalid_at': 26.9}])
    before = top_picks.select(claude, deepseek, None)
    assert [p['ticker'] for p in before['picks']] == ['AC.TO', 'HBM.TO']      # both agreed
    after = top_picks.select(claude, deepseek, None, prices={'AC.TO': 26.78, 'HBM.TO': 38.13})
    assert [p['ticker'] for p in after['picks']] == ['HBM.TO']              # AC void: left out
    assert after['void_at_entry'] == ['SHORT AC.TO']
    assert after['rule_version'] == 'day121-agreement+' + E.RULE_VERSION
    assert before['rule_version'] == 'day121-agreement'                      # picks-only / late
    assert 'Passed over at 09:46' in '\n'.join(top_picks.table(after))


def debate_section(final, proposals):
    return {'status': 'READY', 'final': final, 'proposals': proposals, 'rulings': [],
            'prompt_version': 'day119-debate-v1'}


def fin(t, side):
    return {'ticker': t, 'side': side, 'proposers': [{'model': 'deepseek'}], 'jev_probability': 0.9,
            'jev_none': 0.1, 'ruling': {'verdict': 'KEEP', 'for': '', 'against': ''}}


def test_debate_drops_void_and_conflicted_finals_never_pads():
    sec = debate_section([fin('HBM.TO', 'LONG'), fin('AC.TO', 'SHORT'), fin('BCE.TO', 'SHORT')],
                         [{'ticker': 'BCE.TO', 'side': 'LONG'}, {'ticker': 'BCE.TO', 'side': 'SHORT'},
                          {'ticker': 'HBM.TO', 'side': 'LONG'}, {'ticker': 'AC.TO', 'side': 'SHORT'}])
    debate.entry_filter(sec, {'HBM.TO': 38.13, 'AC.TO': 26.78, 'BCE.TO': 29.0},
                        debate.levels(CLAUDE, DEEPSEEK))
    assert [f['ticker'] for f in sec['final']] == ['HBM.TO']
    why = {d['ticker']: d['dropped_because'] for d in sec['dropped_at_entry']}
    assert why['BCE.TO'] == 'proposed on both sides' and 'already past' in why['AC.TO']
    text = '\n'.join(debate.lines(sec))
    assert 'Dropped at entry (09:46)' in text and 'SHORT AC.TO' in text


def test_debate_without_quotes_or_levels_keeps_everything():
    sec = debate_section([fin('RY.TO', 'LONG')], [{'ticker': 'RY.TO', 'side': 'LONG'}])
    debate.entry_filter(sec, {}, {})
    assert [f['ticker'] for f in sec['final']] == ['RY.TO'] and sec['final'][0]['entry_check'] == 'NOT CHECKED'


def test_recorded_under_the_new_rule_version():
    import model_picks
    intra = {'top_two': {'picks': [{'ticker': 'RY.TO', 'side': 'LONG', 'agreement': '1 of 3'}],
                         'rule_version': E.RULE_VERSION},
             'debate': {'final': [{'ticker': 'HBM.TO', 'side': 'LONG', 'jev_probability': 0.9}],
                        'prompt_version': 'day119-debate-v1', 'entry_rule': E.RULE_VERSION}}
    rows = model_picks.rows_from_report({'session': '2026-09-30', 'intraday': intra})
    pv = {r['model']: r['prompt_version'] for r in rows}
    assert pv == {'top2': 'day120-entry', 'debate': 'day119-debate-v1+day120-entry'}


def test_agreement_on_one_release_is_labelled_not_independent():
    claude = snap(longs=[{'ticker': 'TD.TO', 'confidence': 0.53}])
    deepseek = snap(longs=[{'ticker': 'TD.TO', 'confidence': 0.55}])
    sec = top_picks.select(claude, deepseek, None)
    td = next(p for p in sec['picks'] if p['ticker'] == 'TD.TO')
    assert 'not independent' not in '\n'.join(top_picks.table(sec))
    td['wire'] = {'at': '08:30', 'title': 'TD buyback'}
    assert 'all saw the same release, not independent' in '\n'.join(top_picks.table(sec))
