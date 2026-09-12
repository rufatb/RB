"""Reporting boundaries retain evidence without a second acquisition or invented facts."""
import copy
import datetime as dt
import json
import pytest
import brief
import daily_job
import deliver_report
import email_render
from report_store import Store, encode
from test_daily_pipeline import NOW, services, market_row


def position(ticker='AAA.TO'):
    return dict(id='1',ticker=ticker,side='LONG',shares='10',entry_px='100',
                entry_date='2026-09-01',status='OPEN')


def test_build_returns_one_digest_from_any_working_directory(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    s=services(); counts=[]
    original=s['intraday']
    s['intraday']=lambda cfg:counts.append('intraday') or original(cfg)
    old={}
    d=brief.build(now=NOW,services=s,digest=old)
    assert isinstance(d,brief.Digest) and old==d
    before=encode(d)
    assert 'Part 1' in brief.render_text(d)
    assert 'Part 2' in brief.render_html(d)
    assert 'Part 1' in email_render.html(d)
    assert counts==['intraday'] and s['market'].calls==1
    assert encode(d)==before


def test_malformed_quote_cannot_erase_valid_siblings():
    s=services()
    s['market'].get=lambda ts:{t:None if t=='AAA.TO' else market_row(t) for t in ts}
    d=brief.build(now=NOW,services=s)
    by={l['ticker']:l for l in d['intraday']['legs']}
    assert by['AAA.TO']['quote']['status']=='UNAVAILABLE'
    assert by['BBB.TO']['quote']['status']=='OK'
    assert d['intraday']['benchmark']['status']=='OK'


def test_malformed_position_retains_sibling_and_independent_sections():
    s=services(); rows=[position(),{**position('BAD.TO'),'shares':'broken'}]
    before=copy.deepcopy(rows);s['positions']=lambda:rows
    d=brief.build(now=NOW,services=s)
    assert [p['ticker'] for p in d['positions']['legs']]==['AAA.TO']
    assert d['positions']['invalid_rows']==1 and d['positions']['status']=='PARTIAL'
    assert d['positions']['gaps'] and len(d['intraday']['legs'])==2
    assert rows==before and 'positions: ValueError' in brief.render_text(d)


def test_unreadable_positions_are_unknown_not_confirmed_flat():
    s=services();s['positions']=lambda:(_ for _ in ()).throw(OSError('unreadable'))
    d=brief.build(now=NOW,services=s)
    assert d['positions']['status']=='UNAVAILABLE'
    assert 'holdings are unknown' in d['positions']['verification']
    assert d['readiness']['status']=='PARTIAL'


@pytest.mark.parametrize('date',[NOW.date().isoformat(),'invalid',None])
def test_invalid_session_record_blocks_reselection_without_rewriting(date):
    s=services(); rows=[{'date':date,'ticker':'TRP.TO','side':'LONG','shares':'bad'}]
    s['ledger']=lambda:rows
    s['intraday']=lambda cfg:pytest.fail('invalid original record cannot authorize repicking')
    d=brief.build(now=NOW,services=s)
    assert d['intraday']['ledger_status']['selection_blocked']
    assert 'fresh selection blocked' in d['intraday']['res']['coverage_fail']
    assert rows[0]['shares']=='bad'


def test_nonfinite_ledger_row_does_not_destroy_independent_sections():
    s=services()
    rows=[dict(date='2026-09-01',ticker='TRP.TO',side='LONG',r1=float('nan'))]
    s['ledger']=lambda:rows
    d=brief.build(now=NOW,services=s)
    assert d['intraday']['ledger_status']['invalid_rows']==1
    assert d['provenance']['ledger_snapshot_sha256'] is None
    assert len(d['intraday']['legs'])==2
    assert d['readiness']['status']=='PARTIAL'
    assert 'NaN' not in encode(d)


def test_persistent_compute_fault_uses_no_second_model_pass(tmp_path,monkeypatch):
    calls=[]
    def broken(**kw):
        calls.append(kw)
        raise RuntimeError('persistent schema defect')
    monkeypatch.setattr(brief,'compute',broken)
    monkeypatch.setattr(brief.ledger,'load',lambda:[])
    monkeypatch.setattr(brief.positions,'load',lambda:[])
    d=daily_job.run(tmp_path/'state',tmp_path/'out',now=NOW)
    assert len(calls)==1
    assert d['report_status'].startswith('DATA OUTAGE')
    assert 'not a zero-opportunity result' in d['intraday']['res']['coverage_fail']
    assert (tmp_path/'out'/'report.html').exists()
    assert Store(tmp_path/'state').get(d['session'])['report_status'].startswith('DATA OUTAGE')


def test_persistent_position_assembly_fault_still_renders_factual_outage(tmp_path,monkeypatch):
    s=services();s['positions']=lambda:[position()]
    monkeypatch.setattr(brief.positions,'load',s['positions'])
    monkeypatch.setattr(brief.ledger,'load',lambda:[])
    monkeypatch.setattr(brief.positions,'mark_book',lambda *a,**k:(_ for _ in ()).throw(ValueError('position assembly defect')))
    monkeypatch.setattr(brief,'compute',lambda **kw:brief._compute(now=NOW,services=s))
    d=daily_job.run(tmp_path/'state',tmp_path/'out',now=NOW)
    assert d['positions']['status']=='UNAVAILABLE'
    assert d['positions']['unassembled_records']==[position()]
    assert 'holdings are unknown' in d['positions']['verification']
    assert (tmp_path/'out'/'report.html').exists()


def test_provider_diagnostics_never_render_credentials(monkeypatch):
    token='sk-unit-test-private-credential'
    monkeypatch.setenv('DEEPSEEK_API_KEY',token)
    s=services()
    s['intraday']=lambda cfg:(_ for _ in ()).throw(RuntimeError('GET https://host.invalid/?api_key='+token+' '+token))
    s['biotech_inputs']=lambda:(_ for _ in ()).throw(ValueError('password=anothersecret '+token))
    d=brief.build(now=NOW,services=s)
    for value in (encode(d),brief.render_text(d),brief.render_html(d),email_render.text(d)):
        assert token not in value and 'anothersecret' not in value and 'https://host.invalid' not in value
    assert 'REDACTED' in encode(d)


def test_smtp_authentication_minute_crossing_updates_both_views(tmp_path,monkeypatch):
    store=Store(tmp_path)
    original=brief.build(now=NOW,services=services())
    store.publish(original['session'],original)
    monkeypatch.setenv('RB_SMTP_USER','sender@example.org')
    monkeypatch.setenv('RB_SMTP_PASSWORD','test-password')
    clock=[NOW]
    sent=[]
    class SMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def login(self,*args):clock[0]=NOW+dt.timedelta(minutes=1)
        def send_message(self,msg):sent.append(msg);return {}
    deliver_report.send(store,original['session'],'sender@example.org','recipient@example.org',
                        smtp_factory=SMTP,clock=lambda:clock[0])
    assert 'INFORMATIONAL' in str(sent[0]['Subject'])
    assert '09:47' in sent[0].get_body(('plain',)).get_content()
    assert 'no fresh morning entry claim' in sent[0].get_body(('plain',)).get_content()
    assert store.get(original['session'])==original
