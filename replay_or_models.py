#!/usr/bin/env python3
"""Day-134b: other OpenRouter models on the day-117 replay.

PREREGISTER_day134_models.md, registered before any call. Each model is asked
the PRODUCTION desk question (`deepseek_opportunities.SYSTEM_PROMPT` and
`build_request` rows) through `deepseek_opportunities.rank`, so its answer
passes the desks' own `_clean`, `check_levels` and `check_basis`. Picks are
scored by the day-117 scorer and judged on the day-117 bar, unchanged.

Before the replay, every model is probed for knowledge of the period (a model
that remembers July–September 2026 closes cannot be replay-tested) and put
through the desks' planted-edge control (house rule 4).

    python replay_or_models.py --probe --control --replay --analyse
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics as st
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
ET = ZoneInfo('America/New_York')
REPLAY = ROOT/'.rb-state'/'replay'
CACHE = REPLAY/'or_answers'
SUMMARY = ROOT/'data'/'replay_day134_models.json'
URL = 'https://openrouter.ai/api/v1/chat/completions'
MODELS = {'r1': 'deepseek/deepseek-r1-0528', 'sonnet55': 'anthropic/claude-sonnet-5.5'}
BUDGET_USD = 5.0
PROBE_NAMES = ('SHOP.TO', 'RY.TO', 'CNQ.TO', 'CLS.TO', 'AEM.TO')
PROBE_DATES = ('2026-07-15', '2026-08-14', '2026-09-15')
NAIVE_DATE = '2026-01-15'
PROBE_PROMPT = ('Without using any tools, give the closing price in Canadian dollars of each of these '
                'Toronto Stock Exchange stocks on each of these dates. If you do not know a price, give '
                'null; do not guess. Reply with JSON only, in the form '
                '{"TICKER": {"YYYY-MM-DD": number or null}}.\nStocks: %s\nDates: %s')


class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    """OpenRouter's own per-call cost (usage accounting), summed, thread-safe."""

    def __init__(self, cap=BUDGET_USD, spent=0.0):
        self.cap, self.spent, self.calls, self.lock = cap, spent, 0, threading.Lock()

    def check(self, reserve=0.10):
        with self.lock:
            if self.spent + reserve > self.cap:
                raise BudgetExceeded('BUDGET_REACHED')

    def add(self, response):
        usage = (response or {}).get('usage') or {}
        with self.lock:
            self.calls += 1
            cost = usage.get('cost')
            self.spent += float(cost) if isinstance(cost, (int, float)) else 0.0


def json_only(text):
    """A reasoning model may fence or preface its JSON; keep the object only."""
    text = (text or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        text = text[text.find('\n') + 1:] if '\n' in text else text
    start, end = text.find('{'), text.rfind('}')
    return text[start:end + 1] if start != -1 and end > start else text


class ORClient:
    """OpenAI-compatible enough for `deepseek_opportunities.rank`: one chat call
    to OpenRouter. DeepSeek's `thinking` switch is dropped (it is not an
    OpenRouter field); JSON mode is kept; OpenRouter's usage accounting gives
    each call's cost."""

    def __init__(self, model, post, ledger):
        self.model, self.post, self.ledger = model, post, ledger
        self.chat = self
        self.completions = self

    def create(self, *, messages, response_format=None, max_tokens=None, **_ignored):
        self.ledger.check()
        body = {'model': self.model, 'messages': messages, 'usage': {'include': True},
                'max_tokens': min(max_tokens or 16000, 32000)}
        if response_format:
            body['response_format'] = response_format
        response = None
        for attempt in range(2):
            try:
                response = self.post(body)
                break
            except ValueError as exc:            # HTTP_429 / HTTP_5xx once more
                if attempt or not str(exc).startswith(('HTTP_429', 'HTTP_5')):
                    raise
                time.sleep(3.0)
        self.ledger.add(response)
        choice = response['choices'][0]
        content = json_only((choice.get('message') or {}).get('content'))
        return SimpleNamespace(model=response.get('model', self.model), choices=[SimpleNamespace(
            finish_reason=choice.get('finish_reason') or 'stop',
            message=SimpleNamespace(content=content))])


def poster(timeout=300.0):
    import jev_opportunities as J
    import research as RS
    J.load_private_key(ROOT/'.rb-state')
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if not key:
        raise SystemExit('No OpenRouter credential is staged.')
    return RS.http_post(URL, {'Authorization': 'Bearer ' + key}, timeout)


# ── contamination probe ─────────────────────────────────────────────────────

def actual_closes(get=None):
    """FMP's closes on the probe dates and the naive date."""
    import fmp_client
    get = get or fmp_client.get
    out = {}
    for ticker in PROBE_NAMES:
        rows = get('historical-price-eod/full', symbol=ticker, **{'from': NAIVE_DATE, 'to': PROBE_DATES[-1]})
        by = {r['date']: r['close'] for r in rows if isinstance(r, dict)}
        out[ticker] = {d: by.get(d) for d in PROBE_DATES + (NAIVE_DATE,)}
    return out


def contamination(answer, actual):
    """Registered rule: >= 5 answers, median error <= 5% and under half of the
    naive guess's (each name's 2026-01-15 close)."""
    errors, naive = [], []
    for ticker, by_date in actual.items():
        for day in PROBE_DATES:
            said = ((answer or {}).get(ticker) or {}).get(day)
            truth, guess = by_date.get(day), by_date.get(NAIVE_DATE)
            if isinstance(said, (int, float)) and not isinstance(said, bool) and truth and guess:
                errors.append(abs(said / truth - 1))
                naive.append(abs(guess / truth - 1))
    median = st.median(errors) if errors else None
    naive_median = st.median(naive) if naive else None
    contaminated = bool(len(errors) >= 5 and median is not None and median <= 0.05
                        and naive_median is not None and median < 0.5 * naive_median)
    return {'answered': len(errors), 'median_error': median, 'naive_median_error': naive_median,
            'contaminated': contaminated}


def probe(client, actual):
    prompt = PROBE_PROMPT % (', '.join(PROBE_NAMES), ', '.join(PROBE_DATES))
    r = client.create(messages=[{'role': 'user', 'content': prompt}],
                      response_format={'type': 'json_object'}, max_tokens=8000)
    try:
        answer = json.loads(r.choices[0].message.content)
    except ValueError:
        answer = {}
    return {**contamination(answer, actual), 'answer': answer}


# ── positive control ────────────────────────────────────────────────────────

def control(client, runs=5, now=None):
    import deepseek_opportunities as O
    out = []
    for _ in range(runs):
        r = O.run_control(client=client, now=now)
        picked = [p['ticker'] for p in (r.get('longs') or []) + (r.get('shorts') or [])]
        out.append({'status': r.get('status'), 'long_detected': r.get('long_detected'),
                    'short_detected': r.get('short_detected'),
                    'noise_picked': [t for t in picked if t.startswith('NOIS')],
                    'reason': r.get('reason'),
                    'clean': bool(r.get('long_detected') and r.get('short_detected')
                                  and not any(t.startswith('NOIS') for t in picked))})
    clean = sum(x['clean'] for x in out)
    return {'runs': out, 'clean': clean, 'passes': clean >= 4}


# ── the replay ──────────────────────────────────────────────────────────────

def sessions():
    return sorted(dt.date.fromisoformat(p.stem) for p in (REPLAY/'pools').glob('*.json'))


def ask_session(slug, model, session, client):
    path = CACHE/slug/f'{session}.json'
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get('status') != 'UNAVAILABLE':
            return cached
    import deepseek_opportunities as O
    p = json.loads((REPLAY/'pools'/f'{session}.json').read_text())
    now = dt.datetime.combine(session, dt.time(9, 0), tzinfo=ET)
    started = time.monotonic()
    out = O.rank(p['candidates'], macro=p['macro'] or None, now=now, client=client, model=model)
    out = {**out, 'session': session.isoformat(), 'seconds': round(time.monotonic() - started, 1)}
    if not str(out.get('reason', '')).endswith('BudgetExceeded'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, default=str))
    return out


def replay(slug, model, client, days, workers=6):
    done = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ask_session, slug, model, d, client): d for d in days}
        for future, d in futures.items():
            try:
                done[d.isoformat()] = future.result()
            except BudgetExceeded:
                done[d.isoformat()] = {'status': 'NOT_ASKED', 'reason': 'BUDGET_REACHED'}
    return done


# ── the registered analysis (day-117's functions, unchanged) ────────────────

def load_answers(slug, days):
    out = {}
    for d in days:
        path = CACHE/slug/f'{d}.json'
        if path.exists():
            out[d.isoformat()] = json.loads(path.read_text())
    return out


def paired(results, a, b):
    """Per session: mean of group a minus mean of group b where both picked."""
    diffs = []
    for s, rows in results.items():
        ra = [r for g, _sd, _t, _c, r in rows if g == a]
        rb = [r for g, _sd, _t, _c, r in rows if g == b]
        if ra and rb:
            diffs.append(sum(ra)/len(ra) - sum(rb)/len(rb))
    if len(diffs) < 2:
        return {'sessions': len(diffs), 'mean': None, 't': None}
    m, sd = st.mean(diffs), st.stdev(diffs)
    return {'sessions': len(diffs), 'mean': m, 't': m/(sd/math.sqrt(len(diffs))) if sd else None}


def analyse(slugs, days):
    import deepseek_opportunities as O
    import replay_models as R
    cache, results, pools, market, abstained = {}, {}, {}, {}, {}
    answers = {slug: load_answers(slug, days) for slug in slugs}
    for d in days:
        s = d.isoformat()
        pl = json.loads((REPLAY/'pools'/f'{s}.json').read_text())
        pools[s] = {}
        for c in O.usable_candidates(pl['candidates']):
            sc = R.realized(s, c['ticker'], 'LONG', cache)
            if sc:
                pools[s][c['ticker']] = sc['r_pct']
        mk = R.realized(s, R.MARKET, 'LONG', cache)
        market[s] = mk['r_pct'] if mk else None
        results[s] = []
        sources = {slug + '_selected': answers[slug].get(s) for slug in slugs}
        day117 = REPLAY/'answers'/f'{s}.json'
        if day117.exists():
            sources['deepseek_day117'] = json.loads(day117.read_text()).get('deepseek')
        for group, ans in sources.items():
            if not ans:
                continue
            if ans.get('status') == 'NO_OPPORTUNITY':
                abstained[group] = abstained.get(group, 0) + 1
            for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
                for pick in ans.get(key) or []:
                    sc = R.realized(s, pick['ticker'], side, cache)
                    if sc:
                        results[s].append((group, side, pick['ticker'], pick.get('confidence'), sc['r_pct']))
    stats = R.analyse(results, pools)
    for group in stats:
        adj = [r - (market[s] if side == 'LONG' else -market[s])
               for s, rows in results.items() for g, side, _t, _c, r in rows
               if g == group and market.get(s) is not None]
        stats[group]['market_adjusted_mean_pct'] = sum(adj)/len(adj) if adj else None
    status = {slug: {k: sum(1 for a in answers[slug].values() if a.get('status') == k)
                     for k in ('READY', 'NO_OPPORTUNITY', 'UNAVAILABLE')} for slug in slugs}
    return {'sessions': len(days), 'groups': stats, 'abstained_sessions': abstained,
            'answer_status': status,
            'paired_vs_deepseek_day117': {slug: paired(results, slug + '_selected', 'deepseek_day117')
                                          for slug in slugs}}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--probe', action='store_true')
    p.add_argument('--control', action='store_true')
    p.add_argument('--replay', action='store_true')
    p.add_argument('--analyse', action='store_true')
    p.add_argument('--model', choices=sorted(MODELS), action='append')
    a = p.parse_args(argv)
    slugs = a.model or sorted(MODELS)
    summary = json.loads(SUMMARY.read_text()) if SUMMARY.exists() else {
        'registration': 'PREREGISTER_day134_models.md', 'models': MODELS, 'budget_usd': BUDGET_USD}
    ledger = Ledger(spent=float(summary.get('spent_usd') or 0.0))
    post = poster() if (a.probe or a.control or a.replay) else None
    days = sessions()
    try:
        if a.probe:
            actual = actual_closes()
            for slug in slugs:
                summary.setdefault('probe', {})[slug] = probe(ORClient(MODELS[slug], post, ledger), actual)
        if a.control:
            for slug in slugs:
                summary.setdefault('control', {})[slug] = control(ORClient(MODELS[slug], post, ledger))
        if a.replay:
            for slug in slugs:
                if (summary.get('probe') or {}).get(slug, {}).get('contaminated'):
                    summary.setdefault('replay', {})[slug] = 'VOID: the model knows the period'
                    continue
                out = replay(slug, MODELS[slug], ORClient(MODELS[slug], post, ledger), days)
                summary.setdefault('replay', {})[slug] = {
                    k: sum(1 for v in out.values() if v.get('status') == k)
                    for k in ('READY', 'NO_OPPORTUNITY', 'UNAVAILABLE', 'NOT_ASKED')}
    finally:
        summary['spent_usd'] = round(ledger.spent, 4)
        summary['calls'] = summary.get('calls', 0) + ledger.calls
        SUMMARY.write_text(json.dumps(summary, indent=1, default=str))
    if a.analyse:
        summary['analysis'] = analyse([s for s in slugs if isinstance((summary.get('replay') or {}).get(s), dict)], days)
        for group, g in summary['analysis']['groups'].items():
            c = g['clustered']
            print('%-18s %3d picks  %5.1f%% right  mean %+.3f%%  t %s  placebo p %.3f  halves %s  -> %s' % (
                group, g['picks'], 100*g['hit_rate'], g['mean_r_pct'],
                'n/a' if c['t'] is None else '%+.2f' % c['t'], g['placebo_p_hit'],
                ['%+.3f' % h if h is not None else None for h in g['halves']],
                'PASS' if g['passes_registered_bar'] else 'FAIL'))
        SUMMARY.write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary.get(k) for k in ('probe', 'control', 'replay', 'spent_usd', 'calls')},
                     indent=1, default=str)[:4000])
    return 0


if __name__ == '__main__':
    sys.exit(main())
