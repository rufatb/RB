"""Day-152 (PREREGISTER_day152_intraday_habit.md): the habit test's machinery,
on synthetic data only. No network and no real bar is read here."""
import numpy as np
import pandas as pd

import intraday_habit as I


def _days(n):
    return [(pd.Timestamp('2024-01-01') + pd.Timedelta(days=k)).date().isoformat() for k in range(n)]


def test_the_habit_uses_only_the_prior_sessions_and_needs_fifteen_of_twenty():
    days = _days(30)
    h = pd.DataFrame({'A': np.arange(30, dtype=float)}, index=days)
    hab = I.habit(h)
    # session 20's habit is the mean of sessions 0..19, never session 20 itself
    assert hab['A'].iloc[20] == np.mean(np.arange(20))
    assert np.isnan(hab['A'].iloc[14])                     # only 14 prior values
    assert hab['A'].iloc[15] == np.mean(np.arange(15))     # 15 prior values: enough
    h2 = h.copy()
    h2.iloc[0:6, 0] = np.nan                               # 14 of the 20 before session 20
    assert np.isnan(I.habit(h2)['A'].iloc[20])


def test_a_session_ranks_by_habit_and_takes_the_fifths():
    tickers = ['T%02d' % i for i in range(30)]
    hab = np.arange(30, dtype=float)                       # T29 has the strongest habit
    out = np.arange(30, dtype=float) / 10                  # and the best day
    ordered, k = I.session_sort(hab, out, tickers)
    assert k == 6 and list(ordered) == list(out)
    days = ['2024-03-01']
    rows, skipped = I.spread(pd.DataFrame([hab], index=days, columns=tickers),
                             pd.DataFrame([out], index=days, columns=tickers))
    assert skipped == 0 and len(rows) == 1
    assert abs(rows[0]['y'] - (out[-6:].mean() - out[:6].mean())) < 1e-12
    # fewer than 25 names with both a habit and a result: skipped and counted
    few = hab.copy()
    few[:6] = np.nan
    rows, skipped = I.spread(pd.DataFrame([few], index=days, columns=tickers),
                             pd.DataFrame([out], index=days, columns=tickers))
    assert rows == [] and skipped == 1


def test_the_member_filter_limits_the_names_on_each_date():
    tickers = ['T%02d' % i for i in range(30)]
    days = ['2024-03-01']
    hab = pd.DataFrame([np.arange(30.0)], index=days, columns=tickers)
    out = pd.DataFrame([np.ones(30)], index=days, columns=tickers)
    rows, skipped = I.spread(hab, out, member=lambda d, t: t != 'T00')
    assert rows[0]['n'] == 29


def _rows(ys, start='2024-01-01'):
    days = _days(len(ys))
    return [{'session': d, 'y': y, 'top': y / 2, 'bottom': -y / 2} for d, y in zip(days, ys)]


def test_the_verdict_reads_the_registered_bar():
    rng = np.random.default_rng(0)
    # noise around zero, powered: NULL
    ys = list(rng.normal(0, 0.2, 600))
    v = I.verdict(_rows(ys), rng.normal(0, 0.01, 2000), [0.1, 0.1])
    assert v['control']['t_planted'] >= 3 and v['verdict'] == 'NULL'
    # a big persistent spread, clearing cost, placebo and both secondaries
    ys = list(rng.normal(0.5, 0.2, 600))
    v = I.verdict(_rows(ys), rng.normal(0, 0.01, 2000), [0.05, 0.02])
    assert v['verdict'] == 'PERSISTENCE' and v['per_pick_edge_pct'] > I.COST_PER_PICK
    # the same, with a secondary panel negative: not PERSISTENCE
    v = I.verdict(_rows(ys), rng.normal(0, 0.01, 2000), [0.05, -0.02])
    assert v['verdict'] == 'NULL'
    # a strong reversal
    v = I.verdict(_rows([-y for y in ys]), rng.normal(0, 0.01, 2000), [-0.05, -0.02])
    assert v['verdict'] == 'REVERSAL'
    # too noisy to see a planted 0.10%: UNDERPOWERED
    ys = list(rng.normal(0, 3.0, 300))
    v = I.verdict(_rows(ys), rng.normal(0, 0.1, 2000), [0.1, 0.1])
    assert v['control']['t_planted'] < 3 and v['verdict'] == 'UNDERPOWERED'


def test_the_placebo_shuffles_within_a_session():
    tickers = ['T%02d' % i for i in range(30)]
    days = _days(40)
    rng = np.random.default_rng(1)
    hab = pd.DataFrame(rng.normal(size=(40, 30)), index=days, columns=tickers)
    out = hab * 1.0                                         # the habit IS the result: perfect sort
    draws = I.placebo(hab, out, draws=200, seed=5)
    rows, _ = I.spread(hab, out)
    obs = np.mean([r['y'] for r in rows])
    assert draws.size == 200 and obs > draws.max()          # nothing shuffled comes close
    assert abs(draws.mean()) < 0.2
