#!/usr/bin/env python3
"""Stage the biotech universe before the report deadline.

Fetch every page of US-listed Biotechnology equities, calculate actual ADV20
from completed daily sessions, and retain coverage errors. Current membership
is appropriate for today's scan, never for a historical survivorship-free test.
Events are a versioned, source-linked evidence feed; keyword-only discoveries
are reviewed before promotion. Do not substitute ClinicalTrials.gov completion
dates for a sponsor's announced readout window.
"""
from __future__ import annotations
import argparse
import datetime as dt
import time
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import biotech
from quotes import stamp
from report_store import encode


def write_atomic(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(encode(value))
    os.replace(tmp,path)


def discover_universe(screen_fn=None):
    """Full pagination, stable total and unique symbols; no market-cap prefilter."""
    import yfinance as yf
    query=yf.EquityQuery('and',[
        yf.EquityQuery('eq',['industry','Biotechnology']),
        yf.EquityQuery('eq',['region','us'])])
    screen_fn=screen_fn or yf.screen
    rows=[];expected=None;offset=0
    while True:
        page=screen_fn(query,offset=offset,size=250,sortField='ticker',sortAsc=True)
        if not isinstance(page,dict) or not isinstance(page.get('total'),int):
            raise ValueError('screener total absent; cannot certify universe coverage')
        if expected is None: expected=page['total']
        if expected != page['total']:
            raise ValueError('universe changed while paginating; retry the snapshot')
        got=page.get('quotes') or []
        if not got and offset < expected:
            raise ValueError('truncated universe response')
        rows.extend(got);offset+=len(got)
        if offset >= expected:
            break
        if offset > 10000:
            raise ValueError('unexpected universe size')
    if len(rows)!=expected or len({r['symbol'] for r in rows})!=expected:
        raise ValueError('duplicate or incomplete universe pages')
    return rows


class Excluded(ValueError):
    """Outside the population BY DEFINITION — a warrant, a unit, a non-US or
    non-biotech listing. Not a failure to measure anything.

    Before 2026-09-22 these were ordinary errors, and `universe_complete`
    required ZERO errors, so the screener's own warrants (APLMW, ASBPW, ...)
    made a certified top-100 unreachable and Part 2 was empty every day."""


def fetch_security(row, now):
    """Verify provider metadata and every one of the last 20 exchange sessions."""
    import yfinance as yf
    import pandas_market_calendars as mcal
    t=row['symbol']
    if row.get('quoteType')!='EQUITY':
        raise Excluded('not an equity')
    obj=yf.Ticker(t)
    info=obj.get_info()
    if info.get('industry')!='Biotechnology' or info.get('exchange') not in biotech.US_EXCHANGES:
        raise Excluded('membership does not match Biotechnology/US-listing query')
    frame=obj.history(period='6mo',interval='1d',auto_adjust=True,raise_errors=True)
    frame=frame[[i.date()<now.date() for i in frame.index]]
    if frame.empty:
        raise ValueError('no completed daily bars')
    sessions=mcal.get_calendar('NYSE').valid_days(
        start_date=now.date()-dt.timedelta(days=45),end_date=now.date()-dt.timedelta(days=1))
    expected=[i.date().isoformat() for i in sessions[-20:]]
    bars=[{'date':i.date().isoformat(),'adjusted_close':float(r['Close']),'volume':float(r['Volume'])}
          for i,r in frame.iterrows()]
    if [r['date'] for r in bars[-20:]]!=expected:
        raise ValueError('ADV20 history missing exchange sessions or wrong interval')
    # A NaN from the provider is a measurement FAILURE for this name — retried
    # once at the end like any other — never a value written to the snapshot.
    # 2026-09-22: one non-finite field killed a 1,005-name build at name 150,
    # because the snapshot writer (rightly) refuses non-finite JSON.
    import math
    finite=lambda x: isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
    if not all(finite(b['adjusted_close']) and finite(b['volume']) for b in bars):
        raise ValueError('non-finite price or volume from provider')
    if not finite(info.get('marketCap')):
        raise ValueError('non-finite or missing market cap from provider')
    if info.get('shortPercentOfFloat') is not None and not finite(info.get('shortPercentOfFloat')):
        info['shortPercentOfFloat']=None
    short_time=info.get('dateShortInterest')
    # No guessed borrow fee. Its absence remains unknown in the crowding vote.
    return {'ticker':t,'company':info.get('longName',t),'industry':info['industry'],
            'exchange':info['exchange'],'currency':info.get('currency'),
            'security_type':'ADR' if 'ADR' in info.get('longName','') else 'COMMON',
            'market_cap':info.get('marketCap'),'market_cap_asof':now.isoformat(),
            'daily_bars':bars,'short_float':info.get('shortPercentOfFloat'),
            'short_asof':stamp(short_time).isoformat() if short_time else None,
            'borrow_apr':None,'borrow_asof':None,
            'source':'Yahoo Finance via yfinance; captured metadata and completed daily bars'}


# ADV20 <= (63/20) x ADV63: a 63-session average contains the last 20 sessions,
# so even if ALL of its volume fell in those 20, ADV20 is at most 3.15x it.
# An exact bound, not an estimate.
ADV_BOUND = 63/20
TOP_N = 100


def adv20(security):
    vols=[b['volume'] for b in security.get('daily_bars',[])[-20:]]
    return sum(vols)/len(vols) if len(vols)==20 else None


def bound_out(out, symbols, adv63):
    """Record `symbols` as PROVABLY outside the top-100 and return True, or
    change nothing and return False. Every symbol must have a screener 3-month
    ADV, and ADV_BOUND times it must sit below the 100th measured ADV20."""
    measured=sorted((a for a in map(adv20,out['securities']) if a is not None),reverse=True)
    if len(measured)<TOP_N or not symbols:
        return not symbols and len(measured)>=TOP_N
    floor=measured[TOP_N-1]
    if all(isinstance(adv63.get(t),(int,float)) and ADV_BOUND*adv63[t]<floor for t in symbols):
        out.setdefault('bounded_out',{}).update({t:adv63[t] for t in symbols})
        out['bound_floor_adv20']=floor
        return True
    return False


RATE_LIMIT_PAUSES = 3
MAX_UNMEASURED_LARGE_CAPS = 5   # more than this and the ranking is too uncertain to certify
RATE_LIMIT_PAUSE_SECONDS = 60


def build(now=None,workers=4,*,checkpoint=None,discovery_budget=15,security_budget=20):
    now=now or dt.datetime.now(ZoneInfo('America/New_York'))
    out={'as_of':now.isoformat(),'universe_complete':False,'universe_count':0,
         'securities':[],'errors':[],'options':{}}
    from bounded import acquire
    discovered=acquire({'universe':(discover_universe,discovery_budget)})['universe']
    if discovered['status']!='OK':
        out['errors'].append('universe discovery: '+discovered['error'])
        if checkpoint: checkpoint(out)
        return out
    raw=discovered['value']
    # Non-shares never enter the population; they are counted, not failed.
    out['exclusions']={r['symbol']:'not an equity' for r in raw
                       if r.get('quoteType') not in (None,'EQUITY')}
    pending=[r for r in raw if r['symbol'] not in out['exclusions']]
    # MOST LIQUID FIRST, so the build can stop as soon as the rest are PROVABLY
    # outside the top-100 (see `bound_out`). Names with no screener volume are
    # measured first of all: nothing bounds them.
    pending.sort(key=lambda r: (r.get('averageDailyVolume3Month') is not None,
                                -(r.get('averageDailyVolume3Month') or 0), r['symbol']))
    adv63={r['symbol']:r.get('averageDailyVolume3Month') for r in raw}
    out['universe_count']=len(raw)
    if checkpoint: checkpoint(out)
    retry=[]
    rate_limit_pauses=0
    def run(rows, record_failure):
        nonlocal rate_limit_pauses
        for offset in range(0,len(rows),workers):
            remaining=[r['symbol'] for r in rows[offset:]]
            if bound_out(out, remaining, adv63):
                return True
            batch=rows[offset:offset+workers]
            results=acquire({row['symbol']:(lambda row=row:fetch_security(row,now),security_budget) for row in batch})
            limited=False
            for row in batch:
                ticker=row['symbol']; result=results[ticker]
                if result['status']=='OK':
                    out['securities'].append(result['value'])
                elif result['error']=='Excluded':
                    out['exclusions'][ticker]='outside Biotechnology/US-listing population'
                else:
                    record_failure(row, result['error'])
                    limited |= result['error']=='YFRateLimitError'
            if checkpoint: checkpoint(out)
            if limited:
                # A rate limit is the provider asking us to wait, not proof
                # the rest is unmeasurable. This runs the evening before, so
                # waiting is affordable; the morning never runs this loop.
                rate_limit_pauses+=1
                if rate_limit_pauses>RATE_LIMIT_PAUSES:
                    out['errors'].append('provider rate limit persisted; remaining symbols not requested')
                    return False
                time.sleep(RATE_LIMIT_PAUSE_SECONDS)
        return True
    # First pass collects transient failures for ONE retry at the end, instead
    # of stopping on the first timeout — which is what stopped 09-15's build at
    # ~120 of 1,005 names.
    if run(pending, lambda row, error: retry.append((row, error))):
        run([r for r, _ in retry], lambda row, error: out['errors'].append(row['symbol']+': '+error))
    else:
        out['errors'].extend(r['symbol']+': '+e for r, e in retry)
    # AN UNMEASURABLE LARGE CAP CANNOT APPEAR IN THE MONITOR (which keeps only
    # names under $500M), so its one possible effect is to displace the
    # 100th-ranked name. It is recorded, not failed, and the reader certifies
    # one fewer rank for each (top-99 instead of top-100): every name it keeps
    # is then provably inside the true top-100 wherever the unknown ranks.
    # 2026-09-22: ETRA ($832M, 3M shares/day) failed the 20-session check and
    # alone voided a 971-name universe.
    failed_names={e.split(':',1)[0] for e in out['errors']}
    caps={r['symbol']:r.get('marketCap') for r in raw}
    large=[t for t in failed_names
           if isinstance(caps.get(t),(int,float)) and caps[t]>=biotech.MONITOR_MAX_CAP]
    if large and len(large)<=MAX_UNMEASURED_LARGE_CAPS:
        out['unmeasured_large_cap']={t:caps[t] for t in large}
        out['errors']=[e for e in out['errors'] if e.split(':',1)[0] not in large]
    # Whatever failed or was never requested may still be bounded out.
    unmeasured=[r['symbol'] for r in pending
                if r['symbol'] not in {x['ticker'] for x in out['securities']}
                and r['symbol'] not in out.get('unmeasured_large_cap',{})]
    if bound_out(out, unmeasured, adv63):
        failed=set(out.get('bounded_out',{}))
        out['errors']=[e for e in out['errors']
                       if e.split(':',1)[0] not in failed and 'not requested' not in e]
    out['eligible_count']=(out['universe_count']-len(out['exclusions'])
                           -len(out.get('bounded_out',{}))
                           -len(out.get('unmeasured_large_cap',{})))
    out['universe_complete']=bool(raw) and not out['errors']
    if checkpoint: checkpoint(out)
    return out


def refresh_options(snapshot, events, now, client=None):
    """Single validated options layer. Called near 09:45, not in a renderer."""
    from quotes import market_client,YahooMarketData,event_quote
    client=client or market_client()
    eligible={s['ticker'] for s in biotech.select_universe(snapshot,now)}
    rows={}
    for event in events:
        if event.get('ticker') not in eligible:
            continue
        try:
            biotech.validate_event(event,now)
        except (KeyError,ValueError,TypeError) as exc:
            snapshot.setdefault('event_errors',[]).append(str(exc))
            continue
        rows[event['event_id']]=event_quote(client,event['ticker'],dt.date.fromisoformat(event['window_end']),now)
    snapshot['options']=rows
    return snapshot


def certified_within(path, now, hours):
    """True when `path` holds a COMPLETE universe prepared within `hours`."""
    try:
        snap=json.loads(Path(path).read_text())
        age=(now-dt.datetime.fromisoformat(snap['as_of'])).total_seconds()
        return bool(snap.get('universe_complete')) and 0<=age<=hours*3600
    except (OSError,ValueError,KeyError,TypeError):
        return False


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default=os.getenv('RB_BIOTECH_SNAPSHOT_JSON','data/biotech_snapshot.json'))
    p.add_argument('--events',default=os.getenv('RB_BIOTECH_EVENTS_JSON','data/biotech_events.json'))
    p.add_argument('--refresh-options',action='store_true')
    p.add_argument('--skip-if-certified-within',type=float,default=None,metavar='HOURS',
                   help='exit 0 without fetching when the output already holds a complete universe this recent')
    a=p.parse_args(argv)
    now=dt.datetime.now(ZoneInfo('America/New_York'))
    if a.skip_if_certified_within is not None and certified_within(a.output,now,a.skip_if_certified_within):
        print(f"Universe already certified within {a.skip_if_certified_within:g}h; not rebuilt.")
        return 0
    if a.refresh_options:
        snap=json.loads(Path(a.output).read_text())
        events=json.loads(Path(a.events).read_text())['events']
        snap=refresh_options(snap,events,now)
        write_atomic(a.output,snap)
    else:
        # BUILD BESIDE, PROMOTE ON MERIT. Checkpoints used to write straight to
        # the output, so a morning run killed by its time slice would replace
        # the evening's CERTIFIED universe with a partial one and empty Part 2.
        # A partial build never overwrites a certified snapshot.
        partial=str(a.output)+'.partial'
        snap=build(now,checkpoint=lambda value:write_atomic(partial,value))
        if snap['universe_complete'] or not certified_within(a.output,now,36):
            write_atomic(a.output,snap)
        else:
            print('Build incomplete; the existing certified snapshot is kept.')
    print(f"Universe {len(snap['securities'])}/{snap.get('eligible_count',snap['universe_count'])} eligible "
          f"({len(snap.get('exclusions',{}))} excluded); complete={snap['universe_complete']}; errors={len(snap['errors'])}")
    for error in snap['errors'][:12]: print(error)
    return 0 if snap['universe_complete'] else 2

if __name__=='__main__':
    raise SystemExit(main())
