"""Day-143 (council lab item 4, PREREGISTER_day143_report_day.md): the report-day
size rule's machinery, on synthetic data only. No FMP call is made here."""
import datetime as dt

import numpy as np

import report_day as R


def cal(n=140, start=dt.date(2024, 1, 2)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def test_windows_map_a_report_to_its_first_session_and_the_next():
    c = ['2024-01-02', '2024-01-03', '2024-01-05', '2024-01-08']
    wins, outside = R.windows(['2024-01-04', '2023-12-01'], c, '2024-01-02', '2024-01-31')
    assert wins == [('2024-01-04', '2024-01-05', '2024-01-08')] and outside == 1
    shifted, _ = R.windows(['2024-01-05'], c, '2024-01-02', '2024-01-31', shift=2)
    assert shifted == [('2024-01-05', '2024-01-02', '2024-01-03')]
    assert R.label([('x', 'A', 'B'), ('y', 'B', 'C')]) == {'A': 'D0', 'B': 'D0', 'C': 'D1'}


def row(t, d, y, m=0.1, atr=2.0, win=''):
    return (t, d, y, y, 0.5, m, atr, win, '')


def test_the_filter_drops_what_the_two_live_rules_pass_over():
    rows = [row('N%d' % i, 'D', 0.1, atr=float(i)) for i in range(1, 21)]        # cut = 18.1
    rows[0] = row('N1', 'D', 0.1, m=-1.2, atr=1.0)                                # a big mover
    keep, counts = R.comparison(rows + [row('X', 'E', 0.1)])                      # E: one name only
    names = {r[0] for r in keep}
    assert 'N1' not in names and 'N19' not in names and 'N20' not in names and 'N18' in names
    assert counts['passed_over_mover'] == 1 and counts['passed_over_wild'] == 2
    assert counts['sessions_too_few_names'] == 1


def test_the_control_finds_a_planted_quarter_and_not_noise():
    rest = np.random.default_rng(1).normal(0, 1, 4000)
    c = R.control(rest, 400)
    assert c['unscaled'] < R.BAR <= c['scaled'] and c['detected']


def test_the_verdict_needs_all_four_and_a_detected_control():
    lean_ok = {'a': {'t': 1.0}, 'b': {'t': -0.5}}
    ok = {'detected': True}
    assert R.verdict(1.3, lean_ok, 1.0, 1.2, ok)[1] == 'PASS'
    assert R.verdict(1.3, lean_ok, 1.2, 1.2, ok)[1] == 'FAIL'                     # the placebo swings too
    assert R.verdict(1.3, {'a': {'t': 2.5}, 'b': {'t': 0}}, 1.0, 1.2, ok)[1] == 'FAIL'   # it leans
    assert R.verdict(1.3, lean_ok, 1.0, 1.05, ok)[1] == 'FAIL'                    # survivors only
    assert R.verdict(1.3, lean_ok, 1.0, 1.2, {'detected': False})[1].startswith('UNDERPOWERED')


def synthetic(window_scale, n_names=30, seed=5):
    """A market and n names on one calendar: flat daily bars (no big movers),
    09:45 -> close returns N(0, 1%), and one report a quarter per name whose
    D0 and D1 swing `window_scale` times wider."""
    rng = np.random.default_rng(seed)
    c = cal()
    data = {}

    def eod(seed_):
        r = np.random.default_rng(seed_)
        px, out = 100.0, []
        for d in c:
            px *= 1 + r.normal(0, 0.001)
            out.append([d, px, px * 1.02, px * 0.98, px, 1e6])
        return out
    data[R.MARKET] = {'eod': eod(0), 'bars': {d: [1, 100.0, 100, 100.0] for d in c}, 'reports': []}
    for k in range(n_names):
        reports = [c[j] for j in range(30 + k % 20, len(c) - 2, 45)]
        wins = R.label(R.windows(reports, c, c[0], c[-1])[0])
        bars = {}
        for d in c:
            y = rng.normal(0, 1.0) * (window_scale if d in wins else 1.0)
            bars[d] = [100.0, 100.0, 100.0, 100.0 * (1 + y / 100)]
        data['N%02d' % k] = {'eod': eod(k + 1), 'bars': bars, 'reports': reports}
    return data, c


def test_a_planted_wider_window_shows_and_its_placebo_does_not():
    data, c = synthetic(1.6)
    rows, counts = R.panel(data, R.MARKET, c[20], c[-1], intraday=True)
    keep, _ = R.comparison(rows)
    w, rest, ratio = R.size(keep)
    _, _, placebo = R.size(keep, col=8)
    assert len(w) > 100 and ratio >= R.BAR and placebo < R.BAR
    assert counts['reports_in_window'] > 0
    boot = R.bootstrap(keep, draws=200)
    assert boot['ci95'][0] <= ratio <= boot['ci95'][1]
    data, c = synthetic(1.0)
    keep, _ = R.comparison(R.panel(data, R.MARKET, c[20], c[-1], intraday=True)[0])
    assert R.size(keep)[2] < R.BAR
