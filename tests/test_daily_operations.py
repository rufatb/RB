"""Failures at operational boundaries must remain visible and immutable."""
import copy
import datetime as dt
import json
import subprocess
import pytest
import brief
import cost
import execution
import daily_job
import discover_biotech_events as D
import collect_execution as C
import quotes as Q
import validate_execution as V
from report_store import Store
from test_daily_pipeline import NOW,services,market_row
from test_market_validation import chain


def test_legacy_cost_entrypoint_requires_bbo_timestamp(monkeypatch):
    class Client:
        def get(self,t):
            row=market_row('AAA.TO');del row['bidAskTimestamp']
            return {'AAA.TO':row}
    monkeypatch.setattr(cost,'market_client',Client)
    out=cost.assess([{'ticker':'AAA.TO'}],now=NOW)
    assert out[0]['cost']['bps'] is None and 'timestamp' in out[0]['error']


def test_option_expiry_must_cover_after_close_event():
    client,_,_=chain()
    assert Q.event_quote(client,'AAA',dt.date(2026,10,16),NOW)['status']=='UNAVAILABLE'


def test_cached_option_snapshot_preserves_oldest_observation_time():
    client,_,full=chain();full['options'][0]['calls'][0]['quoteTime']-=60
    q=Q.event_quote(client,'AAA',dt.date(2026,10,1),NOW)
    assert Q.stamp(q['as_of'])==NOW-dt.timedelta(seconds=60)


def test_duplicate_contract_strike_is_quarantined():
    client,_,full=chain();full['options'][0]['calls']*=2
    assert Q.event_quote(client,'AAA',dt.date(2026,10,1),NOW)['status']=='UNAVAILABLE'


def test_short_borrow_cannot_default_to_free():
    q={'status':'OK','bid':99,'ask':101,'spread_bps':200}
    with pytest.raises(ValueError,match='borrow'):
        execution.score_leg({'side':'SHORT','quote':q},q,0,fees_bps=0,slippage_bps=0)
    r=execution.score_leg({'side':'SHORT','quote':q},q,0,fees_bps=0,slippage_bps=0,borrow_bps=1)
    assert r['net_pct']==pytest.approx(-2.01)


def test_wrong_entry_benchmark_minute_blocks_all_net_scores(tmp_path):
    d=brief.compute(now=NOW,services=services());store=Store(tmp_path)
    d['intraday']['benchmark']['quote_time']=(NOW-dt.timedelta(minutes=1)).isoformat()
    store.publish(d['session'],d)
    exit=NOW.replace(hour=15,minute=59)
    class Client:
        def get(self,tickers):return {t:market_row(t,exit) for t in tickers}
    rows=C.collect(store,'15:59',exit,Client(),fees_bps=0,slippage_bps=0,borrow_bps=0)
    assert rows and all(r['status']=='INCOMPLETE' for r in rows)


def test_complete_exact_window_record_has_matched_net_and_tide(tmp_path):
    d=brief.compute(now=NOW,services=services());store=Store(tmp_path);store.publish(d['session'],d)
    exit=NOW.replace(hour=15,minute=59)
    class Client:
        def get(self,tickers):return {t:market_row(t,exit) for t in tickers}
    rows=C.collect(store,'15:59',exit,Client(),fees_bps=0,slippage_bps=0,borrow_bps=0)
    result=execution.observed_performance([d],[dict(r,session=d['session']) for r in rows])
    assert result['scored_legs']==2 and result['complete_sessions']==1
    assert result['mean_net_pct']<0 and result['mean_tide_pct']==0
    assert result['mean_selection_net_pct']==result['mean_net_pct']


def test_catastrophic_assembly_failure_emits_one_frozen_outage(tmp_path,monkeypatch):
    d=brief.compute(now=NOW,services=services(),no_net=True)
    def compute(**kw):
        if not kw.get('no_net'): raise ValueError('bad assembly')
        return copy.deepcopy(d)
    monkeypatch.setattr(daily_job.brief,'compute',compute)
    # Clock INJECTED (day-94). Without this the job froze the report under the
    # real date while this looked it up under NOW, so the test could only pass
    # on 2026-09-08 and failed silently every day after.
    report=daily_job.run(tmp_path/'state',tmp_path/'output',now=NOW)
    assert any(e['error']=='ValueError' for e in report['errors'])
    frozen=Store(tmp_path/'state').get(NOW.date().isoformat())
    assert frozen['report_status'].startswith('DATA OUTAGE')
    assert (tmp_path/'output'/'report.html').read_text().count('Part 2')==1


def test_filing_date_is_never_promoted_to_event_date():
    sub={'cik':'123','filings':{'recent':{'form':['8-K'],'filingDate':['2026-09-01'],
         'accessionNumber':['000123-26-000001'],'primaryDocument':['report.htm']}}}
    rows=D.filing_candidates(sub,'AAA','2026-01-01','2026-09-08')
    assert rows[0]['review_status']=='needs_review' and 'window_start' not in rows[0]
    assert '/123/00012326000001/report.htm' in rows[0]['source_url']


def test_unreviewed_events_do_not_replace_validated_feed(tmp_path):
    source=tmp_path/'source.json';output=tmp_path/'events.json'
    source.write_text(json.dumps({'events':[{'kind':'topline','status':'scheduled'}]}))
    output.write_text('original')
    with pytest.raises((ValueError,KeyError)):
        D.import_reviewed(source,output,NOW)
    assert output.read_text()=='original'


def test_variance_study_checks_all_blocks_and_noninferiority():
    import numpy as np
    rng=np.random.default_rng(90);base=rng.normal(0,10,1000)
    candidate=.75*base+rng.normal(0,.15,1000)
    assert V.variance_gate(base,candidate)['passes']
    assert not V.variance_gate(base,candidate-5)['passes']


def test_legacy_ledger_rendering_cannot_acquire_tide_data(monkeypatch):
    import ledger
    monkeypatch.setattr(ledger,'_tides_for_report',lambda:pytest.fail('render-time acquisition'))
    rows=[{'date':'2026-09-01','ticker':'AAA.TO','side':'LONG','role':'pair',
           'confidence':'dense','hit':'1','r1':'.2','weight':'.5','p945':'100'}]
    assert 'PAIR legs' in ledger.report(rows)


def test_the_job_clock_is_injectable_so_this_suite_cannot_expire(tmp_path,
                                                                 monkeypatch):
    """A test that only passes on the day it was written guards nothing.

    daily_job.run read the wall clock directly, so the outage test above froze
    its report under the real date and looked it up under a fixed NOW. It
    passed on 2026-09-08 and failed every day after, in a suite of 1100+ where
    one red line is easy to inherit as background noise.
    """
    import datetime as dt
    from zoneinfo import ZoneInfo
    import inspect
    assert 'now' in inspect.signature(daily_job.run).parameters

    d = brief.compute(now=NOW, services=services(), no_net=True)
    monkeypatch.setattr(daily_job.brief, 'compute',
                        lambda **kw: copy.deepcopy(d))
    far = dt.datetime(2027, 3, 15, 9, 46, 20, tzinfo=ZoneInfo('America/New_York'))
    d['session'] = far.date().isoformat()
    d['generated_at'] = far.isoformat()
    report = daily_job.run(tmp_path / 's', tmp_path / 'o', now=far)
    assert Store(tmp_path / 's').get(far.date().isoformat()) is not None, \
        "an injected clock did not govern the session key"


def test_a_live_run_still_uses_the_wall_clock(tmp_path, monkeypatch):
    """Production must be unchanged: now=None reads the real clock."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    d = brief.compute(now=NOW, services=services(), no_net=True)
    # Stub the wall-clock provider, not a report with a conflicting old date.
    # The test remains deterministic before the open and across midnight.
    class WallClock(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(daily_job.dt, 'datetime', WallClock)
    monkeypatch.setattr(daily_job.brief, 'compute',
                        lambda **kw: copy.deepcopy(d))
    daily_job.run(tmp_path / 's', tmp_path / 'o')
    today = NOW.date().isoformat()
    assert Store(tmp_path / 's').get(today) is not None
