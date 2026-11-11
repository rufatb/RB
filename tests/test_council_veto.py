import json
import random

import council_veto as V


def bars(session, a, b):
    return [{'date': '%s 09:40:00' % session, 'close': a}, {'date': '%s 15:55:00' % session, 'close': b}]


def fake(prices):
    def fetch(symbol, session):
        p = prices.get((symbol, session))
        return bars(session, *p) if p else []
    return fetch


def test_y_is_signed_against_xiu_and_missing_bars_are_counted_not_filled():
    pos = [{'session': '2026-10-05', 'ticker': 'AAA.TO', 'side': 'LONG', 'oppose': 2, 'endorse': 1, 'members': 4},
           {'session': '2026-10-05', 'ticker': 'BBB.TO', 'side': 'SHORT', 'oppose': 0, 'endorse': 3, 'members': 4},
           {'session': '2026-10-05', 'ticker': 'GONE.TO', 'side': 'LONG', 'oppose': 0, 'endorse': 3, 'members': 4}]
    fetch = fake({('XIU.TO', '2026-10-05'): (100, 101), ('AAA.TO', '2026-10-05'): (10, 10.3),
                  ('BBB.TO', '2026-10-05'): (50, 49)})
    rows, missing = V.score(pos, fetch)
    by = {r['ticker']: r for r in rows}
    assert round(by['AAA.TO']['y'], 6) == 2.0            # +3% less XIU's +1%
    assert round(by['BBB.TO']['y'], 6) == 3.0            # short: −(−2% − 1%)
    assert by['AAA.TO']['vetoed'] and not by['BBB.TO']['vetoed']
    assert missing == [{'session': '2026-10-05', 'ticker': 'GONE.TO', 'side': 'LONG', 'why': 'no bars'}]


def synthetic(edge, sessions=24, seed=1):
    rng = random.Random(seed)
    rows = []
    for i in range(sessions):
        s = '2026-10-%02d' % (i + 1)
        for k in range(10):
            vetoed = k < 4
            rows.append({'session': s, 'ticker': 'T%d' % k, 'side': 'LONG', 'oppose': 2 if vetoed else 0,
                         'endorse': 1, 'members': 4, 'vetoed': vetoed,
                         'y': rng.gauss(-edge if vetoed else 0.0, 1.5), 'raw': 0.0})
    return rows


def test_a_large_planted_gap_sorts_and_noise_does_not():
    assert V.verdict(synthetic(2.0), draws=500)['status'] == 'VETO_SORTS'
    v = V.verdict(synthetic(0.0), draws=500)
    assert v['status'] in ('NULL', 'UNDERPOWERED') and v['control']['planted_pct'] == 1.0


def test_backwards_is_its_mirror():
    rows = synthetic(-2.0)
    assert V.verdict(rows, draws=500)['status'] == 'OBJECTIONS_BACKWARDS'


def test_the_pin_holds_no_return():
    data = json.loads(V.PIN.read_text())
    assert len(data['positions']) == 239
    for p in data['positions']:
        assert not ({'y', 'raw', 'return', 'ret'} & set(p))
