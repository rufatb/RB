import copy
import datetime as dt
import json
import time
from pathlib import Path
import pytest
import bar_cache
import build_biotech as build
from test_daily_pipeline import NOW


def cache(tmp_path):
    cfg={'exchange_tz':'America/New_York','scan':{'universe':['A.TO']},'data_sources':{'primary':'yahoo_direct'}}
    manifest=dict(complete=True,session=NOW.date().isoformat(),prepared_at=NOW.replace(hour=8).isoformat(),
                  source='yahoo_direct',tickers=['A.TO'])
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    return cfg,manifest


def test_manifest_alone_does_not_certify_missing_cache_bytes(tmp_path):
    cfg,_=cache(tmp_path)
    result=bar_cache.inspect_cache(cfg,tmp_path,NOW)
    assert result['status']=='NOT READY' and result['verified']==0


def test_cache_verifies_identity_and_rejects_after_open_preparation(tmp_path):
    cfg,m=cache(tmp_path)
    row=dict(ticker='A.TO',session=NOW.date().isoformat(),frame=json.dumps(dict(
        columns=['Open','High','Low','Close','Volume'],index=['2026-09-04T15:55:00-04:00'],data=[[1,1,1,1,10]])))
    (tmp_path/bar_cache.key('A.TO')).write_text(json.dumps(row))
    assert bar_cache.inspect_cache(cfg,tmp_path,NOW)['status']=='READY'
    m['prepared_at']=NOW.replace(hour=9,minute=31).isoformat()
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    assert bar_cache.inspect_cache(cfg,tmp_path,NOW)['status']=='NOT READY'


def test_scheduled_scan_cannot_download_full_history_when_cache_is_unconfigured(monkeypatch):
    import r945
    monkeypatch.delenv('RB_INTRADAY_CACHE_DIR',raising=False)
    monkeypatch.setattr(r945,'build_adapter',lambda **kw:pytest.fail('network adapter created'))
    with pytest.raises(ValueError,match='prepared cache'):
        r945.run({},require_cache=True)


def test_biotech_timeout_is_bounded_and_checkpointed(monkeypatch):
    monkeypatch.setattr(build,'discover_universe',lambda:time.sleep(1))
    saved=[];start=time.monotonic()
    out=build.build(NOW,discovery_budget=.03,checkpoint=lambda x:saved.append(copy.deepcopy(x)))
    assert time.monotonic()-start<.7
    assert not out['universe_complete'] and 'TimeoutExpired' in out['errors'][0]
    assert saved[-1]==out


def test_biotech_rate_limit_preserves_successes_and_stops_further_batches(monkeypatch):
    class YFRateLimitError(Exception):pass
    monkeypatch.setattr(build,'discover_universe',lambda:[{'symbol':s} for s in 'ABCD'])
    def fetch(row,now):
        if row['symbol']=='B':raise YFRateLimitError()
        return {'ticker':row['symbol']}
    monkeypatch.setattr(build,'fetch_security',fetch)
    saved=[]
    out=build.build(NOW,workers=2,checkpoint=lambda x:saved.append(copy.deepcopy(x)))
    assert [r['ticker'] for r in out['securities']]==['A']
    assert out['universe_count']==4 and not out['universe_complete']
    assert any('remaining symbols not requested' in e for e in out['errors'])
    assert saved[-1]==out


def test_options_timer_can_supply_a_quote_inside_the_120_second_window():
    import re
    root=Path(__file__).resolve().parents[1]/'deploy'
    def at(name):
        m=re.search(r'^OnCalendar=.*?(\d\d):(\d\d):(\d\d)',(root/name).read_text(),re.M)
        return dt.datetime(2026,9,11,*map(int,m.groups()))
    options=at('rb-options.timer');report=at('rb-report.timer')
    end=options.replace(hour=9,minute=46,second=59)
    assert 0<(end-options).total_seconds()<=120
    assert report<options
