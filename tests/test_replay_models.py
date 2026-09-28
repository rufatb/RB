"""The replay may not see the future, and its statistics must be able to fail."""
import datetime as dt

import pandas as pd
import pytest

import replay_models as R

TZ = 'America/Toronto'


def raw(days, symbol='ABC.TO'):
    ts, closes = [], []
    for i, d in enumerate(days):
        for t in ('09:30', '12:00', '15:55'):
            ts.append(int(pd.Timestamp(f'{d} {t}', tz=TZ).timestamp()))
            closes.append(10.0 + i)
    n = len(ts)
    return {'meta': {'symbol': symbol, 'currency': 'CAD', 'exchangeName': 'TOR',
                     'instrumentType': 'EQUITY'},
            'timestamp': ts,
            'indicators': {'quote': [{'open': closes, 'high': closes, 'low': closes,
                                      'close': closes, 'volume': [100.0] * n}]}}


DAYS = ['2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24']


def test_truncation_removes_every_bar_on_or_after_the_session():
    out = R.truncate_raw(raw(DAYS), dt.date(2026, 9, 23))
    dates = {pd.Timestamp(t, unit='s', tz='UTC').tz_convert(TZ).date() for t in out['timestamp']}
    assert max(dates) == dt.date(2026, 9, 22)
    assert len(out['indicators']['quote'][0]['close']) == len(out['timestamp']) == 6


def test_the_history_fetcher_serves_only_the_past_and_checks_the_prior_session(monkeypatch):
    monkeypatch.setattr(R, 'fetch_raw', lambda t, i, r: raw(DAYS, t))
    now = dt.datetime(2026, 9, 23, 8, 55, tzinfo=R.ET)
    item = R.history_fetcher('ABC.TO', now)
    import json
    index = json.loads(item['frame'])['index']
    assert max(pd.Timestamp(i).date() for i in index) == dt.date(2026, 9, 22)
    # A history that stops two sessions early is refused, exactly as live.
    monkeypatch.setattr(R, 'fetch_raw', lambda t, i, r: raw(DAYS[:1], t))
    with pytest.raises(ValueError, match='PRIOR_SESSION_MISSING'):
        R.history_fetcher('ABC.TO', now)


def test_the_replay_adapter_refuses_hourly_bars_and_cuts_daily_ones(monkeypatch):
    monkeypatch.setattr(R, 'fetch_raw', lambda t, i, r: raw(DAYS, t))
    a = R.ReplayAdapter(dt.date(2026, 9, 23))
    frame = a._bars_df(a._chart('ABC.TO', '1d', '1y'))
    assert max(i.date() for i in frame.index) == dt.date(2026, 9, 22)
    with pytest.raises(RuntimeError):
        a._chart('ABC.TO', '60m', '1mo')


def test_the_oracle_control_scores_perfectly_and_its_mirror_never():
    pools = {'d1': {'A': 2.0, 'B': 1.0, 'C': -1.0, 'D': -2.0},
             'd2': {'A': -3.0, 'B': 0.5, 'C': 1.5, 'D': -0.5}}
    o = R.oracle(pools)
    assert o['oracle_hit_rate'] == 1.0 and o['anti_oracle_hit_rate'] == 0.0


def test_a_planted_skill_passes_the_bar_and_a_coin_flip_does_not():
    """House rule 4: the statistic must be able to detect an edge before its
    null is reported."""
    rng = __import__('random').Random(1)
    pools, skilled, flips = {}, {}, {}
    for s in range(40):
        names = {f'N{i}': rng.gauss(0, 1) for i in range(40)}
        pools[s] = names
        ranked = sorted(names, key=names.get)
        skilled[s] = [('m', 'LONG', t, None, names[t]) for t in ranked[-2:]] + \
                     [('m', 'SHORT', t, None, -names[t]) for t in ranked[:2]]
        pick = rng.sample(ranked, 4)
        flips[s] = [('m', 'LONG', t, None, names[t]) for t in pick[:2]] + \
                   [('m', 'SHORT', t, None, -names[t]) for t in pick[2:]]
    assert R.analyse(skilled, pools, draws=300)['m']['passes_registered_bar'] is True
    assert R.analyse(flips, pools, draws=300)['m']['passes_registered_bar'] is False


def test_rule_picks_take_the_extremes_and_the_reversal_flips_them():
    cands = [{'ticker': t, 'technicals': {'rel_sector_pct': v}}
             for t, v in (('A', 3), ('B', 1), ('C', -1), ('D', -3), ('E', 0))]
    assert R.rule_picks(cands, k=1) == [('LONG', 'A'), ('SHORT', 'D')]
    assert R.rule_picks(cands, k=1, reverse=True) == [('LONG', 'D'), ('SHORT', 'A')]
