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
