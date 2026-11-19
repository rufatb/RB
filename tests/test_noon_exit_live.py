"""Day-153 (PREREGISTER_day153_noon_exit_live.md): the noon-exit test's
machinery, on synthetic rows only. No real lab row is read here."""
import random

import noon_exit_live as N


def _row(session, model, kind, ticker, side, r, r_noon, **kw):
    return {'session': session, 'model': model, 'kind': kind, 'ticker': ticker, 'side': side,
            'r': str(r), 'r_noon': str(r_noon), **{k: str(v) for k, v in kw.items()}}


def test_the_population_is_the_live_sources_each_position_once_through_the_cut():
    rows = [
        _row('2026-11-02', 'gemini', 'selected', 'AAA.TO', 'LONG', 1.0, 0.5),
        _row('2026-11-02', 'top2', 'pick', 'AAA.TO', 'LONG', 1.0, 0.5),         # same position
        _row('2026-11-02', 'engine', 'board', 'BBB.TO', 'SHORT', 2.0, 1.0),     # the engine
        _row('2026-11-02', 'top2council', 'pick', 'CCC.TO', 'LONG', 2.0, 1.0),  # a shadow
        _row('2026-11-02', 'top2floor', 'pick', 'DDD.TO', 'LONG', 2.0, 1.0),    # a shadow
        _row('2026-11-02', 'claude', 'late', 'EEE.TO', 'LONG', 2.0, 1.0),       # a late pick
        _row('2026-11-03', 'jev', 'forced', 'FFF.TO', 'SHORT', -1.0, 0.0),
        _row('2026-11-03', 'debate', 'final', 'GGG.TO', 'LONG', 0.2, 0.1),
        _row('2026-11-18', 'deepseek', 'selected', 'HHH.TO', 'LONG', 3.0, 1.0),  # after the cut
        {**_row('2026-11-03', 'deepseek', 'selected', 'III.TO', 'LONG', 1, 1), 'r_noon': ''},
    ]
    ps, counts = N.positions(rows, cut='2026-11-17')
    assert [(p['session'], p['ticker']) for p in ps] == [
        ('2026-11-02', 'AAA.TO'), ('2026-11-03', 'FFF.TO'), ('2026-11-03', 'GGG.TO')]
    assert ps[0]['models'] == ['gemini', 'top2']
    assert counts == {'rows': 4, 'rows_missing_a_window': 1, 'positions': 3, 'sessions': 2}
    assert abs(ps[1]['d'] - 1.0) < 1e-12                    # d = r_noon - r, signed to the pick


def test_halves_hold_equal_numbers_of_sessions_and_an_odd_middle_sits_out():
    ps = [{'session': '2026-10-%02d' % (k + 1), 'r': 0.0, 'r_noon': 0.0, 'd': 0.0} for k in range(5)]
    a, b, middle = N.halves(ps)
    assert [p['session'] for p in a] == ['2026-10-01', '2026-10-02']
    assert [p['session'] for p in b] == ['2026-10-04', '2026-10-05']
    assert middle == '2026-10-03'
    a, b, middle = N.halves(ps[:4])
    assert len(a) == len(b) == 2 and middle is None


def _synthetic(n_sessions, per, *, close_sd, noon_sd, d_mean, seed=0):
    rng = random.Random(seed)
    rows = []
    for s in range(n_sessions):
        session = '%04d-%02d-%02d' % (2020 + s // 336, 1 + (s // 28) % 12, 1 + s % 28)
        for k in range(per):
            noon = rng.gauss(0, noon_sd)
            close = noon - d_mean + rng.gauss(0, (max(close_sd ** 2 - noon_sd ** 2, 0.01)) ** 0.5)
            rows.append(_row(session, 'gemini', 'selected', 'T%02d.TO' % k, 'LONG', close, noon))
    return rows


def test_the_verdict_reads_the_registered_bar():
    # noon swings much less and costs nothing, on a large, quiet record: CONFIRMED
    ps, _ = N.positions(_synthetic(200, 10, close_sd=2.0, noon_sd=1.2, d_mean=0.0), cut='2099-01-01')
    v = N.verdict(ps, draws=300)
    assert v['verdict'] == 'CONFIRMED', v
    assert v['control']['t_planted'] >= 3 and v['bootstrap']['p5'] > 1.0
    # noon costs money, clearly: WORSE
    ps, _ = N.positions(_synthetic(200, 10, close_sd=2.0, noon_sd=1.2, d_mean=-0.6), cut='2099-01-01')
    v = N.verdict(ps, draws=300)
    assert v['verdict'] == 'WORSE' and v['worse']
    # the same swing either way: NOT_CONFIRMED
    ps, _ = N.positions(_synthetic(200, 10, close_sd=1.5, noon_sd=1.5, d_mean=0.0, seed=3),
                        cut='2099-01-01')
    v = N.verdict(ps, draws=300)
    assert v['verdict'] in ('NOT_CONFIRMED', 'WORSE') and not v['legs']['swing']
    # too few, too noisy positions to see a planted 0.20%: UNDERPOWERED
    ps, _ = N.positions(_synthetic(6, 2, close_sd=6.0, noon_sd=3.0, d_mean=0.0), cut='2099-01-01')
    v = N.verdict(ps, draws=300)
    assert v['control']['t_planted'] < 3 and v['verdict'] == 'UNDERPOWERED'


def test_the_control_is_the_planted_cost_over_its_standard_error():
    ps, _ = N.positions(_synthetic(40, 5, close_sd=2.0, noon_sd=1.5, d_mean=0.3), cut='2099-01-01')
    v = N.verdict(ps, draws=100)
    assert abs(v['control']['t_planted'] - N.PLANTED / v['full']['se']) < 0.02
    assert abs(v['control']['mde_pct'] - 2.8 * v['full']['se']) < 1e-3


def test_the_bootstrap_is_seeded_and_resamples_whole_sessions():
    ps, _ = N.positions(_synthetic(20, 4, close_sd=2.0, noon_sd=1.5, d_mean=0.0), cut='2099-01-01')
    assert N.bootstrap(ps, draws=50, seed=153) == N.bootstrap(ps, draws=50, seed=153)
    assert N.bootstrap(ps, draws=50, seed=153) != N.bootstrap(ps, draws=50, seed=1)
