"""Day-147 (PREREGISTER_day147_holds.md): the holds test's population, its
measure, what it leaves out, and its verdict, on synthetic data only."""
import datetime as dt
import json
import random

import holds_history as H


def _days(n, start='2026-09-17'):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


class FakeFMP:
    """Daily closes per symbol and XIU's 09:40 bar per session."""

    def __init__(self, closes, xiu_entry):
        self.closes, self.xiu_entry, self.calls = closes, xiu_entry, []
        self.failures = {}

    def __call__(self, path, **params):
        self.calls.append((path, params))
        sym = params['symbol']
        if path == 'historical-price-eod/full':
            return [{'date': d, 'close': c} for d, c in sorted(self.closes.get(sym, {}).items())]
        if path == 'historical-chart/5min':
            s = params['from']
            v = self.xiu_entry.get(s)
            return [] if v is None else [{'date': s + ' 09:35:00', 'close': v * 2},
                                         {'date': s + ' 09:40:00', 'close': v}]
        raise AssertionError(path)


def _row(session, ticker, side, *, model='deepseek', kind='selected', entry=100.0, exit_=None,
         r_pct=0.0, scored=True):
    return {'session': session, 'ticker': ticker, 'side': side, 'model': model, 'kind': kind,
            'entry': str(entry), 'exit': '' if exit_ is None else str(exit_), 'r_pct': str(r_pct),
            'scored_at': '2026-11-01T16:30:00' if scored else ''}


def test_the_population_is_the_pooled_rule_inside_the_window():
    rows = [
        _row('2026-09-16', 'AAA.TO', 'LONG'),                        # before the window
        _row('2026-09-17', 'AAA.TO', 'LONG', model='claude'),        # kept (first)
        _row('2026-09-17', 'AAA.TO', 'LONG', model='deepseek'),      # same bet: dropped
        _row('2026-09-17', 'AAA.TO', 'SHORT', model='gemini'),       # the other side: kept
        _row('2026-09-17', 'BBB.TO', 'LONG', model='engine', kind='board'),
        _row('2026-09-17', 'CCC.TO', 'LONG', model='top2count', kind='pick'),
        _row('2026-09-17', 'DDD.TO', 'LONG', kind='late'),
        _row('2026-09-17', 'EEE.TO', 'LONG', scored=False),
        _row('2026-10-29', 'FFF.TO', 'SHORT', model='jev', kind='forced'),
        _row('2026-10-30', 'GGG.TO', 'LONG'),                        # after the window
    ]
    got = H.population(rows)
    assert [(r['session'], r['ticker'], r['side'], r['model']) for r in got] == [
        ('2026-09-17', 'AAA.TO', 'LONG', 'claude'), ('2026-09-17', 'AAA.TO', 'SHORT', 'gemini'),
        ('2026-10-29', 'FFF.TO', 'SHORT', 'jev')]


def test_y_is_the_sided_return_against_xiu_from_the_0945_entry():
    cal = _days(8)
    s = cal[0]
    xiu = {d: 50.0 for d in cal}
    xiu[cal[3]] = 51.0                                  # XIU +2% by the third close
    stock = {d: 100.0 for d in cal}
    stock[cal[3]] = 105.0                               # the stock +5% by the third close
    fmp = FakeFMP({'XIU.TO': xiu, 'AAA.TO': stock, 'BBB.TO': stock}, {s: 50.0})
    rows, left = H.outcomes([_row(s, 'AAA.TO', 'LONG'), _row(s, 'BBB.TO', 'SHORT')], fmp,
                            end=cal[-1])
    assert left == {}
    long_, short = rows
    assert abs(long_['y3'] - 3.0) < 1e-9 and abs(short['y3'] + 3.0) < 1e-9
    assert abs(long_['raw3'] - 5.0) < 1e-9 and abs(short['raw3'] + 5.0) < 1e-9
    assert long_['y0'] == 0 and long_['y1'] == 0 and long_['y5'] == 0
    # the 09:40 bar's close is XIU's entry, never another bar
    assert all(p != 'historical-chart/5min' or q['from'] == s for p, q in fmp.calls)


def test_a_missing_price_or_an_open_horizon_is_left_out_and_counted_never_filled():
    cal = _days(8)
    xiu = {d: 50.0 for d in cal}
    gappy = {d: 100.0 for d in cal if d != cal[3]}      # no close three sessions after
    full = {d: 100.0 for d in cal}
    fmp = FakeFMP({'XIU.TO': xiu, 'GAP.TO': gappy, 'OK.TO': full}, {cal[0]: 50.0, cal[4]: 50.0})
    picks = [_row(cal[0], 'GAP.TO', 'LONG'), _row(cal[0], 'OK.TO', 'LONG'),
             _row(cal[1], 'OK.TO', 'LONG'),                       # no XIU 09:45 that session
             _row(cal[4], 'OK.TO', 'SHORT'),                      # 5 sessions not closed yet
             _row(cal[0], 'NONE.TO', 'LONG'), _row(cal[0], 'OK.TO', 'SHORT', entry='')]
    rows, left = H.outcomes(picks, fmp, end=cal[-1])
    assert [(r['ticker'], r['side']) for r in rows] == [('OK.TO', 'LONG')]
    assert left == {'a missing close': 2, 'no XIU price that session': 1,
                    'the horizon is not closed yet': 1, 'no recorded entry': 1}


def test_a_close_far_from_the_records_exit_is_left_out_as_a_basis_mismatch():
    cal = _days(8)
    fmp = FakeFMP({'XIU.TO': {d: 50.0 for d in cal}, 'SPL.TO': {d: 50.0 for d in cal},
                   'OK.TO': {d: 100.0 for d in cal}}, {cal[0]: 50.0})
    rows, left = H.outcomes([_row(cal[0], 'SPL.TO', 'LONG', exit_=100.0),
                             _row(cal[0], 'OK.TO', 'LONG', exit_=100.4)], fmp, end=cal[-1])
    assert [r['ticker'] for r in rows] == ['OK.TO']
    assert left == {'basis mismatch (split or bad bar)': 1}


def _synthetic(mean, sd, sessions=30, per=6, seed=1):
    rng = random.Random(seed)
    out = []
    for i, s in enumerate(_days(sessions)):
        for j in range(per):
            y = mean + rng.gauss(0, sd)
            out.append({'session': s, 'ticker': 'T%d.TO' % j, 'side': 'LONG', 'y3': y, 'y0': 0.0})
    return out


def test_a_planted_drift_reads_drift_a_reversal_reads_reversal_noise_reads_neither():
    assert H.verdict(_synthetic(2.0, 1.0), draws=500)['status'] == 'DRIFT'
    assert H.verdict(_synthetic(-2.0, 1.0), draws=500)['status'] == 'REVERSAL'
    noise = H.verdict(_synthetic(0.0, 1.0), draws=500)
    assert noise['status'] == 'NULL' and noise['control']['detected']


def test_the_cost_and_both_halves_bind():
    tiny = H.verdict(_synthetic(0.10, 0.01), draws=500)     # t is huge, the net is not
    assert tiny['t'] > 3 and tiny['net'] < 0 and tiny['status'] == 'NULL'
    rows = _synthetic(2.0, 0.5)
    days = sorted({r['session'] for r in rows})
    for r in rows:                                            # the first half turned negative
        if r['session'] in days[:len(days) // 2]:
            r['y3'] = -0.5 + (r['y3'] - 2.0) * 0.01
    assert H.verdict(rows, draws=500)['status'] != 'DRIFT'


def test_the_control_is_centred_so_the_real_mean_cannot_help_it():
    a = H.control(_synthetic(0.0, 3.0, sessions=20), 'y3')
    b = H.control(_synthetic(5.0, 3.0, sessions=20), 'y3')
    assert a['t'] == b['t']
    weak = H.control(_synthetic(0.0, 40.0, sessions=8, per=2), 'y3')
    assert not weak['detected']
    assert H.verdict(_synthetic(0.0, 40.0, sessions=8, per=2), draws=200)['status'] == 'UNDERPOWERED'


def test_claudes_first_named_follows_the_frozen_order_else_the_review(tmp_path):
    reviews = tmp_path / 'reviews'
    reviews.mkdir()
    (reviews / '2026-10-14.json').write_text(json.dumps({'rows': [
        {'section': 'Nominated (forced)', 'model': 'claude', 'side': 'LONG', 'ticker': 'BBB.TO'},
        {'section': 'Nominated (forced)', 'model': 'claude', 'side': 'LONG', 'ticker': 'AAA.TO'},
        {'section': 'Nominated (forced)', 'model': 'claude', 'side': 'SHORT', 'ticker': 'CCC.TO'}]}))
    noms = [_row('2026-10-14', 'AAA.TO', 'LONG', model='claude', kind='nominated'),
            _row('2026-10-14', 'BBB.TO', 'LONG', model='claude', kind='nominated'),
            _row('2026-10-14', 'CCC.TO', 'SHORT', model='claude', kind='nominated'),
            _row('2026-10-15', 'DDD.TO', 'LONG', model='claude', kind='nominated')]
    got = H.first_named(noms, db=tmp_path / 'none.sqlite3', reviews=reviews)
    assert [(r['session'], r['ticker']) for r in got] == [('2026-10-14', 'BBB.TO'),
                                                         ('2026-10-14', 'CCC.TO')]


def test_the_run_writes_no_record_and_calls_no_model(tmp_path):
    cal = _days(8)
    fmp = FakeFMP({'XIU.TO': {d: 50.0 for d in cal}, 'AAA.TO': {d: 100.0 for d in cal}},
                  {cal[0]: 50.0})
    rows = [_row(cal[0], 'AAA.TO', 'LONG')]
    got = H.run(rows, fmp, end=cal[-1], draws=50, db=tmp_path / 'none.sqlite3', reviews=tmp_path)
    assert got['population'] == 1 and got['scored'] == 1
    assert {p for p, _ in fmp.calls} == {'historical-price-eod/full', 'historical-chart/5min'}
