"""Biotech universe, evidence, crowding and five-bullet contract boundaries."""
import copy
import datetime as dt
import pandas as pd
import pytest
import biotech as B
from test_daily_pipeline import NOW


def security(t='BIO', volume=1000000, cap=200000000):
    dates=pd.bdate_range(end='2026-09-04',periods=70)
    return {'ticker':t,'industry':'Biotechnology','exchange':'NMS','security_type':'COMMON',
            'currency':'USD','market_cap':cap,'market_cap_asof':NOW.isoformat(),
            'daily_bars':[{'date':str(d.date()),'volume':volume,'adjusted_close':10.} for d in dates],
            'short_float':.05,'short_asof':NOW.isoformat(),'borrow_apr':.01,'borrow_asof':NOW.isoformat()}


def snapshot(rows=None):
    rows=rows or [security()]
    return {'as_of':NOW.isoformat(),'universe_complete':True,'universe_count':len(rows),'securities':rows}


def event(t='BIO',eid=None):
    return {'event_id':eid or t+'-trial-2026','ticker':t,'kind':'topline','status':'scheduled',
            'window_start':'2026-10-01','window_end':'2026-12-31','verified_at':NOW.isoformat(),
            'announced_at':(NOW-dt.timedelta(days=1)).isoformat(),'date_basis':'issuer_guidance',
            'source_url':'https://example.org/issuer-release','source_type':'issuer','review_status':'verified',
            'asset':'Compound A','indication':'Condition B','stage':'Phase 2',
            'new_information':'Primary endpoint analysis is expected.',
            'known_data':'Protocol and prior safety cohort are disclosed.',
            'read_throughs':'Endpoint and safety results may inform the next development study.'}


def test_universe_intersection_ranks_before_cap_filter():
    rows=[security(f'L{i:03}',10000-i,1_000_000_000) for i in range(100)]
    rows.append(security('MICRO',1,1_000_000))
    assert B.select_universe(snapshot(rows),NOW)==[]


def test_microcaps_included_but_500m_boundary_excluded():
    rows=[security('TINY',100,1),security('LIMIT',200,500000000),security('BELOW',300,499999999)]
    assert {s['ticker'] for s in B.select_universe(snapshot(rows),NOW)}=={'TINY','BELOW'}


def test_adv_is_exactly_last20_share_volume():
    s=security();s['daily_bars'][-20:]=[{**b,'volume':100} for b in s['daily_bars'][-20:]]
    assert B.select_universe(snapshot([s]),NOW)[0]['adv20']==100


@pytest.mark.parametrize('change',[{'universe_complete':False},{'universe_count':99},{'as_of':'2026-09-01T09:00:00-04:00'}])
def test_partial_stale_or_wrong_count_never_produces_top2(change):
    s=snapshot();s.update(change)
    out=B.scan(s,[event()],{},NOW)
    assert out['status']=='UNAVAILABLE' and out['monitor']==[]


@pytest.mark.parametrize('flags,expectation',[
    ([True,True,False],'Crowded / High-Expectations'),
    ([True,None,True],'Crowded / High-Expectations'),
    ([False,False,None],'Monitor'),([False,False,False],'Monitor'),
    ([True,False,None],'Insufficient evidence'),([None,None,False],'Insufficient evidence')])
def test_two_of_three_rule_including_unknown_bounds(flags,expectation):
    assert B.crowding(flags)==expectation


def test_missing_options_can_pass_only_when_other_two_flags_are_false():
    out=B.scan(snapshot(),[event()],{},NOW)
    assert len(out['monitor'])==1 and out['monitor'][0]['flags']==[None,False,False]
    s=security();s['borrow_apr']=None
    assert not B.scan(snapshot([s]),[event()],{},NOW)['monitor']


def test_top2_unique_issuers_and_exactly_five_bullets_each():
    securities=[security(t) for t in ['AAA','BBB','CCC']]
    events=[event(t) for t in ['AAA','BBB','CCC']]+[event('AAA','AAA-second')]
    out=B.scan(snapshot(securities),events,{},NOW)
    assert len(out['monitor'])==2
    assert len({x['ticker'] for x in out['monitor']})==2
    rendered=B.render(out)
    assert sum(line.startswith('- ') for line in rendered.splitlines())==10
    assert all(len(x['bullets'])==5 for x in out['monitor'])


@pytest.mark.parametrize('changes',[
    {'kind':'trial_completion'},{'date_basis':'ClinicalTrials.gov'}, {'source_url':'javascript:alert(1)'},
    {'review_status':'candidate'},{'window_start':'2027-09-01','window_end':'2027-10-01'},
    {'verified_at':'2026-08-01T00:00:00+00:00'}, {'new_information':''},
    {'announced_at':'2026-09-09T09:00:00-04:00'}, {'status':'resolved'}])
def test_unverified_or_out_of_scope_events_are_never_promoted(changes):
    e=event();e.update(changes)
    out=B.scan(snapshot(),[e],{},NOW)
    assert out['monitor']==[] and len(out['unverified'])==1


def test_positioning_counts_once_even_if_both_measures_high():
    s=security();s.update(short_float=.5,borrow_apr=.7)
    flag,_=B.positioning(s,NOW)
    assert flag is True
    assert B.crowding([False,flag,False])=='Monitor'


def test_iv_percentile_needs_comparable_tenor_population():
    p={'ticker':'BIO','status':'OK','iv':.8,'as_of':NOW.isoformat(),'expiry':'2026-10-16'}
    peers=[{**p,'ticker':f'P{i}','iv':i/100+.1} for i in range(20)]
    pct,n=B.option_percentile(p,peers,NOW)
    assert pct==1 and n==20
    assert B.option_percentile(p,peers[:19],NOW)==(None,19)
    assert B.option_percentile(p,[{**x,'expiry':'2027-01-15'} for x in peers],NOW)==(None,0)


def test_crowded_event_is_appendix_only():
    s=security();s.update(short_float=.5)
    events=[event()]
    opt={'ticker':'BIO','status':'OK','iv':3.,'as_of':NOW.isoformat(),'expiry':'2027-01-15'}
    options={f'peer{i}':{**opt,'ticker':f'P{i}','iv':.5+i/100} for i in range(20)}
    options[events[0]['event_id']]=opt
    out=B.scan(snapshot([s]),events,options,NOW)
    assert not out['monitor'] and len(out['crowded'])==1
