"""Execution measurements and preregistered shadow overlays; never a predictor.

Signal reference (09:45 bar close), quote as-of, actual fill and exit are distinct.
MDE/paired research lives in validate_execution.py, never in a renderer.
"""
from __future__ import annotations
import datetime as dt
import math
from zoneinfo import ZoneInfo
from quotes import CORROBORATED, number, stamp

ET = ZoneInfo('America/New_York')


def clock_status(now, calendar='TSX'):
    """Exchange calendar including holidays/early closes; fail closed if unknown."""
    import pandas_market_calendars as mcal
    now = stamp(now).astimezone(ET)
    schedule = mcal.get_calendar(calendar).schedule(start_date=now.date(), end_date=now.date())
    out = {'session': now.date().isoformat(), 'entry_time': '09:46', 'exit_time': '15:59',
           'status': 'CLOSED', 'eligible': False, 'close_at': None}
    if schedule.empty:
        return out
    close = schedule.iloc[0]['market_close'].to_pydatetime().astimezone(ET)
    out['close_at'] = close.isoformat()
    if close.time() < dt.time(16):
        out['status'] = 'SHORT_SESSION — 15:59 contract unavailable'
    elif now.time() < dt.time(9,46):
        out['status'] = 'PREPARING — signal not final before 09:46'
    elif now.time() >= dt.time(9,47):
        out['status'] = 'LATE — informational only; entry window missed'
    else:
        out.update(status='09:46 publication window', eligible=True)
    return out


def evaluate_legs(res, cfg, quotes, clock, shadow):
    """Keep every baseline leg. Integrity failures abstain without replacements.

    Cost H1/H2 values are shadow diagnostics only, with no claimed adoption.
    Original hypothetical capacity is not redistributed after an abstention.
    """
    import r945
    pair = res.get('pair') or {}
    picks = []
    for side in ('long','short'):
        lg = pair.get(side) or {}
        for rank, p in enumerate(([lg['pick']] if lg.get('pick') else []) + (lg.get('extra') or [])):
            p['side_hint'] = side.upper()
            p['leg_hint'] = 'primary' if rank == 0 else 'extra'
            picks.append(p)
    rcfg, pcfg = cfg.get('risk', {}), cfg.get('pair', {})
    if not res.get('_allocation_done'):
        r945.allocate_book(picks, rcfg.get('account_equity',0), rcfg.get('max_position_pct',50),
                           risk_weight=pcfg.get('risk_weight',True), weight_cap=pcfg.get('weight_cap',.35))
    book_cap = rcfg.get('account_equity',0)*rcfg.get('max_position_pct',50)/100
    legs = []
    for p in picks:
        q = quotes.get(p['t'], {})
        sp = number(q.get('spread_bps'))
        vol = number(p.get('vol'), positive=True)
        density = sp/(100*vol) if sp is not None and vol else None
        reasons = []
        if not clock['eligible']:
            reasons.append(clock['status'])
        if q.get('status') == 'OK' and stamp(q['quote_time']).astimezone(ET).strftime('%H:%M') != '09:46':
            reasons.append('quote not from exact 09:46 entry minute')
        # MEASURING A SPREAD AND ACTING ON IT ARE TWO DECISIONS, and they get
        # two switches. `corroborate_bbo` (brief.py) makes an unstamped quote
        # produce a CORROBORATED spread instead of "unknown" — that is pure
        # visibility and changes no sizing. THIS flag decides whether such a
        # quote may also clear the abstain and let the leg be sized.
        #
        # Both default OFF. A CORROBORATED quote is recency-BOUNDED by a
        # timestamped trade bar, not recency-CERTIFIED by the venue, and the
        # difference is exactly the sort of thing that should be an explicit
        # choice rather than a quiet default.
        accept_corr = bool(cfg.get('execution', {}).get('accept_corroborated_bbo'))
        if q.get('status') == CORROBORATED and accept_corr:
            pass                      # spread known, recency bounded, accepted
        elif q.get('status') != 'OK':
            reasons.append(q.get('reason','validated BBO unavailable'))
        bound = r945.fill_bound(p['side_hint'],p['p945'],res.get('max_chase_pct',.04))
        fill = q.get('ask' if p['side_hint']=='LONG' else 'bid')
        if fill is not None and (fill > bound if p['side_hint']=='LONG' else fill < bound):
            reasons.append('quote outside original signal fill bound')
        allocated = p.get('alloc',0)
        legs.append({'ticker':p['t'],'side':p['side_hint'],'role':p['leg_hint'],
                     'signal_reference':p['p945'],'signal_time':'09:45 bar close',
                     'p_sided':p['p_up'] if p['side_hint']=='LONG' else 1-p['p_up'],
                     'density_tag':p.get('confidence'),'vol_pct':vol,
                     'baseline_shares':p.get('shares',0),'baseline_alloc':allocated,
                     'weight':allocated/book_cap if book_cap else 0,
                     'fill_bound':bound,'quote':q,'entry_reference':fill,
                     'entry_time':q.get('quote_time'), 'entry_spread_bps':sp,
                     'status':'ABSTAIN' if reasons else ('SHADOW' if shadow else 'ELIGIBLE'),
                     'reasons':reasons,'spread_density':density,
                     'h1_keep':density is not None and density <= .10,
                     'h2_scale':max(0,1-density) if density is not None else 0,
                     'estimated_round_trip_spread_usd':allocated*sp/10000 if sp is not None else None})
    return legs


def score_leg(leg, exit_quote, index_return_pct, *, fees_bps=None, slippage_bps=None, borrow_bps=None):
    """Actual BBO crossing proxy, with separately supplied commissions/slippage.

    Both entry and exit BBO must be validated. An assumed constant entry spread
    is not substituted for the exit spread. The timestamp caller enforces the
    registered sampling window. Actual fills may be analysed in a separate feed.
    """
    entry = leg.get('quote') or {}
    if entry.get('status') != 'OK' or exit_quote.get('status') != 'OK':
        raise ValueError('entry/exit validated BBO missing')
    values = [number(x) for x in (index_return_pct, fees_bps, slippage_bps)]
    if any(x is None for x in values) or values[1] < 0 or values[2] < 0:
        raise ValueError('missing/nonfinite benchmark or execution costs')
    if leg.get('side') not in {'LONG','SHORT'}:
        raise ValueError('invalid execution side')
    side = 1 if leg['side']=='LONG' else -1
    borrow = 0 if side == 1 else number(borrow_bps)
    if borrow is None or borrow < 0:
        raise ValueError('missing/nonfinite short borrow costs')
    em, xm = (entry['bid']+entry['ask'])/2, (exit_quote['bid']+exit_quote['ask'])/2
    raw = (xm/em-1)*100
    spread = (entry['spread_bps']+exit_quote['spread_bps']*(xm/em))/2
    net = side*raw-(spread+fees_bps+slippage_bps+borrow)/100
    return {'gross_pct':side*raw, 'net_pct':net, 'net_hit':net>0,
            'decisive':abs(net)>=.10, 'index_pct':index_return_pct,
            'selection_net_pct':net-side*index_return_pct,
            'tide_pct':side*index_return_pct,'round_trip_spread_bps':spread,
            'fees_bps':fees_bps,'slippage_bps':slippage_bps,'borrow_bps':borrow}


def observed_performance(reports, outcomes):
    """Exact-window BBO-proxy record, separate from the legacy close ledger.

    A complete book requires every selected leg and the matched independent
    index. No-pick sessions are cash only when the model actually ran with
    sufficient coverage. Missing legs never turn a partial winner into a book.
    """
    by={(r['session'],r['ticker'],r['exit_time']):r for r in outcomes}
    scores=[];daily=[];unscored=0
    for report in reports:
        intra=report['intraday'];legs=intra['legs'];values=[]
        if report['offline'] or intra['res'].get('coverage_fail'):
            continue
        for leg in legs:
            outcome=by.get((report['session'],leg['ticker'],'15:59'),{})
            if outcome.get('status')!='SCORED_BBO_PROXY':
                unscored+=1;continue
            m=outcome['metrics'];scores.append(m)
            values.append((leg,m))
        if len(values)!=len(legs):continue
        net=sum(l['weight']*m['net_pct'] for l,m in values)
        tide=sum(l['weight']*m['tide_pct'] for l,m in values)
        selection=sum(l['weight']*m['selection_net_pct'] for l,m in values)
        longs=[m['gross_pct'] for l,m in values if l['side']=='LONG']
        shorts=[-m['gross_pct'] for l,m in values if l['side']=='SHORT']
        ls=(sum(longs)/len(longs)-sum(shorts)/len(shorts)) if longs and shorts else None
        daily.append({'session':report['session'],'net_pct':net,'tide_pct':tide,
                      'selection_net_pct':selection,'long_minus_short_pct':ls})
    decisive=[m for m in scores if m['decisive']]
    return {'label':'09:46–15:59 timestamped BBO crossing proxy; actual fills may differ',
            'scored_legs':len(scores),'unscored_legs':unscored,
            'net_hit_rate':sum(m['net_hit'] for m in scores)/len(scores) if scores else None,
            'decisive_net_hit_rate':sum(m['net_hit'] for m in decisive)/len(decisive) if decisive else None,
            'complete_sessions':len(daily),'daily':daily,
            'mean_net_pct':sum(r['net_pct'] for r in daily)/len(daily) if daily else None,
            'mean_tide_pct':sum(r['tide_pct'] for r in daily)/len(daily) if daily else None,
            'mean_selection_net_pct':sum(r['selection_net_pct'] for r in daily)/len(daily) if daily else None}
