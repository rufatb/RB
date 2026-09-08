#!/usr/bin/env python3
"""Discover primary-source filing candidates; never infer a catalyst date.

SEC 8-K, 6-K and periodic filings form a review queue, not a complete clinical
calendar. Issuer guidance, FDA schedules and conference programs must supplement
it. Only evidence-reviewed records meeting biotech.validate_event can enter
biotech_events.json. SEC identification must be configured, never impersonated.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
import biotech
from build_biotech import write_atomic


class SEC:
    def __init__(self, user_agent):
        if not user_agent or '@' not in user_agent:
            raise ValueError('Set RB_SEC_USER_AGENT to your application name and contact email')
        self.user_agent=user_agent
        self.last=0.
    def get(self,url):
        # Single-threaded, no more than five requests/second, no 403 retry storm.
        time.sleep(max(0,.2-(time.monotonic()-self.last)))
        self.last=time.monotonic()
        req=urllib.request.Request(url,headers={'User-Agent':self.user_agent,'Accept':'application/json'})
        with urllib.request.urlopen(req,timeout=15) as response:
            return json.load(response)


def filing_candidates(submission,ticker,since,today):
    """Stable accession/document identity; absent fields are an explicit error."""
    recent=submission['filings']['recent'];required=['form','filingDate','accessionNumber','primaryDocument']
    if len({len(recent[k]) for k in required})!=1:
        raise ValueError('SEC filing array lengths differ')
    out=[]
    for form,date,accession,document in zip(*(recent[k] for k in required)):
        if form not in {'8-K','8-K/A','6-K','6-K/A','10-Q','10-K','S-1','S-3','424B5'} or not since<=date<=today:
            continue
        if not document or '/' in document or '..' in document:
            raise ValueError('invalid primary document path')
        cik=str(int(submission['cik']))
        out.append({'candidate_id':f'{cik}:{accession}:{document}','ticker':ticker,
                    'filing_date':date,'form':form,'source_type':'SEC',
                    'source_url':f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace("-","")}/{document}',
                    'review_status':'needs_review',
                    'note':'Read filing/exhibits; confirm issuer readout guidance, FDA milestone, or material financing. Filing date is NOT event date.'})
    return out


def discover(snapshot,now,client):
    universe=biotech.select_universe(snapshot,now)
    mapping=client.get('https://www.sec.gov/files/company_tickers.json')
    by={r['ticker']:r['cik_str'] for r in mapping.values()}
    today=now.date().isoformat();since=(now.date()-dt.timedelta(days=190)).isoformat()
    out={'as_of':now.isoformat(),'coverage':'SEC filing discovery only; requires issuer/FDA/conference review',
         'candidates':[],'errors':[],'reviewed_events':0}
    for s in universe:
        t=s['ticker']
        try:
            cik=by[t]
            sub=client.get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json')
            out['candidates'].extend(filing_candidates(sub,t,since,today))
        except Exception as exc:
            out['errors'].append(f'{t}: {type(exc).__name__}')
    return out


def import_reviewed(source,output,now):
    """Validate a complete reviewed feed before atomic replacement; no partial promotion."""
    feed=json.loads(Path(source).read_text());seen=set()
    for event in feed['events']:
        biotech.validate_event(event,now)
        if event['event_id'] in seen:
            raise ValueError('duplicate event identity')
        seen.add(event['event_id'])
    feed.update(as_of=now.isoformat(),schema_version=1)
    write_atomic(output,feed)
    return len(seen)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',default=os.getenv('RB_BIOTECH_SNAPSHOT_JSON','data/biotech_snapshot.json'))
    p.add_argument('--output',default='data/biotech_candidates.json')
    p.add_argument('--import-reviewed',help='JSON feed with evidence-reviewed event facts')
    a=p.parse_args(argv);now=dt.datetime.now(ZoneInfo('America/New_York'))
    if a.import_reviewed:
        print(f'Imported {import_reviewed(a.import_reviewed,a.output,now)} reviewed events')
        return 0
    try:
        out=discover(json.loads(Path(a.snapshot).read_text()),now,SEC(os.getenv('RB_SEC_USER_AGENT')))
    except Exception as exc:
        out={'as_of':now.isoformat(),'candidates':[],'errors':[type(exc).__name__+': '+str(exc)[:160]]}
    write_atomic(a.output,out)
    print(f"Candidates: {len(out['candidates'])}; errors: {len(out['errors'])}")
    return 2 if out['errors'] else 0

if __name__=='__main__':
    raise SystemExit(main())
