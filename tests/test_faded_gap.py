"""Day-155 (PREREGISTER_day155_faded_gap.md): the faded gap's setup is the
registration's own count, the placebo moves an event at least five sessions,
and the bar is the one registered. Synthetic bars only; no network."""
import csv

import numpy as np
import pandas as pd

import faded_gap as G


def registered_events(daily, lo, hi, nx):
    """The registration's counting code (2026-11-24, before any return), verbatim."""
    rows = [r for r in daily if all(x and x > 0 for x in r[1:5])]
    out = []
    for i in range(15, len(rows)):
        d1, d2 = rows[i], rows[i-1]
        if nx.get(d2[0]) != d1[0]: continue
        win = rows[i-14:i+1]
        if any(nx.get(win[k][0]) != win[k+1][0] for k in range(14)): continue
        tr = [max(r[2]-r[3], abs(r[2]-p[4]), abs(r[3]-p[4])) for p, r in zip(win[:-1], win[1:])]
        atr = float(np.mean(tr))
        if atr <= 0: continue
        g = (d1[1]-d2[4])/atr
        d = nx.get(d1[0])
        if d is None or not (lo <= d <= hi): continue
        if g >= 1 and d1[4] < d1[1]: out.append((d, 'SHORT', g))
        elif g <= -1 and d1[4] > d1[1]: out.append((d, 'LONG', g))
    return out


CAL = [d.date().isoformat() for d in pd.bdate_range('2024-01-01', periods=320)]


def series(seed, holes=0, jump=0.03):
    """[[date, o, h, l, c, vol]] on CAL with random gaps, some of them faded,
    and `holes` sessions missing."""
    rng = np.random.default_rng(seed)
    rows, c = [], 100.0
    for d in CAL:
        o = c * (1 + rng.normal(0, 0.006) + rng.choice([0, jump, -jump], p=[0.8, 0.1, 0.1]))
        c2 = o * (1 + rng.normal(0, 0.012))
        h, l = max(o, c2) * (1 + abs(rng.normal(0, 0.004))), min(o, c2) * (1 - abs(rng.normal(0, 0.004)))
        rows.append([d, o, h, l, c2, 1000.0])
        c = c2
    for k in rng.choice(np.arange(20, len(rows)), size=holes, replace=False):
        rows[k] = None
    return [r for r in rows if r is not None]


def market():
    return [[d, 10, 10.1, 9.9, 10, 1.0] for d in CAL]


def test_the_setup_is_the_registration_count():
    nx = G.next_session(market())
    lo, hi = CAL[30], CAL[-1]
    for seed, holes in ((1, 0), (2, 5), (3, 25), (4, 60)):
        s = series(seed, holes)
        got = [(d, side, g) for d, side, g, _ in G.faded(G.prior_sessions(s, nx, lo, hi))]
        want = registered_events(s, lo, hi, nx)
        assert got == want and len(want) > 0, seed


def day(d, o, h, l, c):
    return [d, o, h, l, c, 1.0]


def flat(n, c=100.0):
    """n quiet sessions with a true range of exactly 2 (ATR 2)."""
    return [day(CAL[i], c, c + 1, c - 1, c) for i in range(n)]


def test_a_faded_up_gap_is_a_short_and_a_faded_down_gap_a_long():
    nx = G.next_session(market())
    up = flat(16) + [day(CAL[16], 103.0, 103.5, 100.5, 101.0)]          # gaps 3 above 100, closes below its open
    (d, g, o1, c1, c2), = [r for r in G.prior_sessions(up, nx, CAL[0], CAL[-1]) if r[0] == CAL[17]]
    tr = [2.0] * 13 + [max(103.5 - 100.5, 3.5, 0.5)]
    assert abs(g - 3.0 / np.mean(tr)) < 1e-12 and (o1, c1, c2) == (103.0, 101.0, 100.0)
    assert G.faded([(d, g, o1, c1, c2)]) == [(CAL[17], 'SHORT', g, False)]
    full = flat(16) + [day(CAL[16], 103.0, 103.5, 99.0, 99.5)]           # closed back below d-2's close
    f = G.faded(G.prior_sessions(full, nx, CAL[17], CAL[17]))[0]
    assert f[1] == 'SHORT' and f[3] is True
    down = flat(16) + [day(CAL[16], 97.0, 99.5, 96.5, 99.0)]
    assert G.faded(G.prior_sessions(down, nx, CAL[17], CAL[17]))[0][1] == 'LONG'
    kept = flat(16) + [day(CAL[16], 103.0, 104.5, 102.5, 104.0)]         # the gap held: no fade
    rows = G.prior_sessions(kept, nx, CAL[17], CAL[17])
    assert G.faded(rows) == [] and G.held(rows)[0][1] == 'LONG'


def test_a_hole_in_the_fifteen_sessions_skips_the_name():
    nx = G.next_session(market())
    s = flat(16) + [day(CAL[16], 103.0, 103.5, 100.5, 101.0)]
    del s[5]                                       # one market session missing among the 15
    assert G.prior_sessions(s, nx, CAL[17], CAL[17]) == []


def test_the_placebo_session_is_at_least_five_sessions_away():
    ps = np.array([i for i in range(60) if i not in (3, 17, 40)])
    rng = np.random.default_rng(155)
    u = G.draw_away(ps, 20, rng, 20000)
    picked = set(ps[u].tolist())
    assert all(abs(x - 20) >= 5 for x in picked)
    assert picked == {x for x in ps.tolist() if abs(x - 20) >= 5}
    assert G.draw_away(np.array([18, 19, 20, 21]), 20, rng, 10) is None


def tsx_fixture():
    """XIU and one name: a faded up-gap on CAL[16], scored on CAL[17]."""
    xiu = {'daily': market(), 'bars': {d: [10.0, 10.0, 10.0, 10.1] for d in CAL}}   # +1% 09:45 -> close
    name = flat(16) + [day(CAL[16], 103.0, 103.5, 100.5, 101.0)] + flat(3)[1:]
    name = [[CAL[i]] + r[1:] for i, r in enumerate(name)]
    bars = {d: [100.0, 100.0, 99.5, 99.0] for d in CAL}                            # -1% 09:45 -> close
    return {'XIU.TO': xiu, 'AAA.TO': {'daily': name, 'bars': bars}}


def test_the_outcome_is_the_side_times_the_name_against_xiu(monkeypatch):
    monkeypatch.setattr(G, 'START', CAL[0])
    monkeypatch.setattr(G, 'END', CAL[-1])
    tsx = tsx_fixture()
    ev = G.intraday_events(tsx, ['AAA.TO'])
    (e,) = [e for e in ev if e['session'] == CAL[17]]
    assert e['side'] == 'SHORT' and abs(e['y'] - (-1) * (-1.0 - 1.0)) < 1e-9
    del tsx['AAA.TO']['bars'][CAL[17]]                     # no bar on d: not an event
    assert not [e for e in G.intraday_events(tsx, ['AAA.TO']) if e['session'] == CAL[17]]


def evs(ys, per=4):
    return [{'ticker': 'T%d.TO' % (i % per), 'session': CAL[i // per], 'side': 'SHORT', 'y': y}
            for i, y in enumerate(ys)]


def test_the_bar_is_the_registered_one():
    rng = np.random.default_rng(0)
    strong = evs(list(0.6 + rng.normal(0, 0.3, 800)))
    zero = np.zeros(2000)
    v = G.verdict(strong, zero, [0.1, 0.2])
    assert v['verdict'] == 'FOLLOWS' and v['control']['detected']
    mean, se, _ = G.clustered([(e['session'], e['y']) for e in strong])
    assert v['control']['t_planted'] == round(0.30 / se, 2) != round((mean + 0.30) / se, 2)
    assert G.verdict(strong, zero, [0.1, -0.2])['verdict'] == 'NULL'       # a secondary disagrees
    small = evs(list(0.10 + rng.normal(0, 0.05, 800)))                     # under the 0.13 cost
    assert G.verdict(small, zero, [0.1, 0.2])['verdict'] == 'NULL'
    weak = evs(list(-0.6 + rng.normal(0, 0.3, 800)))
    assert G.verdict(weak, zero, [-0.1, -0.2])['verdict'] == 'REVERSES'
    noisy = evs(list(rng.normal(0, 8.0, 40)))
    out = G.verdict(noisy, zero, [0.1, 0.2])
    assert out['verdict'] == 'UNDERPOWERED' and out['rejection_70']


def test_the_live_record_sorts_nominations_by_the_prior_session(tmp_path):
    p = tmp_path / 'picks.csv'
    fields = ['session', 'model', 'kind', 'side', 'ticker', 'r_pct']
    rows = [{'session': CAL[17], 'model': 'claude', 'kind': 'nominated', 'side': 'SHORT', 'ticker': 'AAA.TO', 'r_pct': '0.5'},
            {'session': CAL[17], 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'BBB.TO', 'r_pct': '-0.2'},
            {'session': CAL[17], 'model': 'claude', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'CCC.TO', 'r_pct': '0.1'},
            {'session': CAL[17], 'model': 'deepseek', 'kind': 'nominated', 'side': 'LONG', 'ticker': 'AAA.TO', 'r_pct': '1'},
            {'session': CAL[18], 'model': 'claude', 'kind': 'nominated', 'side': 'SHORT', 'ticker': 'AAA.TO', 'r_pct': ''}]
    with open(p, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    gapped = flat(16) + [day(CAL[16], 103.0, 103.5, 100.5, 101.0)] + flat(2)[1:]
    gapped = [[CAL[i]] + r[1:] for i, r in enumerate(gapped)]
    data = {'XIU.TO': market()[:19], 'AAA.TO': gapped, 'BBB.TO': gapped, 'CCC.TO': None}

    def fetch(path, symbol, **params):
        rows = data[symbol]
        return None if rows is None else [{'date': r[0], 'adjOpen': r[1], 'adjHigh': r[2], 'adjLow': r[3],
                                           'adjClose': r[4], 'volume': 1} for r in rows]

    out = G.live(fetch, path=p, first=CAL[10], today=CAL[18])
    assert out['nominations_scored'] == 3
    assert out['follows_a_faded_gap'] == {'n': 1, 'right': 1, 'mean_r_pct': 0.5}
    assert out['against_a_faded_gap'] == {'n': 1, 'right': 0, 'mean_r_pct': -0.2}
    assert out['prior_session_unread'] == 1 and out['names_without_bars'] == ['CCC.TO']
