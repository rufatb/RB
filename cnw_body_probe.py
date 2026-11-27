#!/usr/bin/env python3
"""Does THIS host get newswire.ca's issuer text? A small, polite probe (day-156d).

The owner, 2026-11-26: keep the edition's issuer-text requirement, and "test a
small sample of recent CNW releases from the Azure worker, including CU.TO.
Verify that it returns actual issuer text. If Azure also gets challenged, use an
authorized full-text feed."

From the RB morning container newswire.ca answers its release pages with
HTTP 403 and a bot challenge (11-04 onward; checked again on 11-26), so the
edition sets aside every Toronto-only CNW release. This probe answers the same
question on any other host. It never bypasses anything:

  * one ordinary GET per page, the collector's own User-Agent, no retries,
    no redirects followed, a pause between requests;
  * it STOPS after two refusals, so a challenged host is asked twice at most;
  * it prints the status, whether the release body was found, its length
    against the edition's 300-character minimum, and the first words of it.

    python cnw_body_probe.py                       # 5 recent releases from the archive, CU.TO first
    python cnw_body_probe.py URL [URL ...]         # or the pages you name

It writes nothing. Standalone: without an RB checkout it uses its own copy of
the two regular expressions below and needs URLs on the command line.
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import re
import time

USER_AGENT = 'Mozilla/5.0 (compatible; RB research collector)'   # newswire.USER_AGENT
MIN_BODY = 300                                                     # news_edition.MIN_BODY
CU_RELEASE = ('https://www.newswire.ca/news-releases/canadian-utilities-responds-to-puerto-rico-'
              'supreme-court-decision-regarding-luma-866994237.html')
STOP_AFTER = 2
_BODY = re.compile(r'<section class="release-body[^"]*"[^>]*>(.*?)</section>', re.S)   # newswire._BODY
_CHALLENGE = re.compile(r'captcha|challenge|cf-chl|access denied', re.I)


def text_of(fragment):
    try:
        import newswire
        return newswire._text(fragment)
    except ImportError:
        fragment = re.sub(r'(?is)<(style|script)\b.*?</\1>', ' ', fragment)
        return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', fragment)).split())


def sample(n=5):
    """CU.TO's 11-25 release first, then the newest CNW releases naming a TSX symbol."""
    rows = []
    for path in sorted(glob.glob('data/newswire/*.jsonl'))[-4:]:
        for line in open(path, encoding='utf-8'):
            r = json.loads(line)
            if 'newswire.ca' in (r.get('url') or '') and any(
                    t.endswith('.TO') for t in r.get('tickers') or []):
                rows.append(r['url'])
    urls = [CU_RELEASE] + [u for u in reversed(rows) if u != CU_RELEASE]
    return urls[:n]


def probe(urls, *, get=None, pause=1.0):
    if get is None:
        import requests

        def get(url):
            r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=10, allow_redirects=False)
            return r.status_code, r.text
    out, refused = [], 0
    for i, url in enumerate(urls):
        if refused >= STOP_AFTER:
            out.append({'url': url, 'skipped': f'stopped after {STOP_AFTER} refusals'})
            continue
        if i and pause:
            time.sleep(pause)
        try:
            status, page = get(url)
        except Exception as exc:                      # named, never silent
            out.append({'url': url, 'error': type(exc).__name__})
            refused += 1
            continue
        m = _BODY.search(page or '') if status == 200 else None
        body = text_of(m.group(1)) if m else ''
        row = {'url': url, 'status': status, 'bytes': len(page or ''),
               'challenged': bool(status != 200 and _CHALLENGE.search(page or '')),
               'body_found': bool(m), 'body_chars': len(body), 'meets_min_body': len(body) >= MIN_BODY,
               'opening': body[:90]}
        if status != 200:
            refused += 1
        out.append(row)
    read = [r for r in out if r.get('meets_min_body')]
    return {'asked': sum('skipped' not in r for r in out), 'issuer_text': len(read),
            'verdict': ('ISSUER_TEXT_AVAILABLE' if read and len(read) == len([r for r in out if 'skipped' not in r])
                        else 'PARTIAL' if read else 'REFUSED_OR_NO_TEXT'),
            'pages': out}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('urls', nargs='*')
    p.add_argument('--max', type=int, default=5)
    a = p.parse_args(argv)
    urls = (a.urls or sample(a.max))[:a.max]
    if not urls:
        p.error('no URLs: pass release URLs, or run from an RB checkout')
    print(json.dumps(probe(urls), indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
