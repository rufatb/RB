#!/usr/bin/env python3
"""DID THE HTML ARRIVE? A mechanical check after every Gmail send (day-130).

The session pastes the report's HTML into the Gmail `send_message` call by
hand. On 2026-10-07 it sent the text alone. Gmail then made its own HTML from
the text, and the owner got raw "|" tables and "#" headers instead of the
report. This check turns "did it include the HTML" into two facts.

Gmail's `get_message` (MINIMAL) returns the message's `snippet` and
`sizeEstimate`.

THE SNIPPET says which part Gmail rendered. Every sent email since 09-30 shows
it:
* with the HTML, it starts with the HTML's first visible words, "Morning
  research note · not an order RB Daily Report — …" (10-09 report, flash and
  open check);
* without it, it starts with the text file, "# RB Daily Report — 2026-10-07 …".
This works at any size. Size alone could not tell a 4 KB noon email from its
text-only twin: Gmail's header overhead is as large as the difference.

THE SIZE catches an HTML that arrived cut short. Measured:
* 10-09 report, both parts: 87,539 for 76,014 bytes of files (+15%);
* 10-09 flash: 10,568 for 7,803; open check: 6,139 for 4,666;
* 10-07, text only: 34,979, about 2.5x its 14 KB text;
* 10-11 test, HTML only: 30,572 for 28,879 bytes, even though the send path
  stripped <style>, classes and backgrounds.
A message must reach 80% of the two files.

    python send_check.py --html H --text T --size-estimate N --snippet 'S'   the first send
    python send_check.py --html H --size-estimate N --snippet 'S' --html-only   the HTML resend

Prints OK (exit 0) or HTML_MISSING (exit 2), with what it compared. The
command requires --snippet; `verify` without one checks the size alone.
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
from pathlib import Path

FLOOR = 0.8
MATCH = 20      # characters of the HTML's first visible text the snippet must start with


def first_visible(html_text):
    """The words a reader sees first: the body's text, tags stripped."""
    body = re.split(r'<body[^>]*>', html_text, maxsplit=1, flags=re.I)[-1]
    text = re.sub(r'<[^>]+>', ' ', body)
    return ' '.join(_html.unescape(text).split())


def _plain(snippet):
    return ' '.join(_html.unescape(snippet or '').split())


def expected(html_path, text_path=None):
    """The smallest sizeEstimate a message carrying these files can have."""
    html = len(Path(html_path).read_bytes())
    text = len(Path(text_path).read_bytes()) if text_path else 0
    return {'html_bytes': html, 'text_bytes': text, 'min_size': int(FLOOR * (html + text))}


def verify(html_path, size_estimate, text_path=None, snippet=None):
    e = expected(html_path, text_path)
    out = {**e, 'size_estimate': int(size_estimate)}
    reasons = []
    if snippet is not None:
        lead = first_visible(Path(html_path).read_text(encoding='utf-8'))[:MATCH]
        seen = _plain(snippet)
        out.update(html_starts=lead, snippet_starts=seen[:MATCH])
        if not seen.startswith(lead):
            reasons.append('the snippet is not the HTML: Gmail rendered the text part')
    if int(size_estimate) < e['min_size']:
        reasons.append('the message is smaller than its two files: the HTML is missing or cut short')
    out['status'] = 'HTML_MISSING' if reasons else 'OK'
    if reasons:
        out['why'] = '; '.join(reasons)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--html', required=True)
    p.add_argument('--text')
    p.add_argument('--size-estimate', type=int, required=True)
    p.add_argument('--snippet', required=True,
                   help="the first 40 characters of the message's snippet (get_message MINIMAL)")
    p.add_argument('--html-only', action='store_true',
                   help='check the HTML resend: only the HTML file is expected')
    a = p.parse_args(argv)
    if not a.html_only and not a.text:
        p.error('--text is required unless --html-only')
    out = verify(a.html, a.size_estimate, None if a.html_only else a.text, a.snippet)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out['status'] == 'OK' else 2


if __name__ == '__main__':
    sys.exit(main())
