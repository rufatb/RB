"""Read-only pre-open readiness checks; missing prerequisites are explicit."""
import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import biotech
from build_biotech import write_atomic


def check(state,now=None):
    now=now or dt.datetime.now(ZoneInfo('America/New_York'));state=Path(state)
    checks={}
    from bar_cache import inspect_cache
    from dashboard import load_config
    history=inspect_cache(load_config(str(Path(__file__).resolve().parent/'config.yaml')),state/'intraday_cache',now)
    checks['intraday_history']=history['status']+' — '+f"{history['verified']}/{history['expected']} history files verified"
    try:
        snap=json.loads((state/'biotech_snapshot.json').read_text())
        eligible=biotech.select_universe(snap,now)
        checks['biotech_universe']=f'READY — {len(eligible)} names in strict intersection'
    except (OSError,ValueError,KeyError,TypeError) as exc:
        checks['biotech_universe']='NOT READY — '+str(exc)[:300]
    try:
        events=json.loads((state/'biotech_events.json').read_text())['events']
        cal=biotech.research_calendar(events,now)
        checks['reviewed_calendar']=f"{len(cal['events'])} current verified events; {len(cal['gaps'])} quarantined"
        if not cal['events']: checks['reviewed_calendar']='NOT READY — empty/currently unverified event feed'
    except (OSError,ValueError,KeyError,TypeError): checks['reviewed_calendar']='NOT READY — reviewed event feed missing'
    import eodhd
    provider = eodhd.load_prepared(state,now)
    return {'checked_at':now.isoformat(),'checks':checks,'intraday_cache':history,
            'optional_historical_provider':provider,
            'status':'PARTIAL' if any(v.startswith('NOT READY') for v in checks.values()) else 'PREPARED',
            'note':'Preparation status only; live BBO and final signal are checked at publication.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-dir',required=True)
    p.add_argument('--output');a=p.parse_args();result=check(a.state_dir)
    if a.output: write_atomic(a.output,result)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='PREPARED' else 2)
