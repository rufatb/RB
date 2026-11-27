"""Replay the November 26 source, model, and delivery failure paths."""
import datetime as dt
import json

import pandas as pd
import pytest

import news_desk
import news_edition as edition
import newswire


NOW = dt.datetime(2026, 11, 26, 9, 36, tzinfo=edition.ET)
SESSION = NOW.date()
BODY = 'The issuer announced a material change to committed financing terms. ' * 10


def row(ticker, provider, time):
    return {'tickers': [ticker], 'published_at': f'2026-11-25T{time}:00-05:00',
            'title': f'{ticker} announces new transaction terms',
            'url': f'https://{provider}/news-releases/{ticker}-876543210.html'}


def archives(tmp_path):
    cnw, press = tmp_path/'cnw', tmp_path/'press'
    for path, entry in ((cnw, row('CU.TO', 'www.newswire.ca', '19:39')),
                        (press, row('MX.TO', 'www.globenewswire.com', '17:01'))):
        path.mkdir()
        (path/'2026-11-25.jsonl').write_text(json.dumps(entry) + '\n', encoding='utf-8')
    return cnw, press


def chart(ticker):
    dates = pd.date_range(end='2026-11-25', periods=23, freq='B')
    return {'instrumentType': 'EQUITY', 'currency': 'CAD'}, pd.DataFrame(
        {'Close': 40., 'Volume': 100_000}, index=dates)


def ask(batch, **kwargs):
    return {'calls': [{'id': item['id'], 'ticker': item['ticker'], 'side': 'SHORT' if item['ticker'] == 'CU.TO' else 'LONG',
                       'confidence': .65, 'material': True, 'reason': 'Financing terms changed.',
                       'evidence_quote': 'a material change to committed financing terms',
                       'invalidation': 'The new terms are withdrawn.'} for item in batch]}, news_desk.MODEL


def stage(tmp_path, paths, **kwargs):
    return edition.stage(tmp_path, now=NOW, clock=lambda: NOW, archive=paths[0], press_archive=paths[1],
                         **{'chart': chart, 'fetch_body': lambda *a, **k: (BODY, 'Verified publisher'),
                            'ask': ask, **kwargs})


def complete_wire(tmp_path):
    start, end = newswire.window(SESSION)
    newswire.log_read('sitemap', start, end + dt.timedelta(minutes=1), state_dir=tmp_path)


def complete_press(tmp_path):
    result = edition.capture_press(
        tmp_path, NOW, twins={'MX.TO': {'us': 'MEOH', 'name': 'Methanex Corporation'}},
        get=lambda *a, **k: [{'publishedDate': '2026-11-25 15:00:00',
                             'url': 'https://www.globenewswire.com/news-releases/old.html', 'text': BODY}],
    )
    assert result['complete']


def test_replay_combines_methanex_and_canadian_utilities_without_rewriting_research(tmp_path):
    paths = archives(tmp_path)
    complete_wire(tmp_path)
    complete_press(tmp_path)
    result = stage(tmp_path, paths)
    assert result['status'] == 'READY'
    assert {r['ticker'] for r in result['featured']} == {'MX.TO', 'CU.TO'}
    assert all(row['answered_at'] == NOW.isoformat() for row in result['featured'])
    assert news_desk.section(tmp_path, NOW)['edition_id'] == result['edition_id']
    assert stage(tmp_path, paths, ask=lambda *a, **k: pytest.fail('edition reran')) == result
    text = '\n'.join(edition.edition_lines(result))
    edition.verify_render(result, text)
    from email_render import html_from_text
    edition.verify_render(result, html_from_text(text))
    with pytest.raises(ValueError, match='RENDER_MISMATCH'):
        edition.verify_render(result, text.replace('MX.TO', ''))
    with pytest.raises(ValueError, match='RENDER_MISMATCH'):
        edition.verify_render(result, 'Elsewhere in the report: LONG MX.TO\n' + text.replace('LONG MX.TO', 'SHORT MX.TO'))


def test_price_outage_never_becomes_a_quiet_morning(tmp_path):
    paths = archives(tmp_path)
    complete_wire(tmp_path)
    def refused(_):
        raise TimeoutError()
    result = stage(tmp_path, paths, chart=refused)
    assert result['status'] == 'UNAVAILABLE'
    assert result['excluded']['liquidity unavailable'] == 2
    assert 'completed review found no' not in '\n'.join(edition.edition_lines(result))


def test_failed_body_and_incomplete_wire_are_visible_with_one_verified_call(tmp_path):
    paths = archives(tmp_path)
    def body(release, ticker, root, **kwargs):
        if ticker == 'CU.TO':
            raise ValueError('HTTP_403')
        return BODY, 'FMP matched body'
    result = stage(tmp_path, paths, fetch_body=body)
    assert result['status'] == 'PARTIAL'
    assert result['excluded']['issuer body unavailable'] == 1
    assert 'overnight wire coverage incomplete' in result['reason']
    assert [r['ticker'] for r in result['featured']] == ['MX.TO']


def test_a_missing_release_does_not_wipe_out_verified_evidence_for_that_issuer(tmp_path):
    cnw, press = archives(tmp_path)
    refused = row('CU.TO', 'www.newswire.ca', '20:40')
    refused.update(url='https://www.newswire.ca/news-releases/other-876543210.html',
                   title='Canadian Utilities reports updated regulatory terms')
    with (cnw / '2026-11-25.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(refused) + '\n')
    complete_wire(tmp_path)
    complete_press(tmp_path)

    def body(release, *args, **kwargs):
        if release['url'] == refused['url']:
            raise ValueError('HTTP_403')
        return BODY, 'Matched issuer release'

    result = stage(tmp_path, (cnw, press), fetch_body=body)
    assert result['status'] == 'PARTIAL'
    cu = next(call for call in result['featured'] if call['ticker'] == 'CU.TO')
    assert cu['url'] != refused['url'] and len(cu['release_urls']) == 1


def test_invalid_response_retries_only_the_failed_candidate(tmp_path):
    paths = archives(tmp_path)
    complete_wire(tmp_path)
    complete_press(tmp_path)
    seen = []
    def partial(batch, **kwargs):
        seen.append([item['ticker'] for item in batch])
        reply, model = ask(batch)
        if len(seen) == 1:
            reply['calls'][0]['ticker'] = 'WRONG.TO'
            reply['calls'][0]['material'] = 'true'
        return reply, model
    result = stage(tmp_path, paths, ask=partial)
    assert result['status'] == 'READY'
    assert seen == [['CU.TO', 'MX.TO'], ['CU.TO']]


def test_final_press_capture_retains_good_issuer_evidence_and_exposes_coverage_gap(tmp_path):
    complete_wire(tmp_path)
    cnw, press = tmp_path / 'cnw', tmp_path / 'press'
    twins = {'MX.TO': {'us': 'MEOH', 'name': 'Methanex Corp'},
             'GFL.TO': {'us': 'GFL', 'name': 'GFL Environmental'}}

    def get(*args, symbols, **kwargs):
        if symbols == 'GFL':
            raise TimeoutError()
        return [{'publishedDate': '2026-11-25T17:01:00-05:00', 'text': BODY,
                 'title': 'Methanex completes Trinidad transaction',
                 'url': 'https://www.globenewswire.com/news-releases/methanex.html'}]

    receipt = edition.capture_press(tmp_path, NOW, twins=twins, get=get)
    assert receipt['checked'] == 1
    assert receipt['failures'] == {'TimeoutError': 1}
    assert receipt['archived'] == 1
    result = stage(tmp_path, (cnw, press))
    assert result['status'] == 'PARTIAL'
    assert result['reason'] == 'FMP final press coverage incomplete'
    assert [pick['ticker'] for pick in result['featured']] == ['MX.TO']


def test_missing_final_press_check_blocks_quiet_morning(tmp_path):
    complete_wire(tmp_path)
    result = stage(tmp_path, (tmp_path / 'cnw', tmp_path / 'press'))
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'FMP final press coverage incomplete'


def test_late_addendum_is_single_edition_bound_to_the_original(tmp_path):
    paths = archives(tmp_path)
    original = stage(tmp_path, paths, fetch_body=lambda release, ticker, root, **k: (
        (BODY, 'Verified publisher') if ticker == 'MX.TO' else (_ for _ in ()).throw(ValueError('blocked'))
    ))
    late = NOW.replace(hour=11)
    result = edition.stage(tmp_path, now=late, clock=lambda: late, archive=paths[0], press_archive=paths[1],
                           chart=chart, ask=ask, fetch_body=lambda *a, **k: (BODY, 'Verified publisher'), late=True)
    assert result['status'] == 'LATE'
    assert result['parent_edition_id'] == original['edition_id']
    assert [r['ticker'] for r in result['featured']] == ['CU.TO']
    assert result['featured'][0]['answered_at'] == late.isoformat()
    assert news_desk.section(tmp_path, late)['edition_id'] == original['edition_id']


def test_stale_or_truncated_sitemap_cannot_certify_coverage(tmp_path):
    pages = [f'{newswire.SITEMAP_URL}?page={index}' for index in range(13)]
    def fetch(url):
        if url == newswire.SITEMAP_URL:
            return ''.join(f'<loc>{page}</loc>' for page in pages)
        return ('<url><loc>https://www.newswire.ca/news-releases/stale-876543210.html</loc>'
                '<news:title>Old release</news:title>'
                '<news:publication_date>2026-11-25T16:00:00-05:00</news:publication_date></url>')
    receipt = newswire.collect_sitemap(root=tmp_path, fetch=fetch, now=NOW, state_dir=tmp_path)
    assert receipt['pages_advertised'] == 13
    assert receipt['pages'] == 12
    assert receipt['whole'] is False
    assert not newswire.coverage(*newswire.window(SESSION), state_dir=tmp_path)['read']


def test_ambiguous_primary_delivery_requires_reconciliation(tmp_path, monkeypatch):
    import delivery_plan
    import gmail_delivery
    from report_store import Store

    record = stage(tmp_path, archives(tmp_path))
    Store(tmp_path).publish(SESSION.isoformat(), {'intraday': {'news_desk': record}})
    monkeypatch.setattr(gmail_delivery, 'prepare', lambda *a, **k: {
        'status': 'ALREADY_ATTEMPTED', 'delivery': {'state': 'unknown', 'message_id': 'existing'},
    })
    morning = delivery_plan.plan(tmp_path, now=NOW.replace(minute=48))
    assert morning['mode'] == 'RECONCILE'
    assert 'html_path' not in morning
