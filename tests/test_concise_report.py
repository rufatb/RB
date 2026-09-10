import copy
import datetime as dt
import json
import pytest
import brief
import email_render
import prepare_delivery as delivery
import deliver_report
from report_store import encode
from test_daily_pipeline import NOW,services


def test_concise_email_retains_full_board_in_attachment_without_recomputing(tmp_path,monkeypatch):
    d=brief.compute(now=NOW,services=services())
    d['intraday']['res']['longs'].append({'t':'ATTACHMENT_ONLY.TO','p_up':.57})
    before=encode(d)
    monkeypatch.setattr(brief,'compute',lambda **kw:pytest.fail('delivery recomputed'))
    p=delivery.artifacts(d,tmp_path,NOW)
    assert 'AAA.TO LONG' in p['text'] and 'BBB.TO SHORT' in p['text']
    assert 'ATTACHMENT_ONLY.TO' not in p['text']
    assert 'ATTACHMENT_ONLY.TO' in p['attachments'][0]['content']
    assert p['attachments'][0]['content']==brief.render_html(delivery.view(d,NOW))
    assert encode(d)==before
    assert len(p['text']) < len(brief.render_text(d))*.7
    assert p['text'].count('INFORMATIONAL')==1
    assert 'MDE80' in p['text'] and 'index' in p['text'] and 'shadow' in p['text']


def test_no_scan_is_not_presented_as_no_opportunities():
    d=brief.compute(now=NOW,no_net=True,services=services())
    text=email_render.text(d)
    assert 'SCAN UNAVAILABLE' in text
    assert 'no qualifying baseline' not in text.lower()
    assert 'No demonstrated predictive edge' not in text  # concise empirical evidence remains


def test_monitor_keeps_exact_five_bullets_and_calendar_is_separate():
    d=brief.compute(now=NOW,services=services())
    d['biotech']['monitor']=[dict(ticker='BIO',bullets=[f'fact {i}' for i in range(5)],
                                  source_url='https://issuer.example/release')]
    body=email_render.text(d)
    section=body.split('### BIO')[1].split('## Evidence')[0]
    assert sum(line.startswith('- **') for line in section.splitlines())==5
    assert '3–6 months' in body and 'directional' in body


def test_recent_closures_are_computed_once_and_not_open_marks():
    s=services();s['positions']=lambda:[dict(ticker='ZYME',side='LONG',status='CLOSED',
        shares='400',entry_px='24.9',exit_px='26.55',exit_date=NOW.date().isoformat())]
    d=brief.compute(now=NOW,no_net=True,services=s)
    assert d['positions']['legs']==[]
    assert d['positions']['recent_closed'][0]['pnl_usd']==pytest.approx(660)
    assert 'Recorded CLOSED ZYME' in email_render.text(d)
    assert '+660.00' in brief.render_text(d)


def test_smtp_has_one_alternative_body_and_the_same_full_attachment():
    d=brief.compute(now=NOW,services=services())
    d=delivery.view(d,NOW+dt.timedelta(minutes=10))
    msg=deliver_report.message(d,'a@example.org','b@example.org')
    assert msg.get_content_type()=='multipart/mixed'
    assert msg.get_payload()[0].get_content_type()=='multipart/alternative'
    attached=list(msg.iter_attachments())
    assert len(attached)==1 and attached[0].get_content_type()=='text/html'
    assert attached[0].get_content().strip()==brief.render_html(d).strip()
    assert 'INFORMATIONAL' in str(msg['Subject'])
    assert msg.get_body(('plain',)).get_content().strip()==email_render.text(d)
