#!/usr/bin/env python3
"""Day-90 preregistered execution study. Historical rows are exploratory only.

No synthetic outcomes or reconstructed spreads. Emit every blocked arm and
both threshold MDE and 80%-power MDE. Session clusters, including no-trade days,
are the independent units. This module never changes production settings.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import numpy as np
import ledger
from report_store import encode

SEED=90
DRAWS=10_000
Z=3.5
POWER_Z=.8416212336
ARMS=('H1_spread_density','H2_cost_sizing','H3a_exit_1530','H3b_exit_1545')


def estimate(values, plant_bps=5):
    """Session bootstrap of a mean, values in bps; plant tests edge/SE only."""
    x=np.asarray(values,dtype=float)
    if not np.isfinite(x).all():
        raise ValueError('nonfinite session observation')
    out={'sessions':len(x),'mean_bps':float(x.mean()) if len(x) else None,
         'se_bps':None,'ci95_bps':None,'mde_threshold_bps':None,'mde80_bps':None,
         'z':None,'positive_control_z':None,'status':'UNDERPOWERED'}
    if len(x)<2:
        return out
    rng=np.random.default_rng(SEED)
    # Chunks bound memory for multi-year daily panels.
    means=np.concatenate([x[rng.integers(0,len(x),(min(1000,DRAWS-i),len(x)))].mean(axis=1)
                          for i in range(0,DRAWS,1000)])
    se=float(means.std(ddof=1))
    out.update(se_bps=se,ci95_bps=[float(v) for v in np.quantile(means,[.025,.975])],
               mde_threshold_bps=Z*se,mde80_bps=(Z+POWER_Z)*se)
    if se==0:
        # A deterministic synthetic dataset is a harness fixture, not proof.
        out['status']='DEGENERATE — no observed session dispersion'
        return out
    out.update(z=out['mean_bps']/se,positive_control_z=plant_bps/se,
               status='POWERED' if plant_bps/se >= Z+POWER_Z else 'UNDERPOWERED')
    return out


def paired_session_rows(baseline, candidate):
    """Identical sessions required; absence cannot masquerade as abstention."""
    if set(baseline)!=set(candidate):
        raise ValueError('candidate is missing baseline opportunity days')
    return [candidate[d]-baseline[d] for d in sorted(baseline)]


def placebo_max(differences):
    """Shared sign per session across ALL arms preserves their dependence."""
    x=np.asarray(differences,dtype=float)
    if x.ndim!=2 or x.shape[0]<2 or not np.isfinite(x).all():
        raise ValueError('need finite session x arm differences')
    rng=np.random.default_rng(SEED)
    maxima=[]
    for _ in range(DRAWS//1000):
        signs=rng.choice([-1.,1.],size=(1000,len(x)))
        maxima.extend((signs@x/len(x)).max(axis=1))
    return float(np.quantile(maxima,.95))


def variance_gate(baseline, candidate):
    """Variance-only evidence, never relabelled as accuracy or alpha.

    Compare paired net returns on original capacity; noninferiority uses the
    lower 95% mean-difference bound, not a favourable point estimate.
    """
    b,c=np.asarray(baseline,dtype=float),np.asarray(candidate,dtype=float)
    if len(b)!=len(c) or len(b)<8 or not np.isfinite([b,c]).all():
        return {'passes':False,'status':'UNDERPOWERED'}
    ratios=[]
    for bb,cc in zip(np.array_split(b,4),np.array_split(c,4)):
        sd=float(bb.std(ddof=1))
        if sd<=0:return {'passes':False,'status':'DEGENERATE'}
        ratios.append(float(cc.std(ddof=1)/sd))
    delta=estimate(c-b)
    rng=np.random.default_rng(SEED);samples=[]
    for offset in range(0,DRAWS,1000):
        idx=rng.integers(0,len(b),(min(1000,DRAWS-offset),len(b)))
        den=b[idx].std(axis=1,ddof=1)
        if (den<=0).any():return {'passes':False,'status':'DEGENERATE'}
        samples.extend(c[idx].std(axis=1,ddof=1)/den)
    se=float(np.std(samples,ddof=1))
    control=.10/se if se>0 else None
    powered=control is not None and control>=Z+POWER_Z
    passes=powered and max(ratios)<=.90 and delta['ci95_bps'][0]>=-1
    return {'passes':passes,'status':'POWERED' if powered else 'UNDERPOWERED',
            'block_volatility_ratios':ratios,'mean_net_difference':delta,
            'volatility_reduction_mde80':(Z+POWER_Z)*se,
            'positive_control_z':control,'claim':'Variance only; no accuracy improvement claim'}


def historical_diagnostics(rows, as_of):
    """Stored-spread coverage and complete-session net proxy on original weight."""
    pair=[r for r in rows if r.get('role')=='pair' and r['date']<as_of]
    a=ledger.accuracy(pair)
    by={}
    for r in pair:
        by.setdefault(r['date'],[]).append(r)
    daily=[];incomplete=[]
    for day,legs in sorted(by.items()):
        values=[]
        for row in legs:
            try:
                cap=ledger.capture(row)
                weight=float(row['weight']);spread=float(row['spread_bps'])
                if cap is None or not np.isfinite([cap,weight,spread]).all() or weight<0 or spread<0:
                    raise ValueError('invalid cost/weight')
                values.append(weight*(cap*100-spread))
            except (ValueError,KeyError,TypeError):
                values=[];break
        if values and len(values)==len(legs): daily.append(sum(values))
        else: incomplete.append(day)
    return {'accuracy':a,'complete_session_net_proxy':estimate(daily),
            'complete_sessions':len(daily),'incomplete_sessions':len(incomplete),
            'label':'EXPLORATORY — stored entry spread assumes same exit spread; fees/slippage absent; not exact execution',
            'adoptable':False}


def gate_native(panel, metadata, as_of=None):
    """Validate preregistered panel, then compare all arms without tuning.

    panel rows: session, market, ticker, weight, side, baseline_net_bps,
    h1_net_bps, h2_net_bps, exit1530_net_bps, exit1545_net_bps.
    For each return key also require key+'_index_bps' (same exit window)
    and key+'_scale' (active exposure). Require entry_spread_bps and
    trailing_vol_pct to verify H1/H2. H2 uses proportional notional costs.
    Optional key+'_net_hit' enables the
    paired net-hit MDE, where abstention is zero on the original opportunity.
    A zero is a measured abstention, not a missing observation.
    """
    if not metadata.get('exact_bbo') or not metadata.get('point_in_time_universe') or not metadata.get('all_costs'):
        return {'status':'BLOCKED','reason':'exact BBO, point-in-time membership and all costs required'}
    as_of=as_of or dt.date.today().isoformat()
    if any(r['session']>=as_of for r in panel):
        return {'status':'BLOCKED','reason':'future or incomplete-session observations in panel'}
    keys=('baseline_net_bps','h1_net_bps','h2_net_bps','exit1530_net_bps','exit1545_net_bps')
    result={}
    for market in ('TSX','US'):
        source=[r for r in panel if r['market']==market]
        if any(r['session']<'2026-09-09' for r in source):
            return {'status':'BLOCKED','reason':'discovery observations in prospective holdout'}
        days=sorted({r['session'] for r in source})
        if len(days)<252:
            result[market]={'status':'UNDERPOWERED','sessions':len(days),'required':252}
            continue
        import pandas_market_calendars as mcal
        schedule=mcal.get_calendar('TSX' if market=='TSX' else 'NYSE').schedule(start_date=days[0],end_date=days[-1])
        closes=schedule['market_close'].dt.tz_convert('America/New_York')
        full_sessions={i.date().isoformat() for i,c in closes.items() if c.hour>=16}
        if not set(days)<=full_sessions:
            raise ValueError('panel includes non-session or early-close dates')
        by={d:[r for r in source if r['session']==d] for d in days}
        matrix=[];name_diff={};daily_returns=[];hit_differences=[]
        for d,rows in by.items():
            if len({r['ticker'] for r in rows})!=len(rows):
                raise ValueError('duplicate session/security')
            if abs(sum(float(r['weight']) for r in rows))>1.000001:
                raise ValueError('weights exceed original capacity')
            for r in rows:
                spread,vol=float(r['entry_spread_bps']),float(r['trailing_vol_pct'])
                if not np.isfinite([spread,vol]).all() or spread<0 or vol<=0:
                    raise ValueError('invalid spread/volatility overlay inputs')
                density=spread/(100*vol)
                scales=(1.,float(density<=.10),max(0.,1-density),1.,1.)
                for key,scale in zip(keys,scales):
                    if not np.isclose(float(r[key+'_scale']),scale,rtol=0,atol=1e-10):
                        raise ValueError('panel exposure differs from preregistered overlay')
                for key,scale in zip(keys[1:3],scales[1:3]):
                    if not np.isclose(r[key],scale*r[keys[0]],rtol=0,atol=1e-8):
                        raise ValueError('panel H1/H2 return differs from fixed-capacity overlay')
                    if r[key+'_index_bps']!=r[keys[0]+'_index_bps']:
                        raise ValueError('cost overlay benchmark window differs from baseline')
            totals=[]
            for key in keys:
                total=0
                for r in rows:
                    if r.get('side') not in {'LONG','SHORT'}:
                        raise ValueError('invalid native side')
                    vals=[float(r[key]),float(r[key+'_index_bps']),float(r['weight'])]
                    if not np.isfinite(vals).all() or vals[2]<0:
                        raise ValueError('invalid native observation')
                    # Each arm records its own active exposure: abstention
                    # removes its tide too, not just its total P&L.
                    scale=float(r[key+'_scale'])
                    if not 0<=scale<=1: raise ValueError('invalid overlay exposure')
                    sign=1 if r['side']=='LONG' else -1
                    total+=r['weight']*(r[key]-scale*sign*r[key+'_index_bps'])
                totals.append(total)
            matrix.append(np.array(totals[1:])-totals[0])
            daily_returns.append([sum(r['weight']*r[key] for r in rows) for key in keys])
            if all(r.get(k+'_net_hit') in (0,1,False,True) for r in rows for k in keys):
                hit_differences.append([100*np.mean([r[k+'_net_hit']-r[keys[0]+'_net_hit'] for r in rows]) for k in keys[1:]])
            for r in rows:
                sign=1 if r['side']=='LONG' else -1
                base=r['baseline_net_bps']-sign*r['baseline_net_bps_index_bps']
                diffs=[r['weight']*(r[k]-float(r[k+'_scale'])*sign*r[k+'_index_bps']-base) for k in keys[1:]]
                name_diff.setdefault(r['ticker'],np.zeros(4))[:]+=diffs
        matrix=np.array(matrix);returns=np.array(daily_returns)
        bound=placebo_max(matrix);arms={}
        def es(x):
            return np.mean(np.sort(x)[:max(1,int(np.ceil(.05*len(x))))])
        for i,arm in enumerate(ARMS):
            est=estimate(matrix[:,i]);blocks=[float(v[:,i].mean()) for v in np.array_split(matrix,4)]
            positive=sum(max(0,v[i]) for v in name_diff.values())
            concentration=max((max(0,v[i])/positive for v in name_diff.values()),default=0) if positive else 1
            tail_delta=float(es(returns[:,i+1])-es(returns[:,0]))
            passes=(est['status']=='POWERED' and est['z']>=Z and est['mean_bps']>=5 and
                    est['ci95_bps'][0]>0 and all(v>0 for v in blocks) and
                    est['mean_bps']>bound and concentration<=.20 and tail_delta>=-1)
            variance=variance_gate(returns[:,0],returns[:,i+1])
            variance['passes']=variance['passes'] and tail_delta>=-1
            hit=estimate(np.asarray(hit_differences)[:,i],plant_bps=5) if len(hit_differences)==len(days) else None
            arms[arm]={**est,'blocks_bps':blocks,'placebo_max95_bps':bound,
                       'max_name_share':concentration,'expected_shortfall_delta_bps':tail_delta,
                       'net_hit_mde80_pp':hit['mde80_bps'] if hit else None,
                       'net_hit_mde_note':'Paired session hit differences on original opportunities; missing data leaves MDE unavailable',
                       'variance_only':variance,'passes':passes}
        result[market]={'status':'EVALUATED','sessions':len(days),'arms':arms}
    adopted=[a for a in ARMS if all(result[m].get('arms',{}).get(a,{}).get('passes') for m in ('TSX','US'))]
    variance=[a for a in ARMS if all(result[m].get('arms',{}).get(a,{}).get('variance_only',{}).get('passes') for m in ('TSX','US'))]
    return {'status':'CANDIDATE_REQUIRES_REVIEW' if adopted or variance else 'NO_ADOPTION',
            'markets':result,'adopted':adopted,'variance_only_candidates':variance,
            'production_settings_changed':False}


def run(path='ledger.csv',as_of=None):
    as_of=as_of or dt.date.today().isoformat()
    rows=ledger.load(path)
    diag=historical_diagnostics(rows,as_of)
    return {'registration':'PREREGISTER_day90.md','as_of':as_of,
            'input_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'overall':'NO STRATEGY ADOPTED','historical_diagnostics':diag,
            'arms':{arm:{'status':'BLOCKED','mde80_bps':None,'reason':
                'No exact 09:46 BBO / trailing-vol / matched index / alternate-exit panel in repository; historical results cannot certify this arm.'} for arm in ARMS},
            'harness_controls':'Synthetic controls are tested separately; they are not historical performance evidence.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',default='ledger.csv');p.add_argument('--as-of',default=dt.date.today().isoformat())
    p.add_argument('--output',default='data/day90_results.json')
    p.add_argument('--panel',help='JSON object with rows and metadata for a prospective native-market panel')
    a=p.parse_args(argv)
    if a.panel:
        panel=json.loads(Path(a.panel).read_text())
        result=gate_native(panel['rows'],panel['metadata'],as_of=a.as_of)
        result['as_of']=a.as_of
        result['input_sha256']=hashlib.sha256(Path(a.panel).read_bytes()).hexdigest()
    else:
        result=run(a.ledger,a.as_of)
    Path(a.output).write_text(encode(result)+'\n')
    print(json.dumps(result,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
