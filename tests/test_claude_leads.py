"""Day-144 (owner, 2026-10-30; PREREGISTER_day144_claude_leads.md).

"Claude picks are doing much better than council. I want council to be led by
Claude picks." The Top 2 is Claude's first-named long and short from its
council nominations; the council's vote on each is shown and cannot replace
it; the council's own choice is recorded beside as the `top2council` shadow;
and the guardrails are off ("Let's get rid of these guardrails rules").

The rest of the suite pins the earlier rules (tests/conftest.py). Every test
here is marked `day144` and runs on the production values.
"""
import datetime as dt

import pytest

import council as K
import entry_checks
from tests.test_council import council_snap, counted

pytestmark = pytest.mark.day144

# Claude's nominations, best first. CNQ.TO is on the table and the council
# turned it down (1 of 3 endorse, 2 object); SU.TO the council agreed 3 of 3.
CLAUDE = {'longs': [{'ticker': 'CNQ.TO', 'confidence': 0.55, 'reason': 'Claude long reason',
                     'invalid_at': 40.0, 'basis': 'technical'},
                    {'ticker': 'AC.TO', 'confidence': 0.5, 'reason': 'second long', 'invalid_at': 29.0}],
          'shorts': [{'ticker': 'SU.TO', 'confidence': 0.52, 'reason': 'Claude short reason',
                      'invalid_at': 52.0},
                     {'ticker': 'TD.TO', 'confidence': 0.5, 'reason': 'second short', 'invalid_at': 90.0}]}


def led_snap(claude=CLAUDE):
    """council_snap (the council's own picks: LONG AC.TO, SHORT SU.TO) with
    Claude's nominations sealed beside it, as council.stage keeps them."""
    s = council_snap()
    s['nomination_picks'] = {'claude': claude, 'deepseek': {'longs': [], 'shorts': []}}
    return s


def test_the_production_switches_from_the_eleven_two_morning():
    assert K.CLAUDE_LEADS is True and K.CLAUDE_RULE == 'day144-claude-leads'
    assert K.SKIP_MOVERS is False and K.SKIP_WILD is False
    assert entry_checks.VOID_TOP2 is False


def test_the_top_two_is_claudes_first_long_and_short_with_the_councils_vote():
    sec = K.top_two(led_snap(), previous={})
    assert sec['claude_leads'] and sec['council'] and sec['status'] == 'READY'
    assert sec['rule_version'] == 'day144-claude-leads' and sec['runner_up'] is None
    assert [(p['side'], p['ticker']) for p in sec['picks']] == [('LONG', 'CNQ.TO'), ('SHORT', 'SU.TO')]
    long_, short = sec['picks']
    # Claude's own reason, level and confidence, not the table's lead proposer's
    assert (long_['lead'], long_['reason'], long_['invalid_at']) == ('Claude', 'Claude long reason', 40.0)
    assert long_['confidence'] == 0.55 and long_['models'] == ['claude']
    # the council's vote is shown and did not replace the pick: it turned CNQ.TO down
    assert long_['council_vote'] == '1 of 3 endorse, 2 object'
    assert long_['agreement'] == 'Claude 0.55; council 1 of 3 endorse, 2 object'
    assert short['council_vote'] == '3 of 3 endorse' and short['invalid_at'] == 52.0
    # the council's own choice, kept beside as the shadow, with its own rule
    assert [(p['side'], p['ticker']) for p in sec['council_own']] == [('LONG', 'AC.TO'), ('SHORT', 'SU.TO')]
    assert sec['council_own_rule'] == K.RULE_VERSION and sec['council_own_status'] == 'READY'


def test_one_side_named_leaves_the_other_slot_empty():
    sec = K.top_two(led_snap({'longs': [], 'shorts': CLAUDE['shorts']}), previous={})
    assert [p['ticker'] for p in sec['picks']] == ['SU.TO'] and sec['status'] == 'PARTIAL'
    assert 'second slot is left empty' in sec['reason']


def test_a_pick_the_council_never_voted_on_says_so():
    claude = {'longs': [{'ticker': 'BNS.TO', 'confidence': 0.6, 'reason': 'r', 'invalid_at': 70.0}],
              'shorts': []}
    sec = K.top_two(led_snap(claude), previous={})
    p = sec['picks'][0]
    assert p['ticker'] == 'BNS.TO' and p['council_vote'] == "not voted on (not on the council's table)"
    assert K.council_lines(sec) == ["Council on LONG BNS.TO: not voted on (not on the council's table)."]


def test_without_claudes_picks_the_councils_own_top_two_stands_labelled():
    import top_picks
    s = council_snap()
    s['errors'] = {'nominations claude': 'HTTPError'}
    sec = K.top_two(s, previous={})
    assert not sec.get('claude_leads') and [p['ticker'] for p in sec['picks']] == ['AC.TO', 'SU.TO']
    assert sec['claude_note'] == ("Claude's picks were unavailable today (HTTPError); the council's "
                                  'own Top 2 stands.')
    assert sec['claude_note'] in '\n'.join(top_picks.table(sec, concise=True))
    empty = K.top_two({**council_snap(), 'nomination_picks': {'claude': {'longs': [], 'shorts': []}}},
                      previous={})
    assert '(it nominated nothing)' in empty['claude_note']


def test_the_council_did_not_sit_and_claudes_picks_stand_without_a_vote():
    s = {'status': 'UNAVAILABLE', 'reason': 'fewer than two members answered', 'session': '2026-10-05',
         'nomination_picks': {'claude': CLAUDE}}
    sec = K.decide(counted(), s)
    assert sec['claude_leads'] and [p['ticker'] for p in sec['picks']] == ['CNQ.TO', 'SU.TO']
    assert all(p['council_vote'] == 'not voted on (the council did not sit)' for p in sec['picks'])
    assert sec['council_note'].startswith('The council did not sit today (fewer than two members answered)')
    assert K.claude_own_line(sec) is None
    # and with no nominations either, the counted rule still decides, as before
    fall = K.decide(counted(), {'status': 'UNAVAILABLE', 'reason': 'not staged'})
    assert not fall.get('claude_leads') and fall['picks'][0]['ticker'] == 'AC.TO'


def test_the_guardrails_are_off_a_big_mover_a_wild_name_or_a_crossed_level_stays_a_pick():
    import top_picks
    s = led_snap()
    s['moves'] = {'CNQ.TO': {'move_atr': 2.4, 'atr_pct': 9.0}, 'SU.TO': {'move_atr': -1.3, 'atr_pct': 2.0},
                  'AC.TO': {'move_atr': 1.8, 'atr_pct': 3.0}}
    s['wild'] = {'pctile': 90, 'atr_pct': 5.0, 'names': 150}
    sec = K.decide(counted(), s)
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO', 'SU.TO']
    assert not sec.get('passed_movers') and not sec.get('passed_wild')
    assert [p['ticker'] for p in sec['council_own']] == ['AC.TO', 'SU.TO']   # not thinned either
    assert "The last session's big movers" in top_picks.mover_line(sec)    # the caution still prints
    # E1 never removes a Claude pick, even past its own level at 09:46
    sec = K.top_two(s, previous={}, prices={'CNQ.TO': 39.0, 'SU.TO': 53.0})
    assert [p['ticker'] for p in sec['picks']] == ['CNQ.TO', 'SU.TO']
    assert all(p['entry_check'] is None for p in sec['picks'])


def test_the_email_flash_and_page_say_whose_picks_they_are():
    import council_flash
    import report_page
    import top_picks
    sec = K.top_two(led_snap(), previous={})
    text = '\n'.join(top_picks.table(sec, concise=True))
    assert "## Top 2 — Claude's picks, with the council's vote" in text
    assert '| 1 | LONG CNQ.TO | 0.55 | 1 of 3 endorse, 2 object | below 40 | — | Claude long reason |' in text
    assert "The council's own choice, recorded beside and not a pick: LONG AC.TO" in text
    assert 'Council on LONG CNQ.TO: Claude endorse 0.60' in text
    assert 'coin flip' not in text                              # the email carries no caveat prose
    assert 'coin flip' in '\n'.join(top_picks.table(sec))       # the full report does
    assert council_flash.subject('2026-10-05', sec) == (
        'RB Council Flash — 2026-10-05 — LONG CNQ.TO (Claude 0.55; council 1 of 3 endorse, 2 object)'
        ' · SHORT SU.TO (Claude 0.52; council 3 of 3 endorse)')
    page = report_page._top_two_section({'top_two': sec})
    assert "Claude's picks, with the council's vote" in page and 'Claude: Claude long reason' in page
    assert "Claude's conf." in page and 'coin flip yet' in page


def test_the_flash_and_open_check_no_longer_promise_the_0946_drop():
    import council_flash
    snap = {**led_snap(), 'asked_at': '2026-10-05T08:58:00-04:00'}
    now = dt.datetime(2026, 10, 5, 8, 59, tzinfo=K.ET)
    subj, body, html = council_flash.compose(snap, now)
    assert 'check each "wrong if" against your own quote first' in body
    assert 'the 09:46 report drops' not in body
    rows = [{**p, 'verdict': 'VOID', 'price': 39.0, 'at': '09:31', 'open_for_pick': -1.0,
             'open_days': None, 'now_for_pick': -1.0, 'etf': 'XEG.TO', 'etf_move': 0.1, 'reach': None}
            for p in K.top_two(snap, previous={})['picks']]
    _, text, _ = council_flash.compose_open(snap, rows, now.replace(hour=9, minute=31))
    assert 'no longer drops a VOID pick (day-144)' in text


def test_the_subject_and_hero_name_claudes_top_two():
    import email_render
    import prepare_delivery
    sec = K.top_two(led_snap(), previous={})
    report = {'session': '2026-10-05', 'report_status': 'ON_TIME',
              'intraday': {'desks': [{'id': 'claude', 'legs': []}], 'top_two': sec}}
    assert prepare_delivery.subject_state(report) == "CLAUDE'S TOP 2 ONLY — 2 positions, no sized desk leg — "
    hero = email_render._hero(report)
    assert "the Top 2 is Claude's best long and short" in hero.replace('&#x27;', "'")


def test_the_record_keeps_claudes_picks_and_the_councils_own_choice_apart():
    import model_picks as M
    sec = K.top_two(led_snap(), previous={})
    rows = M.rows_from_report({'session': '2026-10-05', 'intraday': {'top_two': sec}})
    top2 = [(r['side'], r['ticker'], r['prompt_version']) for r in rows if r['model'] == 'top2']
    own = [(r['side'], r['ticker'], r['prompt_version']) for r in rows if r['model'] == 'top2council']
    assert top2 == [('LONG', 'CNQ.TO', 'day144-claude-leads'), ('SHORT', 'SU.TO', 'day144-claude-leads')]
    assert own == [('LONG', 'AC.TO', K.RULE_VERSION), ('SHORT', 'SU.TO', K.RULE_VERSION)]
    assert next(r for r in rows if r['model'] == 'top2')['confidence'] == 0.55   # Claude's own number
    assert 'top2council' in M.POOLED_EXCLUDED


def _row(session, model, ticker, side, rule, r=None):
    return {'session': session, 'model': model, 'kind': 'pick', 'ticker': ticker, 'side': side,
            'prompt_version': rule, 'r_pct': '' if r is None else str(r)}


def test_the_scoreboard_shows_both_under_the_top_two_once_scored():
    import model_picks as M
    import primary_board as P
    scored = {'scored_at': '2026-11-02T16:30:00-05:00'}
    rows = [{**_row('2026-10-30', 'top2', 'A.TO', 'LONG', K.RULE_VERSION, -1.0), **scored, 'hit': '0'},
            {**_row('2026-11-02', 'top2', 'B.TO', 'LONG', K.CLAUDE_RULE, 1.0), **scored, 'hit': '1'},
            {**_row('2026-11-02', 'top2council', 'C.TO', 'SHORT', K.RULE_VERSION, -0.5), **scored, 'hit': '0'}]
    board = P.leaderboard(M.scorecard(rows))
    assert [r['source'] for r in board][:4] == [
        'Top 2 (where the models agree)', 'Top 2 led by Claude (from 2026-11-02)',
        "The council's own choice, not a pick (from 2026-11-02)", 'Claude']
    assert board[0]['picks'] == 2 and (board[1]['picks'], board[1]['mean_r_pct']) == (1, 1.0)
    assert (board[2]['picks'], board[2]['mean_r_pct']) == (1, -0.5)
    assert [r['source'] for r in P.leaderboard(M.scorecard(rows[:1]))][1] == 'Claude'   # not before
    assert M.pooled_card(rows)['all_model_picks']['picks'] == 2                          # never pooled


def test_the_councils_own_rows_follow_the_rule_each_session():
    import model_picks as M
    rows = [_row('2026-10-30', 'top2', 'A.TO', 'LONG', K.RULE_VERSION),
            _row('2026-11-02', 'top2', 'B.TO', 'LONG', K.CLAUDE_RULE),
            _row('2026-11-02', 'top2council', 'C.TO', 'SHORT', K.RULE_VERSION),
            _row('2026-11-03', 'top2', 'D.TO', 'LONG', K.CLAUDE_RULE)]       # the council chose nothing
    assert [(r['session'], r['ticker']) for r in M.council_rows(rows)] == [('2026-10-30', 'A.TO'),
                                                                           ('2026-11-02', 'C.TO')]


def test_the_review_scores_the_councils_own_choice_in_its_own_section():
    import daily_review
    sec = K.top_two(led_snap(), previous={})
    got = [(p['section'], p['ticker']) for p in daily_review.picks_of({'intraday': {'top_two': sec}})]
    assert ('Top 2', 'CNQ.TO') in got and ('Top 2', 'AC.TO') not in got
    assert ("Council's own choice (shadow)", 'AC.TO') in got
    assert daily_review.claude_led_section('2026-11-02', lines=lambda s: ['x']) == '\nx\n'

    def broken(session):
        raise KeyError('x')
    assert 'unavailable (KeyError)' in daily_review.claude_led_section('2026-11-02', lines=broken)


def test_the_memory_council_stays_on_the_councils_own_rule_and_pairs_with_it():
    import council_memory
    out = council_memory.section(led_snap())
    assert not out.get('claude_leads') and [p['ticker'] for p in out['picks']] == ['AC.TO', 'SU.TO']
    rows = [_row('2026-11-02', 'top2', 'B.TO', 'LONG', K.CLAUDE_RULE, 5.0),
            _row('2026-11-02', 'top2council', 'C.TO', 'SHORT', K.RULE_VERSION, 1.0),
            {**_row('2026-11-02', 'top2memory', 'C.TO', 'SHORT', 'day130-memory', 1.0)}]
    c = council_memory.comparison(rows)
    assert c['days'] == 1 and c['mean_d'] == 0.0 and c['same_days'] == 1


# ── the registered comparison (claude_leads.py) ──────────────────────────────

def _sessions(ds, start=dt.date(2026, 11, 2)):
    """One Claude-led pick returning d and one council pick returning 0 per
    session, so each session's net difference is exactly d."""
    rows = []
    for i, d in enumerate(ds):
        s = (start + dt.timedelta(days=i)).isoformat()
        rows += [_row(s, 'top2', 'A.TO', 'LONG', K.CLAUDE_RULE, d),
                 _row(s, 'top2council', 'B.TO', 'SHORT', K.RULE_VERSION, 0.0)]
    return rows


def test_the_comparison_is_net_and_a_council_that_stood_aside_counts_zero():
    import claude_leads as L
    rows = [_row('2026-11-02', 'top2', 'A.TO', 'LONG', K.CLAUDE_RULE, 1.0),
            _row('2026-11-02', 'top2', 'B.TO', 'SHORT', K.CLAUDE_RULE, -0.5),
            _row('2026-11-02', 'top2council', 'C.TO', 'LONG', K.RULE_VERSION, 0.2),
            _row('2026-11-03', 'top2', 'D.TO', 'LONG', K.CLAUDE_RULE, 0.3),        # the council stood aside
            _row('2026-11-04', 'top2', 'E.TO', 'LONG', K.CLAUDE_RULE),             # not scored yet
            _row('2026-10-30', 'top2', 'F.TO', 'LONG', K.RULE_VERSION, 9.0)]       # before the change
    days = L.paired(rows)
    assert [s for s, *_ in days] == ['2026-11-02', '2026-11-03']
    assert days[0][1] == pytest.approx((0.25 - 0.13) - (0.2 - 0.13))
    assert days[1][1] == pytest.approx(0.3 - 0.13)
    r = L.readout(rows)
    assert r['sessions'] == 2 and r['pending'] == 1 and r['council_stood_aside'] == 1
    assert r['claude'] == {'picks': 3, 'right': 2, 'mean': 0.267, 'net': 0.137}


def test_the_verdict_is_not_due_before_twenty_and_detects_a_planted_edge_at_forty():
    import claude_leads as L
    assert L.verdict(_sessions([0.5] * 19))['status'] == 'NOT_DUE'
    harm = L.verdict(_sessions([-1.0 + (0.5 if i % 2 else -0.5) for i in range(25)]))
    assert harm['status'] == 'HARM' and harm['look'] == 20
    planted = L.verdict(_sessions([1.0 + (0.5 if i % 2 else -0.5) for i in range(40)]), draws=2000)
    assert planted['status'] == 'CLAUDE_BETTER' and planted['t'] >= 3 and planted['placebo_p'] < 0.01
    null = L.verdict(_sessions([0.5 if i % 2 else -0.5 for i in range(40)]), draws=2000)
    assert null['status'] == 'NO_DIFFERENCE' and null['t'] == 0
    worse = L.verdict(_sessions([-1.0 + (0.5 if i % 2 else -0.5) for i in range(40)]), draws=2000)
    assert worse['status'] == 'COUNCIL_BETTER'
