"""Day-135c's measurement (risk_rules.py) on synthetic panels: R2 passes only a
wider swing with no lean, the clustered t is by session, and R1 compares the
two-pick books on the same random pairs."""
import types

import numpy as np

import risk_rules as R


def panel(k=60, s=900, wide=1.4, lean=0.0, seed=7):
    """k names over s sessions. A name-day after a big move (|m| >= 1) swings
    `wide` times wider; `lean` is planted as continuation (in %, signed by m)."""
    rng = np.random.default_rng(seed)
    m = rng.normal(0, 0.8, size=(k, s))
    big = np.abs(m) >= 1
    r = rng.normal(0, 2.0, size=(k, s)) * np.where(big, wide, 1.0) + lean * np.sign(m) * big
    mr = rng.normal(0, 0.8, size=s)
    return types.SimpleNamespace(m=m, r=r + mr, mr=mr, adj=r, cal=['2020-01-01'] * s,
                                 tickers=['N%d.TO' % j for j in range(k)])


def test_r2_passes_a_wider_swing_that_leans_neither_way():
    out = R.r2(panel())
    assert out['ratio_sd_movers_to_rest'] > R.BAR and abs(out['signed_mean_movers']['t']) < 2
    assert out['verdict'] == 'PASS'


def test_r2_fails_when_the_movers_lean_and_when_they_do_not_swing_wider():
    leaning = R.r2(panel(lean=0.5))
    assert leaning['signed_mean_movers']['t'] > 3 and leaning['verdict'] == 'FAIL'
    assert R.r2(panel(wide=1.0))['verdict'] == 'FAIL'


def test_the_clustered_t_treats_one_session_as_one_draw():
    vals = np.array([1.0, 1.0, 1.0, -1.0, -1.0, -1.0])
    mean, se, t = R.clustered_t(vals, ['a', 'a', 'a', 'b', 'b', 'b'])
    assert mean == 0.0 and t == 0.0
    _, se_one, _ = R.clustered_t(vals, ['a', 'b', 'c', 'd', 'e', 'f'])
    assert se > se_one                       # same-session rows are not independent


def test_r1_same_side_swings_wider_than_a_long_short_pair_when_names_move_together():
    d = panel(k=40, s=600, wide=1.0)
    out = R.r1(d)
    assert out['rho'] > 0.05
    sd = out['sd']
    assert sd['same side, two picks'] > sd['long and short, two picks'] > sd['one pick']
    assert out['verdict'] == ('PASS' if out['ratio_same_to_long_short'] >= R.BAR else 'FAIL')


def test_describe_reports_the_planted_control_as_edge_over_se():
    out = R.describe(panel())
    c = out['signed_mean_control']
    assert c['planted_pct'] == 0.10 and c['t_planted'] > 0
    assert abs(c['mde80_at_t2_pct'] - 2.84 * 0.10 / c['t_planted']) < 1e-9
    assert out['note'].startswith('descriptive')
