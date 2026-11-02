#!/usr/bin/env python3
"""Day-143, council lab item 4 (PREREGISTER_day143_report_day.md): a name on its
report day, a size rule.

Does a name's report window (D0 and D1 around FMP's report date) swing wider
from 09:45 to the close than its other days, among the name-days the two live
size rules (day-135c big movers, day-137 widest swings) would not already pass
over, without leaning either way, and also on the point-in-time S&P 500?

    python report_day.py --fetch     # download into .rb-state/report_day_cache; computes no return
    python report_day.py             # the one registered look -> data/report_day143.json

Primary: FMP 15-minute bars, 2024-01-02 -> 2026-10-29 (council_history's
09:45 -> 16:00). Secondary (descriptive): FMP dividend-adjusted daily bars,
2016-01-04 -> 2026-10-29, open -> close. Point in time: the S&P 500 as it stood
on each date (replay_events.sp500_membership), daily open -> close against SPY.
Research only: nothing here is read by the morning.
"""
from __future__ import annotations

import argparse
import bisect
import concurrent.futures as cf
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

import council_history as CH
import fmp_client as F
import replay_chasing as RC
import replay_weeks as W
from replay_drift import Fetch

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'data'/'report_day143.json'
NAMES = ROOT/'data'/'report_day143_names.json'
CACHE = ROOT/'.rb-state'/'report_day_cache'
START, END, EOD_FROM = '2024-01-02', '2026-10-29', '2023-10-01'
DAILY_START, DAILY_FROM = '2016-01-04', '2015-06-01'
DAILY_CHUNKS = (('2015-06-01', '2020-12-31'), ('2021-01-01', END))
MARKET, US_MARKET = 'XIU.TO', 'SPY'
BAR, LEAN_T, PLACEBO_SHIFT, SCALE = 1.15, 2.0, 20, 1.25
MOVER_ATR, WILD_PCTILE, WILD_MIN_NAMES, ATR_N = 1.0, 90, 20, 14
DRAWS, SEED = 2000, 143
WORKERS = 24                      # FMP latency, not its rate limit, binds the download


def names():
    return list(json.loads(NAMES.read_text())['names'])


# ── the download (no return is computed here) ───────────────────────────────

def _eod(rows, prefix=''):
    """[[date, open, high, low, close, volume]] ascending; rows without all four
    prices, or with high below low, are dropped."""
    out = []
    for r in rows or []:
        v = [r.get(prefix + k) for k in (('Open', 'High', 'Low', 'Close') if prefix else
                                         ('open', 'high', 'low', 'close'))]
        if all(isinstance(x, (int, float)) and x > 0 for x in v) and v[1] >= v[2]:
            vol = r.get('volume')
            out.append([str(r['date'])[:10]] + [float(x) for x in v]
                       + [float(vol) if isinstance(vol, (int, float)) else None])
    return sorted(out)


def _reports(rows):
    """Report dates FMP marks as reported (an actual EPS), ascending and unique."""
    return sorted({str(r['date'])[:10] for r in rows or []
                   if r.get('date') and r.get('epsActual') is not None})


def _daily(fetch, t):
    rows = []
    for a, b in DAILY_CHUNKS:
        got = fetch('historical-price-eod/dividend-adjusted', symbol=t, **{'from': a, 'to': b})
        if got is None:
            return None
        rows += got
    return _eod(rows, prefix='adj')


def collect_tsx(t, fetch, cache=CACHE):
    """One TSX name: daily bars (with volume), 15-minute session prices, the
    adjusted daily set and its report dates. Cached whole; a run resumes."""
    f = Path(cache)/'tsx'/(t + '.json')
    if f.exists():
        return json.loads(f.read_text())
    eod = _eod(fetch('historical-price-eod/full', symbol=t, **{'from': EOD_FROM, 'to': END}))
    bars, failed, capped = {}, 0, 0
    for a, b in RC.months(START, END):
        rows = fetch('historical-chart/15min', symbol=t, **{'from': a, 'to': b})
        if rows is None:
            failed += 1
            continue
        if len(rows) >= RC.CAP_BARS:
            capped += 1
        bars.update(RC.reduce_bars(rows))
    daily = _daily(fetch, t)
    reports = [] if t == MARKET else _reports(fetch('earnings', symbol=t, limit=400))
    out = {'ticker': t, 'eod': eod, 'bars': bars, 'daily': daily, 'reports': reports,
           'failed_calls': failed + (daily is None), 'capped_calls': capped}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def collect_us(t, fetch, cache=CACHE):
    """One S&P 500 name (or SPY): adjusted daily bars and its report dates."""
    f = Path(cache)/'us'/(t + '.json')
    if f.exists():
        return json.loads(f.read_text())
    daily = _daily(fetch, t)
    reports = [] if t == US_MARKET else _reports(fetch('earnings', symbol=t, limit=400))
    out = {'ticker': t, 'daily': daily, 'reports': reports, 'failed_calls': int(daily is None)}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def membership(fetch, cache=CACHE):
    """The S&P 500's intervals by name (replay_events.sp500_membership), cached."""
    import replay_events as E
    f = Path(cache)/'sp500_membership.json'
    if f.exists():
        got = json.loads(f.read_text())
        return {t: [tuple(x) for x in iv] for t, iv in got['intervals'].items()}, got['glitches']
    intervals, glitches = E.sp500_membership(fetch)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({'intervals': intervals, 'glitches': glitches}))
    return intervals, glitches


def us_names(intervals):
    """Every name that was a member at some point inside the daily window."""
    return sorted(t for t, iv in intervals.items() if any(b > DAILY_START and a <= END for a, b in iv))


def fetch_all():
    F.load_key('.rb-state')
    fetch = W.robust(Fetch(None))
    tsx = [MARKET] + names()
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        got = list(pool.map(lambda t: collect_tsx(t, fetch), tsx))
    intervals, glitches = membership(fetch)
    us = [US_MARKET] + us_names(intervals)
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        got_us = list(pool.map(lambda t: collect_us(t, fetch), us))
    return {'tsx_names': len(tsx), 'tsx_failed_calls': sum(x['failed_calls'] for x in got),
            'tsx_capped_calls': sum(x.get('capped_calls', 0) for x in got),
            'us_names': len(us), 'us_without_bars': sum(1 for x in got_us if not x['daily']),
            'membership_glitches': glitches, 'fetch_failures': getattr(fetch, 'failures', None)}


# ── the panels ────────────────────────────────────────────────────────────────

def windows(reports, cal, lo, hi, shift=0):
    """[(report, D0, D1)] for the report dates inside [lo, hi] on the session
    calendar `cal`: D0 is the first session on or after the date, D1 the next.
    `shift` moves both that many sessions earlier (the placebo: a window with
    no report). Returns (windows, how many reports fell outside)."""
    out, outside = [], 0
    for r in reports:
        k = bisect.bisect_left(cal, r)
        if not (lo <= r <= hi) or k + 1 >= len(cal) or k - shift < 0:
            outside += 1
            continue
        out.append((r, cal[k - shift], cal[k + 1 - shift]))
    return out, outside


def label(wins):
    """{session: 'D0' | 'D1'}; a session that is D0 of one report keeps D0."""
    out = {}
    for _, d0, d1 in wins:
        out[d0] = 'D0'
    for _, d0, d1 in wins:
        out.setdefault(d1, 'D1')
    return out


def rows_of(series, cal, mret, lo, hi, *, reports, member=None, bars=None):
    """One row per session of one name: (session, y, adj, gap, m, atr, win, pwin).
    `series` is [[date, o, h, l, c, vol]] ascending. With `bars` (the 15-minute
    session prices) y is 09:45 -> close; without, the day's open -> close. m is
    the prior session's move in its ATRs (daily_technicals, as day-135c reads
    it); atr is ATR14 as % of the last close (day-137's cut). The name's last
    bar must be the market's last session."""
    pos = {r[0]: i for i, r in enumerate(series)}
    mpos = {d: i for i, d in enumerate(cal)}
    wins, outside = windows(reports, cal, lo, hi)
    pw, _ = windows(reports, cal, lo, hi, shift=PLACEBO_SHIFT)
    win, pwin = label(wins), label(pw)
    out, skipped = [], {'short_history': 0, 'not_the_market_session': 0, 'not_a_member': 0}
    days = sorted(bars) if bars is not None else [r[0] for r in series]
    for d in days:
        if not (lo <= d <= hi) or d not in mret:
            continue
        i = pos.get(d)
        if i is None:
            continue
        if i < ATR_N + 2:
            skipped['short_history'] += 1
            continue
        if mpos.get(d, 0) < 1 or series[i - 1][0] != cal[mpos[d] - 1]:
            skipped['not_the_market_session'] += 1
            continue
        if member is not None and not member(d):
            skipped['not_a_member'] += 1
            continue
        if bars is not None:
            o, p945, _, c = bars[d]
            y = 100 * (c / p945 - 1)
        else:
            o, c = series[i][1], series[i][4]
            y = 100 * (c / o - 1)
        _, atr = CH.prior_fields(series, i)
        out.append((d, y, y - mret[d], 100 * (o / series[i - 1][4] - 1), RC.move_atr(series, i - 1), atr,
                    win.get(d, ''), pwin.get(d, '')))
    have = {r[0] for r in out}
    no_bar = sum(1 for _, d0, d1 in wins if d0 not in have and d1 not in have)
    return out, {'reports_in_window': len(wins), 'reports_outside_window': outside,
                 'reports_without_a_bar': no_bar, **skipped}


def comparison(rows):
    """The name-days neither live rule would pass over: the prior session's move
    under 1 ATR (day-135c) and ATR % under the session's 90th percentile across
    the names (day-137). A session with fewer than 20 names cannot be cut."""
    by = {}
    for r in rows:
        by.setdefault(r[1], []).append(r)
    keep, cuts, counts = [], {}, {'sessions_too_few_names': 0, 'no_move_or_atr': 0,
                                  'passed_over_mover': 0, 'passed_over_wild': 0}
    for d, rs in by.items():
        atrs = [r[6] for r in rs if r[6] is not None]
        if len(atrs) < WILD_MIN_NAMES:
            counts['sessions_too_few_names'] += 1
            continue
        cut = float(np.percentile(atrs, WILD_PCTILE))
        cuts[d] = cut
        for r in rs:
            if r[5] is None or r[6] is None:
                counts['no_move_or_atr'] += 1
            elif abs(r[5]) >= MOVER_ATR:
                counts['passed_over_mover'] += 1
            elif r[6] >= cut:
                counts['passed_over_wild'] += 1
            else:
                keep.append(r)
    return keep, counts


def panel(data, market_sym, lo, hi, *, intraday, members=None):
    """[(ticker, session, y, adj, gap, m, atr, win, pwin)] and the counts."""
    mk = data[market_sym]
    series = mk['eod'] if intraday else mk['daily']
    cal = [r[0] for r in series]
    if intraday:
        mret = {d: 100 * (b[3] / b[1] - 1) for d, b in mk['bars'].items() if d in set(cal)}
    else:
        mret = {r[0]: 100 * (r[4] / r[1] - 1) for r in series}
    rows, counts = [], {}
    for t, x in sorted(data.items()):
        if t == market_sym or not (x.get('eod') if intraday else x.get('daily')):
            continue
        member = None
        if members is not None:
            member = lambda d, t=t: any(a <= d < b for a, b in members.get(t, ()))
        got, c = rows_of(x['eod'] if intraday else x['daily'], cal, mret, lo, hi, reports=x['reports'],
                         member=member, bars=x['bars'] if intraday else None)
        rows += [(t,) + r for r in got]
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + v
    return rows, counts


# ── the statistics ───────────────────────────────────────────────────────────

def sd(xs):
    return float(np.std(xs, ddof=1)) if len(xs) > 1 else None


def ratio(win, rest):
    a, b = sd(win), sd(rest)
    return a / b if a is not None and b else None


def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def size(keep, col=7, y=2):
    """(window ys, rest ys, ratio) on one window column (7 the report window, 8 the placebo)."""
    w = [r[y] for r in keep if r[col]]
    rest = [r[y] for r in keep if not r[col]]
    return w, rest, ratio(w, rest)


def leans(keep):
    """The window's lean, 09:45 -> close against XIU, date-clustered: signed by
    the session's opening gap (continuation positive), and long."""
    w = [r for r in keep if r[7]]
    return {'continuation_vs_xiu': CH.stat([(r[1], sign(r[4]) * r[3]) for r in w if sign(r[4])]),
            'long_vs_xiu': CH.stat([(r[1], r[3]) for r in w])}


def control(rest, n, seed=SEED):
    """A random pseudo-window of the window's size drawn from the rest: its
    ratio unscaled, and with the pseudo-window scaled by 1.25 (house rule 10)."""
    rest = np.asarray(rest, float)
    if n < 2 or len(rest) - n < 2:
        return {'n': n, 'unscaled': None, 'scaled': None, 'detected': False}
    pick = np.zeros(len(rest), bool)
    pick[np.random.default_rng(seed).choice(len(rest), size=n, replace=False)] = True
    a, b = rest[pick], rest[~pick]
    un, sc = sd(a) / sd(b), sd(SCALE * a) / sd(b)
    return {'n': n, 'unscaled': round(un, 3), 'scaled': round(sc, 3), 'detected': bool(un < BAR <= sc)}


def bootstrap(keep, draws=DRAWS, seed=SEED):
    """The 95% interval of the window/rest ratio, resampling whole sessions, and
    the smallest ratio the test can tell from 1.00 (1 + 2.8 bootstrap sd: 95%
    two-sided, 80% power)."""
    sessions = sorted({r[1] for r in keep})
    idx = {d: i for i, d in enumerate(sessions)}
    agg = np.zeros((len(sessions), 6))
    for r in keep:
        o = 0 if r[7] else 3
        agg[idx[r[1]], o:o + 3] += (1.0, r[2], r[2] * r[2])
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        t = np.bincount(rng.integers(0, len(sessions), len(sessions)), minlength=len(sessions)) @ agg
        if t[0] < 2 or t[3] < 2:
            continue
        vw = (t[2] - t[1] ** 2 / t[0]) / (t[0] - 1)
        vr = (t[5] - t[4] ** 2 / t[3]) / (t[3] - 1)
        if vw > 0 and vr > 0:
            out.append(float(np.sqrt(vw / vr)))
    if not out:
        return None
    s = float(np.std(out, ddof=1))
    return {'draws': len(out), 'ci95': [round(float(np.percentile(out, 2.5)), 3),
                                        round(float(np.percentile(out, 97.5)), 3)],
            'sd': round(s, 4), 'smallest_detectable_ratio': round(1 + 2.8 * s, 3)}


def verdict(primary, lean, placebo_ratio, us_ratio, ctrl):
    bar = {'size': primary is not None and primary >= BAR,
           'no_lean': all(x['t'] is not None and abs(x['t']) < LEAN_T for x in lean.values()),
           'placebo': placebo_ratio is not None and placebo_ratio < BAR,
           'point_in_time': us_ratio is not None and us_ratio >= BAR}
    if not ctrl['detected']:
        return bar, 'UNDERPOWERED (the planted control was not detected)'
    return bar, 'PASS' if all(bar.values()) else 'FAIL'


# ── beside the verdict (descriptive) ──────────────────────────────────────────

def within_name(keep, k=6):
    """The median, across names with >= k window days, of each name's own ratio."""
    by = {}
    for r in keep:
        by.setdefault(r[0], ([], []))[0 if r[7] else 1].append(r[2])
    rs = [ratio(w, o) for w, o in by.values() if len(w) >= k and len(o) >= k]
    rs = [x for x in rs if x is not None]
    return {'names': len(rs), 'median': round(float(np.median(rs)), 3) if rs else None}


def by_year(keep):
    out = {}
    for y in sorted({r[1][:4] for r in keep}):
        sub = [r for r in keep if r[1][:4] == y]
        w, rest, x = size(sub)
        out[y] = {'window': len(w), 'rest': len(rest), 'ratio': None if x is None else round(x, 3)}
    return out


def volume_confirmed(data, cal):
    """{(ticker, D0)}: reports whose volume spike over D0 .. D1+3 falls on D0 or
    D1 (day-135b's test of FMP's date). Selecting on the spike inflates a size
    ratio, so this is flagged, never a verdict."""
    mpos = {d: i for i, d in enumerate(cal)}
    out = set()
    for t, x in data.items():
        if t == MARKET:
            continue
        vol = {r[0]: r[5] for r in x['eod'] if r[5]}
        for _, d0, d1 in windows(x['reports'], cal, START, END)[0]:
            span = cal[mpos[d0]:mpos[d1] + 4]
            vs = [(vol.get(d) or 0.0, d) for d in span]
            if any(v > 0 for v, _ in vs) and max(vs)[1] in (d0, d1):
                out.add((t, d0))
                out.add((t, d1))
    return out


def council_positions(data, cal, path=ROOT/'data'/'model_picks.csv'):
    """How many of the record's council positions (top2 and the passed-over
    shadows, 10-05 -> 10-29) sat in their name's report window."""
    import model_picks as M
    rows = [r for r in M.read(path) if r.get('model') in ('top2', 'top2mover', 'top2wild')
            and r.get('kind') == 'pick' and '2026-10-05' <= r.get('session', '') <= '2026-10-29']
    pos = {(r['session'], r['ticker'], r['side']) for r in rows}
    inside, unknown, detail = 0, 0, []
    for s, t, side in sorted(pos):
        x = data.get(t)
        if x is None:
            unknown += 1
            continue
        if s in label(windows(x['reports'], cal, START, END)[0]):
            inside += 1
            detail.append('%s %s %s' % (s, side, t))
    return {'positions': len(pos), 'in_a_report_window': inside, 'names_not_in_the_list': unknown,
            'which': detail}


# ── the one registered look ──────────────────────────────────────────────────

def load(kind):
    d = CACHE/kind
    if not d.exists():
        raise SystemExit('no cache: run `python report_day.py --fetch` first')
    return {f.stem: json.loads(f.read_text()) for f in d.glob('*.json')}


def r3(x):
    return None if x is None else round(x, 3)


def run():
    tsx = load('tsx')
    missing = [t for t in [MARKET] + names() if t not in tsx]
    if missing:
        raise SystemExit('the download is incomplete: %d names missing (%s)' % (len(missing), ', '.join(missing[:5])))
    rows, counts = panel(tsx, MARKET, START, END, intraday=True)
    keep, kept_counts = comparison(rows)
    w, rest, primary = size(keep)
    lean = leans(keep)
    _, _, placebo_ratio = size(keep, col=8)
    ctrl = control(rest, len(w))
    boot = bootstrap(keep)
    us = load('us')
    intervals = {t: [tuple(x) for x in iv] for t, iv in
                 json.loads((CACHE/'sp500_membership.json').read_text())['intervals'].items()}
    us_rows, us_counts = panel(us, US_MARKET, DAILY_START, END, intraday=False, members=intervals)
    us_keep, us_kept = comparison(us_rows)
    uw, urest, us_ratio = size(us_keep, y=3)          # against SPY, as registered
    bar, decision = verdict(primary, lean, placebo_ratio, us_ratio, ctrl)
    cal = [r[0] for r in tsx[MARKET]['eod']]
    vc = volume_confirmed(tsx, cal)
    d_rows, d_counts = panel(tsx, MARKET, DAILY_START, END, intraday=False)
    d_keep, _ = comparison(d_rows)
    out = {
        'registered': 'PREREGISTER_day143_report_day.md', 'run_on': dt.date.today().isoformat(),
        'window': [START, END], 'names': len(names()),
        'counts': counts, 'comparison': kept_counts, 'name_days': len(rows), 'kept_name_days': len(keep),
        'primary': {'window_name_days': len(w), 'rest_name_days': len(rest),
                    'sd_window_pct': r3(sd(w)), 'sd_rest_pct': r3(sd(rest)), 'ratio': r3(primary),
                    'bootstrap': boot},
        'lean': lean,
        'placebo': {'shift_sessions': PLACEBO_SHIFT, 'ratio': r3(placebo_ratio)},
        'point_in_time_sp500': {'window': [DAILY_START, END], 'members_in_window': len(us_names(intervals)),
                                'names_with_bars': sum(1 for t, x in us.items() if x.get('daily') and t != US_MARKET),
                                'counts': us_counts, 'comparison': us_kept, 'window_name_days': len(uw),
                                'rest_name_days': len(urest), 'sd_window_pct': r3(sd(uw)),
                                'sd_rest_pct': r3(sd(urest)), 'ratio': r3(us_ratio)},
        'control': ctrl, 'bar': bar, 'verdict': decision,
        'descriptive': {
            'D0': r3(ratio([r[2] for r in keep if r[7] == 'D0'], rest)),
            'D1': r3(ratio([r[2] for r in keep if r[7] == 'D1'], rest)),
            'without_the_live_rule_filter': r3(size(rows)[2]),
            'within_name_median_ratio': within_name(keep),
            'share_moving_3pct': {'window': r3(float(np.mean(np.abs(w) > 3))) if w else None,
                                  'rest': r3(float(np.mean(np.abs(rest) > 3))) if rest else None},
            'volume_confirmed_reports_FLAGGED': {
                'note': 'selecting on the volume spike inflates the ratio',
                'window_name_days': sum(1 for r in keep if r[7] and (r[0], r[1]) in vc),
                'ratio': r3(ratio([r[2] for r in keep if r[7] and (r[0], r[1]) in vc], rest))},
            'daily_open_to_close_tsx': {'window': [DAILY_START, END], 'counts': d_counts,
                                        'ratio': r3(size(d_keep)[2]), 'by_year': by_year(d_keep)},
            'council_positions': council_positions(tsx, cal)}}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--fetch', action='store_true', help='download only; computes no return')
    a = p.parse_args(argv)
    if a.fetch:
        print(json.dumps(fetch_all(), indent=1))
        return 0
    out = run()
    print(json.dumps({k: out[k] for k in ('verdict', 'bar', 'primary', 'lean', 'placebo', 'control')}, indent=1))
    print(json.dumps({'point_in_time_sp500': out['point_in_time_sp500']['ratio']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
