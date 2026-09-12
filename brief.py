#!/usr/bin/env python3
"""One daily computation feeding text, HTML and JSON renderers.

Part 1 retains the full intraday board, baseline research record and hypothetical
allocation. The 09:45 signal reference is distinct from the 09:46 execution
quote. Part 2 is an independent factual biotech monitor. No renderer fetches,
re-picks, sizes, scores or persists anything. No component submits orders.

Use --publish once at 09:46 ET; publication persists even on zero-pick days.
Previews never write ledgers; offline runs also avoid network acquisition. Source errors
are data in the report, not absent observations interpreted as clean evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import hashlib
import os
import math
from collections.abc import Mapping
from pathlib import Path
from zoneinfo import ZoneInfo

import biotech
import execution
import ledger
import positions
import quotes as quotes_mod
from quotes import market_client, validate_equity, stamp
from report_store import Store, encode
from diagnostics import safe_detail, safe_error

ROOT = Path(__file__).resolve().parent


class Digest(dict):
    """JSON-compatible unified computation; renderers consume it without acquisition."""


def _ledger_rows(loader, now, errors):
    """Validate read boundaries without modifying any source row or protected ledger."""
    try:
        original = loader()
        if not isinstance(original, list):
            raise ValueError('ledger is not a row list')
    except Exception as exc:
        errors.append(safe_error('ledger', exc, 'Ledger unavailable; fresh selection blocked to avoid replacing an unknown published board.'))
        return [], [], {'status': 'UNAVAILABLE', 'invalid_rows': 0, 'selection_blocked': True}
    valid, rejected = [], []
    blocked = False
    for index, row in enumerate(original):
        try:
            if not isinstance(row, Mapping):
                raise ValueError('row is not an object')
            day = dt.date.fromisoformat(row['date'])
            if not isinstance(row['ticker'], str) or not row['ticker'].strip() or row['side'] not in ('LONG', 'SHORT'):
                raise ValueError('invalid ticker or side')
            if row.get('hit', '') not in ('', '0', '1', 0, 1):
                raise ValueError('invalid recorded hit')
            for key in ('p945', 'p_sided', 'shares', 'weight', 'spread_bps', 'r1'):
                if row.get(key) not in (None, ''):
                    value = float(row[key])
                    if not math.isfinite(value) or (key in ('p945', 'shares') and value <= 0):
                        raise ValueError('invalid recorded '+key)
            valid.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            # An invalid/missing session date may hide today's original board.
            candidate_day = row.get('date') if isinstance(row, Mapping) else None
            try:
                candidate_day = dt.date.fromisoformat(candidate_day)
            except (ValueError, TypeError):
                candidate_day = None
            blocked |= candidate_day is None or candidate_day == now.date()
            rejected.append({'row_index': index, 'reason': safe_detail(exc)})
    if rejected:
        errors.append(safe_error('ledger', ValueError(), f'{len(rejected)} invalid ledger rows excluded from computed evidence; source records retained.'))
    return valid, original, {'status': 'PARTIAL' if rejected else 'RECORDED',
                             'invalid_rows': len(rejected), 'rejected': rejected,
                             'selection_blocked': blocked}


def _position_rows(loader, now, errors):
    """Reject malformed position rows independently; never turn failure into flat holdings."""
    try:
        original = loader()
        if not isinstance(original, list):
            raise ValueError('position ledger is not a row list')
    except Exception as exc:
        errors.append(safe_error('positions', exc, 'Position ledger unavailable; holdings are unknown.'))
        return [], {'status': 'UNAVAILABLE', 'invalid_rows': 0,
                    'gaps': ['Position ledger unavailable; holdings are unknown.']}
    valid, invalid = [], 0
    for row in original:
        try:
            if not isinstance(row, Mapping) or row.get('status') not in (positions.OPEN, positions.CLOSED):
                raise ValueError('invalid position status')
            if not isinstance(row['ticker'], str) or not row['ticker'].strip() or row['side'] not in ('LONG', 'SHORT'):
                raise ValueError('invalid position identity')
            for field in ('shares', 'entry_px'):
                value = float(row[field])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError('invalid position '+field)
            if row['status'] == positions.OPEN:
                if not row.get('id') or dt.date.fromisoformat(row['entry_date']) > now.date():
                    raise ValueError('invalid position entry identity/date')
            valid.append(row)
        except (ValueError, TypeError, KeyError):
            invalid += 1
    gaps = [f'{invalid} malformed position rows could not be marked; original records retained and holdings may be incomplete.'] if invalid else []
    if invalid:
        errors.append(safe_error('positions', ValueError(), gaps[0]))
    return valid, {'status': 'PARTIAL' if invalid else 'RECORDED', 'invalid_rows': invalid, 'gaps': gaps}


def _compute(cfg_path=None, shadow=True, no_net=False, *, now=None,
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
    live_clock = now is None
    now = now or dt.datetime.now(ZoneInfo('America/New_York'))
    now = stamp(now).astimezone(ZoneInfo('America/New_York'))
    state_dir = state_dir or os.environ.get('RB_STATE_DIR', str(ROOT/'.rb-state'))
    store = Store(state_dir) if publish and not no_net else None
    if store:
        prior = store.get(now.date().isoformat())
        if prior:
            return prior
    cfg = load_config(str(cfg_path if cfg_path is not None else ROOT/'config.yaml'))
    errors = []
    def error(layer, exc):
        errors.append(safe_error(layer, exc, exc))
    try:
        clock = services.get('clock', execution.clock_status)(now)
    except Exception as exc:
        error('calendar',exc)
        clock = {'session':now.date().isoformat(),'status':'CALENDAR UNAVAILABLE',
                 'eligible':False,'entry_time':'09:46','exit_time':'15:59','close_at':None}
    rows, original_rows, ledger_status = _ledger_rows(services.get('ledger',ledger.load), now, errors)
    # Do not grade today's partial session or display future-dated rows.
    past_rows = [r for r in rows if r['date'] < now.date().isoformat()]
    pair_rows = [r for r in past_rows if r.get('role')=='pair']
    recorded_today = [r for r in rows if r['date']==now.date().isoformat()]
    record = ledger.accuracy(pair_rows)
    record.update(status=ledger_status['status'], invalid_rows=ledger_status['invalid_rows'])
    record['label'] = 'Historical 09:45-bar to official-close PROXY; not exact 09:46–15:59 fills'
    record['benchmark_label'] = 'Historical universe median is not an index; exact index record starts with this version'
    record['future_rows_excluded'] = sum(r['date'] > now.date().isoformat() for r in rows)
    prows, position_status = _position_rows(services.get('positions',positions.load), now, errors)
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
        if not recorded_today and not ledger_status['selection_blocked'] and not clock['status'].startswith(('SHORT_SESSION','CALENDAR','PREPARING')):
            tasks['intraday'] = (lambda: r945.run(cfg,require_cache=publish), 22)
        section_status = acquire(tasks)
        raw_live = section_status['equity_quotes']['value'] or {}
        for name, result in section_status.items():
            if result['error']:
                last_stage = (result.get('progress') or [{}])[-1].get('stage', 'not recorded')
                errors.append({'layer': name, 'error': result['error'],
                               'detail': f"Independent section failed after {result['seconds']}s; last stage: {last_stage}; other sections retained."})
    res = {'now':now.isoformat(),'longs':[],'shorts':[], 'pair':{}, 'evaluated':[],
           'coverage_fail':None,'fetch_errors':{},'n_names':0}
    if ledger_status['selection_blocked']:
        res['coverage_fail']='LEDGER UNAVAILABLE / INVALID SESSION RECORD — original board cannot be safely replaced; fresh selection blocked'
        res['source']='record integrity unavailable'
    elif recorded_today:
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
                errors.append({'layer':'intraday','error':'DATA_UNAVAILABLE','detail':safe_detail(f'{ticker}: {why}')})
            res['fetch_errors'] = {str(t):safe_detail(why) for t,why in res.get('fetch_errors',{}).items()}
        except Exception as exc:
            res['coverage_fail']='intraday computation unavailable'; error('intraday',exc)
    res['live_record'] = ledger.live_summary([{**r,'hit':r.get('hit','')} for r in past_rows])
    try:
        client = services.get('market') or market_client()
    except Exception as exc:
        client = None
        error('market_client',exc)
    # One equity call for the full board, open positions and independent index.
    tickers = {r['t'] for r in res.get('longs',[])+res.get('shorts',[])}
    tickers |= {r['t'] for r in res.get('factor_candidates',[])}
    tickers |= {r['ticker'] for r in prows if r.get('status')==positions.OPEN}
    tickers |= {r['ticker'] for r in rows if r['date']==now.date().isoformat()}
    tickers.add('XIU.TO')
    quotes = {}
    if not no_net and clock['status'] != 'CLOSED':
        try:
            raw = raw_live if raw_live is not None else client.get(sorted(tickers))
            if live_clock:
                now = dt.datetime.now(ZoneInfo('America/New_York'))
            # OFF BY DEFAULT. Yahoo serves a usable bid/ask with no quote
            # timestamp, so `fresh()` fails on every name and every leg
            # abstains on this provider forever — 2026-09-10 and 09-11 both
            # abstained with uncrossed books and 1.5-15bps spreads. The
            # corroborator checks the quoted mid against a TIMESTAMPED
            # one-minute trade bar and can only return CORROBORATED, never OK.
            # Enabling it changes what the engine will SIZE, so it is a
            # deliberate config decision and not a default. See
            # quotes.corroborate_bbo.
            corr = (quotes_mod.minute_bar_corroborator()
                    if (cfg.get('execution') or {}).get('corroborate_bbo')
                    else None)
            quotes = quotes_mod.validate_equities(raw,tickers,now,corroborate=corr)
            for ticker, quote in quotes.items():
                if quote.get('error_class'):
                    errors.append({'layer':'equity_quotes','error':safe_detail(quote['error_class'],60),
                                   'detail':safe_detail(f"{ticker}: {quote.get('reason','quote unavailable')}")})
        except Exception as exc:
            # Provider exception text can contain authentication URLs: record class only.
            error('equity_quotes',RuntimeError(type(exc).__name__))
    for t in tickers:
        quotes.setdefault(t, {'ticker':t,'status':'UNAVAILABLE','reason':'quote unavailable',
                              'mark':None,'spread_bps':None})
    book = positions.mark_book(prows, {t:q['mark'] for t,q in quotes.items() if q.get('mark') is not None},now.date())
    book.update(position_status)
    book['verification'] = 'Recorded ledger only — holdings have not been reconciled with a brokerage account.'
    if position_status['gaps']:
        book['verification'] += ' ' + ' '.join(position_status['gaps'])
    book['recent_closed']=[]
    from quotes import number
    for row in prows:
        if row.get('status')!=positions.CLOSED: continue
        try:
            day=dt.date.fromisoformat(row['exit_date'])
            if not 0 <= (now.date()-day).days <= 7: continue
            shares,entry,exit_px=(number(row.get(k),positive=True) for k in ('shares','entry_px','exit_px'))
            if None in (shares,entry,exit_px) or row.get('side') not in ('LONG','SHORT'):
                raise ValueError('invalid recorded closed position')
            pct,dollars=positions.pnl(row['side'],entry,exit_px,shares)
            book['recent_closed'].append(dict(ticker=row['ticker'],side=row['side'],shares=shares,
                entry_px=entry,exit_px=exit_px,exit_date=row['exit_date'],pnl_pct=pct,pnl_usd=dollars))
        except (ValueError,KeyError,TypeError) as exc:
            error('closed_position',exc)
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
             'errors':[safe_detail(f'{type(exc).__name__}: {exc}')],'universe_n':0,'screened_events':0,'top_limit':2}
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
    import eodhd
    provider_evidence = eodhd.load_prepared(state_dir, now)
    # Model assessment was staged before the open. This path is local and pure:
    # neither a missing snapshot nor a renderer can call an LLM or repick a board.
    import deepseek_factors
    from scan import deepseek_shadow
    try:
        factor_evidence = deepseek_factors.load_prepared(state_dir, now)
        factor_evidence['shadow'] = deepseek_shadow(
            res.get('factor_candidates', []), factor_evidence, quotes, now, cfg,
            scan_available=not bool(res.get('coverage_fail')) and not no_net)
    except Exception as exc:
        error('deepseek', RuntimeError(type(exc).__name__))
        factor_evidence = deepseek_factors.unavailable('Optional factor assembly failed: '+type(exc).__name__)
    try:
        ledger_hash=hashlib.sha256(encode(original_rows).encode()).hexdigest()
    except (TypeError,ValueError) as exc:
        ledger_hash=None
        errors.append(safe_error('ledger_provenance',exc,'Malformed source ledger cannot be encoded; original file is unchanged.'))
    # Optional local factor validation can consume CPU after acquisition. Use
    # the actual assembly clock, rather than retaining stale 09:46 eligibility.
    if live_clock:
        now = dt.datetime.now(ZoneInfo('America/New_York'))
        try:
            clock = execution.clock_status(now)
        except Exception as exc:
            clock['eligible'] = False
            error('calendar_assembly_check', exc)
        if not clock.get('eligible'):
            legs = [{**leg, 'status':'ABSTAIN',
                     'reasons':list(dict.fromkeys([*leg.get('reasons', []), clock['status']]))}
                    for leg in legs]
    report = {'schema_version':2,'session':now.date().isoformat(),'generated_at':now.isoformat(),
              'provenance':{'code_commit':release,
                            'config_sha256':hashlib.sha256(encode(cfg).encode()).hexdigest(),
                            'r945_sha256':hashlib.sha256((ROOT/'r945.py').read_bytes()).hexdigest(),
                            'ledger_snapshot_sha256':ledger_hash,
                            'universe':cfg.get('scan',{}).get('universe',[]),
                            'biotech_source':'independent staged evidence feed'},
              'clock':clock,'offline':no_net,'shadow':shadow,'errors':errors,
              'sections':{k:{a:b for a,b in v.items() if a!='value'} for k,v in section_status.items()},
              'intraday':{'res':res,'legs':legs,'record':record,'publish':pub,
                          'benchmark':benchmark,'benchmark_symbol':'XIU.TO','exact_record':exact_record,
                          'contract':'09:46 entry / 15:59 exit, same session',
                          'model_claim':'No demonstrated predictive edge; score, density and sided-P are diagnostics.',
                          'recorded_today':recorded_today, 'risk_evidence':risk,
                          'ledger_status':ledger_status,
                          'deepseek':factor_evidence,
                          'historical_provider':provider_evidence},
              'biotech':bio,'positions':book,'research_calendar':calendar,
              'research':{'registration':'PREREGISTER_day90.md','status':'SHADOW — no strategy adoption',
                          'mde':'Historical 2-session proxy MDE80: 64.10 bps versus 5 bps target (UNDERPOWERED). Exact-arm MDE unavailable without matched BBO/cost/index observations.'},
              'report_status':'OFFLINE' if no_net else ('ON_TIME' if clock['eligible'] else 'INFORMATIONAL')}
    from readiness import assess
    report['readiness'] = assess(report)
    boundary_gaps = position_status['gaps'] + ([f"Ledger {ledger_status['status']}: {ledger_status['invalid_rows']} invalid rows; historical evidence may be incomplete."]
                                               if ledger_status['status'] != 'RECORDED' else [])
    report['readiness']['gaps'].extend(boundary_gaps)
    if boundary_gaps:
        report['readiness']['status']='PARTIAL'
    if not no_net and report['readiness']['gaps']:
        report['report_status'] += ' — PARTIAL DATA; consult section status'
    if store and now.strftime('%H:%M') == '09:46':
        return store.publish(report['session'],report)
    return json.loads(encode(report))



def compute(cfg_path=None, shadow=True, no_net=False, *, now=None,
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


def outage_digest(now, exc):
    """Factual local-record fallback; never invoke providers, a selector or an LLM.

    This is used only when no immutable publication exists and assembly failed.
    Missing sections are explicitly unavailable, not observed zero positions or
    a fully evaluated zero-opportunity scan. Original CSV records stay untouched.
    """
    now=stamp(now).astimezone(ZoneInfo('America/New_York'))
    errors=[safe_error('daily_job',exc,'Local report assembly failed; live scan unavailable. No second model or network pass was attempted.')]
    rows,_,lstatus=_ledger_rows(ledger.load,now,errors)
    recorded=[r for r in rows if r['date']==now.date().isoformat()]
    historical=[r for r in rows if r['date']<now.date().isoformat() and r.get('role')=='pair']
    try:
        record=ledger.accuracy(historical)
    except Exception as record_exc:
        errors.append(safe_error('ledger_evidence',record_exc,'Historical evidence could not be computed; rates and returns are unknown.'))
        lstatus['status']='UNAVAILABLE'
        record={'n':0,'hits':0,'rate':None,'mean':None,'net_rate':None,'net_mean':None,
                'net_n':0,'net_unpriced':0}
    record.update(status=lstatus['status'],invalid_rows=lstatus['invalid_rows'],
                  label='Historical 09:45-bar to official-close PROXY; no new outcome measured.',
                  benchmark_label='Exact index evidence unavailable in assembly fallback.')
    prows,pstatus=_position_rows(positions.load,now,errors)
    try:
        book=positions.mark_book(prows,{},now.date())
    except Exception as position_exc:
        errors.append(safe_error('positions',position_exc,'Recorded positions could not be assembled; holdings and marks are unknown.'))
        pstatus={'status':'UNAVAILABLE','invalid_rows':len(prows),
                 'gaps':['Recorded positions could not be assembled; holdings are unknown.']}
        book={'legs':[],'stale':0,'net_usd':None,'gross':None,'net_pct':None,
              'unassembled_records':prows}
    book.update(pstatus)
    book.update(recent_closed=[],verification='Recorded ledger only; live marks unavailable and holdings have not been independently reconciled.')
    if pstatus['gaps']:
        book['verification']+=' '+' '.join(pstatus['gaps'])
    quote={'ticker':'XIU.TO','status':'UNAVAILABLE','reason':'assembly failed; quote not acquired',
           'mark':None,'spread_bps':None}
    report=Digest(schema_version=2,session=now.date().isoformat(),generated_at=now.isoformat(),
        provenance={'code_commit':None,'biotech_source':'unavailable after assembly failure'},
        clock={'session':now.date().isoformat(),'status':'ASSEMBLY UNAVAILABLE','eligible':False,
               'entry_time':'09:46','exit_time':'15:59','close_at':None},
        offline=True,shadow=True,errors=errors,sections={},
        intraday={'res':{'longs':[],'shorts':[],'pair':{},'evaluated':[],'fetch_errors':{},'n_names':0,
                         'coverage_fail':'SCAN UNAVAILABLE — report assembly failed; not a zero-opportunity result',
                         'source':'local recorded facts only'},
                  'legs':[],'record':record,'recorded_today':recorded,'ledger_status':lstatus,
                  'publish':{'picks':0,'pair':0,'already':False,'errors':[]},
                  'benchmark':quote,'benchmark_symbol':'XIU.TO',
                  'exact_record':execution.observed_performance([],[]),'risk_evidence':{},
                  'historical_provider':{'status':'NOT CONFIGURED'},
                  'contract':'09:46 entry / 15:59 exit, same session',
                  'model_claim':'SCAN UNAVAILABLE; no current prediction or execution claim.'},
        biotech={'status':'UNAVAILABLE','monitor':[],'crowded':[],'unverified':[],
                 'errors':['Report assembly failed; staged biotech evidence was not evaluated.'],
                 'universe_n':0,'screened_events':0,'top_limit':2},
        positions=book,research_calendar={'events':[],'gaps':['Reviewed calendar not evaluated after assembly failure.']},
        research={'registration':'PREREGISTER_day90.md','status':'SHADOW — no strategy adoption',
                  'mde':'Unavailable in assembly fallback; no improvement was measured.'},
        readiness={'status':'PARTIAL','gaps':['Local report assembly failed; independent live sections unavailable.',*pstatus['gaps']]},
        report_status='DATA OUTAGE — informational only')
    return report


def build(cfg_path=None, shadow=True, no_net=False, days_back=4, digest=None, **kwargs):
    """Return one unified Digest. Preview by default; explicit publication is durable.

    `compute` remains the compatible acquisition/publication implementation.
    Legacy `digest=` callers receive the same schema; this function never renders.
    """
    report=Digest(compute(cfg_path,shadow,no_net,**kwargs))
    if digest is not None:
        digest.update(report)
    return report


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
    report=build(args.config,args.shadow,args.offline,publish=args.publish,state_dir=args.state_dir)
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
