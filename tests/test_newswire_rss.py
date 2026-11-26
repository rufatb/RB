"""Day-156: when newswire.ca refuses its list, the collector reads the wire's RSS
feeds; a watcher keeps reading them; every read that shows the wire whole is
logged, so the news desk can say which part of its window nobody read."""
import datetime as dt
import json

import pytest

import news_desk
import newswire as N

ET = N.ET


def item(slug, when, title, lead, dateline='TORONTO, Nov. 25, 2026 /CNW/ -- '):
    return (f'<item><title>{title}</title>'
            f'<link>https://www.newswire.ca/news-releases/{slug}.html</link>'
            f'<guid>https://www.newswire.ca/news-releases/{slug}.html</guid>'
            f'<pubDate>{when}</pubDate>'
            f'<description><![CDATA[<p>{dateline}{lead}...</p>]]></description>'
            f'<prn:industry><![CDATA[Mining]]></prn:industry></item>')


def feed(*items):
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            '<title>News Releases</title>' + ''.join(items) + '</channel></rss>')


MAIN = feed(
    item('acme-results-111', 'Thu, 26 Nov 2026 12:30:00 +0000', 'ACME Mining reports Q3 &amp; record output',
         'ACME Mining Corp. (TSX: ACM) (NYSE: ACM) today reported'),
    item('gov-funding-222', 'Wed, 25 Nov 2026 22:00:00 +0000', 'Government announces funding',
         'The Government of Canada today announced'),
)
ENERGY = feed(
    item('oilco-dividend-333', 'Wed, 25 Nov 2026 21:05:00 +0000', 'OilCo declares dividend',
         'OilCo Ltd. (TSX: OIL.B) declared', dateline='CALGARY, AB, Nov. 25, 2026 /CNW/ - '),
    item('acme-results-111', 'Thu, 26 Nov 2026 12:30:00 +0000', 'ACME Mining reports Q3 &amp; record output',
         'ACME Mining Corp. (TSX: ACM) (NYSE: ACM) today reported'),
)


def refusing_list(feeds, asked=None):
    """The list answers HTTP 403; each RSS feed answers from `feeds`."""
    def fetch(url):
        if asked is not None:
            asked.append(url)
        if '/news-releases/news-releases-list/' in url:
            raise ValueError('HTTP_403')
        path = url[len(N.BASE):]
        if path in feeds:
            return feeds[path]
        raise ValueError('HTTP_404')
    return fetch


def test_an_rss_item_reads_as_a_list_card_did():
    (a, b) = N.parse_rss(MAIN)
    url, at, title, summary = a
    assert url == 'https://www.newswire.ca/news-releases/acme-results-111.html'
    assert at == dt.datetime(2026, 11, 26, 7, 30, tzinfo=ET)
    assert title == 'ACME Mining reports Q3 & record output'
    assert summary.startswith('ACME Mining Corp. (TSX: ACM)')        # the dateline dropped
    row = N.rss_row(url, at, title, summary)
    assert row['tickers'] == ['ACM.TO'] and row['source'] == N.RSS_SOURCE
    assert row['published_at'] == '2026-11-26T07:30:00-05:00'
    card = N.list_row(url, 'Nov 26, 2026, 07:30 ET', title, summary, dt.date(2026, 11, 26), 'X')
    assert set(row) == set(card)                         # the same fields as a card's row
    assert {k: row[k] for k in ('url', 'title', 'published_at', 'tickers', 'summary')} == \
           {k: card[k] for k in ('url', 'title', 'published_at', 'tickers', 'summary')}
    assert N.parse_rss(ENERGY)[0][3].startswith('OilCo Ltd. (TSX: OIL.B)')
    assert N.symbols(N.parse_rss(ENERGY)[0][3]) == ['OIL-B.TO']


def test_an_item_that_cannot_make_a_row_is_named():
    at = dt.datetime(2026, 11, 26, 7, 30, tzinfo=ET)
    with pytest.raises(ValueError, match='NOT_A_RELEASE_URL'):
        N.rss_row('https://example.com/x-1.html', at, 'T', 'S')
    with pytest.raises(ValueError, match='NO_RSS_TIME'):
        N.rss_row('https://www.newswire.ca/news-releases/x-1.html', None, 'T', 'S')
    with pytest.raises(ValueError, match='NO_RELEASE_TITLE'):
        N.rss_row('https://www.newswire.ca/news-releases/x-1.html', at, '', 'S')
    bad = feed(item('x-9', 'not a date', 'T', 'S'))
    assert N.parse_rss(bad)[0][1] is None


def test_a_refused_list_is_read_from_the_feeds_once_each(tmp_path):
    state = tmp_path / 'state'
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    asked = []
    fetch = refusing_list({N.RSS_MAIN: MAIN, '/rss/energy-latest-news/energy-latest-news-list.rss': ENERGY}, asked)
    out = N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', fetch=fetch, pause=0,
                    now=now, state_dir=state)
    assert out['list_pages'] == 0 and out['list_error'] == 'page 1: ValueError'
    rss = out['rss']
    assert rss['rss_answered'] == 2 and rss['archived'] == 3 and out['archived'] == 3
    assert set(rss['feed_errors']) == set(N.RSS_FEEDS) - {N.RSS_MAIN, '/rss/energy-latest-news/energy-latest-news-list.rss'}
    assert set(rss['feed_errors'].values()) == {'HTTP_404'}
    assert rss['with_tsx_symbol'] == 2 == out['with_tsx_symbol']
    rows = N.read(tmp_path / 'wire')
    assert sorted(r['url'].rsplit('/', 1)[-1] for r in rows) == sorted(['acme-results-111.html', 'gov-funding-222.html',
                                                          'oilco-dividend-333.html'])
    assert {r['source'] for r in rows} == {N.RSS_SOURCE}
    assert not any('/news-releases/acme' in u for u in asked)     # no release page asked for
    # A second read archives nothing again.
    again = N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', fetch=fetch, pause=0,
                      now=now, state_dir=state)
    assert again['rss']['archived'] == 0 and len(N.read(tmp_path / 'wire')) == 3


def test_a_working_list_is_never_replaced_by_the_feeds(tmp_path):
    cards = ('<div class="row newsCards" lang="en"><a class="newsreleaseconsolidatelink" '
             'href="/news-releases/acme-results-111.html"><h3 class="no-top-margin">'
             '<small>Nov 24, 2026, 07:30 ET</small> ACME Mining reports</h3>'
             '<p class="remove-outline">ACME Mining Corp. (TSX: ACM) today reported</p></a></div>')
    asked = []

    def fetch(url):
        asked.append(url)
        if url == N.LIST_URL.format(page=1):
            return cards
        raise ValueError('HTTP_403')          # release pages refused, as since 11-04

    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    out = N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', fetch=fetch, pause=0,
                    now=now, state_dir=tmp_path / 'state')
    assert 'rss' not in out and not any('/rss/' in u for u in asked)
    # The walk showed the wire whole from its oldest card to now.
    log = [json.loads(l) for l in (tmp_path / 'state' / N.READS).read_text().splitlines()]
    assert log == [{'kind': 'list', 'from': '2026-11-24T07:30:00-05:00', 'to': now.isoformat()}]


def test_the_main_feed_logs_the_stretch_it_shows_whole(tmp_path):
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    N.collect_rss(root=tmp_path / 'wire', fetch=refusing_list({N.RSS_MAIN: MAIN}),
                  feeds=(N.RSS_MAIN,), now=now, state_dir=tmp_path)
    (entry,) = [json.loads(l) for l in (tmp_path / N.READS).read_text().splitlines()]
    # Its oldest item is 17:00 on 11-25; that minute itself may be cut, so from 17:01.
    assert entry == {'kind': 'rss', 'from': '2026-11-25T17:01:00-05:00', 'to': now.isoformat()}
    # A category feed shows only its category: it logs nothing.
    (tmp_path / N.READS).unlink()
    N.collect_rss(root=tmp_path / 'wire2', feeds=('/rss/energy-latest-news/energy-latest-news-list.rss',),
                  fetch=refusing_list({'/rss/energy-latest-news/energy-latest-news-list.rss': ENERGY}),
                  now=now, state_dir=tmp_path)
    assert not (tmp_path / N.READS).exists()


def test_only_the_main_feeds_own_bad_item_voids_its_read(tmp_path):
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    bad = feed(item('x-1', 'Wed, 25 Nov 2026 22:30:00 +0000', '', 'untitled'))       # no title
    energy = '/rss/energy-latest-news/energy-latest-news-list.rss'
    out = N.collect_rss(root=tmp_path / 'w1', fetch=refusing_list({N.RSS_MAIN: MAIN, energy: bad}),
                        feeds=(N.RSS_MAIN, energy), now=now, state_dir=tmp_path / 's1')
    assert out['failures'] == {'NO_RELEASE_TITLE': 1} and out['read_logged'] is True
    main_bad = feed(item('x-2', 'Wed, 25 Nov 2026 22:30:00 +0000', '', 'untitled'),
                    item('acme-results-111', 'Thu, 26 Nov 2026 12:30:00 +0000', 'ACME', 'x'))
    out = N.collect_rss(root=tmp_path / 'w2', fetch=refusing_list({N.RSS_MAIN: main_bad}),
                        feeds=(N.RSS_MAIN,), now=now, state_dir=tmp_path / 's2')
    assert out['failed'] == 1 and 'read_logged' not in out
    assert not (tmp_path / 's2' / N.READS).exists()


def test_coverage_names_the_stretches_no_read_showed():
    start = dt.datetime(2026, 11, 25, 16, 0, tzinfo=ET)
    end = dt.datetime(2026, 11, 26, 9, 30, tzinfo=ET)
    assert N.coverage(start, end) == {'read': False, 'gaps': [[start.isoformat(), end.isoformat()]],
                                      'uncovered_minutes': 1050, 'unreadable_lines': 0}
    for a, b in (('2026-11-25T15:50', '2026-11-25T20:00'), ('2026-11-25T19:30', '2026-11-26T02:00'),
                 ('2026-11-26T06:00', '2026-11-26T09:31')):
        N.log_read('rss', dt.datetime.fromisoformat(a).replace(tzinfo=ET),
                   dt.datetime.fromisoformat(b).replace(tzinfo=ET))
    cov = N.coverage(start, end)
    assert cov['read'] is True and cov['uncovered_minutes'] == 240
    assert cov['gaps'] == [['2026-11-26T02:00:00-05:00', '2026-11-26T06:00:00-05:00']]


def test_the_deadline_reaches_past_the_next_sessions_evening():
    at = lambda *a: dt.datetime(*a, tzinfo=ET)
    assert N.watch_until(at(2026, 11, 26, 10, 40)) == at(2026, 11, 27, 18, 5)   # Thursday, after the open
    assert N.watch_until(at(2026, 11, 27, 8, 12)) == at(2026, 11, 27, 18, 5)    # Friday, before it
    assert N.watch_until(at(2026, 11, 27, 16, 20)) == at(2026, 11, 30, 18, 5)   # Friday evening: Monday


class FakeProc:
    pid = 4242


def test_a_start_spawns_one_watcher_and_a_second_moves_its_deadline(tmp_path):
    spawned = []

    def popen(cmd, **kw):
        spawned.append(cmd)
        assert kw['start_new_session'] is True
        return FakeProc()

    now = dt.datetime(2026, 11, 26, 16, 20, tzinfo=ET)
    assert N.start_watch(now, state_dir=tmp_path, popen=popen, alive=lambda pid: False) == 'started'
    assert spawned and spawned[0][-3:] == ['--watch', '--state-dir', str(tmp_path)]
    ctl = json.loads((tmp_path / N.WATCH_FILE).read_text())
    assert ctl['pid'] == 4242 and ctl['until'] == '2026-11-27T18:05:00-05:00'
    later = dt.datetime(2026, 11, 27, 16, 20, tzinfo=ET)
    assert N.start_watch(later, state_dir=tmp_path, popen=popen, alive=lambda pid: pid == 4242) == 'extended'
    assert len(spawned) == 1
    assert json.loads((tmp_path / N.WATCH_FILE).read_text())['until'] == '2026-11-30T18:05:00-05:00'
    # An earlier start never pulls the deadline back.
    assert N.start_watch(now, state_dir=tmp_path, popen=popen, alive=lambda pid: True) == 'extended'
    assert json.loads((tmp_path / N.WATCH_FILE).read_text())['until'] == '2026-11-30T18:05:00-05:00'
    assert not (tmp_path / 'newswire_watch.lock').exists()


def test_a_start_that_cannot_spawn_says_so_and_never_raises(tmp_path):
    def popen(cmd, **kw):
        raise OSError('no')
    assert N.start_watch(state_dir=tmp_path, popen=popen, alive=lambda pid: False) == 'NOT_STARTED_OSError'
    (tmp_path / 'newswire_watch.lock').mkdir()
    assert N.start_watch(state_dir=tmp_path, popen=popen, alive=lambda pid: False) == 'BUSY'


def test_the_watcher_reads_the_main_feed_often_and_the_rest_hourly_then_stops(tmp_path):
    state = tmp_path / 'state'
    state.mkdir()
    (state / N.WATCH_FILE).write_text(json.dumps({'pid': 7, 'until': '2026-11-26T18:05:00-05:00'}))
    clock = [dt.datetime(2026, 11, 26, 16, 20, tzinfo=ET)]
    asked = []

    def sleep(seconds):
        clock[0] += dt.timedelta(seconds=seconds)

    fetch = refusing_list({N.RSS_MAIN: MAIN, '/rss/energy-latest-news/energy-latest-news-list.rss': ENERGY}, asked)
    assert N.watch(state_dir=state, root=tmp_path / 'wire', fetch=fetch, clock=lambda: clock[0],
                   sleep=sleep, me=7) == 'DONE'
    main_reads = sum(1 for u in asked if u.endswith(N.RSS_MAIN))
    energy_reads = sum(1 for u in asked if 'energy-latest-news' in u)
    assert main_reads == 11 and energy_reads == 2       # 16:20 to 18:05, every 10 min; hourly
    assert len(N.read(tmp_path / 'wire')) == 3
    assert len((state / N.READS).read_text().splitlines()) == 11
    # Another process named in the control file: this one stops at once.
    (state / N.WATCH_FILE).write_text(json.dumps({'pid': 8, 'until': '2026-11-27T18:05:00-05:00'}))
    assert N.watch(state_dir=state, root=tmp_path / 'wire', fetch=fetch, clock=lambda: clock[0],
                   sleep=lambda s: None, me=7) == 'REPLACED'


def test_main_says_the_list_was_refused_and_starts_the_watcher(monkeypatch, capsys):
    base = {'reached_since': False, 'failed': 0, 'from_list': 0, 'page_failures': {},
            'list_error': 'page 1: ValueError'}
    started = []
    monkeypatch.setattr(N, 'start_watch', lambda **k: started.append(k) or 'started')
    monkeypatch.setattr(N, 'collect', lambda *a, **k: {**base, 'rss': {
        'rss_answered': 13, 'rss_feeds': 13, 'archived': 9, 'feed_errors': {}}})
    assert N.main(['--collect', '--since', '2026-11-25']) == 6
    err = capsys.readouterr().err
    assert 'the list was refused' in err and 'the watcher: started' in err and started
    monkeypatch.setattr(N, 'collect', lambda *a, **k: {**base, 'rss': {
        'rss_answered': 0, 'rss_feeds': 13, 'archived': 0, 'feed_errors': {'x': 'HTTP_403'}}})
    assert N.main(['--collect', '--since', '2026-11-25']) == 4
    assert 'the wire was not read' in capsys.readouterr().err


def test_the_news_desk_reads_an_rss_release_as_it_read_a_list_card(tmp_path):
    """The seam: RSS -> archive file -> news_desk.events, unchanged."""
    import pandas as pd
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', pause=0, now=now, state_dir=tmp_path,
              fetch=refusing_list({N.RSS_MAIN: MAIN, '/rss/energy-latest-news/energy-latest-news-list.rss': ENERGY}))
    idx = pd.bdate_range('2026-10-01', '2026-11-26', tz='America/Toronto')
    frame = pd.DataFrame({'Close': 50.0, 'Volume': 1e6}, index=idx)
    chart = lambda t: ({'instrumentType': 'EQUITY', 'currency': 'CAD'}, frame)
    evs, excluded = news_desk.events(dt.date(2026, 11, 26), chart=chart, archive=tmp_path / 'wire')
    assert [e['ticker'] for e in evs] == ['ACM.TO', 'OIL-B.TO'] and excluded == {}
    assert evs[0]['releases'][0]['title'] == 'ACME Mining reports Q3 & record output'
