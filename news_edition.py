"""Bounded morning News Desk publication with source and decision receipts."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
from pathlib import Path
import sys
import time

from dda_protocol import ET, digest, stamp
from factor_news import canonical_url, normalized_title
import news_desk as desk
import newswire as wire
import press_feed as press

VERSION = 'news-desk-edition-v1'
PRODUCTION_PROMPT = desk.SYSTEM_PROMPT + (
    '\nFor every call also include "evidence_quote", an exact excerpt of 16 to 180 characters from that item’s '
    'supplied release text, and "invalidation", a short condition that would undermine your reasoning.'
    ' A featured call requires material, incremental issuer evidence and a specific mechanism.'
)
SEAL_BY = dt.time(9, 43)
MAX_MORNING_SECONDS = 260
MIN_BODY = 300
PRESS_LIMIT = 15
PUBLISHERS = {'newswire.ca', 'www.newswire.ca', 'globenewswire.com', 'www.globenewswire.com',
              'businesswire.com', 'www.businesswire.com', 'newsfilecorp.com', 'www.newsfilecorp.com'}


def local_now():
    return dt.datetime.now(ET)


def edition_path(root, session, late=False):
    return Path(root) / 'news_editions' / f"{session}.{'addendum' if late else 'morning'}.json"


def save_first(path, record):
    from dda_desk import first_write, read
    first_write(path, record)
    return read(path)


def capture(root, now=None, *, final=False):
    """Capture permitted wire channels into private persistent storage."""
    now = now or local_now()
    start, _ = wire.window(now.date())
    import sqlite3
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / 'news_capture.sqlite3', timeout=10) as lease:
        lease.execute('BEGIN EXCLUSIVE')
        if final:
            with ThreadPoolExecutor(max_workers=2) as pool:
                fmp = pool.submit(capture_press, root, now)
                result = wire.collect(start.date(), root=root / 'news_wire', now=now, state_dir=root,
                                      sources=('rss', 'sitemap'), pause=0)
            result['press'] = fmp.result()
        elif now.minute < 10:
            result = wire.collect(start.date(), root=root / 'news_wire', now=now, state_dir=root,
                                  sources=('rss', 'sitemap'), pause=0)
        else:
            rss = wire.collect_rss(root=root / 'news_wire', now=now, state_dir=root, feeds=(wire.RSS_MAIN,))
            result = {'rss': rss, 'archived': rss['archived']}
    return {'checked_at': now.isoformat(), 'sitemap': result.get('sitemap', {}),
            'rss': result.get('rss', {}), 'press': result.get('press', {}), 'archived': result['archived']}


def press_time(value):
    when = stamp(value)
    if when:
        return when
    try:
        return dt.datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
    except ValueError:
        return None


def capture_press(root, now, *, twins=None, get=None):
    """Reconcile the FMP press feed through the same cutoff as the CNW capture."""
    import fmp_client
    from morning_service import atomic
    from us_preopen import load_twins, releases as issuer_releases

    start, end = wire.window(now.date())
    twins = load_twins() if twins is None else twins
    root = Path(root)
    outcomes = {}
    samples = set()
    failures = Counter()
    archived = 0
    try:
        key = fmp_client.load_key(root)
        if not twins:
            failures['missing issuer map'] += 1
        elif not key and get is None:
            failures['unavailable credential'] += 1
        elif now < end:
            failures['read before cutoff'] += 1
        else:
            def read(path, *, symbols, limit):
                try:
                    rows = (get or fmp_client.get)(path, key=key, timeout=4, retries=0,
                                                   symbols=symbols, limit=min(limit, PRESS_LIMIT))
                    if not isinstance(rows, list):
                        raise ValueError('unexpected response')
                    times = [press_time(row.get('publishedDate')) if isinstance(row, dict) else None for row in rows]
                    if any(t is None for t in times):
                        outcomes[symbols] = 'unreadable timestamps'
                    elif len(rows) >= PRESS_LIMIT and min(times) >= start:
                        outcomes[symbols] = 'response capped within window'
                    else:
                        outcomes[symbols] = 'checked'
                    if any(isinstance(row, dict) and row.get('url') and row.get('text') for row in rows):
                        samples.add(symbols)
                    return [{**row, 'publishedDate': when.strftime('%Y-%m-%d %H:%M:%S')}
                            for row, when in zip(rows, times) if when]
                except (OSError, ValueError) as exc:
                    outcomes[symbols] = type(exc).__name__
                    return []

            # Use the same-ISIN issuer mapping and title checks as the existing feed.
            # A missing wire archive here keeps the press receipt source-specific.
            directory = root / 'news_edition_press'
            found, _ = issuer_releases(read, twins, start - dt.timedelta(microseconds=1),
                                       end - dt.timedelta(microseconds=1), directory / 'no-wire')
            archived = press.append(press.rows_from(found), directory)
    except (OSError, ValueError) as exc:
        failures[type(exc).__name__] += 1
    failures.update(status for status in outcomes.values() if status != 'checked')
    expected = {t['us'] for t in twins.values()}
    checked = sum(status == 'checked' for status in outcomes.values())
    if checked and not samples:
        failures['no recent press samples returned by provider'] += 1
    receipt = {'requested_at': now.isoformat(), 'window_start': start.isoformat(),
               'window_end': end.isoformat(), 'checked': checked, 'expected': len(expected),
               'archived': archived, 'failures': dict(failures),
               'complete': bool(expected) and checked == len(expected) and not failures}
    path = root / 'news_editions' / f'{now.date()}.press.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, receipt)
    return receipt


def unavailable(now, reason):
    start, end = wire.window(now.date())
    record = {'edition_version': VERSION, 'session': now.date().isoformat(), 'edition': 'morning',
              'status': 'UNAVAILABLE', 'reason': reason, 'coverage': {'read': False, 'gaps': []},
              'window_start': start.isoformat(), 'window_end': end.isoformat(),
              'sealed_at': now.isoformat(), 'candidates': 0, 'events': 0, 'answered': 0,
              'excluded': {}, 'problems': {}, 'calls': [], 'featured': [], 'prompt_version': VERSION}
    return {**record, 'edition_id': digest(record)}


def releases(root, start, end, *, archive=None, press_archive=None):
    """One issuer event per canonical release across the wire and press archives."""
    from urllib.parse import urlsplit
    wire_rows = wire.read(archive, since=start.date()) + wire.read(Path(root) / 'news_wire', since=start.date())
    press_rows = (press.read(press_archive, since=start.date())
                  + press.read(Path(root) / 'news_edition_press', since=start.date()))
    groups, urls, titles = {}, set(), set()
    for row in wire_rows + press_rows:
        at = stamp(row.get('published_at'))
        ticker = (row.get('tickers') or [None])[0]
        title = row.get('title') or ''
        if not at or not start <= at < end or not ticker or not ticker.endswith('.TO') or not title:
            continue
        if wire.NOT_ISSUER.match(title):
            continue
        try:
            url = canonical_url(row.get('url'))
        except (TypeError, ValueError):
            continue
        if urlsplit(url).hostname not in PUBLISHERS:
            continue
        key = (ticker, normalized_title(title), at.date())
        if url in urls or key in titles:
            continue
        urls.add(url)
        titles.add(key)
        groups.setdefault(ticker, []).append({**row, 'url': url})
    return {ticker: sorted(rows, key=lambda row: stamp(row['published_at']))[-desk.MAX_RELEASES:]
            for ticker, rows in groups.items()}


def issuer_text(release, ticker, root, *, timeout, get=None):
    """Accept same-release FMP text or a publisher body from the allowed wire."""
    import fmp_client
    from urllib.parse import urlsplit
    from us_preopen import load_twins
    from diagnostics import safe_detail

    at = stamp(release['published_at'])
    twin = load_twins().get(ticker) or {}
    source_url = release['url']
    try:
        read = get or fmp_client.get
        rows = read('news/press-releases', key=fmp_client.load_key(root), timeout=timeout, retries=0,
                    symbols=twin.get('us') or ticker, limit=15)
    except (OSError, ValueError):
        rows = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            matched = canonical_url(row.get('url')) == source_url
        except (ValueError, TypeError):
            matched = False
        published = press_time(row.get('publishedDate'))
        text = ' '.join(str(row.get('text') or '').split())
        if matched and published and abs(published - at) <= dt.timedelta(minutes=5) and len(text) >= MIN_BODY:
            return safe_detail(text, desk.BODY_CHARS), 'Matched FMP issuer text'
    if urlsplit(source_url).hostname not in {'newswire.ca', 'www.newswire.ca'}:
        raise ValueError('ISSUER_BODY_UNAVAILABLE')
    import requests
    def fetch(url):
        result = requests.get(url, headers={'User-Agent': wire.USER_AGENT},
                              timeout=timeout, allow_redirects=False)
        if result.status_code != 200:
            raise ValueError(f'PUBLISHER_HTTP_{result.status_code}')
        return result.text
    text = desk.body(source_url, Path(root) / 'news_bodies', fetch=fetch)
    if len(text) < MIN_BODY:
        raise ValueError('ISSUER_BODY_TOO_SHORT')
    return safe_detail(text, desk.BODY_CHARS), 'Publisher body'


def validate(reply, batch):
    wanted = {item['id']: item['ticker'] for item in batch}
    allowed, _ = desk.parse(reply, batch)
    supplied = {item['id']: [row.get('text') or '' for row in item['releases']] for item in batch}
    valid = {}
    rows = reply.get('calls') if isinstance(reply, dict) else None
    if not isinstance(rows, list):
        return {}
    from diagnostics import safe_detail
    for row in rows:
        if not isinstance(row, dict) or row.get('id') not in allowed:
            continue
        ident = row['id']
        evidence, invalidation = row.get('evidence_quote'), row.get('invalidation')
        if (row.get('ticker') == wanted[ident] and isinstance(row.get('material'), bool)
                and allowed[ident]['reason'] and isinstance(invalidation, str) and invalidation.strip()
                and isinstance(evidence, str) and 16 <= len(evidence.strip()) <= 180
                and any(evidence.strip() in text for text in supplied[ident])):
            valid[ident] = {**allowed[ident], 'evidence_quote': evidence.strip(),
                            'invalidation': safe_detail(invalidation, 220)}
    return valid


def answer(events, texts, *, ask=desk.ask, remaining, clock):
    """Retry only missing IDs, within the same model and edition deadline."""
    calls, receipt = {}, Counter()
    pending = desk.items(events, 'full', texts)
    for attempt in range(2):
        retry = []
        for batch in desk.batches(pending):
            started = clock()
            if remaining() < 4:
                receipt['deadline'] += len(batch)
                continue
            try:
                reply, model = ask(batch, timeout=min(35, remaining()), system_prompt=PRODUCTION_PROMPT)
                valid = validate(reply, batch) if model == desk.MODEL else {}
            except Exception as exc:
                receipt[type(exc).__name__] += len(batch)
                valid, model = {}, None
            completed = clock()
            if remaining() <= 0:
                receipt['deadline'] += len(batch)
                continue
            for item in batch:
                ident = item['id']
                if ident in valid:
                    calls[ident] = {**valid[ident], 'model': model, 'asked_at': started.isoformat(),
                                    'answered_at': completed.isoformat()}
                elif attempt == 0:
                    retry.append(item)
            receipt['valid_responses'] += len(valid)
        pending = retry
        if not pending:
            break
    return calls, dict(receipt)


def stage(root, *, now=None, clock=local_now, chart=desk.daily_chart, fetch_body=issuer_text,
          ask=desk.ask, archive=None, press_archive=None, late=False, monotonic=time.monotonic):
    """Seal Part 6 once. The edition is separate from the registered research ledger."""
    from dda_desk import read
    now = (now or clock()).astimezone(ET)
    date = now.date()
    start, end = wire.window(date)
    path = edition_path(root, date, late)
    existing = read(path)
    if existing:
        return existing
    original = read(edition_path(root, date))
    if late and (not original or original.get('status') not in {'PARTIAL', 'UNAVAILABLE'}):
        raise ValueError('NO_INCOMPLETE_MORNING_EDITION')
    if now < end or (late and not dt.time(9, 46) <= now.time() < dt.time(16)):
        raise ValueError('OUTSIDE_EDITION_WINDOW')
    seal = dt.datetime.combine(date, SEAL_BY if not late else dt.time(16), ET)
    if now >= seal:
        raise ValueError('EDITION_DEADLINE_PASSED')
    deadline = monotonic() + min(MAX_MORNING_SECONDS, (seal-now).total_seconds())

    def remaining():
        return min(deadline - monotonic(), (seal - clock()).total_seconds())

    cov = wire.coverage(start, end, state_dir=root, minimum_gap=dt.timedelta(0), kinds={'rss', 'sitemap'})
    press_receipt = read(Path(root) / 'news_editions' / f'{date}.press.json') or {}
    press_checked = stamp(press_receipt.get('requested_at'))
    press_complete = bool(press_receipt.get('complete') and press_checked and end <= press_checked <= now
                          and press_receipt.get('window_start') == start.isoformat()
                          and press_receipt.get('window_end') == end.isoformat())
    cov['press'] = {**press_receipt, 'complete': press_complete}
    groups = releases(root, start, end, archive=archive, press_archive=press_archive)
    if late:
        already_read = {row['ticker']: row.get('release_urls') for row in original.get('calls', [])}
        groups = {ticker: rows for ticker, rows in groups.items()
                  if [row['url'] for row in rows] != already_read.get(ticker)}
    complete_wire = bool(cov['read'] and not cov['gaps'] and not cov['unreadable_lines'])
    if groups and ask is desk.ask:
        import prepare_deepseek
        try:
            prepare_deepseek.load_private_key(root)
        except (OSError, ValueError):
            pass

    def prepare(pair):
        ticker, rows = pair
        if remaining() < 8:
            return None, {}, 'deadline'
        try:
            meta, frame = chart(ticker)
            why = desk.liquid(meta, frame, date)
        except Exception:
            return None, {}, 'liquidity unavailable'
        if why and why != 'no bar for the session':
            return None, {}, why
        texts, sources = {}, []
        for row in rows:
            if remaining() < 8:
                return None, {}, 'body deadline'
            try:
                texts[row['url']], source = fetch_body(row, ticker, root, timeout=min(5, remaining() / 3))
                sources.append(source)
            except Exception:
                return None, {}, 'issuer body unavailable'
        return {'id': f'{date}:{ticker}', 'ticker': ticker, 'releases': rows, 'text_sources': sources}, texts, None

    with ThreadPoolExecutor(max_workers=5) as pool:
        prepared = list(pool.map(prepare, sorted(groups.items())))
    excluded = Counter(reason for _, _, reason in prepared if reason)
    events = [event for event, _, _ in prepared if event]
    texts = {url: content for _, parts, _ in prepared for url, content in parts.items()}
    answered, model_receipt = answer(events, texts, ask=ask, remaining=remaining, clock=clock)
    calls = []
    for event in events:
        response = answered.get(event['id'])
        if not response:
            continue
        releases_ = event['releases']
        cited = next(row for row in releases_ if response['evidence_quote'] in texts[row['url']])
        calls.append({'session': date.isoformat(), 'ticker': event['ticker'], 'arm': 'full', **response,
                      'first_at': cited['published_at'], 'title': cited['title'][:200],
                      'url': cited['url'], 'prompt_version': VERSION,
                      'text_sources': event['text_sources'], 'release_urls': [row['url'] for row in releases_],
                      'evidence_sha256': digest(desk.items([event], 'full', texts))})
    calls.sort(key=desk.order_key)
    qualified = [row for row in calls if row['material']]
    gaps = [name for name, count in excluded.items() if count and name in {
        'deadline', 'body deadline', 'liquidity unavailable', 'issuer body unavailable',
    }]
    if len(answered) != len(events):
        gaps.append('incomplete DeepSeek responses')
    if not complete_wire:
        gaps.append('overnight wire coverage incomplete')
    if not press_complete:
        gaps.append('FMP final press coverage incomplete')
    if late:
        prior = {(row['ticker'], row['side'], row['url']) for row in original.get('calls', [])}
        qualified = [row for row in qualified if (row['ticker'], row['side'], row['url']) not in prior]
        if not qualified:
            raise ValueError('NO_NEW_VERIFIED_MATERIAL_CALLS')
    qualified = qualified[:2]
    status = 'LATE' if late else 'PARTIAL' if gaps and calls else 'UNAVAILABLE' if gaps else 'READY'
    record = {'edition_version': VERSION, 'session': date.isoformat(), 'edition': 'addendum' if late else 'morning',
              'status': status, 'reason': ', '.join(gaps) or None, 'coverage': cov,
              'window_start': start.isoformat(), 'window_end': end.isoformat(), 'sealed_at': clock().isoformat(),
              'candidates': len(groups), 'events': len(events), 'answered': len(answered), 'excluded': dict(excluded),
              'problems': model_receipt, 'calls': calls, 'featured': qualified,
              'prompt_version': VERSION, 'parent_edition_id': original.get('edition_id') if original else None}
    record['edition_id'] = digest(record)
    return save_first(path, record)


def edition_lines(record):
    label = 'Late News Desk update' if record['edition'] == 'addendum' else 'Part 6 — The News Desk'
    out = ['', '## ' + label]
    wire_cov = record['coverage']
    coverage = ('Complete' if wire_cov['read'] and not wire_cov['gaps'] and not wire_cov.get('unreadable_lines')
                else 'Incomplete')
    out.append(f"**{record['status']}** · CNW coverage {coverage.lower()} through the 09:30 ET cutoff · "
               f"{record['answered']} verified reads across {record['candidates']} candidate issuers.")
    press_cov = record['coverage'].get('press') or {}
    if press_cov.get('expected'):
        out.append(f"FMP final coverage · {press_cov['checked']} of {press_cov['expected']} tracked cross-listed names.")
    if record.get('reason'):
        out.append(f"Coverage notes — {record['reason']}.")
    if record['edition'] == 'addendum':
        out.append('Informational update after the morning window. Actual answer times are shown.')
    picks = record['featured']
    if not picks:
        if record['status'] == 'READY':
            out.append('The completed review found no verified material calls.')
        else:
            out.append('The available evidence produced no verified material calls.')
    for row in picks:
        released = stamp(row['first_at']).strftime('%a %H:%M ET')
        answered = stamp(row['answered_at']).strftime('%H:%M ET')
        out += ['', f"**{row['side']} {row['ticker']}** · {released} release · reviewed {answered}",
                f"[{row['title']}]({row['url']})",
                row['reason'], f"Issuer evidence — “{row['evidence_quote']}”",
                f"What would weaken the case — {row['invalidation']}"]
    out.append(f"News Desk receipt {record['edition_id'][:12]}.")
    return out


def verify_render(record, rendered):
    """The same receipt and the same featured names must survive each renderer."""
    import html
    content = html.unescape(rendered)
    receipt = f"News Desk receipt {record['edition_id'][:12]}"
    if receipt not in content or any(row['ticker'] not in content for row in record['featured']):
        raise ValueError('NEWS_DESK_RENDER_MISMATCH')


def audit(root, now=None):
    """Verify the published edition, website export and received HTML receipt."""
    from dda_desk import ROOT, read
    from report_store import Store
    now = now or local_now()
    session = now.date().isoformat()
    report = Store(root).get(session) or {}
    section = ((report.get('intraday') or {}).get('news_desk') or {})
    export = read(ROOT/'data'/'reviews'/'dda'/f'{session}.report.json') or {}
    public = (((export.get('report') or {}).get('intraday') or {}).get('news_desk') or {})
    received = read(Path(root)/'news_editions'/f'{session}.delivery.json') or {}
    ident = section.get('edition_id')
    expected = [pick.get('ticker') for pick in section.get('featured', [])]
    published = bool(ident and public.get('edition_id') == ident and public.get('status') == section.get('status')
                     and [pick.get('ticker') for pick in public.get('calls', [])] == expected)
    verified = bool(ident and received.get('edition_id') == ident and received.get('status') == 'VERIFIED'
                    and received.get('message_id'))
    return {'session': session, 'checked_at': now.isoformat(), 'edition_id': ident,
            'news_status': section.get('status') or 'UNAVAILABLE', 'report_matches_export': published,
            'received_html_verified': verified, 'email_delivery': (Store(root).delivery(session) or {}).get('state')}


def preflight(root, *, now=None):
    """Run low-cost read probes at the actual worker using its configured credentials."""
    import fmp_client
    import os
    import prepare_deepseek
    from smtp_credential import readiness
    now = now or local_now()
    start, end = wire.window(now.date())

    def one(name, probe):
        try:
            return name, {'state': 'READY' if probe() else 'INCOMPLETE'}
        except Exception as exc:
            return name, {'state': 'UNAVAILABLE', 'error_type': type(exc).__name__}

    def yahoo():
        meta, frame = desk.daily_chart(desk.MARKET)
        return (meta.get('currency') == 'CAD' and len(frame) >= 21
                and frame.index[-1].date() >= now.date() - dt.timedelta(days=5))

    def fmp():
        key = fmp_client.load_key(root)
        rows = fmp_client.get('news/press-releases', key, timeout=7, retries=0, symbols='MEOH', limit=5)
        return isinstance(rows, list) and any(isinstance(row, dict) and row.get('url') and row.get('text') for row in rows)

    def model():
        if not prepare_deepseek.load_private_key(root):
            return False
        from openai import OpenAI
        client = OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com',
                        max_retries=0, timeout=7)
        if not any(item.id == desk.MODEL for item in client.models.list().data):
            return False
        import requests
        response = requests.get('https://api.deepseek.com/user/balance',
                                headers={'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY']},
                                timeout=7, allow_redirects=False)
        return response.status_code == 200 and response.json().get('is_available') is True

    probes = {'Yahoo CAD history': yahoo, 'FMP press-text entitlement': fmp,
               'DeepSeek model and balance': model}
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(lambda pair: one(*pair), probes.items()))
    results['Delivery transport'] = {'state': 'SMTP_CONFIGURED' if readiness(root)['ready'] else 'VERIFY_GMAIL_CONNECTOR'}
    cutoff = min(now, end)
    return {'checked_at': now.isoformat(), 'session': now.date().isoformat(), 'probes': results,
            'wire_through_check': wire.coverage(start, cutoff, state_dir=root)}


def main(argv=None):
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('capture', 'final-capture', 'preflight', 'stage', 'seal-unavailable',
                                           'addendum', 'claim-addendum', 'verify-delivery', 'audit'))
    parser.add_argument('--state-dir', default=os.getenv('RB_STATE_DIR') or '.rb-state')
    parser.add_argument('--received-html', type=Path)
    parser.add_argument('--message-id')
    args = parser.parse_args(argv)
    root = Path(args.state_dir)
    try:
        if args.action in {'preflight', 'audit'}:
            from dashboard import is_trading_day
            if not is_trading_day(local_now().date()):
                print(json.dumps({'status': 'NOT_A_TRADING_DAY'}))
                return 0
        if args.action in {'capture', 'final-capture'}:
            record = capture(args.state_dir, final=args.action == 'final-capture')
            print(json.dumps(record))
            ready = (record['sitemap'].get('whole') and record['press'].get('complete')
                     if args.action == 'final-capture'
                     else record['sitemap'].get('whole') or record['rss'].get('read_logged'))
            return 0 if ready else 6
        if args.action == 'preflight':
            from morning_service import atomic
            record = preflight(root)
            path = root / 'news_editions' / f"{record['session']}.preflight.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic(path, record)
            print(json.dumps(record))
            return 0 if all(p['state'] == 'READY' for name, p in record['probes'].items() if name != 'Delivery transport') else 6
        if args.action == 'seal-unavailable':
            now = local_now()
            record = save_first(edition_path(root, now.date()),
                                unavailable(now, 'Source, text, or model checks did not seal by the report deadline'))
            print(json.dumps({'status': record['status'], 'edition_id': record['edition_id']}))
            return 0
        if args.action == 'audit':
            result = audit(root)
            print(json.dumps(result))
            return 0 if result['report_matches_export'] and result['received_html_verified'] and result['news_status'] == 'READY' else 6
        if args.action == 'claim-addendum':
            from dda_desk import read, first_write
            date = local_now().date().isoformat()
            primary = read(root/'news_editions'/f'{date}.delivery.json') or {}
            payload_path = root/'news_editions'/f'{date}.addendum-payload.json'
            payload = read(payload_path)
            if not primary.get('message_id') or not payload:
                raise ValueError('VERIFIED_PRIMARY_EMAIL_AND_ADDENDUM_REQUIRED')
            claim = {'edition_id': payload['edition_id'], 'reply_to_message_id': primary['message_id'],
                     'claimed_at': local_now().isoformat(), 'payload_path': str(payload_path.resolve())}
            if not first_write(root/'news_editions'/f'{date}.addendum-delivery.json', claim):
                print(json.dumps({'status': 'RECONCILE_ADDENDUM_IN_SENT_MAIL'}))
                return 4
            print(json.dumps({'status': 'CLAIMED', **claim}))
            return 0
        if args.action == 'verify-delivery':
            from dda_desk import read
            if not args.received_html or not args.message_id:
                raise ValueError('RECEIVED_HTML_AND_PROVIDER_ID_REQUIRED')
            now = local_now()
            record = read(edition_path(root, now.date()))
            if not record:
                raise ValueError('NO_MORNING_EDITION')
            verify_render(record, args.received_html.read_text(encoding='utf-8'))
            result = save_first(root / 'news_editions' / f'{now.date()}.delivery.json',
                                {'checked_at': now.isoformat(), 'edition_id': record['edition_id'],
                                 'message_id': args.message_id, 'status': 'VERIFIED'})
            print(json.dumps(result))
            return 0
        record = stage(args.state_dir, late=args.action == 'addendum')
        if args.action == 'addendum':
            from daily_render import markdown_html
            path = root / 'news_editions' / f"{record['session']}.addendum-payload.json"
            lines = edition_lines(record)
            save_first(path, {'subject': f"RB News Desk — {record['session']} — coverage update",
                              'edition_id': record['edition_id'], 'text': '\n'.join(lines),
                              'html': markdown_html('\n'.join(lines))})
        print(json.dumps({key: record[key] for key in ('edition_id', 'status', 'candidates', 'answered', 'reason')}))
        return 0 if record['status'] in {'READY', 'LATE'} else 6
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'UNAVAILABLE', 'error': type(exc).__name__}), file=sys.stderr)
        return 6


if __name__ == '__main__':
    raise SystemExit(main())
