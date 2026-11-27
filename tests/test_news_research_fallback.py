"""Day-156e (owner, 2026-11-27: "Fix now give me the news desk picks").

An edition that is not READY verified fewer calls than the desk made: on 11-27 it read
UNAVAILABLE (newswire.ca refused every release text) while the registered research arm
had made five calls by 09:32. The desk's own calls are frozen beside the edition and
print after its receipt line, outside what `verify_render` checks.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import news_desk
import news_edition
import report_page

ET = ZoneInfo('America/New_York')
NOW = dt.datetime(2026, 11, 27, 9, 46, 12, tzinfo=ET)
JWEL = 'Jamieson Wellness Inc. Announces Closing of Acquisition by Kirin Holdings Company, Limited'


def call(ticker, side='LONG', conf='0.60', material='True', title='A release', at='07:00'):
    return {'session': '2026-11-27', 'ticker': ticker, 'arm': 'full', 'side': side,
            'confidence': conf, 'material': material, 'reason': f'{ticker} reason.',
            'releases': '1', 'first_at': f'2026-11-27T{at}:00-05:00', 'title': title,
            'url': f'https://www.newswire.ca/news-releases/{ticker.lower()}.html'}


CALLS = [call('JWEL.TO', title=JWEL, at='09:27'),
         call('OGC.TO', title='OceanaGold Announces Ausgold Shareholder Approval'),
         call('CAE.TO', conf='0.55', material='False', title='CAE announces a consent solicitation')]


def edition(status='UNAVAILABLE', featured=()):
    record = news_edition.unavailable(dt.datetime(2026, 11, 27, 9, 31, 49, tzinfo=ET),
                                      'issuer body unavailable')
    record.update(status=status, featured=list(featured), coverage={'read': True, 'gaps': []},
                  candidates=9)
    return record


def state(tmp_path, record=None, calls=CALLS):
    if record is not None:
        path = news_edition.edition_path(tmp_path, '2026-11-27')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record))
    if calls is not None:
        (tmp_path / news_desk.STAGED).write_text(json.dumps(
            {'session': '2026-11-27', 'events': len(calls), 'calls': calls,
             'bodies_failed': {'ValueError': len(calls)}, 'excluded': {}, 'problems': {}}))
    return tmp_path


def test_an_unavailable_edition_carries_the_desks_own_calls(tmp_path):
    sec = news_desk.section(state(tmp_path, edition()), NOW, path=tmp_path / 'ledger.csv')
    assert sec['status'] == 'UNAVAILABLE' and sec['edition_version']
    assert [c['ticker'] for c in sec['research']['calls']] == ['JWEL.TO', 'OGC.TO', 'CAE.TO']
    assert sec['research']['version'] == news_desk.RESEARCH


def test_a_ready_edition_carries_none_and_a_verified_name_is_not_repeated(tmp_path):
    ready = news_desk.section(state(tmp_path, edition('READY')), NOW, path=tmp_path / 'ledger.csv')
    assert 'research' not in ready
    partial = edition('PARTIAL', featured=[{'ticker': 'OGC.TO', 'side': 'LONG'}])
    sec = news_desk.with_research(partial, state(tmp_path), NOW, path=tmp_path / 'ledger.csv')
    assert [c['ticker'] for c in sec['research']['calls']] == ['JWEL.TO', 'CAE.TO']


def test_an_edition_that_did_not_seal_still_carries_them(tmp_path, monkeypatch):
    monkeypatch.setenv('RB_NEWS_EDITION_REQUIRED', '1')
    sec = news_desk.section(state(tmp_path), NOW, path=tmp_path / 'ledger.csv')
    assert sec['status'] == 'UNAVAILABLE' and len(sec['research']['calls']) == 3


def test_the_calls_print_after_the_receipt_and_the_delivery_check_still_passes(tmp_path):
    sec = news_desk.section(state(tmp_path, edition()), NOW, path=tmp_path / 'ledger.csv')
    lines = news_desk.lines(sec, concise=True)
    receipt = next(i for i, line in enumerate(lines) if line.startswith('News Desk receipt'))
    table = next(i for i, line in enumerate(lines) if line.startswith('| # | Call'))
    assert receipt < table
    news_edition.verify_render(sec, '\n'.join(lines))          # raises on a mismatch
    rows = [line for line in lines if line.startswith('| 1 ') or line.startswith('| 2 ')]
    assert 'OGC.TO' in rows[0] and 'JWEL.TO' in rows[1]       # a closed takeover never leads
    assert any(line.startswith('⚠ LONG JWEL.TO is no trade') for line in lines)
    assert any('CAE.TO' in line and line.startswith('Routine releases') for line in lines)


def test_a_publication_from_before_renders_as_it_did():
    record = edition()
    assert news_desk.lines(record, concise=True) == news_edition.edition_lines(record)


def test_an_unreadable_desk_is_named_not_silent(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError('disk')
    monkeypatch.setattr(news_desk, 'research_section', broken)
    sec = news_desk.with_research(edition(), tmp_path, NOW)
    assert sec['research']['error'] == 'OSError'
    assert "could not be read today (OSError)" in '\n'.join(news_desk.lines(sec, concise=True))


def test_a_closed_takeover_is_told_apart_from_the_buyers_release():
    assert news_desk.deal_closed(JWEL)
    assert news_desk.deal_closed('Completion of the Previously Announced Arrangement by ABC Holdings')
    assert not news_desk.deal_closed('Acme Announces Closing of Acquisition of Widgets Inc.')
    assert not news_desk.deal_closed('Acme Completes Acquisition of Widgets, Financed by a New Facility')
    assert not news_desk.deal_closed('OceanaGold Announces Ausgold Shareholder Approval')


def test_the_page_renders_bold_and_links_and_escapes_the_rest():
    out = report_page._inline('**UNAVAILABLE** · see [the release](https://www.newswire.ca/x.html) <b>')
    assert out.startswith('<strong>UNAVAILABLE</strong>')
    assert '<a href="https://www.newswire.ca/x.html"' in out and '&lt;b&gt;' in out
    assert '**' not in out
