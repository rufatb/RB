#!/usr/bin/env python3
"""The day-122 backtest: does reading the whole release call the stock after 09:45?

Runs exactly PREREGISTER_day122_releases.md over the wire archive, with
news_desk's event rule, prompt and arithmetic. Resumable: daily bars, release
bodies, five-minute bars and every answer are cached under
.rb-state/replay/news/ (bodies are not committed). Writes the summary to
data/replay_day122_releases.json.

    python replay_news.py            # everything (cached steps are skipped)
"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import datetime as dt
import json
import math
import pickle
import random
import statistics
import sys
from pathlib import Path

import news_desk as N

CACHE = Path('.rb-state/replay/news')
FIRST, LAST = dt.date(2026, 7, 2), dt.date(2026, 10, 1)
HOLIDAYS = {dt.date(2026, 8, 3), dt.date(2026, 9, 7)}
SHUFFLES = 2000
PLANT = 0.5
SEED = 122
PROBE = 12


def sessions():
    out, d = [], FIRST
    while d <= LAST:
        if d.weekday() < 5 and d not in HOLIDAYS:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _cached(kind, ticker, fetch):
    path = CACHE / kind / (ticker + '.pkl')
    if path.exists():
        return pickle.loads(path.read_bytes())
    got = fetch(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(got))
    return got


def chart(ticker):
    return _cached('daily', ticker, N.daily_chart)


def bars5(ticker):
    import model_picks
    return _cached('5m', ticker, model_picks._yahoo_bars)


def gather():
    evs, excluded = {}, collections.Counter()
    for s in sessions():
        e, x = N.events(s, chart=chart)
        evs[s] = e
        excluded.update(x)
    return evs, dict(excluded)


def fetch_bodies(evs):
    urls = sorted({r['url'] for e in sum(evs.values(), []) for r in e['releases']})
    failed = collections.Counter()

    def one(u):
        try:
            return u, N.body(u, CACHE / 'bodies')
        except Exception as exc:
            return u, exc
    texts = {}
    with cf.ThreadPoolExecutor(4) as pool:
        for u, t in pool.map(one, urls):
            if isinstance(t, Exception):
                failed[type(t).__name__] += 1
            else:
                texts[u] = t
    return texts, dict(failed)


def answers(evs, texts):
    def one(job):
        s, arm = job
        path = CACHE / 'answers' / f'{s.isoformat()}_{arm}.json'
        if path.exists():
            return job, json.loads(path.read_text())
        calls, problems, model = N.answer(evs[s], arm, texts)
        got = {'calls': calls, 'problems': problems, 'model': model}
        if not any(k.startswith('request failed') for k in problems):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(got))
        return job, got
    jobs = [(s, arm) for s in evs if evs[s] for arm in N.ARMS]
    out = {}
    with cf.ThreadPoolExecutor(4) as pool:
        for job, got in pool.map(one, jobs):
            out[job] = got
    return out


def clustered(by_session):
    means = [statistics.fmean(v) for v in by_session.values() if v]
    if len(means) < 2:
        return None
    m, sd = statistics.fmean(means), statistics.stdev(means)
    return {'mean': round(m, 4), 't': round(m / (sd / math.sqrt(len(means))), 2) if sd else None,
            'sessions': len(means), 'sd_session_means': round(sd, 4)}


def summary(rows, key):
    """Signed outcome `key` over `rows` (each has session, value under key)."""
    by = collections.defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            by[r['session']].append(r[key])
    vals = [v for vs in by.values() for v in vs]
    out = clustered(by) or {}
    out.update(n=len(vals), right=sum(v > 0 for v in vals))
    if vals:
        out['hit'] = round(out['right'] / len(vals), 3)
    return out, by


def placebo(rows, key, real_mean, rng):
    """Shuffle the sides among each session's own events (a sign flip for a moved side)."""
    by = collections.defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            by[r['session']].append((r['side'], r[key]))
    if not by:
        return None
    # the unsigned (LONG-direction) return; a side shuffle re-signs it
    raw = {s: [(v if side == 'LONG' else -v) for side, v in xs] for s, xs in by.items()}
    sides = {s: [side for side, _ in xs] for s, xs in by.items()}
    hits = 0
    for _ in range(SHUFFLES):
        means = []
        for s in by:
            sd = sides[s][:]
            rng.shuffle(sd)
            means.append(statistics.fmean((u if x == 'LONG' else -u) for x, u in zip(sd, raw[s])))
        if statistics.fmean(means) >= real_mean:
            hits += 1
    return round(hits / SHUFFLES, 4)


def blocks(by):
    keys = sorted(by)
    q = len(keys) // 4
    if q == 0:
        return []
    parts = [keys[i * q:(i + 1) * q] if i < 3 else keys[3 * q:] for i in range(4)]
    return [round(statistics.fmean(statistics.fmean(by[k]) for k in p), 4) for p in parts]


def probe(rows, texts):
    """Contamination: ask the closing price on the session for PROBE events."""
    rng = random.Random(SEED)
    pick = rng.sample(rows, min(PROBE, len(rows)))
    from openai import OpenAI
    import os
    client = OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com',
                    max_retries=0, timeout=120)
    q = [{'id': r['id'], 'ticker': r['ticker'], 'date': r['session']} for r in pick]
    resp = client.chat.completions.create(
        model=N.MODEL, response_format={'type': 'json_object'}, max_tokens=2000,
        extra_body={'thinking': {'type': 'disabled'}},
        messages=[{'role': 'system', 'content': 'For each Toronto Stock Exchange share and date, give '
                   'your best estimate of its closing price in CAD on that date. If you do not know, '
                   'still give your best estimate. Return JSON only: {"prices": [{"id": "...", '
                   '"close": <number>}]}'},
                  {'role': 'user', 'content': json.dumps({'items': q})}])
    got = {p.get('id'): p.get('close') for p in json.loads(resp.choices[0].message.content).get('prices', [])}
    errs = []
    for r in pick:
        frame = chart(r['ticker'])[1]
        days = [i.date() for i in frame.index]
        d = dt.date.fromisoformat(r['session'])
        g = got.get(r['id'])
        if d in days and isinstance(g, (int, float)) and g > 0:
            actual = float(frame['Close'].iloc[days.index(d)])
            errs.append(abs(g / actual - 1) * 100)
    med = statistics.median(errs) if errs else None
    return {'asked': len(pick), 'answered': len(errs),
            'median_abs_error_pct': round(med, 2) if med is not None else None,
            'void': med is not None and med < 2.0}


def main():
    import prepare_deepseek
    prepare_deepseek.load_private_key('.rb-state')
    evs, excluded = gather()
    n_ev = sum(len(v) for v in evs.values())
    print(f'events {n_ev} on {sum(1 for v in evs.values() if v)} sessions; excluded {excluded}',
          flush=True)
    texts, body_failed = fetch_bodies(evs)
    print(f'bodies {len(texts)}; failed {body_failed}', flush=True)
    ans = answers(evs, texts)
    problems = {arm: collections.Counter() for arm in N.ARMS}
    for (s, arm), got in ans.items():
        problems[arm].update(got['problems'])
    print(f'answers: {[(a, sum(len(g["calls"]) for (s, x), g in ans.items() if x == a)) for a in N.ARMS]}; '
          f'problems {dict((a, dict(c)) for a, c in problems.items())}', flush=True)

    mkt5, mkt1 = bars5(N.MARKET), chart(N.MARKET)[1]
    rows = {arm: [] for arm in N.ARMS}
    bar_failed = collections.Counter()
    for s, es in evs.items():
        for e in es:
            try:
                s5 = bars5(e['ticker'])
            except Exception as exc:
                bar_failed[type(exc).__name__] += 1
                s5 = None
            s1 = chart(e['ticker'])[1]
            for arm in N.ARMS:
                c = ans.get((s, arm), {}).get('calls', {}).get(e['id'])
                if not c:
                    continue
                o = N.outcomes(c['side'], s, s5, s1, mkt5, mkt1)
                rows[arm].append({'id': e['id'], 'session': s.isoformat(), 'ticker': e['ticker'],
                                  **c, **o})
    rng = random.Random(SEED)
    keys = ('w945', 'w945_raw', 'w_day', 'w_day_raw', 'w5d', 'w5d_raw', 'gap', 'gap_raw')
    result = {'registered': 'PREREGISTER_day122_releases.md', 'prompt_version': N.PROMPT_VERSION,
              'model': N.MODEL, 'events': n_ev, 'excluded': excluded, 'bodies_failed': body_failed,
              'five_minute_bars_failed': dict(bar_failed),
              'problems': {a: dict(c) for a, c in problems.items()}, 'arms': {}}
    for arm in N.ARMS:
        result['arms'][arm] = {}
        for k in keys:
            st, by = summary(rows[arm], k)
            result['arms'][arm][k] = st
        for label, sub in (('material', [r for r in rows[arm] if r['material']]),
                           ('confidence_0.6', [r for r in rows[arm] if r['confidence'] >= 0.6])):
            result['arms'][arm][label + '_w945'] = summary(sub, 'w945')[0]
            result['arms'][arm][label + '_w_day'] = summary(sub, 'w_day')[0]
        result['arms'][arm]['long_share'] = round(
            sum(r['side'] == 'LONG' for r in rows[arm]) / max(1, len(rows[arm])), 3)
    full = result['arms']['full']
    st, by = summary(rows['full'], 'w945')
    primary = dict(st)
    primary['placebo_p'] = placebo(rows['full'], 'w945', st.get('mean', 0), rng) if by else None
    primary['blocks'] = blocks(by)
    planted = {s: [v + PLANT for v in vs] for s, vs in by.items()}
    primary['planted_t'] = (clustered(planted) or {}).get('t')
    for k in ('w_day', 'gap'):
        s2, b2 = summary(rows['full'], k)
        full[k]['placebo_p'] = placebo(rows['full'], k, s2.get('mean', 0), rng) if b2 else None
    # FULL − HEADLINE, the same events
    hd = {r['id']: r for r in rows['headline']}
    diff = collections.defaultdict(list)
    agree = n_both = 0
    for r in rows['full']:
        h = hd.get(r['id'])
        if h:
            n_both += 1
            agree += h['side'] == r['side']
            if r.get('w945') is not None and h.get('w945') is not None:
                diff[r['session']].append(r['w945'] - h['w945'])
    result['full_minus_headline_w945'] = clustered(diff)
    result['same_side_as_headline'] = round(agree / n_both, 3) if n_both else None
    powered = primary['planted_t'] is not None and primary['planted_t'] >= 3
    passed = (powered and (primary.get('t') or 0) >= 3 and primary.get('mean', 0) > 0
              and (primary['placebo_p'] or 1) < 0.01 and primary['blocks']
              and all(b > 0 for b in primary['blocks']))
    try:
        result['contamination'] = probe(rows['full'], texts)
    except Exception as exc:
        result['contamination'] = {'error': type(exc).__name__}
    if result['contamination'].get('void'):
        verdict = 'VOID'
    elif not powered:
        verdict = 'UNDERPOWERED'
    else:
        verdict = 'PASS' if passed else 'FAIL'
    primary['verdict'] = verdict
    result['primary'] = primary
    gap = full['gap']
    result['line'] = (
        f"Backtest on {n_ev} overnight releases (Jul–Sep 2026), full text read: 09:45 to the close "
        f"against the market {primary.get('right')}/{primary.get('n')} right "
        f"({100 * primary.get('hit', 0):.0f}%), {primary.get('mean', 0):+.2f}% per call, t = "
        f"{primary.get('t')}, placebo p = {primary['placebo_p']} — "
        + ('beats chance.' if verdict == 'PASS' else 'does NOT beat chance.')
        + f" On the overnight gap the release caused (before the open, not tradable) it was "
        f"{gap.get('mean', 0):+.2f}% per call, t = {gap.get('t')}: it reads which way a release "
        "points, and the open has already priced it.")
    Path('data/replay_day122_releases.json').write_text(json.dumps(result, indent=1))
    print(json.dumps({'primary': primary, 'line': result['line'],
                      'contamination': result['contamination']}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
