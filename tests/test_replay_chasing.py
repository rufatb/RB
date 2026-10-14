"""Day-132 chasing test: the harness must measure move_atr exactly as the models
see it, find a planted continuation and a planted reversal, and find neither
in noise."""
import datetime as dt
import random

import pandas as pd

import daily_technicals as DT
import replay_chasing as R


def bdays(a, b):
    d, out = dt.date.fromisoformat(a), []
    while d <= dt.date.fromisoformat(b):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def synthetic(names, edge, seed=1, days=None):
    """Reduced per-name data. A name moves 1.5-3 ATR on about one day in six;
    the next day's 09:45 → close (against a flat-ish XIU) is sign(move) × edge
    plus noise, so edge > 0 plants continuation and edge < 0 reversal."""
    rng = random.Random(seed)
    days = days or bdays('2023-12-01', '2024-12-31')
    data = {}
    for t in [R.MARKET] + names:
        eod, bars, close, prev_big = [], {}, 50.0, 0
        for d in days:
            o = close * (1 + rng.gauss(0, 0.002))
            p945 = o * (1 + rng.gauss(0, 0.002))
            noon = p945 * (1 + rng.gauss(0, 0.002))
            drift = 0.0 if t == R.MARKET else edge / 100 * prev_big
            c = p945 * (1 + drift + rng.gauss(0, 0.004 if t != R.MARKET else 0.001))
            big = 0
            if t != R.MARKET and rng.random() < 1 / 6:
                big = rng.choice((-1, 1))
                c = close * (1 + big * rng.uniform(0.03, 0.05))
            hi, lo = max(o, p945, noon, c) * 1.003, min(o, p945, noon, c) * 0.997
            eod.append([d, o, hi, lo, c])
            bars[d] = [o, p945, noon, c]
            close, prev_big = c, big
        data[t] = {'ticker': t, 'eod': eod, 'bars': bars, 'reports': [], 'failed_calls': 0, 'capped_calls': 0}
    return data


def rows_of(data):
    rows = []
    for t, d in data.items():
        if t != R.MARKET:
            rows.extend(R.name_rows(d, data[R.MARKET])[0])
    return rows


def test_move_atr_matches_daily_technicals():
    data = synthetic(['AAA.TO'], 0.0)
    eod = data['AAA.TO']['eod'][:60]
    frame = pd.DataFrame(eod, columns=['date', 'open', 'high', 'low', 'close'])
    want = DT.context(frame, frame['close'], frame['close'].iloc[-1], frame['close'].iloc[-2])['move_atr']
    assert abs(R.move_atr(eod, len(eod) - 1) - want) < 1e-12


def test_reduce_bars_reads_the_scored_instants():
    rows = [{'date': '2024-03-04 09:30:00', 'open': 10.0, 'close': 10.2},
            {'date': '2024-03-04 09:45:00', 'open': 10.2, 'close': 10.3},
            {'date': '2024-03-04 11:45:00', 'open': 10.4, 'close': 10.5},
            {'date': '2024-03-04 15:45:00', 'open': 10.6, 'close': 10.7},
            {'date': '2024-03-05 09:30:00', 'open': 10.7, 'close': 10.8}]
    assert R.reduce_bars(rows) == {'2024-03-04': [10.0, 10.2, 10.5, 10.7]}


def test_months_cover_the_window_without_gaps():
    ms = R.months('2024-01-02', '2024-03-13')
    assert ms == [('2024-01-02', '2024-01-31'), ('2024-02-01', '2024-02-29'), ('2024-03-01', '2024-03-13')]


def test_detects_a_planted_continuation():
    out = R.summarize(rows_of(synthetic(['A%d.TO' % i for i in range(6)], 0.8)))
    assert out['primary']['mean_pct'] > 0.5 and out['primary']['t'] >= 3
    assert out['verdict'] == 'CONTINUATION'


def test_detects_a_planted_reversal():
    out = R.summarize(rows_of(synthetic(['A%d.TO' % i for i in range(6)], -0.8, seed=2)))
    assert out['primary']['mean_pct'] < -0.5 and out['primary']['t'] <= -3
    assert out['verdict'] == 'REVERSAL'


def test_noise_is_neither():
    out = R.summarize(rows_of(synthetic(['A%d.TO' % i for i in range(6)], 0.0, seed=3)))
    assert out['verdict'] in ('NULL', 'UNDERPOWERED')
    assert abs(out['primary']['t']) < 3


def test_a_pick_chases_only_on_the_side_of_a_big_move():
    assert R.chases('LONG', 1.2) and R.chases('SHORT', -1.0)
    assert not R.chases('SHORT', 1.2) and not R.chases('LONG', 0.9) and not R.chases('LONG', None)
