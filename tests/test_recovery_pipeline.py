import copy
import datetime as dt
import json
import time
import pandas as pd
import pytest
import brief
import biotech
import bar_cache
from bounded import acquire
from quotes import reference_close
from sync_runtime import merge
from test_daily_pipeline import NOW, services, market_row
from test_biotech_monitor import event


def test_slow_section_cannot_erase_fast_sibling():
    def slow(): time.sleep(2); return 'late'
    start=time.monotonic()
    result=acquire({'slow':(slow,.10),'quotes':(lambda:{'A':3},1)})
    assert time.monotonic()-start<1.5
    assert result['quotes']['value']=={'A':3}
    assert result['slow']['error']=='TimeoutExpired'


def test_worker_error_is_visible_without_provider_secret():
    def bad(): raise ValueError('https://example.com/?apiKey=secret')
    result=acquire({'bad':(bad,1)})
    assert result['bad']['error']=='ValueError'
    assert 'secret' not in json.dumps(result)


def test_recorded_board_survives_offline_and_is_not_repicked():
    s=services()
    rows=[dict(date=NOW.date().isoformat(),ticker=t,side=side,role='pair',leg='primary',
               p945='100',shares='10',spread_bps='5',weight='.25')
          for t,side in [('TRP.TO','LONG'),('T.TO','LONG'),('AEM.TO','SHORT'),('NTR.TO','SHORT')]]
    s['ledger']=lambda:rows
    s['intraday']=lambda cfg:pytest.fail('must not repick published board')
    d=brief.compute(now=NOW,no_net=True,services=s)
    out=brief.render_text(d)
    assert d['intraday']['recorded_today']==rows
    assert all(r['ticker'] in out for r in rows)
    assert 'No qualifying baseline legs' not in out and 'NO TRADE' not in out
    assert 'not a fresh entry' in out


def test_unavailable_is_not_a_zero_opportunity_result():
    d=brief.compute(now=NOW,no_net=True,services=services())
    text=brief.render_text(d)
    assert 'NOT EVALUATED' in text and 'No verified uncrowded setup passes' not in text
    assert 'No qualifying baseline legs' not in text


def test_reference_close_is_never_live_mark():
    row={'ticker':'ZYME','currency':'USD','session':'2026-09-04','close':29.19,
         'retrieved_at':NOW.isoformat(),'source_url':'https://massive.com/docs/rest/stocks/aggregates/previous-day-bar'}
    assert reference_close(row,'ZYME',NOW)['status']=='OK'
    for field,value in [('currency','CAD'),('session','2026-09-03'),('close',float('nan')),
                        ('ticker','OTHER'),('retrieved_at',(NOW+dt.timedelta(minutes=1)).isoformat())]:
        assert reference_close({**row,field:value},'ZYME',NOW)['status']=='UNAVAILABLE'


def test_position_known_fields_survive_missing_mark():
    s=services();s['positions']=lambda:[{'id':'1','ticker':'ZYME','side':'LONG','status':'OPEN',
        'shares':'400','entry_px':'24.9','entry_date':'2026-08-19','event_date':'2026-08-25'}]
    d=brief.compute(now=NOW,no_net=True,services=s)
    out=brief.render_text(d)
    assert '400 recorded shares' in out and '24.90' in out and 'RECONCILE' in out
    assert d['positions']['legs'][0]['mark'] is None


def test_runtime_merge_preserves_immutable_values():
    original=[{'date':'2026-09-08','ticker':'A','p945':'10'}]
    merged,added=merge(original,original+[{'date':'2026-09-08','ticker':'B','p945':'20'}],('date','ticker'))
    assert len(merged)==2 and len(added)==1
    with pytest.raises(ValueError,match='conflicting'):
        merge(original,[{**original[0],'p945':'11'}],('date','ticker'))


def test_reviewed_calendar_survives_incomplete_universe():
    s=services();s['biotech_inputs']=lambda:({'universe_complete':False,'errors':['outage']},[event()])
    d=brief.compute(now=NOW,services=s)
    assert d['biotech']['monitor']==[] and len(d['research_calendar']['events'])==1
    assert 'not certified Monitor' not in d['research_calendar']['label']  # stronger explicit certification wording
    assert 'NOT certified' in d['research_calendar']['label']
    assert 'FORWARD CALENDAR' in brief.render_text(d)


def test_stale_and_duplicate_calendar_events_are_not_promoted():
    e=event();stale={**e,'verified_at':(NOW-dt.timedelta(days=8)).isoformat()}
    assert not biotech.research_calendar([stale],NOW)['events']
    assert not biotech.research_calendar([e,e],NOW)['events']


def test_intraday_error_does_not_erase_quote_marks():
    s=services()
    def fail(cfg): raise RuntimeError('intraday unavailable')
    s['intraday']=fail
    s['positions']=lambda:[{'id':'1','ticker':'AAA.TO','side':'LONG','status':'OPEN','shares':'10',
                           'entry_px':'90','entry_date':'2026-09-01'}]
    d=brief.compute(now=NOW,services=s)
    assert d['positions']['legs'][0]['mark']==100 and d['intraday']['legs']==[]


def test_safe_bundle_preserves_sent_claim_and_rejects_traversal(tmp_path):
    import zipfile
    from report_store import Store
    from state_bundle import pack,extract
    s=Store(tmp_path/'source');s.publish('2026-09-08',{'known':1})
    assert s.claim_delivery('2026-09-08','gmail-real-id')
    s.finish_delivery('2026-09-08','sent')
    pack(tmp_path/'source',tmp_path/'ok.zip');extract(tmp_path/'ok.zip',tmp_path/'restored')
    assert Store(tmp_path/'restored').delivery('2026-09-08')['message_id']=='gmail-real-id'
    with zipfile.ZipFile(tmp_path/'bad.zip','w') as z: z.writestr('../escape','bad')
    with pytest.raises(ValueError,match='unsafe'):
        extract(tmp_path/'bad.zip',tmp_path/'bad')


def test_history_cache_combination_matches_cold_bars(tmp_path,monkeypatch):
    idx=pd.DatetimeIndex(['2026-09-04T09:30:00-04:00','2026-09-08T09:30:00-04:00']).tz_convert('America/New_York')
    frame=pd.DataFrame({'Open':[10.,11.],'High':[12.,13.],'Low':[9.,10.],
                        'Close':[11.,12.],'Volume':[100.,200.]},index=idx)
    class Adapter:
        name='fixture';exchange_tz='America/New_York'
        def _chart(self,t,i,r): return frame if r=='60d' else frame.iloc[1:]
        def _bars_df(self,v): return v
    adapter=Adapter();cold=bar_cache.get_bars(adapter,'A',NOW)
    (tmp_path/'manifest.json').write_text(json.dumps({'complete':True,'session':'2026-09-08','source':'fixture','tickers':['A']}))
    (tmp_path/bar_cache.key('A')).write_text(json.dumps({'ticker':'A','session':'2026-09-08',
        'frame':frame.iloc[:1].to_json(orient='split',date_format='iso',double_precision=15)}))
    monkeypatch.setenv('RB_INTRADAY_CACHE_DIR',str(tmp_path))
    cached=bar_cache.get_bars(adapter,'A',NOW)
    pd.testing.assert_frame_equal(cached,cold,check_dtype=False)
    with pytest.raises(ValueError,match='not prepared'):
        bar_cache.get_bars(adapter,'A',NOW+dt.timedelta(days=1))
