"""The execution lab (day-130, PREREGISTER_day130_learning.md): every scored
pick under other entries, exits, hedges and holds. It never touches a pick or
the scored record."""
import datetime as dt

import pandas as pd

import execution_lab as L

ET = L.ET
DAY = dt.date(2026, 10, 9)


def frame(days):
    """{date: [(time, o, h, l, c)]} -> the 5-minute DataFrame model_picks returns."""
    idx, rows = [], []
    for d, bars in days.items():
        for t, o, h, l, c in bars:
            idx.append(dt.datetime.combine(d, t, tzinfo=ET))
            rows.append({'Open': o, 'High': h, 'Low': l, 'Close': c})
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def session(d, entry=100.0, noon=101.0, close=102.0, low=None, high=None, open_=99.5):
    """09:30, 09:40 (entry), 11:55 (noon), 13:00 and 15:55 (exit) bars."""
    lo = low if low is not None else min(entry, noon, close) - 0.1
    hi = high if high is not None else max(entry, noon, close) + 0.1
    return [(dt.time(9, 30), open_, open_ + 0.2, open_ - 0.2, open_),
            (dt.time(9, 40), entry, entry, entry, entry),
            (dt.time(11, 55), noon, noon, noon, noon),
            (dt.time(13, 0), noon, hi, lo, noon),
            (dt.time(15, 55), close, close, close, close)]


def history(n=20, end=DAY, price=100.0):
    """`n` quiet prior sessions so ATR and beta exist."""
    days, d = {}, end
    while len(days) < n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            p = price * (1 + 0.001 * (len(days) % 3 - 1))
            days[d] = session(d, entry=p, noon=p, close=p, low=p - 1, high=p + 1, open_=p)
    return days


def test_the_same_day_rules_on_one_pick():
    days = {**history(), DAY: session(DAY, entry=100, noon=101, close=102, low=98.5)}
    m = L.measure('LONG', DAY, L.sessions(frame(days)), invalid_at=99.0)
    assert round(m['r'], 4) == 2.0                    # 100 -> 102, as the record scores it
    assert round(m['r_noon'], 4) == 1.0               # 100 -> 101
    assert round(m['r_open'], 4) == round((102 / 99.5 - 1) * 100, 4)
    # the 13:00 bar trades 98.5, below the 99 "wrong if": stopped at that bar's close (101)
    assert m['wrongif_hit'] is True and round(m['r_stop_wrongif'], 4) == 1.0
    assert m['atr_pct'] > 0 and 'r_stop_1atr' in m


def test_a_short_is_signed_and_an_incomplete_session_is_not_measured():
    days = {**history(), DAY: session(DAY, entry=100, noon=99, close=98)}
    assert round(L.measure('SHORT', DAY, L.sessions(frame(days)))['r'], 4) == 2.0
    broken = {DAY: [b for b in session(DAY) if b[0] != dt.time(15, 55)]}
    assert L.measure('LONG', DAY, L.sessions(frame(broken))) is None


def test_the_hedge_removes_the_sector_move():
    stock = {**history(), DAY: session(DAY, entry=100, noon=100, close=102)}
    etf = {**history(price=50.0), DAY: session(DAY, entry=50, noon=50, close=51)}
    m = L.measure('LONG', DAY, L.sessions(frame(stock)), etf='XFN.TO', etf_days=L.sessions(frame(etf)))
    assert m['etf'] == 'XFN.TO' and m['beta'] is not None
    assert round(m['r_vs_etf'], 4) == round(m['r'] - m['beta'] * 2.0, 4)


def test_holds_need_the_later_sessions():
    nxt = DAY + dt.timedelta(days=3)                  # Monday
    days = {**history(), DAY: session(DAY, entry=100, close=102), nxt: session(nxt, close=103)}
    got = L.holds('LONG', DAY, L.sessions(frame(days)))
    assert round(got['r_hold1d'], 4) == 3.0 and 'r_hold3d' not in got


def pick(**kw):
    return {'session': '2026-10-09', 'model': 'top2', 'kind': 'pick', 'side': 'LONG',
            'ticker': 'TD.TO', 'invalid_at': '99', 'scored_at': '2026-10-09T16:21', **kw}


def test_update_adds_scored_picks_once_and_never_rewrites(tmp_path):
    days = {**history(), DAY: session(DAY, entry=100, noon=101, close=102)}
    bars = lambda t: frame(days)
    lab = tmp_path/'lab.csv'
    got = L.update(picks=[pick(), pick(scored_at=''), pick(kind='late', model='claude')],
                   lab=lab, bars_for=bars, now=dt.datetime(2026, 10, 9, 16, 30, tzinfo=ET))
    assert got['added'] == 1                          # unscored and late picks are not measured
    first = L.read(lab)
    assert first[0]['r'] == '2.0000'
    later = {d: [(t, o * 2, h * 2, l * 2, c * 2) for t, o, h, l, c in b] for d, b in days.items()}
    L.update(picks=[pick()], lab=lab, bars_for=lambda t: frame(later))
    assert L.read(lab)[0]['r'] == first[0]['r']        # a filled cell is never rewritten


def test_a_failed_fetch_is_counted_not_silent(tmp_path):
    def boom(t):
        raise RuntimeError('429')
    got = L.update(picks=[pick()], lab=tmp_path/'lab.csv', bars_for=boom)
    assert got['fetch_failures'] == {'TD.TO': 'RuntimeError'} and got['added'] == 0


def test_the_table_counts_a_name_once_and_keeps_the_top_two_apart():
    rows = [{'session': '2026-10-09', 'model': m, 'kind': 'selected', 'side': 'LONG', 'ticker': 'TD.TO',
             'r': '1.0', 'r_noon': '0.5'} for m in ('gemini', 'deepseek')]
    rows.append({'session': '2026-10-09', 'model': 'top2', 'kind': 'pick', 'side': 'LONG',
                 'ticker': 'TD.TO', 'r': '1.0', 'r_noon': '0.5'})
    text = '\n'.join(L.table(rows))
    assert '— 1 picks over 1 sessions' in text        # three rows, one outcome
    assert '| Exit at noon | 1 | 100% | +0.50% | -0.50% | 0.00 |' in text
    assert 'never applied' in text


def test_the_review_appends_the_lab_and_survives_its_failure():
    import daily_review
    ok = daily_review.lab_section(update=lambda: {'fetch_failures': {'ARX.TO': 'HTTPError'}},
                                  table=lambda: ['## Execution lab'])
    assert '## Execution lab' in ok and 'ARX.TO (HTTPError)' in ok

    def broken():
        raise OSError('disk')
    assert 'Execution lab unavailable (OSError)' in daily_review.lab_section(update=broken)


def test_the_council_section_carries_the_exit_note():
    import council as K
    import top_picks
    from test_council import counted, council_snap
    text = '\n'.join(top_picks.table(K.decide(counted(), council_snap()), concise=True))
    assert L.NOON_NOTE in text
    reg = open('PREREGISTER_day130_learning.md').read()
    assert 'noon exit' in reg and 'never applied to the scored record' in reg
