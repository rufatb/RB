"""Day-138's harness (replay_events.py) on synthetic data: no network.

A premium planted on the report day is found, noise is not, the sides look
only at reports already public at the entry, and the S&P 500 membership is
rebuilt as it stood on each date."""
import datetime as dt

import numpy as np

import replay_events as R
import replay_weeks as W


def sessions(n, start=dt.date(2012, 1, 3)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def synthetic(plant=0.0, names=60, n=1100, seed=11):
    """Random walks; each name reports every 63 sessions; the report day
    carries `plant` % on top of its noise."""
    rng = np.random.default_rng(seed)
    cal = sessions(n)
    mkt = 50 * np.cumprod(1 + rng.normal(0, 0.008, n))
    data = {W.MARKET: {'adj': dict(zip(cal, mkt)), 'raw': dict(zip(cal, mkt))}}
    meta = {}
    for k in range(names):
        t = 'N%02d.TO' % k
        r = rng.normal(0, 0.012, n) + (np.r_[1, mkt[1:] / mkt[:-1]] - 1)
        earnings = []
        for d0 in range(30 + k % 60, n - 30, 63):
            earnings.append({'date': cal[d0], 'epsActual': 1.0 + rng.normal(0, 0.05), 'epsEstimated': 1.0})
            r[d0] += plant / 100
        px = 20 * np.cumprod(1 + r)
        data[t] = {'adj': dict(zip(cal, px)), 'raw': dict(zip(cal, px)), 'earnings': earnings}
        meta[t] = {'median_dollar_volume_20': float(k), 'sector': 'Energy', 'industry': 'Oil & Gas %d' % (k % 4)}
    return data, sorted(meta), meta


def test_a_premium_planted_on_the_report_day_is_found():
    data, tickers, meta = synthetic(plant=1.0)
    out = R.run_reports(data, tickers, meta, {})
    s = out['hypotheses']['E1']
    assert s['verdict'] == 'PASS' and 0.6 < s['excess'] < 1.4 and s['t'] >= 3


def test_noise_is_not_a_premium():
    data, tickers, meta = synthetic(plant=0.0)
    out = R.run_reports(data, tickers, meta, {})
    for k in ('E1', 'E2', 'E3'):
        assert out['hypotheses'][k]['verdict'] in ('NULL', 'UNDERPOWERED', 'NOT COMPUTABLE')


def test_the_window_holds_the_report_and_enters_the_session_before():
    data, tickers, meta = synthetic()
    panel = W.Panel(data, tickers)
    reports = R.all_reports(panel, data, {})
    r = reports[tickers[0]][0]
    assert panel.cal[r['p0']] < r['date'] < panel.cal[r['d1']]
    assert r['d1'] - r['p0'] == 2      # the report date is a session here


def test_the_previous_surprise_is_an_earlier_report_never_this_one():
    rows = [{'date': '2020-01-10', 'surprise': 1, 'size': 0.1},
            {'date': '2020-04-10', 'surprise': -1, 'size': 0.2},
            {'date': '2020-07-01', 'surprise': 1, 'size': 0.3},   # under 30 days before: skipped
            {'date': '2020-07-10', 'surprise': 1, 'size': 0.4}]
    assert R.previous_side(rows, 3) == (-1, 0.2)
    assert R.previous_side(rows, 0) == (None, None)
    far = [{'date': '2019-01-10', 'surprise': 1, 'size': 0.1}, {'date': '2020-01-10', 'surprise': 1, 'size': 0.1}]
    assert R.previous_side(far, 1) == (None, None)     # more than 200 days back


def test_a_peer_counts_only_once_its_report_is_public_by_the_entry():
    data, tickers, meta = synthetic()
    panel = W.Panel(data, tickers)
    ev = {'ticker': 'X', 'date': panel.cal[500], 'p0': 499, 'd1': 501}
    reports = {'A': [{'date': panel.cal[499 - R.PEER_GAP], 'surprise': 1}],
               'B': [{'date': panel.cal[499 - R.PEER_GAP + 1], 'surprise': -1}],   # too close to the entry
               'C': [{'date': panel.cal[440], 'surprise': -1}]}                   # more than 30 days back
    assert R.peer_side(panel, ev, ['A', 'B', 'C'], reports) == (1, 1)


def test_the_sp500_membership_is_rebuilt_as_it_stood():
    current = [{'symbol': 'NEW'}, {'symbol': 'OLD'}]
    changes = [{'date': '2020-06-01', 'addedTicker': 'NEW', 'removedTicker': 'GONE'},
               {'date': '2015-03-02', 'addedTicker': 'GONE', 'removedTicker': ''}]

    def fetch(path, **params):
        return current if path == 'sp500-constituent' else changes
    iv, glitches = R.sp500_membership(fetch)
    assert glitches == {}
    assert R.member(iv, 'GONE', '2018-01-02') and not R.member(iv, 'GONE', '2020-06-01')
    assert not R.member(iv, 'GONE', '2014-12-31')
    assert R.member(iv, 'NEW', '2020-06-01') and not R.member(iv, 'NEW', '2020-05-29')
    assert R.member(iv, 'OLD', '2001-01-02') and R.member(iv, 'OLD', '2026-10-14')
