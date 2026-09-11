"""Replay a saved cache's label integrity; no network, fitting or publication."""
import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from bar_cache import key
from intraday_history import completed_history
from r945 import session_rows


def paired_differences(daily):
    """Registered sensitivity of corrected labels, never strategy performance."""
    out = dict(sessions=len(daily), delta_bps=float(np.mean(daily)) if daily else None,
               se_bps=None, ci95_bps=None, mde80_bps=None)
    if len(daily) < 20:
        return out
    a = np.asarray(daily, dtype=float)
    rng = np.random.default_rng(98)
    means = []
    for _ in range(2000):
        starts = rng.integers(0, len(a)-4, size=int(np.ceil(len(a)/5)))
        indices = np.concatenate([np.arange(s,s+5) for s in starts])[:len(a)]
        means.append(a[indices].mean())
    se = float(np.std(means,ddof=1))
    if np.isfinite(se) and se > 0:
        out.update(se_bps=se,ci95_bps=[out['delta_bps']-1.96*se,out['delta_bps']+1.96*se],
                   mde80_bps=(3.5+.8416212336)*se)
    return out


def audit(cache, ledger, now=None):
    now = now or dt.datetime.now(ZoneInfo('America/New_York'))
    cache = Path(cache)
    manifest_raw = (cache/'manifest.json').read_bytes()
    manifest = json.loads(manifest_raw)
    prepared = pd.Timestamp(manifest['prepared_at'])
    if (not manifest.get('complete') or manifest.get('source')!='yahoo_direct'
            or prepared.tzinfo is None or prepared > pd.Timestamp(now)
            or manifest.get('session')!=now.date().isoformat()):
        raise ValueError('cache identity/completeness/as-of mismatch')
    tickers = manifest['tickers']
    if not tickers or len(tickers)!=len(set(tickers)):
        raise ValueError('invalid cache universe')
    rows = list(csv.DictReader(Path(ledger).read_text().splitlines()))
    pairs = [r for r in rows if r['role']=='pair' and r['date']<now.date().isoformat()]
    if len({(r['date'],r['ticker']) for r in pairs}) != len(pairs):
        raise ValueError('duplicate published ticker/session')
    old_map, new_map, refs, hashes, diagnostics = {}, {}, {}, {}, []
    started = time.monotonic()
    validation_seconds = 0.0
    for ticker in tickers:
        raw = (cache/key(ticker)).read_bytes()
        hashes[ticker] = hashlib.sha256(raw).hexdigest()
        saved = json.loads(raw)
        if saved['ticker']!=ticker or saved['session']!=manifest['session']:
            raise ValueError('cached symbol/session mismatch')
        f = json.loads(saved['frame'])
        frame = pd.DataFrame(f['data'],columns=f['columns'],
                             index=pd.to_datetime(f['index'],utc=True).tz_convert('America/New_York'))
        if any(i.date()>=now.date() for i in frame.index):
            raise ValueError('prepared cache includes current/future outcomes')
        old = session_rows(frame,ticker)
        start = time.monotonic()
        new = completed_history(frame,ticker,now)
        validation_seconds += time.monotonic()-start
        diagnostics.append(new['diagnostics'])
        old_map.update({(ticker,r['date']):r for r in old})
        new_map.update({(ticker,r['date']):r for r in new['rows']})
        for date,day in frame.groupby(frame.index.date):
            if len(day)>=3:
                refs[ticker,str(date)] = float(day['Close'].iloc[2])
    matched = set(old_map)&set(new_map)
    changes = []
    for k in sorted(matched):
        changed = [f for f in ('r0','gap','v15','r1','mae_dn','mae_up')
                   if (old_map[k][f] is None)!=(new_map[k][f] is None)
                   or (old_map[k][f] is not None and new_map[k][f] is not None
                       and not np.isclose(old_map[k][f],new_map[k][f],rtol=0,atol=1e-10))]
        if changed:
            changes.append(dict(ticker=k[0],session=k[1],fields=changed))
    observations, excluded, daily = [], [], []
    for date in sorted({r['date'] for r in pairs}):
        board = [r for r in pairs if r['date']==date]
        one, errors = [], []
        for r in board:
            k = r['ticker'],date
            if k not in old_map or k not in new_map:
                errors.append(dict(ticker=k[0],reason='unmatched complete historical outcome'))
                continue
            if not np.isfinite(float(r['p945'])) or abs(float(r['p945'])-refs[k])>.01000001:
                errors.append(dict(ticker=k[0],reason='recorded reference differs from cache'))
                continue
            if r['side'] not in ('LONG','SHORT'):
                raise ValueError('invalid published side')
            sign = 1 if r['side']=='LONG' else -1
            old_bps, new_bps = sign*old_map[k]['r1']*100,sign*new_map[k]['r1']*100
            one.append(dict(session=date,ticker=k[0],side=r['side'],
                            legacy_label_bps=old_bps,corrected_label_bps=new_bps))
        if errors:
            excluded.append(dict(session=date,gaps=errors))
        else:
            observations.extend(one)
            daily.append(float(np.mean([r['corrected_label_bps']-r['legacy_label_bps'] for r in one])))
    return dict(status='DESCRIPTIVE LABEL AUDIT — no predictive-accuracy gain established',
                registration='PREREGISTER_day98_training_integrity.md',generated_at=now.isoformat(),
                code_commit=__import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip(),
                manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),input_sha256=hashes,
                ledger_sha256=hashlib.sha256(Path(ledger).read_bytes()).hexdigest(),
                raw_legacy_rows=len(old_map),validated_rows=len(new_map),
                excluded_legacy_rows=len(set(old_map)-set(new_map)),changed_matched_rows=changes,
                history_diagnostics=diagnostics,matched_original_legs=len(observations),
                sign_changes=int(sum((r['legacy_label_bps']>0)!=(r['corrected_label_bps']>0) for r in observations)),
                paired_label_sensitivity=paired_differences(daily),observations=observations,
                excluded_original_boards=excluded,validation_seconds=validation_seconds,
                total_seconds=time.monotonic()-started,adopted_strategy=False,
                exact_net_pnl=None,
                limits=['Cache is already observed development history; no untouched confirmation',
                        'Equal original-leg capacity; actual account fills/costs/index absent',
                        'Old and new endpoint conventions differ where a terminal marker was present'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-dir',required=True);p.add_argument('--ledger',default='ledger.csv')
    p.add_argument('--output',required=True);a=p.parse_args()
    result=audit(a.cache_dir,a.ledger)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in result.items() if k not in
          ('input_sha256','history_diagnostics','changed_matched_rows','observations','excluded_original_boards')},indent=2))
