#!/usr/bin/env python3
"""Fill Part 2 with REVIEWED catalyst events — leads, quote-checked adds, re-verification.

WHY THIS EXISTS. The biotech monitor has always read "No reviewed catalyst event"
because `biotech.validate_event` admits only evidence-reviewed events and nothing
ever reviewed any. The universe was certified (37 names on 2026-09-23); the
feed that should sit beside it was an empty file.

THE REVIEW STEP IS A SESSION'S JOB; THE CHECKING IS THIS FILE'S.
  --leads        per certified ticker, catalyst-like headlines from the exact-
                 ticker news feed (PDUFA, topline, BLA/NDA, AdCom ...). A lead is
                 a pointer to read, never an event.
  --add FILE     events a reviewer wrote after reading the PRIMARY source. Each
                 must carry `source_quote`: a sentence copied verbatim from
                 `source_url` that states the date. This file RE-FETCHES the page
                 and refuses any event whose quote is not on it — the check that
                 makes an invented date impossible to merge — then runs the
                 registered `validate_event` and merges by `event_id`.
  --reverify     re-fetches every stored event's source; a quote still present
                 refreshes `verified_at` (the 7-day rule), a vanished quote or a
                 passed window drops the event and says so.

Secondary write-ups (MarketBeat, analyst notes) are leads only: the event's
source must be the issuer's own release or FDA. Nothing here infers a date,
predicts an outcome or picks a side. Read-only research.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import biotech

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / 'data' / 'biotech_events.json'
SNAPSHOT = ROOT / 'data' / 'biotech_snapshot.json'
FEED = 'https://feeds.finance.yahoo.com/rss/2.0/headline'
LEAD = re.compile(r'PDUFA|topline|top-line|readout|data (?:expected|in|from)|Phase 3|Phase III|'
                  r'\bBLA\b|\bNDA\b|Advisory Committee|AdCom|target action date|'
                  r'FDA (?:accept|grant|approv|decision|clearance)', re.I)
MIN_QUOTE_CHARS = 30
MAX_PAGE_BYTES = 5_000_000


def _get(url, timeout=20):
    import requests
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html,*/*'},
                     timeout=timeout)
    r.raise_for_status()
    if len(r.content) > MAX_PAGE_BYTES:
        raise ValueError('PAGE_TOO_LARGE')
    return r.text


def page_text(markup):
    """Visible text, whitespace-normalised, entities decoded — what a reader sees."""
    markup = re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>', ' ', markup)
    text = htmllib.unescape(re.sub(r'(?s)<[^>]+>', ' ', markup))
    return _norm(text)


def _norm(text):
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = text.replace('–', '-').replace('—', '-').replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', text).strip().lower()


def quote_on_page(quote, url, fetch=_get):
    """True only when the reviewer's quote appears verbatim on the source page."""
    if not isinstance(quote, str) or len(quote.strip()) < MIN_QUOTE_CHARS:
        raise ValueError('source_quote missing or shorter than %d characters' % MIN_QUOTE_CHARS)
    return _norm(quote) in page_text(fetch(url))


def universe(now=None):
    now = now or dt.datetime.now(ET)
    snap = json.loads(SNAPSHOT.read_text())
    return [s['ticker'] for s in biotech.select_universe(snap, now)]


def leads(tickers, fetch=_get):
    import xml.etree.ElementTree as XT
    out = []
    for t in tickers:
        try:
            root = XT.fromstring(fetch(FEED + '?s=%s&region=US&lang=en-US' % t))
            items = root.find('channel').findall('item')
        except Exception as exc:
            out.append({'ticker': t, 'error': type(exc).__name__})
            continue
        for i in items:
            title = (i.findtext('title') or '').strip()
            if LEAD.search(title):
                out.append({'ticker': t, 'published': (i.findtext('pubDate') or '')[5:16],
                            'title': title, 'link': (i.findtext('link') or '').strip()})
    return out


def load():
    obj = json.loads(EVENTS.read_text()) if EVENTS.exists() else {'schema_version': 1, 'events': []}
    obj.setdefault('events', [])
    return obj


def save(obj):
    from build_biotech import write_atomic
    obj['coverage_note'] = ('Issuer/FDA-sourced scheduled catalysts, each re-fetched and quote-checked '
                            'by biotech_review.py within the last 7 days. Coverage is partial: an '
                            'absent name is not evidence of no upcoming catalyst.')
    write_atomic(EVENTS, obj)


def add(candidates, *, now=None, fetch=_get):
    """Verify each candidate against its own source, validate, merge. Returns a report."""
    now = now or dt.datetime.now(ET)
    obj = load()
    by_id = {e['event_id']: e for e in obj['events']}
    accepted, rejected = [], []
    for c in candidates:
        c = {**c, 'review_status': 'verified', 'verified_at': now.isoformat()}
        try:
            if not quote_on_page(c.get('source_quote'), c.get('source_url', ''), fetch):
                raise ValueError('source_quote is not on the source page')
            biotech.validate_event(c, now)
        except Exception as exc:
            rejected.append({'event_id': c.get('event_id'), 'ticker': c.get('ticker'),
                             'reason': str(exc)[:160] or type(exc).__name__})
            continue
        by_id[c['event_id']] = c
        accepted.append(c['event_id'])
    obj['events'] = sorted(by_id.values(), key=lambda e: (e['window_end'], e['ticker']))
    save(obj)
    return {'accepted': accepted, 'rejected': rejected, 'stored': len(obj['events'])}


def reverify(*, now=None, fetch=_get):
    now = now or dt.datetime.now(ET)
    obj = load()
    kept, dropped = [], []
    for e in obj['events']:
        try:
            if not quote_on_page(e.get('source_quote'), e.get('source_url', ''), fetch):
                raise ValueError('source_quote no longer on the source page')
            e = {**e, 'verified_at': now.isoformat()}
            biotech.validate_event(e, now)
            kept.append(e)
        except Exception as exc:
            dropped.append({'event_id': e.get('event_id'), 'reason': str(exc)[:160]})
    obj['events'] = kept
    save(obj)
    return {'kept': len(kept), 'dropped': dropped}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--leads', action='store_true', help='catalyst-like headlines per certified ticker')
    g.add_argument('--add', metavar='EVENTS_JSON', help='verify and merge reviewed events')
    g.add_argument('--reverify', action='store_true', help='re-check every stored event')
    a = p.parse_args(argv)
    if a.leads:
        out = leads(universe())
    elif a.add:
        rows = json.loads(Path(a.add).read_text())
        out = add(rows if isinstance(rows, list) else rows.get('events', []))
    else:
        out = reverify()
    print(json.dumps(out, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
