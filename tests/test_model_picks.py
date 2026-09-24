"""Every model pick recorded, every pick scored — the track record that the
report has said 'does not exist' every morning since 2026-09-17."""
import datetime as dt

import pandas as pd
import pytest

import model_picks as M

ET = dt.timezone(dt.timedelta(hours=-4))


def bars(day='2026-09-22', entry=100.0, exit_=101.0, low=99.0, high=102.0):
    idx = pd.date_range(f'{day} 09:30', f'{day} 15:55', freq='5min', tz='America/Toronto')
    close = [entry] * len(idx)
    close[-1] = exit_
    return pd.DataFrame({'Open': close, 'High': [high]*len(idx), 'Low': [low]*len(idx),
                         'Close': close, 'Volume': [1]*len(idx)}, index=idx)


def report():
    return {'session': '2026-09-22', 'intraday': {
        'opportunities': {'status': 'READY', 'longs': [{'ticker': 'A.TO', 'confidence': 0.6,
                                                        'invalid_at': 99.5}],
                          'shorts': [{'ticker': 'B.TO', 'confidence': 0.55}]},
        'jev': {'status': 'NO_OPPORTUNITY', 'longs': [], 'shorts': [],
                'forced_long': {'ticker': 'C.TO', 'probability': 0.4,
                                'gated_abstain_probability': 0.6}, 'forced_short': None}}}


def test_selected_and_forced_are_recorded_separately():
    rows = M.rows_from_report(report())
    kinds = {(r['model'], r['kind'], r['ticker']) for r in rows}
    assert kinds == {('deepseek', 'selected', 'A.TO'), ('deepseek', 'selected', 'B.TO'),
                     ('jev', 'forced', 'C.TO')}


def test_the_ledger_is_append_only(tmp_path):
    path = tmp_path / 'picks.csv'
    assert M.append(M.rows_from_report(report()), path) == 3
    assert M.append(M.rows_from_report(report()), path) == 0
    assert len(M.read(path)) == 3


def test_a_long_and_a_short_are_scored_with_the_right_sign(tmp_path):
    path = tmp_path / 'picks.csv'
    M.append(M.rows_from_report(report()), path)
    after_close = dt.datetime(2026, 9, 22, 16, 30, tzinfo=ET)
    assert M.score(path, now=after_close, bars_for=lambda t: bars()) == 3
    rows = {r['ticker']: r for r in M.read(path)}
    assert float(rows['A.TO']['r_pct']) == pytest.approx(1.0) and rows['A.TO']['hit'] == '1'
    assert float(rows['B.TO']['r_pct']) == pytest.approx(-1.0) and rows['B.TO']['hit'] == '0'
    # A.TO's own invalidation level 99.5 was traded through (low 99.0).
    assert rows['A.TO']['invalidated'] == '1'


def test_nothing_is_scored_before_the_close(tmp_path):
    path = tmp_path / 'picks.csv'
    M.append(M.rows_from_report(report()), path)
    midday = dt.datetime(2026, 9, 22, 13, 0, tzinfo=ET)
    assert M.score(path, now=midday, bars_for=lambda t: bars()) == 0


def test_a_session_with_missing_bars_is_never_partially_scored(tmp_path):
    path = tmp_path / 'picks.csv'
    M.append(M.rows_from_report(report()), path)
    b = bars().drop(pd.Timestamp('2026-09-22 15:55', tz='America/Toronto'))
    after = dt.datetime(2026, 9, 22, 16, 30, tzinfo=ET)
    assert M.score(path, now=after, bars_for=lambda t: b) == 0


def test_the_scorecard_prints_its_interval_and_says_coin_flip_when_it_is():
    rows = [{'model': 'deepseek', 'kind': 'selected', 'session': f'2026-09-{d}', 'hit': h,
             'r_pct': '0.5' if h == '1' else '-0.5', 'scored_at': 'x', 'invalidated': ''}
            for d, h in (('22', '1'), ('23', '0'), ('24', '1'))]
    card = M.scorecard(rows)
    line = M.scorecard_line(card, 'deepseek_selected', 'DeepSeek')
    assert '2/3' in line and 'coin flip' in line and 'Proxy' in line


def test_no_record_is_said_plainly():
    assert 'no pick has been scored yet' in M.scorecard_line({}, 'jev_selected', 'Jev')


def test_the_record_reaches_both_renderers():
    import daily_render, report_page
    snap = {'status': 'READY', 'model': 'm', 'considered': 1, 'longs': [], 'shorts': [],
            'comparison': {}, 'track_record': ['DeepSeek track record: 3/5 picks right']}
    assert 'DeepSeek track record: 3/5' in '\n'.join(daily_render.opportunities_summary({'opportunities': snap}))
    assert 'DeepSeek track record: 3/5' in report_page._exposure(snap, 'DeepSeek')


def test_claude_picks_are_recorded_as_their_own_source():
    """Claude's desk is scored on the same yardstick, under its own name —
    never pooled with DeepSeek's, which answers the same question."""
    r = report()
    r['intraday']['claude'] = {'status': 'READY', 'route': 'session',
                               'longs': [{'ticker': 'CNQ.TO', 'confidence': 0.57,
                                          'invalid_at': 44.1}], 'shorts': []}
    rows = [x for x in M.rows_from_report(r) if x['model'] == 'claude']
    assert [(x['kind'], x['side'], x['ticker']) for x in rows] == [('selected', 'LONG', 'CNQ.TO')]
    assert rows[0]['invalid_at'] == 44.1
    r['intraday']['claude'] = {'status': 'UNAVAILABLE', 'longs': [{'ticker': 'X.TO'}]}
    assert not [x for x in M.rows_from_report(r) if x['model'] == 'claude']


def test_a_late_pick_is_scored_from_its_own_bar_not_from_0945():
    import datetime as dt
    import pandas as pd
    import model_picks as M
    idx = pd.date_range('2026-09-24 09:30', '2026-09-24 15:55', freq='5min', tz='America/New_York')
    close = [100.0] * len(idx)
    close[list(idx.strftime('%H:%M')).index('09:40')] = 90.0     # the 09:45 bar
    close[list(idx.strftime('%H:%M')).index('10:10')] = 110.0    # when the late pick was sent
    bars = pd.DataFrame({'Open': close, 'High': close, 'Low': close, 'Close': close}, index=idx)
    base = {'session': '2026-09-24', 'side': 'LONG', 'ticker': 'X'}
    assert M.score_one(base, bars)['entry'] == 90.0
    late = M.score_one({**base, 'entry_time': '10:10'}, bars)
    assert late['entry'] == 110.0 and late['hit'] is False


def test_basis_is_recorded_and_carded_only_for_the_registered_population():
    import model_picks as M
    rows = [{'model': 'claude', 'kind': 'selected', 'basis': 'news', 'scored_at': 'x', 'hit': '1', 'r_pct': '1', 'session': 'a'},
            {'model': 'deepseek', 'kind': 'selected', 'basis': 'technical', 'scored_at': 'x', 'hit': '0', 'r_pct': '-1', 'session': 'a'},
            {'model': 'claude', 'kind': 'late', 'basis': 'news', 'scored_at': 'x', 'hit': '0', 'r_pct': '-1', 'session': 'a'},
            {'model': 'jev', 'kind': 'selected', 'basis': 'news', 'scored_at': 'x', 'hit': '0', 'r_pct': '-1', 'session': 'a'}]
    card = M.basis_card(rows)
    assert card['news']['picks'] == 1 and card['news']['hits'] == 1
    assert card['technical']['picks'] == 1
    assert 'basis' in M.FIELDS and 'entry_time' in M.FIELDS
