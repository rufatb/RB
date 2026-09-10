"""Day97 preregistered five-minute research; never called by the live engine.

Read prepared native bars only. No network, publication, strategy mutation or
order capability. Inadequate history is BLOCKED, not a negative alpha result.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import eodhd as E
from bar_cache import key
from build_biotech import write_atomic

WARMUP = 20
TRAIN = 120
TEST = 60
FOLDS = 5
BLOCK = 20
DRAWS = 2000
SEED = 97
ARMS = {'volume_pace':['r0','gap','vp'],
        'opening_path':['r0','gap','vp','path_accel','path_efficiency']}


def history_requirement(raw_sessions):
    usable = max(0, raw_sessions-WARMUP)
    oos = max(0, usable-TRAIN)
    return {'raw_sessions':raw_sessions, 'volume_warmup':WARMUP,
            'initial_training':TRAIN, 'potential_oos_sessions':oos,
            'minimum_oos_sessions':TEST, 'minimum_raw_sessions':WARMUP+TRAIN+TEST,
            'status':'RUNNABLE' if oos >= TEST else 'BLOCKED — insufficient out-of-sample sessions',
            'mde_auc':None, 'mde_net_bps':None, 'adopted':False}


def session_features(frame, ticker, now):
    """Only first three complete bars enter X; final regular close enters y."""
    now = E.aware(now)
    idx = pd.DatetimeIndex(frame.index)
    if idx.tz is None or idx.has_duplicates or not idx.is_monotonic_increasing:
        raise E.DataGap('INVALID_CACHE_TIMESTAMPS')
    frame = frame.copy()
    frame.index = idx.tz_convert(E.ET)
    if frame.empty:
        raise E.DataGap('EMPTY_CACHE')
    if any(i.date() >= now.date() for i in frame.index):
        raise E.DataGap('CACHE_CONTAINS_TODAY_OR_FUTURE')
    cal = E.schedule(frame.index[0].date(),frame.index[-1].date())
    result, gaps = [], []
    previous = None
    for date, schedule in cal.iterrows():
        grid = pd.date_range(schedule['market_open'],schedule['market_close'],freq='5min',inclusive='left').tz_convert(E.ET)
        day = frame.reindex(grid)
        if len(grid) != 78 or day.isna().any().any():
            gaps.append({'ticker':ticker,'session':str(date.date()),'reason':'missing bars or short session'})
            previous = None
            continue
        for row in day.to_dict('records'):
            E.ohlcv({k.lower():v for k,v in row.items()})
        first = day.iloc[:3]
        o = float(first['Open'].iloc[0])
        p = float(first['Close'].iloc[-1])
        close = float(day['Close'].iloc[-1])
        returns = 100*(first['Close'].to_numpy()/first['Open'].to_numpy()-1)
        r0 = 100*(p/o-1)
        denominator = float(np.abs(returns).sum())
        result.append({'t':ticker,'date':str(date.date()),'r0':r0,
            'gap':100*(o/previous-1) if previous else np.nan,
            'v15':float(first['Volume'].sum()), 'r1':100*(close/p-1),
            'path_accel':float(returns[2]-returns[0]),
            'path_efficiency':r0/denominator if denominator else 0.0})
        previous = close
    return result,gaps


def load_cache(directory, now):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    now = E.aware(now)
    tickers = manifest.get('tickers',[])
    if not manifest.get('complete') or manifest.get('source') != 'yahoo_direct':
        raise E.DataGap('CACHE_NOT_COMPLETE_OR_WRONG_SOURCE')
    if manifest.get('session') != now.date().isoformat() or E.aware(manifest['prepared_at']) > now:
        raise E.DataGap('WRONG_CACHE_SESSION_OR_FUTURE_PREPARATION')
    if not tickers or len(tickers) != len(set(tickers)):
        raise E.DataGap('MISSING_OR_DUPLICATE_UNIVERSE')
    rows,gaps,hashes = [],[],{}
    for ticker in tickers:
        path = directory/key(ticker)
        raw = path.read_bytes()
        hashes[ticker] = hashlib.sha256(raw).hexdigest()
        saved = json.loads(raw)
        if saved.get('ticker') != ticker or saved.get('session') != manifest['session']:
            raise E.DataGap('CACHE_IDENTITY_MISMATCH')
        encoded = json.loads(saved['frame'])
        frame = pd.DataFrame(encoded['data'],columns=encoded['columns'],
                             index=pd.to_datetime(encoded['index'],utc=True))
        one,missing = session_features(frame,ticker,now)
        rows += one
        gaps += missing
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise E.DataGap('NO_COMPLETE_SESSIONS')
    # All arms and the benchmark use the same complete fixed universe/dates.
    counts = panel.groupby('date')['t'].nunique()
    good = set(counts[counts == len(tickers)].index)
    removed = len(panel)-int(panel['date'].isin(good).sum())
    panel = panel[panel['date'].isin(good)].sort_values(['t','date']).reset_index(drop=True)
    if panel.empty:
        raise E.DataGap('NO_COMMON_UNIVERSE_SESSIONS')
    return panel, {'provider':'yahoo_direct','universe':tickers,'input_sha256':hashes,
        'missing_session_details':gaps,'partial_universe_rows_excluded':removed,
        'survivorship':'Current configured universe; not a point-in-time historical universe'}


def paired_summary(y, baseline, candidates, sessions):
    """Session-block uncertainty of paired AUC effects; no net-return claim."""
    from validate_ceiling import auc_influence
    dates = np.unique(sessions)
    if len(dates) < TEST:
        raise E.DataGap('INSUFFICIENT_OOS_SESSIONS')
    effects, daily, estimates = {}, [], []
    for name, scores in candidates.items():
        reference = baseline[name] if isinstance(baseline,dict) else baseline
        base_auc, base_if = auc_influence(y,reference)
        auc, influence = auc_influence(y,scores)
        delta = auc-base_auc
        values = pd.Series(influence-base_if).groupby(sessions).sum().reindex(dates).to_numpy()*len(dates)
        effects[name] = {'auc':auc,'baseline_auc':base_auc,'delta_auc':delta}
        estimates.append(delta)
        daily.append(values)
    influences = np.asarray(daily).T
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(DRAWS):
        starts = rng.integers(0,len(dates)-BLOCK+1,size=int(np.ceil(len(dates)/BLOCK)))
        sample = np.concatenate([np.arange(s,s+BLOCK) for s in starts])[:len(dates)]
        draws.append(influences[sample].mean(axis=0))
    draws = np.asarray(draws)
    # Joint block signs preserve contemporaneous dependence between arms.
    pseudo = influences + np.asarray(estimates)
    placebo = []
    for _ in range(DRAWS):
        signs = np.repeat(rng.choice([-1,1],size=int(np.ceil(len(dates)/BLOCK))),BLOCK)[:len(dates)]
        placebo.append(float((pseudo*signs[:,None]).mean(axis=0).max()))
    for col, (name, scores) in enumerate(candidates.items()):
        effect = effects[name]
        se = float(draws[:,col].std(ddof=1))
        valid = bool(np.isfinite(se) and se > 0)
        effect.update({'sessions':len(dates),'se_auc':se,'mde80_auc':(3.5+.8416212336)*se if valid else None,
            'ci95_auc':[effect['delta_auc']-1.96*se,effect['delta_auc']+1.96*se] if valid else None,
            'valid_inference':valid,'mde_net_bps':None,
            'max_arm_placebo_p':(1+int((np.asarray(placebo)>=effect['delta_auc']).sum()))/(DRAWS+1),
            'statistical_sensitivity_control':{'shift_auc':.02,'detected':bool(valid and .02/se > 3.5),
                'label':'Influence-shift sensitivity only; not an end-to-end planted predictor'},
            'four_blocks':[],'adopted':False})
        for block in np.array_split(dates,4):
            mask = np.isin(sessions,block)
            if len(np.unique(y[mask])) < 2:
                effect['four_blocks'].append(None)
            else:
                a,_ = auc_influence(y[mask],scores[mask])
                reference = baseline[name] if isinstance(baseline,dict) else baseline
                b,_ = auc_influence(y[mask],reference[mask])
                effect['four_blocks'].append(a-b)
        effect['discovery_threshold_exceeded'] = bool(valid and effect['delta_auc'] > effect['mde80_auc']
            and effect['delta_auc'] > 3.5*se and effect['max_arm_placebo_p'] < .05)
    return effects


def analyze(panel, provenance):
    from validate_ceiling import knn_scores
    panel = panel.sort_values(['t','date']).copy()
    if panel.duplicated(['t','date']).any():
        raise E.DataGap('DUPLICATE_TICKER_SESSION')
    panel['vp'] = panel['v15']/panel.groupby('t')['v15'].transform(
        lambda s:s.shift(1).expanding(min_periods=WARMUP).median()).replace(0,np.nan)
    initial = len(panel['date'].unique())
    features = ['r0','gap','vp','path_accel','path_efficiency']
    valid = np.isfinite(panel[features+['r1']].to_numpy()).all(axis=1)
    eligible = panel[valid].copy()
    n_tickers = panel['t'].nunique()
    counts = eligible.groupby('date')['t'].nunique()
    eligible = eligible[eligible['date'].isin(counts[counts==n_tickers].index)].copy()
    dates = np.sort(eligible['date'].unique())
    out = {'registration':'PREREGISTER_day97.md','provenance':provenance,
           'history':history_requirement(initial),'usable_sessions':len(dates),
           'oos_sessions':max(0,len(dates)-TRAIN),'rows':len(eligible),'adopted':False,
           'label':'Five-minute trade-price proxy; no exact fills, costs or index-relative P&L',
           'mde_auc':None,'mde_net_bps':None}
    if len(dates) < TRAIN+TEST:
        out['status'] = 'BLOCKED — insufficient out-of-sample sessions; no strategy result'
        return out
    arms = {'two_features':['r0','gap'],**ARMS}
    output = {name:[] for name in arms}
    labels,session_ids = [],[]
    for a,b in zip(np.linspace(TRAIN,len(dates),FOLDS+1).astype(int)[:-1],
                   np.linspace(TRAIN,len(dates),FOLDS+1).astype(int)[1:]):
        train = eligible[eligible['date'].isin(dates[:a])]
        test = eligible[eligible['date'].isin(dates[a:b])]
        if len(train) < 500 or train['r1'].gt(0).nunique() != 2:
            raise E.DataGap('INSUFFICIENT_TRAINING_ROWS_OR_CLASSES')
        for name, feats in arms.items():
            score = knn_scores(train[feats].to_numpy(),train['r1'].gt(0).to_numpy(int),test[feats].to_numpy())
            if not np.isfinite(score).all():
                raise E.DataGap('NONFINITE_MODEL_OUTPUT')
            output[name].append(score)
        labels.extend(test['r1'].gt(0).to_numpy(int))
        session_ids.extend(test['date'])
    output = {name:np.concatenate(values) for name,values in output.items()}
    # First comparison: vp vs two features. Second: path vs vp. Compute each
    # influence against its own prespecified comparator, then use a joint null.
    y, sessions = np.asarray(labels),np.asarray(session_ids)
    results = paired_summary(y,{'volume_pace':output['two_features'],'opening_path':output['volume_pace']},
                             {name:output[name] for name in ARMS},sessions)
    out.update({'status':'RESEARCH ONLY — no automatic adoption','results':results})
    return out


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-dir',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    now=dt.datetime.now(E.ET)
    try:
        panel, provenance = load_cache(a.cache_dir,now)
        result = analyze(panel,provenance)
    except (E.DataGap,OSError,ValueError,KeyError) as exc:
        result={'status':'BLOCKED — '+type(exc).__name__,'detail':str(exc)[:180],
                'registration':'PREREGISTER_day97.md','adopted':False,'mde_auc':None,'mde_net_bps':None}
    write_atomic(a.output,result)
    print(json.dumps(result,indent=2,allow_nan=False))
    raise SystemExit(2 if result['status'].startswith('BLOCKED') else 0)
