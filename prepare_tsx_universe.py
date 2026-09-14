"""Bounded, once/session TSX research directory and completed-day liquidity staging."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import io
import json
import re
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as XML
import zipfile
from collections import Counter
from pathlib import Path

from bounded import acquire
from build_biotech import write_atomic
from diagnostic_context import SNAPSHOT_KIND
import tsx_universe as U

BUDGET_SECONDS, REQUEST_SECONDS, WORKERS = 180, 18, 8
TMX_BULK = 'https://www.tsx.com/en/resource/571'
TMX_DIRECTORY = 'https://www.tsx.com/json/company-directory/search/tsx/'


class ReferenceRateLimitError(RuntimeError):
    acquisition_http_status = 429
    acquisition_reason_code = 'RATE_LIMITED'


class ReferenceAuthenticationError(RuntimeError):
    acquisition_reason_code = 'AUTHENTICATION_ERROR'


def _fetch(url):
    U.source_url(url)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            data = response.read(12_000_001)
            if len(data) > 12_000_000:
                raise ValueError('REFERENCE_RESPONSE_TOO_LARGE')
            return {'source_url': url, 'retrieved_at': dt.datetime.now(U.ET).isoformat(),
                    'sha256': hashlib.sha256(data).hexdigest(), 'content_hex': data.hex()}
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ReferenceRateLimitError('Reference provider rate limited') from None
        if exc.code in (401, 403):
            raise ReferenceAuthenticationError('Reference provider refused access') from None
        raise


def parse_tmx_xlsx(data):
    """Read the official issuer sheet; preserve its date, root symbols and gaps."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist()) > 80_000_000:
            raise ValueError('REFERENCE_WORKBOOK_TOO_LARGE')
        strings = [''.join(x.itertext()) for x in XML.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns)]
        sheets = XML.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet', ns)
        if not sheets or not sheets[0].attrib.get('name', '').startswith('TSX Issuers '):
            raise ValueError('TMX_ISSUER_SHEET_CHANGED')
        rows = []
        for row in XML.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('s:sheetData/s:row', ns):
            parsed = {}
            for cell in row.findall('s:c', ns):
                value = cell.find('s:v', ns)
                text = value.text if value is not None else ''
                if cell.attrib.get('t') == 's':
                    text = strings[int(text)]
                parsed[re.sub('[0-9]', '', cell.attrib['r'])] = text
            rows.append(parsed)
    header = next((r for r in rows if r.get('A') == 'Co_ID' and r.get('B') == 'Exchange'), None)
    if header is None or not header.get('E', '').startswith('Market Cap (C$)'):
        raise ValueError('TMX_ISSUER_HEADERS_CHANGED')
    date = dt.datetime.strptime(header['E'].split('\n')[-1], '%d-%B-%Y').date()
    out = []
    for row in rows:
        if row.get('B') != 'TSX' or not row.get('A') or not row.get('D'):
            continue
        industry = row.get('H') or next((row.get(c) for c in ('T', 'V', 'W', 'X', 'Y') if row.get(c)), '')
        out.append({'issuer_id': row['A'], 'root_symbol': row['D'], 'issuer_name': row.get('C', ''),
                    'sector': row.get('G', ''), 'industry': industry,
                    'structured_product_type': row.get('AD', ''),
                    'metadata_as_of': str(date), 'source_url': TMX_BULK,
                    'source_ytd_value_cad': float(row.get('AG') or 0),
                    'source_trading_months': float(row.get('AI') or 0)})
    return {'rows': out, 'metadata_as_of': str(date), 'issuer_count': len(out),
            'discovery_order': 'YTD CAD value descending; not ADV20 or current liquidity'}


def explicit_security_type(name):
    text = name.lower()
    if re.search(r'\b(preferred|pr|warrants?|rights?|debentures?|etf|cdr|depositary)\b', text):
        return None
    # 'REIT' may describe an ETF or a REIT issuer's debenture. Unit type needs
    # the issuer classification and exact .UN instrument together below.
    if re.search(r'\bcommon\b|\bordinary shares\b', text):
        return 'COMMON_STOCK'
    return None


def _name_key(name):
    return re.sub(r'[^a-z0-9]', '', str(name).casefold())


def reit_issuer(issuer):
    """Positive TMX business classification, not the occurrence of REIT in a fund name."""
    name = issuer.get('issuer_name', '').casefold()
    return (issuer.get('sector') == 'Real Estate'
            and re.search(r'\breits?\b', issuer.get('industry', '').casefold()) is not None
            and ('real estate investment trust' in name or re.search(r'\breit\b', name) is not None)
            and issuer.get('structured_product_type', '') in ('', 'Income Trust'))


def eligible_issuer(issuer):
    """Income-trust REITs are eligible units; ETFs and other funds remain excluded."""
    if issuer.get('sector') in {'ETP', 'CDR', 'Closed-End Funds', 'SPAC'}:
        return False
    return not issuer.get('structured_product_type') or reit_issuer(issuer)


def resolve_tmx_instruments(issuers, instrument_rows, blocked_symbols=(), *, active_verified=False):
    """Join retained facts without requests. Only exact root or documented .UN.

    The pure receipt replay defaults to inactive/unverified. The production
    caller separately verifies the two current status feeds before setting
    active_verified=True; matching symbols alone cannot establish tradability.
    """
    out, errors = [], []
    for issuer in issuers:
        root = issuer['root_symbol']
        if not eligible_issuer(issuer):
            errors.append({'ticker': root, 'reason': 'INELIGIBLE_ISSUER_FUND_OR_PRODUCT'})
            continue
        ref = instrument_rows.get(root, {})
        if not ref and reit_issuer(issuer):
            ref = instrument_rows.get(root+'.UN', {})
        directory = ref.get('row', {})
        instruments = directory.get('instruments', [])
        if (not instruments or ref.get('conflict')
                or _name_key(directory.get('name')) != _name_key(issuer.get('issuer_name'))):
            errors.append({'ticker': root, 'reason': 'CURRENT_EXACT_INSTRUMENT_UNVERIFIED'})
            continue
        for instrument in instruments:
            symbol, name = instrument.get('symbol', ''), instrument.get('name', '')
            if symbol in blocked_symbols or root in blocked_symbols:
                errors.append({'ticker': symbol, 'reason': 'SUSPENDED_OR_DELISTED_SECURITY'})
                continue
            parts = symbol.upper().split('.')
            if any(p in ('PR', 'PF', 'DB', 'WT', 'RT', 'U') for p in parts[1:]):
                errors.append({'ticker': symbol, 'reason': 'INELIGIBLE_SECURITY_SYMBOL'})
                continue
            # Exact .UN plus the classified REIT issuer establishes trust units,
            # even when its display name abbreviates 'RioCan Rl Est Tr Un'.
            if reit_issuer(issuer) and symbol == root+'.UN':
                kind, rule = 'REIT', 'TMX_REIT_ISSUER_EXACT_UN_UNIT'
            else:
                kind, rule = explicit_security_type(name), 'EXPLICIT_COMMON_INSTRUMENT_DESCRIPTION'
            if not kind or not issuer['industry']:
                errors.append({'ticker': symbol, 'reason': 'EXPLICIT_SECURITY_TYPE_OR_INDUSTRY_MISSING'})
                continue
            ticker = symbol.replace('.', '-')+'.TO'
            if not U.TICKER.fullmatch(ticker):
                errors.append({'ticker': symbol, 'reason': 'INELIGIBLE_SECURITY_SYMBOL'})
                continue
            receipt = ref['receipt']
            out.append({**issuer, 'ticker': ticker, 'instrument_name': name,
                'security_type': kind, 'security_type_rule': rule,
                'exchange': 'TSX', 'currency': 'CAD', 'active': active_verified,
                'retrieved_at': receipt['retrieved_at'], 'listing_verified_at': ref['clock'].isoformat(),
                'evidence': {'listing': receipt['source_url'], 'security_type': receipt['source_url'], 'industry': TMX_BULK}})
    return out, errors


def _directory_query(letter):
    url = (f'https://www.tsx.com/json/company-directory/{letter}/tsx'
           if letter in ('suspended', 'delisted') else TMX_DIRECTORY+letter)
    receipt = _fetch(url)
    raw = json.loads(bytes.fromhex(receipt['content_hex']))
    if not isinstance(raw.get('results'), list) or raw.get('length') != len(raw['results']):
        raise ValueError('TMX_DIRECTORY_COUNT_MISMATCH')
    return receipt


def fetch_daily(ticker, now):
    from adapters import ChartAuthenticationError, ChartRateLimitError
    import requests
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
    response = requests.get(url, params={'interval': '1d', 'range': '3mo'},
                            headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
    if response.status_code == 429:
        raise ChartRateLimitError('Daily reference rate limited')
    if response.status_code in (401, 403):
        raise ChartAuthenticationError('Daily reference provider refused access')
    response.raise_for_status()
    raw = response.json().get('chart', {}).get('result')
    if not isinstance(raw, list) or len(raw) != 1:
        raise ValueError('DAILY_CHART_RESPONSE_INVALID')
    return {'response': raw[0], 'retrieved_at': dt.datetime.now(U.ET).isoformat(),
            'source_url': url}


def _automatic_master(root, history, now, deadline, acquire_fn, receipt_files, errors):
    remaining = deadline-time.monotonic()
    result = acquire_fn({'bulk': (lambda: _fetch(TMX_BULK), min(30, remaining))})['bulk']
    if result['status'] != 'OK':
        errors.append({'source': 'TMX_BULK', 'reason': result.get('error', 'UNAVAILABLE')})
        return [], {'directory': 'UNAVAILABLE', 'complete_market_rank': False}
    bulk = result['value']
    _save_receipt(root, history/'tmx_bulk.receipt.json', bulk, receipt_files)
    parsed = parse_tmx_xlsx(bytes.fromhex(bulk['content_hex']))
    issuers = sorted((r for r in parsed['rows'] if eligible_issuer(r)),
                     key=lambda r: (-r['source_ytd_value_cad'], r['root_symbol']))[:U.DISCOVERY_LIMIT]
    # A listed issuer may be suspended. Both independent status feeds must be
    # current before a current-directory match can establish active status.
    blocked_symbols, status_ok = set(), []
    remaining = deadline-time.monotonic()
    if remaining > 0:
        statuses = acquire_fn({k: (lambda k=k: _directory_query(k), min(REQUEST_SECONDS, remaining))
                               for k in ('suspended', 'delisted')})
        for key, item in statuses.items():
            if item['status'] != 'OK':
                errors.append({'source': 'TMX_STATUS', 'query': key, 'reason': item.get('error', 'UNAVAILABLE')})
                continue
            receipt = item['value']
            _save_receipt(root, history/f'tmx_{key}.receipt.json', receipt, receipt_files)
            raw = json.loads(bytes.fromhex(receipt['content_hex']))
            timestamp = dt.datetime.fromtimestamp(raw['last_updated'], U.ET)
            prior = U.previous_sessions(now, 1)[0]
            prior_close = U.session_schedule(str(prior), str(prior)).iloc[0]['market_close'].to_pydatetime()
            if timestamp > U.aware(receipt['retrieved_at']) or timestamp < prior_close:
                errors.append({'source': 'TMX_STATUS', 'query': key, 'reason': 'ACTIVE_STATUS_FEED_STALE'})
                continue
            blocked_symbols.update(r.get('symbol') for r in raw['results'] if isinstance(r, dict))
            status_ok.append(key)
    if len(status_ok) != 2:
        return [], {'directory': 'ACTIVE_STATUS_UNVERIFIED', 'issuer_count': parsed['issuer_count'],
                    'metadata_as_of': parsed['metadata_as_of'], 'discovery_issuers': len(issuers),
                    'directory_queries_completed': 0, 'directory_queries_requested': 27,
                    'complete_market_rank': False}
    # Company names may match multiple prefixes. Union all advertised alphabet
    # queries; exact issuer root and instrument identities remain distinct.
    query_keys = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')+['0-9']
    instrument_rows, succeeded = {}, []
    for offset in range(0, len(query_keys), WORKERS):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            errors.append({'source': 'TMX_DIRECTORY', 'reason': 'PREPARATION_BUDGET_EXHAUSTED'})
            break
        batch = query_keys[offset:offset+WORKERS]
        result = acquire_fn({k: (lambda k=k: _directory_query(k), min(REQUEST_SECONDS, remaining)) for k in batch})
        failed, refusal = 0, False
        for k in batch:
            item = result[k]
            if item['status'] != 'OK':
                failed += 1
                refusal |= item.get('error') in ('ReferenceRateLimitError', 'ReferenceAuthenticationError')
                errors.append({'source': 'TMX_DIRECTORY', 'query': k, 'reason': item.get('error', 'UNAVAILABLE')})
                continue
            receipt = item['value']
            _save_receipt(root, history/f'tmx_directory_{k}.receipt.json', receipt, receipt_files)
            raw = json.loads(bytes.fromhex(receipt['content_hex']))
            clock = dt.datetime.fromtimestamp(raw['last_updated'], U.ET)
            if clock > U.aware(receipt['retrieved_at']) or clock.date() < U.previous_sessions(now, 1)[0]:
                errors.append({'source': 'TMX_DIRECTORY', 'query': k, 'reason': 'LISTING_STATUS_NOT_CURRENT'})
                continue
            succeeded.append(k)
            for row in raw['results']:
                key = row.get('symbol')
                if not key:
                    continue
                if key in instrument_rows and instrument_rows[key]['row'] != row:
                    errors.append({'source': 'TMX_DIRECTORY', 'ticker': key, 'reason': 'CONFLICTING_ISSUER_DIRECTORY_ROWS'})
                    instrument_rows[key] = {'row': {}, 'conflict': True}
                elif key not in instrument_rows:
                    instrument_rows[key] = {'row': row, 'clock': clock, 'receipt': receipt}
        if refusal or failed == len(batch):
            errors.append({'source': 'TMX_DIRECTORY', 'reason': 'WHOLE_WAVE_OUTAGE_REQUESTS_STOPPED'})
            break
    out, join_errors = resolve_tmx_instruments(issuers, instrument_rows,
        blocked_symbols, active_verified=True)
    errors.extend(join_errors)
    return out, {'directory': 'CURRENT_INSTRUMENTS_WITH_DATED_ISSUER_METADATA',
                'issuer_count': parsed['issuer_count'], 'discovery_issuers': len(issuers),
                'directory_queries_completed': len(succeeded), 'directory_queries_requested': len(query_keys),
                'active_status_feeds_verified': status_ok,
                'metadata_as_of': parsed['metadata_as_of'], 'discovery_order': parsed['discovery_order'],
                'complete_market_rank': False,
                'limit': 'Monthly issuer metadata and explicit instrument names do not certify every TSX common share.'}


def _save_receipt(root, path, receipt, hashes):
    write_atomic(path, receipt)
    hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(state_dir, *, now=None, master_path=None, fetcher=None, acquire_fn=None, diagnostic=False):
    """Run once before open; diagnostics require an explicitly isolated context."""
    root = Path(state_dir)
    live_clock = now is None
    now = U.aware(now or dt.datetime.now(U.ET))
    if diagnostic:
        from diagnostic_context import require_context
        require_context(root)
    elif (root/'diagnostic_context.json').exists() or now.time() >= dt.time(9, 30):
        raise ValueError('TSX_UNIVERSE_PRODUCTION_PREOPEN_ONLY')
    budget = BUDGET_SECONDS if diagnostic else min(BUDGET_SECONDS,
        (now.replace(hour=9, minute=30, second=0, microsecond=0)-now).total_seconds())
    started_monotonic = time.monotonic()
    deadline = started_monotonic+budget
    acquire_fn, fetcher = acquire_fn or acquire, fetcher or fetch_daily
    history = root/'tsx_universe_history'/str(now.date())
    history.mkdir(parents=True, exist_ok=True)
    context = {'kind': SNAPSHOT_KIND, 'morning_snapshot': False, 'prediction_evidence': False} if diagnostic else {}
    with (history/'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'UNAVAILABLE', 'reason': 'PREPARATION_IN_PROGRESS_NO_RETRY', 'candidates': []}
        attempt = history/'attempt.json'
        if attempt.exists():
            try:
                prior = json.loads(attempt.read_text())
                if not isinstance(prior, dict):
                    raise ValueError('ATTEMPT_RECORD_INVALID')
            except (OSError, ValueError, TypeError):
                return {'status': 'UNAVAILABLE', 'session': str(now.date()), 'target': U.TARGET,
                        'mode': U.MODE, 'candidates': [], 'reason': 'ATTEMPT_RECORD_INVALID_NO_RETRY'}
            if prior.get('status') == 'PREPARING':
                return {'status': 'UNAVAILABLE', 'session': str(now.date()), 'target': U.TARGET,
                        'mode': U.MODE, 'candidates': [], 'reason': 'INTERRUPTED_PREPARATION_NO_RETRY'}
            return U.load_prepared(root, now, diagnostic=diagnostic)
        write_atomic(attempt, {'status': 'PREPARING', 'started_at': now.isoformat(), **context})
        obj = {'schema_version': 1, 'session': str(now.date()), 'target': U.TARGET,
               'mode': U.MODE, 'status': 'UNAVAILABLE', 'prepared_at': now.isoformat(),
               'started_at': now.isoformat(), 'candidates': [], 'exclusions': [],
               'receipt_files': {}, 'registration': U.REGISTRATION, 'adopted': False,
               'source_coverage': {'complete_market_rank': False}, **context}

        def checkpoint(final=False):
            stamp = dt.datetime.now(U.ET) if live_clock else now
            obj['prepared_at'] = stamp.isoformat()
            obj['elapsed_seconds'] = round(time.monotonic()-started_monotonic, 3)
            if final and not diagnostic and stamp.time() >= dt.time(9, 30):
                obj['status'] = 'UNAVAILABLE'
                obj['exclusions'].append({'source': 'clock', 'reason': 'PREOPEN_DEADLINE_REACHED'})
            write_atomic(history/'snapshot.json', obj)
            write_atomic(root/'tsx_universe.json', obj)
            write_atomic(attempt, {'status': obj['status'] if final else 'PREPARING',
                'started_at': obj['started_at'], 'snapshot_sha256': hashlib.sha256((history/'snapshot.json').read_bytes()).hexdigest(), **context})

        try:
            input_path = Path(master_path) if master_path else root/'tsx_security_master.json'
            if input_path.exists():
                master = json.loads(input_path.read_text())
                if (not isinstance(master, dict) or master.get('schema_version') != 1
                        or master.get('reviewed') is not True or not isinstance(master.get('candidates'), list)
                        or any(not isinstance(row, dict) for row in master['candidates'])):
                    raise ValueError('REVIEWED_SECURITY_MASTER_SCHEMA_REQUIRED')
                rows = master['candidates']
                if len(rows) > U.DISCOVERY_LIMIT:
                    raise ValueError('REVIEWED_SECURITY_MASTER_EXCEEDS_DISCOVERY_BOUND')
                _save_receipt(root, history/'reviewed_master.receipt.json', master, obj['receipt_files'])
                obj['source_coverage'] = {'directory': 'REVIEWED_SECURITY_MASTER', 'enumerated': len(rows),
                    'complete_market_rank': False,
                    'limit': 'Ranks within the explicitly reviewed source sample; reviewer assertions and URLs are not independent source authentication.'}
            else:
                rows, obj['source_coverage'] = _automatic_master(root, history, now, deadline,
                    acquire_fn, obj['receipt_files'], obj['exclusions'])
            pending, seen = [], set()
            ticker_counts = Counter(row.get('ticker') for row in rows if isinstance(row, dict))
            for row in rows:
                try:
                    checked = U.validate_master_row(row, dt.datetime.now(U.ET) if live_clock else now)
                    if ticker_counts[row['ticker']] > 1:
                        raise ValueError('DUPLICATE_SECURITY_MASTER_TICKER')
                    seen.add(row['ticker'])
                    pending.append(checked)
                except (ValueError, KeyError, TypeError) as exc:
                    obj['exclusions'].append({'ticker': row.get('ticker', '?'), 'reason': U._reason(exc)})
            obj['source_coverage']['metadata_eligible'] = len(pending)
            obj['source_coverage']['daily_requested'] = len(pending)
            good, attempted = [], set()
            checkpoint()
            for offset in range(0, len(pending), WORKERS):
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    break
                batch = pending[offset:offset+WORKERS]
                results = acquire_fn({r['ticker']: (lambda r=r: fetcher(r['ticker'], now),
                    min(REQUEST_SECONDS, remaining)) for r in batch})
                failures, refusal = 0, False
                for row in batch:
                    ticker = row['ticker']; attempted.add(ticker)
                    item = results[ticker]
                    if item['status'] != 'OK':
                        failures += 1
                        reason = item.get('error', 'ACQUISITION_UNAVAILABLE')
                        refusal |= reason in ('ChartRateLimitError', 'ChartAuthenticationError')
                        obj['exclusions'].append({'ticker': ticker, 'reason': reason})
                        continue
                    receipt = item['value']
                    path = history/(ticker+'.daily.receipt.json')
                    _save_receipt(root, path, receipt, obj['receipt_files'])
                    try:
                        measured = U.liquidity(receipt, ticker, dt.datetime.now(U.ET) if live_clock else now)
                        good.append({**row, **measured, 'daily_receipt_file': str(path.relative_to(root))})
                    except (ValueError, TypeError, KeyError) as exc:
                        obj['exclusions'].append({'ticker': ticker, 'reason': U._reason(exc)})
                obj['candidates'], _ = U.rank(good)
                checkpoint()
                if refusal or failures == len(batch):
                    obj['exclusions'].append({'source': 'daily', 'reason': 'PROVIDER_OUTAGE_FURTHER_REQUESTS_SKIPPED'})
                    break
            for row in pending:
                if row['ticker'] not in attempted:
                    obj['exclusions'].append({'ticker': row['ticker'], 'reason': 'NOT_ACQUIRED_WITHIN_BUDGET_OR_PROVIDER_STOP'})
            obj['candidates'], rejected = U.rank(good)
            obj['exclusions'] += rejected
            obj['source_coverage']['daily_attempted'] = len(attempted)
            obj['source_coverage']['daily_eligible'] = len(good)
            obj['status'] = 'READY' if len(obj['candidates']) == U.TARGET else 'PARTIAL' if good else 'UNAVAILABLE'
        except (ValueError, OSError, TypeError, KeyError, IndexError, OverflowError,
                XML.ParseError, zipfile.BadZipFile) as exc:
            obj['exclusions'].append({'source': 'preparation', 'reason': U._reason(exc)})
        checkpoint(final=True)
        return U.load_prepared(root, dt.datetime.now(U.ET) if live_clock else now, diagnostic=diagnostic)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--master', help='Reviewed dated security master JSON; never inferred missing facts.')
    parser.add_argument('--diagnostic', action='store_true', help='Existing isolated diagnostic context; actual clock only.')
    args = parser.parse_args(argv)
    result = prepare(args.state_dir, master_path=args.master, diagnostic=args.diagnostic)
    print(json.dumps({k: result.get(k) for k in ('status', 'session', 'target', 'source_coverage', 'reason')}, indent=2))
    print('Eligible research securities:', len(result.get('candidates', [])))
    return 0 if result['status'] == 'READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
