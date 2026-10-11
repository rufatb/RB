"""Did the HTML arrive? (day-130). The three real sends the floor was set on."""
from pathlib import Path

import email_render as E
import send_check as S


def files(tmp_path, html, text):
    h, t = tmp_path/'report.html', tmp_path/'report.txt'
    h.write_text('x' * html)
    t.write_text('y' * text)
    return str(h), str(t)


def test_the_three_real_sends_are_classified_as_they_were(tmp_path):
    h, t = files(tmp_path, 62094, 13920)
    assert S.verify(h, 87539, t)['status'] == 'OK'               # 10-09: both parts
    assert S.verify(h, 34979, t)['status'] == 'HTML_MISSING'     # 10-07: the text alone
    (tmp_path/'resend').mkdir()
    h2, _ = files(tmp_path/'resend', 28879, 0)
    assert S.verify(h2, 30572)['status'] == 'OK'                 # 10-11 test: the HTML resend


FLASH = '# RB Council Flash — 2026-10-09\nThe council decided at 09:00 ET (before the open).\n'
WITH_HTML = 'Morning research note · not an order RB Council Flash — 2026-10-09 The council decided'
TEXT_ONLY = '# RB Daily Report — 2026-10-07 Prices are the 09:46 ET snapshot; sent 09:46 ET. ## Top 2 — the council&#39;s'


def small(tmp_path):
    h, t = tmp_path/'report.html', tmp_path/'report.txt'
    h.write_text(E.html_from_text(FLASH))
    t.write_text(FLASH)
    return str(h), str(t)


def test_the_snippet_says_which_part_gmail_rendered(tmp_path):
    """Real snippets: 10-09's flash carried its HTML; 10-07's report did not."""
    h, t = small(tmp_path)
    assert S.verify(h, 10568, t, WITH_HTML)['status'] == 'OK'
    out = S.verify(h, 10568, t, '# RB Council Flash — 2026-10-09 The council decided')
    assert out['status'] == 'HTML_MISSING' and 'text part' in out['why']
    assert S.verify(h, 10568, t, TEXT_ONLY)['status'] == 'HTML_MISSING'


def test_a_small_text_only_send_passes_the_size_and_fails_the_snippet(tmp_path):
    """Why the snippet is required: a 4 KB email's text-only twin clears 80% of it."""
    h, t = small(tmp_path)
    size = int(1.5 * S.expected(h, t)['min_size'])
    assert S.verify(h, size, t)['status'] == 'OK'
    assert S.verify(h, size, t, '# RB Council Flash — 2026-10-09')['status'] == 'HTML_MISSING'


def test_the_command_exits_2_when_the_html_is_missing(tmp_path, capsys):
    h, t = files(tmp_path, 49000, 14000)
    Path(h).write_text(E.html_from_text(FLASH) + 'x' * 49000)
    lead = WITH_HTML[:40]
    assert S.main(['--html', h, '--text', t, '--size-estimate', '35000', '--snippet', lead]) == 2
    assert '"HTML_MISSING"' in capsys.readouterr().out
    assert S.main(['--html', h, '--text', t, '--size-estimate', '60000', '--snippet', lead]) == 0
    assert S.main(['--html', h, '--text', t, '--size-estimate', '60000', '--snippet', TEXT_ONLY[:40]]) == 2
    assert S.main(['--html', h, '--html-only', '--size-estimate', '45000', '--snippet', lead]) == 0


def test_the_email_html_uses_only_what_the_send_path_keeps():
    """The send path strips <style>, class attributes and backgrounds (10-11 test)."""
    body = '# RB Daily Report — 2026-10-13\nPublished 09:46 ET.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n'
    html = E.html_from_text(body)
    assert '<style' not in html and 'class="' not in html
    assert '<td valign="top" style="border-bottom:1px solid #dde4ea">1</td>' in html
    assert 'cellpadding="9"' in html


def test_every_morning_send_is_followed_by_the_html_check():
    root = Path(__file__).resolve().parent.parent
    body = (root/'ROUTINE_PROMPT.md').read_text()
    # the definition, the flash, the open check and STEP 7
    assert body.count('THE HTML CHECK') >= 4 and 'htmlBody is REQUIRED' in body
    assert '--snippet' in body and 'messageFormat MINIMAL' in body
    assert 'mcp__Gmail__get_message' in body                 # loaded at 08:50, never later
    fallbacks = (root/'ROUTINE_FALLBACKS.md').read_text()
    assert fallbacks.count('send_check.py') == 2            # the watchdog and the bridge
    assert fallbacks.count('--snippet') == 2 and 'METADATA_ONLY' not in fallbacks
    noon = (root/'ROUTINE_NOON.md').read_text()
    assert 'send_check.py' in noon and 'noon_check.py --state-dir .rb-state --wait' in noon
    assert '--snippet' in noon and 'METADATA_ONLY' not in noon
