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


def test_the_sector_question_is_never_a_lesson():
    """Day-132c: the sector's 09:45 → close move is part of the result, not
    something known at entry. It read t = 4.0 over 10 days on 2026-10-14 and
    would have been reported as a LESSON at 20."""
    rows = []
    for d in range(25):
        s = f'2026-10-{d + 1:02d}'
        rows += [dict(session=s, section='Desk', ticker='A', side='LONG', gap=0, first15=0,
                      sector_r=1.0, r_pct=1.0 + 0.1 * (d % 3)),
                 dict(session=s, section='Desk', ticker='B', side='LONG', gap=0, first15=0,
                      sector_r=-1.0, r_pct=-1.0)]
    q = {x['question']: x for x in dr.lessons(rows)}[dr.SECTOR_QUESTION]
    assert q['days'] == 25 and q['t'] > dr.LESSON_T and q['verdict'] == dr.SAME_WINDOW
    assert 'never a lesson' in dr.markdown('2026-10-25', [], None, dr.lessons(rows), None)


def test_vs_sector_separates_the_name_from_its_sector(tmp_path):
    """2026-09-30: TD long lost 0.75% while its banks lost ~0.7% — a sector
    move, not a stock-picking miss. The review must show both numbers."""
    peers = {'P1.TO': bars(1, 1, 1, 0.99), 'P2.TO': bars(1, 1, 1, 0.99), **BARS}
    out = dr.review(DAY, REPORT, bars_for=peers.__getitem__, root=tmp_path,
                    sector_map={'AAA.TO': 'X', 'P1.TO': 'X', 'P2.TO': 'X'})
    a = next(r for r in out['rows'] if r['ticker'] == 'AAA.TO' and r['section'] == 'Desk')
    assert a['vs_sector'] == round(a['r_pct'] + 1.0, 3)        # long, peers -1%
    assert 'beat by' in dr.why(a) and 'Mean vs sector' in out['markdown']


# ── day-137 M1: the council against its own table ───────────────────────────

def council_report(session, picks=('P1',)):
    """A frozen council: P1 picked by all three members, P2 endorsed by two, P3 by one."""
    rows = [{'id': 'P1', 'ticker': 'AAA.TO', 'side': 'LONG', 'endorse': ['A', 'B', 'C'], 'oppose': []},
            {'id': 'P2', 'ticker': 'BBB.TO', 'side': 'SHORT', 'endorse': ['A', 'B'], 'oppose': ['C']},
            {'id': 'P3', 'ticker': 'CCC.TO', 'side': 'LONG', 'endorse': ['A'], 'oppose': ['B']}]
    return {'session': session, 'intraday': {'council': {
        'picks': list(picks), 'tally': {'members': ['A', 'B', 'C'], 'rows': rows}}}}


def ledger(session, results):
    return [{'session': session, 'model': 'gemini', 'kind': 'nominated', 'ticker': t, 'side': s,
             'r_pct': '' if r is None else str(r)} for (t, s), r in results.items()]


def test_the_table_is_scored_from_the_record_and_split_by_the_council_choice():
    got = dr.council_table(council_report(DAY), ledger(DAY, {
        ('AAA.TO', 'LONG'): -1.0, ('BBB.TO', 'SHORT'): 0.5, ('CCC.TO', 'LONG'): None,
        ('CCC.TO', 'SHORT'): 9.0}))                       # the other side is another position
    assert got['members'] == 3
    assert [(p['ticker'], p['picked'], p['unanimous'], p['r_pct']) for p in got['positions']] == [
        ('AAA.TO', True, True, -1.0), ('BBB.TO', False, False, 0.5), ('CCC.TO', False, False, None)]
    assert dr.council_table({'session': DAY, 'intraday': {}}, []) is None


def test_the_running_record_compares_picks_with_the_whole_table(tmp_path):
    for d, (pick, rest) in enumerate([(-1.0, 1.0), (0.2, 0.0), (-0.5, 0.5)]):
        s = f'2026-10-{d + 1:02d}'
        doc = {'session': s, 'rows': [],
               'council_table': dr.council_table(council_report(s), ledger(s, {
                   ('AAA.TO', 'LONG'): pick, ('BBB.TO', 'SHORT'): rest, ('CCC.TO', 'LONG'): rest}))}
        (tmp_path / f'{s}.json').write_text(json.dumps(doc))
    picked, unanimous = dr.table_record(tmp_path)
    assert [round(d['r_pct'], 3) for d in picked] == [-1.333, 0.133, -0.667]   # pick minus table mean
    assert [round(d['r_pct'], 3) for d in unanimous] == [-2.0, 0.2, -1.0]
    text = dr.table_section('2026-10-04', council_report('2026-10-04'), root=tmp_path,
                            ledger_rows=ledger('2026-10-04', {('AAA.TO', 'LONG'): -0.5}))
    assert 'The council against its own table' in text
    assert 'Record: 3 session(s)' in text and 'no verdict before 40 sessions' in text
    assert 'Counted, not a rule.' in text


def test_the_table_readout_never_costs_the_review(tmp_path):
    def broken():
        raise OSError('no ledger')
    text = dr.table_section(DAY, council_report(DAY), root=tmp_path, ledger_rows=type(
        'L', (), {'__iter__': lambda self: broken()})())
    assert 'unavailable (OSError)' in text
