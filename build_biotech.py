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


def fetch_security(row, now):
    """Verify provider metadata and every one of the last 20 exchange sessions."""
    import yfinance as yf
    import pandas_market_calendars as mcal
    t=row['symbol']
    if row.get('quoteType')!='EQUITY':
        raise ValueError('not an equity')
    obj=yf.Ticker(t)
    info=obj.get_info()
    if info.get('industry')!='Biotechnology' or info.get('exchange') not in biotech.US_EXCHANGES:
        raise ValueError('membership does not match Biotechnology/US-listing query')
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
    out['universe_count']=len(raw)
    if checkpoint: checkpoint(out)
    for offset in range(0,len(raw),workers):
        batch=raw[offset:offset+workers]
        results=acquire({row['symbol']:(lambda row=row:fetch_security(row,now),security_budget) for row in batch})
        stop=False
        for ticker,result in results.items():
            if result['status']=='OK': out['securities'].append(result['value'])
            else:
                out['errors'].append(ticker+': '+result['error'])
                stop |= result['error'] in {'YFRateLimitError','TimeoutExpired'}
        if checkpoint: checkpoint(out)
        if stop:
            out['errors'].append('provider unavailable; remaining symbols not requested')
            break
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


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default=os.getenv('RB_BIOTECH_SNAPSHOT_JSON','data/biotech_snapshot.json'))
    p.add_argument('--events',default=os.getenv('RB_BIOTECH_EVENTS_JSON','data/biotech_events.json'))
    p.add_argument('--refresh-options',action='store_true')
    a=p.parse_args(argv)
    now=dt.datetime.now(ZoneInfo('America/New_York'))
    if a.refresh_options:
        snap=json.loads(Path(a.output).read_text())
        events=json.loads(Path(a.events).read_text())['events']
        snap=refresh_options(snap,events,now)
    else:
        snap=build(now,checkpoint=lambda value:write_atomic(a.output,value))
    write_atomic(a.output,snap)
    print(f"Universe {len(snap['securities'])}/{snap['universe_count']}; complete={snap['universe_complete']}; errors={len(snap['errors'])}")
    for error in snap['errors'][:12]: print(error)
    return 0 if snap['universe_complete'] else 2

if __name__=='__main__':
    raise SystemExit(main())
