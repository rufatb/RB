"""Day-137 H3 (PREREGISTER_day137_council.md): the morning's widest-swinging names.

The registered test passed as a SIZE rule: names at or above the 90th
percentile of the list's ATR % swing 2.46x the rest from 09:45 to the close
and lean neither way. `council.SKIP_WILD` is ON from 2026-10-22 (owner,
10-21): the Top 2 is the council's picks minus those positions, nothing added,
shown and recorded as a shadow (`top2wild`). Off (skip_wild=False) is the
day-135d rule, unchanged.
"""
import json

import council as K
from tests.test_big_movers import ALL_AGREE, NOT_SAT, octfifteen, two_counted, with_moves
from tests.test_council import (FakeDeepSeek, FakeGemini, NOW, b, jev_poster, snap_of,  # noqa: F401
                                staged)


def with_wild(snap, cut=5.0, **atrs):
    """A council that recorded the morning's cut, and each name's ATR %."""
    snap = with_moves(snap)
    for t, a in atrs.items():
        snap['moves'][t.replace('_', '.')] = {'move_atr': 0.1, 'atr_pct': a}
    snap['wild'] = {'pctile': 90, 'atr_pct': cut, 'names': 150}
    return snap


def test_the_switch_is_on_and_the_cut_is_the_ninetieth_percentile():
    assert K.SKIP_WILD is True and K.WILD_PCTILE == 90 and K.WILD_RULE == 'day137-wild'
    rows = [{'ticker': 'N%d' % i, 'atr_pct': float(i)} for i in range(1, 21)]
    assert K.wild_cut(rows) == {'pctile': 90, 'atr_pct': 18.1, 'names': 20}     # numpy's linear rule
    assert K.wild_cut(rows[:19]) is None                                         # too few to cut
    assert K.wild_cut(rows + [{'ticker': 'X', 'atr_pct': None}])['names'] == 20


def test_a_wild_pick_is_passed_over_and_nothing_takes_its_slot():
    import top_picks
    snap = with_wild(snap_of(ALL_AGREE), cut=5.06, AC_TO=7.3, SU_TO=2.5, CNQ_TO=2.0)
    assert snap['picks'] == ['P1', 'P2']                  # the frozen rule chose AC.TO and SU.TO
    sec = K.top_two(snap, previous={})
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('SHORT', 'SU.TO')]
    assert sec['status'] == 'PARTIAL'
    assert sec['reason'] == ("The council's other pick was one of the morning's widest-swinging names, "
                             "passed over by the high-volatility rule (day-137); the second slot is "
                             "left empty.")
    assert [(x['ticker'], x['atr_pct'], x['wild_cut']) for x in sec['passed_wild']] == [('AC.TO', 7.3, 5.06)]
    assert sec['runner_up']['ticker'] == 'CNQ.TO'         # labelled, never a pick
    assert sec['rule_version'] == K.RULE_VERSION + '+day135c-movers+day137-wild'
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert ("Passed over as one of the morning's widest-swinging names (the high-volatility rule, "
            "day-137): LONG AC.TO (a normal day of 7.3%; the morning's cut 5.1%). Recorded as a "
            "shadow, never sized.") in text


def test_off_or_without_a_recorded_cut_nothing_changes():
    snap = with_wild(snap_of(ALL_AGREE), AC_TO=7.3)
    off = K.top_two(snap, previous={}, skip_wild=False)
    assert [p['ticker'] for p in off['picks']] == ['AC.TO', 'SU.TO'] and 'passed_wild' not in off
    assert off['rule_version'] == K.RULE_VERSION + '+day135c-movers'
    old = with_moves(snap_of(ALL_AGREE))                 # sealed before day-137: no cut
    old['moves']['AC.TO'] = {'move_atr': 0.1, 'atr_pct': 9.9}
    sec = K.top_two(old, previous={})
    assert [p['ticker'] for p in sec['picks']] == ['AC.TO', 'SU.TO'] and 'passed_wild' not in sec
    assert sec['rule_version'] == K.RULE_VERSION + '+day135c-movers'


def test_a_wild_name_is_never_the_runner_up_and_the_note_says_why():
    snap = with_wild(snap_of(ALL_AGREE), cut=5.0, AC_TO=7.0, SU_TO=6.0, CNQ_TO=5.5)
    sec = K.top_two(snap, previous={})
    assert sec['picks'] == [] and sec['runner_up'] is None
    assert "LONG CNQ.TO (one of the morning's widest-swinging names)" in sec['runner_up_note']
    assert sec['reason'] == ("The council's picks were among the morning's widest-swinging names, passed "
                             "over by the high-volatility rule (day-137), so there is nothing here to "
                             "act on.")
    assert K.passed_head(sec) == "the council's picks were among the morning's widest-swinging names, passed over"


def test_ten_twenty_one_one_big_mover_and_one_wild_name_leave_no_pick():
    """10-21's shape: LONG TRI.TO rose 1.2 ATR, SHORT CLS.TO swings 7.3% a normal
    day against a 5.06% cut. The big-mover rule takes TRI; this rule takes CLS."""
    import council_flash
    import email_render as E
    import prepare_delivery
    snap = with_wild(snap_of(ALL_AGREE), cut=5.06, SU_TO=7.3, CNQ_TO=2.5)
    snap['moves']['AC.TO'] = {'move_atr': 1.2, 'atr_pct': 3.0}
    sec = K.top_two(snap, previous={})
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT'
    assert [x['ticker'] for x in sec['passed_movers']] == ['AC.TO']
    assert [x['ticker'] for x in sec['passed_wild']] == ['SU.TO']
    assert sec['reason'].startswith("One council pick was one of the last session's big movers")
    assert K.passed_head(sec) == ("one council pick was one of the last session's big movers and the "
                                  "other one of the morning's widest-swinging names, both passed over")
    assert council_flash.subject('2026-10-21', sec) == (
        'RB Council Flash — 2026-10-21 — a big mover and a high-volatility name passed over — no '
        'council pick · runner-up, agreed, ranked below the picks: LONG CNQ.TO')
    report = {'session': '2026-10-21', 'report_status': 'ON_TIME',
              'intraday': {'top_two': sec, 'desks': [{'legs': []}]}}
    assert prepare_delivery.subject_state(report) == \
        '⛔ NO COUNCIL PICK — a big mover and a high-volatility name passed over — '
    html = E._hero({'intraday': {'top_two': sec, 'desks': [{}]}})
    assert 'both passed over' in html


def test_a_big_mover_that_is_also_wild_is_passed_over_once_as_a_mover():
    snap = with_wild(snap_of(ALL_AGREE), cut=5.0, SU_TO=2.0)
    snap['moves']['AC.TO'] = {'move_atr': 2.0, 'atr_pct': 8.0}
    sec = K.top_two(snap, previous={})
    assert [x['ticker'] for x in sec['passed_movers']] == ['AC.TO'] and 'passed_wild' not in sec


def test_the_movers_rule_alone_still_reads_as_before():
    """10-15: every pick a big mover; the subject and reason are day-135d's."""
    import prepare_delivery
    sec = K.top_two(octfifteen(), previous={})
    report = {'session': '2026-10-15', 'report_status': 'ON_TIME',
              'intraday': {'top_two': sec, 'desks': [{'legs': []}]}}
    assert prepare_delivery.subject_state(report) == '⛔ NO COUNCIL PICK — big movers passed over — '


def test_passed_wild_is_recorded_as_a_shadow_never_top2_pooled_or_on_the_board(monkeypatch):
    import daily_review
    import execution_lab
    import model_picks
    import primary_board
    sec = K.top_two(with_wild(snap_of(ALL_AGREE), AC_TO=7.3), previous={})
    rows = model_picks.rows_from_report({'session': '2026-10-22', 'intraday': {'top_two': sec}})
    rule = K.RULE_VERSION + '+day135c-movers+day137-wild'
    assert sorted((r['model'], r['ticker'], r['prompt_version']) for r in rows) == [
        ('top2', 'SU.TO', rule), ('top2runner', 'CNQ.TO', rule), ('top2wild', 'AC.TO', rule)]
    assert 'top2wild' in model_picks.POOLED_EXCLUDED
    assert not any('top2wild' in key for key, _ in primary_board.LEADERBOARD)
    seen = []
    monkeypatch.setattr(execution_lab, '_unique', lambda rs: seen.extend(rs) or [])
    execution_lab.table([{**r, 'kind': 'pick', 'r': '0.5'} for r in rows])
    assert 'AC.TO' not in [r['ticker'] for r in seen]
    got = [(x['section'], x['ticker']) for x in daily_review.picks_of({'intraday': {'top_two': sec}})]
    assert ('Passed over (high volatility)', 'AC.TO') in got and ('Top 2', 'AC.TO') not in got


def test_stage_records_the_mornings_cut_from_every_row_the_desks_read(staged, monkeypatch):
    import claude_opportunities as C
    rows = [{'ticker': 'N%d.TO' % i, 'atr_pct': float(i)} for i in range(1, 31)]
    monkeypatch.setattr(C, 'read_brief', lambda root, now: {'payload': {'candidates': rows}})
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6'), b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6')])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8'), b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75')])
    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm},
                  jev_poster=jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.3, 'NONE': 0.1}),
                  wait=False, clock=lambda: NOW)
    saved = json.loads((staged/K.SNAPSHOT).read_text())
    assert saved['wild'] == out['wild'] == {'pctile': 90, 'atr_pct': 27.1, 'names': 30}
    assert all('wild' not in json.dumps(seen[1]) for seen in gm.seen)   # never sent to the members
    assert 'wild' not in out['errors']


def test_stage_names_a_cut_it_could_not_make(staged, monkeypatch):
    import claude_opportunities as C
    monkeypatch.setattr(C, 'read_brief', lambda root, now: {'payload': {'candidates': []}, 'universe': []})
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6'), b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6')])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8'), b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75')])
    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm},
                  jev_poster=jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.3, 'NONE': 0.1}),
                  wait=False, clock=lambda: NOW)
    assert 'wild' not in out and out['errors']['wild'] == 'fewer than 20 names with an ATR'


def test_the_counted_fallback_applies_the_cut_from_the_brief():
    rows = {'N%d.TO' % i: {'move_atr': 0.1, 'atr_pct': float(i)} for i in range(1, 21)}
    sec = K.decide(two_counted(), NOT_SAT, moves=({**rows, 'AC.TO': {'move_atr': 0.2, 'atr_pct': 30.0},
                                                    'SU.TO': {'move_atr': -0.3, 'atr_pct': 2.0}}, None))
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['status'] == 'PARTIAL'
    assert [x['ticker'] for x in sec['passed_wild']] == ['AC.TO']
    assert sec['rule_version'] == 'day121-agreement+day135c-movers+day137-wild+day120-entry'
    assert sec['reason'].startswith("The other agreed name was one of the morning's widest-swinging names")
    assert K.passed_head({**sec, 'picks': []}) == \
        "the agreed name was one of the morning's widest-swinging names, passed over"


def test_the_memory_council_carries_the_cut_and_the_label(monkeypatch):
    import council_memory
    snap = {**with_wild(snap_of(ALL_AGREE), AC_TO=7.3), 'variant': 'memory'}
    sec = council_memory.section(snap)
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO']
    assert sec['rule_version'] == council_memory.RULE_VERSION + '+day135c-movers+day137-wild'
