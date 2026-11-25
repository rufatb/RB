"""Day-155b (owner, 2026-11-24): the news desk's table without a second side
column, routine releases apart, its record in one line; a Top 2 pick the news
desk reads the other way flagged; the email's markup written once per row.

Display only: no pick, size, record or rule changes."""
import csv
import re

import email_render as E
import news_desk as N
import top_picks as T


def call(ticker, side='LONG', conf=0.6, material=True, title='A title', reason='A reason'):
    return {'ticker': ticker, 'side': side, 'confidence': conf, 'material': material,
            'title': title, 'reason': reason}


def section(calls, *, layout=True, rec=None, headline=None):
    sec = {'status': 'READY', 'calls': calls, 'headline': headline or {}, 'replay': 'r',
           'record': 'rec', 'preopen': None}
    if layout:
        sec.update(layout=N.LAYOUT, rank_record=rec)
    return sec


REC = {'sessions': 32, 'top': {'calls': 59, 'right': 35, 'mean': 0.598},
       'rest': {'calls': 144, 'right': 68, 'mean': -0.005},
       'routine': {'calls': 84, 'right': 34, 'mean': -0.294}, 't': 1.93}


def test_the_email_table_has_one_side_per_row_numbered_by_score():
    calls = [call('DOL.TO', 'SHORT', 0.55), call('GIB-A.TO', 'LONG', 0.65),
             call('TOY.TO', 'SHORT', 0.5, material=False, title='Spin Master to Participate'),
             call('CM.TO', 'LONG', 0.6)]
    text = '\n'.join(N.lines(section(calls, rec=REC, headline={'DOL.TO': 'LONG'}), concise=True))
    assert 'From the title alone' not in text and 'Material' not in text
    rows = re.findall(r'^\| (\d) \| (LONG|SHORT) (\S+) \|', text, re.M)
    assert rows == [('1', 'LONG', 'GIB-A.TO'), ('2', 'LONG', 'CM.TO'), ('3', 'SHORT', 'DOL.TO')]
    # the routine release is named, with no side
    routine = next(line for line in text.splitlines() if line.startswith('Routine releases'))
    assert 'TOY.TO' in routine and 'SHORT' not in routine and 'LONG' not in routine
    assert 'the top two rows each morning 35 of 59 (+0.60%)' in text
    assert 'routine releases 34 of 84 (-0.29%)' in text and 'Not proven' in text


def test_the_full_report_keeps_the_title_column_and_adds_the_record():
    calls = [call('DOL.TO', 'SHORT', 0.55)]
    text = '\n'.join(N.lines(section(calls, rec=REC, headline={'DOL.TO': 'LONG'})))
    assert 'From the title alone' in text and '| SHORT DOL.TO | 0.55 | yes | LONG |' in text
    assert 'the top two rows each morning' in text


def test_a_section_from_before_renders_as_it_did():
    calls = [call('DOL.TO', 'SHORT', 0.55), call('TOY.TO', 'SHORT', 0.5, material=False)]
    old = section(calls, layout=False, headline={'DOL.TO': 'LONG'})
    text = '\n'.join(N.lines(old, concise=True))
    assert '| Call | Own conf. | Material | From the title alone | Release | Why |' in text
    assert '| SHORT TOY.TO | 0.50 | routine | — |' in text and 'Record so far' not in text


def test_only_routine_releases_say_so():
    text = '\n'.join(N.lines(section([call('TOY.TO', 'SHORT', 0.5, material=False)], rec=None),
                             concise=True))
    assert 'No release the model marked material today.' in text and '| # |' not in text
    assert 'Record so far' not in text


def ledger(path, rows):
    fields = ['session', 'ticker', 'arm', 'side', 'confidence', 'material', 'w945']
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_the_record_is_the_registered_split(tmp_path):
    p = tmp_path / 'calls.csv'
    rows = []
    for s, ys in (('2026-11-02', (1.0, 0.5, -1.0, -0.5)), ('2026-11-03', (0.2, 0.2, 0.0, -0.4)),
                  ('2026-11-04', (0.4, -0.2, 0.6, -0.6)), ('2026-11-05', (9.0, 9.0))):
        for i, y in enumerate(ys):
            rows.append({'session': s, 'ticker': f'T{i}.TO', 'arm': 'full', 'side': 'LONG',
                         'confidence': 0.7 - i * 0.05, 'material': 'True' if i < 3 else 'False',
                         'w945': y})
            rows.append({'session': s, 'ticker': f'T{i}.TO', 'arm': 'headline', 'side': 'LONG',
                         'confidence': 0.5, 'material': 'True', 'w945': -y})
    ledger(p, rows)
    rec = N.rank_record(p, before='2026-11-05')        # 11-05 is today: not in the record
    assert rec['sessions'] == 3
    assert rec['top'] == {'calls': 6, 'right': 5, 'mean': round((1.0 + 0.5 + 0.2 + 0.2 + 0.4 - 0.2) / 6, 3)}
    assert rec['rest'] == {'calls': 6, 'right': 1, 'mean': round((-1.0 - 0.5 + 0.0 - 0.4 + 0.6 - 0.6) / 6, 3)}
    assert rec['routine']['calls'] == 3                 # the fourth call of each session
    assert N.rank_record(tmp_path / 'none.csv') is None


def test_the_order_is_one_key_for_the_email_and_the_record():
    import newsdesk_confidence as C
    rows = [{'ticker': 'B.TO', 'confidence': '0.6', 'material': 'True'},
            {'ticker': 'A.TO', 'confidence': '0.6', 'material': 'True'},
            {'ticker': 'C.TO', 'confidence': '0.7', 'material': 'False'}]
    assert sorted(rows, key=N.order_key) == sorted(rows, key=C.email_key)


TOP = {'claude_leads': True, 'rule_version': 'day144-claude-leads', 'answered': [],
       'picks': [{'side': 'LONG', 'ticker': 'DOL.TO', 'confidence': 0.52, 'reason': 'r'},
                 {'side': 'SHORT', 'ticker': 'HUT.TO', 'confidence': 0.53, 'reason': 'r'}]}


def test_a_news_desk_call_against_a_pick_is_frozen_and_flagged():
    news = section([call('DOL.TO', 'SHORT', 0.55), call('HUT.TO', 'SHORT', 0.6),
                    call('CM.TO', 'LONG', 0.6)])
    sec = T.with_news_conflicts(dict(TOP), news)
    assert sec['news_conflicts'] == [{'ticker': 'DOL.TO', 'pick_side': 'LONG',
                                      'news_side': 'SHORT', 'confidence': 0.55}]
    line = T.news_conflict_line(sec)
    assert line.startswith('⚠ ') and 'SHORT DOL.TO (its own 0.55)' in line
    assert "the Top 2's LONG" in line and 'neither is shown to be more accurate' in line
    assert line in T.table(sec, concise=True)


def test_a_routine_or_agreeing_call_is_no_conflict_and_old_sections_print_nothing():
    news = section([call('DOL.TO', 'SHORT', 0.5, material=False), call('HUT.TO', 'SHORT', 0.6)])
    sec = T.with_news_conflicts(dict(TOP), news)
    assert 'news_conflicts' not in sec and T.news_conflict_line(sec) is None
    assert T.with_news_conflicts(dict(TOP), {'status': 'UNAVAILABLE'}) == TOP
    assert T.with_news_conflicts(None, news) is None
    assert not any('news desk (Part 6)' in line for line in T.table(dict(TOP), concise=True))


def test_the_markup_is_written_once_per_row():
    body = ('# RB Daily Report — 2026-11-25\nSent 09:46 ET.\n\n## Part 1\nA paragraph.\n\n'
            '| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n---\nSmall print.\n')
    html = E.html_from_text(body)
    assert html.count('<th align="left">') == 2 and html.count('<td>') == 4
    assert html.count('<tr valign="top" style="border-bottom:1px solid #dde4ea">') == 2
    assert ('<tr style="border-bottom:2px solid #dde4ea;color:#5c6b7a;font:600 11px/1.4 '
            'Arial,sans-serif;letter-spacing:.07em;text-transform:uppercase">') in html
    # paragraphs take the section's font; the small print keeps its own
    assert '<td style="padding:24px 26px 6px;font:14px/1.6 Arial,sans-serif;color:#17212b">' in html
    assert '<p style="margin:9px 0">A paragraph.</p>' in html
    assert '<p style="font:12px/1.6 Arial,sans-serif;color:#5c6b7a;margin:9px 0">Small print.</p>' in html
