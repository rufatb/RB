#!/usr/bin/env python3
"""One daily computation feeding text, HTML and JSON renderers.

Part 1 retains the full intraday board, baseline research record and hypothetical
allocation. The 09:45 signal reference is distinct from the 09:46 execution
quote. Part 2 is an independent factual biotech monitor. No renderer fetches,
re-picks, sizes, scores or persists anything. No component submits orders.

Use --publish once at 09:46 ET; publication persists even on zero-pick days.
Offline/preview runs never write ledgers or query the network. Source errors
are data in the report, not absent observations interpreted as clean evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import biotech
import execution
import ledger
import positions
from quotes import market_client, validate_equity, stamp
from report_store import Store, encode

ROOT = Path(__file__).resolve().parent


def _compute(cfg_path='config.yaml', shadow=True, no_net=False, *, now=None,
            publish=False, state_dir=None, services=None):
    """Acquire and compute once. Inject providers/clock for deterministic tests.

    Published re-reads return the frozen report before any provider is called.
    Expensive biotech discovery is staged by build_biotech.py before the open.
    An absent/stale snapshot is explicitly unavailable, never a partial top 2.
    """
    from dashboard import load_config
    import r945
    injected = services is not None
    services = services or {}
    cfg = load_config(str(cfg_path))
    live_clock = now is None
    now = now or dt.datetime.now(ZoneInfo('America/New_York'))
    now = stamp(now).astimezone(ZoneInfo('America/New_York'))
    state_dir = state_dir or os.environ.get('RB_STATE_DIR', str(ROOT/'.rb-state'))
    store = Store(state_dir) if publish and not no_net else None
    if store:
        prior = store.get(now.date().isoformat())
        if prior:
            return prior
    errors = []
    def error(layer, exc):
        errors.append({'layer': layer, 'error': type(exc).__name__, 'detail': str(exc)[:240]})
    try:
        clock = services.get('clock', execution.clock_status)(now)
    except Exception as exc:
        error('calendar',exc)
        clock = {'session':now.date().isoformat(),'status':'CALENDAR UNAVAILABLE',
                 'eligible':False,'entry_time':'09:46','exit_time':'15:59','close_at':None}
    rows = services.get('ledger',ledger.load)()
    # Do not grade today's partial session or display future-dated rows.
    past_rows = [r for r in rows if r['date'] < now.date().isoformat()]
    pair_rows = [r for r in past_rows if r.get('role')=='pair']
    recorded_today = [r for r in rows if r['date']==now.date().isoformat()]
    record = ledger.accuracy(pair_rows)
    record['label'] = 'Historical 09:45-bar to official-close PROXY; not exact 09:46–15:59 fills'
    record['benchmark_label'] = 'Historical universe median is not an index; exact index record starts with this version'
    record['future_rows_excluded'] = sum(r['date'] > now.date().isoformat() for r in rows)
    try:
        prows = services.get('positions',positions.load)()
    except Exception as exc:
        prows=[]; error('positions',exc)
    # Fetch the configured universe once, concurrently with model acquisition.
    # Position marks and biotech evidence must survive an intraday timeout.
    section_status = {}
    raw_live = None
    if not no_net and not injected and clock['status'] != 'CLOSED':
        from bounded import acquire
        tickers = set(cfg.get('scan',{}).get('universe',[])) | {'XIU.TO'}
        tickers |= {r['ticker'] for r in prows if r.get('status')==positions.OPEN}
        tickers |= {r['ticker'] for r in rows if r['date']==now.date().isoformat()}
        tasks = {'equity_quotes': (lambda: market_client().get(sorted(tickers)), 10)}
        if not recorded_today and not clock['status'].startswith(('SHORT_SESSION','CALENDAR','PREPARING')):
            tasks['intraday'] = (lambda: r945.run(cfg), 22)
        section_status = acquire(tasks)
        raw_live = section_status['equity_quotes']['value'] or {}
        for name, result in section_status.items():
            if result['error']:
                errors.append({'layer': name, 'error': result['error'],
                               'detail': f"Independent section failed after {result['seconds']}s; other sections retained."})
    res = {'now':now.isoformat(),'longs':[],'shorts':[], 'pair':{}, 'evaluated':[],
           'coverage_fail':None,'fetch_errors':{},'n_names':0}
    if recorded_today:
        res['coverage_fail']='RECORDED BOARD — original selections retained; fresh selection intentionally not rerun'
        res['source']='published baseline ledger'
    elif no_net:
        res['coverage_fail']='OFFLINE — market data not fetched'
    elif clock['status'] == 'CLOSED' or clock['status'].startswith(('SHORT_SESSION','CALENDAR','PREPARING')):
        res['coverage_fail']=clock['status']
    else:
        try:
            if 'intraday' in section_status:
                res = section_status['intraday']['value'] or {**res, 'coverage_fail':
                    'NOT EVALUATED — intraday acquisition unavailable; not a zero-opportunity result'}
            else:
                res = services.get('intraday',r945.run)(cfg)
            for ticker, why in res.get('fetch_errors',{}).items():
                errors.append({'layer':'intraday','error':'DATA_UNAVAILABLE','detail':f'{ticker}: {why}'})
        except Exception as exc:
            res['coverage_fail']='intraday computation unavailable'; error('intraday',exc)
    res['live_record'] = ledger.live_summary(past_rows)
    try:
        client = services.get('market') or market_client()
    except Exception as exc:
        client = None
        error('market_client',exc)
    # One equity call for the full board, open positions and independent index.
    tickers = {r['t'] for r in res.get('longs',[])+res.get('shorts',[])}
    tickers |= {r['ticker'] for r in prows if r.get('status')==positions.OPEN}
    tickers |= {r['ticker'] for r in rows if r['date']==now.date().isoformat()}
    tickers.add('XIU.TO')
    quotes = {}
    if not no_net and clock['status'] != 'CLOSED':
        try:
            raw = raw_live if raw_live is not None else client.get(sorted(tickers))
            if live_clock:
                now = dt.datetime.now(ZoneInfo('America/New_York'))
            quotes = {t:validate_equity(raw.get(t,{}),t,now,
                                        currency='CAD' if t.endswith('.TO') else 'USD') for t in tickers}
        except Exception as exc:
            # Provider exception text can contain authentication URLs: record class only.
            error('equity_quotes',RuntimeError(type(exc).__name__))
    for t in tickers:
        quotes.setdefault(t, {'ticker':t,'status':'UNAVAILABLE','reason':'quote unavailable',
                              'mark':None,'spread_bps':None})
    book = positions.mark_book(prows, {t:q['mark'] for t,q in quotes.items() if q.get('mark') is not None},now.date())
    book['verification'] = 'Recorded ledger only — holdings have not been reconciled with a brokerage account.'
    try:
        reference_path = os.getenv('RB_REFERENCE_CLOSES_JSON')
        references = json.loads(Path(reference_path).read_text()) if reference_path else {}
        from quotes import reference_close
        for leg in book['legs']:
            leg['quote_reason'] = quotes.get(leg['ticker'],{}).get('reason','quote unavailable')
            leg['event_overdue'] = bool(leg.get('event_date') and leg['event_date'] < now.date().isoformat())
            ref = reference_close(references.get(leg['ticker'],{}), leg['ticker'], now)
            leg['reference'] = ref
            if ref['status']=='OK':
                pct, dollars = positions.pnl(leg['side'],leg['entry_px'],ref['close'],leg['shares'])
                leg['reference'] = {**ref, 'pnl_pct':pct,'pnl_usd':dollars}
    except Exception as exc:
        error('position_references',exc)
    assessed = [{'ticker':p['t'],'shares':p.get('shares'),'price':p.get('p945'),
                 'cost':{'bps':quotes.get(p['t'],{}).get('spread_bps')}}
                for p in res.get('longs',[])+res.get('shorts',[])]
    # Neither biotech data nor results can enter r945 selection/allocation.
    try:
        inputs = services.get('biotech_inputs',biotech.load_inputs)
        snap, events = inputs()
        option_rows = {}
        # Source a pre-open options snapshot where supplied; freshness is still
        # checked by biotech.option_percentile against the report's clock.
        option_rows.update(snap.get('options',{}))
        bio = biotech.scan(snap,events,option_rows,now)
        calendar = biotech.research_calendar(events,now)
    except Exception as exc:
        bio={'status':'UNAVAILABLE','monitor':[],'crowded':[],'unverified':[],
             'errors':[f'{type(exc).__name__}: {exc}'],'universe_n':0,'screened_events':0,'top_limit':2}
        # A missing universe file does not invalidate independently reviewed dates.
        try:
            path = os.getenv('RB_BIOTECH_EVENTS_JSON','data/biotech_events.json')
            calendar = biotech.research_calendar(json.loads(Path(path).read_text())['events'],now)
        except Exception as event_exc:
            calendar = {'events':[], 'gaps':[type(event_exc).__name__]}
    # Deadline checked after acquisition, not just when the process started.
    if live_clock:
        now = dt.datetime.now(ZoneInfo('America/New_York'))
        try:
            clock = execution.clock_status(now)
        except Exception as exc:
            clock['eligible'] = False
            error('calendar_final_check',exc)
    # Baseline ledger preserved separately; exact execution measurements live
    # in Store. A late report never creates a retrospectively chosen board.
    pub = {'picks':0,'pair':0,'already':False,'errors':[]}
    if store and clock['eligible'] and not res.get('coverage_fail'):
        try:
            pub = r945.publish(res,cfg,assessed_costs=assessed)
            for why in pub['errors']:
                errors.append({'layer':'baseline_publication','error':'PUBLISH_ERROR','detail':why})
        except Exception as exc:
            error('baseline_publication',exc)
    legs = execution.evaluate_legs(res,cfg,quotes,clock,shadow)
    from report_store import read_observations
    try:
        past_reports, outcomes = services.get('observations',lambda:read_observations(state_dir))()
        past_reports = [r for r in past_reports if r['session'] < now.date().isoformat()]
        exact_record = execution.observed_performance(past_reports,outcomes)
    except Exception as exc:
        error('execution_record',exc)
        exact_record = execution.observed_performance([],[])
    benchmark = quotes['XIU.TO']
    import risk_evidence
    try:
        risk = risk_evidence.assess(pair_rows, legs, recorded_today, cfg)
    except Exception as exc:
        error('risk_evidence', exc)
        risk = {}
    import subprocess
    try:
        release = subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=ROOT,
            capture_output=True,text=True,check=True,timeout=2).stdout.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        error('release_identity',exc)
        release = None
    report = {'schema_version':2,'session':now.date().isoformat(),'generated_at':now.isoformat(),
              'provenance':{'code_commit':release,
                            'config_sha256':hashlib.sha256(encode(cfg).encode()).hexdigest(),
                            'r945_sha256':hashlib.sha256((ROOT/'r945.py').read_bytes()).hexdigest(),
                            'ledger_snapshot_sha256':hashlib.sha256(encode(rows).encode()).hexdigest(),
                            'universe':cfg.get('scan',{}).get('universe',[]),
                            'biotech_source':'independent staged evidence feed'},
              'clock':clock,'offline':no_net,'shadow':shadow,'errors':errors,
              'sections':{k:{a:b for a,b in v.items() if a!='value'} for k,v in section_status.items()},
              'intraday':{'res':res,'legs':legs,'record':record,'publish':pub,
                          'benchmark':benchmark,'benchmark_symbol':'XIU.TO','exact_record':exact_record,
                          'contract':'09:46 entry / 15:59 exit, same session',
                          'model_claim':'No demonstrated predictive edge; score, density and sided-P are diagnostics.',
                          'recorded_today':recorded_today, 'risk_evidence':risk},
              'biotech':bio,'positions':book,'research_calendar':calendar,
              'research':{'registration':'PREREGISTER_day90.md','status':'SHADOW — no strategy adoption',
                          'mde':'Historical 2-session proxy MDE80: 64.10 bps versus 5 bps target (UNDERPOWERED). Exact-arm MDE unavailable without matched BBO/cost/index observations.'},
              'report_status':'OFFLINE' if no_net else ('ON_TIME' if clock['eligible'] else 'INFORMATIONAL')}
    from readiness import assess
    report['readiness'] = assess(report)
    if not no_net and report['readiness']['gaps']:
        report['report_status'] += ' — PARTIAL DATA; consult section status'
    if store and now.strftime('%H:%M') == '09:46':
        return store.publish(report['session'],report)
    return json.loads(encode(report))



def compute(cfg_path='config.yaml', shadow=True, no_net=False, *, now=None,
            publish=False, state_dir=None, services=None):
    """Serialize the entire publication, including the legacy CSV side effects.

    POSIX file locking is appropriate for the supplied Linux/systemd host.
    Previews and offline calls do not create state or acquire write locks.
    """
    if not publish or no_net:
        return _compute(cfg_path,shadow,no_net,now=now,publish=False,
                        state_dir=state_dir,services=services)
    import fcntl
    directory=Path(state_dir or os.environ.get('RB_STATE_DIR',str(ROOT/'.rb-state')))
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'publication.lock').open('a') as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        try:
            return _compute(cfg_path,shadow,no_net,now=now,publish=True,
                            state_dir=directory,services=services)
        finally:
            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def render_text(report):
    """Pure: rendering consumes only the computed snapshot."""
    import daily_render
    return daily_render.text(report)


def render_html(report):
    """Pure HTML over exactly the same model as terminal/email/JSON."""
    import daily_render
    return daily_render.html(report)


def build(cfg_path='config.yaml', shadow=True, no_net=False, days_back=4, digest=None):
    """Compatibility facade. Preview only; use --publish for durable publication."""
    report=compute(cfg_path,shadow,no_net)
    if digest is not None:
        digest.update(report)
    return render_text(report)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(ROOT/'config.yaml'))
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--shadow',action='store_true',default=True)
    parser.add_argument('--full',action='store_true',help='compatibility: full intraday board is always included')
    parser.add_argument('--days-back',type=int,default=4,help=argparse.SUPPRESS)
    parser.add_argument('--format',choices=('text','html','json'),default='text')
    parser.add_argument('--output')
    parser.add_argument('--state-dir')
    args=parser.parse_args(argv)
    report=compute(args.config,args.shadow,args.offline,publish=args.publish,state_dir=args.state_dir)
    value=encode(report) if args.format=='json' else render_html(report) if args.format=='html' else render_text(report)
    if args.output:
        Path(args.output).write_text(value)
    else:
        print(value)
    return 0


def __getattr__(name):
    # Backward-compatible formatting helpers. They are not the daily pipeline.
    if name in {'render_positions','render_actions','render_catalyst_detail','render_intraday',
                'render_record','pair_reasoning'}:
        import legacy_brief
        return getattr(legacy_brief,name)
    raise AttributeError(name)


if __name__=='__main__':
    raise SystemExit(main())
