"""Pure, optional opening context for the unadopted expanded TSX research arm.

No acquisition, order, ranking, model call or persistence occurs here. The
allowlisted local contract is ``research_opening_snapshot.json`` with schema
version 1, an ET session, aware ``prepared_at`` and at most 150 ``rows``.
Each row supplies exact ticker/TSX/CAD identity, interval ``5m``, three bars
(``start/open/high/low/close/volume``), provider/source_url, and aware
``observed_at/published_at/retrieved_at``. Only bars starting 09:30, 09:35 and
09:40 are accepted. The 09:40 bar's close is the 09:45 *bar reference*.

``history`` contains the same bar-receipt contract for each of the immediately
preceding 20 completed TSX sessions. RVOL divides today's first-15-minute volume
by the arithmetic mean of those 20 first-15-minute volumes, never daily volume.
VWAP is a labelled five-minute typical-price/volume proxy, not trade-level VWAP.
An optional ``quote`` uses the existing raw ``quotes.validate_equity`` schema,
plus ``quote_retrieved_at``. A BBO is usable only during the actual 09:46 minute
and must itself be timestamped in that minute. It never replaces a bar.

Pass the validated ``tsx_universe.load_prepared`` result to authenticate
membership and sector. An absent/invalid universe leaves sector context missing;
untrusted sector strings in this snapshot are never used. All quantities are
descriptive SHADOW observations, not expected P&L, selection or a calibrated
probability. Current-time LLM diagnostics are not read or combined with them.
"""

from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import fmean
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from intraday_history import session_schedule
import quotes

ET = ZoneInfo('America/New_York')
MAX_ROWS = 150
MAX_BYTES = 10 * 1024 * 1024
HISTORY_SESSIONS = 20
MIN_SECTOR_PEERS = 2
TICKER = re.compile(r'^[A-Z][A-Z0-9.-]{0,14}\.TO$')
LABEL = 'SHADOW — descriptive opening context; no strategy adoption'


class InputError(ValueError):
    """A bounded contract reason, never arbitrary provider content."""


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise InputError('DUPLICATE_JSON_KEY')
        out[key] = value
    return out


def _aware(value):
    try:
        if not isinstance(value, (str, dt.datetime)):
            raise ValueError
        return quotes.stamp(value).astimezone(ET)
    except (TypeError, ValueError, OverflowError):
        raise InputError('INVALID_AWARE_CLOCK') from None


def _number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError('INVALID_OHLCV')
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise InputError('INVALID_OHLCV')
    return value


def _source(row):
    provider = row.get('provider')
    if not isinstance(provider, str) or not re.fullmatch(r'[A-Za-z0-9 ._-]{1,64}', provider):
        raise InputError('MISSING_SOURCE_IDENTITY')
    try:
        source = urlsplit(row.get('source_url', ''))
        if (source.scheme != 'https' or not source.hostname or source.username
                or source.password or source.query or source.fragment):
            raise ValueError
    except (TypeError, ValueError):
        raise InputError('INVALID_SOURCE_URL') from None


def _receipt(row, ticker, session, cutoff):
    if not isinstance(row, dict):
        raise InputError('INVALID_BAR_RECEIPT')
    if (row.get('ticker') != ticker or row.get('currency') != 'CAD'
            or row.get('exchange') != 'TSX' or row.get('session') != session):
        raise InputError('BAR_IDENTITY_OR_SESSION_MISMATCH')
    if row.get('interval') != '5m':
        raise InputError('WRONG_BAR_INTERVAL')
    _source(row)
    bars = row.get('bars')
    if not isinstance(bars, list) or len(bars) != 3:
        raise InputError('INCOMPLETE_OPENING_GRID')
    start = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(9, 30), ET)
    grid = [start + dt.timedelta(minutes=5 * i) for i in range(3)]
    values = []
    for raw, expected in zip(bars, grid):
        if not isinstance(raw, dict) or _aware(raw.get('start')) != expected:
            raise InputError('WRONG_OPENING_GRID_OR_LOOKAHEAD')
        o, h, l, c = [_number(raw.get(k), positive=True) for k in ('open', 'high', 'low', 'close')]
        v = _number(raw.get('volume'))
        if v < 0 or h < max(o, c) or l > min(o, c) or h < l:
            raise InputError('INVALID_OHLCV')
        values.append((o, h, l, c, v))
    observed, published, retrieved = [_aware(row.get(k)) for k in
                                     ('observed_at', 'published_at', 'retrieved_at')]
    completed = start + dt.timedelta(minutes=15)
    if not completed <= observed <= published <= retrieved <= cutoff:
        raise InputError('SOURCE_CLOCK_ORDER_OR_LOOKAHEAD')
    return values


def _prior_sessions(day):
    schedule = session_schedule((day-dt.timedelta(days=65)).isoformat(), day.isoformat(), 'TSX')
    sessions = [x.date() for x in schedule.index]
    if day not in sessions:
        raise InputError('NON_TRADING_SESSION')
    today = schedule.loc[day.isoformat()]
    if today['market_open'].tz_convert(ET).time() != dt.time(9, 30):
        raise InputError('NONSTANDARD_OPENING_SESSION')
    prior = [x.isoformat() for x in sessions if x < day][-HISTORY_SESSIONS:]
    if len(prior) != HISTORY_SESSIONS:
        raise InputError('TRADING_CALENDAR_INCOMPLETE')
    return prior


def _history_volume(row, ticker, prior, cutoff):
    history = row.get('history')
    if not isinstance(history, list) or len(history) != HISTORY_SESSIONS:
        raise InputError('RVOL_REQUIRES_20_PRIOR_OPENING_RECEIPTS')
    if [r.get('session') if isinstance(r, dict) else None for r in history] != prior:
        raise InputError('RVOL_NONCONSECUTIVE_OR_WRONG_SESSIONS')
    volumes = [sum(x[4] for x in _receipt(receipt, ticker, session, cutoff))
               for receipt, session in zip(history, prior)]
    denominator = fmean(volumes)
    if denominator <= 0:
        raise InputError('RVOL_ZERO_DENOMINATOR')
    return denominator


def _universe(value, session):
    if not isinstance(value, dict) or value.get('status') not in ('READY', 'PARTIAL') or value.get('session') != session:
        return {}, False
    candidates = value.get('candidates')
    if not isinstance(candidates, list) or len(candidates) > MAX_ROWS:
        return {}, False
    out = {}
    for row in candidates:
        if not isinstance(row, dict):
            return {}, False
        ticker, sector = row.get('ticker'), row.get('sector')
        if (not isinstance(ticker, str) or not TICKER.fullmatch(ticker) or ticker in out
                or not isinstance(sector, str) or not sector.strip() or len(sector) > 120):
            return {}, False
        out[ticker] = sector
    return out, bool(out)


def _quote(row, ticker, now, cutoff):
    absent = {'ticker': ticker, 'currency': 'CAD', 'status': 'UNAVAILABLE',
              'reason_code': 'MISSING_QUOTE', 'quote_time': None,
              'bid': None, 'ask': None, 'mark': None, 'spread_bps': None}
    if now.time().replace(second=0, microsecond=0) != dt.time(9, 46):
        return {**absent, 'reason_code': 'OUTSIDE_0946_DECISION_MINUTE'}
    raw = row.get('quote')
    validated = quotes.validate_equity(raw, ticker, now, currency='CAD', max_age=120)
    if validated.get('status') != 'OK':
        # A last-trade mark can be valid independently of BBO. This module does
        # not display it as an execution reference when the quote failed.
        return {**validated, 'mark': None}
    try:
        quoted = _aware(validated.get('quote_time'))
        retrieved = _aware(row.get('quote_retrieved_at'))
        if (quoted.date() != now.date() or quoted.time().replace(second=0, microsecond=0) != dt.time(9, 46)
                or not quoted <= retrieved <= cutoff):
            raise InputError('QUOTE_NOT_EXACT_0946_OR_LOOKAHEAD')
    except InputError as exc:
        return {**absent, 'reason_code': str(exc)}
    return validated


def _empty(session=None, reason='SNAPSHOT_UNAVAILABLE', **kw):
    return dict(status='UNAVAILABLE', shadow=True, adopted=False, label=LABEL,
                session=session, input_hash=None, rows=[],
                coverage=dict(requested=0, opening_valid=0, rvol_valid=0,
                              sector_relative_valid=0, quotes_valid=0),
                gaps=[reason], **kw)


def load_prepared(state, now, universe=None):
    """Read bounded local receipts; healthy row sections survive sibling failures."""
    try:
        now = _aware(now)
    except InputError as exc:
        return _empty(reason=str(exc))
    session = now.date().isoformat()
    start = dt.datetime.combine(now.date(), dt.time(9, 46), ET)
    cutoff = min(now, start+dt.timedelta(minutes=1)-dt.timedelta(microseconds=1))
    if now < start:
        return _empty(session, '0946_PUBLICATION_WINDOW_NOT_REACHED')
    path = Path(state) / 'research_opening_snapshot.json'
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_BYTES+1)
    except FileNotFoundError:
        return _empty(session)
    except OSError as exc:
        return _empty(session, 'SNAPSHOT_READ_FAILED', error_class=type(exc).__name__)
    out = _empty(session)
    if len(raw) > MAX_BYTES:
        out['gaps'] = ['SNAPSHOT_SIZE_LIMIT']
        return out
    out['input_hash'] = hashlib.sha256(raw).hexdigest()
    try:
        document = json.loads(raw, object_pairs_hook=_object)
        if (not isinstance(document, dict) or type(document.get('schema_version')) is not int
                or document.get('schema_version') != 1):
            raise InputError('INVALID_SNAPSHOT_SCHEMA')
        if document.get('session') != session:
            raise InputError('WRONG_SNAPSHOT_SESSION')
        prepared = _aware(document.get('prepared_at'))
        if not start <= prepared <= cutoff:
            raise InputError('SNAPSHOT_CLOCK_OUTSIDE_0946_CUTOFF')
        rows = document.get('rows')
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise InputError('INVALID_ROWS_OR_POOL_LIMIT')
        prior = _prior_sessions(now.date())
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        out['gaps'] = [str(exc) if isinstance(exc, InputError) else 'INVALID_SNAPSHOT_PAYLOAD']
        out['error_class'] = type(exc).__name__
        return out
    except Exception as exc:
        out['gaps'] = ['TRADING_CALENDAR_UNAVAILABLE']
        out['error_class'] = type(exc).__name__
        return out
    out.update(prepared_at=prepared.isoformat(), cutoff=cutoff.isoformat(), gaps=[])
    sectors, universe_ok = _universe(universe, session)
    if not universe_ok:
        out['gaps'].append('VALIDATED_SECTOR_UNIVERSE_UNAVAILABLE')
    symbols = [r.get('ticker') if isinstance(r, dict) and isinstance(r.get('ticker'), str) else None for r in rows]
    duplicates = {t for t, n in Counter(symbols).items() if t and n > 1}
    for source, ticker in zip(rows, symbols):
        item = dict(ticker=ticker if isinstance(ticker, str) and TICKER.fullmatch(ticker) else None,
                    sector=sectors.get(ticker), status='UNAVAILABLE', gaps=[],
                    opening_return_pct=None, orb_high=None, orb_low=None,
                    vwap_5m_proxy=None, vwap_label='Five-minute typical-price/volume proxy',
                    opening_volume=None, rvol_15m=None, rvol_sessions=0,
                    rvol_denominator_mean_15m_volume=None,
                    sector_relative_return_pct=None, sector_peer_count=0,
                    sector_peer_target_count=0, sector_basis='Equal mean of available valid sector peers, excluding self',
                    bar_reference_time=None, bar_reference_price=None,
                    quote={'status': 'UNAVAILABLE', 'reason_code': 'OPENING_RECEIPT_UNAVAILABLE',
                           'quote_time': None, 'bid': None, 'ask': None, 'mark': None, 'spread_bps': None})
        out['rows'].append(item)
        try:
            if item['ticker'] is None:
                raise InputError('INVALID_TSX_TICKER')
            if ticker in duplicates:
                raise InputError('DUPLICATE_TICKER')
            if universe_ok and ticker not in sectors:
                raise InputError('TICKER_OUTSIDE_VALIDATED_UNIVERSE')
            values = _receipt(source, ticker, session, min(cutoff, prepared))
            volume = sum(v[4] for v in values)
            if volume <= 0:
                raise InputError('NO_OPENING_VOLUME')
            item.update(opening_return_pct=(values[-1][3]/values[0][0]-1)*100,
                        orb_high=max(v[1] for v in values), orb_low=min(v[2] for v in values),
                        vwap_5m_proxy=sum(((v[1]+v[2]+v[3])/3)*v[4] for v in values)/volume,
                        opening_volume=volume, bar_reference_price=values[-1][3],
                        bar_reference_time=dt.datetime.combine(now.date(), dt.time(9, 45), ET).isoformat(),
                        source_url=source['source_url'], provider=source['provider'])
        except (InputError, ValueError, TypeError, KeyError) as exc:
            item['gaps'].append(str(exc) if isinstance(exc, InputError) else 'INVALID_BAR_RECEIPT')
            continue
        try:
            denominator = _history_volume(source, ticker, prior, min(cutoff, prepared))
            item.update(rvol_15m=volume/denominator, rvol_sessions=HISTORY_SESSIONS,
                        rvol_denominator_mean_15m_volume=denominator)
        except (InputError, ValueError, TypeError, KeyError) as exc:
            item['gaps'].append(str(exc) if isinstance(exc, InputError) else 'INVALID_RVOL_RECEIPT')
        item['quote'] = _quote(source, ticker, now, min(cutoff, prepared))
        if item['quote']['status'] != 'OK':
            item['gaps'].append(item['quote']['reason_code'])
        if not item['sector']:
            item['gaps'].append('VALIDATED_SECTOR_UNAVAILABLE')
    for item in out['rows']:
        if item['opening_return_pct'] is None:
            continue
        if item['sector']:
            peers = [r for r in out['rows'] if r['ticker'] != item['ticker']
                     and r['sector'] == item['sector'] and r['opening_return_pct'] is not None]
            item['sector_peer_count'] = len(peers)
            item['sector_peer_target_count'] = sum(t != item['ticker'] and s == item['sector'] for t, s in sectors.items())
            if len(peers) >= MIN_SECTOR_PEERS:
                item['sector_relative_return_pct'] = item['opening_return_pct']-fmean(r['opening_return_pct'] for r in peers)
            else:
                item['gaps'].append('INSUFFICIENT_VALID_SECTOR_PEERS')
        item['status'] = 'PARTIAL' if item['gaps'] else 'READY'
    coverage = out['coverage']
    coverage.update(requested=len(rows), opening_valid=sum(r['opening_return_pct'] is not None for r in out['rows']),
                    rvol_valid=sum(r['rvol_15m'] is not None for r in out['rows']),
                    sector_relative_valid=sum(r['sector_relative_return_pct'] is not None for r in out['rows']),
                    quotes_valid=sum((r['quote'] or {}).get('status') == 'OK' for r in out['rows']))
    if coverage['opening_valid']:
        out['status'] = 'READY' if not out['gaps'] and all(r['status'] == 'READY' for r in out['rows']) else 'PARTIAL'
    if not rows:
        out['gaps'].append('EMPTY_STAGED_INPUT')
    return out
