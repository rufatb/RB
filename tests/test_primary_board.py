"""Part 1's headline is the primary source's picks, sized under the engine's rules.

Owner decision 2026-09-22 (the engine went 0/4 at -1.56% that day, and its own
809-leg walk-forward is 50.1%). What must never change with the headline: an
ABSTAIN leg carries no size, eligibility is the engine's, and the subject line
describes the board the reader actually sees first.
"""
import copy
import re

import pytest

import daily_render
import email_render
import prepare_delivery
import primary_board as P
import report_page
from quotes import CORROBORATED

CFG = {'risk': {'account_equity': 100000, 'max_position_pct': 50},
       'execution': {'accept_corroborated_bbo': True}}
OPEN = {'eligible': True, 'status': '09:46 publication window'}
EVIDENCE = {'status': 'READY', 'model': 'deepseek-flash',
            'longs': [{'ticker': 'DOL.TO', 'confidence': 0.56, 'invalid_at': 176.9, 'reason': 'r'}],
            'shorts': [{'ticker': 'SU.TO', 'confidence': 0.62, 'reason': 'r'}]}


def q(status, bid=99.9, ask=100.1):
    return {'status': status, 'bid': bid, 'ask': ask, 'spread_bps': 20.0, 'currency': 'CAD',
            'reason': 'BBO timestamp missing'}


def test_corroborated_quotes_are_sized_with_the_owners_switch_on():
    board = P.build(EVIDENCE, {'DOL.TO': q(CORROBORATED), 'SU.TO': q(CORROBORATED)}, CFG, OPEN, True)
    long, short = board['legs']
    # 25,000 per leg; a long crosses the ask, a short hits the bid.
    assert long['status'] == 'SHADOW' and long['baseline_shares'] == int(25000 // 100.1)
    assert short['baseline_shares'] == int(25000 // 99.9)
    assert long['invalid_at'] == 176.9


def test_with_the_switch_off_a_corroborated_leg_abstains_unsized():
    cfg = copy.deepcopy(CFG)
    cfg['execution']['accept_corroborated_bbo'] = False
    board = P.build(EVIDENCE, {'DOL.TO': q(CORROBORATED), 'SU.TO': q('OK')}, cfg, OPEN, True)
    assert board['legs'][0]['status'] == 'ABSTAIN' and board['legs'][0]['baseline_shares'] == 0
    assert board['legs'][1]['status'] == 'SHADOW'


def test_outside_the_window_every_leg_abstains():
    board = P.build(EVIDENCE, {'DOL.TO': q('OK'), 'SU.TO': q('OK')}, CFG,
                    {'eligible': False, 'status': 'LATE'}, True)
    assert all(l['status'] == 'ABSTAIN' and l['baseline_shares'] == 0 for l in board['legs'])
    assert 'LATE' in board['legs'][0]['reasons']


def test_a_missing_quote_abstains_and_says_why():
    board = P.build(EVIDENCE, {}, CFG, OPEN, True)
    assert all(l['status'] == 'ABSTAIN' for l in board['legs'])
    assert board['legs'][0]['reasons']


def test_no_picks_is_stated_not_hidden():
    board = P.build({'status': 'UNAVAILABLE', 'reason': 'provider down'}, {}, CFG, OPEN, True)
    assert board['legs'] == [] and 'provider down' in board['reason']


def digest(board):
    return {'session': '2026-09-23', 'report_status': 'ON_TIME', 'generated_at': '2026-09-23T09:46:09',
            'intraday': {'primary': board, 'legs': [{'status': 'ABSTAIN', 'ticker': 'BCE.TO', 'side': 'LONG'}]}}


def test_the_subject_describes_the_headline_board():
    sized = P.build(EVIDENCE, {'DOL.TO': q('OK'), 'SU.TO': q('OK')}, CFG, OPEN, True)
    # The engine's only leg abstained; the headline is sized — no DO NOT TRADE.
    assert 'DO NOT TRADE' not in prepare_delivery.subject_state(digest(sized))
    unsized = P.build(EVIDENCE, {}, CFG, OPEN, True)
    assert 'DO NOT TRADE' in prepare_delivery.subject_state(digest(unsized))


def test_an_abstained_headline_leg_shows_no_share_count_in_either_view():
    board = P.build(EVIDENCE, {'DOL.TO': q('OK')}, CFG, OPEN, True)   # SU.TO unquoted
    board['baseline_shares_probe'] = None
    text = '\n'.join(email_render.primary_lines({'primary': board}))
    su = next(line for line in text.splitlines() if 'SU.TO SHORT' in line)
    assert su.split('|')[3].strip() == '—'
    html = report_page._primary_section({'primary': board})
    row = re.search(r'<tr><td><span class="status">ABSTAIN</span></td><td class="tick">SU.TO.*?</tr>', html)
    assert row and '&mdash;' in row.group(0)


def test_the_leaderboard_prints_every_source_even_unscored():
    rows = P.leaderboard({'deepseek_selected': {'picks': 8, 'hits': 3, 'rate': .375,
                                                'mean_r_pct': -.66, 'sessions': 2, 'ci95': [.14, .69]}})
    assert [r['source'] for r in rows][:2] == ['DeepSeek (primary)', 'Baseline engine (k-NN)']
    text = '\n'.join(email_render.primary_lines({'primary': {'source': 'DeepSeek', 'legs': [],
                                                             'reason': 'x', 'leaderboard': rows}}))
    assert '3/8 (38%)' in text and 'not yet scored' in text and 'coin flip' in text
