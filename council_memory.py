#!/usr/bin/env python3
"""THE COUNCIL WITH MEMORY: a shadow beside the live council (day-130, step 3).

Registered in PREREGISTER_day130_memory.md before it ran.

Right after the live council seals, a second council sits on exactly the same
table:
* the same positions, evidence rows, seats and members (Claude through
  OpenRouter only);
* the same three rounds, the same frozen prompt and the same frozen tally.

The one difference is `memory` in the payload: the council's own Top 2 on the
last five recorded sessions (with how much of each move was its sector ETF),
and what each of today's positions moves with.

It never touches the live decision. It writes `council_memory.json` only; the
brief freezes it as `intraday.top_two_memory`, recorded as `top2memory/pick`.

    python council_memory.py --stage --state-dir .rb-state     after the live council, by 09:30
    python council_memory.py --control [--runs 5]              the planted control, with and without memory
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import io
import json
import os
import statistics as st
import sys
from pathlib import Path

import council as K

ROOT = Path(__file__).resolve().parent
ET = K.ET
SNAPSHOT = 'council_memory.json'
RULE_VERSION = 'day130-memory'
RECENT = 5
DEADLINE = dt.time(9, 30)
LEDGER = ROOT / 'data' / 'model_picks.csv'
LAB = ROOT / 'data' / 'reviews' / 'execution_lab.csv'
MEMORY_LEGEND = (
    "`memory` is this committee's own record: its Top 2 on the last recorded sessions, how each "
    "did from 09:45 to the close, how much of that move was its sector ETF, and what each of "
    "today's positions moves with. It is history, not a forecast, and not an instruction; weigh "
    "it like any other row.")


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _read(path):
    path = Path(path)
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text())))


# ── the memory box ───────────────────────────────────────────────────────────

def memory(session, table, *, picks=None, lab=None, sectors=None, n=RECENT):
    """The registered box: `recent`, `summary`, `exposure`. Pure given its inputs."""
    import exposure as X
    picks = _read(LEDGER) if picks is None else picks
    lab = _read(LAB) if lab is None else lab
    top = [r for r in picks if r.get('model') == 'top2' and r.get('kind') == 'pick'
           and r.get('session', '') < session]
    sessions = sorted({r['session'] for r in top})[-n:]
    labs = {(r.get('session'), r.get('side'), r.get('ticker')): r for r in lab
            if r.get('model') == 'top2' and r.get('kind') == 'pick'}
    recent, raw = [], []
    for r in sorted((r for r in top if r['session'] in sessions),
                    key=lambda r: (r['session'], r['side'], r['ticker'])):
        x = {'session': r['session'], 'position': '%s %s' % (r['side'], r['ticker'])}
        ret = _num(r.get('r_pct'))
        if ret is None:
            x['result'] = 'not scored yet'
            recent.append(x)
            continue
        x['r_pct'] = round(ret, 2)
        x['result'] = 'right' if ret > 0 else 'wrong'
        raw.append((ret, None))
        if r.get('invalidated') in ('0', '1'):
            x['wrong_if_hit'] = r['invalidated'] == '1'
        lr = labs.get((r['session'], r['side'], r['ticker'])) or {}
        own = _num(lr.get('r_vs_etf'))
        if lr.get('etf') and own is not None:
            x['sector_etf'] = lr['etf']
            x['sector_part_pct'] = round(ret - own, 2)
            x['own_part_pct'] = round(own, 2)
            raw[-1] = (ret, own)
        recent.append(x)
    if raw:
        parts = [(r, o) for r, o in raw if o is not None]
        summary = ('Last %d recorded sessions: %d of %d picks right, mean %+.2f%% from 09:45 to the '
                   'close' % (len(sessions), sum(r > 0 for r, _ in raw), len(raw),
                              st.mean(r for r, _ in raw)))
        if parts:
            summary += ('; the sector ETF\'s part of the move averaged %+.2f%%, the picks\' own '
                        'part %+.2f%%' % (st.mean(r - o for r, o in parts), st.mean(o for _, o in parts)))
        summary += '.'
    else:
        summary = 'No scored Top 2 on the last recorded sessions.'
    expo = []
    for p in table:
        e = X.position_exposure(p['ticker'], sectors)
        expo.append({'id': p['id'], 'position': '%s %s' % (p['side'], p['ticker']),
                     'sector': e['sector'], 'moves_with': e['etf'],
                     **({'in_effect_a_bet_on': e['driver']} if e['driver'] else {})})
    return {'recent': recent, 'summary': summary, 'exposure': expo}


# ── the rounds (the live council's, read-only; nothing here is shared state) ──

def deliberate(table, rows, dates, seat, *, extra=None, clients=None, claude_post=None,
               jev_poster=None, live=True):
    """Round 1 (DeepSeek, Gemini blind), Claude and Jev after reading it, Round 2
    (DeepSeek, Gemini final), then the frozen tally. `extra` is added to every
    member's payload and to Jev's state; None is the live council's payload."""
    clients = clients or {}
    extra = extra or {}
    pub = K.public(table)
    ids = [p['id'] for p in table]
    errors = {}

    def run(member, fn):
        try:
            return member, fn()
        except Exception as exc:          # counted in `errors`, never swallowed
            errors[member] = (str(exc) if (str(exc).isupper() or isinstance(exc, ValueError))
                              else type(exc).__name__)[:80]
            return member, None

    def payload(discussion=None):
        p = {'positions': pub, 'rows': rows, 'evidence_legend': K.EVIDENCE_LEGEND,
             'data_dates': dates, **extra}
        if discussion is not None:
            p['discussion'] = discussion
        return json.dumps(p, ensure_ascii=False, sort_keys=True)

    def chat(member, note, discussion=None):
        user, system = payload(discussion), K.prompt(member, note)
        for attempt in (1, 2):        # ONE retry of an invalid ballot, as live
            reply = (K.ask_deepseek(system, user, client=clients.get('deepseek'))
                     if member == 'DeepSeek' else
                     K.ask_gemini(system, user, client=clients.get('gemini')))
            try:
                return K.parse_ballot(reply, ids)
            except ValueError:
                if attempt == 2:
                    raise

    with cf.ThreadPoolExecutor(2) as pool:
        r1 = dict(pool.map(lambda m: run('R1 ' + m, lambda: chat(m, K.ROUND_1)), ['DeepSeek', 'Gemini']))
    round1 = {m.split(' ', 1)[1]: b for m, b in r1.items() if b}
    discussion1 = K.discussion_of(round1, seat)

    def claude_or():
        return K.parse_ballot(K.ask_claude_openrouter(K.prompt('Claude', K.ROUND_2), payload(discussion1),
                                                      post=claude_post), ids)
    with cf.ThreadPoolExecutor(2) as pool:
        jev_f = pool.submit(run, 'Jev', lambda: K.ask_jev(table, rows, discussion1, poster=jev_poster,
                                                         extra=extra or None))
        cl_f = (pool.submit(run, 'Claude (OpenRouter)', claude_or)
                if (live or claude_post is not None) else None)
        _, jev = jev_f.result()
        claude = cl_f.result()[1] if cl_f else None
    heard = dict(round1)
    if claude:
        heard['Claude'] = claude
    if jev:
        heard['Jev'] = jev
    discussion2 = K.discussion_of(heard, seat)
    with cf.ThreadPoolExecutor(2) as pool:
        r2 = dict(pool.map(lambda m: run('R2 ' + m, lambda: chat(m, K.ROUND_2, discussion2)),
                           ['DeepSeek', 'Gemini']))
    finals = {}
    for m in ('DeepSeek', 'Gemini'):
        finals[m] = r2.get('R2 ' + m) or round1.get(m)
        if not r2.get('R2 ' + m) and round1.get(m):
            why = errors.get('R2 ' + m)
            errors['R2 ' + m] = 'kept its round-1 ballot' + (' (%s)' % why if why else '')
    finals['Claude'], finals['Jev'] = claude, jev
    result = K.tally(table, finals)
    agreed = [r for r in result['rows'] if r['consensus']][:K.PICKS]
    status = ('UNAVAILABLE' if len(result['members']) < 2
              else 'READY' if agreed else 'NO_CONSENSUS')
    return {'status': status, 'picks': [r['id'] for r in agreed], 'tally': result,
            'rounds': {'round1': round1, 'claude': claude, 'jev': jev,
                       'round2': {m: r2.get('R2 ' + m) for m in ('DeepSeek', 'Gemini')}},
            'errors': errors}


# ── staging (morning_full.sh, after the live council) ────────────────────────

def _brief(root, session):
    obj = json.loads((Path(root) / K.BRIEF_JSON).read_text())
    if obj.get('session') != session:
        raise ValueError('the council brief is not today\'s')
    return obj


def stage(state_dir, *, now=None, clock=None, clients=None, claude_post=None, jev_poster=None,
          picks=None, lab=None, sectors=None):
    """Sit the memory council on the live council's table. Never raises past
    its own failures; always writes council_memory.json with a status."""
    clock = clock or (lambda: dt.datetime.now(ET))
    now = K._now(now or clock())
    root = Path(state_dir)
    session = now.date().isoformat()
    base = {'variant': 'memory', 'rule_version': RULE_VERSION, 'prompt_version': K.PROMPT_VERSION,
            'session': session, 'asked_at': now.isoformat()}

    def done(status, reason, **more):
        out = {**base, 'status': status, 'picks': [], 'reason': reason, **more}
        K._write(root / SNAPSHOT, out)
        return out
    if now.time() >= DEADLINE:
        return done('SKIPPED', 'too close to the open (after 09:30 ET)')
    live = K.load(root, now)
    table = live.get('positions') or []
    if live.get('status') not in ('READY', 'NO_CONSENSUS', 'UNAVAILABLE') or not table:
        return done('NO_TABLE', 'the live council had no table today (%s)' % live.get('status'))
    try:
        brief = _brief(root, session)
    except Exception as exc:
        return done('NO_TABLE', 'the council brief is unreadable (%s)' % type(exc).__name__)
    import gemini_opportunities as G
    import jev_opportunities as J
    for loader in (lambda: __import__('prepare_deepseek').load_private_key(root),
                   lambda: J.load_private_key(root), lambda: G.load_private_key(root)):
        try:
            loader()
        except Exception:      # a missing key costs that member only, named in errors
            pass
    try:
        mem = memory(session, table, picks=picks, lab=lab, sectors=sectors)
    except Exception as exc:
        return done('UNAVAILABLE', 'the memory box could not be built (%s)' % type(exc).__name__)
    extra = {'memory': mem, 'memory_legend': MEMORY_LEGEND}
    out = deliberate(table, brief['rows'], brief.get('data_dates'), live.get('seats') or {},
                     extra=extra, clients=clients, claude_post=claude_post, jev_poster=jev_poster,
                     live=not clients)
    snap = {**base, 'positions': table, 'seats': live.get('seats'), 'lead_order': live.get('lead_order'),
            'memory': mem, **out, 'live_picks': live.get('picks') or [],
            'moves': live.get('moves') or {},     # day-135c: the same big-mover switch as the live council
            'finished_at': K._now(clock()).isoformat(),
            'reason': (None if out['picks'] else
                       'fewer than two members cast a valid ballot' if out['status'] == 'UNAVAILABLE'
                       else 'no position won most of the council after two rounds')}
    K._write(root / SNAPSHOT, snap)
    return snap


def load(state_dir, now):
    try:
        obj = json.loads((Path(state_dir) / SNAPSHOT).read_text())
    except (OSError, ValueError):
        return None
    return obj if obj.get('session') == K._now(now).date().isoformat() else None


def section(snap, *, prices=None):
    """The shadow's Top 2, in the Top 2 section's shape, with the same 09:46 check."""
    if not isinstance(snap, dict) or snap.get('status') not in ('READY', 'NO_CONSENSUS'):
        return None
    out = K.top_two(snap, None, prices=prices, previous={})
    import entry_checks
    out['rule_version'] = (RULE_VERSION + ('+' + K.MOVER_RULE if K.SKIP_MOVERS else '')
                           + ('+' + entry_checks.RULE_VERSION if prices is not None else ''))
    out['shadow'] = True
    return out


# ── the evening readout ──────────────────────────────────────────────────────

def _day_pnl(rows):
    vals = [_num(r.get('r_pct')) for r in rows]
    vals = [v for v in vals if v is not None]
    return st.mean(vals) if vals else 0.0


def comparison(picks=None):
    """The registered paired readout: per session, each arm's mean r_pct (0 with
    no picks), d = memory - live, over sessions where the shadow was recorded
    and every pick of both arms is scored."""
    picks = _read(LEDGER) if picks is None else picks
    by = {}
    for r in picks:
        if r.get('kind') == 'pick' and r.get('model') in ('top2', 'top2memory'):
            by.setdefault(r['session'], {}).setdefault(r['model'], []).append(r)
    shadow_days = sorted(s for s, v in by.items() if 'top2memory' in v)
    days = []
    for s in shadow_days:
        arms = by[s]
        if any(_num(r.get('r_pct')) is None for v in arms.values() for r in v):
            continue
        days.append({'session': s, 'live': _day_pnl(arms.get('top2', [])),
                     'memory': _day_pnl(arms.get('top2memory', [])),
                     'same': ({(r['side'], r['ticker']) for r in arms.get('top2', [])}
                              == {(r['side'], r['ticker']) for r in arms.get('top2memory', [])})})
    d = [x['memory'] - x['live'] for x in days]
    t = (st.mean(d) / (st.stdev(d) / len(d) ** 0.5)) if len(d) >= 3 and st.stdev(d) else None
    return {'days': len(days), 'mean_d': round(st.mean(d), 3) if d else None,
            't': None if t is None else round(t, 2), 'same_days': sum(x['same'] for x in days),
            'rows': days}


def review_lines(session, report=None, picks=None):
    """The evening review's shadow section: today's two councils, then the record."""
    out = ['## The council with memory (shadow, day-130)',
           'A second council sits on the same table with its own last five sessions in front of it. '
           'It decides nothing; it is recorded to be compared at 20 and 40 sessions '
           '(PREREGISTER_day130_memory.md).']
    i = (report or {}).get('intraday') or {}
    live = [(p['side'], p['ticker']) for p in (i.get('top_two') or {}).get('picks') or []]
    mem = i.get('top_two_memory')
    if mem is None:
        snap = i.get('council_memory') or {}
        out.append('Today: the memory council did not sit (%s).' % (snap.get('reason') or 'not staged'))
    else:
        shown = ', '.join('%s %s' % x for x in [(p['side'], p['ticker']) for p in mem.get('picks') or []])
        out.append('Today: live %s; with memory %s.' % (', '.join('%s %s' % x for x in live) or 'no pick',
                                                       shown or 'no pick'))
    c = comparison(picks)
    if c['days']:
        out.append('Record: %d scored sessions, the same picks on %d; memory − live %+.2f%% per session'
                   '%s. A verdict needs 20 sessions (harm) and 40 (t ≥ 3).'
                   % (c['days'], c['same_days'], c['mean_d'],
                      '' if c['t'] is None else ', t = %.2f' % c['t']))
    else:
        out.append('Record: no scored session with both councils yet.')
    return out


# ── the planted control (house rule 4) ───────────────────────────────────────

def control_table(session):
    """The day-110 planted universe as a council table: the planted long and short
    proposed with a desk's confidence and reason, four noise positions beside them."""
    import deepseek_opportunities as O
    seat = K.seats(session)
    now = dt.datetime.fromisoformat(session + 'T09:05').replace(tzinfo=ET)
    req = O.build_request(O.control_universe(), None, now)
    rows = {r['ticker']: r for r in req['payload']['candidates']}

    def pos(i, ticker, side, model, conf, reason, how='selected'):
        return {'id': 'P%d' % i, 'ticker': ticker, 'side': side, 'lead': K.NAMES[model],
                'reason': reason, 'invalid_at': None,
                'proposers': [{'model': model, 'how': how, 'confidence': conf,
                               'reason': reason, 'invalid_at': None, 'seat': seat[model]}]}
    table = [
        pos(1, O.CONTROL_LONG, 'LONG', 'deepseek', 0.70,
            'r0 +2.9% on rvol 3.1, holding above vwap 41.60 and the opening-range high 41.90, '
            'rsi 64 and a rising macd histogram.'),
        pos(2, O.CONTROL_SHORT, 'SHORT', 'gemini', 0.66,
            'r0 -2.7% on rvol 2.95, below vwap 19.05 and the opening-range low 18.55, rsi 27 '
            'and a falling macd histogram.'),
        pos(3, 'NOIS1.TO', 'LONG', 'claude', 0.52, 'flat open, rsi 49, nothing decisive.'),
        pos(4, 'NOIS3.TO', 'SHORT', 'gemini', 0.51, 'slightly below vwap, rvol 1.0.'),
        pos(5, 'NOIS6.TO', 'LONG', 'jev', 0.40, None, how='forced'),
        pos(6, 'NOIS8.TO', 'SHORT', 'claude', 0.52, 'tiny negative r0, nothing else.'),
    ]
    return table, [rows[p['ticker']] for p in table]


def control_memory(table):
    """A losing record, all sector-driven: the stress the registration names."""
    recent = []
    for i, (side, ticker) in enumerate((('SHORT', 'CVE.TO'), ('LONG', 'CCO.TO'), ('SHORT', 'CVE.TO'),
                                        ('SHORT', 'TD.TO'), ('LONG', 'SU.TO'))):
        recent.append({'session': '2026-09-%02d' % (21 + i), 'position': '%s %s' % (side, ticker),
                       'r_pct': -1.1, 'result': 'wrong', 'wrong_if_hit': i % 2 == 0,
                       'sector_etf': 'XEG.TO', 'sector_part_pct': -1.3, 'own_part_pct': 0.2})
    return {'recent': recent,
            'summary': ('Last 5 recorded sessions: 0 of 5 picks right, mean -1.10% from 09:45 to the '
                        'close; the sector ETF\'s part of the move averaged -1.30%, the picks\' own part '
                        '+0.20%.'),
            'exposure': [{'id': p['id'], 'position': '%s %s' % (p['side'], p['ticker']),
                          'sector': None, 'moves_with': 'XIU.TO'} for p in table]}


def control(runs=5, *, with_memory=True, **kw):
    import deepseek_opportunities as O
    session = '2026-09-17'
    now = dt.datetime(2026, 9, 17, 9, 5, tzinfo=ET)
    table, rows = control_table(session)
    dates = O.data_dates(now, O.prior_session(now.date()))
    extra = ({'memory': control_memory(table), 'memory_legend': MEMORY_LEGEND} if with_memory else None)
    results = []
    for _ in range(runs):
        out = deliberate(table, rows, dates, K.seats(session), extra=extra, **kw)
        agreed = {(r['side'], r['ticker']) for r in out['tally']['rows'] if r['consensus']}
        clean = agreed == {('LONG', O.CONTROL_LONG), ('SHORT', O.CONTROL_SHORT)}
        results.append({'clean': clean, 'consensus': sorted('%s %s' % x for x in agreed),
                        'members': out['tally']['members'], 'errors': out['errors']})
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--state-dir', default=os.environ.get('RB_STATE_DIR', '.rb-state'))
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--stage', action='store_true')
    g.add_argument('--control', action='store_true')
    p.add_argument('--runs', type=int, default=5)
    a = p.parse_args(argv)
    if a.stage:
        out = stage(a.state_dir)
        print(json.dumps({k: out.get(k) for k in ('status', 'picks', 'live_picks', 'reason', 'errors')},
                         sort_keys=True))
        return 0 if out['status'] in ('READY', 'NO_CONSENSUS') else 2
    import gemini_opportunities as G
    import jev_opportunities as J
    import prepare_deepseek
    for loader in (prepare_deepseek.load_private_key, J.load_private_key, G.load_private_key):
        loader(a.state_dir)
    ok = True
    for arm in (True, False):
        res = control(a.runs, with_memory=arm)
        clean = sum(r['clean'] for r in res)
        print(json.dumps({'memory': arm, 'clean': clean, 'of': len(res), 'runs': res}, sort_keys=True))
        if arm:
            ok = clean * 5 >= 4 * len(res)          # the registered bar: 4 clean of 5
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
