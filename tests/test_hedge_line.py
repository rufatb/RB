"""Day-148c (owner, 2026-11-09: "Yes should display in email").

When every pick of the Top 2 stands on one side, the pick is also a bet on the
market's direction. On 11-09 the three-day-run rule emptied the short slot and
LONG SHOP.TO stood alone on a day the market rose. The line names the fund that
takes the market out, with the lab's running record and the registered test
that failed (day-130, H2) beside it. DISPLAY ONLY: no pick, no size, no record.

The rest of the suite runs with the line off (tests/conftest.py). Every test
here is marked `day148` and runs on the production value; the Claude-led ones
also carry `day144` and `day146`.
"""
import datetime as dt

import pytest

import council as K
import top_picks as T
from tests.test_claude_leads import CLAUDE, led_snap

pytestmark = pytest.mark.day148

SECTORS = {'SHOP.TO': {'sector': 'Technology', 'industry': 'Software - Application'},
           'CLS.TO': {'sector': 'Technology', 'industry': 'Electronic Components'},
           'CCO.TO': {'sector': 'Energy', 'industry': 'Uranium'},
           'CVE.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Integrated'},
           'WCP.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Exploration & Production'},
           'CNQ.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Exploration & Production'},
           'SU.TO': {'sector': 'Energy', 'industry': 'Oil & Gas Integrated'}}
RECORD = {'picks': 124, 'more_pct': 0.18, 'swing_cut_pct': 15}


@pytest.fixture(autouse=True)
def _a_fixed_sector_map(monkeypatch):
    """The committed map expires after 62 days; a test must not expire with it."""
    import exposure
    monkeypatch.setattr(exposure, 'load_sectors', lambda path=None: SECTORS)


def pick(side, ticker):
    return {'side': side, 'ticker': ticker}


def test_the_production_switch_is_on():
    assert T.HEDGE is True


def test_no_hedge_unless_every_pick_stands_on_one_side():
    assert T.hedge({'picks': []}) is None and T.hedge(None) is None
    assert T.hedge({'picks': [pick('LONG', 'SHOP.TO'), pick('SHORT', 'CVE.TO')]}) is None
    # a runner-up or a single-model pointer is never a pick
    assert T.hedge({'picks': [], 'runner_up': pick('LONG', 'SHOP.TO'),
                    'single': [pick('SHORT', 'CVE.TO')]}) is None
    both = {'picks': [pick('LONG', 'SHOP.TO'), pick('SHORT', 'CVE.TO')]}
    assert T.with_hedge(both, RECORD) is both and T.hedge_line(both) is None


def test_one_long_names_its_fund_the_market_and_what_it_bets_on():
    sec = T.with_hedge({'picks': [pick('LONG', 'SHOP.TO')]}, RECORD)
    assert sec['hedge'] == {'side': 'LONG', 'market': 'XIU.TO', 'record': RECORD,
                            'legs': [{'ticker': 'SHOP.TO', 'etf': 'XIT.TO'}]}
    line = T.hedge_line(sec)
    assert line.startswith('⚠ Only a LONG stands today, so LONG SHOP.TO is also a bet that the market '
                           'does not turn down. Hedge (shown, not a pick): short XIT.TO, its sector '
                           'fund, or XIU.TO, for about the same dollars.')
    assert T.hedge_short(sec) == ('⚠ Only a LONG stands today: it is also a bet on the market. Hedge '
                                  '(shown, not a pick): short XIT.TO, its sector fund, or XIU.TO, for '
                                  'about the same dollars.')


def test_one_short_is_hedged_by_buying():
    line = T.hedge_line(T.with_hedge({'picks': [pick('SHORT', 'CVE.TO')]}, RECORD))
    assert 'Only a SHORT stands today, so SHORT CVE.TO is also a bet that the market does not turn up.' in line
    assert 'buy XEG.TO, its sector fund, or XIU.TO, for about the same dollars.' in line


def test_a_name_with_no_sector_is_hedged_with_the_market_fund_alone():
    line = T.hedge_line(T.with_hedge({'picks': [pick('LONG', 'ZZZ.TO')]}, RECORD))
    assert 'Hedge (shown, not a pick): short XIU.TO for about the same dollars.' in line
    assert 'sector fund' not in line


def test_two_picks_on_one_side_name_each_fund_or_the_one_they_share():
    two = T.with_hedge({'picks': [pick('SHORT', 'CLS.TO'), pick('SHORT', 'CCO.TO')]}, RECORD)
    line = T.hedge_line(two)
    # the day-135 caution already says both share one exposure: no second lead-in
    assert line.startswith('⚠ Hedge (shown, not a pick): buy XIT.TO against CLS.TO and URNM against '
                           'CCO.TO, or XIU.TO against both, for about the same dollars.')
    same = T.hedge_short(T.with_hedge({'picks': [pick('SHORT', 'CVE.TO'), pick('SHORT', 'WCP.TO')]}, RECORD))
    assert same == ('⚠ Hedge (shown, not a pick): buy XEG.TO, the sector fund of both, or XIU.TO, for '
                    'about the same dollars.')
    mixed = T.hedge_short(T.with_hedge({'picks': [pick('LONG', 'SHOP.TO'), pick('LONG', 'ZZZ.TO')]}, RECORD))
    assert mixed == '⚠ Hedge (shown, not a pick): short XIU.TO against both for about the same dollars.'


def test_the_record_is_quoted_as_it_stands_and_the_failed_test_is_always_said():
    good = T.hedge_line(T.with_hedge({'picks': [pick('LONG', 'SHOP.TO')]}, RECORD))
    assert ("On the record so far (124 picks, the hedge sized by each stock's beta to its fund) the "
            'hedged pick made 0.18% a pick more than the unhedged one and swung 15% less.') in good
    bad = T.hedge_line(T.with_hedge({'picks': [pick('LONG', 'SHOP.TO')]},
                                    {'picks': 40, 'more_pct': -0.07, 'swing_cut_pct': -3}))
    assert 'made 0.07% a pick less than the unhedged one and swung 3% more.' in bad
    for line in (good, bad):
        assert line.endswith('On the 379-pick replay it swung 18% less and made 0.11% a pick less, which '
                             'failed its registered test (day-130). Never sized, never recorded.')
    # no record yet (a reset, or too few picks): the line still prints, without a number
    none = T.hedge_line({'picks': [pick('LONG', 'SHOP.TO')],
                         'hedge': {'side': 'LONG', 'market': 'XIU.TO', 'record': None,
                                   'legs': [{'ticker': 'SHOP.TO', 'etf': 'XIT.TO'}]}})
    assert 'On the record so far' not in none and 'failed its registered test (day-130)' in none


def test_the_line_is_rendered_from_the_frozen_hedge_only():
    """A publication from before day-148c carries no `hedge` and renders as it did."""
    old = {'picks': [pick('LONG', 'SHOP.TO')]}
    assert T.hedge_line(old) is None and T.hedge_short(old) is None
    assert T.hedge_line({'picks': [pick('LONG', 'SHOP.TO')], 'hedge': {'side': 'LONG', 'legs': []}}) is None
    assert T.hedge_line({'picks': [pick('LONG', 'SHOP.TO')], 'hedge': 'yes'}) is None


def test_the_switch_off_restores_the_section(monkeypatch):
    monkeypatch.setattr(T, 'HEDGE', False)
    sec = {'picks': [pick('LONG', 'SHOP.TO')]}
    assert T.with_hedge(sec, RECORD) is sec and T.hedge_line(sec) is None


def test_a_fault_costs_the_line_never_the_section(monkeypatch):
    import execution_lab
    import exposure
    sec = {'picks': [pick('LONG', 'SHOP.TO')]}
    monkeypatch.setattr(execution_lab, 'hedge_record', lambda rows=None: 1 / 0)
    got = T.with_hedge(sec)                        # the record could not be read: no number
    assert got['hedge']['record'] is None and 'On the record so far' not in T.hedge_line(got)
    monkeypatch.setattr(exposure, 'load_sectors', lambda path=None: 1 / 0)
    assert T.with_hedge(sec, RECORD) is sec        # the map could not be read: no line
    assert T.with_hedge(None) is None and T.with_hedge('x') == 'x'


def test_the_labs_record_counts_only_picks_measured_both_ways():
    import execution_lab as L

    def row(i, r, hedged, model='claude', kind='selected'):
        return {'session': '2026-10-%02d' % (1 + i % 28), 'model': model, 'kind': kind, 'side': 'LONG',
                'ticker': 'T%d.TO' % i, 'r': str(r), 'r_vs_etf': '' if hedged is None else str(hedged)}
    rows = [row(i, 2.0 if i % 2 else -2.0, 1.2 if i % 2 else -0.8) for i in range(40)]
    rows += [row(100 + i, 5.0, None) for i in range(10)]                    # no fund: not counted
    rows += [row(200 + i, 9.0, 9.0, model='engine', kind='board') for i in range(10)]     # not a model pick
    rows += [row(300 + i, 9.0, 9.0, kind='nominated') for i in range(10)]   # a forced nomination
    got = L.hedge_record(rows)
    assert got == {'picks': 40, 'more_pct': 0.2, 'swing_cut_pct': 50}
    assert L.hedge_record(rows[:L.HEDGE_MIN - 1]) is None and L.hedge_record([]) is None
    # the evening review's table is the same population
    assert '| Hedged with its sector ETF | 40 |' in '\n'.join(L.table(rows))


@pytest.mark.day144
@pytest.mark.day146
def test_the_run_rule_emptying_a_slot_brings_the_hedge_under_the_pick(monkeypatch):
    """11-09: Claude's shorts both followed three-day runs, so LONG stood alone."""
    import council_flash
    import execution_lab
    import email_render
    import report_page
    monkeypatch.setattr(execution_lab, 'hedge_record', lambda rows=None: RECORD)
    s = led_snap()
    s['runs'] = {'SU.TO': {'run': -3, 'as_of': '2026-11-06', 'dates': [], 'changes_pct': [-1, -1, -1]},
                 'TD.TO': {'run': -5, 'as_of': '2026-11-06', 'dates': [], 'changes_pct': [-1] * 5},
                 'CNQ.TO': {'run': 0, 'as_of': '2026-11-06', 'dates': [], 'changes_pct': []}}
    plain = K.top_two(s, previous={})
    assert [p['ticker'] for p in plain['picks']] == ['CNQ.TO'] and 'hedge' not in plain
    sec = T.with_hedge(plain)
    lines = T.table(sec, concise=True)
    row = next(i for i, x in enumerate(lines) if x.startswith('| 1 | LONG CNQ.TO'))
    assert lines[row + 1].startswith('⚠ Only a LONG stands today, so LONG CNQ.TO is also a bet')
    assert 'short XEG.TO, its sector fund, or XIU.TO' in lines[row + 1]
    assert lines.count(lines[row + 1]) == 1
    # the picks, the status, the rule and the reason are untouched
    assert {k: v for k, v in sec.items() if k != 'hedge'} == plain
    # the flash: body and hero, as a caution
    snap = {**s, 'asked_at': '2026-11-09T08:58:00-05:00'}
    subj, body, html = council_flash.compose(snap, dt.datetime(2026, 11, 9, 8, 59, tzinfo=K.ET))
    assert lines[row + 1] in body and 'Only a LONG stands today: it is also a bet on the market.' in html
    assert 'hedge' not in subj.lower()             # the subject names picks, never the hedge
    assert email_render.CAUTION in html
    # the report email's hero and the page
    report = {'session': '2026-11-09', 'report_status': 'ON_TIME',
              'intraday': {'desks': [{'id': 'claude', 'legs': []}], 'top_two': sec}}
    assert 'Hedge (shown, not a pick): short XEG.TO' in email_render._hero(report)
    page = report_page._top_two_section({'top_two': sec})
    assert page.count('Only a LONG stands today, so LONG CNQ.TO') == 1
    # a section from before day-148c reads as it did, everywhere
    assert 'Hedge (shown' not in '\n'.join(T.table(plain, concise=True))
    assert 'Hedge (shown' not in email_render._hero({**report, 'intraday': {**report['intraday'],
                                                                           'top_two': plain}})
    assert 'Hedge (shown' not in report_page._top_two_section({'top_two': plain})


@pytest.mark.day144
@pytest.mark.day146
def test_a_long_and_a_short_carry_no_hedge(monkeypatch):
    import council_flash
    sec = T.with_hedge(K.top_two(led_snap(), previous={}), RECORD)
    assert 'hedge' not in sec and len(sec['picks']) == 2
    snap = {**led_snap(), 'asked_at': '2026-11-09T08:58:00-05:00'}
    _, body, html = council_flash.compose(snap, dt.datetime(2026, 11, 9, 8, 59, tzinfo=K.ET))
    assert 'Hedge (shown' not in body and 'Hedge (shown' not in html


@pytest.mark.day144
@pytest.mark.day146
def test_the_open_check_says_it_too(monkeypatch):
    import council_flash
    import execution_lab
    monkeypatch.setattr(execution_lab, 'hedge_record', lambda rows=None: RECORD)
    snap = {**led_snap({'longs': CLAUDE['longs'], 'shorts': []}), 'asked_at': '2026-11-09T08:58:00-05:00'}
    now = dt.datetime(2026, 11, 9, 9, 31, tzinfo=K.ET)
    rows = [{**p, 'verdict': 'STILL VALID', 'price': 41.0, 'at': '09:31', 'open_for_pick': 0.4,
             'open_days': None, 'now_for_pick': 0.3, 'etf': 'XEG.TO', 'etf_move': 0.1, 'reach': None}
            for p in K.top_two(snap, previous={})['picks']]
    assert [r['ticker'] for r in rows] == ['CNQ.TO']
    subj, text, html = council_flash.compose_open(snap, rows, now)
    assert 'Only a LONG stands today, so LONG CNQ.TO is also a bet' in text
    assert 'Only a LONG stands today: it is also a bet on the market.' in html
    assert 'hedge' not in subj.lower()


@pytest.mark.day144
@pytest.mark.day146
def test_the_hedge_is_never_recorded(monkeypatch):
    import model_picks as M
    plain = K.top_two(led_snap({'longs': CLAUDE['longs'], 'shorts': []}), previous={})
    sec = T.with_hedge(plain, RECORD)
    assert 'hedge' in sec
    with_ = M.rows_from_report({'session': '2026-11-09', 'intraday': {'top_two': sec}})
    without = M.rows_from_report({'session': '2026-11-09', 'intraday': {'top_two': plain}})
    assert with_ == without
    assert not any('XEG' in str(r.get('ticker')) or 'XIU' in str(r.get('ticker')) for r in with_)



@pytest.mark.day144
@pytest.mark.day146
def test_a_malformed_frozen_hedge_costs_the_line_alone():
    sec = K.top_two(led_snap({'longs': CLAUDE['longs'], 'shorts': []}), previous={})
    bad = {**sec, 'hedge': {'side': 'LONG', 'legs': ['CNQ.TO'], 'market': 'XIU.TO'}}
    assert T.hedge_line(bad) is None and T.hedge_short(bad) is None
    lines = T.table(bad, concise=True)
    assert any(x.startswith('| 1 | LONG CNQ.TO') for x in lines)
    assert not any('Hedge (shown' in x for x in lines)
