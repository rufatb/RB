"""End-to-end report invariants, including blank boards and no-network rendering."""
import copy
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import pytest
import brief
import execution
import daily_render
from report_store import Store,encode

NOW=dt.datetime(2026,9,8,9,46,20,tzinfo=ZoneInfo('America/New_York'))


def market_row(t,now=NOW):
    return {'symbol':t,'currency':'CAD' if t.endswith('.TO') else 'USD',
            'regularMarketPrice':100.,'regularMarketTime':now.timestamp(),
            'bid':99.99,'ask':100.01,'bidAskTimestamp':now.timestamp()}


def res():
    p={'t':'AAA.TO','p_up':.56,'nd':.2,'p945':100.,'last':100.,'vol':1.,'confidence':'dense',
       'r0':.1,'gap':.2,'vp':1.}
    q={**p,'t':'BBB.TO','p_up':.44}
    return {'now':NOW.isoformat(),'longs':[p],'shorts':[q],
            'pair':{'long':{'status':'OK','pick':p,'sided':.56},
                    'short':{'status':'OK','pick':q,'sided':.56}},'evaluated':[],
            'fetch_errors':{},'n_names':21,'max_chase_pct':.04}


class Market:
    def __init__(self):self.calls=0
    def get(self,tickers):
        self.calls+=1
        return {t:market_row(t) for t in tickers}


def services():
    return {'ledger':lambda:[],'positions':lambda:[],'market':Market(),
            'intraday':lambda cfg:res(),
            'biotech_inputs':lambda:({'universe_complete':False,'errors':['fixture outage']},[])}


def test_full_board_and_engines_are_isolated():
    a=services();first=brief.compute(now=NOW,services=a)
    a['biotech_inputs']=lambda:(_ for _ in ()).throw(ValueError('bad catalyst data'))
    second=brief.compute(now=NOW,services=a)
    assert first['intraday']==second['intraday']
    assert first['biotech']!=second['biotech']
    assert len(first['intraday']['res']['longs'])==1
    assert len(first['intraday']['legs'])==2
    assert first['intraday']['legs'][0]['status']=='SHADOW'


def test_single_quote_call_feeds_all_legs_and_index():
    s=services();d=brief.compute(now=NOW,services=s)
    assert s['market'].calls==1
    assert d['intraday']['benchmark']['status']=='OK'
    assert all(l['entry_spread_bps'] is not None for l in d['intraday']['legs'])


def test_renderers_cannot_fetch_or_mutate(monkeypatch):
    d=brief.compute(now=NOW,services=services());before=encode(d)
    def fail(*a,**k):raise AssertionError('renderer touched network/files')
    monkeypatch.setattr('urllib.request.urlopen',fail)
    monkeypatch.setattr('builtins.open',fail)
    assert 'AAA.TO' in brief.render_text(d)
    assert 'AAA.TO' in brief.render_html(d)
    assert encode(d)==before
    assert 'Part 1' in brief.render_text(d) and 'Part 2' in brief.render_text(d)


def test_offline_does_not_publish_or_fetch(tmp_path):
    s=services()
    s['intraday']=lambda cfg:pytest.fail('offline model fetch')
    d=brief.compute(now=NOW,no_net=True,publish=True,state_dir=tmp_path/'state',services=s)
    assert s['market'].calls==0
    assert not (tmp_path/'state').exists()
    assert d['offline'] and d['intraday']['res']['coverage_fail'].startswith('OFFLINE')


def test_publish_once_restores_before_any_acquisition(tmp_path,monkeypatch):
    s=services();calls=[]
    monkeypatch.setattr('r945.publish',lambda *a,**k: calls.append('publish') or {'errors':[]})
    first=brief.compute(now=NOW,publish=True,state_dir=tmp_path,services=s)
    assert calls==['publish']
    def fail():pytest.fail('published re-read acquired data')
    s['ledger']=fail
    second=brief.compute(now=NOW,publish=True,state_dir=tmp_path,services=s)
    assert first==second and s['market'].calls==1


def test_zero_pick_day_is_also_immutable(tmp_path):
    store=Store(tmp_path)
    a=store.publish('2026-09-08',{'legs':[]})
    b=store.publish('2026-09-08',{'legs':['changed']})
    assert a==b=={'legs':[]}


def test_concurrent_publication_has_one_winner(tmp_path):
    store=Store(tmp_path)
    with ThreadPoolExecutor(4) as pool:
        out=list(pool.map(lambda i:store.publish('2026-09-08',{'n':i}),range(8)))
    assert all(x==out[0] for x in out)


@pytest.mark.parametrize('day,clock,eligible',[('2026-09-07','09:46',False),
    ('2026-09-08','09:40',False),('2026-09-08','09:46',True),
    ('2026-09-08','09:47',False),('2026-12-24','09:46',False),
    ('2026-11-02','09:46',True)])
def test_exchange_clock_dst_holidays_and_early_close(day,clock,eligible):
    now=dt.datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo('America/New_York'))
    assert execution.clock_status(now,'NYSE')['eligible']==eligible


def test_old_quote_in_same_session_is_not_exact_entry():
    from quotes import validate_equity
    r=res();q=market_row('AAA.TO',NOW-dt.timedelta(minutes=1))
    quotes={'AAA.TO':validate_equity(q,'AAA.TO',NOW,currency='CAD')}
    legs=execution.evaluate_legs(r,{'risk':{'account_equity':100000,'max_position_pct':50}},
                                  quotes,{'eligible':True},True)
    assert legs[0]['status']=='ABSTAIN'
    assert any('exact 09:46' in x for x in legs[0]['reasons'])


def test_html_does_not_execute_source_markup():
    d=brief.compute(now=NOW,services=services())
    d['errors'].append({'layer':'<script>alert(1)</script>','error':'x','detail':'<img onerror=x>'})
    h=brief.render_html(d)
    assert '<script>' not in h and '&lt;script&gt;' in h
