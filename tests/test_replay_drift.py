"""Report-day drift (day-130 step 4): the harness, end to end on synthetic FMP
data, must find a planted continuation and must not find one in noise."""
import datetime as dt
import random

import replay_drift as R


def bdays(a, b):
    d, out = dt.date.fromisoformat(a), []
    while d <= dt.date.fromisoformat(b):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def fake_fmp(names, edge, seed=1):
    """earnings, daily bars and 5-minute bars. On each report's D0 the name gaps
    5%; its 10:00 → close move against XIU is sign(x30) × edge + noise."""
    rng = random.Random(seed)
    days = bdays('2023-11-01', R.END)
    reports = {t: [d for i, d in enumerate(days) if d >= R.START and i % 63 == (7 * k) % 63]
               for k, t in enumerate(names)}
    react = {t: set(r) for t, r in reports.items()}
    moves = {}

    def fetch(path, **p):
        t = p.get('symbol')
        if path == 'earnings':
            return [{'date': d, 'epsActual': 1.0} for d in reports[t]]
        if path == 'historical-price-eod/full':
            out, close = [], 50.0
            for d in days:
                gap = 0.05 if d in react[t] else rng.uniform(-0.004, 0.004)
                op = close * (1 + gap)
                close = op * (1 + rng.uniform(-0.01, 0.01))
                out.append({'date': d, 'open': op, 'close': close})
            return out[::-1]
        rows = []
        for d in bdays(p['from'], p['to']):
            key = (t, d)
            if key not in moves:
                x = rng.uniform(-0.02, 0.02)
                event = t in react and d in react[t]
                y = (edge if x > 0 else -edge) if event else 0.0
                moves[key] = (x, y / 100 + rng.gauss(0, 0.008), rng.gauss(0, 0.004))
            x, rest, noon = moves[key] if t != 'XIU.TO' else (0.0, 0.0, 0.0)
            op = 40.0
            p1000 = op * (1 + x)
            rows += [{'date': d + ' 09:30:00', 'open': op, 'close': op},
                     {'date': d + ' 09:55:00', 'open': p1000, 'close': p1000},
                     {'date': d + ' 11:55:00', 'open': p1000, 'close': p1000 * (1 + noon)},
                     {'date': d + ' 15:55:00', 'open': p1000, 'close': p1000 * (1 + rest)}]
        return rows
    return fetch


NAMES = ['N%02d.TO' % i for i in range(40)]


def test_a_planted_continuation_passes_and_noise_does_not():
    rows, placebo, counts = R.run(NAMES, fake_fmp(NAMES, edge=0.6))
    assert counts['events'] == counts['reports'] > 300 and counts['no_bars'] == 0
    out = R.summarize(rows, placebo, counts, {})
    assert out['verdict'] == 'PASS', out['checks']
    assert abs(out['primary']['mean_pct'] - 0.6) < 0.15
    rows, placebo, counts = R.run(NAMES, fake_fmp(NAMES, edge=0.0))
    null = R.summarize(rows, placebo, counts, {})
    assert null['verdict'] == 'FAIL' and null['checks']['control_detects_planted_0_5']
    assert abs(null['primary']['t']) < 3


def test_the_reaction_day_is_chosen_from_its_own_gap_only():
    days = [('2026-01-%02d' % i, 10.0, 10.0) for i in range(1, 23)]      # 21 flat gaps, then:
    days += [('2026-01-23', 10.0, 10.0), ('2026-01-26', 10.5, 10.5)]      # D0 flat, D1 +5%
    days = [(d, o * (1 + 0.001 * (i % 3)), c) for i, (d, o, c) in enumerate(days[:22])] + days[22:]
    d0, d1, ev, why = R.reaction(days, '2026-01-23')
    assert (d0, d1, ev, why) == ('2026-01-23', '2026-01-26', '2026-01-26', None)
    assert R.reaction(days[:23], '2026-01-23')[2] is None                  # D1 not there yet: no event
    assert R.reaction(days, '2026-01-05')[3] == 'no daily history'


def test_the_signal_and_outcome_are_against_xiu():
    s = {'open': 10.0, 'p1000': 10.2, 'noon': 10.3, 'close': 10.404}
    m = {'open': 20.0, 'p1000': 20.0, 'noon': 20.0, 'close': 20.2}
    x30, y = R.xy(s, m)
    assert round(x30, 6) == 2.0 and round(y, 6) == 1.0                    # +2% name, +1% market → +1
    s2 = {**s, 'p1000': 9.8, 'close': 9.604}
    x30, y = R.xy(s2, m)
    assert x30 < 0 and round(y, 6) == 3.0                                 # short: −2% name, +1% market
    assert R.xy({**s, 'p1000': 10.0}, {**m, 'p1000': 20.0})[1] is None
