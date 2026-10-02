"""Day-122 Test 3 — the biotech catalyst finder: nothing the model writes is trusted."""
import datetime as dt
import json

import biotech_finder as F
import biotech_review as R

ET = F.ET
NOW = dt.datetime(2026, 10, 2, 16, 30, tzinfo=ET)
LEAD = {'ticker': 'ABCD', 'link': 'https://finance.yahoo.com/a.html',
        'published': dt.datetime(2026, 9, 30, 8, 0, tzinfo=ET)}


def ev(quote, kind='topline', start='2026-10-01', end='2026-12-31'):
    return {'asset': 'AB-101', 'indication': 'x', 'stage': 'Phase 2', 'kind': kind,
            'window_start': start, 'window_end': end, 'date_basis': 'issuer_guidance',
            'source_quote': quote, 'new_information': 'n', 'known_data': 'k', 'read_throughs': 'r'}


def test_candidate_refuses_what_it_cannot_check():
    ok, why = F.candidate(ev('Topline data from the AB-101 trial are expected in the fourth quarter of 2026.'), LEAD)
    assert why is None and ok['event_id'] == 'ABCD-AB101-topline-2026-12-31'
    assert ok['source_type'] == 'issuer' and ok['announced_at'].startswith('2026-09-30')
    assert F.candidate(ev('Topline data from the AB-101 trial are expected soon.'), LEAD)[1] == \
        'quote states no timing'
    assert F.candidate(ev('First patient dosing is expected in the fourth quarter of 2026.'), LEAD)[1] == \
        'quote does not name the event its kind claims'
    two = ('with first patient dosing anticipated in the fourth quarter of 2026 and initial '
           'clinical data expected in the first half of 2027')
    assert F.candidate(ev(two, kind='interim'), LEAD)[1] == 'quote states more than one timing'
    assert F.candidate(ev('Topline data in Q4 2026.', kind='CRL'), LEAD)[1] == \
        'kind not one this finder adds'


RSS = """<rss><channel>
<item><title>ABCD Reports Second Quarter 2026 Financial Results</title>
<link>https://finance.yahoo.com/a.html</link><pubDate>Wed, 30 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>Why ABCD stock is a buy (analysis)</title>
<link>https://finance.yahoo.com/b.html</link><pubDate>Wed, 30 Sep 2026 13:00:00 GMT</pubDate></item>
<item><title>ABCD announces topline results timing</title>
<link>https://finance.yahoo.com/c.html</link><pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""
PAGE_A = ('<html><p>BOSTON, Sept. 30, 2026 (GLOBE NEWSWIRE) -- ABCD today reported results.</p>'
          '<p>Topline data from the AB-101 trial are expected in the fourth quarter of 2026.</p></html>')
PAGE_C = '<html><p>An article about ABCD by a columnist. Data in Q4 2026.</p></html>'


class Client:
    def __init__(self, events):
        self.events, self.calls = events, 0
        self.chat = self.completions = self

    def create(self, **kw):
        self.calls += 1
        assert kw['messages'][0]['content'] == F.SYSTEM_PROMPT
        content = json.dumps({'events': self.events})

        class Resp:
            choices = [type('C', (), {'finish_reason': 'stop',
                                      'message': type('M', (), {'content': content})})]
        return Resp


def fetcher(pages):
    def fetch(url):
        if 'rss' in url or 'headline' in url:
            return RSS
        return pages[url]
    return fetch


def test_only_wire_releases_are_read_and_every_merge_is_quote_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'EVENTS', tmp_path / 'events.json')
    good = ev('Topline data from the AB-101 trial are expected in the fourth quarter of 2026.')
    invented = ev('Topline data from AB-202 are expected in the fourth quarter of 2026.')
    invented['asset'] = 'AB-202'
    client = Client([good, invented])
    pages = {'https://finance.yahoo.com/a.html': PAGE_A, 'https://finance.yahoo.com/c.html': PAGE_C}
    out = F.run(now=NOW, fetch=fetcher(pages), client=client, tickers=['ABCD'])
    assert out['leads'] == 2                               # the "why it is a buy" item is no lead
    assert out['releases read'] == 1 and out['not an issuer release (no wire dateline)'] == 1
    assert client.calls == 1
    assert out['accepted'] == ['ABCD-AB101-topline-2026-12-31']
    assert out['rejected'] == {'source_quote is not on the source page': 1}
    stored = json.loads((tmp_path / 'events.json').read_text())['events']
    assert [e['event_id'] for e in stored] == ['ABCD-AB101-topline-2026-12-31']
    assert stored[0]['review_status'] == 'verified' and stored[0]['finder'] == F.PROMPT_VERSION


def test_dry_run_merges_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(R, 'EVENTS', tmp_path / 'events.json')
    client = Client([ev('Topline data from the AB-101 trial are expected in the fourth quarter of 2026.')])
    out = F.run(now=NOW, fetch=fetcher({'https://finance.yahoo.com/a.html': PAGE_A,
                                        'https://finance.yahoo.com/c.html': PAGE_C}),
                client=client, tickers=['ABCD'], dry_run=True)
    assert out['accepted'] == ['ABCD-AB101-topline-2026-12-31']
    assert not (tmp_path / 'events.json').exists()


def test_visible_keeps_case_for_quoting():
    assert F.visible('<p>Topline&nbsp;Data</p><script>x()</script>') == 'Topline Data'
