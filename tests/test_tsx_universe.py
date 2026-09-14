"""Eligibility, exact daily session data, sealed snapshots and failure isolation."""
import copy
import datetime as dt
import hashlib
import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest

import prepare_tsx_universe as P
import tsx_universe as U
from build_biotech import write_atomic
from diagnostic_context import create_context

NOW = dt.datetime(2026, 9, 14, 8, 5, tzinfo=U.ET)


def row(ticker='AAA.TO', issuer='ISSUER_A'):
    return {'ticker': ticker, 'issuer_id': issuer, 'sector': 'Industrials',
        'industry': 'Transportation', 'security_type': 'COMMON_STOCK',
        'source_url': 'https://www.tsx.com/en/resource/571',
        'metadata_as_of': '2026-07-31', 'retrieved_at': NOW.isoformat(),
        'listing_verified_at': NOW.isoformat(), 'exchange': 'TSX', 'currency': 'CAD',
        'active': True, 'evidence': {'security_type': 'https://issuer.example/common-shares',
          'industry': 'https://issuer.example/business',
          'listing': 'https://www.tsx.com/json/company-directory/search/tsx/A'}}


def receipt(ticker='AAA.TO', value=12_000_000, now=NOW):
    dates = U.previous_sessions(now)
    times = [int(dt.datetime.combine(d, dt.time(9, 30), U.ET).timestamp()) for d in dates]
    return {'source_url': f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
        'retrieved_at': now.isoformat(), 'response': {
            'meta': {'symbol': ticker, 'currency': 'CAD', 'exchangeName': 'TOR',
                     'instrumentType': 'EQUITY', 'dataGranularity': '1d'},
            'timestamp': times, 'indicators': {'quote': [{'open': [10]*20, 'high': [11]*20,
                'low': [9]*20, 'close': [10]*20, 'volume': [value/10]*20}]}}}


def acquire(tasks):
    out = {}
    for k, (fn, timeout) in tasks.items():
        try:
            out[k] = {'status': 'OK', 'value': fn()}
        except Exception as exc:
            out[k] = {'status': 'UNAVAILABLE', 'error': type(exc).__name__}
    return out


def master(directory, rows):
    path = directory/'tsx_security_master.json'
    write_atomic(path, {'schema_version': 1, 'reviewed': True, 'candidates': rows})
    return path


def test_measured_median_and_completed_session_boundary():
    r = receipt()
    result = U.liquidity(r, 'AAA.TO', NOW)
    assert result['median_dollar_volume_20'] == 12_000_000
    assert result['liquidity_last_session'] == '2026-09-11'
    # Current incomplete bar is not allowed to change the completed-day median.
    r['response']['timestamp'].append(int(NOW.replace(hour=9, minute=30).timestamp()))
    for field, values in r['response']['indicators']['quote'][0].items():
        values.append(1e12)
    assert U.liquidity(r, 'AAA.TO', NOW)['median_dollar_volume_20'] == 12_000_000


@pytest.mark.parametrize('field,value', [('currency', 'USD'), ('exchangeName', 'PNK'),
    ('instrumentType', 'ETF'), ('symbol', 'BBB.TO'), ('dataGranularity', '1wk')])
def test_daily_identity_is_not_inferred(field, value):
    r = receipt(); r['response']['meta'][field] = value
    with pytest.raises(ValueError, match='IDENTITY_OR_INTERVAL'):
        U.liquidity(r, 'AAA.TO', NOW)


@pytest.mark.parametrize('mutation,reason', [
    ('missing_prior', 'GRID_INCOMPLETE'), ('duplicate', 'DUPLICATE'),
    ('wrong_hour', 'NOT_TSX_OPEN'), ('zero_volume', 'NONPOSITIVE'),
    ('bad_ohlc', 'INCONSISTENT'), ('low_liquidity', 'LIQUIDITY_FLOOR')])
def test_daily_data_failures(mutation, reason):
    r = receipt(); data = r['response']; q = data['indicators']['quote'][0]
    if mutation == 'missing_prior':
        data['timestamp'].pop()
        for value in q.values(): value.pop()
    if mutation == 'duplicate': data['timestamp'][-1] = data['timestamp'][-2]
    if mutation == 'wrong_hour': data['timestamp'][-1] += 3600
    if mutation == 'zero_volume': q['volume'][-1] = 0
    if mutation == 'bad_ohlc': q['high'][0] = 1
    if mutation == 'low_liquidity': q['volume'] = [100]*20
    with pytest.raises(ValueError, match=reason): U.liquidity(r, 'AAA.TO', NOW)


@pytest.mark.parametrize('field,value,reason', [
    ('industry', '', 'FIELDS_MISSING'), ('currency', 'USD', 'TSX_CAD'),
    ('security_type', 'EQUITY', 'SECURITY_TYPE'), ('active', False, 'TSX_CAD'),
    ('metadata_as_of', '2026-01-01', 'STALE'), ('ticker', 'AAA.V', 'EXACT_TSX'),
    ('listing_verified_at', '2026-09-10T08:00:00-04:00', 'NOT_CURRENT')])
def test_security_master_required_facts(field, value, reason):
    r = row(); r[field] = value
    with pytest.raises(ValueError, match=reason): U.validate_master_row(r, NOW)


def test_share_class_dedup_is_by_issuer_liquidity_not_sector_quota():
    a = {**row(), 'median_dollar_volume_20': 12e6}
    b = {**row('AAA-B.TO'), 'median_dollar_volume_20': 15e6}
    c = {**row('CCC.TO', 'ISSUER_C'), 'median_dollar_volume_20': 15e6}
    ranked, excluded = U.rank([a, c, b])
    assert [r['ticker'] for r in ranked] == ['AAA-B.TO', 'CCC.TO']
    assert excluded == [{'ticker': 'AAA.TO', 'reason': 'DUPLICATE_ISSUER_SHARE_CLASS'}]


def test_sealed_roundtrip_reuses_attempt_and_retains_rejected_rows(tmp_path):
    bad = row('BAD.TO', 'ISSUER_BAD'); bad['industry'] = ''
    master(tmp_path, [row(), bad])
    calls = []
    def fetch(ticker, now):
        calls.append(ticker); return receipt(ticker)
    out = P.prepare(tmp_path, now=NOW, fetcher=fetch, acquire_fn=acquire)
    assert out['status'] == 'PARTIAL'
    assert out['target'] == 150 and out['mode'] == U.MODE
    assert [r['ticker'] for r in out['candidates']] == ['AAA.TO']
    assert any(r['ticker'] == 'BAD.TO' for r in out['exclusions'])
    assert out['source_coverage']['complete_market_rank'] is False
    assert P.prepare(tmp_path, now=NOW, fetcher=fetch, acquire_fn=acquire) == out
    assert calls == ['AAA.TO']
    path = tmp_path/out['candidates'][0]['daily_receipt_file']
    path.write_text('{}')
    assert U.load_prepared(tmp_path, NOW)['reason'] == 'UNIVERSE_RECEIPT_HASH_MISMATCH'


def test_duplicate_ticker_conflict_excludes_both_without_request(tmp_path):
    a = row(); b = {**a, 'industry': 'A different industry'}
    master(tmp_path, [a, b])
    out = P.prepare(tmp_path, now=NOW, fetcher=lambda *a: pytest.fail('ambiguous ticker fetched'), acquire_fn=acquire)
    assert out['candidates'] == []
    assert len(out['exclusions']) == 2


def test_whole_wave_failure_stops_and_records_remaining(tmp_path):
    rows = [row(f'A{i}.TO', f'I{i}') for i in range(12)]
    master(tmp_path, rows); calls = []
    def fetch(ticker, now):
        calls.append(ticker); raise TimeoutError()
    out = P.prepare(tmp_path, now=NOW, fetcher=fetch, acquire_fn=acquire)
    assert len(calls) == 8 and out['status'] == 'UNAVAILABLE'
    assert out['source_coverage']['daily_attempted'] == 8
    assert sum(r['reason'] == 'NOT_ACQUIRED_WITHIN_BUDGET_OR_PROVIDER_STOP' for r in out['exclusions']) == 4


def test_interrupted_attempt_cannot_retry(tmp_path):
    directory = tmp_path/'tsx_universe_history'/str(NOW.date()); directory.mkdir(parents=True)
    write_atomic(directory/'attempt.json', {'status': 'PREPARING'})
    out = P.prepare(tmp_path, now=NOW, fetcher=lambda *a: pytest.fail('retry'), acquire_fn=acquire)
    assert out['status'] == 'UNAVAILABLE'


def test_diagnostic_never_loads_as_production_even_before_open(tmp_path):
    root = tmp_path/'isolated'; create_context(root, now=NOW)
    master(root, [row()])
    out = P.prepare(root, now=NOW, diagnostic=True, fetcher=lambda t, n: receipt(t), acquire_fn=acquire)
    assert out['status'] == 'PARTIAL' and out['morning_snapshot'] is False
    assert U.load_prepared(root, NOW)['reason'] == 'UNIVERSE_DIAGNOSTIC_CONTEXT_MISMATCH'
    with pytest.raises(ValueError, match='PREOPEN_ONLY'): P.prepare(root, now=NOW)
    (root/'reports.sqlite3').touch()
    with pytest.raises(ValueError, match='NONPUBLICATION'): P.prepare(root, now=NOW, diagnostic=True)


def test_postopen_production_is_refused(tmp_path):
    with pytest.raises(ValueError, match='PREOPEN_ONLY'):
        P.prepare(tmp_path, now=NOW.replace(hour=10))


@pytest.mark.parametrize('name,expected', [('A Ltd', None), ('Commonwealth Inc', None),
    ('A Common Shares', 'COMMON_STOCK'), ('A REIT Trust Units', None),
    ('A Preferred Common', None), ('A ETF Common Units', None)])
def test_only_explicit_instrument_security_type(name, expected):
    assert P.explicit_security_type(name) == expected


def test_no_industry_or_security_type_inference_from_tmx_directory():
    assert P.explicit_security_type('Royal Bank of Canada') is None


def test_receipt_endpoint_and_clock_must_be_exact():
    r = receipt(); r['source_url'] = 'https://query1.finance.yahoo.com.evil.test/v8/finance/chart/AAA.TO'
    with pytest.raises(ValueError, match='ENDPOINT_MISMATCH'): U.liquidity(r, 'AAA.TO', NOW)
    r = receipt(); r['retrieved_at'] = NOW.replace(hour=9).isoformat()
    with pytest.raises(ValueError, match='CLOCK_MISMATCH'): U.liquidity(r, 'AAA.TO', NOW)


def workbook_bytes():
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    strings = ['Co_ID', 'Exchange', 'Market Cap (C$)\n31-July-2026',
               'ID_A', 'TSX', 'A REIT', 'AAA', 'Real Estate', 'Diversified REITs']
    cells = [(10, [('A', 0), ('B', 1), ('E', 2)]),
             (11, [('A', 3), ('B', 4), ('C', 5), ('D', 6), ('G', 7), ('X', 8)])]
    rows = ''.join('<row r="%d">%s</row>' % (r, ''.join(
        '<c r="%s%d" t="s"><v>%d</v></c>' % (c, r, v) for c, v in values)) for r, values in cells)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('xl/sharedStrings.xml', '<sst xmlns="%s">%s</sst>' %
            (ns, ''.join('<si><t>%s</t></si>' % escape(s) for s in strings)))
        z.writestr('xl/workbook.xml', '<workbook xmlns="%s"><sheets><sheet name="TSX Issuers July 2026"/></sheets></workbook>' % ns)
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (ns, rows))
    return out.getvalue()


def test_official_issuer_parser_uses_field_date_and_explicit_industry():
    parsed = P.parse_tmx_xlsx(workbook_bytes())
    assert parsed['metadata_as_of'] == '2026-07-31'
    assert parsed['rows'][0]['industry'] == 'Diversified REITs'
    assert parsed['rows'][0]['root_symbol'] == 'AAA'
    assert 'ticker' not in parsed['rows'][0] and 'security_type' not in parsed['rows'][0]
    assert 'not ADV20' in parsed['discovery_order']


def test_automatic_directory_refusal_stops_new_waves(tmp_path):
    history = tmp_path/'history'; history.mkdir()
    calls, errors, hashes = [], [], {}
    def wave(tasks):
        calls.extend(tasks)
        if 'bulk' in tasks:
            return {'bulk': {'status': 'OK', 'value': {'content_hex': workbook_bytes().hex(),
                'retrieved_at': NOW.isoformat(), 'source_url': P.TMX_BULK}}}
        if 'suspended' in tasks:
            raw = {'length': 0, 'results': [], 'last_updated': NOW.timestamp()}
            return {key: {'status': 'OK', 'value': {'content_hex': json.dumps(raw).encode().hex(),
                'retrieved_at': NOW.isoformat(), 'source_url': f'https://www.tsx.com/json/company-directory/{key}/tsx'}} for key in tasks}
        return {key: {'status': 'UNAVAILABLE', 'error': 'ReferenceRateLimitError'} for key in tasks}
    out, coverage = P._automatic_master(tmp_path, history, NOW, P.time.monotonic()+180, wave, hashes, errors)
    assert out == [] and len(calls) == 11
    assert coverage['directory_queries_completed'] == 0
    assert hashes and any(r['reason'] == 'WHOLE_WAVE_OUTAGE_REQUESTS_STOPPED' for r in errors)


@pytest.mark.parametrize('invalid', [[], {'schema_version': 1, 'reviewed': True, 'candidates': ['bad']}])
def test_malformed_reviewed_master_is_saved_as_explicit_failure(tmp_path, invalid):
    write_atomic(tmp_path/'tsx_security_master.json', invalid)
    out = P.prepare(tmp_path, now=NOW, acquire_fn=acquire)
    assert out['status'] == 'UNAVAILABLE'
    assert out['exclusions'][0]['reason'] == 'REVIEWED_SECURITY_MASTER_SCHEMA_REQUIRED'


def test_listing_check_before_prior_close_is_stale():
    r = row(); r['listing_verified_at'] = '2026-09-11T09:00:00-04:00'
    with pytest.raises(ValueError, match='LISTING_STATUS_NOT_CURRENT'): U.validate_master_row(r, NOW)


@pytest.mark.parametrize('invalid', [[], {'candidates': ['not-a-row']}, {'schema_version': 1, 'target': 150, 'candidates': []}])
def test_bad_optional_snapshot_has_explicit_gap(tmp_path, invalid):
    write_atomic(tmp_path/'tsx_universe.json', invalid)
    result = U.load_prepared(tmp_path, NOW)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'UNIVERSE_SNAPSHOT_SCHEMA_INVALID'


def real_reit_reference(root='REI', issuer_name='Riocan Real Estate Investment Trust',
                        directory_name='RioCan Real Estate Investment Trust',
                        instrument_name='RioCan Rl Est Tr Un'):
    # Exact observed shapes from the retained TMX July workbook and September
    # directory. No fixture assigns current liquidity or an executable quote.
    issuer = {'issuer_id': 'RIO0005', 'root_symbol': root, 'issuer_name': issuer_name,
        'sector': 'Real Estate', 'industry': 'REIT', 'structured_product_type': 'Income Trust',
        'metadata_as_of': '2026-07-31', 'source_url': P.TMX_BULK}
    ref = {'row': {'symbol': root+'.UN', 'name': directory_name,
                  'instruments': [{'symbol': root+'.UN', 'name': instrument_name}]},
           'clock': NOW, 'receipt': {'source_url': P.TMX_DIRECTORY+'R', 'retrieved_at': NOW.isoformat()}}
    return issuer, ref


@pytest.mark.parametrize('root,issuer_name,instrument', [
    ('REI', 'RioCan Real Estate Investment Trust', 'RioCan Rl Est Tr Un'),
    ('AP', 'Allied Properties Real Estate Investment Trust', 'Allied Prop. REIT Un'),
    ('BEI', 'Boardwalk Real Estate Investment Trust', 'Boardwalk REIT Un'),
    ('DIR', 'Dream Industrial Real Estate Investment Trust', 'Dream Industrl REIT'),
    ('FCR', 'First Capital Real Estate Investment Trust', 'First Cap REIT Un'),
    ('KMP', 'Killam Apartment Real Estate Investment Trust', 'Killam Apt REIT Un J'),
    ('SRU', 'SmartCentres Real Estate Investment Trust', 'SmartCtr REIT VV Un')])
def test_actual_tmx_unit_shape_maps_root_and_retains_income_trust(root, issuer_name, instrument):
    issuer, ref = real_reit_reference(root, issuer_name, issuer_name, instrument)
    assert P.eligible_issuer(issuer)
    rows, errors = P.resolve_tmx_instruments([issuer], {root+'.UN': ref})
    assert len(rows) == 1 and not errors
    assert rows[0]['ticker'] == root+'-UN.TO'
    assert rows[0]['security_type'] == 'REIT'
    assert rows[0]['security_type_rule'] == 'TMX_REIT_ISSUER_EXACT_UN_UNIT'
    assert rows[0]['active'] is False
    assert 'median_dollar_volume_20' not in rows[0]


def test_reit_join_requires_exact_name_symbol_and_issuer_classification():
    issuer, ref = real_reit_reference()
    for key, value in [('industry', ''), ('sector', 'ETP'), ('structured_product_type', 'Exchange Traded Funds')]:
        rows, errors = P.resolve_tmx_instruments([{**issuer, key: value}], {'REI.UN': ref})
        assert not rows and errors
    bad = copy.deepcopy(ref); bad['row']['name'] = 'Different Real Estate Investment Trust'
    assert not P.resolve_tmx_instruments([issuer], {'REI.UN': bad})[0]
    # Prefix matching could confuse REI with REIT.UN or REI.DB. It is forbidden.
    assert not P.resolve_tmx_instruments([issuer], {'REIT.UN': ref})[0]


def test_reit_issuer_does_not_make_its_debenture_or_preferred_eligible():
    issuer, ref = real_reit_reference('MRT', 'Morguard Real Estate Investment Trust',
        'Morguard Real Estate Investment Trust', 'Morguard REIT Un')
    ref['row']['instruments'] += [{'symbol': 'MRT.DB.A', 'name': 'Morguard REIT'},
                                 {'symbol': 'MRT.PR.A', 'name': 'Morguard REIT'}]
    rows, errors = P.resolve_tmx_instruments([issuer], {'MRT.UN': ref}, active_verified=True)
    assert [r['ticker'] for r in rows] == ['MRT-UN.TO']
    assert len(errors) == 2


@pytest.mark.parametrize('symbol,name', [('HCRE', 'GblX EqlWgtCA REIT'), ('XRE', 'iShares S&P/TSX REIT')])
def test_reit_etf_display_name_is_not_a_reit_unit(symbol, name):
    issuer, ref = real_reit_reference(symbol, name, name, name)
    issuer.update(sector='ETP', industry='', structured_product_type='Exchange Traded Funds')
    ref['row'].update(symbol=symbol, instruments=[{'symbol': symbol, 'name': name}])
    assert P.explicit_security_type(name) is None
    assert not P.resolve_tmx_instruments([issuer], {symbol: ref})[0]


def test_status_feed_exclusion_still_applies_to_joined_reit_units():
    issuer, ref = real_reit_reference()
    assert not P.resolve_tmx_instruments([issuer], {'REI.UN': ref}, {'REI.UN'}, active_verified=True)[0]
