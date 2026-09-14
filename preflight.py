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
    cfg=load_config(str(Path(__file__).resolve().parent/'config.yaml'))
    history=inspect_cache(cfg,state/'intraday_cache',now)
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
    import deepseek_factors
    factors = deepseek_factors.load_prepared(state, now)
    from yahoo_auth_cache import inspect as inspect_auth
    auth = inspect_auth(state, now)
    # Read the actual prepared candidates and cached histories. A staged
    # success count or manifest by itself is not evidence of usable inputs.
    import research_coverage
    pool = research_coverage.inspect_pool(state, cfg, now, verify_history=True)
    expanded = None
    if (state/'tsx_universe.json').is_file() or pool.get('research_universe'):
        try:
            expanded = research_coverage.load_prepared(state, cfg, now, factors,
                                                       verify_history=True, pool=pool)
        except Exception as exc:
            expanded = {'status':'UNAVAILABLE', 'gaps':['Expanded coverage validation failed: '+type(exc).__name__],
                        'adopted':False}
    return {'checked_at':now.isoformat(),'checks':checks,'intraday_cache':history,
            'optional_historical_provider':provider,
            'optional_deepseek':{k:factors.get(k) for k in
                                ('status','model','requested','eligible','submitted','covered','prepared_at','gaps')},
            'optional_factor_pool':pool, 'optional_expanded_research':expanded,
            'quote_authentication':auth,
            'status':'PARTIAL' if any(v.startswith('NOT READY') for v in checks.values()) else 'PREPARED',
            'note':'Preparation status only; live BBO and final signal are checked at publication.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-dir',required=True)
    p.add_argument('--output');a=p.parse_args();result=check(a.state_dir)
    if a.output: write_atomic(a.output,result)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='PREPARED' else 2)
