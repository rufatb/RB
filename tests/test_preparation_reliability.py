import copy
import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
import bar_cache
import build_biotech as build
from test_daily_pipeline import NOW

ET = ZoneInfo('America/New_York')


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
    import pandas as pd
    cfg,m=cache(tmp_path)
    row=dict(ticker='A.TO',session=NOW.date().isoformat(),frame=json.dumps(dict(
        columns=['Open','High','Low','Close','Volume'],
        index=[t.isoformat() for t in pd.date_range('2026-09-04 09:30',periods=78,freq='5min',tz='America/New_York')],
        data=[[1,1,1,1,10]]*78)))
    (tmp_path/bar_cache.key('A.TO')).write_text(json.dumps(row))
    assert bar_cache.inspect_cache(cfg,tmp_path,NOW)['status']=='READY'
    m['prepared_at']=NOW.replace(hour=9,minute=31).isoformat()
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    assert bar_cache.inspect_cache(cfg,tmp_path,NOW)['status']=='NOT READY'


def test_cache_with_only_a_closing_bar_is_not_ready(tmp_path):
    cfg,_=cache(tmp_path)
    row=dict(ticker='A.TO',session=NOW.date().isoformat(),frame=json.dumps(dict(
        columns=['Open','High','Low','Close','Volume'],index=['2026-09-04T15:55:00-04:00'],data=[[1,1,1,1,10]])))
    (tmp_path/bar_cache.key('A.TO')).write_text(json.dumps(row))
    result = bar_cache.inspect_cache(cfg,tmp_path,NOW)
    assert result['status']=='NOT READY'
    assert result['training_history'][0]['rejected_sessions']==1



class _FixedDatetime(dt.datetime):
    """Pin `dt.datetime.now` inside r945 without touching anything else."""

    _fixed = None

    def __new__(cls, fixed):
        obj = super().__new__(cls, 2000, 1, 1)
        obj._fixed = fixed
        return obj

    def now(self, tz=None):
        return self._fixed.astimezone(tz) if tz else self._fixed


def test_scheduled_scan_degrades_to_live_history_instead_of_losing_the_board(monkeypatch):
    """REPLACES a rule that cost two consecutive sessions.

    The scheduled path used to RAISE when no cache directory was configured,
    to protect the 22-second acquisition budget after the 2026-09-10 timeout.
    The protection was worth having; refusing to run was not the way to get
    it. On 2026-09-14 and 2026-09-15 the feed was healthy, the whole TSX-21
    took 4.1-5.1s live, and both mornings published a board with ZERO names
    evaluated and emailed "SCAN UNAVAILABLE".

    The cache "changes acquisition only, not baseline features or rules"
    (CLAUDE.md), so the live path yields the same board. What the scheduled
    path must now do is degrade, and say so — never silently (house rule 1).

    THIS TEST USED TO READ THE WALL CLOCK. `r945.run` calls
    `dt.datetime.now(...)` itself, so before 09:46 ET it returns on the
    too-early branch, and that branch dropped `cache_degraded` entirely. The
    assertion therefore only ever exercised the afternoon path: it passed every
    time the suite was run after the open and raised KeyError at 09:05, which
    is precisely the hour it exists to protect. Both clocks are pinned now."""
    import r945
    monkeypatch.delenv('RB_INTRADAY_CACHE_DIR',raising=False)
    built=[]
    monkeypatch.setattr(r945,'build_adapter',lambda **kw:built.append(kw) or (_ for _ in ()).throw(TypeError('no 5m')))
    cfg={'exchange_tz':'America/New_York','scan':{'universe':[]}}
    for label,clock in (('pre-open',dt.datetime(2026,9,18,9,5,tzinfo=ET)),
                        ('publication',dt.datetime(2026,9,18,9,46,tzinfo=ET))):
        monkeypatch.setattr(r945.dt,'datetime',_FixedDatetime(clock))
        out=r945.run(cfg,require_cache=True)
        assert out['cache_degraded'], f'{label}: a degraded acquisition path must be recorded'
        assert 'cache' in out['cache_degraded']
        assert 'cache_fallbacks' in out, f'{label}: per-name fallbacks must be countable'


def test_an_unconfigured_cache_is_not_reported_as_ready(monkeypatch):
    """cache_ready must answer for THIS session and source, not merely whether
    the environment variable is set — the stale-manifest case is what made the
    2026-09-15 board empty even with the variable exported."""
    import bar_cache
    class Adapter: name='yahoo_direct'
    monkeypatch.delenv('RB_INTRADAY_CACHE_DIR',raising=False)
    ok,why=bar_cache.cache_ready(Adapter(),NOW)
    assert ok is False and 'no cache directory' in why


def test_biotech_timeout_is_bounded_and_checkpointed(monkeypatch):
    monkeypatch.setattr(build,'discover_universe',lambda:time.sleep(1))
    saved=[];start=time.monotonic()
    out=build.build(NOW,discovery_budget=.03,checkpoint=lambda x:saved.append(copy.deepcopy(x)))
    assert time.monotonic()-start<.7
    assert not out['universe_complete'] and 'TimeoutExpired' in out['errors'][0]
    assert saved[-1]==out


def test_biotech_rate_limit_pauses_retries_and_keeps_every_success(monkeypatch):
    """2026-09-22: stopping on the first rate limit or timeout ended 09-15's
    build at ~120 of 1,005 names, and Part 2 had been empty ever since. The
    build now runs the evening before, so it can afford to wait: pause, carry
    on, retry the failures once at the end. A name that still fails is still
    an error and the universe is still NOT certified."""
    class YFRateLimitError(Exception):pass
    monkeypatch.setattr(build,'discover_universe',lambda:[{'symbol':s} for s in 'ABCD'])
    monkeypatch.setattr(build.time,'sleep',lambda s:None)
    def fetch(row,now):
        if row['symbol']=='B':raise YFRateLimitError()
        return {'ticker':row['symbol']}
    monkeypatch.setattr(build,'fetch_security',fetch)
    saved=[]
    out=build.build(NOW,workers=2,checkpoint=lambda x:saved.append(copy.deepcopy(x)))
    assert [r['ticker'] for r in out['securities']]==['A','C','D']
    assert out['universe_count']==4 and not out['universe_complete']
    assert out['errors']==['B: YFRateLimitError']
    assert saved[-1]==out


def test_a_persistent_rate_limit_still_stops_and_says_so(monkeypatch):
    class YFRateLimitError(Exception):pass
    monkeypatch.setattr(build,'discover_universe',lambda:[{'symbol':s} for s in 'ABCDEFGHIJ'])
    monkeypatch.setattr(build.time,'sleep',lambda s:None)
    def fetch(row,now): raise YFRateLimitError()
    monkeypatch.setattr(build,'fetch_security',fetch)
    out=build.build(NOW,workers=2)
    assert not out['universe_complete']
    assert any('rate limit persisted; remaining symbols not requested' in e for e in out['errors'])


def test_a_warrant_is_an_exclusion_not_a_failure(monkeypatch):
    """The screener's own warrants made certification unreachable."""
    monkeypatch.setattr(build,'discover_universe',lambda:[
        {'symbol':'A','quoteType':'EQUITY'},{'symbol':'AW','quoteType':'WARRANT'}])
    monkeypatch.setattr(build,'fetch_security',lambda row,now:{'ticker':row['symbol']})
    out=build.build(NOW,workers=2)
    assert out['exclusions']=={'AW':'not an equity'} and out['errors']==[]
    assert out['universe_complete'] and out['eligible_count']==1


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


def sec(t, volume):
    return {'ticker': t, 'daily_bars': [{'volume': volume}] * 20}


def test_names_provably_outside_the_top_100_are_bounded_not_failed():
    """ADV20 <= 3.15 x ADV63 exactly. Once 100 names are measured, anything
    whose 3.15 x 3-month ADV sits below the 100th ADV20 cannot be top-100."""
    out = {'securities': [sec(f'S{i}', 1_000_000) for i in range(100)]}
    adv63 = {'LOW': 300_000, 'HIGH': 400_000, 'NONE': None}
    assert build.bound_out(out, ['LOW'], adv63) is True           # 945k < 1M
    assert out['bounded_out'] == {'LOW': 300_000}
    assert build.bound_out(out, ['HIGH'], adv63) is False          # 1.26M >= 1M
    assert build.bound_out(out, ['NONE'], adv63) is False          # no screener volume: never bounded


def test_no_bound_before_one_hundred_names_are_measured():
    out = {'securities': [sec(f'S{i}', 1_000_000) for i in range(99)]}
    assert build.bound_out(out, ['LOW'], {'LOW': 1}) is False


def test_the_reader_re_checks_the_bound_rather_than_trusting_it():
    import datetime as dt, biotech
    from zoneinfo import ZoneInfo
    now = dt.datetime(2026, 9, 22, 18, tzinfo=ZoneInfo('America/New_York'))
    days = [d for d in (now.date() - dt.timedelta(days=i) for i in range(40, 0, -1)) if d.weekday() < 5]
    def s(t, v):
        return {'ticker': t, 'industry': 'Biotechnology', 'exchange': 'NMS', 'security_type': 'COMMON',
                'currency': 'USD', 'market_cap': 1e8, 'market_cap_asof': now.isoformat(),
                'daily_bars': [{'date': d.isoformat(), 'adjusted_close': 10.0, 'volume': v} for d in days]}
    secs = [s(f'S{i:03d}', 1_000_000) for i in range(100)]
    base = {'as_of': now.isoformat(), 'universe_complete': True, 'securities': secs,
            'universe_count': 101, 'eligible_count': 100}
    assert len(biotech.select_universe({**base, 'bounded_out': {'LOW': 100_000}}, now)) == 100
    with pytest.raises(ValueError, match='bound does not hold'):
        biotech.select_universe({**base, 'bounded_out': {'LIE': 900_000}}, now)


def test_an_unmeasurable_large_cap_costs_one_rank_not_the_universe(monkeypatch):
    """2026-09-22: ETRA ($832M) failed the 20-session check and alone voided a
    971-name universe. It cannot appear in a monitor capped at $500M; it can
    only displace the 100th name — so certify top-99 instead."""
    monkeypatch.setattr(build, 'discover_universe', lambda: [
        {'symbol': 'A', 'quoteType': 'EQUITY', 'marketCap': 1e8},
        {'symbol': 'BIG', 'quoteType': 'EQUITY', 'marketCap': 8e8}])
    def fetch(row, now):
        if row['symbol'] == 'BIG':
            raise ValueError('ADV20 history missing exchange sessions')
        return {'ticker': row['symbol']}
    monkeypatch.setattr(build, 'fetch_security', fetch)
    monkeypatch.setattr(build.time, 'sleep', lambda s: None)
    out = build.build(NOW, workers=2)
    assert out['unmeasured_large_cap'] == {'BIG': 8e8}
    assert out['errors'] == [] and out['universe_complete'] and out['eligible_count'] == 1


def test_an_unmeasurable_small_cap_still_blocks_certification(monkeypatch):
    """A small cap COULD be in the monitor; not measuring it is a real gap."""
    monkeypatch.setattr(build, 'discover_universe', lambda: [
        {'symbol': 'A', 'quoteType': 'EQUITY', 'marketCap': 1e8},
        {'symbol': 'SMALL', 'quoteType': 'EQUITY', 'marketCap': 1e8}])
    def fetch(row, now):
        if row['symbol'] == 'SMALL':
            raise ValueError('ADV20 history missing exchange sessions')
        return {'ticker': row['symbol']}
    monkeypatch.setattr(build, 'fetch_security', fetch)
    monkeypatch.setattr(build.time, 'sleep', lambda s: None)
    assert not build.build(NOW, workers=2)['universe_complete']


def test_a_name_with_no_volume_at_all_is_validly_bounded():
    """AMBS had a three-month ADV of 0. The reader rejected it as 'not
    positive' while the builder had correctly bounded it out."""
    import datetime as dt, biotech
    from zoneinfo import ZoneInfo
    now = dt.datetime(2026, 9, 22, 18, tzinfo=ZoneInfo('America/New_York'))
    days = [d for d in (now.date() - dt.timedelta(days=i) for i in range(40, 0, -1)) if d.weekday() < 5]
    secs = [{'ticker': f'S{i:03d}', 'industry': 'Biotechnology', 'exchange': 'NMS',
             'security_type': 'COMMON', 'currency': 'USD', 'market_cap': 1e8,
             'market_cap_asof': now.isoformat(),
             'daily_bars': [{'date': d.isoformat(), 'adjusted_close': 10.0, 'volume': 1e6} for d in days]}
            for i in range(100)]
    snap = {'as_of': now.isoformat(), 'universe_complete': True, 'securities': secs,
            'universe_count': 101, 'eligible_count': 100, 'bounded_out': {'DEAD': 0}}
    assert len(biotech.select_universe(snap, now)) == 100
