"""Day-149b — the commodity nowcast and its history test (PREREGISTER_day149_nowcast.md)."""
import datetime as dt
import random
from pathlib import Path

import pytest

import nowcast as N
import nowcast_history as H

ROOT = Path(__file__).resolve().parent.parent
D = dt.date.fromisoformat
SECTORS = {'K.TO': {'industry': 'Gold'}, 'AG.TO': {'industry': 'Silver'}, 'RY.TO': {'industry': 'Banks - Diversified'}}
TWINS = {'K.TO': {'us': 'KGC'}, 'RY.TO': {'us': 'RY'}}


def daily(start, end, price):
    out, day = [], D(start)
    while day <= D(end):
        if day.weekday() < 5:
            out.append({'date': day.isoformat(), 'price': price(day) if callable(price) else price})
        day += dt.timedelta(days=1)
    return out


def test_a_report_covers_the_last_quarter_that_ended_two_weeks_before_it():
    for day, want in (('2026-10-28', (2026, 3)), ('2026-02-12', (2025, 4)), ('2026-04-10', (2025, 4)),
                      ('2026-04-14', (2026, 1)), ('2026-07-29', (2026, 2)), ('2026-01-14', (2025, 4))):
        assert N.quarter(D(day)) == want, day
    assert N.previous((2026, 1)) == (2025, 4) and N.quarter_end(2025, 4) == D('2025-12-31')


def test_a_quarters_average_needs_most_of_its_days():
    rows = daily('2026-04-01', '2026-06-30', 100.0) + daily('2026-07-01', '2026-07-20', 110.0)
    assert N.averages(rows) == {(2026, 2): 100.0}


def test_the_nowcast_carries_last_quarters_revenue_to_this_quarters_price():
    avgs = {(2026, 2): 4000.0, (2026, 3): 4200.0}
    assert N.estimate(1000.0, avgs, (2026, 3)) == pytest.approx(1050.0)
    assert N.estimate(1000.0, avgs, (2026, 2)) is None and N.estimate(0, avgs, (2026, 3)) is None
    assert N.gap(1050.0, 1000.0) == pytest.approx(0.05) and N.gap(1050.0, None) is None


def test_a_side_needs_three_percent_and_a_gap_beyond_the_guard_takes_none():
    assert N.side(0.029) is None and N.side(0.03) == 'LONG' and N.side(-0.03) == 'SHORT'
    assert N.side(0.25) == 'LONG' and N.side(0.251) is None and N.side(-0.4) is None and N.side(None) is None
    assert (N.THETA, N.GUARD, N.LAG_DAYS, N.MIN_PRICES) == (0.03, 0.25, 14, 55)


def earnings(*rows):
    return [{'date': d, 'revenueActual': a, 'revenueEstimated': e} for d, a, e in rows]


def test_history_pairs_each_quarter_with_the_one_before_and_drops_a_doubled_quarter():
    avgs = {(2025, 4): 100.0, (2026, 1): 110.0, (2026, 2): 121.0, (2026, 3): 121.0}
    rows = earnings(('2026-02-12', 1000, 990), ('2026-04-29', 1150, 1000), ('2026-07-29', 1200, 1250),
                    ('2026-10-20', 1300, 1200), ('2026-10-28', 1310, 1200))          # two rows for Q3
    out = N.history(rows, avgs)
    assert [h['quarter'] for h in out] == ['2026Q1', '2026Q2']
    q1, q2 = out
    assert q1['nowcast'] == pytest.approx(1100.0) and q1['gap'] == pytest.approx(0.10) and q1['side'] == 'LONG'
    assert q2['nowcast'] == pytest.approx(1265.0) and q2['gap'] == pytest.approx(0.012) and q2['side'] is None
    assert q2['prev'] == 1150 and q2['actual'] == 1200


def reader(coming_us=2000.0, coming_to=2800.0):
    def read(path, **p):
        if path == 'historical-price-eod/light' and p['symbol'] == 'GCUSD':
            return daily('2026-04-01', '2026-06-30', 4000.0) + daily('2026-07-01', '2026-09-30', 4200.0)
        if path == 'historical-price-eod/light' and p['symbol'] == 'USDCAD':
            return [{'date': '2026-10-20', 'price': 1.40}]
        if path == 'earnings' and p['symbol'] == 'KGC':
            return [{'date': '2026-10-28', 'revenueActual': None, 'revenueEstimated': coming_us},
                    {'date': '2026-07-29', 'revenueActual': 2200.0, 'revenueEstimated': 2240.0}]
        if path == 'earnings' and p['symbol'] == 'K.TO':
            return [{'date': '2026-10-28', 'revenueActual': None, 'revenueEstimated': coming_to}]
        raise AssertionError((path, p))
    return read


def test_the_figures_for_a_coming_report():
    out = N.for_report('K.TO', D('2026-10-28'), reader(), twins=TWINS, sectors=SECTORS, today=D('2026-10-21'))
    assert (out['us'], out['metal'], out['quarter'], out['currency']) == ('KGC', 'gold', '2026Q3', 'USD')
    assert out['nowcast'] == 2310 and out['consensus'] == 2000.0 and out['gap_pct'] == 15.5
    assert out['side'] == 'LONG' and out['price_change_pct'] == 5.0 and out['structural'] is False
    assert out['consensus_checked'] is True                    # 2800 / 2000 = 1.40, the spot rate


def test_a_consensus_the_two_listings_disagree_on_is_flagged_and_a_merger_takes_no_side():
    out = N.for_report('K.TO', D('2026-10-28'), reader(coming_to=3300.0), twins=TWINS, sectors=SECTORS,
                       today=D('2026-10-21'))
    assert out['consensus_checked'] is False
    big = N.for_report('K.TO', D('2026-10-28'), reader(coming_us=3200.0, coming_to=4480.0), twins=TWINS,
                       sectors=SECTORS, today=D('2026-10-21'))
    assert big['gap_pct'] == -27.8 and big['side'] is None and big['structural'] is True


def test_only_a_gold_or_silver_producer_with_a_new_york_listing_gets_one():
    assert N.for_report('RY.TO', D('2026-10-28'), reader(), twins=TWINS, sectors=SECTORS) is None
    out = N.for_report('AG.TO', D('2026-10-28'), reader(), twins=TWINS, sectors=SECTORS)
    assert 'no New York listing' in out['reason'] and 'nowcast' not in out
    assert N.metal_for('K.TO', SECTORS) == 'GCUSD' and N.metal_for('AG.TO', SECTORS) == 'SIUSD'


# ── the history test ────────────────────────────────────────────────────────

def test_the_window_enters_before_the_report_and_leaves_three_sessions_after():
    dates = [d['date'] for d in daily('2026-09-01', '2026-11-06', 1.0)]
    entry, exit_, pre = H.window(dates, '2026-10-28')               # a Wednesday
    assert (dates[entry], dates[exit_], dates[pre]) == ('2026-10-27', '2026-11-02', '2026-09-29')
    entry, exit_, _ = H.window(dates, '2026-10-31')                 # a Saturday stands as Monday
    assert (dates[entry], dates[exit_]) == ('2026-10-30', '2026-11-05')
    assert H.window(dates, '2026-11-05') is None and H.window(dates, '2026-09-01') is None
    assert H.window(dates, '2026-09-04')[2] is None                 # no twenty sessions before it


def test_a_quarter_counts_only_when_both_listings_agree_on_the_surprise():
    avgs = {(2025, 4): 100.0, (2026, 1): 110.0, (2026, 2): 110.0}
    us = earnings(('2026-02-12', 1000, 990), ('2026-04-29', 1150, 1000), ('2026-07-29', 1200, 1100))
    to = earnings(('2026-04-30', 1610, 1400), ('2026-07-29', 1680, 1700))          # +15% and -1.2%
    q1, q2 = H.quarters(us, to, avgs)
    assert q1['agree'] is True and q1['surprise'] == pytest.approx(0.15)
    assert q2['agree'] is False and q2['surprise'] == pytest.approx(1200 / 1100 - 1)
    assert [q['agree'] for q in H.quarters(us, [], avgs)] == [False, False]


def rows(n, edge=0.0, seed=7, sd=4.0):
    rng, out, day = random.Random(seed), [], D('2022-01-05')
    for k in range(n):
        side = 'LONG' if k % 2 else 'SHORT'
        s = 1 if side == 'LONG' else -1
        iso = day.isocalendar()
        out.append({'ticker': 'T%d' % (k % 9), 'date': day.isoformat(), 'quarter': 'q', 'gap': 0.05 * s,
                    'side': side, 'agree': True, 'surprise': 0.02 * s, 'before': 0.0,
                    'r': s * edge + rng.gauss(0, sd), 'week': '%d-W%02d' % (iso[0], iso[1])})
        day += dt.timedelta(days=5)
    return out


def test_a_common_report_premium_cancels_in_the_statistic():
    base = H.signed(rows(60))
    lifted = H.signed([{**r, 'r': r['r'] + 5.0} for r in rows(60)])
    assert [round(r['y'], 9) for r in base] == [round(r['y'], 9) for r in lifted]
    unsided = rows(60)
    unsided[0]['side'] = None
    assert len(H.signed(unsided)) == 59


def test_the_bar_finds_a_planted_edge_and_calls_noise_by_its_power():
    found = H.bar(H.signed(rows(200, edge=2.0)))
    assert found['verdict'] == 'NOWCAST_SORTS' and found['t'] >= 3 and found['placebo_p'] < 0.01
    noise = H.bar(H.signed(rows(200)))
    assert noise['verdict'] == 'NULL' and abs(noise['t']) < 3 and noise['control_t_planted_1pct'] >= 3
    thin = H.bar(H.signed(rows(40)))
    assert thin['verdict'] == 'UNDERPOWERED' and thin['control_t_planted_1pct'] < 3
    assert H.bar(H.signed(rows(6)))['verdict'] == 'UNDERPOWERED'
    assert noise['mde_pct'] == pytest.approx((3 + 1.28) * abs(noise['mean_pct'] / noise['t']), abs=0.02)


def test_the_information_check_counts_matches_against_a_half():
    sided = H.signed(rows(100))
    out = H.hit_rate(sided)                              # every surprise carries its side's sign
    assert out == {'n': 100, 'matched': 100, 'rate': 1.0, 't_against_half': None}
    for r in sided[::2]:
        r['surprise'] = -r['surprise']
    assert H.hit_rate(sided)['rate'] == 0.5


def test_the_registration_fixes_what_the_script_does():
    doc = (ROOT/H.REGISTRATION).read_text()
    for t in H.NAMES:
        assert t.split('.')[0] in doc, t
    for needle in ('269 quarters qualify', '65 LONG, 98 SHORT', 'three sessions after', 'XGD.TO', 'seed 149',
                   '2,000', '0.13%', '+1.0% planted', 'rejection #65', '3 points', 'within 3 days'):
        assert needle in doc, needle
    assert (H.HOLD, H.AGREE, H.MATCH_DAYS, H.BAR, H.PLACEBO_P, H.DRAWS, H.SEED, H.COST, H.PLANT) == \
        (3, 0.03, 3, 3.0, 0.01, 2000, 149, 0.13, 1.0)
    assert len(H.NAMES) == 19 and H.BENCH == 'XGD.TO' and (H.START, H.END) == ('2012-01-01', '2026-11-09')
