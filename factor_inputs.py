"""Point-in-time public inputs for staged DeepSeek analysis; never acquire data.

Indicators are deterministic context, not win probabilities. The default pool is
exactly the configured scan universe, not a purported 500-stock discovery. Data
and evidence gaps live outside the candidate records sent to the LLM.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import math
import re
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qsl
from zoneinfo import ZoneInfo

import pandas as pd

import deepseek_policy as policy
from intraday_history import completed_history, session_schedule
from metrics import macd, rsi, vwap

ET = ZoneInfo('America/New_York')
TECHNICAL_KEYS = frozenset(('r0', 'gap', 'vp', 'quant_probability', 'vwap', 'rsi',
    'macd', 'macd_signal', 'macd_hist', 'orb_high', 'orb_low', 'rvol', 'last',
    'price', 'open', 'volume'))
TICKER = re.compile(r'[A-Z0-9][A-Z0-9.\-]{0,19}\Z')
SENSITIVE = re.compile(r'api.?key|token|secret|password|signature|credential|authorization', re.I)


def _stamp(value):
    try:
        out = pd.Timestamp(value)
    except (ValueError, TypeError):
        raise ValueError('INVALID_TIMESTAMP') from None
    if pd.isna(out) or out.tzinfo is None:
        raise ValueError('AWARE_TIMESTAMP_REQUIRED')
    return out.tz_convert(ET)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _url(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError('INVALID_PUBLIC_SOURCE_URL')
    try:
        parts = urlsplit(value)
        host = parts.hostname or ''
        if (parts.scheme != 'https' or not host or '.' not in host or parts.username
                or parts.password or parts.fragment or parts.port not in (None, 443)
                or host.lower().endswith(('.localhost', '.local', '.internal'))
                or any(k.lower() == 'key' or SENSITIVE.search(k) for k, _ in parse_qsl(parts.query))):
            raise ValueError('INVALID_PUBLIC_SOURCE_URL')
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError('INVALID_PUBLIC_SOURCE_URL')
        except ValueError as exc:
            if str(exc) == 'INVALID_PUBLIC_SOURCE_URL':
                raise
        return value
    except (ValueError, TypeError):
        raise ValueError('INVALID_PUBLIC_SOURCE_URL') from None


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def _loads(raw):
    if len(raw.encode('utf-8')) > policy.MAX_INPUT_BYTES:
        raise ValueError('INPUT_SIZE_LIMIT')
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def _read(path):
    if path.stat().st_size > policy.MAX_INPUT_BYTES:
        raise ValueError('INPUT_SIZE_LIMIT')
    return _loads(path.read_text(encoding='utf-8'))


def _previous_close(now):
    schedule = session_schedule((now.date()-dt.timedelta(days=14)).isoformat(),
                                (now.date()-dt.timedelta(days=1)).isoformat())
    if schedule.empty:
        raise ValueError('PRIOR_EXCHANGE_SESSION_UNAVAILABLE')
    return _stamp(schedule.iloc[-1]['market_close'])


def _blank(now, reason=None):
    return {'as_of': now.isoformat(), 'candidates': [], 'macro': {},
            'coverage': {'requested': 0, 'accepted': 0, 'complete': 0,
                         'complete_tickers': [], 'macro_complete': False,
                         'macro_scope': 'Dated references since the previous TSX session close; not live executable quotes.',
                         'target_capacity': policy.MAX_CANDIDATES},
            'gaps': [reason] if reason else [], 'candidate_gaps': {}}


def _evidence(items, field, now, gaps, cutoff):
    if not isinstance(items, list):
        gaps.append('INVALID_'+field.upper())
        return []
    maximum = policy.MAX_NEWS_PER_CANDIDATE if field == 'headlines' else policy.MAX_TAGS_PER_CANDIDATE
    if len(items) > maximum:
        gaps.append(field.upper()+'_LIMIT_EXCEEDED')
    output = []
    text_field = 'title' if field == 'headlines' else 'tag'
    for item in items[:maximum]:
        try:
            if not isinstance(item, dict):
                raise ValueError('INVALID_EVIDENCE_OBJECT')
            text = item[text_field]
            if (not isinstance(text, str) or not text.strip() or
                    len(text) > policy.MAX_TITLE_CHARS or any(ord(c) < 32 for c in text)):
                raise ValueError('INVALID_EVIDENCE_TEXT')
            date = _stamp(item['published_at'])
            if date > cutoff:
                raise ValueError('FUTURE_EVIDENCE')
            if now-date > pd.Timedelta(hours=policy.MAX_NEWS_AGE_HOURS):
                raise ValueError('STALE_EVIDENCE')
            output.append({text_field: text.strip(), 'source_url': _url(item['source_url']),
                           'published_at': date.isoformat()})
        except (KeyError, TypeError, ValueError) as exc:
            # Never echo rejected user/provider values (which may include secrets).
            reason = str(exc) if isinstance(exc, ValueError) else 'MISSING_EVIDENCE_FIELDS'
            gaps.append(field.upper()+':'+reason[:80])
    return output


def validate_payload(payload, now):
    """Sanitize a staged pool; retain independent facts and explicit coverage.

    Supplied technicals require a declared Python computation and auditable input
    hash. That declaration is NOT independent verification of upstream execution.
    Cache-built records are identified separately by their computation identifier.
    Unknown fields never pass through to the provider.
    """
    now = _stamp(now)
    output = _blank(now)
    if not isinstance(payload, dict):
        return _blank(now, 'INVALID_INPUT_OBJECT')
    try:
        as_of = _stamp(payload['as_of'])
        if as_of > now:
            raise ValueError('FUTURE_SNAPSHOT')
        if now-as_of > pd.Timedelta(hours=policy.MAX_SNAPSHOT_AGE_HOURS):
            raise ValueError('STALE_SNAPSHOT')
        candidates = payload['candidates']
        if not isinstance(candidates, list):
            raise ValueError('INVALID_CANDIDATE_POOL')
        if len(candidates) > policy.MAX_CANDIDATES:
            raise ValueError('CANDIDATE_LIMIT_EXCEEDED')
    except (KeyError, TypeError, ValueError) as exc:
        return _blank(now, str(exc) if isinstance(exc, ValueError) else 'MISSING_SNAPSHOT_FIELDS')
    output['as_of'] = as_of.isoformat()
    output['coverage']['requested'] = len(candidates)
    # Resolve the calendar once for the complete pool, not once per ticker.
    try:
        prior_close = _previous_close(now)
    except Exception:
        prior_close = None
        output['gaps'].append('PRIOR_EXCHANGE_SESSION_UNAVAILABLE')
    supplied_macro = payload.get('macro', {})
    if not isinstance(supplied_macro, dict):
        supplied_macro = {}
    for name in policy.MACRO_KEYS:
        try:
            item = supplied_macro[name]
            if not isinstance(item, dict) or not _number(item.get('value')) or item['value'] <= 0:
                raise ValueError('INVALID_MACRO_VALUE')
            observed = _stamp(item['as_of'])
            if observed > as_of:
                raise ValueError('FUTURE_MACRO')
            # A cash-index close is necessarily older than six hours before
            # the next open. Its exchange-session date, not wall-clock age,
            # governs dated macro context; this never certifies a live quote.
            if prior_close is None:
                raise ValueError('PRIOR_EXCHANGE_SESSION_UNAVAILABLE')
            if observed < prior_close:
                raise ValueError('STALE_MACRO')
            clean = {'value': float(item['value']), 'as_of': observed.isoformat(),
                     'source_url': _url(item['source_url'])}
            if 'change_pct' in item:
                if not _number(item['change_pct']):
                    raise ValueError('INVALID_MACRO_CHANGE')
                clean['change_pct'] = float(item['change_pct'])
            output['macro'][name] = clean
        except (KeyError, TypeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'MISSING_MACRO'
            output['gaps'].append(name.upper()+':'+reason[:80])
    macro_complete = len(output['macro']) == len(policy.MACRO_KEYS)
    output['coverage']['macro_complete'] = macro_complete
    counts = {}
    for item in candidates:
        if isinstance(item, dict) and isinstance(item.get('ticker'), str):
            counts[item['ticker']] = counts.get(item['ticker'], 0)+1
    for item in candidates:
        if not isinstance(item, dict) or not isinstance(item.get('ticker'), str) or not TICKER.fullmatch(item['ticker']):
            output['gaps'].append('INVALID_CANDIDATE_TICKER')
            continue
        ticker = item['ticker']
        gaps = []
        if counts[ticker] != 1:
            output['candidate_gaps'][ticker] = ['DUPLICATE_CANDIDATE']
            continue
        clean = {'ticker': ticker}
        try:
            scope = item['technicals_scope']
            observed = _stamp(item['technicals_as_of'])
            if observed > as_of:
                raise ValueError('FUTURE_TECHNICALS')
            if not isinstance(scope, str) or len(scope) > 160:
                raise ValueError('INVALID_TECHNICAL_SCOPE')
            if scope.startswith('previous_completed_session'):
                if prior_close is None:
                    raise ValueError('PRIOR_EXCHANGE_SESSION_UNAVAILABLE')
                if observed != prior_close:
                    raise ValueError('STALE_OR_WRONG_PREVIOUS_SESSION_TECHNICALS')
            elif scope == 'current_session':
                if observed.date() != now.date() or now-observed > pd.Timedelta(hours=policy.MAX_SNAPSHOT_AGE_HOURS):
                    raise ValueError('STALE_TECHNICALS')
            else:
                raise ValueError('UNSUPPORTED_TECHNICAL_SCOPE')
            source = _url(item['source_url'])
            if item.get('technical_source') != 'python':
                raise ValueError('PYTHON_TECHNICAL_DECLARATION_REQUIRED')
            provenance = item['technical_provenance']
            if not isinstance(provenance, dict):
                raise ValueError('INVALID_TECHNICAL_PROVENANCE')
            digest = provenance['input_sha256']
            computation = provenance['computation']
            computed = _stamp(provenance['computed_at'])
            if (not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)
                    or not isinstance(computation, str) or not computation.strip()
                    or len(computation) > 120 or computed > as_of or computed < observed
                    or _url(provenance['source_url']) != source):
                raise ValueError('INVALID_TECHNICAL_PROVENANCE')
            technicals = item['technicals']
            if not isinstance(technicals, dict) or not technicals:
                raise ValueError('MISSING_TECHNICALS')
            clean_technicals = {}
            for key, value in technicals.items():
                if key not in TECHNICAL_KEYS:
                    gaps.append('UNKNOWN_TECHNICAL_FIELD')
                    continue
                if value is None:
                    clean_technicals[key] = None
                    gaps.append('TECHNICAL_UNAVAILABLE:'+key)
                    continue
                if not _number(value):
                    raise ValueError('NONFINITE_OR_NONNUMERIC_TECHNICAL')
                if ((key == 'quant_probability' and not 0 <= value <= 1)
                        or (key == 'rsi' and not 0 <= value <= 100)
                        or (key in ('price', 'last', 'open', 'vwap', 'orb_high', 'orb_low') and value <= 0)
                        or (key in ('volume', 'rvol', 'vp') and value < 0)):
                    raise ValueError('OUT_OF_RANGE_TECHNICAL')
                clean_technicals[key] = float(value)
            for required in ('vwap', 'rsi', 'macd', 'macd_signal', 'macd_hist', 'orb_high', 'orb_low', 'rvol'):
                if required not in clean_technicals:
                    gaps.append('TECHNICAL_MISSING:'+required)
            if not any(v is not None for v in clean_technicals.values()):
                raise ValueError('NO_USABLE_TECHNICALS')
            if (clean_technicals.get('orb_high') is not None and clean_technicals.get('orb_low') is not None
                    and clean_technicals['orb_high'] < clean_technicals['orb_low']):
                raise ValueError('INCONSISTENT_OPENING_RANGE')
            clean.update(technicals=clean_technicals, technicals_as_of=observed.isoformat(),
                         technicals_scope=scope, source_url=source, technical_source='python',
                         technical_provenance={'input_sha256': digest, 'computation': computation,
                             'computed_at': computed.isoformat(), 'source_url': source})
        except (KeyError, TypeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'MISSING_TECHNICAL_FIELDS'
            gaps.append(reason[:80])
            clean['technicals'] = {}
        clean['headlines'] = _evidence(item.get('headlines', []), 'headlines', now, gaps, as_of)
        clean['catalyst_tags'] = _evidence(item.get('catalyst_tags', []), 'catalyst_tags', now, gaps, as_of)
        if not clean['headlines'] and not clean['catalyst_tags']:
            gaps.append('NO_CURRENT_CATALYST_EVIDENCE')
        if not macro_complete:
            gaps.append('INCOMPLETE_MACRO')
        output['candidates'].append(clean)
        output['candidate_gaps'][ticker] = sorted(set(gaps))
        if not gaps:
            output['coverage']['complete_tickers'].append(ticker)
    output['coverage']['accepted'] = len(output['candidates'])
    output['coverage']['complete'] = len(output['coverage']['complete_tickers'])
    output['gaps'] = list(dict.fromkeys(output['gaps']))
    return output


def _from_cache(ticker, directory, manifest, cfg, now):
    from bar_cache import key
    path = directory/key(ticker)
    raw = path.read_bytes()
    if len(raw) > policy.MAX_INPUT_BYTES:
        raise ValueError('CACHE_INPUT_SIZE_LIMIT')
    item = _loads(raw.decode('utf-8'))
    if item.get('ticker') != ticker or item.get('session') != now.date().isoformat():
        raise ValueError('CACHE_IDENTITY_MISMATCH')
    encoded = _loads(item['frame']) if isinstance(item.get('frame'), str) else item.get('frame')
    if not isinstance(encoded, dict) or not isinstance(encoded.get('index'), list):
        raise ValueError('INVALID_CACHE_FRAME')
    # pd.to_datetime(utc=True) would otherwise silently grant naive input a UTC zone.
    for value in encoded['index']:
        _stamp(value)
    frame = pd.DataFrame(encoded['data'], columns=encoded['columns'],
                         index=pd.to_datetime(encoded['index'], utc=True).tz_convert(cfg.get('exchange_tz', str(ET))))
    validated = completed_history(frame, ticker, now, timezone=cfg.get('exchange_tz', str(ET)))
    rows = validated['rows']
    if not rows or validated['prior_close'] is None or rows[-1]['date'] != str(_previous_close(now).date()):
        reasons = [entry['reason'] for entry in validated['diagnostics']['exclusions']
                   if entry['session'] == str(_previous_close(now).date())]
        reason = reasons[-1] if reasons else 'COMPLETE_PREVIOUS_SESSION_UNAVAILABLE'
        raise ValueError('CACHE_PRIOR_SESSION:'+reason)
    accepted = {row['date'] for row in rows}
    # Momentum warm-up must be consecutive complete exchange sessions, not a
    # concatenation across invalid/missing days. Keep the valid contiguous tail.
    schedule = session_schedule(rows[0]['date'], rows[-1]['date'])
    contiguous = []
    for day in reversed(schedule.index):
        if str(day.date()) not in accepted:
            break
        contiguous.append(str(day.date()))
    contiguous.reverse()
    regular = frame[(frame.index.date == _previous_close(now).date()) &
                    (frame.index.time >= dt.time(9, 30)) & (frame.index.time < dt.time(16))]
    daily_closes = pd.Series([float(frame[(frame.index.date == dt.date.fromisoformat(day)) &
                                        (frame.index.time == dt.time(15, 55))]['Close'].iloc[0])
                              for day in contiguous], dtype=float)
    daily_volumes = [float(frame[(frame.index.date == dt.date.fromisoformat(day)) &
                                  (frame.index.time >= dt.time(9, 30)) &
                                  (frame.index.time < dt.time(16))]['Volume'].sum())
                     for day in contiguous]
    latest = rows[-1]
    prior_rows = [row for row in rows[:-1] if row['date'] in set(contiguous)]
    v15_prior = [row['v15'] for row in prior_rows[-20:]]
    vp = latest['v15']/(sum(v15_prior)/20) if len(v15_prior) == 20 and sum(v15_prior) > 0 else None
    adv_prior = daily_volumes[-21:-1]
    rvol = daily_volumes[-1]/(sum(adv_prior)/20) if len(adv_prior) == 20 and sum(adv_prior) > 0 else None
    momentum = macd(daily_closes)
    source = 'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker, safe='')+'?interval=5m&range=60d'
    technicals = {'r0': latest['r0'], 'gap': latest['gap'], 'vp': vp,
                 'vwap': vwap(regular, None)['vwap'], 'rsi': rsi(daily_closes),
                 'macd': momentum['macd'], 'macd_signal': momentum['signal'], 'macd_hist': momentum['hist'],
                 'orb_high': float(regular.iloc[:3]['High'].max()),
                 'orb_low': float(regular.iloc[:3]['Low'].min()), 'rvol': rvol,
                 'last': float(regular['Close'].iloc[-1]), 'open': float(regular['Open'].iloc[0]),
                 'volume': float(regular['Volume'].sum())}
    diagnostics = []
    if any(day >= now.date() for day in frame.index.date):
        diagnostics.append('CACHE_CURRENT_OR_FUTURE_BARS_IGNORED')
    if validated['diagnostics']['rejected_sessions']:
        diagnostics.append('HISTORICAL_SESSIONS_EXCLUDED:'+str(validated['diagnostics']['rejected_sessions']))
    return {'ticker': ticker, 'technicals': technicals,
            'technicals_as_of': _previous_close(now).isoformat(),
            'technicals_scope': 'previous_completed_session; daily RSI/MACD from consecutive full sessions',
            'source_url': source, 'technical_source': 'python',
            'technical_provenance': {'input_sha256': hashlib.sha256(raw).hexdigest(),
                'computation': 'factor_inputs.completed_history.metrics.day99-v1',
                'computed_at': now.isoformat(), 'source_url': source}}, diagnostics


def build_from_state(state_dir, cfg, now):
    """Load a staged <=500 pool or compute the actual configured cached pool.

    Neither staged evidence nor prior-session bars are executable morning quotes.
    Errors are credential-free reason codes, never provider payload echoes.
    """
    now = _stamp(now)
    root = Path(state_dir)
    candidate_file = root/'deepseek_candidates.json'
    additional = []
    cache_gaps = {}
    if candidate_file.exists():
        try:
            payload = _read(candidate_file)
        except (OSError, UnicodeError, ValueError, TypeError):
            return _blank(now, 'STAGED_CANDIDATE_FILE_INVALID')
    else:
        payload = {'as_of': now.isoformat(), 'candidates': [], 'macro': {}}
        tickers = cfg.get('scan', {}).get('universe', [])
        if not isinstance(tickers, list) or len(tickers) > policy.MAX_CANDIDATES:
            return _blank(now, 'INVALID_CONFIGURED_CANDIDATE_POOL')
        directory = root/'intraday_cache'
        try:
            manifest = _read(directory/'manifest.json')
            prepared = _stamp(manifest['prepared_at'])
            if (manifest.get('session') != now.date().isoformat() or prepared.date() != now.date()
                    or prepared > now or prepared.time() >= dt.time(9, 30)
                    or manifest.get('source') != cfg.get('data_sources', {}).get('primary', 'yahoo_direct')
                    or manifest.get('source') != 'yahoo_direct'):
                raise ValueError('CACHE_MANIFEST_IDENTITY_MISMATCH')
            if not manifest.get('complete'):
                additional.append('CACHE_MANIFEST_INCOMPLETE')
        except (OSError, UnicodeError, KeyError, ValueError, TypeError):
            manifest = None
            additional.append('CACHE_MANIFEST_UNAVAILABLE_OR_INVALID')
        for ticker in tickers:
            if not isinstance(ticker, str) or not TICKER.fullmatch(ticker):
                additional.append('INVALID_CONFIGURED_TICKER')
                continue
            try:
                if manifest is None or ticker not in manifest.get('tickers', []):
                    raise ValueError('CACHE_TICKER_UNAVAILABLE')
                item, diagnostics = _from_cache(ticker, directory, manifest, cfg, now)
                cache_gaps[ticker] = diagnostics
            except (OSError, UnicodeError, KeyError, ValueError, TypeError, IndexError) as exc:
                item = {'ticker': ticker}
                cache_gaps[ticker] = ['CACHE_TICKER_UNAVAILABLE_OR_INVALID']
                # Only our uppercase reason codes may leave this boundary. Pandas
                # exceptions can contain raw staged content and are never echoed.
                if isinstance(exc, ValueError) and re.fullmatch(r'[A-Z0-9_:]{1,100}', str(exc)):
                    cache_gaps[ticker].append(str(exc))
            payload['candidates'].append(item)
    if not isinstance(payload, dict):
        return _blank(now, 'INVALID_INPUT_OBJECT')
    for filename, key in [('deepseek_macro.json', 'macro'), ('deepseek_news.json', 'news')]:
        path = root/filename
        if not path.exists():
            continue
        try:
            staged = _read(path)
            if not isinstance(staged, dict):
                raise ValueError('INVALID_STAGED_OBJECT')
            if key == 'macro':
                payload['macro'] = staged
            else:
                for item in payload.get('candidates', []):
                    if not isinstance(item, dict):
                        continue
                    evidence = staged.get(item.get('ticker'), {})
                    if not isinstance(evidence, dict):
                        raise ValueError('INVALID_NEWS_OBJECT')
                    for field in ('headlines', 'catalyst_tags'):
                        if field in evidence:
                            item[field] = evidence[field]
        except (OSError, UnicodeError, KeyError, ValueError, TypeError):
            additional.append('STAGED_'+key.upper()+'_FILE_INVALID')
    output = validate_payload(payload, now)
    output['gaps'] = list(dict.fromkeys(output['gaps']+additional))
    for ticker, gaps in cache_gaps.items():
        output['candidate_gaps'][ticker] = sorted(set(output['candidate_gaps'].get(ticker, [])+gaps))
    output['coverage']['complete_tickers'] = [item['ticker'] for item in output['candidates']
        if not output['candidate_gaps'].get(item['ticker'])]
    output['coverage']['complete'] = len(output['coverage']['complete_tickers'])
    output['coverage']['pool_source'] = 'staged_public_candidates' if candidate_file.exists() else 'configured_cached_universe'
    output['coverage']['upstream_python_declaration'] = bool(candidate_file.exists())
    return output
