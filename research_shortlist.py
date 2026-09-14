"""Day101 fixed pre-news coverage shortlist; pure, shadow and outcome-blind.

The selector reads validated Python technicals and dated security metadata.
It never reads headlines, model results, future returns or execution decisions.
The saved receipt is checked again rather than backfilled after acquisition.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
import re

from report_store import encode

MODE = 'EXPANDED_TSX_RESEARCH'
REGISTRATION = 'PREREGISTER_day101_tsx_expansion.md'
MAX_POOL = 150
MIN_LIQUIDITY_CAD = 10_000_000
MIN_SHORTLIST = 30
MAX_SHORTLIST = 50
TECHNICALS = ('vwap', 'rsi', 'macd', 'macd_signal', 'macd_hist',
              'orb_high', 'orb_low', 'rvol')


def expanded(payload):
    return isinstance(payload, dict) and isinstance(payload.get('research_universe'), dict) and (
        payload['research_universe'].get('mode') == MODE)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _text(value):
    from diagnostics import safe_detail
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= 160
            and not any(ord(c) < 32 for c in value) and safe_detail(value, 160) == value)


def normalize_universe(raw, session):
    """Retain only public directory facts, with no loose type coercion."""
    if (not isinstance(raw, dict) or raw.get('mode') != MODE
            or raw.get('session') != session or raw.get('target') != MAX_POOL
            or raw.get('status') not in ('READY', 'PARTIAL', 'UNAVAILABLE')
            or not isinstance(raw.get('candidates'), list) or len(raw['candidates']) > MAX_POOL):
        raise ValueError('INVALID_RESEARCH_UNIVERSE')
    rows = []
    for row in raw['candidates']:
        if (not isinstance(row, dict) or not isinstance(row.get('ticker'), str)
                or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,19}\.TO', row['ticker'])):
            raise ValueError('INVALID_RESEARCH_SECURITY_IDENTITY')
        # Missing directory facts stay missing and exclude that security below.
        clean = {'ticker': row['ticker']}
        for field in ('issuer_id', 'sector', 'industry', 'security_type'):
            clean[field] = row.get(field) if _text(row.get(field)) else None
        value = row.get('median_dollar_volume_20')
        clean['median_dollar_volume_20'] = float(value) if _number(value) and value > 0 else None
        rows.append(clean)
    result = {'mode': MODE, 'session': session, 'target': MAX_POOL,
              'status': raw['status'], 'candidates': rows}
    for key in ('expanded_status', 'source_complete'):
        if key in raw and isinstance(raw[key], (str, bool)):
            result[key] = raw[key]
    return result


def select(clean, universe, session):
    """Round-robin sectors, then descending median liquidity and ticker ties."""
    meta = normalize_universe(universe, session)
    rows = clean.get('candidates', [])
    if not isinstance(rows, list) or len(rows) > MAX_POOL:
        raise ValueError('INVALID_RESEARCH_TECHNICAL_POOL')
    counts = Counter(row.get('ticker') for row in rows if isinstance(row, dict))
    metadata_counts = Counter(row['ticker'] for row in meta['candidates'])
    by_ticker = {row['ticker']: row for row in meta['candidates']}
    issuer_counts = Counter(row['issuer_id'] for row in meta['candidates'] if row['issuer_id'])
    sectors, exclusions, identities = defaultdict(list), [], []
    technical_complete = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('ticker'), str):
            raise ValueError('INVALID_RESEARCH_TECHNICAL_IDENTITY')
        ticker, technicals = row['ticker'], row.get('technicals', {})
        security = by_ticker.get(ticker)
        reasons = []
        identities.append({key: row[key] for key in ('ticker', 'technicals', 'technicals_as_of',
            'technicals_scope', 'technical_source', 'technical_provenance', 'source_url') if key in row})
        full = (isinstance(technicals, dict) and all(_number(technicals.get(k)) for k in TECHNICALS)
                and row.get('technical_source') == 'python' and isinstance(row.get('technical_provenance'), dict))
        if not full:
            reasons.append('INCOMPLETE_PYTHON_TECHNICALS')
        else:
            technical_complete += 1
        if counts[ticker] != 1 or metadata_counts[ticker] != 1:
            reasons.append('MISSING_OR_DUPLICATE_SECURITY_IDENTITY')
        if not security:
            reasons.append('SECURITY_METADATA_UNAVAILABLE')
        else:
            if any(not security[field] for field in ('issuer_id', 'sector', 'industry')):
                reasons.append('INCOMPLETE_SECURITY_METADATA')
            if security['security_type'] not in ('COMMON_STOCK', 'REIT'):
                reasons.append('INELIGIBLE_SECURITY_TYPE')
            if security['issuer_id'] and issuer_counts[security['issuer_id']] != 1:
                reasons.append('DUPLICATE_ISSUER')
            if (security['median_dollar_volume_20'] is None
                    or security['median_dollar_volume_20'] < MIN_LIQUIDITY_CAD):
                reasons.append('INSUFFICIENT_MEDIAN_DOLLAR_VOLUME_20')
        if meta['status'] == 'UNAVAILABLE':
            reasons.append('RESEARCH_UNIVERSE_UNAVAILABLE')
        if reasons:
            exclusions.append({'ticker': ticker, 'reasons': sorted(set(reasons))})
        else:
            sectors[security['sector']].append(security)
    for sector in sectors:
        sectors[sector].sort(key=lambda row: (-row['median_dollar_volume_20'], row['ticker']))
    selected = []
    for depth in range(max((len(items) for items in sectors.values()), default=0)):
        for sector in sorted(sectors):
            if depth < len(sectors[sector]) and len(selected) < MAX_SHORTLIST:
                selected.append(sectors[sector][depth])
    names = {row['ticker'] for row in selected}
    for items in sectors.values():
        exclusions.extend({'ticker': row['ticker'], 'reasons': ['OUTSIDE_FIXED_PRE_NEWS_SHORTLIST']}
                          for row in items if row['ticker'] not in names)
    source_requested = clean.get('coverage', {}).get('requested', len(rows))
    if type(source_requested) is not int or not len(rows) <= source_requested <= MAX_POOL:
        raise ValueError('INVALID_RESEARCH_SOURCE_COUNT')
    gaps = [] if len(selected) >= MIN_SHORTLIST else ['SHORTLIST_BELOW_30_COMPLETE_NAMES']
    result = {'mode': MODE, 'session': session, 'registration': REGISTRATION, 'adopted': False,
              'source_requested': source_requested, 'source_accepted': len(rows),
              'technical_complete': technical_complete, 'selected_count': len(selected),
              'tickers': [row['ticker'] for row in selected], 'rows': selected,
              'exclusions': sorted(exclusions, key=lambda row: row['ticker']), 'gaps': gaps,
              'input_sha256': hashlib.sha256(encode({'universe': meta,
                  'technical_inputs': identities, 'source_requested': source_requested}).encode()).hexdigest()}
    result['shortlist_sha256'] = hashlib.sha256(encode(result).encode()).hexdigest()
    return result


def validate_saved(saved, clean, universe, session):
    """A changed or padded shortlist cannot inherit a prior model receipt."""
    expected = select(clean, universe, session)
    if not isinstance(saved, dict) or saved != expected:
        raise ValueError('RESEARCH_SHORTLIST_RECEIPT_MISMATCH')
    return expected
