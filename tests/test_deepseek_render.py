"""Factor research is a pure saved view, never a new selection or order ticket."""
import copy
import pytest
import brief
import daily_render
import email_render
import prepare_delivery
import readiness
from report_store import encode
from test_daily_pipeline import NOW, services


def snapshot():
    long={'ticker':'FACTORLONG.TO','status':'CANDIDATE','direction':'LONG',
          'quant_probability':.64,'combined_probability':.62,'sided_score':.62,
          'spread_bps':2.5,'reason':None}
    short={**long,'ticker':'FACTORSHORT.TO','direction':'SHORT',
           'quant_probability':.36,'combined_probability':.38}
    return {'status':'READY','model':'deepseek-chat','requested':2,'covered':2,
            'adopted':False,'gaps':[],'candidate_gaps':{},
            'assessments':[dict(ticker=t,directional_lean=lean,sentiment_score=s,
                               factor_rationale='Model contextual interpretation; cited issuer evidence may be incomplete.')
                           for t,lean,s in [('FACTORLONG.TO','BULL',.6),('FACTORSHORT.TO','BEAR',-.6)]],
            'inputs':{'candidates':[{'ticker':'FACTORLONG.TO','technicals_as_of':NOW.isoformat(),
                'technicals_scope':'current_session','source_url':'https://public.example/market/FACTORLONG',
                'headlines':[{'title':'Issuer announces an operating update','published_at':NOW.isoformat(),
                              'source_url':'https://issuer.example/releases/update'}],
                'catalyst_tags':[]}], 'macro':{}},
            'shadow':{'h1':{'longs':[long],'shorts':[short]},'h2':{'longs':[long],'shorts':[short]},
                      'rows':[long,short],'gaps':[],'registration':'PREREGISTER_day99_deepseek.md',
                      'mde':{'status':'UNAVAILABLE','minimum_forward_sessions':120,'net_bps':None}}}


def report():
    d=brief.build(now=NOW,services=services())
    d['intraday']['deepseek']=snapshot()
    return d


def test_saved_factors_render_in_both_views_without_compute_or_provider(tmp_path,monkeypatch):
    d=report(); before=encode(d)
    import deepseek_factors
    def no_pass(*a,**k):pytest.fail('renderer attempted computation/acquisition')
    monkeypatch.setattr(brief,'compute',no_pass)
    monkeypatch.setattr(deepseek_factors,'load_prepared',no_pass)
    monkeypatch.setattr(deepseek_factors,'rank_shadow',no_pass)
    payload=prepare_delivery.artifacts(d,tmp_path,NOW)
    assert 'FACTORLONG.TO' in payload['text'] and 'FACTORSHORT.TO' in payload['html']
    assert 'https://issuer.example/releases/update' in payload['attachments'][0]['content']
    assert 'Combined DESIGN score' in payload['attachments'][0]['content']
    assert 'not calibrated probabilities' in payload['text']
    assert encode(d)==before
    assert len(daily_render.deepseek_summary(d['intraday']))<=6


def test_no_factor_order_ticket_or_h1_unpriced_name_in_concise_summary():
    d=report(); snap=d['intraday']['deepseek']
    snap['shadow']['h2']={'longs':[],'shorts':[]}
    for row in snap['shadow']['rows']:row['spread_bps']=None
    section='\n'.join(daily_render.deepseek_summary(d['intraday']))
    assert 'COST EVIDENCE UNAVAILABLE' in section and 'lack exact entry-spread evidence' in section
    assert 'NO EDGE - WAIT' not in section
    assert 'FACTORLONG' not in section and 'FACTORSHORT' not in section
    assert 'shares' not in section and '$' not in section and 'BUY' not in section
    full=brief.render_text(d)
    assert 'Unpriced H1 rows are not executable' in full


@pytest.mark.parametrize('kind',['unavailable','empty','incomplete'])
def test_unevaluated_factor_scan_is_not_no_market_opportunities(kind):
    d=report();snap=d['intraday']['deepseek'];snap['shadow']['h2']={'longs':[],'shorts':[]}
    if kind=='unavailable':snap['status']='UNAVAILABLE'
    elif kind=='empty':snap['shadow']['rows']=[]
    else:snap['shadow']['rows'][0]['status']='UNAVAILABLE'
    body=email_render.text(d)
    assert 'UNAVAILABLE — UNEVALUATED / incomplete evidence' in body
    assert 'NO EDGE - WAIT' not in body
    assert 'absence of candidates is not evidence of no market opportunities' in body


def test_evaluated_abstention_names_threshold_failure():
    d=report();snap=d['intraday']['deepseek']
    snap['shadow']['h1']={'longs':[],'shorts':[]};snap['shadow']['h2']={'longs':[],'shorts':[]}
    for row in snap['shadow']['rows']:row['status']='ABSTAIN'
    assert 'Evaluated factors did not clear the registered threshold' in email_render.text(d)


def test_old_publication_without_factor_key_acquires_no_new_section():
    d=brief.build(now=NOW,services=services())
    d['intraday'].pop('deepseek',None)
    d['readiness']=readiness.assess(d)
    assert 'DeepSeek' not in brief.render_text(d)
    assert 'DeepSeek' not in email_render.text(d)
    assert daily_render.deepseek_summary(d['intraday'])==[]


def test_unavailable_records_never_look_like_confirmed_empty_holdings():
    d=report()
    d['positions'].update(status='UNAVAILABLE',legs=[],gaps=['Position ledger unreadable.'])
    d['intraday']['record'].update(status='UNAVAILABLE',n=0,hits=0)
    for body in (brief.render_text(d),email_render.text(d)):
        assert 'holdings are unknown' in body
        assert 'No open positions recorded' not in body
        assert 'Historical record UNAVAILABLE' in body
        assert 'Historical gross proxy: 0/0' not in body and 'Historical baseline: 0/0' not in body
    assert readiness.assess(d)['status']=='PARTIAL'


def test_partial_records_disclose_rejected_rows_and_keep_valid_facts():
    d=report()
    d['positions'].update(status='PARTIAL',invalid_rows=2,gaps=['Two position rows invalid.'])
    d['intraday']['record'].update(status='PARTIAL',invalid_rows=3)
    body=email_render.text(d)
    assert 'Position ledger PARTIAL; 2 malformed rows excluded' in body
    assert 'Historical record PARTIAL: 3 invalid rows excluded' in body
    assert 'AAA.TO LONG' in body


def test_model_rationale_cannot_inject_html_or_secret(monkeypatch):
    d=report(); token='sk-fixture-secret-only'
    monkeypatch.setenv('DEEPSEEK_API_KEY',token)
    d['intraday']['deepseek']['assessments'][0]['factor_rationale']='<script>alert(1)</script> '+token
    html=brief.render_html(d)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert token not in html
