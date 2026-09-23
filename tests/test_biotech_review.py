"""Part 2 events are merged only when the reviewer's quote is on the source page."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest

import biotech_review as R

NOW = dt.datetime(2026, 9, 23, 17, 0, tzinfo=ZoneInfo('America/New_York'))
URL = 'https://issuer.example/releases/q2'
QUOTE = 'Topline data from TRIAL-1 are expected in the fourth quarter of 2026.'
PAGE = ('<html><head><script>var x="Topline data from FAKE";</script></head><body>'
        '<p>Topline data from TRIAL&#8209;1 are expected in the '
        'fourth\n  quarter of 2026.</p></body></html>').replace('&#8209;', '-')


def event(**over):
    return {'event_id': 'ABC-TRIAL1-TOPLINE-2026Q4', 'ticker': 'ABC', 'kind': 'topline',
            'status': 'scheduled', 'window_start': '2026-10-01', 'window_end': '2026-12-31',
            'date_basis': 'issuer_guidance', 'source_type': 'issuer', 'source_url': URL,
            'source_quote': QUOTE, 'announced_at': '2026-08-12T16:05:00-04:00',
            'asset': 'ABC-1', 'indication': 'Indication', 'stage': 'Phase 2',
            'new_information': 'Topline expected Q4 2026.', 'known_data': 'None reported.',
            'read_throughs': 'None asserted.', **over}


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / 'biotech_events.json'
    monkeypatch.setattr(R, 'EVENTS', path)
    return path


def fetch_page(page=PAGE):
    return lambda url: page


def test_quote_matches_visible_text_across_whitespace_and_markup():
    assert R.quote_on_page(QUOTE, URL, fetch_page())
    # Text inside a <script> is not what a reader sees and never matches.
    assert not R.quote_on_page('var x="Topline data from FAKE";', URL, fetch_page())


def test_short_or_missing_quote_is_refused_not_matched():
    for quote in (None, '', 'Q4 2026'):
        with pytest.raises(ValueError):
            R.quote_on_page(quote, URL, fetch_page())


def test_add_refuses_an_event_whose_quote_is_not_on_its_source(store):
    invented = event(source_quote='Topline data from TRIAL-1 are expected in the third quarter of 2026.')
    out = R.add([invented], now=NOW, fetch=fetch_page())
    assert out['accepted'] == [] and out['stored'] == 0
    assert 'not on the source page' in out['rejected'][0]['reason']


def test_add_runs_the_registered_validator_after_the_quote(store):
    secondary = event(source_type='analyst')
    out = R.add([secondary], now=NOW, fetch=fetch_page())
    assert out['accepted'] == [] and 'primary-source' in out['rejected'][0]['reason']


def test_add_merges_by_event_id_and_stamps_review(store):
    R.add([event()], now=NOW, fetch=fetch_page())
    out = R.add([event(stage='Phase 2b')], now=NOW, fetch=fetch_page())
    stored = json.loads(store.read_text())['events']
    assert out['stored'] == 1 and stored[0]['stage'] == 'Phase 2b'
    assert stored[0]['review_status'] == 'verified'
    assert stored[0]['verified_at'] == NOW.isoformat()


def test_reverify_drops_a_vanished_quote_and_refreshes_the_rest(store):
    R.add([event(), event(event_id='ABC-OTHER', source_url='https://issuer.example/other')],
          now=NOW, fetch=lambda url: PAGE)
    later = NOW + dt.timedelta(days=6)
    pages = {URL: PAGE, 'https://issuer.example/other': '<p>Release withdrawn.</p>'}
    out = R.reverify(now=later, fetch=pages.__getitem__)
    stored = json.loads(store.read_text())['events']
    assert out['kept'] == 1 and out['dropped'][0]['event_id'] == 'ABC-OTHER'
    assert stored[0]['verified_at'] == later.isoformat()


def test_reverify_drops_a_passed_window(store):
    R.add([event(window_start='2026-09-24', window_end='2026-09-30')], now=NOW, fetch=fetch_page())
    out = R.reverify(now=dt.datetime(2026, 10, 1, 17, tzinfo=NOW.tzinfo), fetch=fetch_page())
    assert out['kept'] == 0 and 'window' in out['dropped'][0]['reason']
