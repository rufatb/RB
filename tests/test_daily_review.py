"""The evening review: every printed pick scored on one yardstick, explained from
measured facts, and a 'lesson' only when it survives across days."""
import datetime as dt
import json

import pandas as pd

import daily_review as dr

DAY = '2026-09-29'


def bars(prev, open_, entry, close, hi=None, lo=None):
    """A prior-day close and one session of 5-minute bars on the ET clock."""
    idx = [pd.Timestamp('2026-09-28 15:55')]
    rows = [dict(Open=prev, High=prev, Low=prev, Close=prev)]
    t = pd.Timestamp(f'{DAY} 09:30')
    while t <= pd.Timestamp(f'{DAY} 15:55'):
        c = open_ if t.time() < dt.time(9, 40) else entry if t.time() == dt.time(9, 40) else close
        rows.append(dict(Open=open_ if t.time() == dt.time(9, 30) else c, High=c, Low=c, Close=c))
        idx.append(t)
        t += pd.Timedelta(minutes=5)
    df = pd.DataFrame(rows, index=idx)
    if hi is not None:
        df.loc[pd.Timestamp(f'{DAY} 12:00'), 'High'] = hi
    if lo is not None:
        df.loc[pd.Timestamp(f'{DAY} 12:00'), 'Low'] = lo
    return df


REPORT = {'session': DAY, 'intraday': {
    'top_two': {'picks': [{'ticker': 'AAA.TO', 'side': 'LONG', 'models': ['deepseek'], 'agreement': '1 of 3'}]},
    'desks': [{'id': 'claude', 'legs': [
        {'ticker': 'AAA.TO', 'side': 'LONG', 'confidence': 0.52, 'baseline_shares': 100, 'invalid_at': 9.0},
        {'ticker': 'BBB.TO', 'side': 'SHORT', 'confidence': 0.53, 'baseline_shares': 50, 'invalid_at': 19.0}]}],
    'jev': {'forced_long': {'ticker': 'CCC.TO', 'probability': 0.4}, 'forced_short': None},
    'debate': {'final': [], 'rulings': [{'ticker': 'BBB.TO', 'side': 'SHORT', 'verdict': 'REJECT'}]},
    'deepseek': {'assessments': [{'ticker': 'AAA.TO', 'directional_lean': 'NEUTRAL'}]},
}}

BARS = {'AAA.TO': bars(10, 10.2, 10.3, 10.5),        # long, open agreed, +1.94%
        'BBB.TO': bars(20, 20.5, 20.4, 20.8),        # short, open against, 'wrong if' 19 crossed
        'CCC.TO': bars(5, 5, 5, 4.9),
        'XIU.TO': bars(40, 40, 40, 40.4)}


def run(tmp_path, bars_for=None, **kw):
    return dr.review(DAY, REPORT, bars_for=bars_for or BARS.__getitem__, root=tmp_path,
                     sector_map={}, **kw)


def test_every_printed_pick_is_collected_with_its_section():
    got = [(p['section'], p['model'], p['side'], p['ticker']) for p in dr.picks_of(REPORT)]
    assert got == [('Top 2', 'deepseek', 'LONG', 'AAA.TO'),
                   ('Desk', 'claude', 'LONG', 'AAA.TO'),
                   ('Desk', 'claude', 'SHORT', 'BBB.TO'),
                   ('Desk', 'jev forced', 'LONG', 'CCC.TO'),
                   ('Debate ruling', 'REJECT', 'SHORT', 'BBB.TO')]   # NEUTRAL lean is not a pick


def test_scored_signed_and_explained(tmp_path):
    out = run(tmp_path)
    by = {(r['section'], r['ticker']): r for r in out['rows']}
    a, b = by[('Desk', 'AAA.TO')], by[('Desk', 'BBB.TO')]
    assert a['r_pct'] == round((10.5 / 10.3 - 1) * 100, 3) and a['pnl_cad'] == 20.0
    assert b['r_pct'] < 0 and b['pnl_cad'] == -20.0      # short, price rose 0.4 x 50
    assert b['crossed'] is True and a['crossed'] is False
    assert b['gap'] < 0 and a['gap'] > 0                  # signed to the pick's side
    assert 'already crossed' in dr.why(b) and dr.why(b).startswith('WRONG')
    assert json.loads((tmp_path / f'{DAY}.json').read_text())['market_pct'] == 1.0


def test_a_failed_fetch_is_reported_not_swallowed(tmp_path):
    def flaky(t):
        if t == 'CCC.TO':
            raise TimeoutError
        return BARS[t]
    out = run(tmp_path, bars_for=flaky)
    assert out['failures'] == {'CCC.TO': 'TimeoutError'}
    assert 'LONG CCC.TO' in out['unscored'] and 'CCC.TO (TimeoutError)' in out['markdown']


def test_sector_is_peer_median_signed_to_the_pick(tmp_path):
    peers = {'P1.TO': bars(1, 1, 1, 1.01), 'P2.TO': bars(1, 1, 1, 1.03), **BARS}
    out = dr.review(DAY, REPORT, bars_for=peers.__getitem__, root=tmp_path,
                    sector_map={'BBB.TO': 'X', 'P1.TO': 'X', 'P2.TO': 'X'})
    b = next(r for r in out['rows'] if r['ticker'] == 'BBB.TO' and r['section'] == 'Desk')
    assert b['sector_r'] == -2.0                           # peers +2% median, pick is SHORT


def test_one_day_never_makes_a_lesson_and_duplicates_count_once(tmp_path):
    out = run(tmp_path)
    q = {x['question']: x for x in out['learn']}
    assert all(x['verdict'] != 'LESSON' for x in out['learn'])
    # AAA.TO long appears as Top 2 and as a desk pick: one outcome, counted once.
    assert q["today's open agreed with the pick"]['yes']['n'] == 1
    # CCC.TO has no 'wrong if': excluded from that question, not counted as 'no'.
    crossed = q["its 'wrong if' was NOT already crossed at entry (day-120 E1)"]
    assert crossed['yes']['n'] == 1 and crossed['no']['n'] == 1


def test_a_lesson_needs_the_bar_across_many_days():
    rows = []
    for d in range(25):
        s = f'2026-10-{d + 1:02d}'
        rows += [dict(session=s, section='Desk', ticker='A', side='LONG', gap=1, first15=0,
                      r_pct=1.0 + 0.1 * (d % 3)),
                 dict(session=s, section='Desk', ticker='B', side='LONG', gap=-1, first15=0,
                      r_pct=-1.0)]
    q = dr.lessons(rows)[1]
    assert q['days'] == 25 and q['t'] > dr.LESSON_T and q['verdict'] == 'LESSON'
    assert dr.lessons(rows[:2 * (dr.MIN_DAYS - 1)])[1]['verdict'] == 'not established'
