"""Day-132b T1: the confidence-ranking harness must find a planted top-pick
edge and must not find one when confidence is unrelated to the outcome."""
import random

import feedback_review as R
from replay_chasing import MARKET


def synthetic(edge, seed=1, sessions=60, per=4):
    rng = random.Random(seed)
    days = ['2026-07-%02d' % (i % 28 + 1) if i < 28 else '2026-08-%02d' % (i % 28 + 1) for i in range(sessions)]
    data = {MARKET: {'bars': {d: [100.0, 100.0, 100.0, 100.0] for d in days}}}
    runs = {'flash': {}}
    for d in days:
        ps = []
        confs = [rng.uniform(0.5, 0.8) for _ in range(per)]
        top = max(range(per), key=lambda j: confs[j])
        for j in range(per):
            t = 'N%d.TO' % j
            r = rng.gauss(0, 1.0) + (edge if j == top else 0.0)
            data.setdefault(t, {'bars': {}})['bars'][d] = [50.0, 50.0, 50.0, 50.0 * (1 + r / 100)]
            ps.append(('LONG', t, confs[j]))
        runs['flash'][d] = ps
    return runs, data


def test_finds_a_planted_top_pick_edge():
    runs, data = synthetic(1.5)
    out = R.t1(runs, data, data[MARKET], draws=300)
    assert out['top_minus_rest']['mean_pct'] > 1.0 and out['verdict'] == 'PASS'


def test_no_edge_is_not_a_pass():
    runs, data = synthetic(0.0, seed=2)
    out = R.t1(runs, data, data[MARKET], draws=300)
    assert out['verdict'] != 'PASS'


def test_top_pick_ties_go_to_the_first_returned():
    assert R.top_minus_rest([(0.6, 1.0), (0.6, -1.0), (0.5, 0.0)]) == 1.0 - (-0.5)


def test_power_counts_picks_for_t3():
    picks = [{'key': 'top2_pick', 'raw': x} for x in (1.0, -1.0, 1.0, -1.0)]
    out = R.power(picks)
    assert out['picks_for_t3']['0.1'] == round((3 * out['per_pick_sd_pct'] / 0.1) ** 2 + 0.5) or out['picks_for_t3']['0.1'] > 900
