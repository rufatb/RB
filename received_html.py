#!/usr/bin/env python3
"""The received HTML of a sent email, from a saved Gmail `get_message` RAW result.

Day-156c. `news_edition.py verify-delivery --received-html PATH` checks the HTML
the owner received, not the file that was dispatched: Gmail's send path drops
the page wrapper and the backgrounds, and turns every ticker into a
google.com/url link (seen on the 11-26 report: 34 links). The connector's
FULL_CONTENT read filters inline CSS, and its RAW read of a full report is too
large to return inline, so the session saves the RAW result to a file. This
reads that file, decodes the message and writes its one text/html part exactly
as received. It never fetches, never sends.

    python received_html.py <saved RAW result (JSON)> <out.html>
"""
from __future__ import annotations

import argparse
import base64
import email
import email.policy
import json
from pathlib import Path


def html_part(raw_result):
    """(message id, subject, html) from a Gmail RAW result: the JSON the
    connector returns, as text or already parsed."""
    data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    raw = data['raw']
    message = email.message_from_bytes(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)),
                                       policy=email.policy.default)
    parts = [p for p in message.walk() if p.get_content_type() == 'text/html']
    if len(parts) != 1:
        raise ValueError(f'EXPECTED_ONE_HTML_PART_FOUND_{len(parts)}')
    return data.get('id'), str(message['Subject'] or ''), parts[0].get_content()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('raw_result', type=Path, help="the saved get_message RAW result")
    p.add_argument('output', type=Path, help='where to write the received text/html part')
    a = p.parse_args(argv)
    try:
        ident, subject, html = html_part(a.raw_result.read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'FAILED', 'error': type(exc).__name__}))
        return 1
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(html, encoding='utf-8')
    print(json.dumps({'status': 'SAVED', 'message_id': ident, 'subject': subject,
                      'html_chars': len(html), 'path': str(a.output)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
