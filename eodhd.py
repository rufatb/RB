"""Bounded EODHD historical/reference access; deliberately NOT a live adapter.

Credentials go only to the fixed HTTPS API host, never to logs or redirects.
No automatic retry, exchange substitution, daily-to-intraday conversion, quote
fallback or strategy promotion is supported. See PREREGISTER_day97.md.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal
import requests

ET = ZoneInfo('America/New_York')
BASE = 'https://eodhd.com/api/'


class DataGap(ValueError):
    """Sanitized, actionable provider or validation failure."""


def credential():
    token = os.environ.get('RB_EODHD_API_KEY', '').strip()
    if not token:
        path = os.environ.get('RB_EODHD_API_KEY_FILE')
        if not path:
            state = os.environ.get('RB_STATE_DIR')
            path = str(Path(state)/'secrets'/'eodhd_api_key') if state else None
        if path:
            try:
                token = Path(path).read_text().strip()
            except OSError:
                raise DataGap('CREDENTIAL_UNAVAILABLE') from None
    if not token or any(c.isspace() for c in token):
        raise DataGap('CREDENTIAL_UNAVAILABLE')
    return token


def aware(value):
    try:
        result = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        raise DataGap('INVALID_TIMESTAMP') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise DataGap('NAIVE_TIMESTAMP')
    return result.astimezone(ET)


class Client:
    def __init__(self, token=None, *, transport=None, max_credits=15,
                 max_requests=8, timeout=5, deadline_seconds=40):
        self._token = token or credential()
        self._get = transport or requests.get
        self.max_credits, self.max_requests = max_credits, max_requests
        self.timeout = timeout
        self.deadline = time.monotonic() + deadline_seconds
        self.credits = self.requests = 0
        self.blocked = set()
        self.remaining = None

    def get(self, endpoint, *, params=None, cost=1):
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', endpoint) or '..' in endpoint:
            raise DataGap('INVALID_ENDPOINT')
        family = endpoint.split('/')[0]
        if '*' in self.blocked or family in self.blocked:
            raise DataGap('CIRCUIT_OPEN')
        if cost < 1 or self.credits + cost > self.max_credits or self.requests >= self.max_requests:
            raise DataGap('LOCAL_REQUEST_BUDGET')
        if self.remaining is not None and cost > self.remaining:
            raise DataGap('PROVIDER_CREDIT_BUDGET')
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise DataGap('ACQUISITION_DEADLINE')
        self.credits += cost
        self.requests += 1
        if self.remaining is not None:
            self.remaining -= cost
        try:
            response = self._get(BASE+endpoint,
                params={**(params or {}), 'api_token':self._token, 'fmt':'json'},
                timeout=min(self.timeout, seconds), allow_redirects=False)
        except requests.RequestException:
            self.blocked.add('*')
            raise DataGap('TRANSPORT_UNAVAILABLE — entitlement not tested') from None
        status = response.status_code
        if status in (401, 429):
            self.blocked.add('*')
        elif status == 403:
            self.blocked.add(family)
        if not 200 <= status < 300:
            tag = {401:'AUTH_REJECTED',403:'NOT_ENTITLED',429:'RATE_LIMITED'}.get(status, 'HTTP_ERROR')
            raise DataGap(f'{tag} HTTP {status}')
        try:
            value = response.json()
        except ValueError:
            raise DataGap('INVALID_JSON_RESPONSE') from None
        if isinstance(value, dict) and any(k in value for k in ('error','errors','message')):
            # Error bodies can echo request tokens. Never serialize them.
            raise DataGap('PROVIDER_ERROR_RESPONSE')
        return value

    def limits(self, now):
        data = self.get('user')
        if not isinstance(data, dict):
            raise DataGap('INVALID_ACCOUNT_RESPONSE')
        result = {}
        for field in ('dailyRateLimit','apiRequests','extraLimit'):
            value = data.get(field)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
                    raise DataGap('INVALID_ACCOUNT_LIMIT')
                result[field] = int(value)
        day = data.get('apiRequestsDate')
        if day is not None:
            try:
                day = dt.date.fromisoformat(str(day))
            except ValueError:
                raise DataGap('INVALID_USAGE_DATE') from None
            utc_day = now.astimezone(dt.timezone.utc).date()
            if day > utc_day:
                raise DataGap('FUTURE_USAGE_DATE')
            result['apiRequestsDate'] = day.isoformat()
            if 'dailyRateLimit' in result and 'apiRequests' in result:
                used = result['apiRequests'] if day == utc_day else 0
                # Do not consume purchased extra credits automatically.
                self.remaining = max(0, result['dailyRateLimit'] - used)
        return result


def identity(catalog, ticker):
    if not ticker.endswith('.TO') or not re.fullmatch(r'[A-Z0-9-]+\.TO', ticker):
        raise DataGap('UNSUPPORTED_IDENTITY — Canadian .TO only')
    if not isinstance(catalog, list):
        raise DataGap('INVALID_CATALOG')
    matches = [r for r in catalog if isinstance(r,dict) and r.get('Code') == ticker[:-3]]
    if len(matches) != 1:
        raise DataGap('MISSING_OR_DUPLICATE_IDENTITY')
    row = matches[0]
    if row.get('Currency') != 'CAD' or row.get('Country') != 'Canada' or row.get('Exchange') not in ('TO','TSX','Toronto'):
        raise DataGap('EXCHANGE_OR_CURRENCY_MISMATCH')
    if row.get('Type') not in ('Common Stock','ETF') or not row.get('Name'):
        raise DataGap('UNVERIFIED_INSTRUMENT_TYPE')
    return {'ticker':ticker, 'currency':'CAD', 'exchange':'TSX', 'name':row['Name']}


def schedule(start, end):
    return mcal.get_calendar('TSX').schedule(start_date=start, end_date=end)


def previous_session(now):
    now = aware(now)
    dates = schedule(now.date()-dt.timedelta(days=14), now.date()-dt.timedelta(days=1))
    if dates.empty:
        raise DataGap('PREVIOUS_SESSION_UNAVAILABLE')
    return dates.index[-1].date()


def number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
        raise DataGap('NONFINITE_OR_MISSING_OHLCV')
    if value < 0 or (positive and value == 0):
        raise DataGap('NONPOSITIVE_PRICE_OR_NEGATIVE_VOLUME')
    return value


def ohlcv(row):
    if not isinstance(row, dict):
        raise DataGap('INVALID_BAR')
    values = [number(row.get(k), positive=k!='volume') for k in ('open','high','low','close','volume')]
    o,h,l,c,v = values
    if l > min(o,c) or h < max(o,c) or l > h:
        raise DataGap('INCONSISTENT_OHLC')
    if int(v) != v:
        raise DataGap('NONINTEGER_SHARE_VOLUME')
    return values


def daily_reference(rows, instrument, now):
    if instrument.get('currency') != 'CAD' or instrument.get('exchange') != 'TSX' or not instrument.get('ticker','').endswith('.TO'):
        raise DataGap('UNVERIFIED_INSTRUMENT')
    expected = previous_session(now).isoformat()
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0],dict) or rows[0].get('date') != expected:
        raise DataGap('MISSING_EXACT_PRIOR_SESSION')
    _,_,_,close,_ = ohlcv(rows[0])
    return {**instrument, 'session':expected, 'close':close,
            'retrieved_at':aware(now).isoformat(), 'provider':'EODHD',
            'provider_endpoint':'/api/eod/'+instrument['ticker'],
            'source_url':BASE+'eod/'+instrument['ticker'],
            'label':'Completed prior-session reference, not live or executable'}


def five_minute_history(rows, instrument, now, start, end):
    """Certify complete regular-session grids, not partial samples or live data."""
    now = aware(now)
    if instrument.get('currency') != 'CAD' or instrument.get('exchange') != 'TSX' or not instrument.get('ticker','').endswith('.TO'):
        raise DataGap('UNVERIFIED_INSTRUMENT')
    if end >= now.date() or start > end:
        raise DataGap('ONLY_COMPLETED_PRIOR_SESSIONS')
    if not isinstance(rows, list) or not rows:
        raise DataGap('EMPTY_INTRADAY_HISTORY')
    times, values = [], []
    for row in rows:
        if not isinstance(row,dict):
            raise DataGap('INVALID_BAR')
        ts = number(row.get('timestamp'), positive=True)
        try:
            stamp = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise DataGap('INVALID_BAR_TIMESTAMP') from None
        if not start <= stamp.astimezone(ET).date() <= end or ts % 300:
            raise DataGap('WRONG_RANGE_OR_NON_FIVE_MINUTE_TIMESTAMP')
        if row.get('datetime') is not None and row['datetime'] != stamp.strftime('%Y-%m-%d %H:%M:%S'):
            raise DataGap('CONFLICTING_BAR_TIMESTAMPS')
        times.append(stamp)
        values.append(ohlcv(row))
    idx = pd.DatetimeIndex(times)
    if idx.has_duplicates or not idx.is_monotonic_increasing:
        raise DataGap('DUPLICATE_OR_UNORDERED_BARS')
    frame = pd.DataFrame(values, index=idx, columns=['Open','High','Low','Close','Volume'])
    cal = schedule(start,end)
    if cal.empty:
        raise DataGap('NO_EXCHANGE_SESSIONS')
    expected = pd.DatetimeIndex([])
    for _, day in cal.iterrows():
        grid = pd.date_range(day['market_open'],day['market_close'],freq='5min',inclusive='left')
        expected = expected.union(grid)
    # Extended hours may exist; regular-session completeness must be exact.
    regular = frame.reindex(expected)
    if regular.isna().any().any():
        raise DataGap('INCOMPLETE_REGULAR_SESSION_GRID')
    regular.index = pd.DatetimeIndex(regular.index).tz_convert(ET)
    return regular


def load_prepared(state, now):
    """Small validated summary for brief.compute; never performs network I/O."""
    path = Path(state)/'eodhd_status.json'
    if not path.exists():
        return {'status':'NOT CONFIGURED', 'reference_count':0, 'intraday_status':'NOT TESTED',
                'note':'Optional historical provider; baseline unchanged.'}
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw,dict):
            raise DataGap('INVALID_PREPARED_EVIDENCE')
        checked = aware(raw['checked_at'])
        now = aware(now)
        if raw.get('schema_version') != 1 or checked > now or checked.date() != now.date():
            raise DataGap('STALE_OR_FUTURE_PROVIDER_CHECK')
        refs = raw.get('references',{})
        if not isinstance(refs,dict):
            raise DataGap('INVALID_PREPARED_REFERENCES')
        valid = 0
        for ticker, ref in refs.items():
            if not isinstance(ref,dict):
                raise DataGap('INVALID_PREPARED_REFERENCE')
            if ref['ticker'] != ticker or ref['currency'] != 'CAD' or ref['session'] != previous_session(now).isoformat():
                raise DataGap('INVALID_PREPARED_REFERENCE')
            number(ref['close'], positive=True)
            if aware(ref['retrieved_at']) > now:
                raise DataGap('FUTURE_PREPARED_REFERENCE')
            if ref.get('source_url') != BASE+'eod/'+ticker or ref.get('provider_endpoint') != '/api/eod/'+ticker:
                raise DataGap('INVALID_REFERENCE_PROVENANCE')
            valid += 1
        status = raw['status']
        if status not in ('PARTIAL','TRANSPORT BLOCKED','REFERENCES READY — HISTORICAL RESEARCH ONLY'):
            raise DataGap('INVALID_PROVIDER_STATUS')
        intra = raw.get('intraday',{}).get('status','NOT TESTED')
        allowed = ('NOT TESTED','SAMPLE VALIDATED — NOT UNIVERSE/HISTORY CERTIFIED',
                   'NOT_ENTITLED','AUTH_REJECTED','RATE_LIMITED','CIRCUIT_OPEN','HTTP_ERROR',
                   'TRANSPORT_UNAVAILABLE','INVALID_','INCOMPLETE_','EMPTY_',
                   'WRONG_','DUPLICATE_','CONFLICTING_','NONFINITE_','NONPOSITIVE_',
                   'NONINTEGER_','INCONSISTENT_','ONLY_COMPLETED_',
                   'LOCAL_REQUEST_BUDGET','PROVIDER_CREDIT_BUDGET','ACQUISITION_DEADLINE','PROVIDER_ERROR_RESPONSE')
        if not isinstance(intra,str) or not intra.startswith(allowed) or len(intra)>160:
            raise DataGap('INVALID_INTRADAY_STATUS')
        return {'status':status, 'reference_count':valid,
                'intraday_status':intra,
                'checked_at':checked.isoformat(),
                'note':'Historical qualification only; no live quote or accuracy improvement certified.'}
    except (KeyError, TypeError, ValueError, OSError):
        return {'status':'UNAVAILABLE', 'reference_count':0, 'intraday_status':'NOT CERTIFIED',
                'note':'Prepared provider evidence is stale, missing fields or invalid; baseline unchanged.'}
