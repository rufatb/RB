#!/usr/bin/env python3
"""Why did the recorded picks win or lose? Descriptive diagnostics, day-117.

For every scored pick made BEFORE the open (Claude/DeepSeek selected, Jev
forced, the engine's board) this measures, from the same five-minute bars the
scorer uses:

  market     XIU.TO over the same bars; `excess` = the pick's return minus
             what simply holding the market in the pick's direction earned
  gap        today's open vs the prior close, signed to the pick's side
  early      open → 09:45, signed: how much of the move happened BEFORE entry
  stop_atr   distance from the 09:45 entry to the pick's own `invalid_at`,
             in daily ATRs (a level inside 0.5 ATR is inside ordinary noise)

Descriptive only. Nineteen picks establish nothing; this says WHAT happened.

    python diagnose_record.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
PRE_OPEN = {('claude', 'selected'), ('deepseek', 'selected'), ('jev', 'forced'),
            ('engine', 'board')}


def _bars(ticker, cache):
    if ticker not in cache:
        try:
            import replay_models
            cache[ticker] = replay_models.bars(ticker)
        except Exception:
            import model_picks
            cache[ticker] = model_picks._yahoo_bars(ticker).tz_convert(ET)
    return cache[ticker]


def _day(frame, day):
    return frame[[i.date() == day for i in frame.index]]


def atr_pct(frame, day, n=14):
    """Daily ATR% from the five-minute bars of the sessions before `day`."""
    days = sorted({i.date() for i in frame.index if i.date() < day})[-(n+1):]
    rows = []
    for d in days:
        f = _day(frame, d)
        rows.append((float(f['High'].max()), float(f['Low'].min()), float(f['Close'].iloc[-1])))
    trs = [max(h-l, abs(h-pc), abs(l-pc)) for (h, l, _), (_, _, pc) in zip(rows[1:], rows[:-1])]
    return (sum(trs)/len(trs))/rows[-1][2]*100 if trs else None


def diagnose(rows, cache=None):
    cache = {} if cache is None else cache
    out = []
    for r in rows:
        if (r['model'], r['kind']) not in PRE_OPEN or not r.get('scored_at'):
            continue
        day = dt.date.fromisoformat(r['session'])
        sign = 1 if r['side'] == 'LONG' else -1
        f = _day(_bars(r['ticker'], cache), day)
        prior = _bars(r['ticker'], cache)
        prior = prior[[i.date() < day for i in prior.index]]
        mk = _day(_bars('XIU.TO', cache), day)
        t = [i.time() for i in f.index]
        tm = [i.time() for i in mk.index]
        if dt.time(9, 40) not in t or prior.empty or dt.time(9, 40) not in tm or dt.time(15, 55) not in tm:
            continue
        open_ = float(f['Open'].iloc[0])
        entry = float(f['Close'].iloc[t.index(dt.time(9, 40))])
        prev_close = float(prior['Close'].iloc[-1])
        market = (float(mk['Close'].iloc[tm.index(dt.time(15, 55))])
                  / float(mk['Close'].iloc[tm.index(dt.time(9, 40))]) - 1) * 100
        level = float(r['invalid_at']) if r.get('invalid_at') else None
        atr = atr_pct(_bars(r['ticker'], cache), day)
        out.append({
            'session': r['session'], 'source': f"{r['model']}_{r['kind']}", 'side': r['side'],
            'ticker': r['ticker'], 'r_pct': float(r['r_pct']), 'hit': r['hit'] == '1',
            'excess_pct': float(r['r_pct']) - sign*market,
            'gap_pct': sign*(open_/prev_close - 1)*100,
            'early_pct': sign*(entry/open_ - 1)*100,
            'atr_pct': atr,
            'stop_atr': (abs(entry-level)/entry*100/atr) if level and atr else None,
            'stop_wrong_side_at_entry': (level is not None and
                                         (entry < level if sign == 1 else entry > level)),
            'invalidated': r.get('invalidated') == '1',
        })
    return out


def summary(diag):
    def rate(xs):
        return {'n': len(xs), 'hits': sum(x['hit'] for x in xs),
                'mean_r': sum(x['r_pct'] for x in xs)/len(xs) if xs else None}
    s = {'all': rate(diag),
         'excess_mean_pct': sum(x['excess_pct'] for x in diag)/len(diag) if diag else None,
         'gap_with_pick': rate([x for x in diag if x['gap_pct'] > 0]),
         'gap_against_pick': rate([x for x in diag if x['gap_pct'] <= 0]),
         'early_move_with_pick': rate([x for x in diag if x['early_pct'] > 0]),
         'early_move_against_pick': rate([x for x in diag if x['early_pct'] <= 0]),
         'longs': rate([x for x in diag if x['side'] == 'LONG']),
         'shorts': rate([x for x in diag if x['side'] == 'SHORT'])}
    stops = [x for x in diag if x['stop_atr'] is not None]
    s['stops'] = {'n': len(stops),
                  'median_stop_atr': sorted(x['stop_atr'] for x in stops)[len(stops)//2] if stops else None,
                  'inside_half_atr': sum(x['stop_atr'] < 0.5 for x in stops),
                  'already_past_at_entry': sum(x['stop_wrong_side_at_entry'] for x in stops),
                  'invalidated': sum(x['invalidated'] for x in stops)}
    by_source = {}
    for x in diag:
        by_source.setdefault(x['source'], []).append(x)
    s['by_source'] = {k: {**rate(v), 'excess_mean_pct': sum(x['excess_pct'] for x in v)/len(v)}
                      for k, v in by_source.items()}
    return s


def main():
    import model_picks
    diag = diagnose(model_picks.read())
    print(json.dumps({'summary': summary(diag), 'picks': diag}, indent=1, default=str))


if __name__ == '__main__':
    main()
