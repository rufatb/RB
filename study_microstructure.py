"""Fixed day97 retrospective gates over original recorded selections.

No network, refitting, live imports, publication or orders. Read the separate
registration before running. Trade-price/friction scenarios are not actual P&L.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import eodhd as E
from bar_cache import key
from build_biotech import write_atomic

ARMS=('baseline_proxy','delay_only','rvol_2p5','orb_vwap','orb_vwap_rvol',
      'exit_1130','half_exit_1130')
REGISTRATION='PREREGISTER_day97_microstructure.md'


def opening_features(day, prior_volumes, side):
    """At 09:50 only four completed bars may enter confirmation features."""
    if side not in ('LONG','SHORT') or len(prior_volumes)!=20:
        raise ValueError('side and exactly 20 prior opening volumes required')
    prior=np.asarray(prior_volumes,dtype=float)
    if not np.isfinite(prior).all() or (prior<0).any() or prior.mean()<=0:
        raise ValueError('invalid prior volume denominator')
    first=day.iloc[:3]; available=day.iloc[:4]
    volume=float(available['Volume'].sum())
    if volume<=0: raise ValueError('zero opening volume')
    approximate_vwap=float(((available['High']+available['Low']+available['Close'])/3
                           *available['Volume']).sum()/volume)
    price=float(available['Close'].iloc[-1])
    high=float(first['High'].max()); low=float(first['Low'].min())
    confirmed=(price>high and price>approximate_vwap) if side=='LONG' else (price<low and price<approximate_vwap)
    return {'opening_rvol':float(first['Volume'].sum()/prior.mean()),
            'opening_high':high,'opening_low':low,'vwap_proxy':approximate_vwap,
            'confirmation_close':price,'confirmed':bool(confirmed),
            'feature_available_at':'09:50 ET'}


def evaluate_leg(row, day, prior_volumes):
    f=opening_features(day,prior_volumes,row['side'])
    sign=1 if row['side']=='LONG' else -1
    entry=float(day['Open'].iloc[3]); delayed=float(day['Open'].iloc[4])
    close=float(day['Close'].iloc[-1]); lunch=float(day.loc[day.index.time==dt.time(11,30),'Open'].iloc[0])
    ret=lambda price,entry:sign*(price/entry-1)*10000
    baseline=ret(close,entry); late=ret(close,delayed); early=ret(lunch,entry)
    rvol=f['opening_rvol']>=2.5; confirm=f['confirmed']
    taken=[True,True,rvol,confirm,confirm and rvol,True,True]
    returns=[baseline,late,baseline,late,late,early,.5*early+.5*baseline]
    return {'session':row['date'],'ticker':row['ticker'],'side':row['side'],
            'recorded_shares':row.get('shares',''),'recorded_weight':row.get('weight',''),
            'features':f,'arms':{name:{'taken':bool(t),'gross_bps':float(r) if t else 0.0}
                                for name,t,r in zip(ARMS,taken,returns)}}


def load_inputs(cache,ledger,now):
    now=E.aware(now);cache=Path(cache);ledger=Path(ledger)
    manifest=json.loads((cache/'manifest.json').read_text())
    if (not manifest.get('complete') or manifest.get('source')!='yahoo_direct'
        or manifest.get('session')!=now.date().isoformat()
        or E.aware(manifest['prepared_at'])>now):
        raise ValueError('cache identity or preparation mismatch')
    raw_ledger=ledger.read_bytes()
    rows=[r for r in csv.DictReader(raw_ledger.decode().splitlines())
          if r.get('role')=='pair' and r['date']<now.date().isoformat()]
    if len({(r['date'],r['ticker'],r['side']) for r in rows})!=len(rows):
        raise ValueError('duplicate recorded selections')
    frames={};hashes={};dates=set()
    for ticker in sorted({r['ticker'] for r in rows}):
        path=cache/key(ticker)
        if not path.exists():continue
        raw=path.read_bytes();hashes[ticker]=hashlib.sha256(raw).hexdigest()
        saved=json.loads(raw);f=json.loads(saved['frame'])
        if saved['ticker']!=ticker or saved['session']!=manifest['session']:
            raise ValueError('cached ticker/session mismatch')
        frame=pd.DataFrame(f['data'],columns=f['columns'],index=pd.to_datetime(f['index'],utc=True).tz_convert(E.ET))
        if frame.empty or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError('invalid cached index')
        if any(i.date()>=now.date() for i in frame.index):
            raise ValueError('cache contains today or future')
        frames[ticker]=frame;dates.update(i.date() for i in frame.index)
    if not dates:raise ValueError('no cached history')
    schedule=E.schedule(min(dates),max(dates))
    date_list=[str(i.date()) for i in schedule.index]
    valid={};invalid=[]
    for ticker,frame in frames.items():
        valid[ticker]={}
        for date,s in schedule.iterrows():
            grid=pd.date_range(s['market_open'],s['market_close'],freq='5min',inclusive='left').tz_convert(E.ET)
            day=frame.reindex(grid)
            try:
                if len(grid)!=78 or day.isna().any().any():raise ValueError('missing bars or short session')
                for r in day.to_dict('records'):E.ohlcv({k.lower():v for k,v in r.items()})
                valid[ticker][str(date.date())]=day
            except (ValueError,E.DataGap) as exc:
                invalid.append({'ticker':ticker,'session':str(date.date()),'reason':str(exc)[:100]})
    matched=[];excluded=[]
    for date in sorted({r['date'] for r in rows}):
        board=[r for r in rows if r['date']==date]
        prepared=[];errors=[]
        for row in board:
            try:
                days=valid.get(row['ticker'],{})
                day=days[date];i=date_list.index(date)
                if i<20:raise ValueError('fewer than 20 prior exchange sessions')
                prior=[float(days[d]['Volume'].iloc[:3].sum()) for d in date_list[i-20:i]]
                reference=float(row['p945'])
                if not np.isfinite(reference) or abs(reference-float(day['Close'].iloc[2]))>.01000001:
                    raise ValueError('recorded opening reference differs from cached bars')
                opening_features(day,prior,row['side'])
                prepared.append((row,day,prior))
            except (KeyError,ValueError,IndexError) as exc:
                errors.append({'ticker':row['ticker'],'reason':type(exc).__name__+': '+str(exc)[:120]})
        if errors:excluded.append({'session':date,'original_legs':len(board),'gaps':errors})
        else:matched.extend(prepared)
    return matched,{'ledger_sha256':hashlib.sha256(raw_ledger).hexdigest(),
        'cache_sha256':hashes,'raw_cache_sessions':len(date_list),
        'original_published_legs':len(rows),'original_published_sessions':len({r['date'] for r in rows}),
        'excluded_boards':excluded,'invalid_cached_sessions':invalid,
        'survivorship':'Current universe; published selections are historical development evidence'}


def summarize(observations):
    if not observations:raise ValueError('no matched original boards')
    dates=sorted({r['session'] for r in observations})
    out={};daily={}
    for name in ARMS:
        gross=np.array([r['arms'][name]['gross_bps'] for r in observations])
        taken=np.array([r['arms'][name]['taken'] for r in observations])
        active=gross[taken];wins=active[active>0];losses=active[active<0]
        series=np.array([np.mean([r['arms'][name]['gross_bps'] for r in observations if r['session']==d]) for d in dates])
        participation=np.array([np.mean([r['arms'][name]['taken'] for r in observations if r['session']==d]) for d in dates])
        daily[name]=series
        out[name]={'admitted':int(taken.sum()),'capacity':len(taken),'participation':float(taken.mean()),
            'conditional_gross_hit_rate':float((active>0).mean()) if len(active) else None,
            'mean_win_bps':float(wins.mean()) if len(wins) else None,
            'mean_loss_bps':float(losses.mean()) if len(losses) else None,
            'conditional_ev_bps':float(active.mean()) if len(active) else None,
            'break_even_proportional_cost_bps':float(active.mean()) if len(active) else None,
            'capacity_daily_gross_bps':float(series.mean()),
            'daily_std_bps':float(series.std(ddof=1)) if len(dates)>1 else None,
            'worst_session_bps':float(series.min()),
            'proportional_cost_scenarios_bps':{str(c):float((series-c*participation).mean()) for c in (5,10,20)},
            'paired_delta_bps':float((series-daily['baseline_proxy']).mean()),
            'se_bps':None,'ci95_bps':None,'mde80_gross_bps':None,'mde80_actual_net_bps':None}
    if len(dates)>=20:
        rng=np.random.default_rng(9702)
        indices=[]
        for _ in range(2000):
            starts=rng.integers(0,len(dates)-5+1,size=int(np.ceil(len(dates)/5)))
            indices.append(np.concatenate([np.arange(s,s+5) for s in starts])[:len(dates)])
        for name in ARMS[1:]:
            delta=daily[name]-daily['baseline_proxy'];draws=delta[np.asarray(indices)].mean(axis=1)
            se=float(draws.std(ddof=1));point=float(delta.mean())
            if np.isfinite(se) and se>0:
                out[name].update(se_bps=se,ci95_bps=[point-1.96*se,point+1.96*se],
                    mde80_gross_bps=(3.5+.8416212336)*se,
                    additive_5bps_sensitivity_detected=bool(5/se>3.5))
    return {'status':'RETROSPECTIVE DEVELOPMENT ONLY — no adoption','sessions':len(dates),
            'matched_legs':len(observations),'first_session':dates[0],'last_session':dates[-1],
            'arms':out,'adopted':False,
            'limits':['Five-minute trade-price/VWAP proxies; not 09:46/15:59 fills',
                      'No observed BBO/fees/slippage/borrow or same-window index; net alpha unscored',
                      'Equal unit capacity diagnostic, not actual recorded portfolio allocation',
                      'Cost scenarios assume proportional friction; extra fixed ticket fees omitted',
                      'Historical outcomes already observed; no untouched confirmation or four-quarter/two-market qualification']}


def run(cache,ledger,output,now=None):
    now=now or dt.datetime.now(E.ET)
    items,provenance=load_inputs(cache,ledger,now)
    observations=[evaluate_leg(*item) for item in items]
    result=summarize(observations)
    result.update(registration=REGISTRATION,generated_at=now.isoformat(),provenance=provenance,observations=observations)
    write_atomic(output,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-dir',required=True);p.add_argument('--ledger',default='ledger.csv')
    p.add_argument('--output',required=True);a=p.parse_args()
    try:
        r=run(a.cache_dir,a.ledger,a.output)
        print(json.dumps({k:v for k,v in r.items() if k not in ('observations','provenance')},indent=2,allow_nan=False))
    except (ValueError,KeyError,IndexError,OSError,E.DataGap) as exc:
        r={'status':'BLOCKED','error':type(exc).__name__,'detail':str(exc)[:180],
           'registration':REGISTRATION,'adopted':False}
        write_atomic(a.output,r);print(json.dumps(r));raise SystemExit(2)
