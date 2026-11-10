"""Day-146 (owner, 2026-11-04; PREREGISTER_day146_runs.md): a Top 2 pick that
follows a three-day run — LONG after three rises, SHORT after three falls — is
passed over. On Claude's picks, Claude's next nomination on that side stands;
on the council's own Top 2 it is remove-only. The registered history test was
NULL (#61): this changes which picks are made, not how often they are right.

The rest of the suite runs with the rule off (tests/conftest.py). Every test
here is marked `day146` and runs on the production values.
"""
import json
import random
import time

import pytest

import council as K
import runs as RU
import runs_history as RH
from tests.test_claude_leads import led_snap
from tests.test_council import NOW, FakeDeepSeek, FakeGemini, b, jev_poster, staged  # noqa: F401

pytestmark = pytest.mark.day146


def rec(n, *changes):
    return {'run': n, 'as_of': '2026-11-04', 'dates': [], 'changes_pct': list(changes)}


def test_the_production_switches_from_the_eleven_five_morning():
    assert K.SKIP_RUNS is True and K.RUN_RULE == 'day146-runs' and RU.RUN == 3
    assert K.CLAUDE_LEADS is True and K.SKIP_MOVERS is False and K.SKIP_WILD is False


def test_the_live_run_count_is_the_registered_tests():
    rng = random.Random(146)
    for _ in range(2000):
        closes, c = [], 100.0
        for _ in range(rng.randint(0, 14)):
            c *= rng.choice((1.0, 1.01, 0.99, 1.02, 0.98))
            closes.append(round(c, 4))
        assert RU.run_length(closes) == RH.run_length(closes)


def test_follows_is_the_continuation_side_only():
    assert RU.follows('LONG', 3) and RU.follows('SHORT', -3) and RU.follows('LONG', 6)
    # against a run (a bounce bet after falls, a fade after rises) is not following it
    assert not RU.follows('LONG', -3) and not RU.follows('SHORT', 3)
    assert not RU.follows('LONG', 2) and not RU.follows('SHORT', -2)
    assert not RU.follows('LONG', None) and not RU.follows('LONG', True)


def test_a_first_named_pick_that_follows_a_run_gives_way_to_claudes_next():
    s = led_snap()
    s['runs'] = {'CNQ.TO': rec(3, 0.5, 0.8, 1.2), 'AC.TO': rec(-1, -0.4),
                 'SU.TO': rec(1, 0.3), 'TD.TO': rec(2, 0.1, 0.2)}
    sec = K.top_two(s, previous={})
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert sec['status'] == 'READY' and sec['rule_version'] == 'day144-claude-leads+day146-runs'
    (x,) = sec['passed_run']
    assert (x['side'], x['ticker'], x['run'], x['replaced_by']) == ('LONG', 'CNQ.TO', 3, 'AC.TO')
    # shaped like a pick, so it is shown and recorded as a shadow
    assert (x['reason'], x['confidence'], x['invalid_at']) == ('Claude long reason', 0.55, 40.0)
    # the shadow beside Claude's picks keeps the council's own rule
    assert [(p['side'], p['ticker']) for p in sec['council_own']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert sec['council_own_rule'] == K.RULE_VERSION
    line = K.run_line(sec)
    assert 'LONG CNQ.TO rose three sessions running (+0.5%, +0.8%, +1.2%)' in line
    assert "Claude's next long, LONG AC.TO, stands in its place" in line
    assert 'not shown to raise accuracy on history' in line
    import top_picks
    assert line in top_picks.table(sec, concise=True)


def test_a_short_after_three_falls_gives_way_and_a_bounce_bet_stands():
    s = led_snap()
    s['runs'] = {'CNQ.TO': rec(-4, -1, -1, -1, -1), 'SU.TO': rec(-3, -0.5, -0.6, -0.7),
                 'TD.TO': rec(-1, -0.2)}
    sec = K.top_two(s, previous={})
    # LONG CNQ.TO after four falls bets on a bounce: it stands
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('LONG', 'CNQ.TO'), ('SHORT', 'TD.TO')]
    assert [x['ticker'] for x in sec['passed_run']] == ['SU.TO']
    assert 'SHORT SU.TO fell three sessions running (-0.5%, -0.6%, -0.7%)' in K.run_line(sec)


def test_both_nominations_on_a_side_following_runs_leave_that_slot_empty():
    s = led_snap()
    s['runs'] = {'SU.TO': rec(-3, -1, -1, -1), 'TD.TO': rec(-5, -1, -1, -1, -1, -1), 'CNQ.TO': rec(0)}
    sec = K.top_two(s, previous={})
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO'] and sec['status'] == 'PARTIAL'
    assert [x['ticker'] for x in sec['passed_run']] == ['SU.TO', 'TD.TO']
    assert all(x['replaced_by'] is None for x in sec['passed_run'])
    assert sec['reason'] == ("Claude's short nominations followed three-day runs, passed over by the "
                             'three-day-run rule (day-146), so the short slot is left empty.')
    assert "no other short of Claude's stands, so the short slot is empty" in K.run_line(sec)


def test_every_nomination_following_a_run_leaves_nothing_to_act_on():
    import council_flash
    import email_render  # noqa: F401  (the hero reads passed_head)
    import top_picks
    s = led_snap()
    s['runs'] = {'CNQ.TO': rec(3), 'AC.TO': rec(4), 'SU.TO': rec(-3), 'TD.TO': rec(-3)}
    sec = K.top_two(s, previous={})
    assert sec['picks'] == [] and sec['status'] == 'NO_AGREEMENT' and len(sec['passed_run']) == 4
    assert K.passed_head(sec) == "Claude's nominations followed three-day runs, passed over"
    assert council_flash.subject('2026-11-05', sec) == (
        'RB Council Flash — 2026-11-05 — three-day runs passed over — nothing to act on')
    lines = top_picks.table(sec, concise=True)
    assert ("Claude's long and short nominations followed three-day runs, passed over by the "
            'three-day-run rule (day-146), so the long and short slots are left empty.') in lines
    assert 'LONG CNQ.TO rose three sessions running; no other long' in K.run_line(sec)
    assert "or its next one where the first followed a three-day run" in lines[1]


def test_a_name_whose_run_was_not_read_stands():
    s = led_snap()
    s['runs'] = {'SU.TO': rec(-1)}                 # CNQ.TO's closes could not be read
    sec = K.top_two(s, previous={})
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO', 'SU.TO'] and 'passed_run' not in sec
    assert sec['rule_version'] == 'day144-claude-leads+day146-runs'


def test_no_runs_recorded_or_the_switch_off_changes_nothing():
    sec = K.top_two(led_snap(), previous={})
    assert sec['rule_version'] == 'day144-claude-leads' and 'passed_run' not in sec
    s = led_snap()
    s['runs'] = {'CNQ.TO': rec(3)}
    off = K.top_two(s, previous={}, skip_runs=False)
    assert [p['ticker'] for p in off['picks']] == ['CNQ.TO', 'SU.TO']
    assert off['rule_version'] == 'day144-claude-leads' and 'passed_run' not in off


def test_the_councils_own_top_two_is_remove_only_when_claudes_picks_are_missing():
    s = led_snap({'longs': [], 'shorts': []})
    s['runs'] = {'AC.TO': rec(3, 1, 1, 1), 'SU.TO': rec(1)}
    sec = K.top_two(s, previous={})
    assert sec.get('claude_note') and [p['ticker'] for p in sec['picks']] == ['SU.TO']
    (x,) = sec['passed_run']
    assert x['ticker'] == 'AC.TO' and x['replaced_by'] is None and sec['status'] == 'PARTIAL'
    assert sec['reason'] == ("The council's other pick followed a three-day run, passed over by the "
                             'three-day-run rule (day-146); the second slot is left empty.')
    assert sec['rule_version'] == K.RULE_VERSION + '+' + K.RUN_RULE
    # with Claude leading off, the council's own is the live Top 2 and the rule applies the same way
    off = K.top_two(s, previous={}, claude_leads=False)
    assert [p['ticker'] for p in off['picks']] == ['SU.TO'] and off['passed_run'][0]['ticker'] == 'AC.TO'


def test_a_council_without_runs_like_the_memory_councils_keeps_its_rule():
    s = led_snap({'longs': [], 'shorts': []})
    sec = K.top_two(s, previous={}, claude_leads=False)
    assert sec['rule_version'] == K.RULE_VERSION and 'passed_run' not in sec


def test_the_passed_over_picks_are_recorded_as_a_shadow_and_reviewed(tmp_path):
    import daily_review
    import model_picks as M
    s = led_snap()
    s['runs'] = {'CNQ.TO': rec(3, 0.5, 0.8, 1.2)}
    sec = K.top_two(s, previous={})
    report = {'session': '2026-11-05', 'intraday': {'top_two': sec}}
    rows = M.rows_from_report(report)
    shadow = [r for r in rows if r['model'] == 'top2run']
    assert [(r['kind'], r['side'], r['ticker']) for r in shadow] == [('pick', 'LONG', 'CNQ.TO')]
    assert shadow[0]['prompt_version'] == 'day144-claude-leads+day146-runs'
    assert [(r['side'], r['ticker']) for r in rows if r['model'] == 'top2'] == [
        ('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    # never pooled, never in the lab's table
    assert 'top2run' in M.POOLED_EXCLUDED
    import inspect
    import execution_lab
    assert "'top2run'" in inspect.getsource(execution_lab._model_picks)      # the table's population
    assert 'Passed over (three-day run)' in inspect.getsource(daily_review)


def test_stage_records_the_runs_of_the_table_and_the_nominations(staged):
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6', top=['P1']),
                       b('ENDORSE 0.7', 'OPPOSE 0.6', 'OPPOSE 0.7', top=['P1'])])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8', top=['P3']),
                     b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75', top=['P1', 'P3'])])
    post = jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.2, 'NONE': 0.2})
    asked = []

    def runs_fn(tickers):
        asked.append(list(tickers))
        return {'AC.TO': rec(3, 1, 1, 1)}, {'SU.TO': 'FMP_HTTP_429'}

    def sleep(_):
        K.seal_ballot(staged, b('ENDORSE 0.66', 'OPPOSE 0.8', 'ABSTAIN', top=['P1']), now=NOW)
    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm}, jev_poster=post,
                  sleep=sleep, clock=lambda: NOW, runs_fn=runs_fn)
    assert asked == [['AC.TO', 'CNQ.TO', 'SU.TO']]
    saved = json.loads((staged/K.SNAPSHOT).read_text())
    assert saved['runs'] == {'AC.TO': rec(3, 1, 1, 1)}
    assert saved['errors']['runs'] == 'SU.TO FMP_HTTP_429'
    # never sent to the members
    assert 'runs' not in json.dumps(gm.seen[0][1]) and 'FMP_HTTP_429' not in json.dumps(gm.seen)
    assert out['status'] == 'READY'


def test_a_runs_failure_costs_the_rule_only(staged):
    ds = FakeDeepSeek([b('ENDORSE 0.7', 'OPPOSE 0.6', 'ENDORSE 0.6', top=['P1']),
                       b('ENDORSE 0.7', 'OPPOSE 0.6', 'OPPOSE 0.7', top=['P1'])])
    gm = FakeGemini([b('ENDORSE 0.6', 'ABSTAIN', 'ENDORSE 0.8', top=['P3']),
                     b('ENDORSE 0.65', 'ABSTAIN', 'ENDORSE 0.75', top=['P1', 'P3'])])

    def runs_fn(tickers):
        raise RuntimeError('boom')

    def sleep(_):
        K.seal_ballot(staged, b('ENDORSE 0.66', 'OPPOSE 0.8', 'ABSTAIN', top=['P1']), now=NOW)
    out = K.stage(staged, now=NOW, clients={'deepseek': ds, 'gemini': gm},
                  jev_poster=jev_poster({'P1': 0.5, 'P2': 0.1, 'P3': 0.2, 'NONE': 0.2}),
                  sleep=sleep, clock=lambda: NOW, runs_fn=runs_fn)
    assert out['status'] == 'READY' and 'runs' not in out and out['errors']['runs'] == 'RuntimeError'


def _fmp(rows_by_ticker):
    def get(t):
        got = rows_by_ticker[t]
        if isinstance(got, Exception):
            raise got
        return got
    return get


def test_fetch_reads_the_prior_session_and_names_each_failure():
    import fmp_client
    rows = {'A.TO': [{'date': '2026-11-04', 'close': 13.0}, {'date': '2026-11-03', 'close': 12.0},
                     {'date': '2026-11-02', 'close': 11.0}, {'date': '2026-10-30', 'close': 10.0},
                     {'date': '2026-10-29', 'close': 10.5}],
            'B.TO': [{'date': '2026-11-03', 'close': 5.0}, {'date': '2026-11-02', 'close': 6.0}],
            'C.TO': fmp_client.FMPError('FMP_HTTP_429'),
            'D.TO': ValueError('a message with the url https://x?apikey=SECRET')}
    got, errors = RU.fetch(['A.TO', 'B.TO', 'C.TO', 'D.TO'], '2026-11-04', get=_fmp(rows))
    assert got == {'A.TO': {'run': 3, 'as_of': '2026-11-04',
                            'dates': ['2026-11-02', '2026-11-03', '2026-11-04'],
                            'changes_pct': [10.0, 9.09, 8.33]}}
    # a stale series is refused, and no message text (which can carry a URL) is kept
    assert errors == {'B.TO': 'NOT_THE_PRIOR_SESSION', 'C.TO': 'FMP_HTTP_429', 'D.TO': 'ValueError'}
    assert RU.words(got['A.TO']) == 'rose three sessions running (+10.0%, +9.1%, +8.3%)'


def test_fetch_never_waits_past_its_deadline():
    def slow(t):
        time.sleep(1.5)
        return []
    t0 = time.monotonic()
    got, errors = RU.fetch(['A.TO', 'B.TO'], '2026-11-04', get=slow, deadline=0.2)
    assert time.monotonic() - t0 < 1.0
    assert got == {} and errors == {'A.TO': 'TIMEOUT', 'B.TO': 'TIMEOUT'}


def test_a_rule_that_could_not_read_the_closes_says_so():
    import top_picks
    s = led_snap()
    s['runs'] = {'SU.TO': rec(1)}
    s['errors'] = {'runs': 'CNQ.TO FMP_HTTP_429'}
    sec = K.top_two(s, previous={})
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO', 'SU.TO']
    assert sec['run_note'] == ("The three-day-run rule (day-146) could not read some names' daily "
                               'closes (CNQ.TO FMP_HTTP_429); those names stand unchecked.')
    assert sec['run_note'] in top_picks.table(sec, concise=True)
    s = led_snap()
    s['errors'] = {'runs': 'RuntimeError'}       # the read failed whole: no runs recorded
    sec = K.top_two(s, previous={})
    assert sec['rule_version'] == 'day144-claude-leads'
    assert sec['run_note'] == ('The three-day-run rule (day-146) could not be applied today '
                               '(RuntimeError); the picks stand unchecked.')
    # switched off, or a council from before day-146, says nothing
    assert 'run_note' not in K.top_two(s, previous={}, skip_runs=False)
    assert 'run_note' not in K.top_two(led_snap(), previous={})


def test_the_page_says_so_too():
    import report_page
    s = led_snap()
    s['runs'] = {'CNQ.TO': rec(3, 0.5, 0.8, 1.2)}
    html = report_page._top_two_section({'top_two': K.top_two(s, previous={})})
    assert "or its next one where the first followed a three-day run" in html
    assert 'Passed over as following a three-day run' in html and 'LONG CNQ.TO rose three sessions' in html
    # a section from before day-146 reads as it did
    old = report_page._top_two_section({'top_two': K.top_two(led_snap(), previous={})})
    assert 'three-day run' not in old
