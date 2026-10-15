"""Day-135b's harness (replay_weeks.py) on synthetic data: no network.

The study's own positive control plants 0.50% on the real outcomes; these
tests check the harness end to end first: a drift planted in the PRICES is
found, noise is not, the signals are causal and the entries come after the
event is public."""
import datetime as dt

import numpy as np

import replay_weeks as W


def sessions(n, start=dt.date(2015, 1, 5)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def synthetic(plant=0.0, names=60, n=1100, seed=7):
    """Random walks; each name reports every 63 sessions with a random
    surprise; after the report the price drifts `plant` % over ten sessions
    in the surprise's direction."""
    rng = np.random.default_rng(seed)
    cal = sessions(n)
    mkt = 50 * np.cumprod(1 + rng.normal(0, 0.008, n))
    data = {W.MARKET: {'adj': dict(zip(cal, mkt)), 'raw': dict(zip(cal, mkt))}}
    meta = {}
    for k in range(names):
        t = 'N%02d.TO' % k
        r = rng.normal(0, 0.012, n) + 0.8 * (np.r_[1, mkt[1:] / mkt[:-1]] - 1)
        earnings = []
        for d0 in range(20 + k % 60, n - 30, 63):
            surprise = rng.normal(0, 0.05)
            earnings.append({'date': cal[d0], 'epsActual': 1.0 + surprise, 'epsEstimated': 1.0,
                             'revenueActual': None, 'revenueEstimated': None})
            if plant:
                r[d0 + 2:d0 + 12] += np.sign(surprise) * plant / 100 / 10
        px = 20 * np.cumprod(1 + r)
        data[t] = {'adj': dict(zip(cal, px)), 'raw': dict(zip(cal, px)), 'earnings': earnings, 'grades': []}
        meta[t] = {'median_dollar_volume_20': float(k), 'sector': 'Energy', 'industry': 'Oil & Gas'}
    return data, sorted(meta), meta


def test_a_drift_planted_in_the_prices_is_found():
    data, tickers, meta = synthetic(plant=2.0)
    out = W.run(data, tickers, meta, {})
    s = out['signals']['W1']['10']
    assert s['verdict'] == 'DRIFT' and 1.0 < s['mean'] < 3.0 and s['t'] >= 3
    assert s['placebo_p'] < 0.01 and s['control_t'] >= 3


def test_noise_is_not_a_drift():
    data, tickers, meta = synthetic(plant=0.0)
    out = W.run(data, tickers, meta, {})
    for k in ('W1', 'W2', 'W3'):
        assert out['signals'][k]['10']['verdict'] in ('NULL', 'UNDERPOWERED', 'NOT COMPUTABLE')


def test_the_rolling_percentile_never_sees_the_same_day_or_the_future():
    cal = sessions(600)
    events = [{'ticker': 'A', 'entry': i, 'v': float(i % 7)} for i in range(0, 500)]
    before = W.rolling_sides(events, 'v', cal)
    later = events + [{'ticker': 'B', 'entry': 550, 'v': 1e9}, {'ticker': 'C', 'entry': 120, 'v': -1e9}]
    after = W.rolling_sides(later, 'v', cal)
    assert all(after[id(e)] == before[id(e)] for e in events if e['entry'] <= 120 and id(e) in before)
    # Same-day events: a day of identical values cannot rank against each other.
    same = [{'ticker': str(i), 'entry': 300, 'v': 5.0} for i in range(5)]
    sides = W.rolling_sides(events[:290] + same, 'v', cal)
    assert len({sides.get(id(e)) for e in same}) == 1


def test_the_entry_is_the_first_close_after_the_report():
    data, tickers, meta = synthetic()
    panel = W.Panel(data, tickers)
    friday = next(d for d in panel.cal if dt.date.fromisoformat(d).weekday() == 4)
    i = panel.idx[friday]
    assert panel.last_before(friday) == i - 1 and panel.first_after(friday) == i + 1
    saturday = (dt.date.fromisoformat(friday) + dt.timedelta(days=1)).isoformat()
    assert panel.last_before(saturday) == i and panel.first_after(saturday) == i + 1


def test_a_days_rating_changes_net_out():
    data, tickers, meta = synthetic(names=3)
    day = sorted(data[W.MARKET]['adj'])[400]
    other = sorted(data[W.MARKET]['adj'])[500]
    data[tickers[0]]['grades'] = [{'date': day, 'action': 'upgrade'}, {'date': day, 'action': 'upgrade'},
                                  {'date': day, 'action': 'downgrade'}, {'date': day, 'action': 'maintain'},
                                  {'date': other, 'action': 'upgrade'}, {'date': other, 'action': 'downgrade'}]
    panel, dropped = W.Panel(data, tickers), {}
    ev = W.grade_events(panel, data, dropped)
    assert [(e['ticker'], panel.cal[e['entry']], e['side']) for e in ev] == [(tickers[0], day, 1)]
    assert dropped == {'grades_net_zero': 1}


def test_a_weekly_series_is_not_daily():
    weekly = {(dt.date(2015, 1, 5) + dt.timedelta(weeks=i)).isoformat(): 1.0 for i in range(100)}
    assert not W.granular(weekly) and W.granular(dict.fromkeys(sessions(100), 1.0))
