"""Offline regressions for observed headline/macro evidence defects."""
import copy
import datetime as dt
import json

import pytest

import factor_macro as M
import factor_news as N
import prepare_deepseek as P
from test_deepseek_rss_day100 import feed, item, mock_rss
from test_factor_inputs import NOW


def headline(title='Operating update', url='https://publisher.example/article'):
    return {'title': title, 'source_url': url, 'published_at': NOW.isoformat()}


def test_tracking_and_identical_titles_dedup_before_cap():
    rows = [headline(url='https://publisher.example/article?utm_source=first'),
            headline('Same URL with tracking', 'https://publisher.example/article?utm_source=second'),
            headline(' OPERATING — UPDATE! ', 'https://syndication.example/reprint')]
    rows += [headline('Unique update '+str(i), 'https://publisher.example/'+str(i)) for i in range(8)]
    result, reasons = N.prepare_headlines(rows, 8)
    assert len(result) == 8 and result[-1]['title'] == 'Unique update 6'
    assert reasons == {'DUPLICATE_CANONICAL_URL': 1, 'DUPLICATE_NORMALIZED_TITLE': 1, 'ITEM_LIMIT': 1}
    assert result[0]['source_url'].endswith('utm_source=first')  # original receipt preserved


def test_article_identity_query_is_not_removed_for_deduplication():
    result, reasons = N.prepare_headlines([
        headline('First', 'https://publisher.example/news?id=1&utm_medium=rss'),
        headline('Second', 'https://publisher.example/news?id=2&utm_medium=rss')], 8)
    assert len(result) == 2 and not reasons
    assert result[0]['evidence_metadata']['canonical_url'].endswith('?id=1')


def test_commentary_labels_do_not_manufacture_novelty_materiality_or_role():
    result, _ = N.prepare_headlines([
        headline('Top 2 Dividend Stocks to Buy and Hold for Decades'),
        headline('Enbridge announces five-year financing plan', 'https://enbridge.com/news/new'),
        headline('Third-party company receives CIBC credit line', 'https://other.example/news')], 8)
    assert result[-1]['title'].startswith('Top 2')
    assert result[-1]['evidence_metadata']['classification'] == 'COMMENTARY'
    assert result[0]['evidence_metadata']['classification'] == 'UNCLASSIFIED'
    assert result[0]['evidence_metadata']['impact_horizon'] == 'MULTI_YEAR_TITLE'
    for row in result:
        m = row['evidence_metadata']
        assert m['issuer_role'] == m['novelty'] == 'UNVERIFIED'
        assert m['first_disclosed_at'] is None and m['updated_at'] is None
        assert m['primary_source_verified'] is False  # domain alone is not a verified issuer mapping


def test_rss_duplicate_first_items_do_not_starve_later_independent_evidence(monkeypatch):
    duplicate = item(title='Old duplicated story', link='https://publisher.example/old')
    raw = feed([duplicate]*8+[item(title='New independently linked headline', link='https://publisher.example/new')])
    mock_rss(monkeypatch, raw)
    result = P._news('RY.TO', NOW)
    assert len(result['headlines']) == 2
    assert result['rejected_rows'] == {'DUPLICATE_CANONICAL_URL': 7}
    assert result['unusable_rows'] == 7
    assert result['headlines'][1]['title'] == 'New independently linked headline'


def epoch(value):
    return dt.datetime.fromisoformat(value).timestamp()


def chart():
    return {'meta': {'dataGranularity': '1d', 'exchangeTimezoneName': 'America/Toronto',
                     'chartPreviousClose': 50, 'previousClose': 800},
            'timestamp': [epoch('2026-09-10T09:30:00-04:00'), epoch('2026-09-11T09:30:00-04:00'),
                          epoch('2026-09-14T09:30:00-04:00')],
            'indicators': {'quote': [{'close': [100., 101., 102.]}]}}


SOURCE = 'https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPTSE?interval=1d&range=5d'
OBSERVED = dt.datetime.fromisoformat('2026-09-14T12:20:00-04:00')


def test_macro_change_uses_actual_previous_bar_not_range_start_metadata():
    result = M.daily_change_context(chart(), 103., OBSERVED, SOURCE)
    assert result['change_status'] == 'READY'
    assert result['change_pct'] == pytest.approx((103./101.-1)*100)
    assert result['reference'] == {
        'value': 101., 'bar_timestamp': '2026-09-11T13:30:00+00:00',
        'source_url': SOURCE, 'scope': 'previous_observed_daily_bar_close', 'interval': '1d'}
    assert result['change_scope'] == 'observed_level_vs_previous_daily_bar_close'
    assert 'close_time' not in json.dumps(result)


def test_preopen_cash_index_change_is_friday_vs_thursday_not_fake_monday_change():
    data = chart()
    data['timestamp'].pop()
    data['indicators']['quote'][0]['close'].pop()
    observed = dt.datetime.fromisoformat('2026-09-11T16:00:00-04:00')
    result = M.daily_change_context(data, 101., observed, SOURCE)
    assert result['change_pct'] == pytest.approx(1.)
    assert result['reference']['bar_timestamp'] == '2026-09-10T13:30:00+00:00'


def test_macro_change_nonfinite_arithmetic_does_not_escape_as_numeric_evidence():
    data = chart()
    data['indicators']['quote'][0]['close'][1] = 1e-308
    result = M.daily_change_context(data, 1e308, OBSERVED, SOURCE)
    assert result['change_status'] == 'UNAVAILABLE'
    assert result['change_gap'] == 'NONFINITE_MACRO_CHANGE'
    assert 'change_pct' not in result


@pytest.mark.parametrize('mutate', [
    lambda p: p['meta'].update(dataGranularity='1wk'),
    lambda p: p['meta'].pop('exchangeTimezoneName'),
    lambda p: p['meta'].update(exchangeTimezoneName='/private-secret'),
    lambda p: p.update(timestamp=[True, *p['timestamp'][1:]]),
    lambda p: p['timestamp'].__setitem__(1, p['timestamp'][0]),
    lambda p: p['timestamp'].__setitem__(1, p['timestamp'][0]+60),
    lambda p: p['timestamp'].__setitem__(2, epoch('2026-09-15T09:30:00-04:00')),
    lambda p: p['timestamp'].__setitem__(2, epoch('2026-09-14T13:30:00-04:00')),
    lambda p: p['indicators']['quote'][0]['close'].__setitem__(1, None),
    lambda p: p['indicators']['quote'][0]['close'].__setitem__(1, '101'),
    lambda p: p['indicators']['quote'][0]['close'].__setitem__(1, float('nan')),
    lambda p: p['indicators']['quote'][0]['close'].pop(),
])
def test_invalid_change_reference_stays_unavailable_without_unsafe_fallback(mutate):
    data = copy.deepcopy(chart()); mutate(data)
    result = M.daily_change_context(data, 103., OBSERVED, SOURCE)
    assert result['change_status'] == 'UNAVAILABLE'
    assert 'change_pct' not in result and result['reference'] is None
    assert result['change_gap'] and 'private-secret' not in json.dumps(result)


def test_macro_no_bar_data_keeps_level_as_healthy_but_reports_missing_change(monkeypatch):
    from types import SimpleNamespace
    from urllib.parse import unquote
    import requests
    def get(url, **kwargs):
        assert kwargs['params'] == {'interval': '1d', 'range': '5d'}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'chart': {'result': [
            {'meta': {'symbol': unquote(url.rsplit('/', 1)[-1]), 'regularMarketPrice': 12.5,
                      'regularMarketTime': epoch('2026-09-10T16:00:00-04:00')}}]}})
    monkeypatch.setattr(requests, 'get', get)
    cfg = {'correlated': {'crude': 'CL=F', 'cadusd': 'CADUSD=X', 'tsx': '^GSPTSE', 'vix': '^VIX'}}
    result = P._macro(cfg, NOW)
    assert all(value['value'] == 12.5 for value in result['values'].values())
    assert all(value['change_status'] == 'UNAVAILABLE' for value in result['values'].values())
    assert len(result['gaps']) == 4


def test_an_empty_placeholder_bar_on_today_is_not_a_duplicate():
    """2026-09-22: Yahoo's FX series served today twice — a 00:00 bar with a None
    close and the live bar — so cadusd read DUPLICATE_DAILY_REFERENCE_DATE and
    UNAVAILABLE every morning."""
    data = chart()
    data['timestamp'].insert(2, epoch('2026-09-14T00:05:00-04:00'))
    data['indicators']['quote'][0]['close'].insert(2, None)
    result = M.daily_change_context(data, 103., OBSERVED, SOURCE)
    assert result['change_status'] == 'READY'
    assert result['change_pct'] == pytest.approx((103./101.-1)*100)


def test_two_valued_bars_on_one_date_are_still_refused():
    data = chart()
    data['timestamp'].insert(2, epoch('2026-09-14T00:05:00-04:00'))
    data['indicators']['quote'][0]['close'].insert(2, 99.)
    result = M.daily_change_context(data, 103., OBSERVED, SOURCE)
    assert result['change_status'] == 'UNAVAILABLE'
