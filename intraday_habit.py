#!/usr/bin/env python3
"""Day-152 (PREREGISTER_day152_intraday_habit.md, council lab item 12): does a
name's own intraday habit persist?

The habit, for a name on session d, is the mean over the prior 20 market
sessions (d-20 .. d-1, never d) of h = the name's 09:45 -> close minus XIU's,
in %; a name needs h on 15 of those 20 sessions. Each session the names with a
habit and with d's bars are ranked; the top fifth and the bottom fifth (n // 5
each; a session with fewer than 25 such names is skipped and counted) give

    y = mean(top fifth's h on d) - mean(bottom fifth's h on d)

Persistence predicts y > 0. The per-pick edge is y / 2.

  primary    the 150 names, FMP 15-minute session prices 2024-01-02 -> 2026-10-29
  secondary  (a) the same names, daily open -> close against XIU's, 2016 ->
             (b) the point-in-time S&P 500, daily open -> close against SPY's

Every bar is read from day-143's cache (.rb-state/report_day_cache); there is
no network call and no model.

    python intraday_habit.py        # writes data/intraday_habit_day152.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE = ROOT/'.rb-state'/'report_day_cache'
NAMES = ROOT/'data'/'report_day143_names.json'
PICKS = ROOT/'data'/'model_picks.csv'
OUT = ROOT/'data'/'intraday_habit_day152.json'
START, END = '2024-01-02', '2026-10-29'
DAILY_START = '2016-01-04'
LIVE_FIRST = '2026-10-14'
MARKET, US_MARKET = 'XIU.TO', 'SPY'
WINDOW, NEED = 20, 15                     # the habit: 15 of the prior 20 sessions
LONG_WINDOW, LONG_NEED = 60, 45           # the descriptive 60-session habit
MIN_NAMES = 25                            # a fifth of at least 5 names
COST_PER_PICK = 0.13                      # the measured round trip, day-132b
PLANTED, DRAWS, SEED = 0.10, 2000, 152
BAR_T, BAR_P = 3.0, 0.01


# ── the habit and the sort ───────────────────────────────────────────────────

def habit(h: pd.DataFrame, window=WINDOW, need=NEED) -> pd.DataFrame:
    """The mean of the prior `window` rows (never the row itself), on the
    market's calendar, where at least `need` of them are present."""
    return h.shift(1).rolling(window, min_periods=need).mean()


def session_sort(hab: np.ndarray, out: np.ndarray, tickers):
    """One session: names with both a habit and an outcome, ranked by habit
    (ties by ticker). Returns (order of outcomes, k) or (None, n)."""
    ok = ~np.isnan(hab) & ~np.isnan(out)
    n = int(ok.sum())
    if n < MIN_NAMES:
        return None, n
    idx = np.flatnonzero(ok)
    keys = sorted(idx, key=lambda i: (hab[i], tickers[i]))
    return out[np.array(keys)], n // 5


def spread(hab: pd.DataFrame, out: pd.DataFrame, member=None):
    """Per session: {session, y, top, bottom, fifths, n}. `member(d, t)` limits
    the names on d (the point-in-time S&P 500)."""
    tickers = list(out.columns)
    rows, skipped = [], 0
    H, O = hab.to_numpy(float), out.to_numpy(float)
    for i, d in enumerate(out.index):
        h, o = H[i].copy(), O[i].copy()
        if member is not None:
            keep = np.array([member(d, t) for t in tickers])
            h[~keep] = np.nan
        ordered, k = session_sort(h, o, tickers)
        if ordered is None:
            if np.isfinite(h).any():
                skipped += 1
            continue
        top, bottom = float(ordered[-k:].mean()), float(ordered[:k].mean())
        fifths = [float(p.mean()) for p in np.array_split(ordered, 5)]
        rows.append({'session': d, 'y': top - bottom, 'top': top, 'bottom': bottom,
                     'fifths': fifths, 'n': len(ordered), 'k': k})
    return rows, skipped


# ── the statistics ───────────────────────────────────────────────────────────

def tstat(ys):
    ys = np.asarray([y for y in ys if y is not None], float)
    if ys.size < 2:
        return {'sessions': int(ys.size), 'mean_pct': None, 'se': None, 't': None}
    se = float(ys.std(ddof=1) / np.sqrt(ys.size))
    m = float(ys.mean())
    return {'sessions': int(ys.size), 'mean_pct': round(m, 4), 'se': round(se, 4),
            't': round(m / se, 2) if se else None,
            'positive_share': round(float((ys > 0).mean()), 3)}


def newey_west_t(ys, lags=5):
    """Descriptive only: the mean's t with a Newey-West variance."""
    x = np.asarray(ys, float) - np.mean(ys)
    n = x.size
    v = float(x @ x) / n
    for l in range(1, lags + 1):
        v += 2 * (1 - l / (lags + 1)) * float(x[l:] @ x[:-l]) / n
    return round(float(np.mean(ys)) / np.sqrt(v / n), 2) if v > 0 else None


def blocks(rows):
    ys = [r['y'] for r in sorted(rows, key=lambda r: r['session'])]
    q = len(ys) // 4
    parts = [ys[i * q:(i + 1) * q] if i < 3 else ys[3 * q:] for i in range(4)]
    return [round(float(np.mean(p)), 4) if p else None for p in parts]


def placebo(hab: pd.DataFrame, out: pd.DataFrame, draws=DRAWS, seed=SEED):
    """Within each session the habits are shuffled across that session's names
    and the mean y recomputed: the draws' means."""
    rng = np.random.default_rng(seed)
    tickers = list(out.columns)
    H, O = hab.to_numpy(float), out.to_numpy(float)
    total, used = np.zeros(draws), 0
    for i in range(len(out.index)):
        ordered, k = session_sort(H[i], O[i], tickers)
        if ordered is None:
            continue
        perm = np.argsort(rng.random((draws, ordered.size)), axis=1)
        shuffled = ordered[perm]
        total += shuffled[:, -k:].mean(axis=1) - shuffled[:, :k].mean(axis=1)
        used += 1
    return total / used if used else np.array([])


def verdict(rows, draws, secondary_means):
    main = tstat([r['y'] for r in rows])
    qs = blocks(rows)
    obs, se, t = main['mean_pct'], main['se'], main['t'] or 0
    p_up = float(np.mean(draws >= obs)) if draws.size and obs is not None else None
    p_down = float(np.mean(draws <= obs)) if draws.size and obs is not None else None
    planted_t = round(PLANTED / se, 2) if se else None
    edge = round(obs / 2, 4) if obs is not None else None
    pers = (obs is not None and obs > 0 and t >= BAR_T
            and all(x is not None and x > 0 for x in qs)
            and p_up is not None and p_up < BAR_P
            and edge > COST_PER_PICK
            and all(m is not None and m > 0 for m in secondary_means))
    rev = (obs is not None and obs < 0 and t <= -BAR_T
           and all(x is not None and x < 0 for x in qs)
           and p_down is not None and p_down < BAR_P)
    if planted_t is None or planted_t < BAR_T:
        name = 'UNDERPOWERED'
    else:
        name = 'PERSISTENCE' if pers else 'REVERSAL' if rev else 'NULL'
    return {'primary': main, 'block_means_pct': qs, 'per_pick_edge_pct': edge,
            'cost_per_pick_pct': COST_PER_PICK,
            'placebo': {'draws': int(draws.size), 'seed': SEED,
                        'p_one_sided_persistence': p_up, 'p_one_sided_reversal': p_down,
                        'sd_of_draws_pct': round(float(draws.std()), 4) if draws.size else None},
            'control': {'planted_pct': PLANTED, 't_planted': planted_t,
                        'mde80_pct': round(2.8 * se, 4) if se else None},
            'secondary_means_positive': all(m is not None and m > 0 for m in secondary_means),
            'verdict': name}


# ── the panels ───────────────────────────────────────────────────────────────

def load(kind):
    d = CACHE/kind
    if not d.exists():
        raise SystemExit('no cache: run `python report_day.py --fetch` first')
    return {f.stem: json.loads(f.read_text()) for f in d.glob('*.json')}


def _ok(*xs):
    return all(x is not None and np.isfinite(x) and x > 0 for x in xs)


def intraday_frames(data, names):
    """h (09:45 -> close against XIU), pre (open -> 09:45 against XIU) and
    night (the prior session's last bar -> today's open, against XIU) on XIU's
    15-minute calendar."""
    mk = data[MARKET]['bars']
    cal = sorted(d for d in mk if START <= d <= END)

    def legs(bars):
        main, pre, night = {}, {}, {}
        days = sorted(bars)
        prev = {d: days[i - 1] for i, d in enumerate(days) if i}
        for d in days:
            o, p, _, c = bars[d]
            if _ok(o, p, c):
                main[d] = 100 * (c / p - 1)
                pre[d] = 100 * (p / o - 1)
            q = prev.get(d)
            if q is not None and _ok(o, bars[q][3]):
                night[d] = (q, 100 * (o / bars[q][3] - 1))
        return main, pre, night

    m_main, m_pre, m_night = legs(mk)
    pos = {d: i for i, d in enumerate(cal)}
    H, P, N = {}, {}, {}
    for t in names:
        main, pre, night = legs(data[t]['bars'])
        H[t] = {d: main[d] - m_main[d] for d in cal if d in main and d in m_main}
        P[t] = {d: pre[d] - m_pre[d] for d in cal if d in pre and d in m_pre}
        # overnight counts only when the name's prior bar is the market's prior session
        N[t] = {d: night[d][1] - m_night[d][1] for d in cal
                if d in night and d in m_night and pos[d] > 0
                and night[d][0] == cal[pos[d] - 1] and m_night[d][0] == cal[pos[d] - 1]}
    frame = lambda x: pd.DataFrame(x, index=cal, columns=names).astype(float)
    return frame(H), frame(P), frame(N)


def daily_frame(data, names, market_sym, lo=DAILY_START, hi=END):
    """open -> close against the market's, on the market's daily calendar
    (the rows before `lo` are kept for the habit's warm-up)."""
    mk = {r[0]: r for r in data[market_sym]['daily']}
    cal = sorted(d for d in mk if d <= hi)
    m = {d: 100 * (mk[d][4] / mk[d][1] - 1) for d in cal if _ok(mk[d][1], mk[d][4])}
    cols = {}
    for t in names:
        rows = {r[0]: r for r in data[t].get('daily') or []}
        cols[t] = {d: 100 * (r[4] / r[1] - 1) - m[d] for d, r in rows.items()
                   if d in m and _ok(r[1], r[4])}
    return pd.DataFrame(cols, index=cal, columns=names).astype(float), lo


def after(rows, lo):
    return [r for r in rows if r['session'] >= lo]


# ── the live record (descriptive; cached bars only, so through END) ──────────

def live(hab: pd.DataFrame, path=PICKS, first=LIVE_FIRST, last=END):
    """Claude's nominations: within a session and side, did the one whose habit
    points its way more strongly do better? A count only."""
    by = {}
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            if (r['kind'] == 'nominated' and r['model'] == 'claude'
                    and first <= r['session'] <= last and r.get('r_pct') not in (None, '')):
                by.setdefault((r['session'], r['side']), []).append(r)
    pairs, better, missing = 0, 0, 0
    detail = []
    for (d, side), rs in sorted(by.items()):
        if len(rs) != 2:
            continue
        s = 1 if side == 'LONG' else -1
        hs = []
        for r in rs:
            v = hab[r['ticker']].get(d) if r['ticker'] in hab.columns and d in hab.index else None
            hs.append(None if v is None or np.isnan(v) else s * float(v))
        if None in hs:
            missing += 1
            continue
        a, b = (0, 1) if hs[0] >= hs[1] else (1, 0)
        win = float(rs[a]['r_pct']) > float(rs[b]['r_pct'])
        pairs += 1
        better += win
        detail.append({'session': d, 'side': side, 'stronger': rs[a]['ticker'],
                       'other': rs[b]['ticker'], 'stronger_did_better': win})
    return {'window': [first, last], 'pairs': pairs, 'stronger_habit_did_better': better,
            'pairs_without_a_habit': missing,
            'note': 'cached bars end %s, so later sessions are not read; a count, never a verdict' % last,
            'pairs_detail': detail}


# ── the run ──────────────────────────────────────────────────────────────────

def summary(rows):
    return {**tstat([r['y'] for r in rows]),
            'top_leg_pct': round(float(np.mean([r['top'] for r in rows])), 4) if rows else None,
            'bottom_leg_negated_pct': round(-float(np.mean([r['bottom'] for r in rows])), 4) if rows else None}


def run():
    names = json.loads(NAMES.read_text())['names']
    tsx = load('tsx')
    missing = [t for t in [MARKET] + names if t not in tsx]
    if missing:
        raise SystemExit('the cache is incomplete: %d names missing (%s)'
                         % (len(missing), ', '.join(missing[:5])))
    h, pre, night = intraday_frames(tsx, names)
    hab = habit(h)
    rows, skipped = spread(hab, h)
    draws = placebo(hab, h)

    d_tsx, lo = daily_frame(tsx, names, MARKET)
    sec_a_rows, sec_a_skip = spread(habit(d_tsx), d_tsx)
    sec_a_rows = after(sec_a_rows, lo)
    us = load('us')
    us_names = sorted(t for t in us if t != US_MARKET and us[t].get('daily'))
    intervals = {t: [tuple(x) for x in iv] for t, iv in
                 json.loads((CACHE/'sp500_membership.json').read_text())['intervals'].items()}
    member = lambda d, t: any(a <= d < b for a, b in intervals.get(t, ()))
    d_us, _ = daily_frame(us, us_names, US_MARKET)
    sec_b_rows, sec_b_skip = spread(habit(d_us), d_us, member=member)
    sec_b_rows = after(sec_b_rows, lo)
    sec_a, sec_b = summary(sec_a_rows), summary(sec_b_rows)
    v = verdict(rows, draws, [sec_a['mean_pct'], sec_b['mean_pct']])

    night_rows, _ = spread(habit(night), h)
    long_rows, _ = spread(habit(h, LONG_WINDOW, LONG_NEED), h)
    pre_rows, _ = spread(hab, pre)
    fifths = np.array([r['fifths'] for r in rows])
    out = {
        'registered': 'PREREGISTER_day152_intraday_habit.md', 'run_on': dt.date.today().isoformat(),
        'window': [START, END], 'names': len(names), 'habit': [WINDOW, NEED], 'seed': SEED,
        'sessions_skipped_under_25_names': skipped,
        'names_per_session_median': int(np.median([r['n'] for r in rows])) if rows else None,
        **v,
        'primary_newey_west_t_lag5': newey_west_t([r['y'] for r in rows]) if rows else None,
        'secondary': {
            'tsx_daily_open_to_close': {'window': [lo, END], 'sessions_skipped': sec_a_skip,
                                        **sec_a},
            'point_in_time_sp500_daily': {'window': [lo, END], 'sessions_skipped': sec_b_skip,
                                          'names_with_bars': len(us_names), **sec_b}},
        'descriptive': {
            'legs': {'top_fifth_pct': summary(rows)['top_leg_pct'],
                     'bottom_fifth_negated_pct': summary(rows)['bottom_leg_negated_pct']},
            'fifths_1_low_to_5_high_pct': [round(float(x), 4) for x in fifths.mean(axis=0)]
            if len(fifths) else None,
            'overnight_habit_predicts_0945_close (reversal expected, y < 0)': summary(night_rows),
            'habit_60_sessions': summary(long_rows),
            'open_to_0945_by_the_20_session_habit': summary(pre_rows),
            'by_year': {y: summary([r for r in rows if r['session'][:4] == y])
                        for y in sorted({r['session'][:4] for r in rows})},
            'secondary_tsx_by_year': {y: summary([r for r in sec_a_rows if r['session'][:4] == y])
                                      for y in sorted({r['session'][:4] for r in sec_a_rows})}},
    }
    try:
        out['live_record'] = live(hab)
    except Exception as exc:                       # descriptive only; named, never silent
        out['live_record'] = {'error': '%s: %s' % (type(exc).__name__, str(exc)[:120])}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.parse_args(argv)
    got = run()
    shown = {k: v for k, v in got.items() if k != 'live_record'}
    print(json.dumps(shown, indent=1))
    print(json.dumps({k: v for k, v in got['live_record'].items() if k != 'pairs_detail'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
