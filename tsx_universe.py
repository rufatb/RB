"""Day101 dated TSX research eligibility. Pure validation; no trade selection."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pandas as pd

from diagnostic_context import SNAPSHOT_KIND
from intraday_history import ohlcv_error, session_schedule

ET = ZoneInfo('America/New_York')
TARGET = 150
DISCOVERY_LIMIT = 500
MIN_MEDIAN_DOLLAR_VOLUME = 10_000_000
METADATA_MAX_DAYS = 62
REGISTRATION = 'PREREGISTER_day101_tsx_expansion.md'
MODE = 'EXPANDED_TSX_RESEARCH'
TICKER = re.compile(r'^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)?\.TO$')


def aware(value):
    result = dt.datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, dt.datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
    return result.astimezone(ET)


def source_url(value):
    if not isinstance(value, str):
        raise ValueError('SOURCE_URL_REQUIRED')
    u = urlsplit(value)
    if (u.scheme != 'https' or not u.hostname or u.username or u.password
            or u.query or u.fragment):
        raise ValueError('CREDENTIAL_FREE_SOURCE_URL_REQUIRED')
    return value


def previous_sessions(now, count=20):
    now = aware(now)
    schedule = session_schedule((now.date()-dt.timedelta(days=65)).isoformat(),
                                (now.date()-dt.timedelta(days=1)).isoformat())
    dates = list(schedule.index.date)[-count:]
    if len(dates) != count:
        raise ValueError('COMPLETED_SESSION_GRID_UNAVAILABLE')
    return dates


def validate_master_row(row, now):
    """A root symbol or EQUITY flag alone cannot establish a common share."""
    now = aware(now)
    required = ('ticker', 'issuer_id', 'sector', 'industry', 'security_type',
                'source_url', 'metadata_as_of', 'retrieved_at', 'listing_verified_at')
    if not isinstance(row, dict) or any(not row.get(k) for k in required):
        raise ValueError('SECURITY_MASTER_FIELDS_MISSING')
    if not TICKER.fullmatch(row['ticker']):
        raise ValueError('EXACT_TSX_TICKER_REQUIRED')
    if row.get('exchange') != 'TSX' or row.get('currency') != 'CAD' or row.get('active') is not True:
        raise ValueError('ACTIVE_TSX_CAD_IDENTITY_REQUIRED')
    if row['security_type'] not in ('COMMON_STOCK', 'REIT'):
        raise ValueError('INELIGIBLE_SECURITY_TYPE')
    if any(not isinstance(row[k], str) or not row[k].strip() or len(row[k]) > 200
           for k in ('issuer_id', 'sector', 'industry')):
        raise ValueError('ISSUER_INDUSTRY_IDENTITY_REQUIRED')
    retrieved = aware(row['retrieved_at'])
    verified = aware(row['listing_verified_at'])
    as_of = dt.date.fromisoformat(row['metadata_as_of'])
    if (retrieved > now or as_of > retrieved.date() or verified > retrieved
            or (now.date()-as_of).days > METADATA_MAX_DAYS):
        raise ValueError('SECURITY_METADATA_STALE_OR_FUTURE')
    prior = previous_sessions(now, 1)[0]
    prior_close = session_schedule(str(prior), str(prior)).iloc[0]['market_close'].to_pydatetime()
    if verified > now or verified < prior_close:
        raise ValueError('LISTING_STATUS_NOT_CURRENT')
    source_url(row['source_url'])
    evidence = row.get('evidence', {})
    for key in ('security_type', 'industry', 'listing'):
        if not isinstance(evidence, dict) or not evidence.get(key):
            raise ValueError('SECURITY_REFERENCE_EVIDENCE_MISSING')
        source_url(evidence[key])
    return dict(row)


def liquidity(receipt, ticker, now):
    """Median raw daily Close*Volume on the exact prior 20-session grid."""
    now = aware(now)
    if not isinstance(receipt, dict) or not isinstance(receipt.get('response'), dict):
        raise ValueError('DAILY_RECEIPT_OBJECT_REQUIRED')
    raw = receipt.get('response', {})
    meta = raw.get('meta', {})
    if not isinstance(meta, dict):
        raise ValueError('DAILY_REFERENCE_METADATA_OBJECT_REQUIRED')
    if (meta.get('symbol') != ticker or meta.get('currency') != 'CAD'
            or meta.get('exchangeName') != 'TOR' or meta.get('instrumentType') != 'EQUITY'
            or meta.get('dataGranularity') != '1d'):
        raise ValueError('DAILY_REFERENCE_IDENTITY_OR_INTERVAL_MISMATCH')
    retrieved = aware(receipt.get('retrieved_at'))
    if retrieved > now or retrieved.date() != now.date():
        raise ValueError('DAILY_RECEIPT_CLOCK_MISMATCH')
    expected_url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}'
    if receipt.get('source_url') not in (expected_url, expected_url.replace('query1.', 'query2.')):
        raise ValueError('DAILY_RECEIPT_ENDPOINT_MISMATCH')
    timestamps = raw.get('timestamp', [])
    indicators = raw.get('indicators')
    if (not isinstance(timestamps, list) or not timestamps or not isinstance(indicators, dict)
            or not isinstance(indicators.get('quote'), list) or len(indicators['quote']) != 1
            or not isinstance(indicators['quote'][0], dict)):
        raise ValueError('DAILY_REFERENCE_ARRAY_SCHEMA_INVALID')
    values = indicators['quote'][0]
    index = pd.to_datetime(timestamps, unit='s', utc=True).tz_convert(ET)
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('DUPLICATE_OR_UNSORTED_DAILY_TIMESTAMPS')
    fields = dict(Open=values.get('open'), High=values.get('high'), Low=values.get('low'),
                  Close=values.get('close'), Volume=values.get('volume'))
    if any(not isinstance(v, list) or len(v) != len(index) for v in fields.values()):
        raise ValueError('DAILY_OHLCV_LENGTH_MISMATCH')
    frame = pd.DataFrame(fields, index=index)
    # An afternoon diagnostic may receive today's unfinished daily candle.
    # It is never a completed-session liquidity observation.
    frame = frame[[i.date() < now.date() for i in frame.index]]
    dates = previous_sessions(now)
    selected = frame[[i.date() >= dates[0] for i in frame.index]]
    if list(selected.index.date) != dates:
        raise ValueError('IMMEDIATE_PRIOR_20_SESSION_GRID_INCOMPLETE')
    if any(i.time() != dt.time(9, 30) for i in selected.index):
        raise ValueError('DAILY_TIMESTAMP_NOT_TSX_OPEN')
    reason = ohlcv_error(selected)
    if reason:
        raise ValueError(reason)
    if (selected['Volume'] <= 0).any():
        raise ValueError('NONPOSITIVE_COMPLETED_SESSION_VOLUME')
    value = float((selected['Close']*selected['Volume']).median())
    if not math.isfinite(value) or value < MIN_MEDIAN_DOLLAR_VOLUME:
        raise ValueError('BELOW_MEDIAN_CAD10M_LIQUIDITY_FLOOR')
    return {'median_dollar_volume_20': value, 'liquidity_first_session': str(dates[0]),
            'liquidity_last_session': str(dates[-1]), 'liquidity_sessions': 20,
            'liquidity_method': 'median(unadjusted daily Close * Volume); proxy, not measured turnover',
            'liquidity_source_url': receipt['source_url']}


def rank(rows):
    """One share class per issuer, within the observed eligible source sample."""
    candidates, exclusions, seen = [], [], set()
    for row in sorted(rows, key=lambda x: (-x['median_dollar_volume_20'], x['ticker'])):
        if row['issuer_id'] in seen:
            exclusions.append({'ticker': row['ticker'], 'reason': 'DUPLICATE_ISSUER_SHARE_CLASS'})
            continue
        seen.add(row['issuer_id'])
        if len(candidates) < TARGET:
            candidates.append(row)
        else:
            exclusions.append({'ticker': row['ticker'], 'reason': 'OUTSIDE_OBSERVED_TOP150'})
    return candidates, exclusions


def load_prepared(state_dir, now, diagnostic=False):
    """Verify frozen snapshot and its raw receipts. Never acquire or infer data."""
    root, now = Path(state_dir), aware(now)
    empty = {'status': 'UNAVAILABLE', 'session': str(now.date()), 'target': TARGET,
             'mode': MODE, 'candidates': [], 'exclusions': [], 'adopted': False,
             'source_coverage': {'complete_market_rank': False}}
    try:
        if diagnostic:
            from diagnostic_context import require_context
            require_context(root)
        path = root/'tsx_universe.json'
        if path.stat().st_size > 8_000_000:
            raise ValueError('UNIVERSE_SNAPSHOT_TOO_LARGE')
        data = path.read_bytes()
        obj = json.loads(data)
        if (not isinstance(obj, dict) or obj.get('schema_version') != 1
                or obj.get('target') != TARGET or not isinstance(obj.get('candidates'), list)
                or any(not isinstance(row, dict) for row in obj['candidates'])
                or len(obj['candidates']) > TARGET or not isinstance(obj.get('receipt_files'), dict)
                or len(obj['receipt_files']) > 1_000 or not isinstance(obj.get('exclusions'), list)
                or any(not isinstance(row, dict) for row in obj['exclusions'])
                or not isinstance(obj.get('source_coverage'), dict)):
            raise ValueError('UNIVERSE_SNAPSHOT_SCHEMA_INVALID')
        if obj.get('session') != str(now.date()) or obj.get('mode') != MODE:
            raise ValueError('UNIVERSE_SESSION_OR_MODE_MISMATCH')
        prepared = aware(obj['prepared_at'])
        is_diagnostic = obj.get('kind') == SNAPSHOT_KIND
        if is_diagnostic != diagnostic or (diagnostic and obj.get('morning_snapshot') is not False):
            raise ValueError('UNIVERSE_DIAGNOSTIC_CONTEXT_MISMATCH')
        if (prepared > now or prepared.date() != now.date()
                or (not diagnostic and prepared.time() >= dt.time(9, 30))):
            raise ValueError('UNIVERSE_PREPARATION_CLOCK_INVALID')
        history = root/'tsx_universe_history'/str(now.date())
        attempt = json.loads((history/'attempt.json').read_text())
        if (not isinstance(attempt, dict) or attempt.get('snapshot_sha256') != hashlib.sha256(data).hexdigest()
                or (history/'snapshot.json').read_bytes() != data
                or attempt.get('status') == 'PREPARING'):
            raise ValueError('UNIVERSE_SEALED_SNAPSHOT_MISMATCH')
        for relative, digest in obj.get('receipt_files', {}).items():
            if (not isinstance(relative, str) or not isinstance(digest, str)
                    or not re.fullmatch('[a-f0-9]{64}', digest)):
                raise ValueError('UNIVERSE_RECEIPT_MANIFEST_INVALID')
            rel = Path(relative)
            if rel.is_absolute() or '..' in rel.parts or rel.is_symlink():
                raise ValueError('UNSAFE_UNIVERSE_RECEIPT_PATH')
            actual = root/rel
            if root.resolve() not in actual.resolve().parents or actual.is_symlink():
                raise ValueError('UNSAFE_UNIVERSE_RECEIPT_PATH')
            if actual.stat().st_size > 25_000_000:
                raise ValueError('UNIVERSE_RECEIPT_TOO_LARGE')
            if hashlib.sha256(actual.read_bytes()).hexdigest() != digest:
                raise ValueError('UNIVERSE_RECEIPT_HASH_MISMATCH')
        valid, rejected = [], list(obj.get('exclusions', []))
        for row in obj.get('candidates', []):
            try:
                checked = validate_master_row(row, now)
                relative = row['daily_receipt_file']
                if relative not in obj.get('receipt_files', {}):
                    raise ValueError('UNIVERSE_DAILY_RECEIPT_UNSEALED')
                receipt = json.loads((root/relative).read_text())
                measured = liquidity(receipt, row['ticker'], now)
                if measured['median_dollar_volume_20'] != row.get('median_dollar_volume_20'):
                    raise ValueError('UNIVERSE_LIQUIDITY_VALUE_MISMATCH')
                valid.append({**checked, **measured})
            except (ValueError, TypeError, KeyError, OSError) as exc:
                rejected.append({'ticker': row.get('ticker', '?'), 'reason': _reason(exc)})
        valid, duplicates = rank(valid)
        status = obj.get('status')
        if status not in ('READY', 'PARTIAL'):
            valid = []
        return {**obj, 'status': ('READY' if status == 'READY' and len(valid) == TARGET
                    else 'PARTIAL' if valid else 'UNAVAILABLE'), 'candidates': valid,
                'exclusions': rejected+duplicates}
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return {**empty, 'reason': _reason(exc)}


def _reason(exc):
    value = str(exc)
    return value if value and value.isupper() and value.replace('_', '').isalnum() else type(exc).__name__
