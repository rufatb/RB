"""Day-135c (PREREGISTER_day135c_risk.md): the last session's big movers.

R2 passed its registered test: after a move of >= 1 ATR a name swings about a
quarter wider the next session and leans neither way. Two things ship:
  * a caution line, always on, naming a pick on such a name (display only);
  * the switch, `council.SKIP_MOVERS`, ON from 2026-10-16 (owner): the Top 2
    passes over those positions, shows them, and records them as a shadow.
    Off (skip_movers=False) reproduces the frozen day-124 rule.
"""
import datetime as dt
import json

import pytest

import council as K
from tests.test_council import (FakeDeepSeek, FakeGemini, NOW, ONE_AND_A_RUNNER_UP, b, ballot,
                                council_snap, counted, jev_poster, snap_of, staged)  # noqa: F401
from tests.test_council_memory import sat  # noqa: F401

ALL_AGREE = {m: ballot(P1='ENDORSE 0.7', P2='ENDORSE 0.6', P3='ENDORSE 0.6', top=['P1', 'P2'])
             for m in ('Claude', 'DeepSeek', 'Gemini')}


def with_moves(snap, **moves):
    """`moves` as council.stage keeps them: {ticker: {'move_atr': m}}."""
    snap['moves'] = {t.replace('_', '.'): {'move_atr': m, 'atr_pct': 2.0} for t, m in moves.items()}
    return snap


def octfifteen():
    """10-15's shape: three positions agreed 4 of 4, every one a big mover."""
    t = [{'id': 'P1', 'ticker': 'CLS.TO', 'side': 'SHORT', 'lead': 'Gemini', 'reason': 'r',
          'invalid_at': 445.0, 'proposers': []},
         {'id': 'P2', 'ticker': 'CCO.TO', 'side': 'SHORT', 'lead': 'Claude', 'reason': 's',
          'invalid_at': 152.0, 'proposers': []},
         {'id': 'P3', 'ticker': 'HUT.TO', 'side': 'SHORT', 'lead': 'DeepSeek', 'reason': 'q',
          'invalid_at': 70.0, 'proposers': []}]
    finals = {m: ballot(P1='ENDORSE 0.8', P2='ENDORSE 0.7', P3='ENDORSE 0.6', top=['P1', 'P2'])
              for m in ('Claude', 'DeepSeek', 'Gemini', 'Jev')}
    tal = K.tally(t, finals)
    snap = {'status': 'READY', 'session': '2026-10-15', 'positions': t, 'tally': tal,
            'picks': [r['id'] for r in tal['rows'] if r['consensus']][:2]}
    return with_moves(snap, CLS_TO=-1.5062, CCO_TO=-1.4567, HUT_TO=-1.2956)


# ── the switch: on from 10-16; off is the frozen rule, unchanged ────────────

def test_the_switch_is_on_from_ten_sixteen_and_the_default_follows_it():
    assert K.SKIP_MOVERS is True and K.MOVER_ATR == 1.0
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=2.5, SU_TO=-1.2)
    assert K.top_two(snap, previous={}) == K.top_two(snap, previous={}, skip_movers=True)
    assert [p['ticker'] for p in K.top_two(snap, previous={})['picks']] == ['CNQ.TO']


def test_off_the_picks_do_not_move():
    plain = K.top_two(snap_of(ALL_AGREE), previous={}, skip_movers=False)
    moved = K.top_two(with_moves(snap_of(ALL_AGREE), AC_TO=2.5, SU_TO=-1.2), previous={},
                      skip_movers=False)
    assert [(p['side'], p['ticker']) for p in moved['picks']] == \
        [(p['side'], p['ticker']) for p in plain['picks']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert moved['rule_version'] == plain['rule_version'] == K.RULE_VERSION
    assert 'passed_movers' not in moved and moved['reason'] is None
    assert [p['move_atr'] for p in moved['picks']] == [2.5, -1.2]     # kept for the caution line


def test_a_council_without_moves_is_read_as_before_even_with_the_switch_on():
    """Every council sealed before day-135c has no `moves`: nothing is passed
    over, and its record keeps the rule it was decided under."""
    sec = K.top_two(snap_of(ALL_AGREE), previous={}, skip_movers=True)
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO', 'SU.TO'] and 'passed_movers' not in sec
    assert sec['rule_version'] == K.RULE_VERSION
    assert K.top_two(with_moves(snap_of(ALL_AGREE)), previous={}, skip_movers=True)['rule_version'] == \
        K.RULE_VERSION + '+' + K.MOVER_RULE                  # moves recorded, even none big


# ── switched on ─────────────────────────────────────────────────────────────

def test_on_a_big_mover_is_passed_over_and_the_next_agreed_position_takes_the_slot():
    import top_picks
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=1.5, SU_TO=0.4, CNQ_TO=-0.2)
    assert snap['picks'] == ['P1', 'P2']                  # the frozen rule chose AC.TO and SU.TO
    sec = K.top_two(snap, previous={}, skip_movers=True)
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('SHORT', 'SU.TO'), ('LONG', 'CNQ.TO')]
    assert sec['status'] == 'READY' and sec['reason'] is None
    assert [(x['side'], x['ticker'], x['move_atr']) for x in sec['passed_movers']] == [('LONG', 'AC.TO', 1.5)]
    assert sec['passed_movers'][0]['agreement'] == '3 of 3 endorse'
    assert sec['rule_version'] == K.RULE_VERSION + '+day135c-movers'
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert ("Passed over as the last session's big movers (the big-mover rule, day-135c): "
            "LONG AC.TO (a rise of 1.5 normal days). Recorded as a shadow, never sized.") in text
    assert '⚠ ' + "The last session's big movers" not in text      # no pick is a mover now


def test_the_entry_check_still_applies_after_the_movers_are_passed_over():
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=1.5)
    sec = K.top_two(snap, previous={}, skip_movers=True, prices={'AC.TO': 31.0, 'SU.TO': 51.0, 'CNQ.TO': 20.0})
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO'] and sec['void_at_entry'] == ['SHORT SU.TO']
    assert sec['rule_version'] == K.RULE_VERSION + '+day135c-movers+day120-entry'
    assert sec['reason'].startswith('One position the council chose was already past')


def test_ten_fifteen_every_agreed_position_was_a_mover_so_nothing_to_act_on():
    import council_flash
    import email_render as E
    import top_picks
    snap = octfifteen()
    off = K.top_two(snap, previous={}, skip_movers=False)
    assert [p['ticker'] for p in off['picks']] == ['CLS.TO', 'CCO.TO']    # what the morning printed
    sec = K.top_two(snap, previous={}, skip_movers=True)
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT' and sec['runner_up'] is None
    assert [x['ticker'] for x in sec['passed_movers']] == ['CLS.TO', 'CCO.TO', 'HUT.TO']
    # listed once, as passed over — never again as a runner-up that "cannot stand"
    assert sec['runner_up_note'] == ('No runner-up: every other position drew at least as many '
                                     'objections as endorsements.')
    assert sec['reason'] == ("Every position the council agreed on was one of the last session's big "
                             "movers, passed over by the big-mover rule (day-135c), so there is "
                             "nothing here to act on.")
    concise = top_picks.table(sec, concise=True)
    assert ("The council agreed only on the last session's big movers — passed over, nothing to act "
            "on.") in concise
    assert 'No consensus' not in '\n'.join(concise)                     # there WAS consensus
    assert sec['reason'] in top_picks.table(sec)                         # the full report
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert ("Top 2 today: the council agreed only on the last session&#x27;s big movers — passed "
            "over, nothing to act on") in html
    assert council_flash.subject('2026-10-15', sec) == (
        'RB Council Flash — 2026-10-15 — agreed only on big movers, passed over — nothing to act on')


def test_on_a_day_the_council_chose_nothing_the_switch_chooses_nothing():
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=1.5)
    snap['picks'], snap['status'] = [], 'NO_CONSENSUS'
    on = K.top_two(snap, previous={}, skip_movers=True)
    off = K.top_two(snap, previous={}, skip_movers=False)
    assert on['picks'] == off['picks'] == [] and on['status'] == off['status'] == 'NO_AGREEMENT'
    assert 'passed_movers' not in on


def test_on_a_big_mover_is_never_the_runner_up_and_the_note_says_why():
    snap = with_moves(snap_of(ONE_AND_A_RUNNER_UP), SU_TO=-1.8)
    assert K.top_two(snap, previous={}, skip_movers=False)['runner_up']['ticker'] == 'SU.TO'   # off
    sec = K.top_two(snap, previous={}, skip_movers=True)
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO'] and sec['runner_up'] is None
    assert sec['runner_up_note'] == ("No runner-up: the other positions with more endorsements than "
                                     "objections cannot stand — SHORT SU.TO (one of the last "
                                     "session's big movers).")
    assert 'passed_movers' not in sec            # it was never agreed, so it was never passed over


def test_one_normal_day_either_way_is_a_mover_and_an_unknown_move_is_not():
    for m, mover in ((1.0, True), (-1.0, True), (0.99, False), (-0.99, False), (None, False)):
        snap = snap_of(ALL_AGREE)
        snap['moves'] = {'AC.TO': {'move_atr': m}}
        sec = K.top_two(snap, previous={}, skip_movers=True)
        assert ('AC.TO' in [x['ticker'] for x in sec.get('passed_movers') or []]) is mover, m
        assert sec['rule_version'] == K.RULE_VERSION + '+' + K.MOVER_RULE
        assert K.is_mover({'move_atr': m}) is mover


def test_the_flash_and_the_open_check_read_the_same_switch(monkeypatch):
    monkeypatch.setattr(K, 'SKIP_MOVERS', True)
    sec = K.top_two(octfifteen(), previous={})
    assert sec['picks'] == [] and len(sec['passed_movers']) == 3
    assert K.decide(counted(), octfifteen())['passed_movers'] == sec['passed_movers']


# ── the caution line (always on, display only) ──────────────────────────────

MOVER_TAIL = ('After a move that size a name swings about a quarter wider the next session '
              '(2016–2026, 49,295 cases), and neither following the move nor betting on a bounce '
              'has had an edge.')


def test_the_caution_names_each_pick_on_a_big_mover_and_which_way_it_leans():
    import top_picks
    sec = K.top_two(octfifteen(), previous={}, skip_movers=False)
    line = top_picks.mover_line(sec)
    assert line == ("⚠ The last session's big movers: SHORT CLS.TO follows a fall of 1.5 normal days · "
                    "SHORT CCO.TO follows a fall of 1.5 normal days. " + MOVER_TAIL)
    text = top_picks.table(sec, concise=True)
    assert text.index(line) == text.index(top_picks.direction_line(sec)) + 1    # right under the picks
    # a bounce and a reversal are named as such
    assert K.mover_phrase({'side': 'LONG', 'ticker': 'X.TO', 'move_atr': -1.2}) == \
        'LONG X.TO bets on a bounce after a fall of 1.2 normal days'
    assert K.mover_phrase({'side': 'SHORT', 'ticker': 'Y.TO', 'move_atr': 2.04}) == \
        'SHORT Y.TO bets on a reversal after a rise of 2.0 normal days'


def test_no_caution_without_a_mover_pick_and_a_runner_up_never_triggers_it():
    import top_picks
    assert top_picks.mover_line(K.top_two(snap_of(ALL_AGREE), previous={})) is None   # no moves known
    sec = K.top_two(with_moves(snap_of(ONE_AND_A_RUNNER_UP), AC_TO=0.3, SU_TO=-1.8), previous={},
                    skip_movers=False)
    assert sec['runner_up']['ticker'] == 'SU.TO' and sec['runner_up']['move_atr'] == -1.8
    assert top_picks.mover_line(sec) is None
    assert top_picks.mover_line(None) is None and top_picks.mover_line({'picks': []}) is None


def test_the_caution_is_in_the_email_hero_and_body_the_flash_and_the_page(monkeypatch):
    import council_flash
    import email_render as E
    import report_page
    import top_picks
    monkeypatch.setattr(K, 'SKIP_MOVERS', False)           # the caution shows when a mover is picked
    sec = K.top_two(octfifteen(), previous={})
    line = top_picks.mover_line(sec)
    esc = E.full.escape(line)
    hero = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert esc in hero and E.full.escape(top_picks.direction_line(sec)) in hero
    body = E._body_blocks('\n'.join(top_picks.table(sec, concise=True)))
    assert E.caution_html(line) in body                                # bordered, never a quiet paragraph
    council = {**octfifteen(), 'finished_at': '2026-10-15T08:58:00-04:00'}
    _, text, html = council_flash.compose(council, dt.datetime(2026, 10, 15, 9, 0, tzinfo=K.ET))
    assert line in text and html.count(esc) >= 2                       # hero and table
    page = report_page._top_two_section({'top_two': sec})
    assert f'<li class="g-caution">{report_page.escape(line)}</li>' in page
    assert page.count(report_page.escape(line)) == 1                   # once, above the table


# ── the record ──────────────────────────────────────────────────────────────

def test_passed_movers_are_recorded_as_a_shadow_never_top2_pooled_or_on_the_board(monkeypatch):
    import execution_lab
    import model_picks
    import primary_board
    sec = K.top_two(with_moves(snap_of(ALL_AGREE), AC_TO=1.5), previous={}, skip_movers=True)
    rows = model_picks.rows_from_report({'session': '2026-10-05', 'intraday': {'top_two': sec}})
    got = sorted((r['model'], r['side'], r['ticker'], r['prompt_version']) for r in rows)
    rule = K.RULE_VERSION + '+day135c-movers'
    assert got == [('top2', 'LONG', 'CNQ.TO', rule), ('top2', 'SHORT', 'SU.TO', rule),
                   ('top2mover', 'LONG', 'AC.TO', rule)]
    assert 'top2mover' in model_picks.POOLED_EXCLUDED
    assert not any('top2mover' in key for key, _ in primary_board.LEADERBOARD)
    seen = []                                      # what the lab's "Model picks" pool is built from
    monkeypatch.setattr(execution_lab, '_unique', lambda rs: seen.extend(rs) or [])
    execution_lab.table([{**r, 'kind': 'pick', 'r': '0.5'} for r in rows])
    assert sorted(r['ticker'] for r in seen) == ['CNQ.TO', 'SU.TO']


def test_the_review_scores_passed_movers_apart_and_keeps_them_out_of_the_lessons():
    import daily_review
    sec = K.top_two(with_moves(snap_of(ALL_AGREE), AC_TO=1.5), previous={}, skip_movers=True)
    got = [(x['section'], x['ticker']) for x in daily_review.picks_of({'intraday': {'top_two': sec}})]
    assert ('Passed over (big mover)', 'AC.TO') in got and ('Top 2', 'AC.TO') not in got
    row = {'section': 'Passed over (big mover)', 'session': '2026-10-05', 'ticker': 'AC.TO',
           'side': 'LONG', 'r_pct': 5.0, 'gap': 1.0, 'first15': 1.0}
    learn = daily_review.lessons([row])
    assert all(q['yes'] == {'n': 0} and q['no'] == {'n': 0} for q in learn[:5])


def test_stage_keeps_each_names_move_beside_the_decision(staged, monkeypatch):
    monkeypatch.setattr(K, 'evidence_rows', lambda root, now, tickers: [
        {'ticker': t, 'r0': 1.0, 'move_atr': {'AC.TO': 1.7}.get(t, 0.2), 'atr_pct': 2.5}
        for t in sorted(tickers)])
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6'), b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6')])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8'), b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75')])
    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm},
                  jev_poster=jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.3, 'NONE': 0.1}),
                  wait=False, clock=lambda: NOW)
    saved = json.loads((staged/K.SNAPSHOT).read_text())
    assert saved['moves'] == out['moves'] == {'AC.TO': {'move_atr': 1.7, 'atr_pct': 2.5},
                                              'CNQ.TO': {'move_atr': 0.2, 'atr_pct': 2.5},
                                              'SU.TO': {'move_atr': 0.2, 'atr_pct': 2.5}}
    # the members never see a "moves" block: their rows already carry move_atr
    assert all('moves' not in json.dumps(seen[1]) for seen in gm.seen)
    assert out['picks'] == ['P1', 'P3']                   # the frozen rule is unchanged
    sec = K.top_two(saved, previous={}, skip_movers=True)
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['passed_movers'][0]['ticker'] == 'AC.TO'


def test_the_memory_council_follows_the_same_switch(monkeypatch):
    import council_memory
    snap = {**with_moves(snap_of(ALL_AGREE), AC_TO=1.5), 'variant': 'memory'}
    monkeypatch.setattr(K, 'SKIP_MOVERS', False)
    assert [p['ticker'] for p in council_memory.section(snap)['picks']] == ['AC.TO', 'SU.TO']
    assert council_memory.section(snap)['rule_version'] == council_memory.RULE_VERSION
    monkeypatch.setattr(K, 'SKIP_MOVERS', True)
    sec = council_memory.section(snap)
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO', 'CNQ.TO'] and sec['shadow']
    assert sec['rule_version'] == council_memory.RULE_VERSION + '+day135c-movers'


def test_the_memory_council_carries_the_live_councils_moves(sat):
    from tests import test_council_memory as TM
    import council_memory
    live = json.loads((sat/K.SNAPSHOT).read_text())
    live['moves'] = {'AC.TO': {'move_atr': 1.5, 'atr_pct': 2.0}}
    (sat/K.SNAPSHOT).write_text(json.dumps(live))
    ds = TM.FakeDeepSeek([TM.b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.7')] * 2)
    gm = TM.FakeGemini([TM.b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8')] * 2)
    out = council_memory.stage(sat, now=TM.NOW, clock=lambda: TM.NOW, clients={'deepseek': ds, 'gemini': gm},
                               jev_poster=TM.jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.3, 'NONE': 0.2}),
                               claude_post=TM.claude_post(TM.b('ENDORSE 0.66', 'OPPOSE 0.8', 'ENDORSE 0.6')),
                               picks=TM.LEDGER, lab=TM.LAB, sectors={})
    assert out['moves'] == live['moves']
    assert json.loads((sat/council_memory.SNAPSHOT).read_text())['moves'] == live['moves']
