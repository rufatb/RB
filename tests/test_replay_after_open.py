"""Day-132c phase 3: the after-open harness reads the registered instants,
applies exactly the registered prompt edits, and its statistics find a planted
edge and no edge in noise."""
import random

import nominations as N
import replay_after_open as R


def bar(t, o, h, l, c, v):
    return {'date': '2026-07-06 ' + t, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}


def test_reduce15_reads_open_0945_1000_close_and_the_vwap():
    rows = [bar('09:30:00', 10.0, 10.4, 9.9, 10.2, 100), bar('09:45:00', 10.2, 10.6, 10.1, 10.5, 300),
            bar('11:45:00', 10.5, 10.5, 10.4, 10.45, 50), bar('15:45:00', 10.4, 10.5, 10.3, 10.35, 200)]
    d = R.reduce15(rows)['2026-07-06']
    assert (d['open'], d['p945'], d['p1000'], d['close']) == (10.0, 10.2, 10.5, 10.35)
    assert (d['high30'], d['low30'], d['vol30']) == (10.6, 9.9, 400)
    typ = lambda h, l, c: (h + l + c) / 3
    assert abs(d['vwap30'] - (typ(10.4, 9.9, 10.2) * 100 + typ(10.6, 10.1, 10.5) * 300) / 400) < 1e-12


def test_open30_against_the_market_and_its_own_volume():
    days = ['2026-06-%02d' % i for i in range(1, 25)] + ['2026-07-06']
    name = {'bars': {d: {'open': 10.0, 'p945': 10.1, 'p1000': 10.2, 'close': 10.3, 'high30': 10.25,
                         'low30': 9.95, 'vol30': 100, 'vwap30': 10.1} for d in days},
            'eod': [[d, 0, 0, 0, 9.9] for d in days]}
    name['bars']['2026-07-06']['vol30'] = 300
    market = {'bars': {d: {'open': 100.0, 'p945': 100.0, 'p1000': 100.5, 'close': 100.0} for d in days},
              'eod': [[d, 0, 0, 0, 100.0] for d in days]}
    o = R.open30(name, market, '2026-07-06')
    assert o['r30_pct'] == 2.0 and o['x30_pct'] == 1.5 and o['rvol30'] == 3.0
    assert o['gap_pct'] == round(100 * (10.0 / 9.9 - 1), 2) and o['range30_pos'] == round(0.25 / 0.30, 2)
    assert R.outcome(name, market, '2026-07-06', 'SHORT', 'p1000') == -100 * ((10.3 / 10.2 - 1) - (100.0 / 100.5 - 1))


def test_the_after_open_prompt_is_the_nomination_prompt_with_exactly_the_registered_edits():
    base = N.prompt()
    b = R.after_open_prompt(base)
    for old, new in ((R.OLD_HEAD, R.NEW_HEAD), (R.OLD_WINDOW, R.NEW_WINDOW), (R.OLD_TIMING, R.NEW_TIMING)):
        assert old in base and old not in b and b.count(new) == 1
    assert b.endswith(R.OPEN30_DOC)
    rebuilt = (b[:-len(R.OPEN30_DOC) - 2].replace(R.NEW_HEAD, R.OLD_HEAD).replace(R.NEW_WINDOW, R.OLD_WINDOW)
               .replace(R.NEW_TIMING, R.OLD_TIMING))
    assert rebuilt == base


def test_the_control_plants_only_in_open30():
    payload, allowed = R.control_payload()
    rows = {r['ticker']: r for r in payload['candidates']}
    strip = lambda r: {k: v for k, v in r.items() if k not in ('ticker', 'open30', 'last', 'open', 'vwap',
                                                                 'orb_high', 'orb_low', 'prev_close')}
    assert strip(rows['CTLUP.TO']) == strip(rows['NOIS5.TO'])
    assert rows['CTLUP.TO']['open30']['x30_pct'] > 2 and rows['CTLDN.TO']['open30']['x30_pct'] < -2
    assert all(abs(r['open30']['x30_pct']) <= 0.3 for t, r in rows.items() if t.startswith('NOIS'))


def synthetic(edge, seed=1, sessions=60, names=30):
    rng = random.Random(seed)
    days = ['2026-07-%02d' % (i % 28 + 1) if i < 28 else '2026-08-%02d' % (i % 28 + 1) for i in range(sessions)]
    market = {'bars': {d: {'open': 100, 'p945': 100, 'p1000': 100, 'close': 100} for d in days}, 'eod': []}
    data, universe, picks = {}, {}, []
    for d in days:
        universe[d] = []
        for j in range(names):
            t = 'N%d.TO' % j
            r = rng.gauss(0, 1.0)
            data.setdefault(t, {'bars': {}, 'eod': []})['bars'][d] = {'open': 50, 'p945': 50, 'p1000': 50,
                                                                    'close': 50 * (1 + r / 100)}
            universe[d].append(t)
        ranked = sorted(universe[d], key=lambda t: data[t]['bars'][d]['close'])
        for t in ranked[-2:] if edge else rng.sample(universe[d], 2):
            picks.append({'session': d, 'side': 'LONG', 'ticker': t,
                          'y': R.outcome(data[t], market, d, 'LONG', 'p1000')})
    return picks, universe, data, market


def test_the_statistics_find_a_planted_edge_and_not_noise():
    good = synthetic(True)
    out = R.summarize(good[0], good[0], [], good[1], good[2], good[3], {'passes': True})
    assert out['t2_after_open']['verdict'] == 'PASS'
    noise = synthetic(False, seed=2)
    out = R.summarize(noise[0], noise[0], [], noise[1], noise[2], noise[3], {'passes': True})
    assert out['t2_after_open']['verdict'] != 'PASS'
    out = R.summarize(good[0], good[0], [], good[1], good[2], good[3], {'passes': False})
    assert out['t2_after_open']['verdict'].startswith('NOT RUN')
