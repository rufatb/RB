#!/usr/bin/env python3
"""Replay the model desks over every past session the 5-minute history covers.

PREREGISTER_day117_replay.md is the contract; read it first. In one line: for
each session D, rebuild the candidate pool AS OF D 08:55 with the PRODUCTION
builder fed history cut off before D, ask DeepSeek and Jev the LIVE question,
and score every pick with the PRODUCTION scorer. Twelve live picks cannot say
whether a desk has skill; ~40 sessions can at least bound it.

    python replay_models.py --fetch          # raw bars, cached under .rb-state/replay
    python replay_models.py --run            # pools + model answers, resumable
    python replay_models.py --analyse        # the registered statistics

Nothing here is wired into the morning. Nothing here sizes or places anything.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
TZ = 'America/Toronto'
ROOT = Path(__file__).resolve().parent
CACHE = ROOT/'.rb-state'/'replay'
MARKET = 'XIU.TO'


# ── raw history, fetched once ────────────────────────────────────────────────

def _raw_path(ticker, interval, rng):
    return CACHE/'raw'/f'{ticker}_{interval}_{rng}.json'


def fetch_raw(ticker, interval, rng, *, adapter=None, retries=3):
    path = _raw_path(ticker, interval, rng)
    if path.exists():
        return json.loads(path.read_text())
    from adapters import YahooDirectAdapter, ChartRateLimitError
    adapter = adapter or YahooDirectAdapter(timeout=20)
    for attempt in range(retries):
        try:
            raw = adapter._chart(ticker, interval, rng)
            break
        except ChartRateLimitError:
            time.sleep(30 * (attempt + 1))
    else:
        raise RuntimeError('RATE_LIMITED')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw))
    return raw


def truncate_raw(raw, before, tz=TZ):
    """The same chart payload with every bar dated ON OR AFTER `before` removed.
    The one place future data could reach a replayed pool; tested directly."""
    import pandas as pd
    ts = raw.get('timestamp') or []
    keep = [i for i, t in enumerate(ts)
            if pd.Timestamp(t, unit='s', tz='UTC').tz_convert(tz).date() < before]
    quote = (raw.get('indicators', {}).get('quote') or [{}])[0]
    return {**raw, 'timestamp': [ts[i] for i in keep],
            'indicators': {**raw.get('indicators', {}),
                           'quote': [{k: [v[i] for i in keep] for k, v in quote.items()
                                      if isinstance(v, list)}]}}


class ReplayAdapter:
    """What `daily_technicals.from_yahoo` calls, serving cached daily bars cut
    off before the replayed session. Hourly bars are refused, so a placeholder
    hole refuses the name exactly as an unfillable live hole would."""
    exchange_tz = TZ

    def __init__(self, session):
        from adapters import YahooDirectAdapter
        self.session = session
        self._inner = YahooDirectAdapter(exchange_tz=TZ)

    def _chart(self, ticker, interval, rng):
        if interval != '1d':
            raise RuntimeError('REPLAY_HAS_NO_HOURLY_BARS')
        return truncate_raw(fetch_raw(ticker, '1d', '2y'), self.session)

    def _bars_df(self, raw):
        return self._inner._bars_df(raw)


def history_fetcher(ticker, now):
    """`prepare_factor_pool.fetch_history`, served from cache and cut off before
    the session. Same identity checks, same prior-session requirement."""
    from adapters import YahooDirectAdapter
    from factor_inputs import _previous_close
    raw = truncate_raw(fetch_raw(ticker, '5m', '60d'), now.date())
    meta = raw.get('meta', {})
    if (meta.get('symbol') != ticker or meta.get('currency') != 'CAD'
            or meta.get('exchangeName') != 'TOR' or meta.get('instrumentType') != 'EQUITY'):
        raise ValueError('RESEARCH_IDENTITY_NOT_VERIFIED')
    bars = YahooDirectAdapter(exchange_tz=TZ)._bars_df(raw)
    if bars.empty or bars.index[-1].date() != _previous_close(now).date():
        raise ValueError('RESEARCH_PRIOR_SESSION_MISSING')
    frame = {'columns': list(bars.columns), 'index': [i.isoformat() for i in bars.index],
             'data': bars.to_numpy().tolist()}
    return {'ticker': ticker, 'session': now.date().isoformat(),
            'frame': json.dumps(frame, allow_nan=False), 'receipt': {'meta': meta},
            'retrieved_at': now.isoformat()}


def serial_acquire(tasks):
    out = {}
    for name, (fn, _seconds) in tasks.items():
        try:
            out[name] = {'status': 'OK', 'value': fn(), 'error': None}
        except Exception as exc:
            out[name] = {'status': 'UNAVAILABLE', 'value': None,
                         'error': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
    return out


# ── sessions and pools ───────────────────────────────────────────────────────

def bars(ticker):
    from adapters import YahooDirectAdapter
    return YahooDirectAdapter(exchange_tz=TZ)._bars_df(fetch_raw(ticker, '5m', '60d')).tz_convert(ET)


def sessions():
    """Every session in the market's 5-minute history with a prior session
    before it and both scoring bars present."""
    frame = bars(MARKET)
    days = sorted({i.date() for i in frame.index})
    out = []
    for d in days[1:]:
        times = {i.time() for i in frame.index if i.date() == d}
        if dt.time(9, 40) in times and dt.time(15, 55) in times:
            out.append(d)
    return out


def pool(session, cfg):
    """Candidate rows as the models would have seen them at 08:55 on `session`."""
    path = CACHE/'pools'/f'{session}.json'
    if path.exists():
        return json.loads(path.read_text())
    import daily_technicals
    import prepare_factor_pool
    from factor_inputs import build_from_state
    now = dt.datetime.combine(session, dt.time(8, 55), tzinfo=ET)
    state = CACHE/'state'/session.isoformat()
    state.mkdir(parents=True, exist_ok=True)
    status = prepare_factor_pool._prepare(
        state, cfg, now=now, fetcher=history_fetcher, acquire_fn=serial_acquire,
        daily_fetcher=lambda t: daily_technicals.from_yahoo(t, ReplayAdapter(session), now),
        biotech_snapshot=None)
    payload = build_from_state(state, cfg, now)
    out = {'session': session.isoformat(), 'status': status.get('status'),
           'candidates': payload.get('candidates') or [], 'macro': payload.get('macro') or {}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=str))
    return out


def ask(session, p):
    path = CACHE/'answers'/f'{session}.json'
    if path.exists():
        return json.loads(path.read_text())
    import deepseek_opportunities as O
    import jev_opportunities as J
    now = dt.datetime.combine(session, dt.time(9, 0), tzinfo=ET)
    started = time.monotonic()
    ds = O.rank(p['candidates'], macro=p['macro'] or None, now=now)
    ds_seconds = time.monotonic() - started
    jev = J.rank(p['candidates'], macro=p['macro'] or None, now=now)
    out = {'session': session.isoformat(), 'deepseek': ds, 'jev': jev,
           'deepseek_seconds': round(ds_seconds, 1)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, default=str))
    return out


# ── scoring and the registered statistics ────────────────────────────────────

def picks_of(answer):
    """(group, side, pick) for every pick the registration scores."""
    out = []
    ds, jev = answer.get('deepseek') or {}, answer.get('jev') or {}
    for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
        for p in ds.get(key) or []:
            out.append(('deepseek_selected', side, p))
        for p in jev.get(key) or []:
            out.append(('jev_selected', side, p))
        f = jev.get('forced_' + side.lower())
        if isinstance(f, dict) and f.get('ticker'):
            out.append(('jev_forced', side, f))
    return out


def realized(session, ticker, side, cache):
    import model_picks
    if ticker not in cache:
        try:
            cache[ticker] = bars(ticker)
        except Exception:
            cache[ticker] = None
    if cache[ticker] is None:
        return None
    return model_picks.score_one({'session': session, 'side': side}, cache[ticker])


def clustered(values_by_session):
    means = [sum(v)/len(v) for v in values_by_session.values() if v]
    n = len(means)
    if n < 2:
        return {'sessions': n, 'mean': means[0] if means else None, 't': None}
    m = sum(means)/n
    sd = math.sqrt(sum((x-m)**2 for x in means)/(n-1))
    return {'sessions': n, 'mean': m, 'sd': sd, 't': m/(sd/math.sqrt(n)) if sd else None}


def analyse(results, pools, *, draws=2000, seed=117):
    """`results`: {session: [(group, side, ticker, confidence, r)]};
    `pools`: {session: {ticker: r_long}} — the realized LONG return of every
    scoreable name in that session's pool (a short earns its negative)."""
    rng = random.Random(seed)
    out = {}
    groups = sorted({g for rows in results.values() for g, *_ in rows})
    for group in groups:
        by_session = {s: [r for g, _side, _t, _c, r in rows if g == group]
                      for s, rows in results.items()}
        flat = [(s, side, r, c) for s, rows in results.items()
                for g, side, _t, c, r in rows if g == group]
        if not flat:
            continue
        hits = sum(r > 0 for _, _, r, _ in flat)
        # PLACEBO: the same sessions, the same long/short counts, random names.
        shape = {s: ([side for g, side, *_ in rows if g == group]) for s, rows in results.items()}
        null_hits, null_mean = [], []
        for _ in range(draws):
            rs = []
            for s, sides in shape.items():
                names = list(pools.get(s) or {})
                if not sides or len(names) < len(sides):
                    continue
                for side, name in zip(sides, rng.sample(names, len(sides))):
                    long_r = pools[s][name]
                    rs.append(long_r if side == 'LONG' else -long_r)
            if rs:
                null_hits.append(sum(r > 0 for r in rs)/len(rs))
                null_mean.append(sum(rs)/len(rs))
        rate = hits/len(flat)
        mean_r = sum(r for _, _, r, _ in flat)/len(flat)
        ordered = sorted(results)
        half = len(ordered)//2
        halves = [clustered({s: by_session[s] for s in part})['mean']
                  for part in (ordered[:half], ordered[half:])]
        c = clustered(by_session)
        p_hit = sum(x >= rate for x in null_hits)/max(len(null_hits), 1)
        p_mean = sum(x >= mean_r for x in null_mean)/max(len(null_mean), 1)
        passed = bool(c['t'] is not None and c['t'] >= 2.0 and p_hit < 0.05
                      and all(h is not None and h > 0 for h in halves))
        out[group] = {'picks': len(flat), 'hits': hits, 'hit_rate': rate, 'mean_r_pct': mean_r,
                      'clustered': c, 'placebo_p_hit': p_hit, 'placebo_p_mean': p_mean,
                      'placebo_hit_rate_mean': sum(null_hits)/len(null_hits) if null_hits else None,
                      'halves': halves, 'passes_registered_bar': passed,
                      'long': _side_stats(flat, 'LONG'), 'short': _side_stats(flat, 'SHORT')}
    return out


def _side_stats(flat, side):
    rs = [r for _, s, r, _ in flat if s == side]
    return {'picks': len(rs), 'hits': sum(r > 0 for r in rs),
            'mean_r_pct': sum(rs)/len(rs) if rs else None}


def oracle(pools, k=2):
    """Harness control: the realized best longs and shorts must score as hits."""
    hits = total = anti = 0
    for s, names in pools.items():
        ranked = sorted(names.items(), key=lambda kv: kv[1])
        best = [r for _, r in ranked[-k:]] + [-r for _, r in ranked[:k]]
        worst = [r for _, r in ranked[:k]] + [-r for _, r in ranked[-k:]]
        hits += sum(r > 0 for r in best)
        anti += sum(r > 0 for r in worst)
        total += len(best)
    return {'oracle_hit_rate': hits/total if total else None,
            'anti_oracle_hit_rate': anti/total if total else None, 'picks': total}


def rule_picks(candidates, key='rel_sector_pct', k=2, reverse=False):
    """Mechanical reference: top-k by `key` long, bottom-k short (or the reverse)."""
    rows = [c for c in candidates if isinstance((c.get('technicals') or {}).get(key), (int, float))]
    rows.sort(key=lambda c: c['technicals'][key])
    longs, shorts = rows[-k:], rows[:k]
    if reverse:
        longs, shorts = shorts, longs
    return [('LONG', c['ticker']) for c in longs] + [('SHORT', c['ticker']) for c in shorts]


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cfg():
    import yaml
    return yaml.safe_load((ROOT/'config.yaml').read_text())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--run', action='store_true')
    p.add_argument('--analyse', action='store_true')
    p.add_argument('--limit', type=int, default=0, help='only the last N sessions')
    a = p.parse_args(argv)
    import factor_pool_policy as P
    tickers = list(P.TICKERS) + [MARKET]
    if a.fetch:
        failed = []
        for i, t in enumerate(tickers):
            for interval, rng in (('5m', '60d'), ('1d', '2y')):
                try:
                    fetch_raw(t, interval, rng)
                except Exception as exc:
                    failed.append((t, interval, type(exc).__name__))
            if i % 10 == 9:
                time.sleep(2)
        print(json.dumps({'tickers': len(tickers), 'failed': failed}))
    days = sessions()
    if a.limit:
        days = days[-a.limit:]
    if a.run:
        from prepare_deepseek import load_private_key
        import jev_opportunities as J
        os.environ.setdefault('DEEPSEEK_MODEL', 'deepseek-flash')
        load_private_key(ROOT/'.rb-state')
        J.load_private_key(ROOT/'.rb-state')
        cfg = _cfg()
        for d in days:
            pl = pool(d, cfg)
            ans = ask(d, pl)
            usable = sum(1 for c in pl['candidates'] if c.get('technicals'))
            print(d, 'pool', usable, 'deepseek', (ans['deepseek'] or {}).get('status'),
                  len(picks_of(ans)), 'picks', flush=True)
    if a.analyse:
        report = run_analysis(days)
        (CACHE/'analysis.json').write_text(json.dumps(report, indent=1, default=str))
        print(json.dumps(report, indent=1, default=str))
    return 0


def run_analysis(days):
    import deepseek_opportunities as O
    cache, results, pools, rules, market = {}, {}, {}, {}, {}
    for d in days:
        ans_path, pool_path = CACHE/'answers'/f'{d}.json', CACHE/'pools'/f'{d}.json'
        if not ans_path.exists() or not pool_path.exists():
            continue
        s = d.isoformat()
        ans, pl = json.loads(ans_path.read_text()), json.loads(pool_path.read_text())
        usable = O.usable_candidates(pl['candidates'])
        pools[s] = {}
        for c in usable:
            sc = realized(s, c['ticker'], 'LONG', cache)
            if sc:
                pools[s][c['ticker']] = sc['r_pct']
        mk = realized(s, MARKET, 'LONG', cache)
        market[s] = mk['r_pct'] if mk else None
        results[s] = []
        for group, side, pick in picks_of(ans):
            sc = realized(s, pick['ticker'], side, cache)
            if sc:
                results[s].append((group, side, pick['ticker'],
                                   pick.get('confidence', pick.get('probability')), sc['r_pct']))
        for name, rev in (('rule_momentum', False), ('rule_reversal', True)):
            for side, t in rule_picks(usable, reverse=rev):
                if t in pools[s]:
                    r = pools[s][t] if side == 'LONG' else -pools[s][t]
                    results[s].append((name, side, t, None, r))
    stats = analyse(results, pools)
    # Market-adjusted, descriptive: each pick's return net of XIU.TO's move.
    for group in stats:
        adj = [r - (market[s] if side == 'LONG' else -market[s])
               for s, rows in results.items() for g, side, _t, _c, r in rows
               if g == group and market.get(s) is not None]
        stats[group]['market_adjusted_mean_pct'] = sum(adj)/len(adj) if adj else None
    conf = {}
    for s, rows in results.items():
        for g, side, t, c, r in rows:
            if g == 'deepseek_selected' and isinstance(c, (int, float)):
                b = '<0.55' if c < 0.55 else '0.55-0.60' if c < 0.60 else '>=0.60'
                conf.setdefault(b, []).append(r)
    return {'sessions': len(results), 'oracle': oracle(pools), 'groups': stats,
            'deepseek_by_confidence': {b: {'picks': len(v), 'hits': sum(x > 0 for x in v),
                                           'mean_r_pct': sum(v)/len(v)} for b, v in conf.items()},
            'market_mean_pct': (sum(v for v in market.values() if v is not None)
                                / max(1, sum(v is not None for v in market.values()))),
            'pool_sizes': {s: len(v) for s, v in pools.items()},
            'picks': {s: rows for s, rows in results.items()}}


if __name__ == '__main__':
    sys.exit(main())


# ── EXPLORATORY (day-117b): is there ANY signal in the rows the models see? ──
#
# Not part of the registered bar. A scan across every name-day of the replay:
# the rank correlation (IC) of each input field with the 09:45 → 15:55 return,
# averaged over sessions, plus the owner's VWAP/rvol rule on every name rather
# than seven picks. Fifteen fields are scanned, so |t| < 3 is noise by
# construction (Bonferroni at 5% two-sided is ~3.1); anything above it is a
# hypothesis to REGISTER and test forward, never something to adopt from here.

ROW_FIELDS = ('move_atr', 'gap', 'gap_atr', 'r0', 'rsi', 'macd_hist', 'rvol', 'sma50_pct',
              'sma200_pct', 'range52_pos', 'atr_pct', 'last_vs_vwap')
OPEN_FIELDS = ('gap_today', 'r0_today', 'vwap_pos_today', 'open_rvol_today')


def _opening_frame(ticker, cache):
    """Only the bars `consensus_picks.opening` reads, per ticker, once."""
    import consensus_picks
    if ticker not in cache:
        try:
            f = bars(ticker)
            cache[ticker] = {'open_bars': f[[i.time() in consensus_picks.OPEN_BARS for i in f.index]],
                             'first': f.groupby(f.index.date)['Open'].first(),
                             'last_close': f.groupby(f.index.date)['Close'].last()}
        except Exception:
            cache[ticker] = None
    return cache[ticker]


def panel(days):
    """One row per (session, pool name): the fields the models saw at 08:55,
    today's opening measures at 09:45, and the realized 09:45 → close return."""
    import consensus_picks
    import deepseek_opportunities as O
    rows, cache, open_cache = [], {}, {}
    for d in days:
        pool_path = CACHE/'pools'/f'{d}.json'
        if not pool_path.exists():
            continue
        s = d.isoformat()
        for c in O.usable_candidates(json.loads(pool_path.read_text())['candidates']):
            t, tech = c['ticker'], c.get('technicals') or {}
            sc = realized(s, t, 'LONG', cache)
            of = _opening_frame(t, open_cache)
            if not sc or of is None:
                continue
            m = consensus_picks.opening(of['open_bars'], d)
            prior = [x for x in of['last_close'].index if x < d]
            row = {'session': s, 'ticker': t, 'r': sc['r_pct']}
            for k in ROW_FIELDS[:-1]:
                v = tech.get(k)
                row[k] = v if isinstance(v, (int, float)) else None
            row['last_vs_vwap'] = ((tech['last']/tech['vwap'] - 1)*100
                                   if tech.get('last') and tech.get('vwap') else None)
            row['gap_today'] = ((of['first'][d]/of['last_close'][prior[-1]] - 1)*100
                                if prior and d in of['first'].index else None)
            row['r0_today'] = ((m['price']/of['first'][d] - 1)*100
                               if m.get('price') and d in of['first'].index else None)
            row['vwap_pos_today'] = m.get('price_vs_vwap_pct') if m.get('status') == 'OK' else None
            row['open_rvol_today'] = m.get('rvol') if m.get('status') == 'OK' else None
            rows.append(row)
    return rows


def feature_scan(rows):
    import pandas as pd
    df = pd.DataFrame(rows)
    out = {}
    for f in ROW_FIELDS + OPEN_FIELDS:
        ics = []
        for _s, g in df.groupby('session'):
            g = g[[f, 'r']].dropna()
            if len(g) >= 10 and g[f].nunique() > 1:
                ics.append(g[f].rank().corr(g['r'].rank()))
        if len(ics) >= 5:
            m = sum(ics)/len(ics)
            sd = (sum((x-m)**2 for x in ics)/(len(ics)-1))**0.5
            out[f] = {'sessions': len(ics), 'mean_ic': round(m, 4),
                      't': round(m/(sd/len(ics)**0.5), 2) if sd else None}
    return out


def vwap_rule(rows, rvol_min=1.2, draws=2000, seed=1172):
    """The owner's rule on every name-day: LONG above today's VWAP, SHORT below,
    opening rvol > rvol_min. Placebo: the same flagged names, random sides."""
    by_session = {}
    for r in rows:
        if r['vwap_pos_today'] is None or r['open_rvol_today'] is None:
            continue
        if r['open_rvol_today'] > rvol_min and r['vwap_pos_today'] != 0:
            sign = 1 if r['vwap_pos_today'] > 0 else -1
            by_session.setdefault(r['session'], []).append((sign, r['r']))
    flat = [(s, sign, x) for s, v in by_session.items() for sign, x in v]
    if not flat:
        return {'flagged': 0}
    signed = [sign*x for _, sign, x in flat]
    rng = random.Random(seed)
    null = []
    for _ in range(draws):
        rs = [rng.choice((1, -1))*x for _, _, x in flat]
        null.append(sum(v > 0 for v in rs)/len(rs))
    rate = sum(v > 0 for v in signed)/len(signed)
    c = clustered({s: [sign*x for sign, x in v] for s, v in by_session.items()})
    return {'flagged': len(flat), 'sessions': len(by_session), 'hit_rate': round(rate, 4),
            'mean_signed_pct': round(sum(signed)/len(signed), 4), 'clustered_t': c['t'] and round(c['t'], 2),
            'placebo_p': sum(x >= rate for x in null)/draws,
            'long': _side_stats([(None, 'LONG', sign*x, None) for _, sign, x in flat if sign == 1], 'LONG'),
            'short': _side_stats([(None, 'SHORT', sign*x, None) for _, sign, x in flat if sign == -1], 'SHORT')}
