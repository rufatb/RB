#!/usr/bin/env python3
"""Day91's fixed 48-arm ETF feasibility study; never imported by daily reporting.

All signals use prior-session observations. Costs are assumptions, not fills.
Development selection is frozen before confirmation files may be accessed.
See PREREGISTER_day91.md for the exact family, restrictions and interpretation.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
from scipy.stats import norm

TICKERS = tuple(sorted(('XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY')))
ALL_TICKERS = TICKERS + ('SPY',)
LOOKBACKS = (1, 5, 20, 60)
HORIZONS = ('intraday', 'overnight', 'weekly')
COSTS = (5, 10, 25)
SEED = 91
DRAWS = 2000
BORROW_APR = .03
REGISTRATION = '48651ec161c691846783025e47c6a4a780216437'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arm_specs():
    return [dict(id=f'{direction}_{lookback}_{sizing}_{horizon}',
                 direction=direction, lookback=lookback, sizing=sizing, horizon=horizon)
            for lookback, direction, sizing, horizon in itertools.product(
                LOOKBACKS, ('momentum','reversal'), ('equal','inverse_vol'), HORIZONS)]


def load_panel(root, phase):
    """Validate requested 2025 feasibility panel; missing sessions stay missing."""
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['mode'] != 'SHORT_HISTORY_FEASIBILITY':
        raise ValueError('This implementation supports the registered short-history fallback only')
    phases = ['development'] + (['confirmation'] if phase == 'confirmation' else [])
    if phase == 'development' and list((root / 'confirmation').glob('*.csv')):
        raise ValueError('Confirmation files already exist: cannot claim unseen development selection')
    end = '2026-09-04' if phase == 'confirmation' else '2025-12-31'
    schedule = mcal.get_calendar('NYSE').schedule(start_date='2025-01-01', end_date=end)
    schedule.index = pd.DatetimeIndex(schedule.index).tz_localize(None)
    frames, provenance, gaps = {}, {}, {}
    for ticker in ALL_TICKERS:
        pieces = []
        for part in phases:
            path = root / part / f'{ticker}.csv'
            if not path.exists():
                raise ValueError(f'Missing required price input: {part}/{ticker}.csv')
            provenance[str(path.relative_to(root))] = file_hash(path)
            df = pd.read_csv(path)
            if not {'t','o','h','l','c','v'} <= set(df.columns):
                raise ValueError(f'Invalid OHLCV schema: {ticker}')
            df['date'] = pd.to_datetime(df.t, unit='ms', utc=True).dt.tz_convert(
                'America/New_York').dt.tz_localize(None).dt.normalize()
            if df.date.duplicated().any():
                raise ValueError(f'Duplicate session: {ticker}')
            # Source timestamps must denote the session date; out-of-window raw
            # responses are retained in provenance, excluded from this experiment.
            df = df.set_index('date')[['o','h','l','c','v']].sort_index()
            lower, upper = ('2025-01-01','2025-12-31') if part == 'development' else ('2026-01-01',end)
            df = df.loc[lower:upper]
            good = (np.isfinite(df).all(axis=1) & (df > 0).all(axis=1)
                    & (df.h >= df[['o','c','l']].max(axis=1))
                    & (df.l <= df[['o','c','h']].min(axis=1)))
            if not good.all():
                raise ValueError(f'Invalid OHLCV rows: {ticker}: {int((~good).sum())}')
            if not df.index.isin(schedule.index).all():
                raise ValueError(f'Non-session bar: {ticker}')
            pieces.append(df)
        df = pd.concat(pieces).sort_index()
        if df.index.duplicated().any():
            raise ValueError(f'Overlapping phase prices: {ticker}')
        gaps[ticker] = int(len(schedule) - len(df))
        frames[ticker] = df.reindex(schedule.index)
    dividend_pieces = []
    dividends_available = True
    for part in phases:
        path = root / part / 'dividends.csv'
        request = manifest.get('distribution_requests',{}).get(part,{})
        lower, upper = ('2025-01-01','2025-12-31') if part == 'development' else ('2026-01-01',end)
        complete = (request.get('pagination_exhausted') is True
                    and set(request.get('tickers',[])) == set(ALL_TICKERS)
                    and request.get('adjustment_basis') == 'current_share_split_adjusted'
                    and request.get('start','9999') <= lower and request.get('end','0000') >= upper)
        if not path.exists() or not complete:
            dividends_available = False
            continue
        if request.get('sha256') != file_hash(path):
            raise ValueError('Distribution file differs from acquisition manifest')
        provenance[str(path.relative_to(root))] = file_hash(path)
        d = pd.read_csv(path)
        fields = {'id','ticker','currency','ex_dividend_date','split_adjusted_cash_amount'}
        if not fields <= set(d.columns):
            raise ValueError('Missing split-adjusted distribution fields')
        if d.id.duplicated().any() or not d.ticker.isin(ALL_TICKERS).all():
            raise ValueError('Duplicate or unexpected dividend identity')
        cash = pd.to_numeric(d.split_adjusted_cash_amount, errors='coerce')
        if not (np.isfinite(cash) & (cash >= 0) & d.currency.eq('USD')).all():
            raise ValueError('Invalid distribution currency or amount')
        d['date'] = pd.to_datetime(d.ex_dividend_date)
        dividend_pieces.append(d[d.date.between(lower, upper)])
    div = pd.DataFrame(0., index=schedule.index, columns=ALL_TICKERS)
    if dividends_available:
        d = pd.concat(dividend_pieces, ignore_index=True)
        if d.id.duplicated().any() or not d.date.isin(schedule.index).all():
            raise ValueError('Duplicate or non-session distribution')
        for (ticker, date), amount in d.groupby(['ticker','date']).split_adjusted_cash_amount.sum().items():
            div.loc[date,ticker] = amount
    close = pd.DataFrame({t: frames[t].c for t in ALL_TICKERS})
    daily = (close + div) / close.shift(1) - 1
    # Expanding product would bridge a missing observation. Rolling products of
    # daily returns instead require every observation in the specified window.
    signals = {n: (1 + daily).rolling(n, min_periods=n).apply(np.prod, raw=True).shift(1) - 1
               for n in LOOKBACKS}
    vol = daily.rolling(20, min_periods=20).std(ddof=1).shift(1)
    joint = pd.DataFrame({t: frames[t].notna().all(axis=1) for t in ALL_TICKERS}).all(axis=1)
    if int(joint.loc['2025'].sum()) < 120:
        raise ValueError('Fewer than 120 complete development sessions')
    return dict(frames=frames, dividends=div, dividends_available=dividends_available,
                schedule=schedule, signals=signals, vol=vol, joint=joint,
                provenance=provenance, gaps=gaps, mode=manifest['mode'])


def choose_legs(signal, vol, direction, sizing):
    if not np.isfinite(signal.loc[list(TICKERS)]).all():
        return None
    if sizing == 'inverse_vol' and not (np.isfinite(vol.loc[list(TICKERS)]) & (vol.loc[list(TICKERS)] > 0)).all():
        return None
    rank = sorted(TICKERS, key=lambda t: (float(signal[t]), t))
    longs, shorts = (rank[-2:],rank[:2]) if direction == 'momentum' else (rank[:2],rank[-2:])
    result = []
    for names, side in ((longs,1),(shorts,-1)):
        raw = np.ones(2) if sizing == 'equal' else np.array([1 / vol[t] for t in names])
        weights = .5 * raw / raw.sum()
        result.extend((t, side, float(w)) for t,w in zip(names,weights))
    return result


def window_return(panel, ticker, i, j, horizon):
    frame, dates = panel['frames'][ticker], panel['schedule'].index
    entry = float(frame.iloc[i]['c' if horizon == 'overnight' else 'o'])
    exit_price = float(frame.iloc[j]['o' if horizon == 'overnight' else 'c'])
    # An opening purchase on the ex-date does not receive that distribution.
    # Holding through the next open does; short returns include the liability.
    dividend = float(panel['dividends'].loc[(dates > dates[i]) & (dates <= dates[j]),ticker].sum())
    return (exit_price + dividend) / entry - 1


def simulate(panel, spec, block_indices):
    rows, missing = [], 0
    schedule = panel['schedule']
    h = 5 if spec['horizon'] == 'weekly' else 1
    for block, indices in enumerate(block_indices):
        if not len(indices):
            continue
        for i in indices[::h]:
            j = i + (4 if spec['horizon'] == 'weekly' else 1 if spec['horizon'] == 'overnight' else 0)
            # No outcome crosses a development/confirmation/block boundary.
            if j > indices[-1] or not panel['joint'].iloc[i:j+1].all():
                missing += 1
                continue
            legs = choose_legs(panel['signals'][spec['lookback']].iloc[i],panel['vol'].iloc[i],
                               spec['direction'],spec['sizing'])
            if legs is None:
                missing += 1
                continue
            entry_t = schedule.iloc[i]['market_close' if spec['horizon'] == 'overnight' else 'market_open']
            exit_t = schedule.iloc[j]['market_open' if spec['horizon'] == 'overnight' else 'market_close']
            days = (exit_t-entry_t).total_seconds()/86400
            returns = np.array([s * window_return(panel,t,i,j,spec['horizon']) for t,s,w in legs])
            weights = np.array([w for t,s,w in legs])
            borrow = np.array([BORROW_APR * days/365 if s < 0 else 0 for t,s,w in legs])
            benchmark = window_return(panel,'SPY',i,j,spec['horizon'])
            long_raw = float(np.dot(weights[:2],returns[:2])/.5)
            short_raw = float(np.dot(weights[2:],-returns[2:])/.5)
            row = dict(date=schedule.index[i].date().isoformat(),exit_date=schedule.index[j].date().isoformat(),
                       block=block,occupied_sessions=h,gross=float(weights @ returns),
                       benchmark=benchmark,long_minus_short=long_raw-short_raw,
                       long_relative=long_raw-benchmark,short_underlying_relative=short_raw-benchmark,
                       legs=[dict(ticker=t,side='LONG' if s>0 else 'SHORT',weight=w) for t,s,w in legs])
            for cost in COSTS:
                net = returns-cost/10000-borrow
                decisive = np.abs(net) >= .001
                row[f'net_{cost}'] = float(weights @ net)
                row[f'hit_{cost}'] = float((net>0).mean())
                row[f'decisive_hits_{cost}'] = int(((net>0)&decisive).sum())
                row[f'decisive_n_{cost}'] = int(decisive.sum())
            rows.append(row)
    return rows, missing


def bootstrap_summary(values, *, scale=10000., seed=SEED):
    """Circular 20-slot block bootstrap; no row-wise pseudo independence."""
    x = np.asarray(values,dtype=float)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite observations in inference')
    n = len(x)
    if not n:
        return dict(n=0,mean=None,se=None,ci95=None,mde80=None,z=None,p=None,status='NO_DATA')
    mean = float(x.mean())
    if n < 2:
        return dict(n=n,mean=mean*scale,se=None,ci95=None,mde80=None,z=None,p=None,status='UNDERPOWERED')
    length = 20
    rng = np.random.default_rng(seed)
    starts = rng.integers(0,n,size=(DRAWS,math.ceil(n/length)))
    idx = ((starts[:,:,None]+np.arange(length)) % n).reshape(DRAWS,-1)[:,:n]
    draws = x[idx].mean(axis=1)
    se = float(draws.std(ddof=1))
    # Degenerate resampling is not infinitely precise market evidence.
    if se <= 1e-15:
        return dict(n=n,mean=mean*scale,se=None,ci95=None,mde80=None,z=None,p=None,
                    positive_control_5bps_z=None,target_5bps_detectable=False,
                    block_length=length,status='DEGENERATE_INFERENCE')
    z = mean/se if se>1e-15 else None
    return dict(n=n,mean=mean*scale,se=se*scale,ci95=(np.quantile(draws,[.025,.975])*scale).tolist(),
                mde80=(3.5+norm.ppf(.8))*se*scale,z=z,p=float(2*norm.sf(abs(z))) if z is not None else None,
                positive_control_5bps_z=.0005/se if se>1e-15 else None,
                target_5bps_detectable=bool(se>1e-15 and .0005/se>=3.5+norm.ppf(.8)),
                block_length=length,status='UNDERPOWERED' if n<40 else 'EXPLORATORY')


def summarize(spec, rows, missing):
    h = 5 if spec['horizon']=='weekly' else 1
    if not rows:
        return dict(**spec,slots=0,missing_windows=missing,primary=bootstrap_summary([]),adoptable=False)
    out = dict(**spec,slots=len(rows),legs=4*len(rows),missing_windows=missing,
               first_entry=rows[0]['date'],last_exit=rows[-1]['exit_date'],adoptable=False,
               gross_bps_per_occupied_session=float(np.mean([r['gross']/h for r in rows])*10000),
               benchmark_bps_per_occupied_session=float(np.mean([r['benchmark']/h for r in rows])*10000),
               long_minus_short_bps_per_occupied_session=float(np.mean([r['long_minus_short']/h for r in rows])*10000),
               long_relative_bps_per_occupied_session=float(np.mean([r['long_relative']/h for r in rows])*10000),
               short_underlying_relative_bps_per_occupied_session=float(np.mean([r['short_underlying_relative']/h for r in rows])*10000),
               gross_turnover_per_round_trip=2.0,cost_scenarios={})
    for cost in COSTS:
        net=np.array([r[f'net_{cost}'] for r in rows])
        curve=np.cumprod(1+net)
        peaks=np.maximum.accumulate(np.r_[1.,curve])[1:]
        dec_n=sum(r[f'decisive_n_{cost}'] for r in rows)
        out['cost_scenarios'][str(cost)] = dict(mean_bps_per_occupied_session=float(net.mean()/h*10000),
            net_leg_hit_rate=float(np.mean([r[f'hit_{cost}'] for r in rows])),
            decisive_net_hit_rate=sum(r[f'decisive_hits_{cost}'] for r in rows)/dec_n if dec_n else None,
            decisive_legs=dec_n,endpoint_drawdown_pct=float(np.min(curve/peaks-1)*100),
            compounded_endpoint_return_pct=float((curve[-1]-1)*100),
            expected_shortfall5_bps_per_trade=float(np.sort(net)[:max(1,math.ceil(.05*len(net)))].mean()*10000))
    out['primary']=bootstrap_summary([r['net_10']/h for r in rows])
    out['net_hit_inference_pp']=bootstrap_summary([r['hit_10'] for r in rows],scale=100.)
    # Probability-of-winning inference is centered on its observed mean; do not
    # reuse the return positive-control fields, whose units differ.
    for key in ('positive_control_5bps_z','target_5bps_detectable','z','p'):
        out['net_hit_inference_pp'].pop(key,None)
    out['blocks_bps']=[float(np.mean([r['net_10']/h for r in rows if r['block']==b])*10000)
                       if any(r['block']==b for r in rows) else None for b in sorted({r['block'] for r in rows})]
    # Block-sign placebo preserves observations within each 20-slot block.
    x=np.array([r['net_10']/h for r in rows]); x=x-x.mean()
    rng=np.random.default_rng(SEED)
    groups=np.arange(len(x))//20
    sums=np.bincount(groups,weights=x)
    placebo=rng.choice([-1,1],size=(DRAWS,len(sums)))@sums/len(x)
    out['placebo_centered_mean95_abs_bps']=float(np.quantile(abs(placebo),.95)*10000)
    return out


def holm_adjust(arms):
    ranked=sorted([(a['primary']['p'],i) for i,a in enumerate(arms) if a['primary']['p'] is not None])
    running=0.
    for rank,(p,i) in enumerate(ranked):
        running=max(running,min(1.,(len(arms)-rank)*p))
        arms[i]['holm_p']=running
    for a in arms:
        a.setdefault('holm_p',None)


def evaluate(panel, phase):
    dates=panel['schedule'].index
    eligible=np.arange(len(dates))
    # A common 60-return lookback + one lag ensures all arms share the same
    # first potential entry. Every individual held window is still validated.
    eligible=eligible[(eligible>=61) & ((dates.year<=2025) if phase=='development' else (dates.year==2026))]
    blocks=np.array_split(eligible,4) if phase=='development' else [eligible]
    arms, trades = [], {}
    for spec in arm_specs():
        rows, missing=simulate(panel,spec,blocks)
        summary=summarize(spec,rows,missing)
        if any(panel.get('gaps',{}).values()):
            # Removing missing dates and bootstrapping the survivors would
            # mislabel nonconsecutive observations as consecutive blocks.
            for metric in ('primary','net_hit_inference_pp'):
                if metric in summary:
                    summary[metric].update(status='BLOCKED_GAPS',se=None,ci95=None,mde80=None)
            summary['primary'].update(z=None,p=None,target_5bps_detectable=False,
                                      positive_control_5bps_z=None)
        arms.append(summary)
        trades[spec['id']]=rows
    holm_adjust(arms)
    return arms,trades


def run(root, phase, output, frozen=None):
    if phase=='confirmation':
        if not frozen:
            raise ValueError('Confirmation requires frozen development result')
        prior=json.loads(Path(frozen).read_text())
        if prior['phase']!='development' or prior['registration_commit']!=REGISTRATION:
            raise ValueError('Invalid development registration')
        winner=prior.get('frozen_development_winner')
        if winner not in {s['id'] for s in arm_specs()}:
            raise ValueError('Development has no valid frozen winner')
    panel=load_panel(root,phase)
    if phase=='confirmation':
        for name,sha in prior['input_sha256'].items():
            if panel['provenance'].get(name)!=sha:
                raise ValueError('Development inputs changed after selection')
    arms,trades=evaluate(panel,phase)
    if phase=='development':
        evaluable=[a for a in arms if a['primary']['mean'] is not None]
        winner=max(evaluable,key=lambda a:a['primary']['mean'])['id'] if evaluable else None
    result=dict(registration_commit=REGISTRATION,phase=phase,mode=panel['mode'],
                source='Massive split-adjusted daily bars and cash dividends',
                label='SIMULATED COSTS; DAILY-BAR PROXY; NO PRODUCTION ADOPTION',
                dividend_accounting='COMPLETE_REQUEST' if panel['dividends_available'] else 'PRICE_ONLY_PROXY',
                missing_sessions=panel['gaps'],input_sha256=panel['provenance'],
                manifest_sha256=file_hash(Path(root)/'manifest.json'),
                evaluator_sha256=file_hash(__file__),
                frozen_development_winner=winner,arms=arms,adoptable=False)
    if phase=='confirmation':
        result['frozen_development_sha256']=file_hash(frozen)
        w=next(a for a in arms if a['id']==winner)
        dw=next(a for a in prior['arms'] if a['id']==winner)
        research_gate=bool(w['primary']['status']=='EXPLORATORY' and w['primary']['mean'] is not None
            and w['primary']['mean']>0 and w['primary']['z'] is not None and w['primary']['z']>=3.5
            and w['holm_p'] is not None and w['holm_p']<.05
            and len(dw.get('blocks_bps',[]))==4 and all(v is not None and v>0 for v in dw['blocks_bps'])
            and w['cost_scenarios']['25']['mean_bps_per_occupied_session']>0
            and panel['dividends_available'])
        result['frozen_winner_research_gate_passed']=research_gate
        result['conclusion']='FURTHER_RESEARCH_ONLY' if research_gate else 'NO_CONFIRMED_CANDIDATE'
    else:
        result['conclusion']='DEVELOPMENT_SELECTION_ONLY' if winner else 'BLOCKED_NO_EVALUABLE_ARMS'
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False); f.write('\n')
    # Per-trade inputs/allocations stay beside raw research data, not public code.
    trade_path=Path(root)/f'{phase}_trades.json'
    trade_path.write_text(json.dumps(trades,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('phase','mode','frozen_development_winner','conclusion')}))
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir',required=True)
    ap.add_argument('--phase',choices=('development','confirmation'),required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--frozen-development')
    args=ap.parse_args()
    run(args.data_dir,args.phase,args.output,args.frozen_development)
