"""Council lab item 9 on history (day-151): the population is the forward
desk's own filter, on a clock cut at each morning's read."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

import us_preopen_history as H

ET = ZoneInfo('America/New_York')
TWINS = {'AEM.TO': {'us': 'AEM', 'name': 'Agnico Eagle Mines Limited', 'exchange': 'NYSE', 'isin': 'x'}}


def row(when, title, text='summary'):
    return {'publishedDate': when, 'title': title, 'text': text, 'url': 'https://example.com/' + title[-3:]}


def test_months_cover_the_window_and_the_first_overnight():
    m = H.months(dt.date(2026, 7, 2), dt.date(2026, 9, 3))
    assert m[0][0] == dt.date(2026, 6, 25) and m[-1][1] == dt.date(2026, 9, 3)
    assert [a.month for a, _ in m] == [6, 7, 8, 9]


def test_asof_serves_the_feed_as_it_stood_and_refuses_prices():
    hist = {'AEM': [row('2026-07-15 07:00:00', 'Agnico Eagle a'), row('2026-07-15 08:30:00', 'Agnico Eagle b')]}
    read = H.AsOf(hist, dt.datetime(2026, 7, 15, 8, 15, tzinfo=ET))
    assert [r['title'] for r in read('news/press-releases', symbols='AEM', limit=15)] == ['Agnico Eagle a']
    with pytest.raises(KeyError):
        read('historical-chart/1min', symbol='AEM')


def test_population_uses_the_live_filter_and_the_first_read_stands(tmp_path, monkeypatch):
    hist = {'AEM': [row('2026-07-14 17:00:00', 'Agnico Eagle Reports Results'),
                    row('2026-07-15 08:30:00', 'Agnico Eagle Announces Dividend'),
                    row('2026-07-15 06:00:00', 'Investor alert: class action against Agnico Eagle'),
                    row('2026-07-16 08:40:00', 'Agnico Eagle Declares Something'),
                    row('2026-07-16 09:10:00', 'Agnico Eagle Late Release')]}
    monkeypatch.setattr(H, 'press_history', lambda read, twins, a=None, b=None: hist)
    pop = H.population(read=object(), twins=TWINS, days=[dt.date(2026, 7, 15), dt.date(2026, 7, 16)],
                       archive=tmp_path, is_trading=lambda d: d.weekday() < 5)
    evs = [(e['session'], e['read_at'][11:16], [r['title'] for r in e['releases']]) for e in pop['events']]
    # 07-15: the 08:15 read sees the evening release; the 08:30 one waits for no second ask (first read stands)
    assert evs[0] == ('2026-07-15', '08:15', ['Agnico Eagle Reports Results'])
    # 07-16: nothing by 08:15, the 08:40 release is read at 08:55; the 09:10 one is never read
    assert evs[1][:2] == ('2026-07-16', '08:55') and 'Agnico Eagle Late Release' not in evs[1][2]
    assert len(evs) == 2 and pop['notices_dropped'] >= 1
    assert H.summary(pop)['second_read'] == 1


# ── the run (day-151) ───────────────────────────────────────────────────────

def bar(day, hhmm, close):
    return {'date': '%s %s:00' % (day, hhmm), 'close': close}


def test_entry_is_the_last_bar_after_the_release_within_thirty_minutes():
    at = dt.datetime(2026, 7, 15, 8, 15, tzinfo=ET)
    bars = H.bars1([bar('2026-07-15', '07:30', 9.0), bar('2026-07-15', '07:50', 10.0),
                    bar('2026-07-15', '08:10', 11.0), bar('2026-07-15', '08:20', 99.0)])
    assert H.entry(bars, at)[:1] == (11.0,)                                  # 08:10 bar ends 08:11
    rel = dt.datetime(2026, 7, 15, 8, 12, tzinfo=ET)
    assert H.entry(bars, at, rel) == (None, None, 'no bar after the release')
    assert H.entry(bars[:1], at)[2] == 'no bar in the 30 minutes before the read'
    assert H.entry([], at)[2] == 'no one-minute bars'


def test_judge_reads_the_registered_bar():
    rows = [{'session': '2026-07-%02d' % (d + 1), 'material': True, 'w_open': w}
            for d, w in enumerate([0.9, 1.1, 1.0, 0.8, 1.2, 1.0, 0.95, 1.05] * 3)]
    assert H.judge(rows)['verdict'] == 'PASS'
    noisy = [dict(r, w_open=(0.1 if i % 2 else -0.1)) for i, r in enumerate(rows)]
    assert H.judge(noisy)['verdict'] == 'NULL'
    assert H.judge(rows, probe={'void': True})['verdict'] == 'VOID'
    wild = [dict(r, w_open=(50 if i % 2 else -49)) for i, r in enumerate(rows)]
    assert H.judge(wild)['verdict'] == 'UNDERPOWERED'
    routine = [dict(r, material=False) for r in rows]
    assert H.judge(routine)['sessions'] == 0


def test_price_scores_from_the_read_to_the_open(tmp_path, monkeypatch):
    monkeypatch.setattr(H, 'CACHE', tmp_path)
    day = '2026-07-15'
    one = {'AEM': [bar(day, '08:00', 100.0)], 'SPY': [bar(day, '08:05', 500.0)]}
    five = {'AEM': [{'date': day + ' 09:30:00', 'open': 102.0}], 'SPY': [{'date': day + ' 09:30:00', 'open': 500.0}]}

    def read(path, symbol=None, **p):
        if path == 'historical-chart/1min':
            return one[symbol]
        if path == 'historical-chart/5min':
            return five[symbol]
        return [{'date': '2026-07-14', 'close': 100.0 if symbol == 'AEM' else 500.0}]
    pop = {'events': [{'session': day, 'ticker': 'AEM.TO', 'us': 'AEM', 'read_at': day + 'T08:15:00-04:00',
                       'releases': [{'published_at': day + 'T07:47:00-04:00', 'title': 't', 'source': 'FMP press feed'}]}]}
    answers = {day + 'T08:15:00-04:00': {'calls': {day + ':AEM.TO': {'side': 'SHORT', 'confidence': 0.6,
                                                                      'material': True}}}}
    rows, _ = H.price(pop, answers, read)
    assert rows[0]['us_px'] == 100.0 and rows[0]['w_open'] == -2.0 and rows[0]['gap'] == -2.0
