"""Day-155b: the news desk's top two by its own score (newsdesk_confidence.py).

Synthetic ledgers only: these check the machinery, never the record."""
import random
import re

import pytest

import news_desk
import newsdesk_confidence as N


def row(session, ticker, side='LONG', conf=0.6, material=True, w945=0.0, raw=None, arm='full',
        w_day=None):
    return {'session': session, 'ticker': ticker, 'arm': arm, 'side': side,
            'confidence': str(conf), 'material': 'True' if material else 'False',
            'w945': '' if w945 is None else str(w945),
            'w945_raw': '' if raw is None and w945 is None else str(w945 if raw is None else raw),
            'w_day': '' if w_day is None else str(w_day)}


def test_the_order_is_the_emails_own_order():
    calls = [{'side': 'LONG', 'ticker': 'BBB.TO', 'confidence': 0.6, 'material': True},
             {'side': 'SHORT', 'ticker': 'AAA.TO', 'confidence': 0.6, 'material': True},
             {'side': 'LONG', 'ticker': 'CCC.TO', 'confidence': 0.7, 'material': False},
             {'side': 'LONG', 'ticker': 'DDD.TO', 'confidence': 0.65, 'material': True},
             {'side': 'SHORT', 'ticker': 'EEE.TO', 'confidence': 0.5, 'material': False}]
    for c in calls:
        c.update(title='t', reason='r')
    sec = {'status': 'READY', 'calls': calls, 'headline': {}}
    printed = [m.group(2) for line in news_desk.lines(sec)
               if (m := re.match(r'^\| (LONG|SHORT) (\S+) \|', line))]
    ledger = [row('2026-11-24', c['ticker'], c['side'], c['confidence'], c['material']) for c in calls]
    ours = [r['ticker'] for r in N.ranked(ledger)['2026-11-24']]
    assert ours == printed == ['DDD.TO', 'AAA.TO', 'BBB.TO', 'CCC.TO', 'EEE.TO']


def test_the_top_two_come_from_every_printed_call_scored_or_not():
    rows = [row('s1', 'A.TO', conf=0.7, w945=None), row('s1', 'B.TO', conf=0.65, w945=1.0),
            row('s1', 'C.TO', conf=0.55, w945=-1.0),
            row('s2', 'A.TO', conf=0.7, w945=0.5), row('s2', 'B.TO', conf=0.6, w945=0.5)]
    prs, skipped = N.pairs(rows)
    # s1: A (unscored) and B are the top two; C is the rest. s2 has no rest.
    assert [p['session'] for p in prs] == ['s1'] and skipped == 1
    assert prs[0]['top'] == [1.0] and prs[0]['rest'] == [-1.0] and prs[0]['d'] == 2.0


def test_one_row_per_session_and_ticker_in_the_window():
    rows = [row('2026-10-01', 'A.TO'), row('2026-10-02', 'A.TO'), row('2026-10-02', 'A.TO'),
            row('2026-10-02', 'A.TO', arm='headline')]
    got, dup = N.population(rows)
    assert len(got) == 1 and dup == 1


def ledger(edge, *, sessions=40, per=6, seed=1, material_edge=0.0):
    rng = random.Random(seed)
    out = []
    for i in range(sessions):
        s = f'2026-{10 + i // 28:02d}-{1 + i % 28:02d}'
        for j in range(per):
            top = j < 2
            mat = j < 4
            y = rng.gauss(0, 1.0) + (edge if top else 0.0) + (material_edge if mat else 0.0)
            out.append(row(s, f'T{j}.TO', conf=0.7 if top else 0.55, material=mat, w945=round(y, 4)))
    return out


def test_h1_finds_a_planted_top_two_edge():
    prs, _ = N.pairs(ledger(1.5))
    got = N.h1(prs, draws=500)
    assert got['status'] == 'TOP2_BETTER' and got['t'] >= 3 and got['control']['detected']


def test_h1_reads_null_on_noise_and_worse_on_a_negative_edge():
    prs, _ = N.pairs(ledger(0.0, seed=2))
    assert N.h1(prs, draws=500)['status'] in ('NULL', 'UNDERPOWERED')
    prs, _ = N.pairs(ledger(-1.5, seed=3))
    assert N.h1(prs, draws=500)['status'] == 'TOP2_WORSE'


def test_h1_needs_the_top_two_to_clear_the_cost():
    rows = ledger(1.5)
    for r in rows:                      # shift every call down so the top two lose net
        r['w945'] = str(float(r['w945']) - 1.6)
    prs, _ = N.pairs(rows)
    got = N.h1(prs, draws=500)
    assert got['t'] >= 3 and got['top_two']['mean'] < N.COST and got['status'] != 'TOP2_BETTER'


def test_the_h1_control_is_edge_over_se():
    ds = [0.3, -0.2, 0.5, -0.4, 0.1, 0.0, 0.2, -0.3]
    import statistics as st
    se = st.stdev(ds) / len(ds) ** 0.5
    assert N.control_h1(ds)['t'] == pytest.approx(N.PLANT / se, abs=0.01)


def test_h2_finds_a_planted_material_edge():
    got = N.h2(ledger(0.0, material_edge=1.5, seed=4), draws=500)
    assert got['status'] == 'MATERIAL_BETTER' and got['control']['detected']


def test_h2_reads_null_on_noise():
    assert N.h2(ledger(0.0, seed=5), draws=500)['status'] in ('NULL', 'UNDERPOWERED')


def test_xiu_is_recovered_from_raw_and_hedged_outcomes():
    long_ = row('s', 'A.TO', 'LONG', w945=0.42, raw=0.07)
    short = row('s', 'B.TO', 'SHORT', w945=0.28, raw=0.63)
    assert N.xiu_945(long_) == pytest.approx(-0.35)
    assert N.xiu_945(short) == pytest.approx(-0.35)


def test_spearman_ranks_ties_by_their_average():
    assert N.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert N.spearman([1, 1, 2, 2], [4, 3, 2, 1]) < 0
