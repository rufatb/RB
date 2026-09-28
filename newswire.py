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

The newswire.ca RSS feed is NOT used: it is PR Newswire's global channel, 20
items (about two minutes of a busy morning), and carried no TSX symbol in the
releases sampled on 2026-09-28. The paginated list at LIST_URL is the Canadian
wire, 100 per page, and reaches back months, which is what makes a replay
possible at all.

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
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import re
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

_CARD = re.compile(
    r'href="(/news-releases/[^"]+-\d+\.html)".*?<small>([^<]+)</small>\s*(.*?)\s*</h3>', re.S)
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


def _text(fragment):
    return ' '.join(htmllib.unescape(re.sub(r'<[^>]+>', ' ', fragment)).split())


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
    """[(url, listed, title)] from one list page, newest first."""
    return [(BASE + href, ' '.join(listed.split()), _text(title))
            for href, listed, title in _CARD.findall(page)]


def listed_date(listed, today):
    """'Aug 10, 2026, 08:29 ET' -> 2026-08-10; a bare '17:39 ET' is today."""
    m = re.match(r'([A-Z][a-z]{2}) (\d{1,2}), (\d{4})', listed)
    if not m:
        return today
    return dt.datetime.strptime(' '.join(m.groups()), '%b %d %Y').date()


def parse_release(page, url, title=None):
    """One archive row, or ValueError naming what the page lacked."""
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
    return {'url': url, 'title': title[:400],
            'published_at': published.astimezone(ET).isoformat(),
            'tickers': symbols(lead), 'source': 'newswire.ca'}


def _get(url, session=None):
    import requests
    r = (session or requests).get(url, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ValueError(f'HTTP_{r.status_code}')
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
    """The overnight window a 09:30 open can not yet have traded: from the
    PRIOR session's 16:00 close to 09:30 on `session`. The prior session is the
    previous weekday; a holiday makes the window longer, never shorter."""
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
        path.write_text(json.dumps(news, indent=1, default=str))
    return gained


# ── collection ───────────────────────────────────────────────────────────────

def collect(since, *, today=None, root=None, fetch=None, max_pages=MAX_PAGES,
            workers=WORKERS, pause=0.5):
    """Walk the list back to `since` (a date), fetch every release page not yet
    archived, append. Failures are COUNTED and returned, never swallowed; a
    failed page is not archived, so the next run retries it."""
    import requests
    session = requests.Session()
    fetch = fetch or (lambda u: _get(u, session))
    today = today or dt.datetime.now(ET).date()
    known = {r['url'] for r in read(root)}
    cards, pages, stop = [], 0, False
    for page in range(1, max_pages + 1):
        listing = parse_list(fetch(LIST_URL.format(page=page)))
        pages += 1
        if not listing:
            break
        for url, listed, title in listing:
            if listed_date(listed, today) < since:
                stop = True
                break
            if url not in known:
                cards.append((url, title))
        if stop:
            break
        time.sleep(pause)
    reached = stop
    failures, rows = {}, []

    def one(card):
        url, title = card
        try:
            return parse_release(fetch(url), url, title), None
        except Exception as exc:     # counted below, never silent (house rule 1)
            code = str(exc) if re.fullmatch(r'[A-Z0-9_]{1,40}', str(exc)) else type(exc).__name__
            return None, code

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row, code in pool.map(one, dict.fromkeys(cards)):
            if row:
                rows.append(row)
            else:
                failures[code] = failures.get(code, 0) + 1
    written = append(rows, root)
    return {'since': since.isoformat(), 'list_pages': pages, 'reached_since': reached,
            'new_releases': len(set(cards)), 'archived': written,
            'with_tsx_symbol': sum(1 for r in rows if r['tickers']),
            'failed': sum(failures.values()), 'failures': failures}


def last_archived(root=None):
    files = sorted(Path(root or ARCHIVE).glob('*.jsonl'))
    return dt.date.fromisoformat(files[-1].stem) if files else None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--collect', action='store_true')
    p.add_argument('--since', type=dt.date.fromisoformat,
                   help='oldest ET date to reach (default: the last archived day, else 3 days back)')
    p.add_argument('--max-pages', type=int, default=MAX_PAGES)
    a = p.parse_args(argv)
    if not a.collect:
        p.print_help()
        return 2
    today = dt.datetime.now(ET).date()
    since = a.since or last_archived() or (today - dt.timedelta(days=3))
    out = collect(since, today=today, max_pages=a.max_pages)
    print(json.dumps(out))
    if not out['reached_since']:
        print(f'NEWSWIRE: list ended before {since} — the archive has a hole', file=sys.stderr)
        return 4
    return 0 if not out['failed'] else 3


if __name__ == '__main__':
    sys.exit(main())
