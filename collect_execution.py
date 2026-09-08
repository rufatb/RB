#!/usr/bin/env python3
"""Capture exit quotes at registered clocks and score the exact-window record.

Run at 15:30, 15:45 and 15:59 ET. Never backfill from a later quote, daily close
or historical 5-minute bar. Missing costs/quotes produce explicit incomplete
outcomes and remain outside net P&L statistics.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo
from quotes import market_client,YahooMarketData,validate_equity,stamp
from report_store import Store,encode
from execution import score_leg


def collect(store, exit_time, now, client=None, fees_bps=None, slippage_bps=None, borrow_bps=None):
    now=stamp(now).astimezone(ZoneInfo('America/New_York'))
    if exit_time not in {'15:30','15:45','15:59'} or now.strftime('%H:%M') != exit_time:
        raise ValueError('outside registered exit minute; no retrospective quote substitution')
    report=store.get(now.date().isoformat())
    if not report:
        raise ValueError('no frozen morning publication')
    client=client or market_client()
    intra=report['intraday']
    tickers={l['ticker'] for l in intra['legs']}|{intra['benchmark_symbol']}
    raw=client.get(sorted(tickers))
    quotes={t:validate_equity(raw.get(t,{}),t,now,currency='CAD' if t.endswith('.TO') else 'USD') for t in tickers}
    for q in quotes.values():
        if q.get('status')=='OK' and stamp(q['quote_time']).astimezone(ZoneInfo('America/New_York')).strftime('%H:%M')!=exit_time:
            q.update(status='UNAVAILABLE',reason='quote is outside the registered exit minute')
    b0=intra['benchmark'];b1=quotes[intra['benchmark_symbol']]
    index_return=None
    if b0.get('status')==b1.get('status')=='OK':
        btime=stamp(b0['quote_time']).astimezone(ZoneInfo('America/New_York'))
        if btime.date()==now.date() and btime.strftime('%H:%M')=='09:46':
            index_return=(b1['mark']/b0['mark']-1)*100
    results=[]
    for l in intra['legs']:
        row={'ticker':l['ticker'],'exit_time':exit_time,'exit_quote':quotes[l['ticker']],
             'index_return_pct':index_return,'status':'INCOMPLETE','error':None,'metrics':None}
        try:
            entry=stamp(l['entry_time']).astimezone(ZoneInfo('America/New_York'))
            if entry.date()!=now.date() or entry.strftime('%H:%M')!='09:46':
                raise ValueError('entry quote does not certify exact 09:46 execution')
            row['metrics']=score_leg(l,quotes[l['ticker']],index_return,
                                     fees_bps=fees_bps,slippage_bps=slippage_bps,borrow_bps=borrow_bps)
            row['status']='SCORED_BBO_PROXY'
        except (ValueError,KeyError,TypeError) as exc:
            row['error']=str(exc)
        results.append(row)
        with store.connect() as db:
            # First observation wins, including an outage. Replacing it would
            # select quotes after observing their quality or movement.
            db.execute('INSERT OR IGNORE INTO outcomes VALUES (?,?,?,?)',
                       (report['session'],l['ticker'],exit_time,encode(row)))
    return results


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exit',required=True,choices=['15:30','15:45','15:59'])
    p.add_argument('--state-dir',default=os.getenv('RB_STATE_DIR','.rb-state'))
    p.add_argument('--fees-bps',type=float);p.add_argument('--slippage-bps',type=float)
    p.add_argument('--borrow-bps',type=float,help='Verified holding-period short borrow cost, not annual APR')
    a=p.parse_args(argv)
    rows=collect(Store(a.state_dir),a.exit,dt.datetime.now(ZoneInfo('America/New_York')),
                 fees_bps=a.fees_bps,slippage_bps=a.slippage_bps,borrow_bps=a.borrow_bps)
    print(json.dumps(rows,indent=2))
    return 0 if all(r['status']=='SCORED_BBO_PROXY' for r in rows) else 2

if __name__=='__main__':
    raise SystemExit(main())
