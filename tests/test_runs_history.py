"""Day-146 (PREREGISTER_day146_runs.md): the three-day-run test's machinery, on
synthetic data only. No network and no real bar is read here."""
import random

import runs_history as R


def test_a_run_is_counted_back_from_the_last_close_and_a_flat_close_breaks_it():
    assert R.run_length([1, 2, 3, 4]) == 3
    assert R.run_length([4, 3, 2, 1]) == -3
    assert R.run_length([1, 2, 2, 3]) == 1
    assert R.run_length([1, 3, 2, 1, 0]) == -3
    assert R.run_length([2, 1, 2, 3, 4, 5]) == 4
    assert R.run_length([5]) == 0 and R.run_length([]) == 0


def _series(closes, start=(2024, 1, 1)):
    import datetime as dt
    d0 = dt.date(*start)
    return [[(d0 + dt.timedelta(days=k)).isoformat(), c, c * 1.01, c * 0.99, c] for k, c in enumerate(closes)]


def test_the_run_uses_only_closes_before_the_session_and_signs_the_result():
    closes = [100.0] * 16 + [101.0, 102.0, 103.0, 90.0]       # three rises, then the session falls
    series = _series(closes)
    cal = [r[0] for r in series]
    d = cal[-1]
    market = {r[0]: {'main': 0.0, 'pre': 0.0, 'oc': 0.0} for r in series}
    bars = {d: [103.0, 100.0, 99.0, 98.0]}                    # 09:45 at 100, close 98: -2%
    rows, _ = R.name_rows(series, cal, market, cal[0], d, bars=bars)
    assert len(rows) == 1
    r = rows[0]
    # the session's own fall (to 90) is not part of its run: three rises before it
    assert r['run'] == 3 and abs(r['u'] - (-2.0)) < 1e-9 and abs(r['y'] - (-2.0)) < 1e-9
    # a down run signs the same fall the other way
    series2 = _series([100.0] * 16 + [99.0, 98.0, 97.0, 90.0])
    rows2, _ = R.name_rows(series2, cal, market, cal[0], d, bars=bars)
    assert rows2[0]['run'] == -3 and abs(rows2[0]['y'] - 2.0) < 1e-9


def test_a_name_whose_prior_session_is_not_the_markets_is_skipped():
    series = _series([100.0] * 16 + [101.0, 102.0, 103.0, 104.0])
    cal = [r[0] for r in series]
    gappy = series[:-2] + series[-1:]                          # the name lacks the market's prior session
    market = {r[0]: {'main': 0.0} for r in series}
    rows, skipped = R.name_rows(gappy, cal, market, cal[0], cal[-1])
    assert not [r for r in rows if r['session'] == cal[-1]]
    assert skipped['not_the_market_session'] >= 1


def _events(edge, noise=1.0, seed=1, names=30, sessions=200):
    rng = random.Random(seed)
    out = []
    for k in range(names):
        for s in range(sessions):
            run = rng.choice((3, -3))
            u = rng.gauss(0, noise) + edge * (1 if run > 0 else -1)
            out.append({'session': '2025-%04d' % s, 'key': 'N%02d' % k, 'run': run, 'u': u,
                        'y': (1 if run > 0 else -1) * u})
    return out


def test_the_verdict_finds_a_planted_reversal_or_continuation_and_not_noise():
    assert R.verdict(_events(-0.2), [-0.1, -0.1])['verdict'] == 'REVERSAL'
    # a reversal the survivor check does not confirm is not a pass
    assert R.verdict(_events(-0.2), [-0.1, 0.05])['verdict'] == 'NULL'
    assert R.verdict(_events(0.2), [0.1, 0.1])['verdict'] == 'CONTINUATION'
    v = R.verdict(_events(0.0), [-0.1, -0.1])
    assert v['verdict'] == 'NULL' and v['control']['t_planted'] >= 3


def test_a_harness_that_cannot_see_a_tenth_of_a_percent_says_underpowered():
    v = R.verdict(_events(0.0, noise=30.0, names=5, sessions=40), [-0.1, -0.1])
    assert v['verdict'] == 'UNDERPOWERED'


def test_the_placebo_keeps_each_names_signs_and_moves_them_in_time():
    ev = _events(-0.3, names=12, sessions=60)
    draws, used = R.placebo(ev, draws=300)
    assert used == len(ev) and draws.size == 300
    obs = sum(e['y'] for e in ev) / len(ev)
    assert (abs(draws) >= abs(obs)).mean() < 0.01
