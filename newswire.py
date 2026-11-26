#!/usr/bin/env python3
"""Timestamped issuer press releases from the Canadian wire (newswire.ca), day-118.

Day-117 established that nothing the desks were shown carries signal: the only
news they ever saw was Yahoo RSS commentary with no disclosure time and no
verified issuer. This collects the one source that has both. A Canadian issuer
discloses material news by press release, and CNW (newswire.ca) is where most
TSX issuers put theirs out. Every release page carries its dissemination time
(`<meta name='date'>`, with offset) and the issuer names its own symbol in the
lead paragraph: "Apotex Health Corp. (TSX: APTX) ...".

    python newswire.py --collect                 # since the last archived release
    python newswire.py --collect --since 2026-07-03

The paginated list at LIST_URL is the Canadian wire, 100 per page, and reaches
back months, which is what makes a replay possible at all. It is read first,
every run.

The RSS feeds, when the list is refused (day-156). From about 09:31 ET on
2026-11-25 newswire.ca refuses its list pages to this collector too (HTTP 403;
the release pages since 11-04), and the 11-26 news desk read nothing. Its RSS
feeds still answer: the main feed (RSS_MAIN) and twelve category feeds, each
holding only its latest 20 releases. They are the list's releases: on 11-26
every RSS item older than the archive's newest row (73 of 73, across 13 feeds)
was already archived from the list, under the same URL. (On 2026-09-28 the
main feed was read as "PR Newswire's global channel, no TSX symbol"; it is the
Canadian wire's list, and its symbols are in the description.) A run whose
list is refused reads them (`collect_rss`) and archives each new item as
`source: 'newswire.ca rss'`: the item's minute, title, and the symbols of its
description's opening, the dateline dropped, as a list card's were. Twenty
items are about 90 minutes of a busy morning: on 35 past nights the four
scheduled reads alone (16:20, 08:12, 08:52, 09:31) would have missed 57% of
the news desk's releases. `--watch` reads the main feed every WATCH_EVERY
seconds, but it cannot run overnight: this session's machine is suspended
while the session is idle (the 11-26 watcher's 10:43 pass never came, and the
machine restarted at 11:00), so it is never started automatically.

The news sitemap (day-156b). robots.txt names https://www.newswire.ca/
sitemap-news.xml for crawlers, and it answers this collector: every release
of about the last 72 hours, with its minute, title and the issuer's tagged
tickers. One read covers a whole night. `collect` reads the RSS feeds first
(their openings give the symbols, as the list cards did), then the sitemap
(its tags give the symbols of a release the feeds no longer hold), and asks
for the list only when the sitemap does not reach back to `since`, so a
normal run makes no request newswire.ca refuses. Every read that shows a
stretch of the wire whole is logged (`log_read`), so the news desk can say
which part of its window was not read (`coverage`). Nothing is bypassed: the
feeds and the sitemap are the site's own machine channels.

The archive is `data/newswire/YYYY-MM-DD.jsonl` (ET date of dissemination), one
release per line, committed: a missed day can be back-filled from the list,
but only while the wire still paginates that far. Every release seen is kept,
with or without a symbol, so the archive also says what was NOT a listed
issuer's release and nothing is fetched twice.

What a row claims, and no more:
  published_at  the wire's own dissemination time for the release
  tickers       TSX/TSX-V symbols named in the LEAD (first LEAD_CHARS of the
                body), in Yahoo form (TECK-B.TO, REI-UN.TO, ABC.V). The issuer
                names itself there; a counterparty named there (an acquisition
                target) is also a party to the news. Symbols deeper in the body
                are not collected — a fund naming its holdings is not news
                about them.
A release is not a verified catalyst, its content is not read or judged here,
and a symbol match is not a claim that the market has not already moved.

The list card (day-147b). Each card on the list also carries the release's
opening sentence (`summary`, about 150 characters, the dateline dropped), so
the lead's symbols are taken from it as well, summary first. From about
2026-10-26 the page's lead was read without its symbol on about 40% of the
releases that name one (ENB, VET, MFI, GIB.A on 11-04): the redesigned body
opens with a ~300-character <style> block, which `_text` kept as text until
day-147b, and the site stopped declaring its charset (read as Latin-1, so
"AtkinsRÃ©alis"). From 11-04 09:31 newswire.ca refuses release pages to this
collector (HTTP 403, a bot challenge, never bypassed here). A release whose
page cannot be read is archived FROM ITS CARD:
`source: 'newswire.ca list'`, the card's time (the page's own minute on 2,324
of 2,336 releases checked on 11-05; the other 12 were re-listed later, never
earlier), the card's title, the summary's symbols, and `page_error` naming why.
The summary misses a symbol the 700-character lead names on about 1 release in
30. After BREAK_AFTER refusals in one run the rest of the run's cards are taken
from the list without asking for their pages.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html as htmllib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT/'data'/'newswire'
BASE = 'https://www.newswire.ca'
LIST_URL = BASE + '/news-releases/news-releases-list/?page={page}&pagesize=100'
USER_AGENT = 'Mozilla/5.0 (compatible; RB research collector)'
LEAD_CHARS = 700
MAX_PAGES = 120
WORKERS = 4
TIMEOUT = 20
LIST_SOURCE = 'newswire.ca list'
BREAK_AFTER = 3          # release pages refused (HTTP 403) before a run stops asking

_CARD = re.compile(
    r'href="(/news-releases/[^"]+-\d+\.html)".*?<small>([^<]+)</small>\s*(.*?)\s*</h3>'
    r'(?:\s*<p class="remove-outline">(.*?)</p>)?', re.S)
_LISTED = re.compile(r'(?:([A-Z][a-z]{2}) (\d{1,2}), (\d{4}), )?(\d{1,2}):(\d{2}) ET$')
_DATE = re.compile(r"<meta name=['\"]date['\"] content=\"([^\"]+)\"")
_BODY = re.compile(r'<section class="release-body[^"]*"[^>]*>(.*?)</section>', re.S)
_TITLE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
# "(TSX: ABC)", "TSX: TECK.B", "TSXV: XYZ", "TSX-V: XYZ", "TSX Venture: XYZ",
# "TSX: ABC, ABC.UN" — the symbol list runs until the closing bracket or ';'.
# "TSX/NYSE: CNQ" and "TSX and NYSE: CNQ" name one symbol on two venues. A
# symbol followed by a colon is the NEXT exchange, never a symbol.
_SYM = r'[A-Z][A-Z0-9]{0,6}(?:\.[A-Z]{1,2})?\b(?!\s*:)'
_SYMBOLS = re.compile(r'\b(TSX[\s\-]?V(?:enture)?(?:\s+Exchange)?|TSX)'
                      r'(?:\s*(?:/|and|&)\s*(?:NYSE|NASDAQ|Nasdaq)(?:\s+American)?)?\s*:\s*'
                      r'(' + _SYM + r'(?:\s*(?:,|and)\s*' + _SYM + r')*)')
_ONE = re.compile(_SYM)


_NOT_TEXT = re.compile(r'<(style|script)\b[^>]*>.*?</\1\s*>', re.S | re.I)


def _text(fragment):
    """Visible text: tags dropped, and a <style> or <script> element dropped
    WITH its contents. From ~10-26 every release body opened with a ~300
    character style block, which ate into LEAD_CHARS and pushed the issuer's
    own symbol out of the lead on about 40% of the releases that name one."""
    return ' '.join(htmllib.unescape(re.sub(r'<[^>]+>', ' ', _NOT_TEXT.sub(' ', fragment))).split())


def yahoo_symbol(symbol, venture=False):
    """TECK.B -> TECK-B.TO, REI.UN -> REI-UN.TO, ABC (TSX-V) -> ABC.V."""
    return symbol.replace('.', '-') + ('.V' if venture else '.TO')


def symbols(text):
    """Every TSX / TSX-V symbol named in `text`, Yahoo form, first-seen order."""
    out = []
    for m in _SYMBOLS.finditer(text):
        venture = 'V' in m.group(1).replace('TSX', '', 1)
        for s in _ONE.findall(m.group(2)):
            y = yahoo_symbol(s, venture)
            if y not in out:
                out.append(y)
    return out


def parse_list(page):
    """[(url, listed, title, summary)] from one list page, newest first. The
    summary is the card's opening sentence ('' when the card has none)."""
    return [(BASE + href, ' '.join(listed.split()), _text(title), _text(summary or ''))
            for href, listed, title, summary in _CARD.findall(page)]


def listed_date(listed, today):
    """'Aug 10, 2026, 08:29 ET' -> 2026-08-10; a bare '17:39 ET' is today."""
    m = re.match(r'([A-Z][a-z]{2}) (\d{1,2}), (\d{4})', listed)
    if not m:
        return today
    return dt.datetime.strptime(' '.join(m.groups()), '%b %d %Y').date()


def listed_at(listed, today):
    """'Nov 04, 2026, 06:02 ET' -> 2026-11-04 06:02 ET; a bare '17:39 ET' is
    today. None when the card's time cannot be read."""
    m = _LISTED.match(' '.join(listed.split()))
    if not m:
        return None
    day = (dt.datetime.strptime(' '.join(m.group(1, 2, 3)), '%b %d %Y').date()
           if m.group(1) else today)
    return dt.datetime.combine(day, dt.time(int(m.group(4)), int(m.group(5))), tzinfo=ET)


def opening_symbols(summary, lead=''):
    """The symbols the release's opening names: the list summary's first (it is
    the lead's first sentence), then any further ones in the page's lead."""
    first = symbols(summary or '')
    return first + [s for s in symbols(lead or '') if s not in first]


def list_row(url, listed, title, summary, today, page_error):
    """One archive row from the list card alone, or ValueError."""
    at = listed_at(listed, today)
    if at is None:
        raise ValueError('NO_LIST_TIME')
    if not title:
        raise ValueError('NO_RELEASE_TITLE')
    return {'url': url, 'title': title[:400], 'published_at': at.isoformat(),
            'tickers': symbols(summary), 'source': LIST_SOURCE,
            'summary': summary[:400], 'page_error': page_error}


def parse_release(page, url, title=None, summary=None):
    """One archive row, or ValueError naming what the page lacked. With the
    list card's `summary`, its symbols come first (`opening_symbols`)."""
    d = _DATE.search(page)
    if not d:
        raise ValueError('NO_RELEASE_DATE')
    published = dt.datetime.fromisoformat(d.group(1))
    if published.tzinfo is None:
        raise ValueError('RELEASE_DATE_WITHOUT_OFFSET')
    body = _BODY.search(page)
    if not body:
        raise ValueError('NO_RELEASE_BODY')
    if not title:
        t = _TITLE.search(page)
        title = _text(t.group(1)) if t else ''
    if not title:
        raise ValueError('NO_RELEASE_TITLE')
    lead = _text(body.group(1))[:LEAD_CHARS]
    row = {'url': url, 'title': title[:400],
           'published_at': published.astimezone(ET).isoformat(),
           'tickers': opening_symbols(summary, lead), 'source': 'newswire.ca'}
    if summary:
        row['summary'] = summary[:400]
    return row


def _get(url, session=None):
    import requests
    r = (session or requests).get(url, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ValueError(f'HTTP_{r.status_code}')
    if 'charset' not in (r.headers.get('content-type') or '').lower():
        r.encoding = 'utf-8'   # from ~10-26 the site declares none; requests then reads Latin-1
    return r.text


# ── the archive ──────────────────────────────────────────────────────────────

def _day_file(day, root=None):
    return Path(root or ARCHIVE)/f'{day.isoformat()}.jsonl'


def read(root=None, since=None):
    """Every archived release (optionally from `since`), oldest file first."""
    out = []
    root = Path(root or ARCHIVE)
    if not root.exists():
        return out
    for f in sorted(root.glob('*.jsonl')):
        if since and f.stem < since.isoformat():
            continue
        for line in f.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def append(rows, root=None):
    """Append rows to their ET day's file; a URL already archived is skipped."""
    seen = {r['url'] for r in read(root)}
    written = 0
    for r in sorted(rows, key=lambda r: r['published_at']):
        if r['url'] in seen:
            continue
        day = dt.datetime.fromisoformat(r['published_at']).astimezone(ET).date()
        path = _day_file(day, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as fh:
            fh.write(json.dumps(r, sort_keys=True) + '\n')
        seen.add(r['url'])
        written += 1
    return written


_INDEX = {}


def index(root=None):
    """canonical url -> row. Rebuilt whenever the archive's files change."""
    from factor_news import canonical_url
    root = Path(root or ARCHIVE)
    files = sorted(root.glob('*.jsonl')) if root.exists() else []
    key = (str(root), tuple((f.name, f.stat().st_size) for f in files))
    if _INDEX.get('key') != key:
        rows = {}
        for r in read(root):
            try:
                rows[canonical_url(r['url'])] = r
            except (KeyError, ValueError):
                continue
        _INDEX.clear()
        _INDEX.update(key=key, rows=rows)
    return _INDEX['rows']


def releases_for(ticker, start, end, root=None):
    """Releases naming `ticker` disseminated in [start, end), oldest first."""
    rows = []
    for r in read(root, since=start.astimezone(ET).date()):
        at = dt.datetime.fromisoformat(r['published_at'])
        if ticker in r.get('tickers', []) and start <= at < end:
            rows.append(r)
    return sorted(rows, key=lambda r: r['published_at'])


def window(session):
    """The overnight window before a 09:30 open: from the previous WEEKDAY's
    16:00 to 09:30 on `session`, exactly as PREREGISTER_day118_wire.md fixed it.
    After a holiday Monday that is Monday 16:00, not Friday's close, so a
    long weekend's earlier releases are not EVENTS (the desks are still shown
    them — `headlines` looks back 72 hours). Registered; not changed after."""
    prior = session - dt.timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= dt.timedelta(days=1)
    return (dt.datetime.combine(prior, dt.time(16, 0), tzinfo=ET),
            dt.datetime.combine(session, dt.time(9, 30), tzinfo=ET))


def headlines(ticker, now, root=None, *, hours=72):
    """The factor_inputs headline form for `ticker`'s releases in the last
    `hours` before `now`, newest first. The class is NOT set here —
    `factor_news.classify_headline` recomputes it from the archive."""
    rows = releases_for(ticker, now - dt.timedelta(hours=hours), now, root)
    return [{'title': r['title'], 'source_url': r['url'], 'published_at': r['published_at']}
            for r in reversed(rows)]


def release_cells(tickers, session, root=None):
    """{ticker: {at, title, url}} — each name's NEWEST release in
    `window(session)`, for the report's "Wire release" column. `at` carries the
    weekday when the release came out before the session's own day."""
    start, end = window(session)
    out = {}
    for t in tickers:
        rows = releases_for(t, start, end, root)
        if rows:
            r = rows[-1]
            at = dt.datetime.fromisoformat(r['published_at']).astimezone(ET)
            out[t] = {'at': at.strftime('%H:%M' if at.date() == session else '%a %H:%M'),
                      'title': r['title'], 'url': r['url'], 'releases': len(rows)}
    return out


# ── staging ──────────────────────────────────────────────────────────────────

def merge_into_news(state_dir, tickers, now, root=None, *, maximum=8):
    """Put each name's wire releases FIRST in the staged `deepseek_news.json`.

    Staged news is capped per name BEFORE it is classified, so a release placed
    after eight Yahoo items would be cut unseen. A name with releases and no
    staged entry gets one (status READY). Returns the names that gained a
    release. Nothing is written when no name has one."""
    path = Path(state_dir)/'deepseek_news.json'
    news = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(news, dict):
        raise ValueError('INVALID_STAGED_NEWS')
    from factor_news import canonical_url
    gained = []
    for t in tickers:
        wire = headlines(t, now, root)
        if not wire:
            continue
        entry = news.get(t) if isinstance(news.get(t), dict) else {}
        urls = {canonical_url(h['source_url']) for h in wire}
        rest = [h for h in entry.get('headlines') or []
                if isinstance(h, dict) and canonical_url(h.get('source_url', '')) not in urls]
        entry = {**entry, 'headlines': (wire + rest)[:maximum], 'status': 'READY'}
        entry.setdefault('catalyst_tags', [])
        news[t] = entry
        gained.append(t)
    if gained:
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(news, indent=1, default=str))
        tmp.replace(path)
    return gained


# ── collection ───────────────────────────────────────────────────────────────

def _retrying(fetch, tries=3, pause=2.0):
    def get(url):
        for n in range(tries):
            try:
                return fetch(url)
            except Exception:
                if n == tries - 1:
                    raise
                time.sleep(pause * (2 ** n))
    return get


def _code(exc):
    return str(exc) if re.fullmatch(r'[A-Z0-9_]{1,40}', str(exc)) else type(exc).__name__


def collect_list(since, *, today=None, root=None, fetch=None, max_pages=MAX_PAGES,
                 workers=WORKERS, pause=0.5, break_after=BREAK_AFTER, now=None, state_dir=None):
    """Walk the list back to `since` (a date), fetch every release page not yet
    archived, append. Each list page is archived before the next is read, so a
    failure keeps what came before it. A list page is tried three times, and one
    that keeps failing ends the walk (`list_error`).

    A release page is asked for ONCE. One that cannot be read is archived from
    its list card (`list_row`, counted in `from_list` and `page_failures` by
    code); after `break_after` HTTP 403 refusals the run stops asking for pages
    and takes the rest from their cards. A card that cannot make a row either
    is not archived, is COUNTED in `failures`, and the next run retries it.
    Nothing is swallowed (house rule 1). A walk that archived every card it
    read logs the stretch it showed whole (`log_read`).

    Day-156b: `collect` asks for the list only when the sitemap does not reach
    back to `since`; newswire.ca refuses it to this collector."""
    import threading
    import requests
    session = requests.Session()
    raw = fetch or (lambda u: _get(u, session))
    list_fetch = _retrying(raw, pause=2.0 if pause else 0)
    now = now or dt.datetime.now(ET)
    today = today or now.date()
    known = {r['url'] for r in read(root)}
    pages = seen = written = with_symbol = from_list = 0
    reached, list_error, failures, page_failures = False, None, {}, {}
    oldest = None                      # the oldest card the walk read (its coverage)
    refused, lock = [0], threading.Lock()

    def one(card):
        url, listed, title, summary = card
        if refused[0] >= break_after:
            code = 'NOT_FETCHED_AFTER_HTTP_403'
        else:
            try:
                return parse_release(raw(url), url, title, summary), None
            except Exception as exc:     # counted below, never silent (house rule 1)
                code = _code(exc)
                if code == 'HTTP_403':
                    with lock:
                        refused[0] += 1
        try:
            return list_row(url, listed, title, summary, today, code), code
        except Exception as exc:
            return None, f'{code}+{_code(exc)}'

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for page in range(1, max_pages + 1):
            try:
                listing = parse_list(list_fetch(LIST_URL.format(page=page)))
            except Exception as exc:
                list_error = f'page {page}: {type(exc).__name__}'
                break
            pages += 1
            if not listing:
                break
            cards = []
            for url, listed, title, summary in listing:
                at = listed_at(listed, today)
                if at is not None and (oldest is None or at < oldest):
                    oldest = at
                if listed_date(listed, today) < since:
                    reached = True
                    break
                if url not in known:
                    cards.append((url, listed, title, summary))
                    known.add(url)
            seen += len(cards)
            rows = []
            for row, code in pool.map(one, cards):
                if not row:
                    failures[code] = failures.get(code, 0) + 1
                    continue
                rows.append(row)
                if code is not None:          # archived from its card
                    from_list += 1
                    page_failures[code] = page_failures.get(code, 0) + 1
            written += append(rows, root)
            with_symbol += sum(1 for r in rows if r['tickers'])
            if reached:
                break
            time.sleep(pause)
    out = {'since': since.isoformat(), 'list_pages': pages, 'reached_since': reached,
           'list_error': list_error, 'new_releases': seen, 'archived': written,
           'with_tsx_symbol': with_symbol, 'from_list': from_list,
           'page_failures': page_failures,
           'failed': sum(failures.values()), 'failures': failures}
    if pages and not failures and oldest is not None:
        out['read_logged'] = log_read('list', oldest, now, state_dir=state_dir)
    return out


SOURCES = ('rss', 'sitemap', 'list')


def collect(since, *, today=None, root=None, fetch=None, max_pages=MAX_PAGES,
            workers=WORKERS, pause=0.5, break_after=BREAK_AFTER, now=None, state_dir=None,
            sources=SOURCES):
    """Day-156b: the wire's machine channels first, the list only for a hole.

    1. The RSS feeds (`collect_rss`): each item's description is the release's
       opening, so its symbols are found as a list card's were.
    2. The news sitemap (`collect_sitemap`): every release of about the last
       72 hours, with its minute, title and the issuer's tagged tickers. A
       release already archived from a feed keeps that row (the URL dedupes).
    3. The list walk (`collect_list`), only when the sitemap could not be read
       whole back to `since`. newswire.ca refuses it to this collector, and the
       walk asks for release pages, which it refuses too, so a normal run makes
       no request that is refused.

    `reached_since` is True when the sitemap or the list showed the wire whole
    back to `since`. Counts from each source sit under `rss`, `sitemap` and the
    list's own keys; `archived` and `with_tsx_symbol` are their sums."""
    now = now or dt.datetime.now(ET)
    today = today or now.date()
    out = {'since': since.isoformat(), 'list_pages': 0, 'reached_since': False,
           'list_error': None, 'new_releases': 0, 'archived': 0, 'with_tsx_symbol': 0,
           'from_list': 0, 'page_failures': {}, 'failed': 0, 'failures': {},
           'list_asked': False}
    for name, run in (('rss', collect_rss), ('sitemap', collect_sitemap)):
        if name in sources:
            got = run(root=root, fetch=fetch, now=now, state_dir=state_dir, pause=pause)
            out[name] = got
            out['archived'] += got['archived']
            out['with_tsx_symbol'] += got['with_tsx_symbol']
            out['failed'] += got['failed']
            for k, v in got['failures'].items():
                out['failures'][k] = out['failures'].get(k, 0) + v
    sm = out.get('sitemap')
    start = dt.datetime.combine(since, dt.time(0, 0), tzinfo=ET)
    out['reached_since'] = bool(sm and sm['whole'] and sm['oldest']
                                and dt.datetime.fromisoformat(sm['oldest']) <= start)
    if 'list' in sources and not out['reached_since']:
        out['list_asked'] = True
        walk = collect_list(since, today=today, root=root, fetch=fetch, max_pages=max_pages,
                            workers=workers, pause=pause, break_after=break_after, now=now,
                            state_dir=state_dir)
        for k in ('list_pages', 'list_error', 'new_releases', 'from_list', 'page_failures'):
            out[k] = walk[k]
        out['reached_since'] = walk['reached_since']
        out['archived'] += walk['archived']
        out['with_tsx_symbol'] += walk['with_tsx_symbol']
        out['failed'] += walk['failed']
        for k, v in walk['failures'].items():
            out['failures'][k] = out['failures'].get(k, 0) + v
        if 'read_logged' in walk:
            out['read_logged'] = walk['read_logged']
    return out


# ── the RSS feeds, when the list is refused (day-156; see the docstring) ─────

RSS_MAIN = '/rss/news-releases-list.rss'
RSS_CATEGORIES = tuple(f'/rss/{c}-latest-news/{c}-latest-news-list.rss' for c in (
    'financial-services', 'energy', 'heavy-industry-manufacturing', 'health',
    'consumer-products-retail', 'consumer-technology', 'telecommunications',
    'automotive-transportation', 'entertainment-media', 'environment',
    'policy-public-interest', 'travel'))       # the twelve that answered on 2026-11-26
RSS_FEEDS = (RSS_MAIN,) + RSS_CATEGORIES
RSS_SOURCE = 'newswire.ca rss'
RSS_PAGE_ERROR = 'NOT_FETCHED_READ_FROM_RSS'
_RELEASE_URL = re.compile(r'https://www\.newswire\.ca/news-releases/[^\s"<>?#]+-\d+\.html')
_ITEM = re.compile(r'<item\b[^>]*>(.*?)</item>', re.S)
_CDATA = re.compile(r'\s*<!\[CDATA\[(.*?)\]\]>\s*', re.S)
_DATELINE = re.compile(r'^[^/]{0,160}/\s*(?:CNW|PRNewswire)\s*/\s*(?:--|[-–—])\s*')


def _rss_tag(item, name):
    """An element's content: a CDATA section as written, anything else
    unescaped once (an RSS title carries "&amp;" for "&")."""
    m = re.search(r'<%s(?:\s[^>]*)?>(.*?)</%s>' % (name, name), item, re.S)
    if not m:
        return ''
    c = _CDATA.fullmatch(m.group(1))
    return c.group(1) if c else htmllib.unescape(m.group(1))


def parse_rss(page):
    """[(url, at, title, summary)] from one RSS feed, in its order (newest
    first). `at` is the item's pubDate in ET, None when it cannot be read or
    carries no offset. `summary` is the description as text with its dateline
    ("TORONTO, Nov. 25, 2026 /CNW/ -- ") dropped: the release's opening."""
    out = []
    for item in _ITEM.findall(page):
        try:
            at = email.utils.parsedate_to_datetime(_rss_tag(item, 'pubDate').strip())
            at = at.astimezone(ET) if at.tzinfo else None
        except (TypeError, ValueError, IndexError):
            at = None
        summary = _DATELINE.sub('', _text(_rss_tag(item, 'description')), count=1)
        out.append((_rss_tag(item, 'link').strip(), at, _text(_rss_tag(item, 'title')), summary))
    return out


def rss_row(url, at, title, summary):
    """One archive row from an RSS item, or ValueError naming what it lacked.
    The symbols are the opening's, as a list card's were (`list_row`)."""
    if not _RELEASE_URL.fullmatch(url or ''):
        raise ValueError('NOT_A_RELEASE_URL')
    if at is None:
        raise ValueError('NO_RSS_TIME')
    if not title:
        raise ValueError('NO_RELEASE_TITLE')
    return {'url': url, 'title': title[:400], 'published_at': at.isoformat(),
            'tickers': symbols(summary), 'source': RSS_SOURCE,
            'summary': summary[:400], 'page_error': RSS_PAGE_ERROR, 'tickers_from': 'opening'}


def collect_rss(*, root=None, fetch=None, feeds=RSS_FEEDS, now=None, state_dir=None, pause=0.0):
    """Read the RSS feeds and archive every release not yet archived. A feed
    that fails is named in `feed_errors`, an item that cannot make a row is
    counted in `failures`; nothing is swallowed. The main feed lists the wire's
    latest releases whole, so a read of it logs the stretch from just after
    its oldest item's minute (a burst can be cut inside that minute) to now."""
    import requests
    session = requests.Session()
    raw = fetch or (lambda u: _get(u, session))
    now = now or dt.datetime.now(ET)
    known = {r['url'] for r in read(root)}
    rows, failures, feed_errors = [], {}, {}
    answered = items = main_failed = skipped = 0
    main_from = main_newest = None
    for i, feed in enumerate(feeds):
        if pause and i:
            time.sleep(POLITE_PAUSE)
        try:
            listing = parse_rss(raw(BASE + feed))
            if not listing:
                raise ValueError('EMPTY_FEED')
        except Exception as exc:             # named, never silent (house rule 1)
            feed_errors[feed] = _code(exc)
            continue
        answered += 1
        items += len(listing)
        if feed == RSS_MAIN:
            times = [at for _, at, _, _ in listing if at is not None]
            if len(times) == len(listing):
                main_from = min(times) + dt.timedelta(minutes=1)
                main_newest = max(times)
        for url, at, title, summary in listing:
            if not _RELEASE_URL.fullmatch(url or ''):     # not a release: counted, not a hole
                skipped += 1
                continue
            if url in known:
                continue
            try:
                row = rss_row(url, at, title, summary)
            except ValueError as exc:
                failures[_code(exc)] = failures.get(_code(exc), 0) + 1
                main_failed += feed == RSS_MAIN     # only the main feed's own items void its read
                continue
            known.add(url)
            rows.append(row)
    written = append(rows, root)
    out = {'rss_feeds': len(feeds), 'rss_answered': answered, 'feed_errors': feed_errors,
           'rss_items': items, 'archived': written,
           'with_tsx_symbol': sum(1 for r in rows if r['tickers']),
           'oldest_new': min((r['published_at'] for r in rows), default=None),
           'failed': sum(failures.values()), 'failures': failures, 'skipped': skipped}
    if main_from is not None and not main_failed:
        out['newest'] = main_newest.isoformat()
        if dt.timedelta(0) <= now - main_newest <= MAX_PUBLICATION_LAG:
            out['read_logged'] = log_read('rss', main_from, now, state_dir=state_dir)
    return out


# ── the news sitemap (day-156b) ──────────────────────────────────────────────
#
# robots.txt (2026-11-26) disallows nothing but one template file and names
# https://www.newswire.ca/sitemap-news.xml for crawlers: an index of pages of
# 100 releases each, about the last 72 hours of the wire (409 on 11-26), each
# with its URL, minute (`news:publication_date`, with offset), title and the
# issuer's tagged tickers (`news:stock_tickers`, "Toronto:EMP.A,NASDAQ:X").
# It answers this collector. Checked on 11-26 against the archive's stretch
# collected from the list (11-23 11:00 → 11-25 09:26): all 276 archived
# releases are in it at the same minute, plus one correction notice the list
# never showed. Where the opening named a TSX symbol (34 releases), the first
# tagged TSX symbol was the same one on all 34. The tags also name a symbol on
# 38 of the 277 whose opening named none: the regulator's halt and resumption
# notices (given no symbol here, as their openings carry none), fund families'
# distribution notices, and some corporate notices of large issuers.

SITEMAP_URL = BASE + '/sitemap-news.xml'
SITEMAP_SOURCE = 'newswire.ca sitemap'
SITEMAP_PAGE_ERROR = 'NOT_FETCHED_READ_FROM_SITEMAP'
SITEMAP_MAX_PAGES = 12
MAX_PUBLICATION_LAG = dt.timedelta(minutes=45)
POLITE_PAUSE = 0.25
_SM_PAGE = re.compile(r'<loc>\s*(https://www\.newswire\.ca/sitemap-news\.xml\?page=\d+)\s*</loc>')
_SM_URL = re.compile(r'<url>(.*?)</url>', re.S)
NOT_ISSUER = re.compile(r'^\s*Canadian Investment Regulatory Organization\b', re.I)
_TAG_VENUES = {'Toronto': False, 'TorontoVE': True}


def tagged_symbols(field):
    """The Toronto and TSX Venture symbols of a `news:stock_tickers` field, in
    its order, Yahoo form: 'Toronto:EMP.A,TorontoVE:GSD,NASDAQ:X' -> ['EMP-A.TO',
    'GSD.V']. Other venues are dropped."""
    out = []
    for part in (field or '').split(','):
        venue, _, sym = part.strip().partition(':')
        sym = sym.strip()
        if venue in _TAG_VENUES and re.fullmatch(r'[A-Z][A-Z0-9]{0,6}(?:\.[A-Z]{1,2})*', sym):
            y = yahoo_symbol(sym, _TAG_VENUES[venue])
            if y not in out:
                out.append(y)
    return out


def parse_sitemap(page):
    """[(url, at, title, stock_tickers, keywords)] from one sitemap page.
    `at` is the publication minute in ET, None when unreadable or without an
    offset."""
    out = []
    for entry in _SM_URL.findall(page):
        def tag(name):
            return _rss_tag(entry, name).strip()
        try:
            at = dt.datetime.fromisoformat(tag('news:publication_date'))
            at = at.astimezone(ET) if at.tzinfo else None
        except ValueError:
            at = None
        out.append((htmllib.unescape(tag('loc')), at, _text(tag('news:title')),
                    tag('news:stock_tickers'), _text(tag('news:keywords'))))
    return out


def sitemap_row(url, at, title, stock_tickers, keywords=''):
    """One archive row from a sitemap entry, or ValueError naming what it
    lacked. Its symbols are the issuer's tags; a regulator's notice gets none."""
    if not _RELEASE_URL.fullmatch(url or ''):
        raise ValueError('NOT_A_RELEASE_URL')
    if at is None:
        raise ValueError('NO_SITEMAP_TIME')
    if not title:
        raise ValueError('NO_RELEASE_TITLE')
    return {'url': url, 'title': title[:400], 'published_at': at.isoformat(),
            'tickers': [] if NOT_ISSUER.match(title) else tagged_symbols(stock_tickers),
            'source': SITEMAP_SOURCE, 'stock_tickers': (stock_tickers or '')[:400],
            'keywords': (keywords or '')[:200], 'page_error': SITEMAP_PAGE_ERROR,
            'tickers_from': 'tag'}


def collect_sitemap(*, root=None, fetch=None, now=None, state_dir=None, pause=0.0):
    """Read the news sitemap's index and pages, and archive every release not
    yet archived. A page that fails is named in `page_errors`; an entry that
    cannot make a row is counted in `failures`. Read whole (every page answered
    and every entry made a row), it logs the stretch from just after its oldest
    minute to now, and `whole` is True."""
    import requests
    session = requests.Session()
    raw = fetch or (lambda u: _get(u, session))
    now = now or dt.datetime.now(ET)
    out = {'pages': 0, 'answered': 0, 'page_errors': {}, 'entries': 0, 'archived': 0,
           'with_tsx_symbol': 0, 'oldest': None, 'failed': 0, 'failures': {}, 'whole': False}
    try:
        advertised = list(dict.fromkeys(_SM_PAGE.findall(raw(SITEMAP_URL))))
        pages = advertised[:SITEMAP_MAX_PAGES]
        if not pages:
            raise ValueError('NO_SITEMAP_PAGES')
    except Exception as exc:                  # named, never silent (house rule 1)
        out['page_errors'][SITEMAP_URL] = _code(exc)
        return out
    out['pages'] = len(pages)
    out['pages_advertised'] = len(advertised)
    known = {r['url'] for r in read(root)}
    rows, times = [], []
    for page in pages:
        if pause:
            time.sleep(POLITE_PAUSE)
        try:
            entries = parse_sitemap(raw(page))
            if not entries:
                raise ValueError('EMPTY_SITEMAP_PAGE')
        except Exception as exc:
            out['page_errors'][page] = _code(exc)
            continue
        out['answered'] += 1
        out['entries'] += len(entries)
        for url, at, title, tickers, keywords in entries:
            if not _RELEASE_URL.fullmatch(url or ''):     # not a release: counted, not a hole
                out['skipped'] = out.get('skipped', 0) + 1
                continue
            if at is not None and at <= now:
                times.append(at)
            else:
                key = 'NO_SITEMAP_TIME' if at is None else 'FUTURE_SITEMAP_TIME'
                out['failures'][key] = out['failures'].get(key, 0) + 1
                continue
            if url in known:
                continue
            try:
                row = sitemap_row(url, at, title, tickers, keywords)
            except ValueError as exc:
                out['failures'][_code(exc)] = out['failures'].get(_code(exc), 0) + 1
                continue
            known.add(url)
            rows.append(row)
    out['archived'] = append(rows, root)
    out['with_tsx_symbol'] = sum(1 for r in rows if r['tickers'])
    out['failed'] = sum(out['failures'].values())
    if times:
        out['oldest'] = min(times).isoformat()
        out['newest'] = max(times).isoformat()
    out['whole'] = bool(times and len(pages) == len(advertised)
                        and not out['page_errors'] and not out['failed']
                        and now - max(times) <= MAX_PUBLICATION_LAG)
    if out['whole']:
        out['read_logged'] = log_read('sitemap', min(times) + dt.timedelta(minutes=1), now,
                                      state_dir=state_dir)
    return out


# ── what was read whole, for the news desk's coverage (day-156) ──────────────

READS = 'newswire_reads.jsonl'


def _state_dir(state_dir=None):
    return Path(state_dir or os.environ.get('RB_STATE_DIR') or ROOT/'.rb-state')


def log_read(kind, covers_from, at, *, state_dir=None):
    """Record that a read at `at` showed the wire whole from `covers_from`.
    The log lives in the state directory: a reset wipes it, and the news desk
    then says its coverage is unknown. False when it could not be written."""
    try:
        path = _state_dir(state_dir)/READS
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as fh:
            fh.write(json.dumps({'kind': kind, 'from': covers_from.isoformat(),
                                 'to': at.isoformat()}) + '\n')
        return True
    except OSError:
        return False


def coverage(start, end, *, state_dir=None, minimum_gap=dt.timedelta(minutes=1), kinds=None):
    """Which part of [start, end) no logged read showed whole. `read` is False
    when no read touched the window at all; `gaps` are the stretches of a
    minute or more that none covered, and `uncovered_minutes` their total."""
    spans, bad = [], 0
    try:
        lines = (_state_dir(state_dir)/READS).read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            r = json.loads(line)
            if not isinstance(r, dict):
                raise ValueError('invalid coverage receipt')
            if kinds is not None and r.get('kind') not in kinds:
                continue
            a, b = dt.datetime.fromisoformat(r['from']), dt.datetime.fromisoformat(r['to'])
            if a.tzinfo is None or b.tzinfo is None or b <= a:
                raise ValueError('invalid coverage interval')
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        if b > start and a < end:
            spans.append((max(a, start), min(b, end)))
    gaps, cur = [], start
    for a, b in sorted(spans):
        if a > cur:
            gaps.append((cur, a))
        cur = max(cur, b)
    if cur < end:
        gaps.append((cur, end))
    gaps = [(a, b) for a, b in gaps if b - a >= minimum_gap]
    return {'read': bool(spans),
            'gaps': [[a.isoformat(), b.isoformat()] for a, b in gaps],
            'uncovered_minutes': int(sum((b - a).total_seconds() for a, b in gaps) // 60),
            'unreadable_lines': bad}


# ── the watcher (day-156) ────────────────────────────────────────────────────

WATCH_EVERY = 600                # seconds between reads of the main feed
WATCH_CATEGORIES_EVERY = 3600    # and of the twelve category feeds
WATCH_UNTIL = dt.time(18, 5)     # past the evening releases of the next session
WATCH_FILE = 'newswire_watch.json'
WATCH_LOG = 'newswire_watch.log'


def watch_until(now):
    """The deadline a start sets: WATCH_UNTIL on the first weekday whose 09:35
    is still ahead, so a Friday evening's watcher reads through the weekend."""
    d = now.astimezone(ET).date()
    while d.weekday() >= 5 or dt.datetime.combine(d, dt.time(9, 35), tzinfo=ET) <= now:
        d += dt.timedelta(days=1)
    return dt.datetime.combine(d, WATCH_UNTIL, tzinfo=ET)


def _alive(pid):
    """True when `pid` is a running watcher (a reused pid is not)."""
    try:
        cmd = Path(f'/proc/{int(pid)}/cmdline').read_bytes().split(b'\0')
    except (OSError, ValueError, TypeError):
        return False
    return b'--watch' in cmd and any(c.endswith(b'newswire.py') for c in cmd)


def _write_json(path, data):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def start_watch(now=None, *, state_dir=None, popen=subprocess.Popen, alive=_alive):
    """Start the watcher, detached, or move a running one's deadline later.
    'started', 'extended', or a code naming why not. It never raises: the
    collection it rides on must finish whatever happens here."""
    now = now or dt.datetime.now(ET)
    state = _state_dir(state_dir)
    lock = state/'newswire_watch.lock'
    try:
        state.mkdir(parents=True, exist_ok=True)
        try:
            lock.mkdir()
        except FileExistsError:            # a start died holding it: take it after a minute
            if time.time() - lock.stat().st_mtime < 60:
                return 'BUSY'
            lock.rmdir()
            lock.mkdir()
    except OSError as exc:
        return 'NOT_STARTED_' + type(exc).__name__
    try:
        path = state/WATCH_FILE
        try:
            cur = json.loads(path.read_text())
        except (OSError, ValueError):
            cur = {}
        until = watch_until(now)
        try:
            until = max(until, dt.datetime.fromisoformat(cur.get('until') or ''))
        except (TypeError, ValueError):
            pass
        if alive(cur.get('pid')):
            _write_json(path, {**cur, 'until': until.isoformat()})
            return 'extended'
        with (state/WATCH_LOG).open('ab') as log:
            proc = popen([sys.executable, str(Path(__file__).resolve()), '--watch',
                          '--state-dir', str(state)],
                         cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True, close_fds=True)
        _write_json(path, {'pid': proc.pid, 'until': until.isoformat(),
                           'started_at': now.isoformat()})
        return 'started'
    except OSError as exc:
        return 'NOT_STARTED_' + type(exc).__name__
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass


def watch(*, state_dir=None, root=None, fetch=None, clock=None, sleep=time.sleep,
          every=WATCH_EVERY, categories_every=WATCH_CATEGORIES_EVERY, me=None):
    """Read the RSS feeds until the control file's deadline: the main feed
    every `every` seconds, all of them every `categories_every`. One JSON line
    a pass. 'DONE' at the deadline; 'REPLACED' when the control file names
    another process or is gone, so two watchers never run on."""
    clock = clock or (lambda: dt.datetime.now(ET))
    me = os.getpid() if me is None else me
    path = _state_dir(state_dir)/WATCH_FILE

    def control():
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
    for _ in range(20):                    # start_watch writes the pid just after the spawn
        if control().get('pid') == me:
            break
        sleep(0.5)
    last_all = None
    while True:
        cur = control()
        if cur.get('pid') != me:
            return 'REPLACED'
        now = clock()
        try:
            until = dt.datetime.fromisoformat(cur['until'])
        except (KeyError, TypeError, ValueError):
            return 'NO_DEADLINE'
        if now >= until:
            return 'DONE'
        due = last_all is None or (now - last_all).total_seconds() >= categories_every
        feeds = RSS_FEEDS if due else (RSS_MAIN,)
        try:
            out = collect_rss(root=root, fetch=fetch, feeds=feeds, now=now, state_dir=state_dir)
            if due:
                last_all = now
        except Exception as exc:            # this pass is lost, logged; the next tries again
            out = {'error': _code(exc)}
        print(json.dumps({'at': now.isoformat(), 'feeds': len(feeds), **out}), flush=True)
        sleep(every)


def last_archived(root=None):
    files = sorted(Path(root or ARCHIVE).glob('*.jsonl'))
    return dt.date.fromisoformat(files[-1].stem) if files else None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--collect', action='store_true')
    p.add_argument('--since', type=dt.date.fromisoformat,
                   help='oldest ET date to reach (default: the last archived day, else 3 days back)')
    p.add_argument('--max-pages', type=int, default=MAX_PAGES)
    p.add_argument('--watch', action='store_true',
                   help='read the RSS feeds until the deadline start_watch set (day-156). Never '
                        'started automatically since day-156b: an idle session\'s machine is '
                        'suspended, and the sitemap covers the night')
    p.add_argument('--start-watch', action='store_true',
                   help='start the watcher, or move a running one\'s deadline later')
    p.add_argument('--state-dir', help='default: $RB_STATE_DIR, else .rb-state')
    a = p.parse_args(argv)
    if a.watch:
        print(json.dumps({'watch': watch(state_dir=a.state_dir)}))
        return 0
    if a.start_watch:
        print(start_watch(state_dir=a.state_dir))
        return 0
    if not a.collect:
        p.print_help()
        return 2
    today = dt.datetime.now(ET).date()
    since = a.since or last_archived() or (today - dt.timedelta(days=3))
    out = collect(since, today=today, max_pages=a.max_pages, state_dir=a.state_dir)
    print(json.dumps(out))
    sm, rss = out.get('sitemap') or {}, out.get('rss') or {}
    if not out['reached_since']:
        if sm.get('answered') or rss.get('rss_answered') or out['list_pages']:
            print(f"NEWSWIRE: the wire was read only in part back to {since}: the sitemap "
                  f"{sm.get('answered', 0)} of {sm.get('pages', 0)} page(s) "
                  f"({sm.get('page_errors') or 'no page error'}), the RSS feeds "
                  f"{rss.get('rss_answered', 0)} of {rss.get('rss_feeds', 0)}, the list "
                  f"{out['list_error'] or 'not needed'} — a release may be missing",
                  file=sys.stderr)
            return 6
        print('NEWSWIRE: nothing answered (the sitemap, the RSS feeds and the list) — '
              'the wire was not read', file=sys.stderr)
        return 4
    if out['failed']:
        return 3
    if out['from_list']:
        print(f"NEWSWIRE: {out['from_list']} release(s) archived from the list card "
              f"(pages: {out['page_failures']}) — titles, times and symbols, no body",
              file=sys.stderr)
        return 5
    return 0


if __name__ == '__main__':
    sys.exit(main())
