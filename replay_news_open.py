#!/usr/bin/env python3
"""The day-142 test: the news desk asked about the window it is scored on.

Runs exactly PREREGISTER_day142_newsdesk_open_prompt.md. Day-122's releases
(news_desk's event rule on the committed wire archive, 2026-07-02 → 10-01)
are asked twice on the same day: once with day-122's prompt moved to the
open by three exact substitutions (the test), once with day-122's own prompt
(beside it, paired). The measure is w_day, the signed open → close against
XIU; the decision is day-139's bar (news_desk._preopen_bar) at seed 142.

Resumable: daily bars, release bodies and every answer are cached under
.rb-state/replay/news_open/ (never committed). Writes the summary to
data/replay_day142_open_prompt.json.

    python replay_news_open.py
"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import datetime as dt
import json
import os
import pickle
import random
import statistics
import sys
import time
from pathlib import Path

import news_desk as N
import replay_news as R

CACHE = Path('.rb-state/replay/news_open')
SUMMARY = Path('data/replay_day142_open_prompt.json')
REGISTERED = 'PREREGISTER_day142_newsdesk_open_prompt.md'
PROMPT_VERSION = N.PROMPT_VERSION + '+day142-open'
SUBSTITUTIONS = (
    ('from 09:45 ET to the close of the same trading day',
     'from the opening trade at 09:30 ET to the close of the same trading day'),
    ('will already reflect what the release says by 09:45.',
     'will already reflect what the release says.'),
    ('why the move should continue or reverse after that.',
     'why the move should continue or reverse after the open.'),
)
SEED = 142
DRAWS = 2000
PLANT = 0.5
BAR = N.PREOPEN_BAR                 # t >= 3.0
POWER_Z = 0.8416                    # 80% power
PROBE = 12
DAY122_EVENTS = 420
WORDINGS = ('open', 'day122')
ATTEMPTS = 3                        # a failed REQUEST is retried; a reply never is


def open_prompt(base=None):
    """Day-122's prompt with its window moved to the open. Each substitution
    must occur exactly once, and no 09:45 may remain."""
    text = N.SYSTEM_PROMPT if base is None else base
    for old, new in SUBSTITUTIONS:
        if text.count(old) != 1:
            raise ValueError('SUBSTITUTION_NOT_FOUND_ONCE: ' + old)
        text = text.replace(old, new)
    if '09:45' in text:
        raise ValueError('09:45_REMAINS')
    return text


PROMPTS = {'open': open_prompt(), 'day122': N.SYSTEM_PROMPT}


# ── data, cached ────────────────────────────────────────────────────────────

def _cached(kind, key, fetch):
    path = CACHE / kind / (key + '.pkl')
    if path.exists():
        return pickle.loads(path.read_bytes())
    got = fetch(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(got))
    return got


def chart(ticker):
    return _cached('daily', ticker, N.daily_chart)


def prefetch(tickers):
    """Fill the chart cache in parallel; a name that fails twice is left to
    news_desk.events, which counts it."""
    def one(t):
        for attempt in range(2):
            try:
                chart(t)
                return None
            except Exception as exc:          # counted below, never swallowed
                if attempt:
                    return type(exc).__name__
                time.sleep(2)
    failed = collections.Counter()
    with cf.ThreadPoolExecutor(4) as pool:
        for why in pool.map(one, sorted(tickers)):
            if why:
                failed[why] += 1
    return dict(failed)


def gather():
    sessions = R.sessions()
    names = {N.MARKET}
    for s in sessions:
        names.update(N.candidates(s))
    chart_failed = prefetch(names)
    evs, excluded = {}, collections.Counter()
    for s in sessions:
        e, x = N.events(s, chart=chart)
        evs[s] = e
        excluded.update(x)
    return evs, dict(excluded), chart_failed


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


# ── the model ───────────────────────────────────────────────────────────────

def client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com',
                  max_retries=0, timeout=N.REQUEST_TIMEOUT)


def ask_with(system, batch, client):
    """news_desk.ask, byte for byte, with the system prompt passed in."""
    response = client.chat.completions.create(
        model=N.MODEL,
        messages=[{'role': 'system', 'content': system},
                  {'role': 'user', 'content': json.dumps({'items': batch}, ensure_ascii=False)}],
        response_format={'type': 'json_object'}, max_tokens=8000, timeout=N.REQUEST_TIMEOUT,
        extra_body={'thinking': {'type': 'disabled'}})
    choice = response.choices[0]
    if choice.finish_reason != 'stop':
        raise ValueError('reply cut off (%s)' % str(choice.finish_reason)[:30])
    return json.loads(choice.message.content), str(getattr(response, 'model', N.MODEL))[:60]


def answers(evs, texts, *, make_client=client):
    """{wording: {id: call}}, problems by wording, retried requests."""
    jobs = []
    for s in sorted(evs):
        for k, b in enumerate(N.batches(N.items(evs[s], 'full', texts))):
            for w in WORDINGS:
                jobs.append((s, k, w, b))

    def one(job):
        s, k, w, b = job
        path = CACHE / 'answers' / f'{s.isoformat()}_{k}_{w}.json'
        if path.exists():
            return job, json.loads(path.read_text()), 0
        retried = 0
        for attempt in range(ATTEMPTS):
            try:
                reply, model = ask_with(PROMPTS[w], b, make_client())
            except Exception as exc:          # counted; the batch is lost after ATTEMPTS
                if attempt + 1 == ATTEMPTS:
                    return job, {'calls': {}, 'problems': {
                        'request failed: ' + type(exc).__name__: len(b)}, 'model': None}, retried
                retried += 1
                time.sleep(4 * (attempt + 1))
                continue
            calls, problems = N.parse(reply, b)
            got = {'calls': calls, 'problems': problems, 'model': model}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(got))
            return job, got, retried

    out = {w: {} for w in WORDINGS}
    problems = {w: collections.Counter() for w in WORDINGS}
    retried = collections.Counter()
    with cf.ThreadPoolExecutor(6) as pool:
        for (s, k, w, b), got, n in pool.map(one, jobs):
            out[w].update(got['calls'])
            problems[w].update(got['problems'])
            retried[w] += n
    return out, {w: dict(c) for w, c in problems.items()}, dict(retried), len(jobs)


# ── the arithmetic ──────────────────────────────────────────────────────────

def by_session(rows, key='w_day'):
    """[(session, [values])] in date order, sessions with a value only."""
    by = collections.defaultdict(list)
    for r in rows:
        if r.get(key) is not None:
            by[r['session']].append(r[key])
    return [(s, by[s]) for s in sorted(by)]


def describe(rows, key='w_day'):
    sess = by_session(rows, key)
    v = [x for _, xs in sess for x in xs]
    m, t = N._clustered(sess)
    return {'n': len(v), 'sessions': len(sess), 'right': sum(x > 0 for x in v),
            'hit': round(sum(x > 0 for x in v) / len(v), 3) if v else None,
            'mean': None if m is None else round(m, 4), 't': None if t is None else round(t, 2)}


def control(sessions):
    """House rule 10: centre every call on the sample mean, add PLANT; the
    same session-clustered t must reach the bar."""
    m, _ = N._clustered(sessions)
    if m is None:
        return {'plant': PLANT, 't': None, 'detected': False, 'mde80': None}
    planted = [(s, [x - m + PLANT for x in xs]) for s, xs in sessions]
    t = N._clustered(planted)[1]
    return {'plant': PLANT, 't': None if t is None else round(t, 2),
            'detected': t is not None and t >= BAR,
            'mde80': round((BAR + POWER_Z) * PLANT / t, 4) if t else None}


def verdict(sessions, *, draws=DRAWS, seed=SEED):
    """Day-139's bar, then the registration's mapping: a mean <= 0 is FAIL;
    positive but short is NULL, or UNDERPOWERED when the control fails."""
    bar = N._preopen_bar(sessions, draws, seed)
    ctl = control(sessions)
    status = bar['status']
    if status == 'UNDERPOWERED':
        status = 'NULL' if ctl['detected'] else 'UNDERPOWERED'
    out = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in bar.items()}
    out['halves'] = [None if h is None else round(h, 4) for h in bar['halves']]
    out.update(status=status, control=ctl)
    return out


def paired(rows_a, rows_b, key='w_day'):
    """a − b on the same events, session-clustered, and how often the side changed."""
    b = {r['id']: r for r in rows_b}
    diff = collections.defaultdict(list)
    same = both = 0
    for r in rows_a:
        o = b.get(r['id'])
        if not o:
            continue
        both += 1
        same += o['side'] == r['side']
        if r.get(key) is not None and o.get(key) is not None:
            diff[r['session']].append(r[key] - o[key])
    sess = [(s, diff[s]) for s in sorted(diff)]
    m, t = N._clustered(sess)
    return {'events': both, 'side_changed': both - same,
            'side_changed_share': round((both - same) / both, 3) if both else None,
            'mean': None if m is None else round(m, 4), 't': None if t is None else round(t, 2),
            'sessions': len(sess)}


def probe(rows):
    """Day-122's contamination probe: each name's closing price on its session."""
    rng = random.Random(SEED)
    pick = rng.sample(rows, min(PROBE, len(rows)))
    q = [{'id': r['id'], 'ticker': r['ticker'], 'date': r['session']} for r in pick]
    resp = client().chat.completions.create(
        model=N.MODEL, response_format={'type': 'json_object'}, max_tokens=2000,
        extra_body={'thinking': {'type': 'disabled'}},
        messages=[{'role': 'system', 'content': 'For each Toronto Stock Exchange share and date, give '
                   'your best estimate of its closing price in CAD on that date. If you do not know, '
                   'still give your best estimate. Return JSON only: {"prices": [{"id": "...", '
                   '"close": <number>}]}'},
                  {'role': 'user', 'content': json.dumps({'items': q})}])
    got = {p.get('id'): p.get('close')
           for p in json.loads(resp.choices[0].message.content).get('prices', [])}
    errs = []
    for r in pick:
        frame = chart(r['ticker'])[1]
        days = [i.date() for i in frame.index]
        d = dt.date.fromisoformat(r['session'])
        g = got.get(r['id'])
        if d in days and isinstance(g, (int, float)) and g > 0:
            errs.append(abs(g / float(frame['Close'].iloc[days.index(d)]) - 1) * 100)
    med = statistics.median(errs) if errs else None
    return {'asked': len(pick), 'answered': len(errs),
            'median_abs_error_pct': None if med is None else round(med, 2),
            'void': med is not None and med < 2.0}


def run():
    import prepare_deepseek
    prepare_deepseek.load_private_key('.rb-state')
    evs, excluded, chart_failed = gather()
    n_ev = sum(len(v) for v in evs.values())
    print(f'events {n_ev} on {sum(1 for v in evs.values() if v)} sessions; '
          f'excluded {excluded}; charts failed {chart_failed}', flush=True)
    texts, body_failed = fetch_bodies(evs)
    print(f'bodies {len(texts)}; failed {body_failed}', flush=True)
    calls, problems, retried, n_jobs = answers(evs, texts)
    print(f'calls {[(w, len(calls[w])) for w in WORDINGS]} from {n_jobs} requests; '
          f'problems {problems}; retried {retried}', flush=True)

    mkt1 = chart(N.MARKET)[1]
    rows = {w: [] for w in WORDINGS}
    for s, es in evs.items():
        for e in es:
            s1 = chart(e['ticker'])[1]
            for w in WORDINGS:
                c = calls[w].get(e['id'])
                if c:
                    o = N.outcomes(c['side'], s, None, s1, None, mkt1)
                    rows[w].append({'id': e['id'], 'session': s.isoformat(),
                                    'ticker': e['ticker'], **c, **o})
    test = rows['open']
    result = {
        'registered': REGISTERED, 'prompt_version': PROMPT_VERSION, 'model': N.MODEL,
        'events': n_ev, 'day122_events': DAY122_EVENTS,
        'sessions_with_events': sum(1 for v in evs.values() if v),
        'excluded': excluded, 'charts_failed': chart_failed, 'bodies_failed': body_failed,
        'bodies_fetched': len(texts), 'requests': n_jobs, 'requests_retried': retried,
        'problems': problems,
        'verdict': verdict(by_session(test)),
        'descriptive': {
            w: {'w_day': describe(rows[w]), 'gap': describe(rows[w], 'gap'),
                'long_share': round(sum(r['side'] == 'LONG' for r in rows[w]) / len(rows[w]), 3)
                if rows[w] else None,
                'material_w_day': describe([r for r in rows[w] if r['material']]),
                'routine_w_day': describe([r for r in rows[w] if not r['material']]),
                'confidence_0.6_w_day': describe([r for r in rows[w] if r['confidence'] >= 0.6])}
            for w in WORDINGS},
        'open_minus_day122': paired(rows['open'], rows['day122']),
    }
    try:
        result['contamination'] = probe(test)
    except Exception as exc:                  # reported, and the verdict says so
        result['contamination'] = {'error': type(exc).__name__}
    if result['contamination'].get('void'):
        result['verdict']['status'] = 'VOID'
    SUMMARY.write_text(json.dumps(result, indent=1, default=str))
    return result


def main():
    result = run()
    print(json.dumps({k: result[k] for k in ('verdict', 'open_minus_day122', 'contamination')},
                     indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
