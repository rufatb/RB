"""Day-147c's machinery on made-up sessions: it finds a planted lean either way,
reads nothing into noise, and keeps its holes out."""
import random

import market_direction as M


def days(n=600, lean=0.0, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        p = rng.gauss(0, 0.6)
        a = rng.gauss(0, 0.7) + lean * (1 if p > 0 else -1)
        out.append((f'2025-{1 + i // 50:02d}-{1 + i % 28:02d}#{i:04d}', p, a))
    return out


def test_a_planted_follow_and_a_planted_fade_are_found():
    up = M.arm(days(lean=0.15), draws=500)
    assert up['t'] >= 3 and up['placebo_p_two'] < 0.01 and M.clears(up)
    down = M.arm(days(lean=-0.15), draws=500)
    assert down['t'] <= -3 and M.clears(down)
    assert M.verdict(up, M.arm(days(lean=0.15, seed=2), draws=200)) == 'PREDICTABLE_FOLLOWS'
    assert M.verdict(down, M.arm(days(lean=-0.15, seed=2), draws=200)) == 'PREDICTABLE_FADES'
    # The other market disagreeing in sign keeps it short of the bar.
    assert M.verdict(up, M.arm(days(lean=-0.15, seed=2), draws=200)) == 'NULL'


def test_noise_is_not_a_lean_and_the_control_still_shows():
    a = M.arm(days(lean=0.0), draws=500)
    assert abs(a['t']) < 3 and not M.clears(a)
    assert a['control']['detected'] and a['mde_pct'] < 0.2
    assert M.verdict(a, a) == 'NULL'


def test_session_points_and_holes():
    series = {'eod': [['2024-01-02', 1, 1, 1, 100.0, 0], ['2024-01-03', 1, 1, 1, 101.0, 0],
                      ['2024-01-20', 1, 1, 1, 99.0, 0]],
              'bars': {'2024-01-03': [100.5, 101.5, 101.0, 103.53],
                       '2024-01-20': [99.0, 99.0, 99.0, 99.0]}}
    pts = M.session_points(series)
    assert set(pts) == {'2024-01-03'}                  # 01-20's prior close is 17 days back
    p = pts['2024-01-03']
    assert round(p['so_far'], 4) == 1.5 and round(p['gap'], 4) == 0.5
    assert round(p['after'], 4) == 2.0 and p['prior'] is None


def test_holm_and_blocks():
    assert M.holm([0.001, 0.04, None, 0.02]) == [0.003, 0.04, None, 0.04]
    assert M.blocks([1, 1, 2, 2, 3, 3, 4, 4]) == [1, 2, 3, 4]
    assert M.sign(0) == 0 and M.sign(None) == 0 and M.sign(-2) == -1
