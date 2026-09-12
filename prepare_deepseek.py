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


def _news(ticker, now):
    import requests
    url = 'https://query1.finance.yahoo.com/v1/finance/search'
    response = requests.get(url, params={'q': ticker, 'newsCount': P.MAX_NEWS_PER_CANDIDATE,
                                         'quotesCount': 1},
                            headers={'User-Agent': 'Mozilla/5.0'}, timeout=P.PUBLIC_REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    out = []
    for item in payload.get('news', []):
        # Exact relatedTicker linkage, not a loose shared word such as energy.
        if ticker not in item.get('relatedTickers', []):
            continue
        try:
            observed = dt.datetime.fromtimestamp(item['providerPublishTime'], dt.timezone.utc)
            link, title = item['link'], item['title']
            if (not 0 <= (now-observed).total_seconds() <= P.MAX_NEWS_AGE_HOURS*3600
                    or not isinstance(title, str) or len(title)>P.MAX_TITLE_CHARS
                    or urlsplit(link).scheme != 'https'):
                continue
            out.append({'title': title, 'source_url': link, 'published_at': observed.isoformat()})
        except (KeyError, TypeError, ValueError, OverflowError):
            continue  # Counted below as unusable source rows; no invented headline.
    return {'headlines': out, 'catalyst_tags': [], 'retrieved_at': now.isoformat(),
            'source_url': url, 'unusable_rows': len(payload.get('news', []))-len(out),
            'tag_status': 'No structured SEC feed supplied; 8-K tags not inferred from headlines.'}


def _macro(cfg, now):
    from quotes import YahooMarketData, number
    from factor_inputs import _previous_close
    prior_close = _previous_close(now)
    names = {'wti': cfg['correlated']['crude'], 'cadusd': cfg['correlated']['cadusd'],
             'tsx': cfg['correlated']['tsx'], 'vix': cfg['correlated']['vix']}
    raw = YahooMarketData(timeout=P.PUBLIC_REQUEST_TIMEOUT).get(list(names.values()))
    values, gaps = {}, []
    for name, ticker in names.items():
        row = raw.get(ticker, {})
        try:
            if row.get('symbol') != ticker:
                raise ValueError('macro symbol mismatch')
            value = number(row.get('regularMarketPrice'), positive=True)
            as_of = stamp(row['regularMarketTime'])
            if value is None or not prior_close <= as_of <= now:
                raise ValueError('macro observation unavailable or stale')
            values[name] = {'value': value, 'as_of': as_of.isoformat(),
                            'source_url': 'https://query2.finance.yahoo.com/v7/finance/quote'}
            change = number(row.get('regularMarketChangePercent'))
            if change is not None:
                values[name]['change_pct'] = change
        except (KeyError, TypeError, ValueError):
            values[name] = None; gaps.append(name+': timestamped macro reference unavailable')
    return {'values': values, 'gaps': gaps, 'label': 'Dated macro references, not live executable BBO.'}


def _read_json(path):
    """One strict parser for staged evidence, CLI input and replay receipts."""
    from factor_inputs import _read
    return _read(Path(path))


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


def _checked_replay(path, now):
    from adapters.deepseek_adapter import parse_assessments
    from factor_inputs import validate_payload
    obj = _read_json(path)
    if not isinstance(obj, dict) or obj.get('snapshot_sha256') != _seal(obj)['snapshot_sha256']:
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
    if obj.get('covered') != len(rows) or obj.get('requested') != len(obj['inputs']['candidates']):
        raise ValueError('SNAPSHOT_COVERAGE_MISMATCH')
    # Replay never calls a model. The decision-time loader separately rechecks
    # freshness and every candidate gap before considering an existing output.
    return obj


def refresh_public_inputs(state_dir, cfg, now):
    """One bounded pass; retain valid prior facts when a new field fails."""
    from factor_inputs import validate_payload
    root = Path(state_dir)
    deadline = time.monotonic()+P.PUBLIC_INPUT_BUDGET_SECONDS
    gaps = []
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
    result = acquire({'macro': (lambda: _macro(cfg, now), min(8, P.PUBLIC_INPUT_BUDGET_SECONDS))})['macro']
    if result.get('value') is not None:
        try:
            fresh = result['value']
            checked = validate_payload({'as_of': now.isoformat(), 'candidates': [],
                                        'macro': fresh['values']}, now)
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
    tickers = cfg['scan']['universe']
    for start in range(0, len(tickers), P.PUBLIC_BATCH_SIZE):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            gaps.append('Public evidence preparation deadline reached.'); break
        block = tickers[start:start+P.PUBLIC_BATCH_SIZE]
        fetched = acquire({t: (lambda t=t: _news(t, now), min(P.PUBLIC_REQUEST_TIMEOUT+1, remaining)) for t in block})
        failed = False
        for ticker, item in fetched.items():
            if item.get('value') is not None:
                # Preserve independently reviewed tags and dated prior headlines
                # when the provider response contains no usable linked evidence.
                fresh = item['value']
                prior = news.get(ticker, {})
                if not isinstance(fresh, dict):
                    failed = True; gaps.append(ticker+': invalid headline result'); continue
                if isinstance(prior, dict):
                    if prior.get('catalyst_tags'):
                        fresh['catalyst_tags'] = prior['catalyst_tags']
                    if not fresh.get('headlines') and prior.get('headlines'):
                        fresh['headlines'] = prior['headlines']
                        gaps.append(ticker+': no fresh linked headlines; dated prior evidence retained.')
                news[ticker] = fresh
            else:
                failed = True
                gaps.append(ticker+': headline acquisition failed: '+safe_detail(item.get('error', 'UNKNOWN')))
        write_atomic(existing, news)
        if failed:
            gaps.append('Stopped headline acquisition after provider failure; remaining names not queried.'); break
    return gaps


def prepare(state_dir, cfg, *, now=None, inputs=None, refresh=False, evaluator=None):
    from adapters.deepseek_adapter import CANDIDATE_KEYS, parse_assessments, public_payload
    from analyst import analyze_factors
    from factor_inputs import build_from_state, validate_payload
    injected_clock = now is not None
    now = stamp(now or dt.datetime.now(ZoneInfo('America/New_York'))).astimezone(ZoneInfo('America/New_York'))
    if now.time() >= dt.time(9, 30):
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
                obj = _checked_replay(prior, now)
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
                               'prompt_version': P.PROMPT_VERSION, 'status': 'STARTED'})
        deadline = time.monotonic()+P.PREP_BUDGET_SECONDS
        gaps = []
        if refresh and inputs is None:
            try:
                gaps.extend(refresh_public_inputs(root, cfg, now))
            except Exception as exc:
                gaps.append('Public input preparation failed: '+type(exc).__name__)
        try:
            clean = validate_payload(inputs, now) if inputs is not None else build_from_state(root, cfg, now)
        except Exception as exc:
            from factor_inputs import _blank
            clean = _blank(now, 'Candidate preparation failed: '+type(exc).__name__)
        gaps.extend(clean.get('gaps', []))
        candidate_gaps = {t: list(gs) for t, gs in clean.get('candidate_gaps', {}).items()}
        macro = {key: clean.get('macro', {}).get(key) for key in P.MACRO_KEYS}
        try:
            model = load_private_model(root)
            model_ok = True
        except (OSError, ValueError, UnicodeError):
            model = None; model_ok = False
            gaps.append('INVALID_MODEL: no DeepSeek request attempted.')
        eligible = []
        for candidate in clean['candidates']:
            ticker = candidate['ticker']
            if not candidate.get('headlines') and not candidate.get('catalyst_tags'):
                candidate_gaps.setdefault(ticker, []).append('No current unstructured evidence to assess.'); continue
            public = {k: candidate[k] for k in CANDIDATE_KEYS if k in candidate}
            try:
                public_payload([public], macro, clean['as_of'])
            except ValueError:
                candidate_gaps.setdefault(ticker, []).append('Candidate failed DeepSeek public payload validation.'); continue
            eligible.append(public)
        assessments, batches = [], []
        try:
            key_ok = evaluator is not None or load_private_key(root)
        except Exception as exc:
            key_ok = False
            gaps.append('Private DeepSeek credential unavailable: '+type(exc).__name__)
        if not key_ok:
            gaps.append('DEEPSEEK_API_KEY unavailable in environment/private host state.')
        elif model_ok:
            for start in range(0, len(eligible), P.BATCH_SIZE):
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    gaps.append('DeepSeek preparation deadline reached.'); break
                batch = eligible[start:start+P.BATCH_SIZE]
                timeout = min(P.REQUEST_TIMEOUT, remaining)
                try:
                    if evaluator is None:
                        got = acquire({'deepseek': (lambda: analyze_factors(batch, macro, clean['as_of'],
                                            model=model, timeout=timeout), timeout)})['deepseek']
                        response = got.get('value') or {'status': 'UNAVAILABLE', 'assessments': [],
                            'errorcode': 'BOUNDED_REQUEST_FAILURE', 'details': 'Bounded DeepSeek request failed.'}
                    else:
                        response = evaluator(batch, macro, clean['as_of'], model=model, timeout=timeout)
                    if not isinstance(response, dict):
                        raise ValueError('INVALID_BATCH_RESPONSE')
                    metadata = {}
                    for key in ('status', 'errorcode', 'details', 'model', 'request_id',
                                'response_id', 'response_model', 'prompt_version',
                                'schema_version', 'input_sha256', 'close_warning'):
                        if key in response:
                            value = response[key]
                            metadata[key] = safe_detail(value) if isinstance(value, str) else value if value is None or isinstance(value, (int, bool)) else 'INVALID_METADATA'
                    batches.append(metadata)
                    if response.get('status') == 'READY':
                        rows = parse_assessments(encode({'assessments': response['assessments']}), [c['ticker'] for c in batch])
                        assessments.extend(rows)
                        continue
                    reason = 'DeepSeek batch unavailable: '+safe_detail(response.get('errorcode', 'UNKNOWN'))
                except Exception as exc:
                    reason = 'DeepSeek batch failed validation or transport: '+type(exc).__name__
                gaps.append(reason)
                for c in batch:
                    candidate_gaps.setdefault(c['ticker'], []).append(reason)
                break  # No blind retry after timeout/auth/balance/rate-limit.
        covered = {a['ticker'] for a in assessments}
        for candidate in clean['candidates']:
            if candidate['ticker'] not in covered:
                candidate_gaps.setdefault(candidate['ticker'], []).append('No successful model assessment for this candidate.')
        prepared = now if injected_clock or evaluator is not None else dt.datetime.now(ZoneInfo('America/New_York'))
        obj = {'schema_version': P.SCHEMA_VERSION, 'session': now.date().isoformat(),
               'as_of': clean['as_of'], 'prepared_at': prepared.isoformat(),
               'prompt_version': P.PROMPT_VERSION, 'model': model, 'adopted': False,
               'status': 'READY' if assessments and not gaps and not any(candidate_gaps.values()) else
                         'PARTIAL' if assessments else 'UNAVAILABLE',
               'requested': len(clean['candidates']), 'covered': len(assessments),
               'inputs': clean, 'input_sha256': hashlib.sha256(encode(clean).encode()).hexdigest(),
               'assessments': assessments, 'batches': batches,
               'candidate_gaps': {t: sorted(set(map(safe_detail, gs))) for t, gs in candidate_gaps.items()},
               'gaps': sorted(set(map(safe_detail, gaps))),
               'registration': P.DESIGN_PROVENANCE['registration']}
        obj = _seal(obj)
        write_atomic(prior, obj)
        write_atomic(root/'deepseek_snapshot.json', obj)
        write_atomic(attempt, {'session': now.date().isoformat(), 'started_at': now.isoformat(),
                               'finished_at': prepared.isoformat(), 'status': 'COMPLETED',
                               'snapshot_sha256': obj['snapshot_sha256']})
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
    print(encode({k: result[k] for k in ('status', 'requested', 'covered', 'model', 'gaps')}))
    return 0 if result['status']=='READY' else 2


if __name__=='__main__':
    raise SystemExit(main())
