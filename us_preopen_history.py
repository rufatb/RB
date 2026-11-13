#!/usr/bin/env python3
"""COUNCIL LAB ITEM 9, ON HISTORY (day-151): the pre-open desk replayed.

The forward desk (us_preopen.py, day-149) has run since 2026-11-10. This asks
its question of the sessions before it, from 2026-07-02 to 2026-11-09:
on a TSX name that also trades in New York, an overnight release read before
the bell, is anything left between the read and the 09:30 open on the New
York listing? Registered in PREREGISTER_day151_us_preopen_history.md before
any return was computed.

The population is pinned first (`--population`), from the forward desk's own
filter (`us_preopen.releases`) run on a clock cut at each morning's read, over
FMP's press feed for the US symbol (fetched by month, served as it stood at
the read) and the Canadian wire archive. It holds titles, times and the
feed's summary: no price and no return.

    python us_preopen_history.py --population     write data/us_preopen_history_day151.json (FMP, ~1 min)
    python us_preopen_history.py --run            the registered test, once (DeepSeek + FMP bars)

The run asks DeepSeek each read's events as the live desk does
(news_desk.answer, the full arm: title and summary), prices the read from the
US listing's last one-minute extended-hours bar of the 30 minutes before it
(after the last release, not before 04:00), exits at the 09:30 open
(us_preopen.session_marks / outcomes), and judges the session means with the
registered bar. Answers and bars are cached under .rb-state, so a killed run
resumes without asking a read twice. Writes data/us_preopen_history_day151_result.json.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import json
import math
import random
import statistics as st
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import us_preopen as U

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
POPULATION = ROOT/'data'/'us_preopen_history_day151.json'
RESULT = ROOT/'data'/'us_preopen_history_day151_result.json'
CACHE = ROOT/'.rb-state'/'us_preopen_history_cache'
FIRST, LAST = dt.date(2026, 7, 2), dt.date(2026, 11, 9)   # the forward desk starts 2026-11-10
READS = (dt.time(8, 15), dt.time(8, 55))                   # the 08:12 Routine; morning_full's second read
REGISTRATION = 'PREREGISTER_day151_us_preopen_history.md'
SEED, DRAWS, BAR, PLACEBO_P = 151, 10_000, 3.0, 0.01
COST = U.DEFAULT_HALF + U.EXIT_COST                         # 0.15% a call: history has no quotes
PLANT = 0.5                                                 # %, the verdict's own planted control
PROBE = 30
ENTRY_WINDOW = dt.timedelta(minutes=30)


def sessions(first=FIRST, last=LAST, is_trading=None):
    is_trading = is_trading or U._trading
    day, out = first, []
    while day <= last:
        if is_trading(day):
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def months(first=FIRST, last=LAST):
    """[(from, to)] calendar months covering the window, padded a week back
    for the first session's overnight."""
    start = first - dt.timedelta(days=7)
    out, cur = [], dt.date(start.year, start.month, 1)
    while cur <= last:
        nxt = dt.date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((max(cur, start), min(nxt - dt.timedelta(days=1), last)))
        cur = nxt
    return out


def press_history(read, twins, first=FIRST, last=LAST):
    """{us symbol: [FMP press rows]} for the window, fetched by month."""
    out = {}
    for twin in twins.values():
        rows, seen = [], set()
        for a, b in months(first, last):
            for r in read('news/press-releases', symbols=twin['us'], limit=100,
                          **{'from': a.isoformat(), 'to': b.isoformat()}) or []:
                if isinstance(r, dict):
                    k = (r.get('publishedDate'), r.get('title'))
                    if k not in seen:
                        seen.add(k)
                        rows.append(r)
        out[twin['us']] = rows
    return out


class AsOf:
    """A read function that serves the press feed as it stood at `end`: the
    newest 15 rows published at or before it, as the live call returns the
    newest 15. Any other endpoint is refused: the population needs no price."""

    def __init__(self, history, end):
        self.history, self.end, self.failures = history, end, {}

    def __call__(self, path, **params):
        if path != 'news/press-releases':
            raise KeyError('ASOF_PRESS_ONLY')
        rows = []
        for r in self.history.get(params.get('symbols'), []):
            try:
                at = dt.datetime.strptime(str(r.get('publishedDate')), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
            except ValueError:
                continue
            if at <= self.end:
                rows.append((at, r))
        rows.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in rows[:int(params.get('limit') or 15)]]


def population(read=None, twins=None, days=None, archive=None, is_trading=None):
    """Every (session, ticker) the forward desk would have asked about, with
    the read it belongs to. The first read stands; a name first seen at the
    second read keeps its own read time, as on the live desk."""
    import newswire
    read = read or U._reader()
    twins = U.load_twins() if twins is None else twins
    days = sessions(is_trading=is_trading) if days is None else days
    history = press_history(read, twins, days[0], days[-1])
    events, dropped = [], 0
    every = newswire.read(archive)                 # read once: the live call re-reads the archive per name
    original = newswire.read
    newswire.read = lambda root=None, since=None: [r for r in every if not since or
                                                   r['published_at'][:10] >= (since - dt.timedelta(days=1)).isoformat()]
    try:
        return _population(read, twins, days, archive, is_trading, history, events, dropped)
    finally:
        newswire.read = original


def _population(read, twins, days, archive, is_trading, history, events, dropped):
    for day in days:
        start = U.prior_close(dt.datetime.combine(day, dt.time(8), tzinfo=ET), is_trading)
        have = set()
        for t in READS:
            at = dt.datetime.combine(day, t, tzinfo=ET)
            found, out = U.releases(AsOf(history, at), twins, start, at, archive)
            dropped += sum(out.values())
            for ticker, rows in sorted(found.items()):
                if ticker in have:
                    continue
                have.add(ticker)
                events.append({'session': day.isoformat(), 'ticker': ticker, 'us': twins[ticker]['us'],
                               'read_at': at.isoformat(timespec='minutes'), 'releases': rows})
    return {'registration': REGISTRATION, 'window': [days[0].isoformat(), days[-1].isoformat()],
            'sessions': len(days), 'names': len(twins), 'reads': [t.strftime('%H:%M') for t in READS],
            'events': events, 'notices_dropped': dropped,
            'fetch_failures': dict(getattr(read, 'failures', None) or {})}


def summary(pop):
    evs = pop['events']
    by_session = {}
    for e in evs:
        by_session[e['session']] = by_session.get(e['session'], 0) + 1
    src = {}
    for e in evs:
        for r in e['releases']:
            src[r['source']] = src.get(r['source'], 0) + 1
    return {'events': len(evs), 'sessions_with_event': len(by_session), 'sessions': pop['sessions'],
            'second_read': sum(1 for e in evs if e['read_at'][11:16] == READS[1].strftime('%H:%M')),
            'names': len({e['ticker'] for e in evs}), 'releases_by_source': src,
            'notices_dropped': pop['notices_dropped'], 'fetch_failures': pop['fetch_failures']}


# ── the run (registered; committed before it runs) ──────────────────────────

def read_groups(pop):
    """[(read_at, [event])] in date order; each event carries the live id."""
    groups = collections.OrderedDict()
    for e in pop['events']:
        ev = dict(e, id='%s:%s' % (e['session'], e['ticker']))
        groups.setdefault(e['read_at'], []).append(ev)
    return list(groups.items())


def _cache_file(*parts):
    path = CACHE.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ask_read(read_at, evs, client=None, cache=True):
    """One read's events asked together, as live. Cached: a read is asked once,
    and a failed batch is counted and never re-asked."""
    import news_desk
    path = _cache_file('answers', read_at.replace(':', '') + '.json')
    if cache and path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    texts = {r['url']: r.get('text') or '' for e in evs for r in e['releases']}
    calls, problems, model = news_desk.answer(evs, 'full', texts, client=client)
    out = {'read_at': read_at, 'calls': calls, 'problems': problems, 'model': model}
    if cache:
        path.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    return out


def fetch(read, endpoint, symbol, day, **extra):
    """An FMP response, cached on disk by (endpoint, symbol, day)."""
    path = _cache_file('fmp', endpoint.replace('/', '_'), '%s_%s.json' % (symbol, day))
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    got = read(endpoint, symbol=symbol, **extra)
    if got is not None:
        path.write_text(json.dumps(got), encoding='utf-8')
    return got


def bars1(rows):
    """[(bar end, close)] from FMP one-minute bars."""
    out = []
    for r in rows or []:
        try:
            end = (dt.datetime.strptime(str((r or {}).get('date')), '%Y-%m-%d %H:%M:%S').replace(tzinfo=ET)
                   + dt.timedelta(minutes=1))
        except ValueError:
            continue
        c = U._num((r or {}).get('close'))
        if c and c > 0:
            out.append((end, c))
    return sorted(out)


def entry(bars, at, after=None):
    """(price, bar end, None) or (None, None, reason): the last one-minute bar
    ending at or before the read, within 30 minutes of it, after the last
    release and not before 04:00."""
    if not bars:
        return None, None, 'no one-minute bars'
    floor = dt.datetime.combine(at.date(), U.EARLIEST, tzinfo=ET)
    near = [(e, c) for e, c in bars if floor <= e <= at and at - e <= ENTRY_WINDOW]
    if not near:
        return None, None, 'no bar in the 30 minutes before the read'
    if after is not None:
        near = [(e, c) for e, c in near if e > after]
        if not near:
            return None, None, 'no bar after the release'
    end, close = near[-1]
    return close, end, None


def prev_close(eod, day):
    """The last regular close before `day` from daily rows."""
    best = None
    for r in eod or []:
        d, c = str((r or {}).get('date') or '')[:10], U._num((r or {}).get('close'))
        if c and d < day.isoformat() and (best is None or d > best[0]):
            best = (d, c)
    return best[1] if best else None


def price(pop, answers, read=None):
    """One row per answered event: the call, the entry, the exit and the outcomes."""
    read = read or U._reader()
    eod = {}

    def daily(symbol):
        if symbol not in eod:
            eod[symbol] = fetch(read, 'historical-price-eod/full', symbol, 'window',
                                **{'from': (FIRST - dt.timedelta(days=12)).isoformat(),
                                   'to': LAST.isoformat()}) or []
        return eod[symbol]
    spy = {}
    rows = []
    for read_at, evs in read_groups(pop):
        at = dt.datetime.fromisoformat(read_at)
        day = at.date().isoformat()
        calls = answers.get(read_at, {}).get('calls', {})
        if not any(e['id'] in calls for e in evs):
            continue
        if day not in spy:
            spy[day] = {'bars': bars1(fetch(read, 'historical-chart/1min', U.MARKET, day,
                                            **{'from': day, 'to': day, 'extended': 'true'})),
                        'marks': U.session_marks(fetch(read, 'historical-chart/5min', U.MARKET, day,
                                                       **{'from': day, 'to': day}), day),
                        'prev': prev_close(daily(U.MARKET), at.date())}
        s = spy[day]
        spy_px, spy_end, spy_why = entry(s['bars'], at)
        for e in evs:
            c = calls.get(e['id'])
            if not c:
                continue
            last = max(dt.datetime.fromisoformat(r['published_at']) for r in e['releases'])
            px, end, why = entry(bars1(fetch(read, 'historical-chart/1min', e['us'], day,
                                             **{'from': day, 'to': day, 'extended': 'true'})), at, last)
            marks = U.session_marks(fetch(read, 'historical-chart/5min', e['us'], day,
                                          **{'from': day, 'to': day}), day)
            row = {'session': day, 'ticker': e['ticker'], 'us': e['us'], 'read_at': read_at,
                   'side': c['side'], 'confidence': c['confidence'], 'material': c['material'],
                   'releases': len(e['releases']), 'source': e['releases'][-1].get('source'),
                   'title': e['releases'][-1]['title'], 'us_px': px,
                   'us_px_at': end.isoformat() if end else None, 'spy_px': spy_px,
                   'us_open': marks['open'], 'spy_open': s['marks']['open']}
            if why or spy_why:
                row['unpriced'] = why or ('SPY: ' + spy_why)
            elif not (marks['open'] and s['marks']['open']):
                row['unpriced'] = 'no 09:30 bar'
            else:
                row.update(U.outcomes(c['side'], px, spy_px, marks, s['marks']))
            prev = prev_close(daily(e['us']), at.date())
            if prev and s['prev'] and marks['open'] and s['marks']['open']:
                sign = 1 if c['side'] == 'LONG' else -1
                row['gap'] = round(sign * 100 * ((marks['open'] / prev - 1)
                                                 - (s['marks']['open'] / s['prev'] - 1)), 4)
            rows.append(row)
    return rows, dict(getattr(read, 'failures', None) or {})


def _tstat(means):
    if len(means) < 3:
        return None
    sd = st.stdev(means)
    return st.mean(means) / (sd / math.sqrt(len(means))) if sd > 0 else None


def judge(rows, probe=None, seed=SEED, draws=DRAWS):
    """The registered verdict on material, priced calls: VOID, UNDERPOWERED,
    PASS or NULL. The statistic is the mean of the session means of w_open."""
    by = {}
    for r in rows:
        if r.get('material') and r.get('w_open') is not None:
            by.setdefault(r['session'], []).append(r['w_open'])
    days = sorted(by)
    means = [st.mean(by[d]) for d in days]
    out = {'sessions': len(means), 'calls': sum(len(v) for v in by.values()), 'cost_pct': round(COST, 4)}
    if len(means) < 3:
        out['verdict'] = 'UNDERPOWERED'
        out['reason'] = 'fewer than three sessions with a material, priced call'
        return out
    mean, t = st.mean(means), _tstat(means)
    se = st.stdev(means) / math.sqrt(len(means))
    rng = random.Random(seed)
    hits = sum(st.mean(m * rng.choice((1, -1)) for m in means) >= mean for _ in range(draws))
    p = (hits + 1) / (draws + 1)
    half = len(means) // 2
    h1, h2 = st.mean(means[:half]), st.mean(means[half:])
    planted = _tstat([m - mean + PLANT for m in means])
    out.update({'mean_pct': round(mean, 4), 't': None if t is None else round(t, 2),
                'placebo_p': round(p, 4), 'halves_pct': [round(h1, 4), round(h2, 4)],
                'net_pct': round(mean - COST, 4), 'control_t_planted_0_5': None if planted is None
                else round(planted, 2), 'mde80_pct': round(2.8 * se, 4)})
    if probe and probe.get('void'):
        out['verdict'] = 'VOID'
    elif planted is None or planted < BAR:
        out['verdict'] = 'UNDERPOWERED'
    elif t is not None and t >= BAR and p < PLACEBO_P and h1 > 0 and h2 > 0 and mean > COST:
        out['verdict'] = 'PASS'
    else:
        out['verdict'] = 'NULL'
    return out


def _group(rows, key, value='w_open'):
    out = {}
    for r in rows:
        if r.get(value) is not None:
            out.setdefault(key(r), []).append(r[value])
    return {k: {'calls': len(v), 'mean_pct': round(st.mean(v), 4),
                'right': sum(1 for x in v if x > 0)} for k, v in sorted(out.items())}


def beside(rows):
    """Descriptive, never judged."""
    mat = [r for r in rows if r.get('material')]
    unpriced = collections.Counter(r['unpriced'] for r in rows if r.get('unpriced'))
    return {'material_w_0945': _group(mat, lambda r: 'all', 'w_0945').get('all'),
            'material_w_close': _group(mat, lambda r: 'all', 'w_close').get('all'),
            'material_gap': _group(mat, lambda r: 'all', 'gap').get('all'),
            'by_material': _group(rows, lambda r: 'material' if r.get('material') else 'routine'),
            'by_read': _group(mat, lambda r: r['read_at'][11:16]),
            'by_source': _group(mat, lambda r: r.get('source') or '?'),
            'by_side': _group(mat, lambda r: r['side']),
            'by_month': _group(mat, lambda r: r['session'][:7]),
            'answered': len(rows), 'material': len(mat),
            'unpriced': sum(unpriced.values()), 'unpriced_why': dict(unpriced)}


def run_probe(rows):
    """Day-122's contamination probe, seed 151, 30 events."""
    import replay_news
    replay_news.SEED, replay_news.PROBE = SEED, PROBE
    pick = [{'id': '%s:%s' % (r['session'], r['ticker']), 'ticker': r['ticker'], 'session': r['session']}
            for r in rows]
    return replay_news.probe(pick, {})


def run(pop=None, *, client=None, read=None, workers=4, probe=True):
    import prepare_deepseek
    pop = pop or json.loads(POPULATION.read_text(encoding='utf-8'))
    if client is None:
        prepare_deepseek.load_private_key(str(ROOT/'.rb-state'))
    groups = read_groups(pop)
    answers = {}
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(ask_read, at, evs, client): at for at, evs in groups}
        for f in cf.as_completed(futs):
            answers[futs[f]] = f.result()
    problems = collections.Counter()
    for a in answers.values():
        problems.update(a.get('problems') or {})
    rows, fmp_failures = price(pop, answers, read)
    pr = run_probe(rows) if probe and rows else None
    out = {'registration': REGISTRATION, 'events': len(pop['events']), 'reads': len(groups),
           'answered': len(rows), 'model_problems': dict(problems), 'fmp_failures': fmp_failures,
           'probe': pr, 'verdict': judge(rows, pr), 'beside': beside(rows), 'calls': rows}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--population', action='store_true')
    p.add_argument('--run', action='store_true')
    a = p.parse_args(argv)
    if a.population:
        pop = population()
        POPULATION.write_text(json.dumps(pop, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        print(json.dumps(summary(pop), indent=1))
        return 0
    if a.run:
        out = run()
        RESULT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in out.items() if k != 'calls'}, indent=1, default=str))
        return 0
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
