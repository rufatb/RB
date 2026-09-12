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
from quotes import (market_client, YahooMarketData, validate_equity, stamp,
                    fetch_equities, quote_failure)
from report_store import Store,encode
from execution import score_leg


def collect(store, exit_time, now, client=None, fees_bps=None, slippage_bps=None, borrow_bps=None):
    now=stamp(now).astimezone(ZoneInfo('America/New_York'))
    if exit_time not in {'15:30','15:45','15:59'} or now.strftime('%H:%M') != exit_time:
        raise ValueError('outside registered exit minute; no retrospective quote substitution')
    report=store.get(now.date().isoformat())
    if not report:
        raise ValueError('no frozen morning publication')
    intra=report['intraday']
    with store.connect() as db:
        recorded = {t:json.loads(body) for t,body in db.execute(
            'SELECT ticker,body FROM outcomes WHERE session=? AND exit_time=?',
            (report['session'],exit_time))}
    missing = [leg for leg in intra['legs'] if leg['ticker'] not in recorded]
    if not missing:
        return [recorded[leg['ticker']] for leg in intra['legs']]
    tickers={l['ticker'] for l in missing}|{intra['benchmark_symbol']}
    try:
        # A failed first acquisition is an observation, not permission to retry
        # later within the minute and silently select a more convenient print.
        quotes=fetch_equities(client or market_client(),tickers,now,max_attempts=1)
    except Exception as exc:
        quotes={t:quote_failure(t,exc) for t in tickers}
    for q in quotes.values():
        if q.get('status')=='OK':
            quoted=stamp(q['quote_time']).astimezone(ZoneInfo('America/New_York'))
            if quoted.date()!=now.date() or quoted.strftime('%H:%M')!=exit_time:
                q.update(status='UNAVAILABLE',reason='quote is outside the registered exit minute',
                         reason_code='WRONG_EXECUTION_WINDOW')
    b0=intra['benchmark'];b1=quotes[intra['benchmark_symbol']]
    index_return=None
    if b0.get('status')==b1.get('status')=='OK':
        btime=stamp(b0['quote_time']).astimezone(ZoneInfo('America/New_York'))
        if btime.date()==now.date() and btime.strftime('%H:%M')=='09:46':
            index_return=(b1['mark']/b0['mark']-1)*100
    results=[]
    for l in intra['legs']:
        if l['ticker'] in recorded:
            results.append(recorded[l['ticker']])
            continue
        row={'ticker':l['ticker'],'exit_time':exit_time,'exit_quote':quotes[l['ticker']],
             'index_return_pct':index_return,'status':'INCOMPLETE','error':None,'metrics':None}
        try:
            if row['exit_quote']['status'] != 'OK':
                raise ValueError(row['exit_quote']['reason'])
            entry=stamp(l['entry_time']).astimezone(ZoneInfo('America/New_York'))
            if entry.date()!=now.date() or entry.strftime('%H:%M')!='09:46':
                raise ValueError('entry quote does not certify exact 09:46 execution')
            row['metrics']=score_leg(l,quotes[l['ticker']],index_return,
                                     fees_bps=fees_bps,slippage_bps=slippage_bps,borrow_bps=borrow_bps)
            row['status']='SCORED_BBO_PROXY'
        except (ValueError,KeyError,TypeError) as exc:
            row['error']=str(exc)
        with store.connect() as db:
            # First observation wins, including an outage. Replacing it would
            # select quotes after observing their quality or movement.
            db.execute('INSERT OR IGNORE INTO outcomes VALUES (?,?,?,?)',
                       (report['session'],l['ticker'],exit_time,encode(row)))
            # Return the immutable winner too, including when another collector
            # won the race between our initial read and INSERT OR IGNORE.
            body=db.execute('SELECT body FROM outcomes WHERE session=? AND ticker=? AND exit_time=?',
                (report['session'],l['ticker'],exit_time)).fetchone()[0]
        results.append(json.loads(body))
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
