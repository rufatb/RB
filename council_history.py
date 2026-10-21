#!/usr/bin/env python3
"""The day-137 registered test (PREREGISTER_day137_council.md): the council's habits on history.

  H1  following a name's last-session move against its sector (rel_sector_pct,
      |rel| >= 1%): does the stock's own part continue after 09:45, or reverse?
  H2  following a sector's last-session move against XIU (|S| >= 0.5%): does
      the sector's 09:45 -> close against XIU continue, or reverse?
  H3  the morning's 15 widest-swinging names (ATR % at or above the 90th
      percentile): do they swing >= 1.15x the rest, and lean neither way?

Primary: FMP 15-minute bars, 2024-01-02 -> 2026-10-02 (09:45 -> 16:00), the
live audit's sessions (from 10-05) left out. Secondary: ten years of FMP
dividend-adjusted daily bars (open -> close), 2016-01-04 -> 2026-10-02.

    python council_history.py      # writes data/council_history_day137.json

Every FMP response is reduced and cached per name under .rb-state, so a run
resumes. Research only: nothing here is read by the morning.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

import fmp_client as F
import replay_chasing as RC
import replay_weeks as W
import risk_rules as RR
from replay_drift import Fetch
from replay_fmp_analyst import clustered

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'council_history_day137.json'
CACHE = ROOT/'.rb-state'/'council_history_cache'
LIST = ROOT/'.rb-state'/'factor_pool_history'/'2026-10-21'/'candidates.json'
SECTORS = ROOT/'data'/'tsx_sectors.json'
START, END = '2024-01-02', '2026-10-02'
DAILY_START = '2016-01-04'
MARKET = 'XIU.TO'
REL_MIN, SECTOR_MIN, MIN_MEMBERS = 1.0, 0.5, 3
WILD_PCTILE, BAR = 90, 1.15
PLANTED, DRAWS, SEED, AWAY, ATR_N = 0.10, 2000, 137, 5, 14
WORKERS = 24                      # FMP latency, not its rate limit, binds the download


def names():
    return sorted(r['ticker'] for r in json.loads(LIST.read_text())['candidates'])


def sector_of():
    return {t: (v or {}).get('sector') for t, v in json.loads(SECTORS.read_text())['sectors'].items()}


def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


# ── the panel: one row per name and session ──────────────────────────────────

def prior_fields(eod, i):
    """(last-session move %, ATR14 % of the last close) seen at session index i."""
    if i < ATR_N + 2:
        return None, None
    c1, c2 = eod[i - 1][4], eod[i - 2][4]
    trs = []
    for j in range(i - ATR_N, i):
        h, l, pc = eod[j][2], eod[j][3], eod[j - 1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return 100 * (c1 / c2 - 1), 100 * (sum(trs) / len(trs)) / c1


def panel(data, sectors, start=START, end=END):
    """{session: {ticker: {'move', 'atr', 'main', 'sector'}}} and XIU's {session: (move, main)}."""
    mk = data[MARKET]
    mpos = {r[0]: i for i, r in enumerate(mk['eod'])}
    market = {}
    for d, (o, p945, noon, close) in mk['bars'].items():
        i = mpos.get(d)
        if start <= d <= end and i is not None and i >= 2:
            market[d] = (100 * (mk['eod'][i - 1][4] / mk['eod'][i - 2][4] - 1), 100 * (close / p945 - 1),
                         mk['eod'][i - 1][0])
    out, skipped = {}, {'no_daily_bar': 0, 'short_history': 0, 'no_market': 0}
    for t, x in data.items():
        if t == MARKET:
            continue
        pos = {r[0]: i for i, r in enumerate(x['eod'])}
        for d, (o, p945, noon, close) in x['bars'].items():
            if not (start <= d <= end):
                continue
            i = pos.get(d)
            if i is None:
                skipped['no_daily_bar'] += 1
                continue
            if d not in market or x['eod'][i - 1][0] != market[d][2]:
                skipped['no_market'] += 1
                continue
            move, atr = prior_fields(x['eod'], i)
            if move is None:
                skipped['short_history'] += 1
                continue
            out.setdefault(d, {})[t] = {'move': move, 'atr': atr, 'main': 100 * (close / p945 - 1),
                                       'sector': sectors.get(t)}
    return out, {d: v[:2] for d, v in market.items()}, skipped


def sector_medians(day):
    """{sector: (median last-session move, median main, members)} with >= 3 members."""
    by = {}
    for t, r in day.items():
        if r['sector']:
            by.setdefault(r['sector'], []).append(r)
    return {s: (st.median(r['move'] for r in rs), st.median(r['main'] for r in rs), len(rs))
            for s, rs in by.items() if len(rs) >= MIN_MEMBERS}


# ── statistics ───────────────────────────────────────────────────────────────

def stat(pairs):
    pairs = [(s, v) for s, v in pairs if v is not None]
    if len(pairs) < 2:
        return {'n': len(pairs), 'mean_pct': None, 'se': None, 't': None, 'hit': None}
    mean, se, t = clustered(pairs)
    return {'n': len(pairs), 'mean_pct': round(mean, 4), 'se': round(se, 4) if se else None,
            't': round(t, 2) if t is not None else None,
            'hit': round(sum(v > 0 for _, v in pairs) / len(pairs), 3)}


def blocks(events):
    ordered = sorted(events, key=lambda e: (e['session'], e['key']))
    q = len(ordered) // 4
    parts = [ordered[i * q:(i + 1) * q] if i < 3 else ordered[3 * q:] for i in range(4)]
    return [round(float(np.mean([e['y'] for e in p])), 4) if p else None for p in parts]


def placebo(events, signals, draws=DRAWS, seed=SEED):
    """Each event's sign replaced by the sign of the same key's signal on a random
    other session at least AWAY sessions away. `signals` is {key: [(session, signal)]}
    in session order; each event carries 'key', 'session' and its unsigned 'u'."""
    rng = np.random.default_rng(seed)
    idx = {k: {s: j for j, (s, _) in enumerate(v)} for k, v in signals.items()}
    signs = {k: np.array([sign(x) for _, x in v]) for k, v in signals.items()}
    groups = {}
    for e in events:
        groups.setdefault(e['key'], []).append((idx[e['key']][e['session']], e['u']))
    means = np.zeros(draws)
    for k, items in groups.items():
        n = len(signs[k])
        if n <= 2 * AWAY:
            continue
        own = np.array([j for j, _ in items])
        val = np.array([v for _, v in items])
        pick = rng.integers(0, n, size=(draws, len(own)))
        bad = np.abs(pick - own) < AWAY
        while bad.any():
            pick[bad] = rng.integers(0, n, size=int(bad.sum()))
            bad = np.abs(pick - own) < AWAY
        means += (signs[k][pick] * val).sum(axis=1)
    return means / len(events)


def verdict(events, signals):
    main = stat([(e['session'], e['y']) for e in events])
    qs = blocks(events)
    draws = placebo(events, signals) if events else np.array([])
    obs, se, t = main['mean_pct'], main['se'], main['t'] or 0
    p = float(np.mean(np.abs(draws) >= abs(obs))) if draws.size and obs is not None else None
    planted_t = round(PLANTED / se, 2) if se else None
    rev = (obs is not None and obs < 0 and t <= -3 and all(x is not None and x < 0 for x in qs)
           and p is not None and p < 0.05)
    cont = (obs is not None and obs > 0 and t >= 3 and all(x is not None and x > 0 for x in qs)
            and p is not None and p < 0.05)
    name = ('REVERSAL' if rev else 'CONTINUATION' if cont else
            'NULL' if planted_t and planted_t >= 3 else 'UNDERPOWERED')
    return {'primary': main, 'block_means_pct': qs,
            'placebo': {'draws': int(draws.size), 'p_two_sided': p,
                        'sd_of_draws_pct': round(float(draws.std()), 4) if draws.size else None},
            'control': {'planted_pct': PLANTED, 't_planted': planted_t,
                        'mde80_pct': round(2.8 * se, 3) if se else None},
            'verdict': name}


# ── H1, H2, H3 on one panel ──────────────────────────────────────────────────

def h1(rows, market):
    events, signals, raw, vs_xiu, by_size, by_side = [], {}, [], [], {}, {}
    for d in sorted(rows):
        med = sector_medians(rows[d])
        for t, r in sorted(rows[d].items()):
            s = med.get(r['sector'])
            if not s:
                continue
            rel = r['move'] - s[0]
            signals.setdefault(t, []).append((d, rel))
            if abs(rel) < REL_MIN:
                continue
            u = r['main'] - s[1]
            e = {'session': d, 'key': t, 'u': u, 'y': sign(rel) * u}
            events.append(e)
            raw.append((d, sign(rel) * r['main']))
            vs_xiu.append((d, sign(rel) * (r['main'] - market[d][1])))
            size = '1-2%' if abs(rel) < 2 else '2-4%' if abs(rel) < 4 else '>=4%'
            by_size.setdefault(size, []).append((d, e['y']))
            by_side.setdefault('LONG (beat its sector)' if rel > 0 else 'SHORT (lagged its sector)', []).append((d, e['y']))
    out = verdict(events, signals)
    out['descriptive'] = {'raw_signed': stat(raw), 'vs_xiu_signed': stat(vs_xiu),
                          'by_size': {k: stat(v) for k, v in sorted(by_size.items())},
                          'by_side': {k: stat(v) for k, v in sorted(by_side.items())}}
    out['events'] = len(events)
    return out


def h2(rows, market):
    events, signals, by_sector = [], {}, {}
    for d in sorted(rows):
        for s, (move, main, n) in sorted(sector_medians(rows[d]).items()):
            sig = move - market[d][0]
            signals.setdefault(s, []).append((d, sig))
            if abs(sig) < SECTOR_MIN:
                continue
            u = main - market[d][1]
            e = {'session': d, 'key': s, 'u': u, 'y': sign(sig) * u}
            events.append(e)
            by_sector.setdefault(s, []).append((d, e['y']))
    out = verdict(events, signals)
    out['descriptive'] = {'by_sector': {k: stat(v) for k, v in sorted(by_sector.items())}}
    out['events'] = len(events)
    return out


def h3(rows, market):
    wild, rest, follow, long_, thresholds = [], [], [], [], []
    for d in sorted(rows):
        atrs = [r['atr'] for r in rows[d].values()]
        if len(atrs) < 20:
            continue
        cut = float(np.percentile(atrs, WILD_PCTILE))
        thresholds.append(cut)
        for t, r in rows[d].items():
            if r['atr'] >= cut:
                wild.append(r['main'])
                adj = r['main'] - market[d][1]
                if r['move']:
                    follow.append((d, sign(r['move']) * adj))
                long_.append((d, adj))
            else:
                rest.append(r['main'])
    sd_w, sd_r = float(np.std(wild, ddof=1)), float(np.std(rest, ddof=1))
    f, lg = stat(follow), stat(long_)
    ratio = sd_w / sd_r
    passed = ratio >= BAR and all(x['t'] is not None and abs(x['t']) < 2 for x in (f, lg))
    return {'wild_name_days': len(wild), 'rest_name_days': len(rest),
            'sd_wild_pct': round(sd_w, 3), 'sd_rest_pct': round(sd_r, 3), 'ratio': round(ratio, 3),
            'threshold_atr_pct': {'median': round(st.median(thresholds), 2),
                                  'p10': round(float(np.percentile(thresholds, 10)), 2),
                                  'p90': round(float(np.percentile(thresholds, 90)), 2)},
            'lean_follow_vs_xiu': f, 'lean_long_vs_xiu': lg,
            'share_moving_3pct': {'wild': round(float(np.mean(np.abs(wild) > 3)), 3),
                                  'rest': round(float(np.mean(np.abs(rest) > 3)), 3)},
            'verdict': 'PASS' if passed else 'FAIL'}


# ── the ten-year daily panel (secondary: open -> close) ──────────────────────

def daily_rows(fetch, tickers, sectors, start=DAILY_START, end=END):
    """The same panel from adjusted daily bars; 'main' is the session's open -> close."""
    mkt = RR.bars(fetch, MARKET)
    cal = [d for d in sorted(mkt) if d <= end]
    pos = {d: i for i, d in enumerate(cal)}
    m_eod = [[d] + list(mkt[d]) for d in cal]
    market, out = {}, {}
    for i, d in enumerate(cal):
        if d >= start and i >= 2:
            market[d] = (100 * (m_eod[i - 1][4] / m_eod[i - 2][4] - 1), 100 * (mkt[d][3] / mkt[d][0] - 1))
    for t in tickers:
        b = RR.bars(fetch, t)
        eod = [[d] + list(b[d]) for d in sorted(b) if d in pos]
        for i, row in enumerate(eod):
            d = row[0]
            if d < start or d not in market or i < ATR_N + 2:
                continue
            if pos[eod[i - 1][0]] != pos[d] - 1:          # the name's last bar must be the market's last session
                continue
            move, atr = prior_fields(eod, i)
            out.setdefault(d, {})[t] = {'move': move, 'atr': atr, 'main': 100 * (row[4] / row[1] - 1),
                                       'sector': sectors.get(t)}
    return out, market


# ── the live Top 2: how often each rule would have acted (descriptive) ───────

def live(path=ROOT/'data'/'council_audit_day137.json'):
    if not path.exists():
        return None
    audit = json.loads(path.read_text())
    out = []
    for r in audit['positions']:
        if not r['picked']:
            continue
        sign_ = 1 if r['side'] == 'LONG' else -1
        rel = r.get('rel_sector_pct')
        pool = ROOT/'.rb-state'/'factor_pool_history'/r['session']/'candidates.json'
        cut = None
        if pool.exists():
            atrs = [c['technicals'].get('atr_pct') for c in json.loads(pool.read_text())['candidates']
                    if isinstance((c.get('technicals') or {}).get('atr_pct'), (int, float))]
            cut = float(np.percentile(atrs, WILD_PCTILE)) if len(atrs) >= 20 else None
        out.append({'session': r['session'], 'side': r['side'], 'ticker': r['ticker'], 'r': r.get('r'),
                    'follows_rel_1pct': None if rel is None else (sign_ * rel >= REL_MIN),
                    'atr_pct': r.get('atr_pct'), 'wild_cut': None if cut is None else round(cut, 2),
                    'wild': None if cut is None or r.get('atr_pct') is None else r['atr_pct'] >= cut})
    return out


def main(argv=None):
    F.load_key('.rb-state')
    fetch = W.robust(Fetch(None))
    sectors = sector_of()
    tickers = names()
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        data = dict(zip([MARKET] + tickers,
                        pool.map(lambda t: RC.collect(t, fetch, CACHE), [MARKET] + tickers)))
    rows, market, skipped = panel(data, sectors)
    primary = {'H1': h1(rows, market), 'H2': h2(rows, market), 'H3': h3(rows, market)}
    weekly = W.robust(Fetch(W.CACHE))
    drows, dmarket = daily_rows(weekly, tickers, sectors)
    secondary = {'H1': h1(drows, dmarket), 'H2': h2(drows, dmarket), 'H3': h3(drows, dmarket)}
    for part in (primary, secondary):
        for k in ('H1', 'H2'):
            part[k].pop('events_detail', None)
    out = {'registered': 'PREREGISTER_day137_council.md', 'run_on': dt.date.today().isoformat(),
           'primary_window': [START, END], 'secondary_window': [DAILY_START, END],
           'names': len(tickers), 'sessions': len(rows), 'name_days': sum(len(v) for v in rows.values()),
           'daily_sessions': len(drows), 'daily_name_days': sum(len(v) for v in drows.values()),
           'skipped': skipped,
           'fetch_failures': {'intraday': fetch.failures, 'daily': weekly.failures if hasattr(weekly, 'failures') else None},
           'capped_calls': sum(x.get('capped_calls', 0) for x in data.values()),
           'failed_calls': sum(x.get('failed_calls', 0) for x in data.values()),
           'primary': primary, 'secondary_daily_open_to_close': secondary, 'live_top2': live()}
    OUT.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ('names', 'sessions', 'name_days', 'daily_sessions',
                                          'daily_name_days', 'skipped', 'failed_calls', 'capped_calls')}))
    for part in ('primary', 'secondary_daily_open_to_close'):
        for k in ('H1', 'H2'):
            x = out[part][k]
            print(part, k, x['verdict'], x['primary'], x['block_means_pct'], x['placebo'], x['control'])
        print(part, 'H3', json.dumps(out[part]['H3']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
