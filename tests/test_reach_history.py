"""Day-141 (PREREGISTER_day141_reach_history.md): a stop within reach, tested
on the record — the population, the gate's labels, the planted control and
the verdict, on synthetic records, no network."""
import random

import reach_history as R


def row(session, model, kind, ticker, side, r, invalid=None, entry=100.0):
    return {'session': session, 'model': model, 'kind': kind, 'ticker': ticker, 'side': side,
            'invalid_at': '' if invalid is None else str(invalid), 'entry': str(entry),
            'r_pct': '' if r is None else str(r)}


def test_the_population_is_the_registered_one():
    rows = [row('2026-09-17', 'claude', 'selected', 'AAA.TO', 'LONG', 0.5),
            row('2026-10-23', 'gemini', 'nominated', 'BBB.TO', 'SHORT', -0.2),
            row('2026-09-16', 'deepseek', 'selected', 'CCC.TO', 'LONG', 0.1),     # before
            row('2026-10-26', 'deepseek', 'selected', 'CCC.TO', 'LONG', 0.1),     # after
            row('2026-10-01', 'jev', 'forced', 'DDD.TO', 'LONG', 0.3),            # Jev
            row('2026-10-01', 'claude', 'late', 'DDD.TO', 'LONG', 0.3),           # late
            row('2026-10-01', 'top2', 'pick', 'DDD.TO', 'LONG', 0.3),             # Top 2
            row('2026-10-01', 'deepseek', 'selected', 'EEE.TO', 'LONG', None)]    # unscored
    got = R.population(rows)
    assert [(p['session'], p['ticker']) for p in got] == [('2026-09-17', 'AAA.TO'),
                                                          ('2026-10-23', 'BBB.TO')]


def test_the_gate_labels_and_a_level_without_an_atr_is_excluded():
    picks = R.population([
        row('2026-10-01', 'claude', 'selected', 'NEAR.TO', 'LONG', 1.0, invalid=98.0),   # 2% away
        row('2026-10-01', 'deepseek', 'selected', 'FAR.TO', 'SHORT', 1.0, invalid=110.0),  # 10%
        row('2026-10-01', 'gemini', 'selected', 'GONE.TO', 'LONG', 1.0, invalid=101.0),  # crossed
        row('2026-10-01', 'gemini', 'nominated', 'NONE.TO', 'LONG', 1.0),               # no level
        row('2026-10-01', 'claude', 'nominated', 'BARE.TO', 'LONG', 1.0, invalid=98.0)])  # no ATR
    asked = []

    def atr(ticker, session):
        asked.append(ticker)
        return None if ticker == 'BARE.TO' else 3.0

    judged, excluded = R.label(picks, atr)
    gates = {p['ticker']: (p['gate'], p['reason']) for p in judged}
    assert gates['NEAR.TO'] == ('kept', '')
    assert gates['FAR.TO'][0] == 'dropped' and 'normal days away' in gates['FAR.TO'][1]
    assert gates['GONE.TO'] == ('dropped', 'wrong-if already crossed at the 09:45 entry')
    assert gates['NONE.TO'] == ('dropped', 'no wrong-if')
    assert [p['ticker'] for p in excluded] == ['BARE.TO']
    assert 'NONE.TO' not in asked            # a pick with no level needs no ATR


def synthetic(sessions, kept_y, dropped_y, wobble=0.3, seed=7):
    rng = random.Random(seed)
    out = []
    for i in range(sessions):
        s = '2026-09-%02d' % (1 + i) if i < 28 else '2026-10-%02d' % (i - 27)
        for j in range(2):
            out.append({'session': s, 'model': 'claude', 'kind': 'selected', 'ticker': 'K%d' % j,
                        'side': 'LONG', 'y': kept_y + rng.gauss(0, wobble), 'gate': 'kept',
                        'invalid_at': 1.0})
            out.append({'session': s, 'model': 'gemini', 'kind': 'selected', 'ticker': 'D%d' % j,
                        'side': 'LONG', 'y': dropped_y + rng.gauss(0, wobble), 'gate': 'dropped',
                        'invalid_at': None})
    return out


def test_the_planted_control_measures_the_edge_alone():
    picks = synthetic(20, 5.0, -3.0)                 # a huge real gap must not leak in
    diff, t = R.control(picks)
    assert abs(diff - R.PLANT) < 1e-9 and t is not None


def test_the_verdict_reads_the_registered_bar():
    strong = R.verdict(synthetic(20, 1.0, -1.0))
    assert strong['status'] == 'PASS' and strong['control']['detected']
    assert R.verdict(synthetic(20, -1.0, 1.0))['status'] == 'FAIL'
    # positive but far short, with a control the sample can see: NULL
    noisy = synthetic(20, 0.05, 0.0, wobble=0.3)
    assert R.verdict(noisy)['status'] == 'NULL'
    # positive, but on a sample too small and noisy to see a planted 1%: UNDERPOWERED
    tiny = synthetic(4, 20.0, 0.0, wobble=9.0)
    v = R.verdict(tiny)
    assert not v['control']['detected'] and v['status'] == 'UNDERPOWERED'


def test_a_position_is_kept_when_any_proposer_is_in_reach():
    picks = [{'session': '2026-10-01', 'ticker': 'AAA.TO', 'side': 'LONG', 'y': 1.0,
              'gate': 'dropped', 'model': 'claude', 'kind': 'nominated'},
             {'session': '2026-10-01', 'ticker': 'AAA.TO', 'side': 'LONG', 'y': 1.0,
              'gate': 'kept', 'model': 'gemini', 'kind': 'selected'}]
    got = R.positions(picks)
    assert len(got) == 1 and got[0]['gate'] == 'kept' and got[0]['proposers'] == 2
