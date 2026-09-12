"""Headless failures stay visible without revealing private provider responses."""
import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

import adapters
import dashboard
import scan


SECRET='PRIVATE_PROVIDER_TOKEN'


def fail(*args,**kwargs):
    raise ConnectionError('https://provider.test/data?api_key='+SECRET)


def test_state_corruption_and_write_failure_have_bounded_diagnostics(tmp_path,caplog):
    path=tmp_path/'state.json';path.write_text('{invalid')
    diagnostics=[]
    assert scan.load_state(path,diagnostics=diagnostics)=={}
    scan.save_state({},tmp_path/'missing'/'state.json',diagnostics=diagnostics)
    assert [r['layer'] for r in diagnostics]==['scan_state_load','scan_state_save']
    assert diagnostics[0]['error']=='JSONDecodeError'
    assert diagnostics[1]['error']=='FileNotFoundError'
    assert 'scan_state_load' in caplog.text


def test_stooq_daily_failure_is_visible_in_empty_result(caplog):
    adapter=adapters.StooqAdapter()
    adapter._requests=SimpleNamespace(get=fail)
    frame=adapter.get_daily_bars('TRP.TO',60)
    assert frame.empty
    assert 'ConnectionError' in frame.attrs['acquisition_warnings'][0]
    assert SECRET not in caplog.text+str(frame.attrs)


def test_yahoo_failover_reports_both_failures_without_authenticated_urls(caplog):
    adapter=adapters.YahooDirectAdapter()
    adapter._requests=SimpleNamespace(get=fail)
    with pytest.raises(RuntimeError) as error:
        adapter._chart('TRP.TO','5m','60d')
    assert 'ConnectionError' in str(error.value)
    assert SECRET not in str(error.value)+caplog.text
    assert len([r for r in caplog.records if 'Yahoo chart fetch' in r.message])==2


class Empty:
    name='empty'
    def get_daily_bars(self,*args): return pd.DataFrame()
    def get_intraday_bars(self,*args): return pd.DataFrame()


class Broken(Empty):
    name='broken'
    get_daily_bars=staticmethod(fail)
    get_intraday_bars=staticmethod(fail)


def test_multisource_failed_fallbacks_are_visible_and_stay_empty(caplog):
    adapter=adapters.MultiSourceAdapter(Empty(),[Broken()])
    assert adapter.get_daily_bars('TRP.TO',60).empty
    assert adapter.get_intraday_bars('TRP.TO').empty
    assert 'broken daily history' in caplog.text and 'broken intraday history' in caplog.text
    assert SECRET not in caplog.text


def test_unconfigured_crosscheck_reports_failure_and_keeps_primary(monkeypatch,caplog):
    primary=Empty()
    def build(name,**kw):
        if name=='primary': return primary
        fail()
    monkeypatch.setattr(adapters,'_build_single',build)
    assert adapters.build_adapter('primary',exchange_tz='America/Toronto',cross_check=['other']) is primary
    assert 'cross-check adapter other' in caplog.text and SECRET not in caplog.text


def test_partial_history_retains_metrics_and_explicit_failure_status(caplog):
    now=dt.datetime(2026,9,11,9,46,tzinfo=ZoneInfo('America/Toronto'))
    quote=adapters.Quote(ticker='TRP.TO',last=100,open=100,high=101,low=99,
        prior_close=100,volume=1000,source='fixture',as_of=now,session_date=now.date(),currency='CAD')
    class Adapter(Broken):
        def get_quote(self,ticker): return quote
    config=dashboard.load_config('config.yaml')
    config['patterns']={'enabled':False}
    out=scan.evaluate(Adapter(),'TRP.TO',config,now,dt.time(9,30),dt.time(16),{})
    assert out['passed']
    assert out['data_status']=='PARTIAL'
    assert {r['layer'] for r in out['data_errors']}=={'intraday_history','daily_history'}
    assert all(r['error']=='ConnectionError' for r in out['data_errors'])
    assert 'probability' in out and 'PARTIAL DATA' in out['note']
    assert SECRET not in repr(out)+caplog.text


def test_terminal_diagnostics_include_failed_names_and_bound_output(capsys):
    data={'results':[{'ticker':'TRP.TO','data_errors':[
        {'layer':'intraday_history','error':'ConnectionError'}]}],
        'data_errors':[{'ticker':'ENB.TO','layer':'history','error':'TimeoutError'}]*15}
    scan._render_data_errors(data)
    out=capsys.readouterr().out
    assert 'DATA GAPS: 16' in out and '4 additional gap(s)' in out
    assert len(out.splitlines())==14
