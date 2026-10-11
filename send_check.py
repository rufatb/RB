#!/usr/bin/env python3
"""DID THE HTML ARRIVE? A mechanical check after every Gmail send (day-130).

The session pastes the report's HTML into the Gmail `send_message` call by
hand. On 2026-10-07 it sent the text alone. Gmail then made its own HTML from
the text, and the owner got raw "|" tables and "#" headers instead of the
report. This check turns "did it include the HTML" into a number.

Gmail's `get_message` (METADATA_ONLY) returns the message's `sizeEstimate`.
Measured on real sends:
* 10-09, both parts: 87,539 for 76,014 bytes of files (+15%);
* 10-07, text only: 34,979, about 2.5x its 14 KB text;
* 10-11 test, HTML only: 30,572 for 28,879 bytes, even though the send path
  stripped <style>, classes and backgrounds.

A message is accepted when it reaches 80% of the two files. That leaves room
for the stripping and stays far above a text-only send while the HTML is more
than about twice the text (49 KB against 14 KB today).

    python send_check.py --html H --text T --size-estimate N          the first send
    python send_check.py --html H --size-estimate N --html-only       the HTML resend

Prints OK (exit 0) or HTML_MISSING (exit 2), with the bytes it compared.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FLOOR = 0.8


def expected(html_path, text_path=None):
    """The smallest sizeEstimate a message carrying these files can have."""
    html = len(Path(html_path).read_bytes())
    text = len(Path(text_path).read_bytes()) if text_path else 0
    return {'html_bytes': html, 'text_bytes': text, 'min_size': int(FLOOR * (html + text))}


def verify(html_path, size_estimate, text_path=None):
    e = expected(html_path, text_path)
    ok = int(size_estimate) >= e['min_size']
    return {**e, 'size_estimate': int(size_estimate), 'status': 'OK' if ok else 'HTML_MISSING'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--html', required=True)
    p.add_argument('--text')
    p.add_argument('--size-estimate', type=int, required=True)
    p.add_argument('--html-only', action='store_true',
                   help='check the HTML resend: only the HTML file is expected')
    a = p.parse_args(argv)
    if not a.html_only and not a.text:
        p.error('--text is required unless --html-only')
    out = verify(a.html, a.size_estimate, None if a.html_only else a.text)
    print(json.dumps(out))
    return 0 if out['status'] == 'OK' else 2


if __name__ == '__main__':
    sys.exit(main())
