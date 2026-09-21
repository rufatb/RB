"""Ticker RSS identity, safe XML and timestamp contracts; entirely offline."""
import datetime as dt
import hashlib
from html import escape
import json
from types import SimpleNamespace

import pytest

import prepare_deepseek as S
from test_factor_inputs import NOW


def item(title='Issuer operating update', link='https://issuer.example/news',
         published='Thu, 10 Sep 2026 15:00:00 GMT'):
    return ('<item><title>'+escape(title)+'</title><link>'+escape(link)+
            '</link><pubDate>'+escape(published)+'</pubDate></item>')


def feed(items=None, ticker='RY.TO', title=None, channel_link=None):
    title = title or 'Yahoo! Finance: '+ticker+' News'
    channel_link = channel_link or 'http://finance.yahoo.com/q/h?s='+ticker
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>'+escape(title)+
            '</title><link>'+escape(channel_link)+'</link><description>Latest Financial News for '+ticker+
            '</description>'+(''.join(items) if items is not None else item())+'</channel></rss>').encode()


def mock_rss(monkeypatch, raw):
    import requests
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None, content=raw)
    monkeypatch.setattr(requests, 'get', get)
    return calls


def test_tsx_news_uses_identity_checked_rss_and_keeps_receipt_metadata(monkeypatch):
    raw = feed()
    calls = mock_rss(monkeypatch, raw)
    monkeypatch.setattr(S, '_search_news', lambda *a, **k: pytest.fail('no second Yahoo request'))
    result = S._news('RY.TO', NOW)
    assert result['status'] == 'READY' and len(result['headlines']) == 1
    assert calls[0][0] == 'https://feeds.finance.yahoo.com/rss/2.0/headline'
    assert calls[0][1]['params'] == {'s': 'RY.TO', 'region': 'CA', 'lang': 'en-CA'}
    assert calls[0][1]['timeout'] == S.P.PUBLIC_REQUEST_TIMEOUT
    assert result['response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert result['channel_title'] == 'Yahoo! Finance: RY.TO News'
    assert result['source_identity'] == 'provider exact-ticker RSS channel'
    assert result['headlines'][0]['source_url'] == 'https://issuer.example/news'


@pytest.mark.parametrize('raw', [
    feed(ticker='TD.TO'),
    feed(title='Yahoo! Finance: General Market News'),
    feed(channel_link='http://finance.yahoo.com/q/h?s=TD.TO'),
    feed(channel_link='http://finance.yahoo.com/q/h?s=RY.TO&s=TD.TO'),
    feed(channel_link='http://finance.yahoo.com.evil.test/q/h?s=RY.TO'),
    feed(channel_link='http://user:password@finance.yahoo.com/q/h?s=RY.TO'),
    b'<rss><channel>',
    b'<!DOCTYPE rss [<!ENTITY a "expansion">]><rss/>',
    b'<!ENTITY a SYSTEM "file:///private"><rss/>',
])
def test_wrong_identity_or_malformed_xml_never_creates_headlines(monkeypatch, raw):
    mock_rss(monkeypatch, raw)
    result = S._news('RY.TO', NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert result['errorcode'] == 'INVALID_PUBLIC_DATA'
    assert not result.get('headlines')
    assert 'password' not in json.dumps(result) and 'file:///' not in json.dumps(result)


def test_bad_items_are_counted_without_erasing_healthy_items(monkeypatch):
    raw = feed([item(), item(published=''), item(published='Thu, 10 Sep 2026 15:00:00'),
                item(published='Wed, 02 Sep 2026 15:00:00 GMT'),
                item(published='Fri, 11 Sep 2026 20:00:00 GMT'),
                item(link='http://issuer.example/news'), item(title='')])
    mock_rss(monkeypatch, raw)
    result = S._news('RY.TO', NOW)
    assert result['status'] == 'READY' and len(result['headlines']) == 1
    assert result['unusable_rows'] == 6
    assert result['rejected_rows'] == {'INVALID_OR_OUT_OF_WINDOW_ITEM': 6}


def test_empty_but_valid_ticker_feed_remains_no_evidence_not_fabricated_no_edge(monkeypatch):
    mock_rss(monkeypatch, feed([]))
    result = S._news('RY.TO', NOW)
    assert result['status'] == 'NO_CURRENT_NEWS' and result['headlines'] == []
    assert 'directional_lean' not in result


def test_item_cap_and_body_size_are_bounded(monkeypatch):
    mock_rss(monkeypatch, feed([item(title='Issuer update '+str(i),
                                    link='https://issuer.example/news/'+str(i)) for i in range(10)]))
    result = S._news('RY.TO', NOW)
    assert len(result['headlines']) == S.P.MAX_NEWS_PER_CANDIDATE
    assert result['unusable_rows'] == 2
    monkeypatch.setattr(S.P, 'MAX_PUBLIC_NEWS_BYTES', 32)
    assert S._news('RY.TO', NOW)['errorcode'] == 'INVALID_PUBLIC_DATA'


def test_receipt_clock_can_accept_item_published_during_request(monkeypatch):
    mock_rss(monkeypatch, feed([item(published='Fri, 11 Sep 2026 12:30:01 GMT')]))
    result = S._news('RY.TO', NOW, clock=lambda: NOW+dt.timedelta(seconds=5))
    assert len(result['headlines']) == 1
    assert S.stamp(result['retrieved_at']) == NOW+dt.timedelta(seconds=5)


# ── the refusal must name which check refused ────────────────────────────────
# 2026-09-21: eleven names reported "headline acquisition failed:
# INVALID_PUBLIC_DATA" and nothing else. The raise sites had already said
# RSS_CHANNEL_IDENTITY_MISMATCH, RSS_SIZE_LIMIT, INVALID_RSS_XML,
# UNTIMED_RSS_ITEM — and `details` overwrote all of them with the exception
# CLASS name, the word "ValueError". A wrong feed and an oversize feed need
# completely different responses.

def test_our_own_reason_survives_into_the_report():
    out = S._public_failure(ValueError('RSS_CHANNEL_IDENTITY_MISMATCH'))
    assert out['errorcode'] == 'INVALID_PUBLIC_DATA'
    assert out['details'] == 'RSS_CHANNEL_IDENTITY_MISMATCH'


def test_an_untrusted_exception_message_is_never_stored():
    """A provider exception can carry a response body, a URL or a query string
    with a credential in it. None of that may reach a stored report, so
    anything that is not one of our own SHOUTING_CODES falls back to the class
    name."""
    leaky = ValueError('failed for https://provider.example/v1?apikey=sk-secret')
    out = S._public_failure(leaky)
    assert out['details'] == 'ValueError'
    assert 'sk-secret' not in repr(out) and 'provider.example' not in repr(out)


def test_a_lowercase_or_punctuated_message_is_not_mistaken_for_a_code():
    assert S._public_failure(ValueError('some prose')) ['details'] == 'ValueError'
    assert S._public_failure(ValueError('A.B.C')) ['details'] == 'ValueError'


def test_the_gap_line_carries_the_detail_not_just_the_code():
    import inspect
    src = inspect.getsource(S)
    assert "'headline acquisition failed: '+code\n" not in src, 'the bare code is back'
    assert "fresh.get('details')" in src
