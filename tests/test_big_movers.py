"""Day-135c (PREREGISTER_day135c_risk.md): the last session's big movers.

R2 passed its registered test: after a move of >= 1 ATR a name swings about a
quarter wider the next session and leans neither way. Two things ship:
  * a caution line, always on, naming a pick on such a name (display only);
  * the switch, `council.SKIP_MOVERS`, ON from 2026-10-16 (owner): the Top 2
    is the council's picks minus those positions, shown and recorded as a
    shadow. Nothing is added in their place (day-135d, remove-only): the rule
    only ever takes a trade away. Off (skip_movers=False) reproduces the
    frozen day-124 rule.
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
    # The rule as it ran 10-19 → 10-30: tests/conftest.py pins it ON for the suite.
    # Production is OFF from 2026-11-02 (day-144, tests/test_claude_leads.py).
    assert K.SKIP_MOVERS is True and K.MOVER_ATR == 1.0
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=2.5, SU_TO=-1.2)
    assert K.top_two(snap, previous={}) == K.top_two(snap, previous={}, skip_movers=True)
    sec = K.top_two(snap, previous={})
    assert sec['picks'] == [] and [x['ticker'] for x in sec['passed_movers']] == ['AC.TO', 'SU.TO']
    assert sec['runner_up']['ticker'] == 'CNQ.TO'         # shown, labelled, never a pick


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

def test_on_a_big_mover_is_passed_over_and_nothing_takes_its_slot():
    """Remove-only (day-135d): on 10-16 the refill made SHORT CVE.TO a pick, and
    it lost 1.39%. The next agreed position is now the labelled runner-up."""
    import council_flash
    import email_render as E
    import top_picks
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=1.5, SU_TO=0.4, CNQ_TO=-0.2)
    assert snap['picks'] == ['P1', 'P2']                  # the frozen rule chose AC.TO and SU.TO
    sec = K.top_two(snap, previous={}, skip_movers=True)
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('SHORT', 'SU.TO')]
    assert sec['status'] == 'PARTIAL'
    assert sec['reason'] == ("The council's other pick was one of the last session's big movers, "
                             "passed over by the big-mover rule (day-135c); the second slot is left empty.")
    ru = sec['runner_up']
    assert (ru['side'], ru['ticker'], ru['label']) == ('LONG', 'CNQ.TO', 'agreed, ranked below the picks')
    assert [(x['side'], x['ticker'], x['move_atr']) for x in sec['passed_movers']] == [('LONG', 'AC.TO', 1.5)]
    assert sec['passed_movers'][0]['agreement'] == '3 of 3 endorse'
    assert sec['rule_version'] == K.RULE_VERSION + '+day135c-movers'
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert ("Passed over as the last session's big movers (the big-mover rule, day-135c): "
            "LONG AC.TO (a rise of 1.5 normal days). Recorded as a shadow, never sized.") in text
    assert 'Runner-up — agreed, ranked below the picks, not a council pick: LONG CNQ.TO' in text
    assert '⚠ ' + "The last session's big movers" not in text      # no pick is a mover now
    assert council_flash.subject('2026-10-05', sec) == (
        'RB Council Flash — 2026-10-05 — SHORT SU.TO (3 of 3 endorse) · runner-up, agreed, ranked '
        'below the picks: LONG CNQ.TO')
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert 'Top 2 today: SHORT SU.TO (3 of 3 endorse) · runner-up, agreed, ranked below the picks: LONG CNQ.TO' in html


def test_ten_sixteen_both_picks_were_movers_so_nothing_is_picked_and_the_runner_up_is_labelled():
    """10-16's shape: LONG AC.TO and LONG SU.TO rose 2.5 ATR (L and WCN), and the
    council's third agreed position (SHORT CVE.TO) was no mover. The refill made
    it a pick; remove-only leaves it the runner-up."""
    import council_flash
    import email_render as E
    import top_picks
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=2.5, SU_TO=2.4, CNQ_TO=0.3)
    sec = K.top_two(snap, previous={}, skip_movers=True)
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT'
    assert [x['ticker'] for x in sec['passed_movers']] == ['AC.TO', 'SU.TO']
    assert sec['runner_up']['ticker'] == 'CNQ.TO'
    assert sec['reason'] == ("The council's picks were the last session's big movers, passed over by "
                             "the big-mover rule (day-135c), so there is nothing here to act on.")
    concise = top_picks.table(sec, concise=True)
    assert "The council's picks were the last session's big movers, passed over — no council pick." in concise
    assert council_flash.subject('2026-10-16', sec) == (
        'RB Council Flash — 2026-10-16 — big movers passed over — no council pick · runner-up, '
        'agreed, ranked below the picks: LONG CNQ.TO')
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert ("Top 2 today: the council&#x27;s picks were the last session&#x27;s big movers, passed over — "
            "no council pick · runner-up, agreed, ranked below the picks: LONG CNQ.TO (3 of 3 endorse), "
            "not a pick") in html


def test_the_entry_check_still_applies_after_the_movers_are_passed_over():
    import top_picks
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=1.5)
    sec = K.top_two(snap, previous={}, skip_movers=True, prices={'AC.TO': 31.0, 'SU.TO': 51.0, 'CNQ.TO': 20.0})
    assert sec['picks'] == [] and sec['void_at_entry'] == ['SHORT SU.TO']
    assert [x['ticker'] for x in sec['passed_movers']] == ['AC.TO']
    assert sec['rule_version'] == K.RULE_VERSION + '+day135c-movers+day120-entry'
    assert sec['reason'] == ("One council pick was one of the last session's big movers, passed over by "
                             "the big-mover rule (day-135c), and the other was already past its own "
                             "\"wrong if\" at 09:46, so there is nothing here to act on.")
    assert ("One council pick was one of the last session's big movers, passed over, and the other was "
            "already past its own \"wrong if\" at 09:46 — no council pick.") in top_picks.table(sec, concise=True)


def test_ten_fifteen_every_agreed_position_was_a_mover_so_nothing_to_act_on():
    import council_flash
    import email_render as E
    import top_picks
    snap = octfifteen()
    off = K.top_two(snap, previous={}, skip_movers=False)
    assert [p['ticker'] for p in off['picks']] == ['CLS.TO', 'CCO.TO']    # what the morning printed
    sec = K.top_two(snap, previous={}, skip_movers=True)
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT' and sec['runner_up'] is None
    # the council's two picks are passed over; HUT.TO was never a pick, so it is
    # not recorded as one, and as a mover it cannot be the runner-up
    assert [x['ticker'] for x in sec['passed_movers']] == ['CLS.TO', 'CCO.TO']
    assert sec['runner_up_note'] == ("No runner-up: the other positions with more endorsements than "
                                     "objections cannot stand — SHORT HUT.TO (one of the last "
                                     "session's big movers).")
    assert sec['reason'] == ("The council's picks were the last session's big movers, passed over by "
                             "the big-mover rule (day-135c), so there is nothing here to act on.")
    concise = top_picks.table(sec, concise=True)
    assert "The council's picks were the last session's big movers, passed over — nothing to act on." in concise
    assert 'No consensus' not in '\n'.join(concise)                     # there WAS consensus
    assert sec['reason'] in top_picks.table(sec)                         # the full report
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert ("Top 2 today: the council&#x27;s picks were the last session&#x27;s big movers, passed "
            "over — nothing to act on") in html
    assert council_flash.subject('2026-10-15', sec) == (
        'RB Council Flash — 2026-10-15 — big movers passed over — nothing to act on')
    one = {**snap, 'picks': ['P1']}                       # a council that picked one mover
    sec = K.top_two(one, previous={}, skip_movers=True)
    assert sec['reason'] == ("The council's pick was one of the last session's big movers, passed over "
                             "by the big-mover rule (day-135c), so there is nothing here to act on.")
    assert council_flash.subject('2026-10-15', sec) == (
        'RB Council Flash — 2026-10-15 — a big mover passed over — nothing to act on')


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
    assert sec['picks'] == [] and len(sec['passed_movers']) == 2
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
    assert got == [('top2', 'SHORT', 'SU.TO', rule), ('top2mover', 'LONG', 'AC.TO', rule),
                   ('top2runner', 'LONG', 'CNQ.TO', rule)]
    assert 'top2mover' in model_picks.POOLED_EXCLUDED
    assert not any('top2mover' in key for key, _ in primary_board.LEADERBOARD)
    seen = []                                      # what the lab's "Model picks" pool is built from
    monkeypatch.setattr(execution_lab, '_unique', lambda rs: seen.extend(rs) or [])
    execution_lab.table([{**r, 'kind': 'pick', 'r': '0.5'} for r in rows])
    assert 'AC.TO' not in [r['ticker'] for r in seen] and 'SU.TO' in [r['ticker'] for r in seen]


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
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['shadow']
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


def test_the_open_check_says_there_is_no_council_pick_when_the_movers_were_passed_over():
    """10-16 with the switch on: only the runner-up is left at 09:31, and the
    open check must not read like a pick to trade."""
    import council_flash as F
    snap = with_moves(snap_of(ALL_AGREE), AC_TO=2.5, SU_TO=2.4, CNQ_TO=0.3)
    snap['positions'][2]['invalid_at'] = 19.0             # LONG CNQ.TO: wrong if below 19
    sec = K.top_two(snap, previous={}, skip_movers=True)
    now = dt.datetime(2026, 10, 5, 9, 31, tzinfo=K.ET)
    quote = lambda sym: {'price': 20.0, 'open': 20.0, 'previousClose': 20.0, 'timestamp': now.timestamp()}
    rows = F.check_open(snap, now, quote=quote, atr={})
    assert [(r['ticker'], bool(r.get('runner_up'))) for r in rows] == [('CNQ.TO', True)]
    subj, text, _ = F.compose_open(snap, rows, now, section=sec)
    assert subj == 'RB Open Check — 2026-10-05 — no council pick · runner-up LONG CNQ.TO STILL VALID'
    assert ("No council pick today: the council's picks were the last session's big movers, passed "
            "over. The runner-up is checked because it is shown; it is not a pick.") in text


def test_the_report_subject_names_the_rule_not_an_empty_morning():
    import prepare_delivery
    sec = K.top_two(octfifteen(), previous={}, skip_movers=True)
    report = {'session': '2026-10-15', 'report_status': 'ON_TIME',
              'intraday': {'top_two': sec, 'desks': [{'legs': []}]}}
    assert prepare_delivery.subject_state(report) == '⛔ NO COUNCIL PICK — big movers passed over — '
    assert prepare_delivery.subject(report) == \
        'RB Daily Report — 2026-10-15 — ⛔ NO COUNCIL PICK — big movers passed over'
    report['intraday']['top_two'] = K.top_two(octfifteen(), previous={}, skip_movers=False)
    assert prepare_delivery.subject_state(report).startswith('COUNCIL TOP 2 ONLY — 2 positions')


# ── the counted fallback: a morning the council did not sit (day-135d) ──────

NOT_SAT = {'status': 'UNAVAILABLE', 'reason': 'fewer than two members answered'}


def two_counted():
    c = counted()
    c['picks'] = [dict(c['picks'][0]), {**c['picks'][0], 'ticker': 'SU.TO', 'side': 'SHORT'}]
    c['status'], c['rule_version'] = 'READY', 'day121-agreement+day120-entry'
    return c


def test_the_counted_fallback_passes_over_big_movers_and_adds_nothing():
    import top_picks
    c = two_counted()
    sec = K.decide(c, NOT_SAT, moves=({'AC.TO': {'move_atr': 2.4}, 'SU.TO': {'move_atr': -0.3}}, None))
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['status'] == 'PARTIAL'
    assert [(x['ticker'], x['move_atr']) for x in sec['passed_movers']] == [('AC.TO', 2.4)]
    assert sec['rule_version'] == 'day121-agreement+day135c-movers+day120-entry'
    assert sec['reason'].startswith("The other agreed name was one of the last session's big movers")
    assert [p['ticker'] for p in c['picks']] == ['AC.TO', 'SU.TO']      # the top2count shadow is untouched
    assert all('move_atr' not in p for p in c['picks'])
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert 'The council did not sit today (fewer than two members answered)' in text
    assert "Passed over as the last session's big movers (the big-mover rule, day-135c): LONG AC.TO" in text
    both = K.decide(c, NOT_SAT, moves=({'AC.TO': {'move_atr': 2.4}, 'SU.TO': {'move_atr': -1.1}}, None))
    assert both['picks'] == [] and both['status'] == 'NO_AGREEMENT'
    assert ("The agreed names were the last session's big movers, passed over — nothing to act on."
            in top_picks.table(both, concise=True))


def test_off_the_counted_fallback_keeps_its_picks_and_gains_the_caution():
    import top_picks
    sec = K.counted_movers(two_counted(), {'AC.TO': {'move_atr': 2.4}}, skip_movers=False)
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO', 'SU.TO'] and 'passed_movers' not in sec
    assert sec['rule_version'] == 'day121-agreement+day120-entry'
    assert top_picks.mover_line(sec).startswith("⚠ The last session's big movers: LONG AC.TO follows a rise")


def test_without_moves_the_fallback_says_the_rule_was_not_applied(tmp_path):
    import top_picks
    moves = K.brief_moves(tmp_path, NOW)
    assert moves == ({}, 'CLAUDE_BRIEF_NOT_STAGED')
    sec = K.decide(two_counted(), NOT_SAT, moves=moves)
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO', 'SU.TO']
    assert sec['mover_note'] == 'The big-mover rule (day-135c) could not be applied: CLAUDE_BRIEF_NOT_STAGED.'
    assert sec['mover_note'] in top_picks.table(sec, concise=True)


def test_the_fallback_prefers_the_moves_the_council_recorded():
    sec = K.decide(two_counted(), {**NOT_SAT, 'moves': {'SU.TO': {'move_atr': -1.4}}},
                   moves=({'AC.TO': {'move_atr': 3.0}}, None))
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO'] and sec['passed_movers'][0]['ticker'] == 'SU.TO'


def test_brief_moves_reads_the_rows_every_desk_read(monkeypatch):
    import claude_opportunities as C
    monkeypatch.setattr(C, 'read_brief', lambda root, now: {'payload': {'candidates': [
        {'ticker': 'AC.TO', 'move_atr': 1.2, 'atr_pct': 2.0}, {'ticker': 'SU.TO', 'move_atr': None}]}})
    assert K.brief_moves('x', NOW) == ({'AC.TO': {'move_atr': 1.2, 'atr_pct': 2.0},
                                         'SU.TO': {'move_atr': None, 'atr_pct': None}}, None)
