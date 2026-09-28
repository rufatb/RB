"""The wire archive: what a release row claims, and how a headline earns ISSUER_RELEASE."""
import datetime as dt
import json

import pytest

import newswire as N
from factor_news import classify_headline, prepare_headlines

ET = N.ET

LIST = '''
<div class="row newsCards" lang="en"><a class="newsreleaseconsolidatelink" href="/news-releases/acme-q3-1.html">
<h3 class="no-top-margin"><small>07:00 ET</small>
   ACME Mining reports record third quarter
</h3><p>teaser</p></a></div>
<div class="row newsCards" lang="en"><a class="newsreleaseconsolidatelink" href="/news-releases/gov-2.html">
<h3 class="no-top-margin"><small>Sep 25, 2026, 16:10 ET</small>
   Government announces funding
</h3><p>teaser</p></a></div>
'''


def release(date='2026-09-28T07:00:00-04:00', lead='ACME Mining Corp. (TSX: ACM) (NYSE: ACM) today reported'):
    return (f"<html><head><meta name='date' content=\"{date}\"/></head><body>"
            f"<h1>ACME Mining reports record third quarter</h1>"
            f'<section class="release-body container "><p>TORONTO, Sept. 28, 2026 /CNW/ - '
            f'{lead} ...</p><p>{"filler " * 200} Partner Co. (TSX: PTN) holds units.</p></section></body></html>')


def test_symbols_cover_the_forms_issuers_write():
    assert N.symbols('(TSX: TECK.A and TECK.B, NYSE: TECK)') == ['TECK-A.TO', 'TECK-B.TO']
    assert N.symbols('(TSX and NYSE: CNQ)') == ['CNQ.TO']
    assert N.symbols('(TSX/NYSE: SU)') == ['SU.TO']
    assert N.symbols('(TSX: REI.UN)') == ['REI-UN.TO']
    assert N.symbols('(TSXV: ABC)') == N.symbols('TSX Venture Exchange: ABC') == ['ABC.V']
    assert N.symbols('(NYSE: XYZ)') == []


def test_list_parsing_and_dates():
    cards = N.parse_list(LIST)
    assert [c[0] for c in cards] == ['https://www.newswire.ca/news-releases/acme-q3-1.html',
                                     'https://www.newswire.ca/news-releases/gov-2.html']
    assert cards[0][2] == 'ACME Mining reports record third quarter'
    today = dt.date(2026, 9, 28)
    assert N.listed_date(cards[0][1], today) == today
    assert N.listed_date(cards[1][1], today) == dt.date(2026, 9, 25)


def test_a_release_row_takes_symbols_from_the_lead_only():
    row = N.parse_release(release(), 'https://www.newswire.ca/news-releases/acme-q3-1.html')
    assert row['tickers'] == ['ACM.TO']          # PTN is deep in the body
    assert row['published_at'] == '2026-09-28T07:00:00-04:00'
    assert row['title'] == 'ACME Mining reports record third quarter'


def test_a_page_without_a_dated_body_is_refused():
    with pytest.raises(ValueError, match='NO_RELEASE_DATE'):
        N.parse_release('<section class="release-body">x</section>', 'u')
    with pytest.raises(ValueError, match='OFFSET'):
        N.parse_release(release(date='2026-09-28T07:00:00'), 'u')
    with pytest.raises(ValueError, match='NO_RELEASE_BODY'):
        N.parse_release("<meta name='date' content=\"2026-09-28T07:00:00-04:00\"/>", 'u')


def fake_fetch(pages):
    def fetch(url):
        if url in pages:
            v = pages[url]
            if isinstance(v, Exception):
                raise v
            return v
        return ''
    return fetch


def test_collect_archives_once_counts_failures_and_stops_at_since(tmp_path):
    pages = {N.LIST_URL.format(page=1): LIST,
             'https://www.newswire.ca/news-releases/acme-q3-1.html': release(),
             'https://www.newswire.ca/news-releases/gov-2.html': ValueError('HTTP_503')}
    out = N.collect(dt.date(2026, 9, 25), today=dt.date(2026, 9, 28), root=tmp_path,
                    fetch=fake_fetch(pages), pause=0)
    assert out['archived'] == 1 and out['failed'] == 1 and out['failures'] == {'HTTP_503': 1}
    assert out['reached_since'] is False           # the list ended without an older card
    assert json.loads((tmp_path/'2026-09-28.jsonl').read_text())['tickers'] == ['ACM.TO']
    # Stopping: a card older than `since` ends the walk; an archived URL is not refetched.
    out = N.collect(dt.date(2026, 9, 26), today=dt.date(2026, 9, 28), root=tmp_path,
                    fetch=fake_fetch(pages), pause=0)
    assert out['reached_since'] is True and out['new_releases'] == 0 and out['archived'] == 0


def archive(tmp_path, **kw):
    row = {'url': 'https://www.newswire.ca/news-releases/acme-q3-1.html',
           'title': 'ACME Mining reports record third quarter',
           'published_at': '2026-09-28T07:00:00-04:00', 'tickers': ['ACM.TO'],
           'source': 'newswire.ca', **kw}
    N.append([row], tmp_path)
    return row


def test_an_archived_release_is_an_issuer_release_with_the_wire_time(tmp_path):
    row = archive(tmp_path)
    meta = classify_headline(row['title'], row['url'] + '?utm_source=x', 'ACM.TO', tmp_path)
    assert meta['classification'] == 'ISSUER_RELEASE'
    assert meta['first_disclosed_at'] == row['published_at']
    assert meta['issuer_role'] == 'VERIFIED' and meta['primary_source_verified'] is True
    # Another name, or no name: the release is still a release, the issuer is not verified.
    assert classify_headline(row['title'], row['url'], 'XYZ.TO', tmp_path)['issuer_role'] == 'UNVERIFIED'


def test_a_staged_claim_cannot_make_a_release(tmp_path):
    """The class is recomputed from the archive: an unarchived URL, or an archived
    URL carrying a different title, is an ordinary headline."""
    row = archive(tmp_path)
    assert classify_headline(row['title'], 'https://example.com/acme', 'ACM.TO', tmp_path)[
        'classification'] == 'UNCLASSIFIED'
    fake = classify_headline('ACME to be acquired at 50% premium', row['url'], 'ACM.TO', tmp_path)
    assert fake['classification'] == 'UNCLASSIFIED' and fake['first_disclosed_at'] is None


def test_releases_rank_ahead_of_other_headlines(tmp_path):
    row = archive(tmp_path)
    items = [{'title': 'Top 3 dividend stocks to buy', 'source_url': 'https://a.com/1'},
             {'title': 'Miners slip', 'source_url': 'https://a.com/2'},
             {'title': row['title'], 'source_url': row['url']}]
    out, _ = prepare_headlines(items, 8, 'ACM.TO', tmp_path)
    assert [o['evidence_metadata']['classification'] for o in out] == [
        'ISSUER_RELEASE', 'UNCLASSIFIED', 'COMMENTARY']


def test_the_window_runs_from_the_prior_close_to_the_open():
    start, end = N.window(dt.date(2026, 9, 28))     # a Monday
    assert start == dt.datetime(2026, 9, 25, 16, 0, tzinfo=ET)
    assert end == dt.datetime(2026, 9, 28, 9, 30, tzinfo=ET)


def test_merge_puts_releases_first_and_keeps_the_cap(tmp_path):
    root = tmp_path/'wire'
    row = archive(root)
    state = tmp_path/'state'
    state.mkdir()
    staged = {'ACM.TO': {'status': 'READY', 'catalyst_tags': [],
                         'headlines': [{'title': f'h{i}', 'source_url': f'https://a.com/{i}',
                                        'published_at': '2026-09-28T06:00:00-04:00'} for i in range(8)]}}
    (state/'deepseek_news.json').write_text(json.dumps(staged))
    now = dt.datetime(2026, 9, 28, 8, 55, tzinfo=ET)
    assert N.merge_into_news(state, ['ACM.TO', 'OTHER.TO'], now, root) == ['ACM.TO']
    news = json.loads((state/'deepseek_news.json').read_text())
    assert news['ACM.TO']['headlines'][0]['source_url'] == row['url']
    assert len(news['ACM.TO']['headlines']) == 8 and 'OTHER.TO' not in news
    # A release after `now` is not staged.
    early = dt.datetime(2026, 9, 28, 6, 0, tzinfo=ET)
    assert N.headlines('ACM.TO', early, root) == []


def test_the_models_are_shown_the_class_and_the_wire_time(tmp_path, monkeypatch):
    """Through the real validator: staged news -> factor_inputs -> the row the
    desks read carries ISSUER_RELEASE, issuer_verified and first_disclosed."""
    import factor_inputs
    import deepseek_opportunities as O
    root = tmp_path/'wire'
    row = archive(root)
    monkeypatch.setattr(N, 'ARCHIVE', root)
    now = dt.datetime(2026, 9, 28, 8, 55, tzinfo=ET)
    ev = factor_inputs._evidence([{'title': row['title'], 'source_url': row['url'],
                                   'published_at': row['published_at']}],
                                 'headlines', factor_inputs._stamp(now), [],
                                 factor_inputs._stamp(now), 'ACM.TO')
    shown = O._headline(ev[0])
    assert shown['class'] == 'ISSUER_RELEASE' and shown['issuer_verified'] is True
    assert shown['first_disclosed'] == row['published_at']
