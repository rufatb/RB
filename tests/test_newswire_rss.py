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
    assert set(card) <= set(row) and row['tickers_from'] == 'opening'   # a card's fields, and where its symbols came from
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


def test_the_feeds_are_read_first_and_a_refused_list_costs_only_its_request(tmp_path):
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


def test_a_working_list_fills_a_hole_the_sitemap_cannot_reach(tmp_path):
    cards = ('<div class="row newsCards" lang="en"><a class="newsreleaseconsolidatelink" '
             'href="/news-releases/acme-results-111.html"><h3 class="no-top-margin">'
             '<small>Nov 24, 2026, 07:30 ET</small> ACME Mining reports</h3>'
             '<p class="remove-outline">ACME Mining Corp. (TSX: ACM) today reported</p></a></div>')
    asked = []

    def fetch(url):
        asked.append(url)
        if url == N.LIST_URL.format(page=1):
            return cards
        raise ValueError('HTTP_403')          # feeds, sitemap and release pages refused

    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    out = N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', fetch=fetch, pause=0,
                    now=now, state_dir=tmp_path / 'state')
    assert out['list_asked'] is True and out['reached_since'] is True
    assert out['sitemap']['page_errors'] == {N.SITEMAP_URL: 'HTTP_403'}
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
    assert not (state / N.READS).exists()  # The static 07:30 feed cannot certify the evening.
    # Another process named in the control file: this one stops at once.
    (state / N.WATCH_FILE).write_text(json.dumps({'pid': 8, 'until': '2026-11-27T18:05:00-05:00'}))
    assert N.watch(state_dir=state, root=tmp_path / 'wire', fetch=fetch, clock=lambda: clock[0],
                   sleep=lambda s: None, me=7) == 'REPLACED'


def test_main_exits_whole_in_part_or_unread_and_starts_no_watcher(monkeypatch, capsys):
    base = {'reached_since': True, 'failed': 0, 'from_list': 0, 'page_failures': {},
            'list_error': None, 'list_pages': 0,
            'rss': {'rss_answered': 13, 'rss_feeds': 13, 'archived': 9, 'feed_errors': {}},
            'sitemap': {'answered': 5, 'pages': 5, 'page_errors': {}}}
    started = []
    monkeypatch.setattr(N, 'start_watch', lambda **k: started.append(k) or 'started')
    monkeypatch.setattr(N, 'collect', lambda *a, **k: dict(base))
    assert N.main(['--collect', '--since', '2026-11-25']) == 0
    monkeypatch.setattr(N, 'collect', lambda *a, **k: {
        **base, 'reached_since': False, 'list_error': 'page 1: ValueError',
        'sitemap': {'answered': 2, 'pages': 5, 'page_errors': {'p3': 'HTTP_403'}}})
    assert N.main(['--collect', '--since', '2026-11-25']) == 6
    assert 'read only in part' in capsys.readouterr().err
    monkeypatch.setattr(N, 'collect', lambda *a, **k: {
        **base, 'reached_since': False, 'list_error': 'page 1: ValueError',
        'rss': {'rss_answered': 0, 'rss_feeds': 13}, 'sitemap': {'answered': 0, 'pages': 0,
                                                                 'page_errors': {'x': 'HTTP_403'}}})
    assert N.main(['--collect', '--since', '2026-11-25']) == 4
    assert 'the wire was not read' in capsys.readouterr().err
    assert started == []                    # day-156b: never started automatically


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


def sm_entry(slug, when, title, tickers='', keywords='Mining'):
    return (f'<url><loc>https://www.newswire.ca/news-releases/{slug}.html</loc><news:news>'
            '<news:publication><news:name>Canada NewsWire</news:name><news:language>en</news:language>'
            '</news:publication><news:genres>PressRelease</news:genres>'
            f'<news:publication_date>{when}</news:publication_date><news:title>{title}</news:title>'
            f'<news:keywords>{keywords}</news:keywords>'
            + (f'<news:stock_tickers>{tickers}</news:stock_tickers>' if tickers else '')
            + '</news:news></url>')


def sm_page(*entries):
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns:news="http://www.google.com/schemas/'
            'sitemap-news/0.9">' + ''.join(entries) + '</urlset>')


SM_INDEX = ('<?xml version="1.0" encoding="UTF-8"?><sitemapindex>'
            '<sitemap><loc>https://www.newswire.ca/sitemap-news.xml?page=1</loc></sitemap>'
            '<sitemap><loc>https://www.newswire.ca/sitemap-news.xml?page=2</loc></sitemap></sitemapindex>')
SM1 = sm_page(sm_entry('acme-results-111', '2026-11-26T07:30:00-05:00', 'ACME Mining reports Q3 &amp; record output',
                       'Toronto:ACM,NYSE:ACM'),
              sm_entry('oilco-deal-444', '2026-11-25T18:10:00-05:00', 'OilCo agrees to buy GasCo',
                       'Toronto:OIL.B,TorontoVE:GAS'))
SM2 = sm_page(sm_entry('ciro-halt-555', '2026-11-25T17:00:00-05:00',
                       'Canadian Investment Regulatory Organization Trading Halt - FOO', 'Toronto:FOO'),
              sm_entry('gov-funding-222', '2026-11-24T12:00:00-05:00', 'Government announces funding'))
SITEMAP = {'/sitemap-news.xml': SM_INDEX, '/sitemap-news.xml?page=1': SM1, '/sitemap-news.xml?page=2': SM2}


def test_tagged_symbols_keep_the_toronto_and_venture_tags_in_order():
    assert N.tagged_symbols('Toronto:EMP.A,TorontoVE:GSD,NASDAQ:X,Toronto:LB.PR.H') == \
        ['EMP-A.TO', 'GSD.V', 'LB-PR-H.TO']
    assert N.tagged_symbols('NYSE:BEN,NEO:ZZZ') == [] == N.tagged_symbols('')
    assert N.tagged_symbols('Toronto:DOO,NASDAQ:DOO,Toronto:DOO') == ['DOO.TO']


def test_a_sitemap_entry_reads_as_an_archive_row():
    (a, b) = N.parse_sitemap(SM1)
    url, at, title, tickers, keywords = a
    assert url == 'https://www.newswire.ca/news-releases/acme-results-111.html'
    assert at == dt.datetime(2026, 11, 26, 7, 30, tzinfo=ET) and title == 'ACME Mining reports Q3 & record output'
    row = N.sitemap_row(url, at, title, tickers, keywords)
    assert row['tickers'] == ['ACM.TO'] and row['tickers_from'] == 'tag' and row['source'] == N.SITEMAP_SOURCE
    assert N.sitemap_row(*b)['tickers'] == ['OIL-B.TO', 'GAS.V']
    halt = N.parse_sitemap(SM2)[0]
    assert N.sitemap_row(*halt)['tickers'] == []            # the regulator's notice, not the issuer's
    with pytest.raises(ValueError, match='NO_SITEMAP_TIME'):
        N.sitemap_row(url, None, title, tickers)
    with pytest.raises(ValueError, match='NOT_A_RELEASE_URL'):
        N.sitemap_row('https://www.newswire.ca/sitemap-news.xml', at, title, tickers)
    card_keys = set(N.list_row(url, 'Nov 26, 2026, 07:30 ET', title, 'x', dt.date(2026, 11, 26), 'X'))
    assert card_keys - {'summary'} <= set(row)        # a sitemap entry carries no opening


def test_the_sitemap_is_read_whole_and_logs_its_stretch(tmp_path):
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    out = N.collect_sitemap(root=tmp_path / 'wire', fetch=refusing_list(SITEMAP), now=now,
                            state_dir=tmp_path)
    assert out['pages'] == 2 and out['answered'] == 2 and out['entries'] == 4 and out['whole']
    assert out['archived'] == 4 and out['with_tsx_symbol'] == 2
    assert out['oldest'] == '2026-11-24T12:00:00-05:00'
    (entry,) = [json.loads(l) for l in (tmp_path / N.READS).read_text().splitlines()]
    assert entry == {'kind': 'sitemap', 'from': '2026-11-24T12:01:00-05:00', 'to': now.isoformat()}
    # A page that fails: named, not whole, no stretch logged.
    part = {k: v for k, v in SITEMAP.items() if not k.endswith('page=2')}
    out = N.collect_sitemap(root=tmp_path / 'w2', fetch=refusing_list(part), now=now,
                            state_dir=tmp_path / 's2')
    assert out['page_errors'] == {'https://www.newswire.ca/sitemap-news.xml?page=2': 'HTTP_404'}
    assert out['whole'] is False and not (tmp_path / 's2' / N.READS).exists()


def test_a_feeds_opening_wins_over_the_sitemaps_tag_for_one_release(tmp_path):
    feeds = {N.RSS_MAIN: MAIN, **SITEMAP}
    tagged = dict(SITEMAP, **{'/sitemap-news.xml?page=1': sm_page(
        sm_entry('acme-results-111', '2026-11-26T07:30:00-05:00', 'ACME', 'Toronto:ZZZ,Toronto:ACM'))})
    feeds.update(tagged)
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', fetch=refusing_list(feeds), pause=0,
              now=now, state_dir=tmp_path)
    (row,) = [r for r in N.read(tmp_path / 'wire') if r['url'].endswith('acme-results-111.html')]
    assert row['source'] == N.RSS_SOURCE and row['tickers'] == ['ACM.TO'] and row['tickers_from'] == 'opening'


def test_the_list_is_never_asked_when_the_sitemap_reaches_back(tmp_path):
    asked = []
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    out = N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', pause=0, now=now, state_dir=tmp_path,
                    fetch=refusing_list({N.RSS_MAIN: MAIN, **SITEMAP}, asked))
    assert out['reached_since'] is True and out['list_asked'] is False and out['list_error'] is None
    assert not any('/news-releases/' in u for u in asked)    # no list page, no release page
    assert out['archived'] == 4                               # 2 from the feed, 2 more from the sitemap
    # A sitemap that does not reach back to `since` sends the collector to the list.
    out = N.collect(dt.date(2026, 11, 24), root=tmp_path / 'w2', pause=0, now=now, state_dir=tmp_path,
                    fetch=refusing_list({N.RSS_MAIN: MAIN, **SITEMAP}, asked))
    assert out['list_asked'] is True and out['reached_since'] is False
    assert out['list_error'] == 'page 1: ValueError'


def test_the_news_desk_reads_a_sitemap_release_by_its_tag(tmp_path):
    """The seam: sitemap -> archive file -> news_desk.events."""
    import pandas as pd
    now = dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET)
    N.collect(dt.date(2026, 11, 25), root=tmp_path / 'wire', pause=0, now=now, state_dir=tmp_path,
              fetch=refusing_list(SITEMAP))
    idx = pd.bdate_range('2026-10-01', '2026-11-26', tz='America/Toronto')
    frame = pd.DataFrame({'Close': 50.0, 'Volume': 1e6}, index=idx)
    chart = lambda t: ({'instrumentType': 'EQUITY', 'currency': 'CAD'}, frame)
    evs, excluded = news_desk.events(dt.date(2026, 11, 26), chart=chart, archive=tmp_path / 'wire')
    assert [e['ticker'] for e in evs] == ['ACM.TO', 'OIL-B.TO']     # the halt is no event
    assert evs[1]['releases'][0]['tickers_from'] == 'tag'


# ── day-156f: a quiet wire is not a partial read ─────────────────────────────
#
# On 9 of the 10 Sundays to 11-22 no release came in the 45 minutes before the
# 16:20 read. The sitemap, read whole, then failed the clock's test, and the run
# asked for the list newswire.ca refuses and exited 6. The main feed, read in
# the same run, now vouches for it; nothing logs a stretch no channel showed.

SUNDAY = dt.datetime(2026, 11, 29, 16, 20, tzinfo=ET)
QUIET_INDEX = ('<?xml version="1.0" encoding="UTF-8"?><sitemapindex>'
               '<sitemap><loc>https://www.newswire.ca/sitemap-news.xml?page=1</loc></sitemap></sitemapindex>')
QUIET_PAGE = sm_page(
    sm_entry('acme-update-901', '2026-11-29T14:00:00-05:00', 'ACME Mining update', 'Toronto:ACM'),
    sm_entry('oilco-notice-902', '2026-11-28T11:00:00-05:00', 'OilCo notice', 'Toronto:OIL.B'),
    sm_entry('gov-note-903', '2026-11-27T16:30:00-05:00', 'Government note'),
    sm_entry('fund-dist-904', '2026-11-26T18:00:00-05:00', 'Fund distributions'))
QUIET_SITEMAP = {'/sitemap-news.xml': QUIET_INDEX, '/sitemap-news.xml?page=1': QUIET_PAGE}
QUIET_FEED = feed(
    item('acme-update-901', 'Sun, 29 Nov 2026 19:00:00 +0000', 'ACME Mining update', 'ACME (TSX: ACM) said'),
    item('oilco-notice-902', 'Sat, 28 Nov 2026 16:00:00 +0000', 'OilCo notice', 'OilCo (TSX: OIL.B) said'),
    item('gov-note-903', 'Fri, 27 Nov 2026 21:30:00 +0000', 'Government note', 'The Government said'))


def reads(state):
    path = state / N.READS
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def test_a_quiet_wire_read_whole_asks_for_no_list_and_claims_no_stretch_it_did_not_see(tmp_path):
    asked = []
    out = N.collect(dt.date(2026, 11, 27), root=tmp_path / 'wire', pause=0, now=SUNDAY,
                    state_dir=tmp_path, fetch=refusing_list({N.RSS_MAIN: QUIET_FEED, **QUIET_SITEMAP}, asked))
    sm = out['sitemap']
    assert sm['complete'] and sm['whole'] and sm['current_by'] == 'feed_agrees'
    assert out['reached_since'] is True and out['list_asked'] is False
    assert not any('/news-releases/' in u for u in asked)        # no list page, no release page
    # The sitemap's stretch ends with its last release's minute; the feed, old
    # by the clock, logs nothing; 14:01 → 16:20 is left for a later read.
    assert reads(tmp_path) == [{'kind': 'sitemap', 'from': '2026-11-26T18:01:00-05:00',
                                'to': '2026-11-29T14:01:00-05:00', 'by': 'feed_agrees'}]
    cov = N.coverage(dt.datetime(2026, 11, 27, 16, 0, tzinfo=ET), SUNDAY, state_dir=tmp_path)
    assert cov['gaps'] == [['2026-11-29T14:01:00-05:00', SUNDAY.isoformat()]]
    assert cov['unreadable_lines'] == 0


def test_a_quiet_wire_without_the_feed_is_still_read_only_in_part(tmp_path):
    out = N.collect(dt.date(2026, 11, 27), root=tmp_path / 'wire', pause=0, now=SUNDAY,
                    state_dir=tmp_path, fetch=refusing_list(QUIET_SITEMAP))      # every feed 404
    assert out['sitemap']['complete'] and out['sitemap']['current_by'] is None
    assert out['sitemap']['whole'] is False and out['reached_since'] is False and out['list_asked']
    assert reads(tmp_path) == []


def test_a_feed_with_another_last_release_vouches_only_when_it_is_current_and_overlaps(tmp_path):
    later = feed(item('late-905', 'Sun, 29 Nov 2026 21:10:00 +0000', 'Late release', 'Late (TSX: LTE) said'),
                 item('acme-update-901', 'Sun, 29 Nov 2026 19:00:00 +0000', 'ACME Mining update', 'x'))
    out = N.collect(dt.date(2026, 11, 27), root=tmp_path / 'wire', pause=0, now=SUNDAY,
                    state_dir=tmp_path, fetch=refusing_list({N.RSS_MAIN: later, **QUIET_SITEMAP}))
    assert out['sitemap']['current_by'] == 'feed_current' and out['reached_since'] is True
    # The two stretches together show the wire whole from the sitemap's oldest minute to now.
    cov = N.coverage(dt.datetime(2026, 11, 27, 16, 0, tzinfo=ET), SUNDAY, state_dir=tmp_path)
    assert cov['read'] and cov['gaps'] == []
    # A feed with another last release that the clock cannot vouch for proves nothing.
    stale = feed(item('late-905', 'Sun, 29 Nov 2026 20:00:00 +0000', 'Late release', 'x'),
                 item('acme-update-901', 'Sun, 29 Nov 2026 19:00:00 +0000', 'ACME Mining update', 'x'))
    out = N.collect(dt.date(2026, 11, 27), root=tmp_path / 'w2', pause=0, now=SUNDAY,
                    state_dir=tmp_path / 's2', fetch=refusing_list({N.RSS_MAIN: stale, **QUIET_SITEMAP}))
    assert out['sitemap']['current_by'] is None and out['list_asked'] is True
    # Nor does one that is current but starts after the sitemap's last release.
    gap = feed(item('late-905', 'Sun, 29 Nov 2026 21:10:00 +0000', 'Late release', 'x'),
               item('late-906', 'Sun, 29 Nov 2026 20:30:00 +0000', 'Later release', 'x'))
    out = N.collect(dt.date(2026, 11, 27), root=tmp_path / 'w3', pause=0, now=SUNDAY,
                    state_dir=tmp_path / 's3', fetch=refusing_list({N.RSS_MAIN: gap, **QUIET_SITEMAP}))
    assert out['sitemap']['current_by'] is None and out['reached_since'] is False


def test_a_one_release_sitemap_vouched_for_logs_no_empty_stretch(tmp_path):
    one = {'/sitemap-news.xml': QUIET_INDEX, '/sitemap-news.xml?page=1': sm_page(
        sm_entry('acme-update-901', '2026-11-29T14:00:00-05:00', 'ACME Mining update', 'Toronto:ACM'))}
    out = N.collect_sitemap(root=tmp_path / 'wire', fetch=refusing_list(one), now=SUNDAY, state_dir=tmp_path,
                            feed={'newest': '2026-11-29T14:00:00-05:00', 'from': '2026-11-27T16:31:00-05:00'})
    assert out['whole'] and out['current_by'] == 'feed_agrees' and 'read_logged' not in out
    assert reads(tmp_path) == []          # an empty interval would poison every later coverage read


def test_a_working_morning_is_still_shown_current_by_the_clock(tmp_path):
    out = N.collect_sitemap(root=tmp_path / 'wire', fetch=refusing_list(SITEMAP),
                            now=dt.datetime(2026, 11, 26, 8, 12, tzinfo=ET), state_dir=tmp_path,
                            feed={'newest': '2026-11-20T08:00:00-05:00', 'from': '2026-11-20T07:00:00-05:00'})
    assert out['current_by'] == 'clock'
    assert reads(tmp_path) == [{'kind': 'sitemap', 'from': '2026-11-24T12:01:00-05:00',
                                'to': '2026-11-26T08:12:00-05:00'}]


def test_main_names_a_complete_sitemap_that_was_not_shown_current(monkeypatch, capsys):
    out = {'reached_since': False, 'failed': 0, 'from_list': 0, 'page_failures': {}, 'list_pages': 0,
           'list_error': 'page 1: ValueError',
           'sitemap': {'answered': 1, 'pages': 1, 'page_errors': {}, 'complete': True,
                       'newest': '2026-11-29T14:00:00-05:00', 'whole': False},
           'rss': {'rss_answered': 0, 'rss_feeds': 13}}
    monkeypatch.setattr(N, 'collect', lambda *a, **k: out)
    assert N.main(['--collect', '--since', '2026-11-27']) == 6
    assert 'its newest release, 2026-11-29T14:00:00-05:00, was not shown current' in capsys.readouterr().err
