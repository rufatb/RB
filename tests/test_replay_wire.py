"""Day-118 replay: no release after 08:55 reaches a pool, and the statistic can fail."""
import datetime as dt
import random

import newswire as N
import replay_wire as W

ET = N.ET
S = dt.date(2026, 9, 28)


def rel(url, at, tickers):
    return {'url': f'https://www.newswire.ca/news-releases/{url}.html', 'title': f'Release {url}',
            'published_at': at, 'tickers': tickers, 'source': 'newswire.ca'}


def test_no_release_at_or_after_0855_reaches_the_pool_but_the_event_set_runs_to_0930(tmp_path, monkeypatch):
    monkeypatch.setattr(N, 'ARCHIVE', tmp_path)
    N.append([rel('a', '2026-09-28T07:00:00-04:00', ['AAA.TO']),
              rel('b', '2026-09-28T09:10:00-04:00', ['BBB.TO']),
              rel('c', '2026-09-28T11:00:00-04:00', ['CCC.TO']),
              rel('d', '2026-09-24T12:00:00-04:00', ['DDD.TO'])])       # 3 days before: not an event
    pool = {'candidates': [{'ticker': t, 'headlines': []} for t in ('AAA.TO', 'BBB.TO', 'CCC.TO', 'DDD.TO')],
            'macro': {}}
    out = W.with_wire(S, pool)
    shown = {c['ticker']: c['headlines'] for c in out['candidates']}
    assert [h['evidence_metadata']['classification'] for h in shown['AAA.TO']] == ['ISSUER_RELEASE']
    assert shown['BBB.TO'] == [] and shown['CCC.TO'] == [] and shown['DDD.TO'] == []
    assert out['events'] == ['AAA.TO', 'BBB.TO']
    for heads in shown.values():
        for h in heads:
            assert dt.datetime.fromisoformat(h['published_at']) < dt.datetime(2026, 9, 28, 8, 55, tzinfo=ET)


def test_the_direction_test_passes_a_planted_edge_and_fails_a_coin():
    rng = random.Random(3)
    sessions = [f'2026-08-{d:02d}' for d in range(1, 29)]
    names = {s: {f'N{i}': rng.gauss(0, 1) for i in range(3)} for s in sessions}
    events = {s: set(v) for s, v in names.items()}
    ctl = W.controls(names, events)
    assert ctl == {'planted': 'PASS', 'coin': 'FAIL', 'event_name_days': 84}


def test_too_few_event_picks_is_underpowered_not_null():
    flat = [('2026-08-01', 'LONG', 1.0)] * 5
    assert W.direction_test(flat)['verdict'] == 'UNDERPOWERED'


def test_event_names_moving_more_is_measured_per_session():
    pools = {f's{i}': {'E': 3.0 * (-1) ** i, 'A': 0.5, 'B': -0.5} for i in range(10)}
    events = {s: {'E'} for s in pools}
    out = W.moves_more(pools, events)
    assert out['mean'] == 2.5 and out['event_name_days'] == 10
