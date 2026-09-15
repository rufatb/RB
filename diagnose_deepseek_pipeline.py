"""Run the real bounded factor pipeline through rendered email at current time.

Explicit interactive diagnostic only. No fake clock, live selection, report
publication, historical rewrite, automatic retry or email transmission.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from diagnostic_context import create_context, ET
from build_biotech import write_atomic
from report_store import encode


def fingerprints(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(root).rglob('*')) if path.is_file() and not path.is_symlink()}


def run(source_state, output_dir, config_path=None, *, expanded=False):
    from dashboard import load_config
    import prepare_factor_pool
    import prepare_deepseek
    import deepseek_factors
    import brief
    import prepare_delivery

    source, output = Path(source_state).resolve(), Path(output_dir).resolve()
    if not (source/'reports.sqlite3').is_file():
        raise ValueError('EXISTING_CANONICAL_STATE_REQUIRED')
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('DIAGNOSTIC_OUTPUT_MUST_BE_SEPARATE_FROM_CANONICAL_STATE')
    if output.exists():
        raise ValueError('FRESH_DIAGNOSTIC_OUTPUT_REQUIRED_NO_RETRY')
    started = dt.datetime.now(ET)
    before = fingerprints(source)
    output.mkdir(parents=True)
    working = output/'state'
    create_context(working, now=started)
    if (source/'intraday_cache').exists():
        shutil.copytree(source/'intraday_cache', working/'intraday_cache')
    repo = Path(__file__).resolve().parent
    cfg = load_config(str(config_path or repo/'config.yaml'))
    revision = subprocess.run(['git','rev-parse','HEAD'], cwd=repo,
        check=True,capture_output=True,text=True).stdout.strip()
    # Populate environment only; never copy secrets into public diagnostics.
    key_gap = None
    try:
        if not prepare_deepseek.load_private_key(source):
            key_gap = 'MISSING_PRIVATE_CREDENTIAL'
        model = prepare_deepseek.load_private_model(source)
    except (OSError,ValueError,UnicodeError) as exc:
        key_gap = type(exc).__name__
        model = None
    record = {'kind':'DEEPSEEK_PIPELINE_DIAGNOSTIC','started_at':started.isoformat(),
              'code_revision':revision,'model':model,'credential_gap':key_gap,
              'morning_snapshot':False,'prediction_evidence':False,
              'sent_email':False,'published_report':False,'stages':{}}
    guards = ExitStack()
    forbidden_calls = []
    def forbidden(*args, **kwargs):
        forbidden_calls.append('FORBIDDEN_REPORT_SIDE_EFFECT')
        raise RuntimeError('FORBIDDEN_REPORT_SIDE_EFFECT')
    write_atomic(output/'pipeline_attempt.json', {**record,'status':'STARTED'})
    try:
        if expanded:
            import prepare_tsx_universe
            then = time.monotonic()
            # A reviewed source may be copied into the isolated diagnostic;
            # canonical publications, attempts and credentials are not copied.
            master = source/'tsx_security_master.json'
            universe = prepare_tsx_universe.prepare(working, diagnostic=True,
                master_path=master if master.is_file() else None)
            record['stages']['universe'] = {key:universe.get(key) for key in
                ('status','session','target','source_coverage','exclusions','reason')}
            record['stages']['universe']['eligible'] = len(universe.get('candidates',[]))
            record['stages']['universe']['elapsed_seconds'] = round(time.monotonic()-then,3)
            if not universe.get('candidates'):
                raise RuntimeError('EXPANDED_UNIVERSE_UNAVAILABLE_NO_MODEL_REQUEST')
            import factor_pool_policy
            if len(universe['candidates']) <= len(factor_pool_policy.TICKERS):
                raise RuntimeError('EXPANDED_POOL_NOT_BROADER_THAN_LEGACY_NO_MODEL_REQUEST')
        if key_gap:
            raise ValueError('PRIVATE_PROVIDER_CONFIGURATION_UNAVAILABLE_NO_FALLBACK')
        then = time.monotonic()
        pool = prepare_factor_pool.prepare_diagnostic(working,cfg)
        record['stages']['pool'] = {key:pool.get(key) for key in
            ('status','requested','verified','complete_technicals','reused_baseline','errors')}
        record['stages']['pool']['elapsed_seconds'] = round(time.monotonic()-then,3)
        write_atomic(output/'pipeline_attempt.json', {**record,'status':'PREPARING_FACTORS'})

        then = time.monotonic()
        prepared = prepare_deepseek.prepare_diagnostic(working,cfg,refresh=True)
        record['stages']['preparation'] = {key:prepared.get(key) for key in
            ('status','source_requested','requested','eligible','submitted','covered','model','gaps','batches')}
        record['stages']['preparation']['elapsed_seconds'] = round(time.monotonic()-then,3)
        snapshot = working/'deepseek_snapshot.json'
        snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        # Tripwires measure forbidden work after acquisition, without replacing
        # the loader, scoring, Digest construction or any rendered data.
        import requests
        import httpx
        import urllib.request
        import adapters.deepseek_adapter
        import analyst
        import r945
        from report_store import Store
        for owner,name in ((requests.Session,'request'), (httpx.Client,'send'),
            (urllib.request,'urlopen'), (adapters.deepseek_adapter,'evaluate_batch'),
            (analyst,'analyze_factors'), (r945,'run'), (r945,'publish'),
            (Store,'publish'), (Store,'claim_delivery')):
            guards.enter_context(patch.object(owner,name,forbidden))
        now = dt.datetime.now(ET)
        loaded = deepseek_factors.load_diagnostic(working,now,snapshot)
        morning_loader = deepseek_factors.load_prepared(working,now,path=snapshot)
        if morning_loader['status'] != 'UNAVAILABLE':
            raise RuntimeError('DIAGNOSTIC_UNEXPECTEDLY_ACCEPTED_AS_MORNING_SNAPSHOT')
        record['stages']['loader'] = {
            key:loaded.get(key) for key in ('status','requested','eligible','submitted','covered','gaps')}
        record['stages']['loader']['morning_loader_rejected_diagnostic'] = True

        # One real Digest, local-only, with the real prepared loader. Empty
        # execution services deliberately mean no position/market experiment.
        digest = brief.build(str(config_path or repo/'config.yaml'),no_net=True,
            state_dir=working,factor_diagnostic=snapshot,services={
                'ledger':lambda:[], 'positions':lambda:[], 'observations':lambda:([],[]),
                'biotech_inputs':lambda:({'universe_complete':False,
                    'errors':['Biotech is outside this factor integration diagnostic.']},[])})
        frozen = encode(digest)
        mail = prepare_delivery.artifacts(digest,output/'dispatch',dt.datetime.now(ET))
        (output/'report.json').write_text(json.dumps(digest,indent=2,allow_nan=False))
        (output/'report.txt').write_text(brief.render_text(digest))
        (output/'report.html').write_text(brief.render_html(digest))
        if encode(digest) != frozen or hashlib.sha256(snapshot.read_bytes()).hexdigest() != snapshot_hash:
            raise RuntimeError('RENDERING_CHANGED_COMPUTATION_OR_SNAPSHOT')
        if digest['intraday']['deepseek']['covered'] != loaded['covered']:
            raise RuntimeError('DIGEST_LOST_PREPARED_ASSESSMENTS')
        if encode(loaded.get('assessments', [])) != encode(prepared.get('assessments', [])):
            raise RuntimeError('LOADER_CHANGED_PREPARED_ASSESSMENTS')
        if encode(digest['intraday']['deepseek'].get('assessments', [])) != encode(loaded.get('assessments', [])):
            raise RuntimeError('DIGEST_CHANGED_PREPARED_ASSESSMENTS')
        rows = loaded.get('assessments',[])
        attachment = mail['attachments'][0]['content']
        missing = [row['ticker'] for row in rows if row['ticker'] not in attachment]
        if missing:
            raise RuntimeError('EMAIL_ATTACHMENT_LOST_ASSESSMENTS')
        watchlist = loaded['research_watchlist']
        if digest['intraday']['deepseek']['research_watchlist']['evaluated'] != watchlist['evaluated']:
            raise RuntimeError('DIGEST_CHANGED_USABLE_ASSESSMENT_COUNT')
        if any('CURRENT-TIME DEEPSEEK DIAGNOSTIC' not in body for body in
               (mail['subject'],mail['text'],mail['html'],attachment)):
            raise RuntimeError('DELIVERY_VIEW_LOST_DIAGNOSTIC_LABEL')
        record['stages']['report'] = {'status':'PASS','single_digest':True,
            'covered':digest['intraday']['deepseek']['covered'],
            'watchlist_usable':watchlist['evaluated'],
            'watchlist_threshold_passes':watchlist['eligible'],
            'watchlist_decision':watchlist['decision'],
            'email_attachment_retained_all_assessments':True,
            'live_quotes_tested':False,'forbidden_side_effect_calls':len(forbidden_calls)}
        if forbidden_calls:
            raise RuntimeError('REPORT_ATTEMPTED_FORBIDDEN_SIDE_EFFECT')
        record['api_successful_batches'] = sum(b.get('status')=='READY' for b in prepared['batches'])
        record['status'] = ('PASS' if rows and watchlist['evaluated']==len(rows)
                            and loaded['covered']==prepared['covered']
                            else 'UNAVAILABLE')
        record['coverage_status'] = loaded['status']
        record['note'] = ('Shared pipeline exercised at the actual current time; partial input coverage '
                          'is not full-pool readiness, a morning execution test or evidence of alpha.')
    except Exception as exc:
        record['status'] = ('UNAVAILABLE' if str(exc) in {
            'EXPANDED_UNIVERSE_UNAVAILABLE_NO_MODEL_REQUEST',
            'EXPANDED_POOL_NOT_BROADER_THAN_LEGACY_NO_MODEL_REQUEST'} else 'FAILED')
        record['failure'] = type(exc).__name__
        # Our fixed upper-case reason codes are safe; external exception text
        # may contain credentials and is never recorded.
        if isinstance(exc, RuntimeError) and str(exc).replace('_','').isalnum() and str(exc).isupper():
            record['failure_reason'] = str(exc)
    finally:
        guards.close()
        record['completed_at'] = dt.datetime.now(ET).isoformat()
        record['canonical_state_unchanged'] = fingerprints(source) == before
        if not record['canonical_state_unchanged']:
            record['status'] = 'FAILED'
            record['failure'] = 'CANONICAL_STATE_CHANGED_DURING_DIAGNOSTIC'
        write_atomic(output/'pipeline_result.json',record)
        write_atomic(output/'pipeline_attempt.json',record)
    return record


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--config')
    parser.add_argument('--expanded',action='store_true',
        help='Stage the strict expanded directory first; no model call if it is unavailable.')
    args=parser.parse_args(argv)
    result=run(args.state_dir,args.output_dir,args.config,expanded=args.expanded)
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
