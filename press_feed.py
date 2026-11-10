#!/usr/bin/env python3
"""THE PRESS FEED (day-150, owner 2026-11-10; PREREGISTER_day150_morning_decision.md).

The desks, the nominations and the council read each name's headlines from
Yahoo and from the newswire.ca archive (`newswire.py`). The pre-open desk's
source, FMP's press feed for a name's New York symbol, never reached them: on
2026-11-10 the 08:12 email named Aris's reserves and GFL's ended takeover
review, and the 09:00 decision was made without either.

This is that feed kept as an archive, `data/newswire/press/YYYY-MM-DD.jsonl`,
one release per line: url, title, published_at (the feed's time, ET), the
Toronto ticker, the feed's summary. The pre-open desk writes it whenever it
reads the feed (`us_preopen.build`), with its own two tests already applied:
the title starts with the company's name, and it is not a third party's notice.

* The headlines are merged into the staged news after the wire's
  (`merge_into_news`, called by `prepare_deepseek.refresh_public_inputs`).
* The class is recomputed from this archive (`factor_news.classify_headline`),
  never trusted from a staged claim.
* The wire archive's readers (`newswire.read`, the wire card, the news desk,
  PEAD) open `data/newswire/*.jsonl` only; this subdirectory is not theirs, so
  no registered population moves. It rides in every `git add data/newswire/`.

Nothing here calls a network: the desk that reads the feed hands the rows over.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT/'data'/'newswire'/'press'
SOURCE = 'FMP press feed'
MAX_TITLE = 180                 # factor_inputs refuses a longer headline


def _day_file(day, root=None):
    return Path(root or ARCHIVE)/f'{day.isoformat()}.jsonl'


def read(root=None, since=None):
    """Every archived press row (optionally from `since`), oldest file first."""
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


def rows_from(found):
    """The pre-open desk's releases ({ticker: [release]}, already tested as the
    issuer's own and not a notice) as archive rows. Only the feed's rows with a
    real https address: the wire's rows live in the wire archive, and a
    headline without an address cannot be shown to a model."""
    out = []
    for ticker, rows in sorted((found or {}).items()):
        for r in rows or []:
            url, title = str(r.get('url') or ''), ' '.join(str(r.get('title') or '').split())
            if r.get('source') != SOURCE or not url.startswith('https://') or not title:
                continue
            out.append({'url': url, 'title': title[:MAX_TITLE], 'published_at': r['published_at'],
                        'tickers': [ticker], 'summary': str(r.get('text') or '')[:600], 'source': SOURCE})
    return out


def append(rows, root=None):
    """Append rows to their ET day's file; an address already archived is skipped."""
    seen = {r['url'] for r in read(root)}
    written = 0
    for r in sorted(rows, key=lambda r: r['published_at']):
        if r['url'] in seen:
            continue
        day = dt.datetime.fromisoformat(r['published_at']).astimezone(ET).date()
        path = _day_file(day, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as fh:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + '\n')
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
    """Press rows naming `ticker` published in [start, end), oldest first."""
    rows = []
    for r in read(root, since=start.astimezone(ET).date()):
        at = dt.datetime.fromisoformat(r['published_at'])
        if ticker in r.get('tickers', []) and start <= at < end:
            rows.append(r)
    return sorted(rows, key=lambda r: r['published_at'])


def headlines(ticker, now, root=None, *, hours=72):
    """The staged headline form for `ticker`'s press rows of the last `hours`,
    newest first. The class is not set here: `factor_news.classify_headline`
    recomputes it from the archive."""
    rows = releases_for(ticker, now - dt.timedelta(hours=hours), now, root)
    return [{'title': r['title'], 'source_url': r['url'], 'published_at': r['published_at']}
            for r in reversed(rows)]


def merge_into_news(state_dir, tickers, now, root=None, *, maximum=8):
    """Put each name's press rows first in the staged `deepseek_news.json`
    (the wire's merge runs after this one, so the wire's releases end up ahead
    of them). A row whose title the name already carries is not added twice.
    Returns the names that gained a row. Nothing is written when none did."""
    from factor_news import canonical_url, normalized_title
    path = Path(state_dir)/'deepseek_news.json'
    news = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(news, dict):
        raise ValueError('INVALID_STAGED_NEWS')
    gained = []
    for t in tickers:
        press = headlines(t, now, root)
        if not press:
            continue
        entry = news.get(t) if isinstance(news.get(t), dict) else {}
        urls = {canonical_url(h['source_url']) for h in press}
        titles = {normalized_title(h['title']) for h in press}
        rest = [h for h in entry.get('headlines') or []
                if isinstance(h, dict) and canonical_url(h.get('source_url', '')) not in urls
                and normalized_title(str(h.get('title') or '')) not in titles]
        entry = {**entry, 'headlines': (press + rest)[:maximum], 'status': 'READY'}
        entry.setdefault('catalyst_tags', [])
        news[t] = entry
        gained.append(t)
    if gained:
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(news, indent=1, default=str))
        tmp.replace(path)
    return gained
