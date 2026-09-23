#!/usr/bin/env python3
"""Pre-market public evidence and bounded DeepSeek assessment; never selection.

This command is preparation, not another daily report entrypoint. The daily
brief only reads the resulting snapshot. An attempt, including failure, is
reused for the same session; it cannot be silently retried after seeing outcomes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.parse import parse_qs
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import deepseek_policy as P
from bounded import acquire
from build_biotech import write_atomic
from diagnostics import safe_detail
from report_store import encode
from quotes import stamp


def load_private_key(state_dir):
    """The environment wins; a private host key can populate that environment."""
    present = os.environ.get('DEEPSEEK_API_KEY')
    if present:
        if len(present) > P.MAX_TITLE_CHARS or any(c.isspace() for c in present):
            raise ValueError('INVALID_PRIVATE_CREDENTIAL')
        return True
    path = Path(state_dir)/'secrets'/'deepseek_api_key'
    if not path.is_file():
        return False
    if path.stat().st_size > P.MAX_TITLE_CHARS:
        raise ValueError('INVALID_PRIVATE_CREDENTIAL')
    key = path.read_text().strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError('invalid private DeepSeek credential format')
    os.environ['DEEPSEEK_API_KEY'] = key
    return True


def load_private_model(state_dir):
    """Explicit account model selection; no implicit unavailable-model fallback."""
    if os.environ.get('DEEPSEEK_MODEL'):
        model = os.environ['DEEPSEEK_MODEL']
    else:
        path = Path(state_dir)/'deepseek_model.txt'
        if not path.exists():
            return P.DEFAULT_MODEL
        if path.stat().st_size > 101:
            raise ValueError('INVALID_PRIVATE_MODEL')
        model = path.read_text(encoding='utf-8').strip()
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,99}', model)
            or model.startswith('sk-')):
        raise ValueError('INVALID_PRIVATE_MODEL')
    os.environ.setdefault('DEEPSEEK_MODEL', model)
    return model


def _public_failure(exc):
    """Credential-free provider status; never persist an exception body/URL."""
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', None) or getattr(exc, 'code', None)
    if status == 429:
        code = 'PROVIDER_RATE_LIMIT'
    elif status in (401, 403):
        code = 'PROVIDER_AUTH'
    elif status is not None:
        code = 'PROVIDER_HTTP_ERROR'
    elif isinstance(exc, (ValueError, KeyError, TypeError, IndexError)):
        code = 'INVALID_PUBLIC_DATA'
    elif 'timeout' in type(exc).__name__.lower():
        code = 'TRANSPORT_TIMEOUT'
    else:
        code = 'TRANSPORT_ERROR'
    # CARRY OUR OWN REASON. `details` was the exception CLASS name, so eleven
    # names on 2026-09-21 reported "INVALID_PUBLIC_DATA" and the detail behind
    # it was the word "ValueError" — while the raise sites below had already
    # said RSS_CHANNEL_IDENTITY_MISMATCH, RSS_SIZE_LIMIT, INVALID_RSS_XML,
    # UNTIMED_RSS_ITEM and so on. Those are OUR constants and they are the
    # whole diagnosis.
    #
    # Only a message that looks like one of our own codes is kept. A provider
    # exception can carry a body or a URL in its message and none of that may
    # reach a stored report, so anything else falls back to the class name.
    message = str(exc)
    reason = (message if re.fullmatch(r'[A-Z][A-Z0-9_]{2,63}', message)
              else type(exc).__name__[:80])
    return {'status': 'UNAVAILABLE', 'errorcode': code, 'details': reason}


def _news(ticker, now, *, clock=None):
    """Exact ticker RSS for TSX; search requires exact relatedTickers elsewhere."""
    if ticker.endswith('.TO'):
        return _rss_news(ticker, now, clock=clock)
    return _search_news(ticker, now, clock=clock)


def _rss_news(ticker, now, *, clock=None):
    """Verify Yahoo's exact-symbol channel before accepting any article.

    A ticker in our request is not evidence of response identity. The provider
    must return the expected channel title AND a matching ticker channel link.
    This is provider-assigned ticker linkage, not inferred issuer-name matching.
    """
    import requests
    from factor_inputs import _url
    from factor_news import prepare_headlines
    url = 'https://feeds.finance.yahoo.com/rss/2.0/headline'
    source_url = url+'?s='+quote(ticker, safe='')+'&region=CA&lang=en-CA'
    digest = None
    try:
        response = requests.get(url, params={'s': ticker, 'region': 'CA', 'lang': 'en-CA'},
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=P.PUBLIC_REQUEST_TIMEOUT)
        response.raise_for_status()
        raw = response.content
        if not isinstance(raw, bytes) or len(raw) > P.MAX_PUBLIC_NEWS_BYTES:
            raise ValueError('RSS_SIZE_LIMIT')
        digest = hashlib.sha256(raw).hexdigest()
        xml = raw.decode('utf-8-sig')
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', xml, re.I):
            raise ValueError('RSS_ENTITY_DECLARATION_REJECTED')
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            raise ValueError('INVALID_RSS_XML') from None
        channels = root.findall('channel')
        if root.tag != 'rss' or len(channels) != 1:
            raise ValueError('RSS_CHANNEL_IDENTITY_MISMATCH')
        channel = channels[0]
        title = (channel.findtext('title') or '').strip()
        link = urlsplit((channel.findtext('link') or '').strip())
        symbols = parse_qs(link.query).get('s')
        if (title != 'Yahoo! Finance: '+ticker+' News'
                or link.scheme not in ('https', 'http') or link.hostname != 'finance.yahoo.com'
                or link.username is not None or link.password is not None
                or link.path not in ('/q/h', '/q/h/') or symbols != [ticker]):
            raise ValueError('RSS_CHANNEL_IDENTITY_MISMATCH')
        retrieved = stamp(clock()) if clock is not None else now
        out, reasons = [], {}
        items = channel.findall('item')
        for item in items:
            try:
                headline = (item.findtext('title') or '').strip()
                if (not headline or len(headline) > P.MAX_TITLE_CHARS
                        or any(ord(c) < 32 for c in headline)):
                    raise ValueError('INVALID_RSS_TITLE')
                article = _url((item.findtext('link') or '').strip())
                published = parsedate_to_datetime(item.findtext('pubDate') or '')
                if published.tzinfo is None or published.utcoffset() is None:
                    raise ValueError('UNTIMED_RSS_ITEM')
                if not 0 <= (retrieved-published).total_seconds() <= P.MAX_NEWS_AGE_HOURS*3600:
                    raise ValueError('STALE_OR_FUTURE_RSS_ITEM')
                out.append({'title': headline, 'source_url': article,
                            'published_at': published.isoformat()})
            except (ValueError, TypeError, OverflowError, AttributeError):
                reasons['INVALID_OR_OUT_OF_WINDOW_ITEM'] = reasons.get('INVALID_OR_OUT_OF_WINDOW_ITEM', 0)+1
        out, quality_reasons = prepare_headlines(out, P.MAX_NEWS_PER_CANDIDATE)
        reasons.update(quality_reasons)
        return {'status': 'READY' if out else 'NO_CURRENT_NEWS', 'headlines': out, 'catalyst_tags': [],
                'retrieved_at': retrieved.isoformat(), 'source_url': source_url,
                'source_identity': 'provider exact-ticker RSS channel',
                'channel_title': title, 'response_sha256': digest,
                'unusable_rows': len(items)-len(out), 'rejected_rows': reasons,
                'tag_status': 'No structured SEC feed supplied; 8-K tags not inferred from headlines.'}
    except Exception as exc:
        return {**_public_failure(exc), 'source_url': source_url, 'response_sha256': digest}


def _search_news(ticker, now, *, clock=None):
    import requests
    from factor_inputs import _url
    from factor_news import prepare_headlines
    url = 'https://query1.finance.yahoo.com/v1/finance/search'
    try:
        response = requests.get(url, params={'q': ticker, 'newsCount': P.MAX_NEWS_PER_CANDIDATE,
                                             'quotesCount': 1,
                                             'newsQueryId': 'news_cie_vespa',
                                             'quotesQueryId': 'tss_match_phrase_query',
                                             'enableFuzzyQuery': False},
                                headers={'User-Agent': 'Mozilla/5.0'}, timeout=P.PUBLIC_REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get('news', []), list):
            raise ValueError('INVALID_NEWS_RESPONSE')
    except Exception as exc:
        return _public_failure(exc)
    retrieved = stamp(clock()) if clock is not None else now
    out = []
    for item in payload.get('news', []):
        # Exact relatedTicker linkage, not a loose shared word such as energy.
        if (not isinstance(item, dict) or not isinstance(item.get('relatedTickers'), list)
                or any(not isinstance(symbol, str) for symbol in item['relatedTickers'])
                or ticker not in item['relatedTickers']):
            continue
        try:
            observed = dt.datetime.fromtimestamp(item['providerPublishTime'], dt.timezone.utc)
            link, title = item['link'], item['title']
            if (not 0 <= (retrieved-observed).total_seconds() <= P.MAX_NEWS_AGE_HOURS*3600
                    or not isinstance(title, str) or not title.strip()
                    or len(title)>P.MAX_TITLE_CHARS or any(ord(c) < 32 for c in title)):
                continue
            out.append({'title': title.strip(), 'source_url': _url(link), 'published_at': observed.isoformat()})
        except (KeyError, TypeError, ValueError, OverflowError):
            continue  # Counted below as unusable source rows; no invented headline.
    invalid_count = len(payload.get('news', []))-len(out)
    out, reasons = prepare_headlines(out, P.MAX_NEWS_PER_CANDIDATE)
    if invalid_count:
        reasons['INVALID_OR_UNLINKED_ITEM'] = invalid_count
    return {'status': 'READY' if out else 'NO_CURRENT_NEWS', 'headlines': out, 'catalyst_tags': [], 'retrieved_at': retrieved.isoformat(),
            'source_url': url, 'unusable_rows': len(payload.get('news', []))-len(out),
            'rejected_rows': reasons,
            'tag_status': 'No structured SEC feed supplied; 8-K tags not inferred from headlines.'}


def _macro(cfg, now, *, clock=None):
    """Parallel dated levels and validated bar-change context; no extra requests."""
    import requests
    from quotes import number
    from factor_inputs import _previous_close
    from factor_macro import daily_change_context
    prior_close = _previous_close(now)
    names = {'wti': cfg['correlated']['crude'], 'cadusd': cfg['correlated']['cadusd'],
             'tsx': cfg['correlated']['tsx'], 'vix': cfg['correlated']['vix']}
    values, gaps = {}, []

    def fetch(pair):
        name, ticker = pair
        url = 'https://query1.finance.yahoo.com/v8/finance/chart/'+quote(ticker, safe='')
        try:
            response = requests.get(url, params={'interval': '1d', 'range': '5d'},
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=P.PUBLIC_REQUEST_TIMEOUT)
            response.raise_for_status()
            chart = response.json()['chart']['result'][0]
            row = chart['meta']
            if row.get('symbol') != ticker:
                raise ValueError('macro symbol mismatch')
            value = number(row.get('regularMarketPrice'), positive=True)
            as_of = stamp(row['regularMarketTime'])
            retrieved = stamp(clock()) if clock is not None else now
            if value is None or not prior_close <= as_of <= retrieved:
                raise ValueError('macro observation unavailable or stale')
            source = url+'?interval=1d&range=5d'
            context = daily_change_context(chart, value, as_of, source)
            gap = (name+': macro change unavailable ('+context['change_gap']+')'
                   if context['change_status'] == 'UNAVAILABLE' else None)
            return name, {'value': value, 'as_of': as_of.isoformat(),
                          'source_url': source, **context}, gap
        except Exception as exc:
            fail = _public_failure(exc)
            return name, None, name+': timestamped macro reference unavailable ('+fail['errorcode']+')'

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        for name, value, gap in pool.map(fetch, names.items()):
            values[name] = value
            if gap:
                gaps.append(gap)
    return {'values': values, 'gaps': gaps, 'label': 'Dated macro references, not live executable BBO.'}


def candidate_roster(state_dir, cfg, now, *, diagnostic=False):
    """Use the actual staged pool, never silently fall back from a bad pool."""
    from factor_inputs import TICKER
    path = Path(state_dir)/'deepseek_candidates.json'
    if path.exists():
        payload = _read_json(path)
        if payload.get('kind') == 'CURRENT_TIME_DIAGNOSTIC' or payload.get('morning_snapshot') is False:
            if not diagnostic:
                raise ValueError('DIAGNOSTIC_CANDIDATES_ARE_NOT_MORNING_INPUTS')
            from diagnostic_context import require_context
            require_context(state_dir)
        observed = stamp(payload['as_of'])
        if (observed > now or (now-observed).total_seconds() > P.MAX_SNAPSHOT_AGE_HOURS*3600
                or observed.astimezone(ZoneInfo('America/New_York')).date() != now.date()):
            raise ValueError('STAGED_CANDIDATE_ROSTER_STALE_OR_FUTURE')
        tickers = [item['ticker'] for item in payload['candidates']]
        from research_shortlist import expanded
        if expanded(payload):
            from factor_inputs import validate_payload
            checked = validate_payload(payload, now)
            receipt = checked.get('research_shortlist')
            if not isinstance(receipt, dict):
                raise ValueError('RESEARCH_SHORTLIST_INVALID_OR_CHANGED')
            _persist_shortlist(state_dir, receipt)
            tickers = receipt['tickers']
    else:
        tickers = cfg['scan']['universe']
    if (not isinstance(tickers, list) or len(tickers) > P.MAX_CANDIDATES
            or any(not isinstance(t, str) or not TICKER.fullmatch(t) for t in tickers)
            or len(set(tickers)) != len(tickers)):
        raise ValueError('INVALID_CANDIDATE_ROSTER')
    return tickers


def fitting_batches(eligible, macro, as_of):
    """BATCH_SIZE-name batches, halved until each fits the adapter's prompt cap.

    MEASURED 2026-09-23: with the day-113 context fields grounded per name, 25
    names came to 310-345k characters against MAX_PROMPT_CHARS 300k, and the
    adapter refused two of three batches as INVALID_INPUT before any request.
    A fixed smaller size would break again the next time a field is added;
    measuring the real payload cannot. A batch whose size cannot be measured is
    passed through unchanged, so the adapter reports its own refusal."""
    from adapters import deepseek_adapter as A
    import factor_grounding as G

    def fits(batch):
        try:
            payload = G.request_payload(A.public_payload(batch, macro, as_of))
        except Exception:
            return True
        return len(json.dumps(payload, ensure_ascii=False)) + len(A.SYSTEM_PROMPT) <= A.MAX_PROMPT_CHARS

    queue = [eligible[i:i+P.BATCH_SIZE] for i in range(0, len(eligible), P.BATCH_SIZE)]
    out = []
    while queue:
        batch = queue.pop(0)
        if len(batch) == 1 or fits(batch):
            out.append(batch)
        else:
            half = len(batch) // 2
            queue[0:0] = [batch[:half], batch[half:]]
    return out


def _read_json(path):
    """One strict parser for staged evidence, CLI input and replay receipts."""
    from factor_inputs import _read
    return _read(Path(path))


def _persist_shortlist(state_dir, receipt):
    path = Path(state_dir)/'deepseek_shortlist.json'
    if path.exists():
        previous = _read_json(path)
        if previous == receipt:
            return
        try:
            prior_session = dt.date.fromisoformat(previous['session'])
            session = dt.date.fromisoformat(receipt['session'])
        except (ValueError, TypeError, KeyError):
            raise ValueError('RESEARCH_SHORTLIST_ALREADY_FROZEN') from None
        if prior_session >= session:
            raise ValueError('RESEARCH_SHORTLIST_ALREADY_FROZEN')
    write_atomic(path, receipt)


def _failure_snapshot(now, reason, model=None):
    from factor_inputs import _blank
    clean = _blank(now, reason)
    return {'schema_version': P.SCHEMA_VERSION, 'session': now.date().isoformat(),
            'as_of': now.isoformat(), 'prepared_at': now.isoformat(),
            'prompt_version': P.PROMPT_VERSION, 'model': model, 'adopted': False,
            'status': 'UNAVAILABLE', 'requested': 0, 'covered': 0,
            'inputs': clean, 'input_sha256': hashlib.sha256(encode(clean).encode()).hexdigest(),
            'assessments': [], 'batches': [], 'candidate_gaps': {},
            'gaps': [reason], 'registration': P.DESIGN_PROVENANCE['registration']}


def _seal(obj):
    obj = dict(obj)
    obj.pop('snapshot_sha256', None)
    obj['snapshot_sha256'] = hashlib.sha256(encode(obj).encode()).hexdigest()
    return obj


def _checked_replay(path, now, *, diagnostic=False):
    from adapters.deepseek_adapter import parse_assessments
    from factor_inputs import validate_payload
    obj = _read_json(path)
    if not isinstance(obj, dict):
        raise ValueError('INVALID_SNAPSHOT_OBJECT')
    diagnostic_snapshot = obj.get('kind') == 'CURRENT_TIME_DIAGNOSTIC' and obj.get('morning_snapshot') is False
    if diagnostic != diagnostic_snapshot:
        raise ValueError('SNAPSHOT_EXECUTION_CONTEXT_MISMATCH')
    if obj.get('snapshot_sha256') != _seal(obj)['snapshot_sha256']:
        raise ValueError('SNAPSHOT_INTEGRITY_MISMATCH')
    observed, prepared = stamp(obj['as_of']), stamp(obj['prepared_at'])
    if (obj.get('schema_version') != P.SCHEMA_VERSION or obj.get('prompt_version') != P.PROMPT_VERSION
            or obj.get('session') != now.date().isoformat() or obj.get('adopted') is not False
            or prepared.astimezone(ZoneInfo('America/New_York')).date() != now.date()
            or not observed <= prepared <= now
            or (now-observed).total_seconds() > P.MAX_SNAPSHOT_AGE_HOURS*3600
            or obj.get('status') not in ('READY', 'PARTIAL', 'UNAVAILABLE')):
        raise ValueError('SNAPSHOT_IDENTITY_OR_TIME_MISMATCH')
    if hashlib.sha256(encode(obj['inputs']).encode()).hexdigest() != obj['input_sha256']:
        raise ValueError('SNAPSHOT_INPUT_HASH_MISMATCH')
    checked = validate_payload(obj['inputs'], now)
    pool = {item['ticker'] for item in checked['candidates']}
    rows = obj['assessments']
    names = [row['ticker'] for row in rows]
    if not set(names) <= pool or len(names) != len(set(names)):
        raise ValueError('SNAPSHOT_ASSESSMENT_IDENTITY_MISMATCH')
    if rows:
        parse_assessments(encode({'assessments': rows}), names)
    from grounded_records import validate_snapshot
    validate_snapshot(obj)
    if obj.get('covered') != len(rows) or obj.get('requested') != len(obj['inputs']['candidates']):
        raise ValueError('SNAPSHOT_COVERAGE_MISMATCH')
    # Replay never calls a model. The decision-time loader separately rechecks
    # freshness and every candidate gap before considering an existing output.
    return obj


def refresh_public_inputs(state_dir, cfg, now, *, clock=None, diagnostic=False):
    """One bounded pass; retain valid prior facts when a new field fails."""
    from factor_inputs import validate_payload
    root = Path(state_dir)
    if diagnostic:
        from diagnostic_context import require_context
        require_context(root)
    preopen_seconds = max(0., (now.replace(hour=9, minute=30, second=0, microsecond=0)-now).total_seconds())
    deadline = time.monotonic()+(P.PUBLIC_INPUT_BUDGET_SECONDS if diagnostic else min(P.PUBLIC_INPUT_BUDGET_SECONDS, preopen_seconds))
    gaps = []
    try:
        tickers = candidate_roster(root, cfg, now, diagnostic=diagnostic)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        tickers = []
        gaps.append('Public evidence roster invalid; no ticker discovery or fallback was attempted.')
    macro_path = root/'deepseek_macro.json'
    previous_macro, can_write_macro = {}, True
    if macro_path.exists():
        try:
            previous_macro = _read_json(macro_path)
            if not isinstance(previous_macro, dict):
                raise ValueError('INVALID_MACRO_OBJECT')
        except (ValueError, OSError, TypeError, UnicodeError):
            can_write_macro = False
            gaps.append('Existing macro inputs unreadable; their file was preserved.')
    macro_budget = min(P.PUBLIC_REQUEST_TIMEOUT+2, max(0., deadline-time.monotonic()))
    result = (acquire({'macro': (lambda: _macro(cfg, now, clock=clock), macro_budget)})['macro']
              if macro_budget > 0 else {'value': None, 'error': 'PRE_OPEN_DEADLINE'})
    if result.get('value') is not None:
        try:
            fresh = result['value']
            reviewed_at = stamp(clock()) if clock is not None else now
            checked = validate_payload({'as_of': reviewed_at.isoformat(), 'candidates': [],
                                        'macro': fresh['values']}, reviewed_at)
            if can_write_macro:
                # A failed or null fresh item never wipes an earlier observation.
                # Stale earlier facts remain dated; factor_inputs will exclude them.
                merged = {**previous_macro, **checked['macro']}
                write_atomic(macro_path, merged)
            gaps.extend(safe_detail(g) for g in fresh.get('gaps', []))
            gaps.extend(checked['gaps'])
        except (KeyError, ValueError, OSError, TypeError):
            gaps.append('Macro input result invalid; prior observations preserved.')
    else:
        gaps.append('Macro input acquisition failed: '+safe_detail(result.get('error', 'UNKNOWN')))
    news = {}
    existing = root/'deepseek_news.json'
    if existing.exists():
        try:
            news = _read_json(existing)
            if not isinstance(news, dict):
                raise ValueError('INVALID_NEWS_OBJECT')
        except (ValueError, OSError, TypeError, UnicodeError):
            gaps.append('Existing news inputs unreadable; their file was preserved.')
            return gaps
    queried = []
    stopped = None
    for start in range(0, len(tickers), P.PUBLIC_BATCH_SIZE):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            gaps.append('Public evidence preparation deadline reached.'); break
        block = tickers[start:start+P.PUBLIC_BATCH_SIZE]
        fetched = acquire({t: (lambda t=t: _news(t, now, clock=clock),
                              min(P.PUBLIC_REQUEST_TIMEOUT+1, remaining)) for t in block})
        failed = 0
        halt_provider = False
        queried.extend(block)
        for ticker, item in fetched.items():
            fresh = item.get('value')
            if isinstance(fresh, dict) and fresh.get('status') == 'UNAVAILABLE':
                failed += 1
                code = safe_detail(fresh.get('errorcode', 'UNKNOWN'))
                # The code alone said INVALID_PUBLIC_DATA for every one of
                # eleven names; the detail says WHICH check refused, and a
                # channel-identity mismatch and an oversize feed need entirely
                # different responses.
                detail = safe_detail(str(fresh.get('details') or ''), 64)
                gaps.append(ticker+': headline acquisition failed: '+code
                            + (' ('+detail+')' if detail else ''))
                prior = news.get(ticker, {})
                news[ticker] = {**(prior if isinstance(prior, dict) else {}),
                    'status': 'UNAVAILABLE', 'errorcode': code, 'details': detail,
                    'last_attempt_at': (stamp(clock()) if clock is not None else now).isoformat()}
                halt_provider |= code in ('PROVIDER_RATE_LIMIT', 'PROVIDER_AUTH')
            elif fresh is not None:
                # Preserve independently reviewed tags and dated prior headlines
                # when the provider response contains no usable linked evidence.
                prior = news.get(ticker, {})
                if not isinstance(fresh, dict):
                    failed += 1; gaps.append(ticker+': invalid headline result'); continue
                if isinstance(prior, dict):
                    if prior.get('catalyst_tags'):
                        fresh['catalyst_tags'] = prior['catalyst_tags']
                    if not fresh.get('headlines') and prior.get('headlines'):
                        fresh['headlines'] = prior['headlines']
                        gaps.append(ticker+': no fresh linked headlines; dated prior evidence retained.')
                news[ticker] = fresh
            else:
                failed += 1
                gaps.append(ticker+': headline acquisition failed: '+safe_detail(item.get('error', 'UNKNOWN')))
                prior = news.get(ticker, {})
                news[ticker] = {**(prior if isinstance(prior, dict) else {}),
                    'status': 'UNAVAILABLE', 'errorcode': safe_detail(item.get('error', 'UNKNOWN')),
                    'last_attempt_at': (stamp(clock()) if clock is not None else now).isoformat()}
        write_atomic(existing, news)
        # A single failed ticker must not discard healthy independent names.
        # A rejected or wholly unavailable provider is not hammered repeatedly.
        if halt_provider or failed == len(block):
            stopped = 'provider refusal' if halt_provider else 'entire batch unavailable'
            gaps.append('Stopped headline acquisition after provider failure; remaining names not queried.'); break
    if len(queried) < len(tickers):
        gaps.append(f'Headline coverage: {len(queried)}/{len(tickers)} queried; remaining names unassessed.')
    reviewed_at = stamp(clock()) if clock is not None else now
    write_atomic(root/'deepseek_public_status.json', {
        'session': now.date().isoformat(), 'as_of': now.isoformat(),
        'finished_at': reviewed_at.isoformat(),
        'requested': len(tickers), 'queried': len(queried), 'queried_tickers': queried,
        'unqueried_tickers': [t for t in tickers if t not in queried],
        'stop_reason': stopped, 'gaps': list(dict.fromkeys(map(safe_detail, gaps))),
        'news_status': {ticker: news.get(ticker, {}).get('status', 'UNAVAILABLE')
                        if ticker in queried else 'NOT_QUERIED' for ticker in tickers},
        **({'kind': 'CURRENT_TIME_DIAGNOSTIC', 'morning_snapshot': False} if diagnostic else {})})
    return gaps


def prepare(state_dir, cfg, *, now=None, inputs=None, refresh=False, evaluator=None):
    """Production-only pre-open preparation through the shared pipeline."""
    if (Path(state_dir)/'diagnostic_context.json').exists():
        raise ValueError('Diagnostic state cannot become a production preparation.')
    return _prepare(state_dir, cfg, now=now, inputs=inputs, refresh=refresh, evaluator=evaluator)


def prepare_diagnostic(state_dir, cfg, *, now=None, inputs=None, refresh=False, evaluator=None):
    """Same pipeline at the actual current time, in explicit isolated state only."""
    from diagnostic_context import require_context
    require_context(state_dir)
    return _prepare(state_dir, cfg, now=now, inputs=inputs, refresh=refresh,
                    evaluator=evaluator, diagnostic=True)


def _prepare(state_dir, cfg, *, now=None, inputs=None, refresh=False, evaluator=None, diagnostic=False):
    from adapters.deepseek_adapter import CANDIDATE_KEYS, parse_assessments, public_payload
    from analyst import analyze_factors
    from factor_inputs import build_from_state, validate_payload, eligible_public_candidates
    injected_clock = now is not None
    now = stamp(now or dt.datetime.now(ZoneInfo('America/New_York'))).astimezone(ZoneInfo('America/New_York'))
    if not diagnostic and now.time() >= dt.time(9, 30):
        raise ValueError('DeepSeek preparation is pre-open only; report critical path must remain local.')
    root = Path(state_dir); root.mkdir(parents=True, exist_ok=True)
    history = root/'deepseek_history'/now.date().isoformat()
    history.mkdir(parents=True, exist_ok=True)
    import fcntl
    with (history/'preparation.lock').open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return _seal(_failure_snapshot(now, 'DeepSeek preparation already in progress; no duplicate request.'))
        prior = history/'snapshot.json'
        if prior.exists():
            try:
                obj = _checked_replay(prior, now, diagnostic=diagnostic)
            except (ValueError, TypeError, KeyError, OSError, UnicodeError):
                obj = _seal(_failure_snapshot(now, 'Prior same-session DeepSeek snapshot failed integrity validation; no retry.'))
            write_atomic(root/'deepseek_snapshot.json', obj)
            return obj
        attempt = history/'attempt.json'
        if attempt.exists():
            obj = _seal(_failure_snapshot(now, 'Prior DeepSeek preparation is incomplete or ambiguous; no automatic retry.'))
            write_atomic(root/'deepseek_snapshot.json', obj)
            return obj
        # Persist before any provider access. A terminated worker/run cannot cause
        # an unrecorded second request on the next same-day invocation.
        write_atomic(attempt, {'session': now.date().isoformat(), 'started_at': now.isoformat(),
                               'prompt_version': P.PROMPT_VERSION, 'status': 'STARTED',
                               **({'kind': 'CURRENT_TIME_DIAGNOSTIC', 'morning_snapshot': False} if diagnostic else {})})
        preopen_seconds = (now.replace(hour=9, minute=30, second=0, microsecond=0)-now).total_seconds()
        deadline = time.monotonic()+(P.PREP_BUDGET_SECONDS if diagnostic else min(P.PREP_BUDGET_SECONDS, preopen_seconds))
        started_at = now
        gaps = []
        if refresh and inputs is None:
            try:
                if diagnostic:
                    gaps.extend(refresh_public_inputs(root, cfg, now, diagnostic=True,
                        clock=None if injected_clock else lambda: dt.datetime.now(ZoneInfo('America/New_York'))))
                    if not injected_clock:
                        now = dt.datetime.now(ZoneInfo('America/New_York'))
                elif injected_clock:
                    gaps.extend(refresh_public_inputs(root, cfg, now))
                else:
                    gaps.extend(refresh_public_inputs(root, cfg, now,
                        clock=lambda: dt.datetime.now(ZoneInfo('America/New_York'))))
                    now = dt.datetime.now(ZoneInfo('America/New_York'))
            except Exception as exc:
                gaps.append('Public input preparation failed: '+type(exc).__name__)
        try:
            clean = (validate_payload(inputs, now) if inputs is not None else
                     build_from_state(root, cfg, now, diagnostic=True) if diagnostic else
                     build_from_state(root, cfg, now))
        except Exception as exc:
            from factor_inputs import _blank
            clean = _blank(now, 'Candidate preparation failed: '+type(exc).__name__)
        gaps.extend(clean.get('gaps', []))
        if isinstance(clean.get('research_shortlist'), dict):
            try:
                _persist_shortlist(root, clean['research_shortlist'])
            except (OSError, ValueError, TypeError, KeyError, UnicodeError):
                clean['research_shortlist'] = None
                gaps.append('RESEARCH_SHORTLIST_ALREADY_FROZEN')
        candidate_gaps = {t: list(gs) for t, gs in clean.get('candidate_gaps', {}).items()}
        macro = {key: clean.get('macro', {}).get(key) for key in P.MACRO_KEYS}
        try:
            model = load_private_model(root)
            model_ok = True
        except (OSError, ValueError, UnicodeError):
            model = None; model_ok = False
            gaps.append('INVALID_MODEL: no DeepSeek request attempted.')
        eligible, eligibility_gaps = eligible_public_candidates(clean)
        for ticker, reasons in eligibility_gaps.items():
            candidate_gaps.setdefault(ticker, []).extend(reasons)
        submitted = []
        assessments, batches, grounded_receipts, grounding_notes = [], [], [], []
        try:
            key_ok = evaluator is not None or load_private_key(root)
        except Exception as exc:
            key_ok = False
            gaps.append('Private DeepSeek credential unavailable: '+type(exc).__name__)
        if not key_ok:
            gaps.append('DEEPSEEK_API_KEY unavailable in environment/private host state.')
        elif model_ok:
            pending = fitting_batches(eligible, macro, clean['as_of'])
            for start in range(0, len(pending), P.MODEL_BATCH_CONCURRENCY):
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    gaps.append('DeepSeek preparation deadline reached.'); break
                wave = pending[start:start+P.MODEL_BATCH_CONCURRENCY]
                submitted.extend(c['ticker'] for batch in wave for c in batch)
                timeout = min(P.REQUEST_TIMEOUT, remaining)
                if evaluator is None:
                    jobs = {('deepseek' if len(wave) == 1 else 'deepseek_'+str(i)):
                            (lambda batch=batch: analyze_factors(batch, macro, clean['as_of'],
                             model=model, timeout=timeout), timeout) for i, batch in enumerate(wave)}
                    completed = acquire(jobs)
                    received = [completed.get(name, {'value': None, 'error': 'MISSING_BATCH_RESULT'})
                                for name in jobs]
                else:
                    # Offline evaluators have no network and intentionally run
                    # in-process, while exercising the same response boundary.
                    received = []
                    for batch in wave:
                        try:
                            value = evaluator(batch, macro, clean['as_of'], model=model, timeout=timeout)
                            received.append({'value': value})
                        except Exception as exc:
                            received.append({'value': None, 'error': type(exc).__name__})
                failed, stop_provider = 0, False
                for batch, got in zip(wave, received):
                    metadata = {'tickers': [c['ticker'] for c in batch]}
                    try:
                        response = got.get('value') or {'status': 'UNAVAILABLE', 'assessments': [],
                            'errorcode': 'BOUNDED_REQUEST_FAILURE',
                            'details': safe_detail(got.get('error', 'Bounded DeepSeek request failed.'))}
                        if not isinstance(response, dict):
                            raise ValueError('INVALID_BATCH_RESPONSE')
                        for key in ('status', 'errorcode', 'details', 'model', 'request_id',
                                    'response_id', 'response_model', 'prompt_version',
                                    'schema_version', 'input_sha256', 'close_warning', 'inference_mode'):
                            if key in response:
                                value = response[key]
                                metadata[key] = safe_detail(value) if isinstance(value, str) else value if value is None or isinstance(value, (int, bool)) else 'INVALID_METADATA'
                        batches.append(metadata)
                        if response.get('status') in ('READY', 'PARTIAL') or response.get('grounding'):
                            from grounded_records import validate_result
                            rows, grounding, private = validate_result(response, batch, macro, clean['as_of'])
                            # Even an all-excluded response is completed model
                            # work with an indispensable receipt, not a generic
                            # transport failure whose evidence may be omitted.
                            metadata['grounded_contract'] = grounding['version']
                            grounded_receipts.append({'batch_index': len(batches)-1,
                                'status': response['status'], 'input_sha256': response['input_sha256'],
                                'assessments': rows, 'grounding': grounding,
                                'private_grounding_receipt': private})
                            grounding_notes.append(grounding)
                            assessments.extend(rows)
                            for ticker, issues in grounding['excluded'].items():
                                candidate_gaps.setdefault(ticker, []).extend('GROUNDING:'+code for code in issues)
                            # A completed but inadmissible opinion is not a
                            # provider outage; later independent batches remain
                            # eligible within the unchanged outer deadline.
                            continue
                        code = safe_detail(response.get('errorcode', 'UNKNOWN'))
                        stop_provider |= code in ('PROVIDER_AUTH', 'PROVIDER_PAYMENT_REQUIRED', 'PROVIDER_RATE_LIMIT')
                        reason = 'DeepSeek batch unavailable: '+code+' ('+safe_detail(response.get('details') or 'no response details')+')'
                    except Exception as exc:
                        from grounded_records import GroundingValidationError
                        detail = str(exc) if isinstance(exc, GroundingValidationError) else type(exc).__name__
                        metadata.update(status='UNAVAILABLE', errorcode='INVALID_BATCH_RESULT',
                                        details=detail)
                        if not any(item is metadata for item in batches):
                            batches.append(metadata)
                        reason = 'DeepSeek batch failed validation or transport: '+detail
                    failed += 1
                    gaps.append(reason)
                    for c in batch:
                        candidate_gaps.setdefault(c['ticker'], []).append(reason)
                # Concurrent successes survive a neighbour's failure. No failed
                # batch is retried, and refusal/full-wave outage stops new work.
                if stop_provider or failed == len(wave):
                    break
        covered = {a['ticker'] for a in assessments}
        for candidate in clean['candidates']:
            if candidate['ticker'] not in covered:
                candidate_gaps.setdefault(candidate['ticker'], []).append('No successful model assessment for this candidate.')
        prepared = now if injected_clock or evaluator is not None else dt.datetime.now(ZoneInfo('America/New_York'))
        missed_cutoff = not diagnostic and prepared.time() >= dt.time(9, 30)
        if missed_cutoff:
            gaps.append('PREOPEN_DEADLINE_REACHED: returned assessments are audit-only, not morning-usable.')
        from grounded_records import merge_grounding
        obj = {'schema_version': P.SCHEMA_VERSION, 'session': now.date().isoformat(),
               'as_of': clean['as_of'], 'prepared_at': prepared.isoformat(),
               'prompt_version': P.PROMPT_VERSION, 'model': model, 'adopted': False,
               'status': 'UNAVAILABLE' if missed_cutoff else 'READY' if assessments and not gaps and not any(candidate_gaps.values()) else
                         'PARTIAL' if assessments else 'UNAVAILABLE',
               'requested': len(clean['candidates']), 'covered': len(assessments),
               'source_requested': clean.get('coverage', {}).get('requested', len(clean['candidates'])),
               'coverage_version': 1,
               'eligible': len(eligible), 'submitted': len(submitted),
               **({'source_accepted': len(clean['candidates']),
                   'shortlist_count': (clean.get('research_shortlist') or {}).get('selected_count', 0),
                   'research_shortlist': clean.get('research_shortlist'),
                   'research_universe': clean.get('research_universe')}
                  if 'research_universe' in clean else {}),
               'inputs': clean, 'input_sha256': hashlib.sha256(encode(clean).encode()).hexdigest(),
               'assessments': assessments, 'batches': batches,
               'grounding': merge_grounding(grounding_notes),
               'grounding_registration': P.EVIDENCE_REGISTRATION,
               'private_grounding_receipts': grounded_receipts,
               'candidate_gaps': {t: sorted(set(map(safe_detail, gs))) for t, gs in candidate_gaps.items()},
               'gaps': sorted(set(map(safe_detail, gaps))),
               'registration': P.DESIGN_PROVENANCE['registration'],
               **({'kind': 'CURRENT_TIME_DIAGNOSTIC', 'morning_snapshot': False,
                   'prediction_evidence': False} if diagnostic else {})}
        obj = _seal(obj)
        write_atomic(prior, obj)
        write_atomic(root/'deepseek_snapshot.json', obj)
        write_atomic(attempt, {'session': now.date().isoformat(), 'started_at': started_at.isoformat(),
                               'finished_at': prepared.isoformat(), 'status': 'COMPLETED',
                               'snapshot_sha256': obj['snapshot_sha256'],
                               **({'kind': 'CURRENT_TIME_DIAGNOSTIC', 'morning_snapshot': False} if diagnostic else {})})
        return obj


def main(argv=None):
    from dashboard import load_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default=os.getenv('RB_STATE_DIR', str(Path(__file__).parent/'.rb-state')))
    parser.add_argument('--config', default=str(Path(__file__).parent/'config.yaml'))
    parser.add_argument('--input', help='A supplied prefiltered pool, at most 500; no invented padding.')
    parser.add_argument('--refresh-public-inputs', action='store_true', help='Bounded pre-open headline/macro refresh.')
    args = parser.parse_args(argv)
    inputs = None
    if args.input:
        path = Path(args.input)
        inputs = _read_json(path)
    result = prepare(args.state_dir, load_config(args.config), inputs=inputs, refresh=args.refresh_public_inputs)
    print(encode({k: result.get(k) for k in
                  ('status', 'source_requested', 'requested', 'eligible', 'submitted', 'covered', 'model', 'gaps')}))
    return 0 if result['status']=='READY' else 2


if __name__=='__main__':
    raise SystemExit(main())
