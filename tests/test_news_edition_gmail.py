"""Day-156c: Part 6's edition as the owner RECEIVES it.

Gmail's send path turns every ticker into a google.com/url link (the 11-26
report came back with 34 of them), and the email renderer printed the edition's
**bold** and [title](url) marks raw. Stripping the tags of a linked ticker left
"CU.TO **", so `verify_render` read no call in a correctly delivered email."""
import base64
import datetime as dt
import json
import re
from email.message import EmailMessage

import pandas as pd
import pytest

import email_render
import news_desk
import news_edition as edition
import newswire
import received_html

NOW = dt.datetime(2026, 11, 26, 9, 36, tzinfo=edition.ET)
BODY = 'The issuer announced a material change to committed financing terms. ' * 10


def sealed(tmp_path):
    """One READY edition featuring SHORT CU.TO and LONG MX.TO (the 11-26 replay's shape)."""
    for name, (ticker, host, at) in {'cnw': ('CU.TO', 'www.newswire.ca', '19:39'),
                                     'press': ('MX.TO', 'www.globenewswire.com', '17:01')}.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / '2026-11-25.jsonl').write_text(json.dumps({
            'tickers': [ticker], 'published_at': f'2026-11-25T{at}:00-05:00',
            'title': f'{ticker} announces new transaction terms',
            'url': f'https://{host}/news-releases/{ticker}-876543210.html'}) + '\n')
    start, end = newswire.window(NOW.date())
    newswire.log_read('sitemap', start, end + dt.timedelta(minutes=1), state_dir=tmp_path)
    assert edition.capture_press(tmp_path, NOW, twins={'MX.TO': {'us': 'MEOH', 'name': 'Methanex'}},
                                 get=lambda *a, **k: [{'publishedDate': '2026-11-25 15:00:00',
                                                       'url': 'https://www.globenewswire.com/x.html',
                                                       'text': BODY}])['complete']

    def chart(ticker):
        dates = pd.date_range(end='2026-11-25', periods=23, freq='B')
        return {'instrumentType': 'EQUITY', 'currency': 'CAD'}, pd.DataFrame(
            {'Close': 40., 'Volume': 100_000}, index=dates)

    def ask(batch, **kwargs):
        return {'calls': [{'id': i['id'], 'ticker': i['ticker'],
                           'side': 'SHORT' if i['ticker'] == 'CU.TO' else 'LONG',
                           'confidence': .65, 'material': True, 'reason': 'Financing terms changed.',
                           'evidence_quote': 'a material change to committed financing terms',
                           'invalidation': 'The new terms are withdrawn.'} for i in batch]}, news_desk.MODEL

    record = edition.stage(tmp_path, now=NOW, clock=lambda: NOW, archive=tmp_path / 'cnw',
                           press_archive=tmp_path / 'press', chart=chart, ask=ask,
                           fetch_body=lambda *a, **k: (BODY, 'Verified publisher'))
    assert record['status'] == 'READY' and [r['ticker'] for r in record['featured']] == ['CU.TO', 'MX.TO']
    return record


def as_gmail_returns_it(html):
    """What the send path did to the real 11-26 report: no page wrapper, no
    backgrounds, and each ticker wrapped in a google.com/url redirect link."""
    html = re.sub(r'(?s)^.*?<body[^>]*>|</body>.*$', '', html)
    html = re.sub(r'background(-color)?:[^;"]+;?', '', html)
    return re.sub(r'(?<![\w/.-])([A-Z][A-Z0-9-]*\.TO)\b',
                  r'<a href="https://www.google.com/url?q=http://\1&amp;source=gmail&amp;sa=E">\1</a>', html)


def test_the_email_renders_the_editions_bold_and_links_as_html_not_markdown(tmp_path):
    record = sealed(tmp_path)
    html = email_render.html_from_text('# T\nstamp\n' + '\n'.join(edition.edition_lines(record)))
    assert '<strong>SHORT CU.TO</strong> · Wed 19:39 ET release · reviewed 09:36 ET' in html
    assert ('<a href="https://www.newswire.ca/news-releases/CU.TO-876543210.html" style="color:#1f5c66">'
            'CU.TO announces new transaction terms</a>') in html
    assert '**' not in html and '](https' not in html


def test_inline_marks_escape_everything_else():
    assert email_render._inline('a <b> & **c**') == 'a &lt;b&gt; &amp; <strong>c</strong>'
    assert email_render._inline('[x](javascript:alert(1))') == '[x](javascript:alert(1))'   # https only
    assert email_render._inline('[t"<](https://e.com/a?b=1&c=2)') == (
        '<a href="https://e.com/a?b=1&amp;c=2" style="color:#1f5c66">t&quot;&lt;</a>')


@pytest.mark.parametrize('rendered', ['html', 'raw markdown'])
def test_a_correctly_delivered_edition_verifies_as_gmail_returns_it(tmp_path, rendered):
    record = sealed(tmp_path)
    text = '# T\nstamp\n' + '\n'.join(edition.edition_lines(record))
    html = (email_render.html_from_text(text) if rendered == 'html'
            else '<p>' + '</p><p>'.join(text.splitlines()) + '</p>')       # the 11-26 renderer's raw **
    received = as_gmail_returns_it(html)
    assert received.count('google.com/url') >= 2
    edition.verify_render(record, received)
    with pytest.raises(ValueError, match='RENDER_MISMATCH'):
        edition.verify_render(record, received.replace('SHORT', 'LONG'))
    with pytest.raises(ValueError, match='RENDER_MISMATCH'):
        edition.verify_render(record, received.replace(record['edition_id'][:12], '0' * 12))


def test_the_received_html_part_is_extracted_exactly_from_a_raw_result(tmp_path):
    html = '<table><tr><td>LONG <a href="https://www.google.com/url?q=http://CNQ.TO">CNQ.TO</a> · −0.29% — ok</td></tr></table>'
    msg = EmailMessage()
    msg['Subject'] = 'RB Daily Report — 2026-11-27 — test'
    msg.set_content('# RB Daily Report — 2026-11-27')
    msg.add_alternative(html, subtype='html', cte='quoted-printable')
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip('=')
    saved = tmp_path / 'raw.json'
    saved.write_text(json.dumps({'id': '1a2', 'raw': raw, 'sizeEstimate': 1}))
    out = tmp_path / 'received.html'
    assert received_html.main([str(saved), str(out)]) == 0
    assert out.read_text().rstrip('\n') == html
    assert received_html.html_part(saved.read_text())[:2] == ('1a2', 'RB Daily Report — 2026-11-27 — test')
    saved.write_text(json.dumps({'id': '1a2', 'raw': base64.urlsafe_b64encode(b'Subject: x\n\nplain').decode()}))
    assert received_html.main([str(saved), str(out)]) == 1                 # no text/html part: refused
