"""Import an actually retrieved Massive daily-bar response as dated context.

No HTTP or credentials. The caller supplies the connected provider's CSV
response, exact ticker and actual retrieval clock. Preserve raw evidence and
refuse conflicting same-session prices; never mutate publications or holdings.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo
from quotes import stamp, number, reference_close
from build_biotech import write_atomic


def import_response(response, ticker, state_dir, retrieved_at):
    if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,20}',ticker) or ticker.endswith('.TO'):
        raise ValueError('exact US ticker required; Massive US bars are not TSX coverage')
    now=stamp(retrieved_at).astimezone(ZoneInfo('America/New_York'))
    rows=list(csv.DictReader(io.StringIO(response)))
    if len(rows)!=1 or rows[0].get('T')!=ticker:
        raise ValueError('one returned bar with matching ticker required')
    r=rows[0]; close=number(r.get('c'),positive=True)
    timestamp=int(r['t'])
    session=stamp(timestamp/1000).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    endpoint=f'/v2/aggs/ticker/{ticker}/prev'
    digest=hashlib.sha256(response.encode()).hexdigest()
    relative=f'evidence/Massive-{ticker}-{session}-{digest[:12]}.csv'
    row=dict(ticker=ticker,currency='USD',session=session,close=close,provider='Massive',
             retrieved_at=now.isoformat(),source_url='https://api.massive.com'+endpoint,
             provider_endpoint=endpoint,documentation_url='https://massive.com/docs/rest/stocks/aggregates/previous-day-bar',
             observation=dict(ticker=r['T'],close=close,timestamp_ms=timestamp),
             response_sha256=digest,evidence_path=relative)
    checked=reference_close(row,ticker,now)
    if checked['status']!='OK': raise ValueError(checked.get('reason','invalid daily reference'))
    state=Path(state_dir)
    if not (state/'reports.sqlite3').is_file():
        raise ValueError('existing operational history required')
    path=state/'reference_closes.json'
    references=json.loads(path.read_text()) if path.exists() else {}
    old=references.get(ticker,{})
    if old.get('session')==session and number(old.get('close'))!=close:
        raise ValueError('conflicting previously recorded reference close')
    if old.get('session','')>session or (old.get('retrieved_at') and stamp(old['retrieved_at'])>stamp(now)):
        raise ValueError('newer reference already retained')
    evidence=state/relative;evidence.parent.mkdir(parents=True,exist_ok=True)
    evidence.write_text(response)
    references[ticker]=row
    write_atomic(path,references)
    return row


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--response',required=True);p.add_argument('--ticker',required=True)
    p.add_argument('--state-dir',required=True);p.add_argument('--retrieved-at',required=True)
    a=p.parse_args()
    row=import_response(Path(a.response).read_text(),a.ticker,a.state_dir,a.retrieved_at)
    print(json.dumps({k:row[k] for k in ('ticker','provider','session','close','response_sha256')}))
