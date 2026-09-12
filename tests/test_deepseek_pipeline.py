"""The canonical report consumes staged LLM context once and preserves baseline facts."""
import copy
import json
import pytest
import brief
import deepseek_factors
import email_render
import prepare_delivery
from report_store import Store, encode
from test_daily_pipeline import NOW, services, res, market_row


def staged():
    return {'status':'READY','model':'deepseek-chat','requested':3,'covered':3,
            'adopted':False,'gaps':[],'candidate_gaps':{},
            'assessments':[{'ticker':ticker,'directional_lean':lean,'sentiment_score':sentiment,
                            'factor_rationale':'Unique staged catalyst context; uncertainty remains.'}
                           for ticker,lean,sentiment in [('AAA.TO','BULL',.7),('BBB.TO','BEAR',-.7),('CCC.TO','BULL',.9)]],
            'inputs':{'candidates':[{'ticker':'CCC.TO','technicals_as_of':NOW.isoformat(),
                       'technicals_scope':'current_session','source_url':'https://prices.example/CCC',
                       'headlines':[{'title':'Independent issuer update','published_at':NOW.isoformat(),
                                     'source_url':'https://issuer.example/news/update'}], 'catalyst_tags':[]}],
                      'macro':{}}}


def setup(monkeypatch):
    s=services();counts={'quant':0,'quotes':0,'prepared':0}
    def quant(cfg):
        counts['quant']+=1
        out=res()
        out['factor_candidates']=[{'t':'AAA.TO','p_up':.64},{'t':'BBB.TO','p_up':.36},
                                  {'t':'CCC.TO','p_up':.65}]
        return out
    def market(tickers):
        counts['quotes']+=1
        out={t:market_row(t) for t in tickers}
        if 'CCC.TO' in out:out['CCC.TO'].update(bid=99.995,ask=100.005)
        return out
    def prepared(*a,**k):
        counts['prepared']+=1
        return staged()
    s['intraday']=quant;s['market'].get=market
    monkeypatch.setattr(deepseek_factors,'load_prepared',prepared)
    return s,counts


def prohibit_network(monkeypatch):
    import requests
    import urllib.request
    import adapters.deepseek_adapter as adapter
    def forbidden(*a,**k):pytest.fail('report path invoked network/DeepSeek processing')
    monkeypatch.setattr(requests.Session,'request',forbidden)
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    monkeypatch.setattr(adapter,'evaluate_batch',forbidden)


def test_headless_single_digest_contains_same_baseline_and_shadow_views(tmp_path,monkeypatch):
    s,counts=setup(monkeypatch);prohibit_network(monkeypatch)
    d=brief.build(now=NOW,services=s,state_dir=tmp_path)
    assert isinstance(d,brief.Digest)
    assert counts=={'quant':1,'quotes':1,'prepared':1}
    assert {l['ticker'] for l in d['intraday']['legs']}=={'AAA.TO','BBB.TO'}
    factors=d['intraday']['deepseek']
    assert factors['covered']==3 and not factors['adopted']
    # CCC was not selected by the baseline. It is still available to the
    # independently recorded cost-ranked shadow without a second model pass.
    assert {r['ticker'] for r in factors['shadow']['rows']}=={'AAA.TO','BBB.TO','CCC.TO'}
    assert factors['shadow']['h2']['longs'][0]['ticker']=='CCC.TO'
    before=encode(d)
    payload=prepare_delivery.artifacts(d,tmp_path/'dispatch',NOW)
    for body in (brief.render_text(d),brief.render_html(d),payload['text'],payload['html']):
        assert 'AAA.TO' in body and 'BBB.TO' in body and 'CCC.TO' in body
        assert 'unadopted' in body
    assert 'Unique staged catalyst context' in payload['attachments'][0]['content']
    assert 'https://issuer.example/news/update' in payload['attachments'][0]['content']
    assert counts=={'quant':1,'quotes':1,'prepared':1} and encode(d)==before


def test_unavailable_optional_model_preserves_baseline_and_visible_gap(tmp_path,monkeypatch):
    s,counts=setup(monkeypatch);prohibit_network(monkeypatch)
    monkeypatch.setattr(deepseek_factors,'load_prepared',lambda *a,**k:deepseek_factors.unavailable('Model preparation timed out; no assessment was produced.',requested=3))
    d=brief.build(now=NOW,services=s,state_dir=tmp_path)
    assert {l['ticker'] for l in d['intraday']['legs']}=={'AAA.TO','BBB.TO'}
    assert d['intraday']['deepseek']['status']=='UNAVAILABLE'
    body=email_render.text(d)
    assert 'preparation timed out' in body and 'AAA.TO LONG' in body
    assert 'UNAVAILABLE' in body and 'NO EDGE - WAIT' not in body
    assert counts['quant']==1 and counts['quotes']==1


def test_available_factors_do_not_change_baseline_selection_or_allocation(tmp_path,monkeypatch):
    s,_=setup(monkeypatch);prohibit_network(monkeypatch)
    available=brief.build(now=NOW,services=s,state_dir=tmp_path)
    monkeypatch.setattr(deepseek_factors,'load_prepared',lambda *a,**k:deepseek_factors.unavailable('Missing optional model'))
    missing=brief.build(now=NOW,services=s,state_dir=tmp_path)
    assert available['intraday']['legs']==missing['intraday']['legs']
    assert available['intraday']['res']['pair']==missing['intraday']['res']['pair']
    assert available['intraday']['record']==missing['intraday']['record']


def test_unexpected_prepared_loader_failure_cannot_erase_successful_engines(tmp_path,monkeypatch):
    s,counts=setup(monkeypatch);prohibit_network(monkeypatch)
    monkeypatch.setattr(deepseek_factors,'load_prepared',lambda *a,**k:(_ for _ in ()).throw(OSError('optional snapshot filesystem failure')))
    d=brief.build(now=NOW,services=s,state_dir=tmp_path)
    assert len(d['intraday']['legs'])==2
    assert d['intraday']['deepseek']['status']=='UNAVAILABLE'
    assert any(e['layer']=='deepseek' for e in d['errors'])


def test_frozen_reread_never_acquires_or_reanalyses_factors(tmp_path,monkeypatch):
    s,counts=setup(monkeypatch);prohibit_network(monkeypatch)
    monkeypatch.setattr('r945.publish',lambda *a,**k:{'errors':[]})
    first=brief.build(now=NOW,services=s,state_dir=tmp_path,publish=True)
    before=copy.deepcopy(first)
    def forbidden(*a,**k):pytest.fail('frozen reread reacquired/recomputed')
    monkeypatch.setattr(deepseek_factors,'load_prepared',forbidden)
    monkeypatch.setattr(deepseek_factors,'rank_shadow',forbidden)
    s['intraday']=forbidden;s['market'].get=forbidden;s['ledger']=forbidden;s['positions']=forbidden
    second=brief.build(now=NOW,services=s,state_dir=tmp_path,publish=True)
    payload=prepare_delivery.artifacts(second,tmp_path/'dispatch',NOW)
    assert 'CCC.TO' in payload['text']
    assert second==before and Store(tmp_path).get(first['session'])==before
    assert counts=={'quant':1,'quotes':1,'prepared':1}


def test_frozen_publication_does_not_depend_on_current_configuration(tmp_path,monkeypatch):
    s,_=setup(monkeypatch);prohibit_network(monkeypatch)
    monkeypatch.setattr('r945.publish',lambda *a,**k:{'errors':[]})
    original=brief.build(now=NOW,services=s,state_dir=tmp_path,publish=True)
    monkeypatch.setattr('dashboard.load_config',lambda *a,**k:(_ for _ in ()).throw(ValueError('current configuration cannot load')))
    restored=brief.build(now=NOW,services=s,state_dir=tmp_path,publish=True)
    assert restored==original


def test_factor_assembly_crossing_minute_cannot_keep_eligible_clock(tmp_path,monkeypatch):
    import datetime as dt
    from types import SimpleNamespace
    s,_=setup(monkeypatch);prohibit_network(monkeypatch)
    clock=[NOW]
    class WallClock:
        @classmethod
        def now(cls,tz=None):return clock[0].astimezone(tz) if tz else clock[0]
    # Replace brief's namespace only; timestamp validators retain real datetime
    # types and the fixture's aware datetime stays valid.
    monkeypatch.setattr(brief,'dt',SimpleNamespace(datetime=WallClock,date=dt.date,time=dt.time,
                                                timezone=dt.timezone,timedelta=dt.timedelta))
    def slow_local_factors(*args,**kwargs):
        clock[0]=NOW+dt.timedelta(minutes=1)
        return staged()
    monkeypatch.setattr(deepseek_factors,'load_prepared',slow_local_factors)
    d=brief.build(services=s,state_dir=tmp_path)
    assert not d['clock']['eligible']
    assert d['report_status'].startswith('INFORMATIONAL')
    assert dt.datetime.fromisoformat(d['generated_at']).minute==47
    assert all(leg['status']=='ABSTAIN' for leg in d['intraday']['legs'])


def test_recorded_baseline_does_not_become_a_reselected_factor_board(tmp_path,monkeypatch):
    s,counts=setup(monkeypatch);prohibit_network(monkeypatch)
    rows=[dict(date=NOW.date().isoformat(),ticker='TRP.TO',side='LONG',role='pair',
               shares='132',p945='87.89',weight='.25')]
    s['ledger']=lambda:rows
    s['intraday']=lambda cfg:pytest.fail('recorded board cannot be selected again')
    d=brief.build(now=NOW,services=s,state_dir=tmp_path)
    assert d['intraday']['recorded_today']==rows
    shadow=d['intraday']['deepseek']['shadow']
    assert not shadow['h2']['longs'] and not shadow['h2']['shorts']
    assert 'UNAVAILABLE' in shadow['decision']
    assert 'TRP.TO LONG' in email_render.text(d)
