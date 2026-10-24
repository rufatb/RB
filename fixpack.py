#!/usr/bin/env python3
"""DAY-140 — THE FIX PACK, IN SHADOW (PREREGISTER_day140_fixpack.md).

Two registered questions about the council's Top 2, judged on the record,
and a few facts recorded beside them. Nothing here is sized, shown in the
email, fed to a member, or run in the morning; a failure costs this test
only.

  A. A STOP WITHIN REACH. Each live Top 2 pick is KEPT when its own "wrong
     if" is within one normal day (council_flash.REACH_ATR) of the 09:45
     entry, and DROPPED when it has none or one out of reach — the open
     check's own rule (day-135). Judged: are the dropped picks worse?
  B. ROUND 1 AGAINST THE DELIBERATED COUNCIL. The two blind Round-1 ballots
     (DeepSeek, Gemini) tallied alone by the frozen rule, against the
     council's own picks before the pass-over rules. Judged, both ways:
     does the discussion change the result?

Recorded, never judged: two same-side picks in one sector fund (the sector
cap), a dated catalyst (earnings within 5 sessions, an issuer release in
the wire window), and whether a pick carried any level at all.

The ledger, data/reviews/fixpack.csv (the evening push carries it), holds
decisions only. Every outcome is read from data/model_picks.csv, the
record's one yardstick: the 09:45 bar's close to the close.

    python fixpack.py --session 2026-10-26          # record one session (the review does it)
    python fixpack.py --backfill .rb-state/reports.sqlite3   # 10-05 → 10-23, period 'before'
    python fixpack.py --verdict                     # the registered decision
    python fixpack.py --line                        # the running record
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import io
import json
import math
import os
import random
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'reviews' / 'fixpack.csv'
STATE = ROOT / '.rb-state'
START = '2026-10-26'            # the first registered session; earlier rows are 'before'
COST = 0.13
DECISION = 40
FINAL = 80
BAR = 3.0
PLACEBO_P = 0.01
DRAWS = 2000
SEED = 140
MIN_GROUP = 10
CATALYST_SESSIONS = 5
MAX_PICKS = 2
TABLE_KINDS = ('selected', 'nominated', 'forced', 'pick')     # daily_review.TABLE_KINDS

FIELDS = ('session', 'period', 'kind', 'ticker', 'side', 'etf', 'invalid_at', 'entry',
          'atr_pct', 'reach_atr', 'gate', 'reason', 'earnings_days', 'wire_release', 'rank',
          'recorded_at')
KEY = ('session', 'kind', 'ticker', 'side')


# ── the ledger (decisions only; a rerun fills blanks, never rewrites) ───────

def read(path=LEDGER):
    path = Path(path)
    return list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []


def _write(rows, path=LEDGER):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore')
    w.writeheader()
    for r in sorted(rows, key=lambda r: tuple(str(r.get(k) or '') for k in KEY)):
        w.writerow({k: '' if r.get(k) is None else r.get(k) for k in FIELDS})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    try:
        with open(tmp, 'w', newline='') as f:
            f.write(out.getvalue())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _merge(new_rows, path=LEDGER):
    """Append new keys; on a known key fill empty cells only. Returns how many
    rows were added and how many cells filled."""
    rows = read(path)
    at = {tuple(r.get(k) or '' for k in KEY): r for r in rows}
    added = filled = 0
    for n in new_rows:
        n = {k: '' if n.get(k) is None else str(n[k]) for k in FIELDS}
        old = at.get(tuple(n[k] for k in KEY))
        if old is None:
            rows.append(n)
            at[tuple(n[k] for k in KEY)] = n
            added += 1
            continue
        for k in FIELDS:
            if (old.get(k) or '') == '' and n[k] != '':
                old[k] = n[k]
                filled += 1
    if added or filled:
        _write(rows, path)
    return added, filled


# ── the gate and the two arms' picks (pure) ─────────────────────────────────

def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def gate(side, invalid_at, entry, atr_pct):
    """(gate, reason, reach_atr) for one live pick: 'kept', 'dropped', or ''
    while the entry or the ATR is not known yet (a later run fills it)."""
    import council_flash as CF
    level = _num(invalid_at)
    if level is None or level <= 0:
        return 'dropped', 'no wrong-if', None
    entry, atr_pct = _num(entry), _num(atr_pct)
    if entry is None:
        return '', 'not scored yet', None
    if atr_pct is None or atr_pct <= 0:
        return '', 'no ATR for the name', None
    got = CF.reach(side, level, entry, atr_pct)
    if got is None:
        return 'dropped', 'wrong-if already crossed at the 09:45 entry', None
    days = round(got['days'], 3)
    if got['out_of_reach']:
        return 'dropped', 'wrong-if %.1f normal days away' % days, days
    return 'kept', '', days


def round1_picks(council):
    """The Round-1 Top 2: the frozen tally over the two blind ballots alone.
    A position needs both to endorse it and neither to oppose; never padded."""
    import council as K
    table = council.get('positions') or []
    round1 = ((council.get('rounds') or {}).get('round1')) or {}
    if not table or not isinstance(round1, dict):
        return []
    rows = K.tally(table, round1)['rows']
    by_id = {p['id']: p for p in table}
    return [by_id[r['id']] for r in rows if r.get('consensus')][:MAX_PICKS]


def final_picks(council):
    """The council's own picks, in its order, BEFORE the pass-over rules."""
    by_id = {p['id']: p for p in council.get('positions') or []}
    return [by_id[i] for i in council.get('picks') or [] if i in by_id][:MAX_PICKS]


# ── recording a session (the evening review) ────────────────────────────────

def _period(session):
    return 'test' if str(session) >= START else 'before'


def _brief_rows(state_dir, session):
    """{ticker: row} from the morning's brief, or {} when it is not this session's."""
    import claude_opportunities as C
    try:
        now = dt.datetime.combine(dt.date.fromisoformat(session), dt.time(16, 0), tzinfo=ET)
        rows = C.read_brief(state_dir, now)['payload']['candidates']
    except Exception:
        return {}
    return {r['ticker']: r for r in rows if isinstance(r.get('ticker'), str)}


def _wire(session, archive=None):
    """Tickers with an issuer release in the session's wire window (day-122's rule)."""
    import news_desk
    try:
        return set(news_desk.candidates(dt.date.fromisoformat(session), archive=archive))
    except Exception:
        return None


def record_session(session, report=None, *, picks_rows=None, brief=None, atr=None,
                   archive=None, sectors=None, path=LEDGER, state_dir=STATE, now=None):
    """Record one session's decisions. `report` is the frozen publication (its
    council feeds arm B); the live picks are the record's top2/pick rows."""
    import exposure
    import model_picks as M
    now = now or dt.datetime.now(ET)
    rows = M.read() if picks_rows is None else picks_rows
    brief = _brief_rows(state_dir, session) if brief is None else brief
    council = ((report or {}).get('intraday') or {}).get('council')
    council = council if isinstance(council, dict) else {}
    moves = council.get('moves') if isinstance(council.get('moves'), dict) else {}
    # The morning brief's ATR first (the rows every model read), then the
    # frozen council's copy of it, then `atr` (daily bars, for the backfill).
    atr = {t: a for t, a in (atr or {}).items() if _num(a) is not None}
    for source in ({t: (m or {}).get('atr_pct') for t, m in moves.items() if isinstance(m, dict)},
                   {t: r.get('atr_pct') for t, r in brief.items()}):
        atr.update({t: _num(a) for t, a in source.items() if _num(a) is not None})
    sectors = exposure.load_sectors() if sectors is None else sectors
    wire = _wire(session, archive)
    period = _period(session)
    stamp = now.isoformat(timespec='seconds')

    def base(kind, ticker, side, rank):
        days = _num((brief.get(ticker) or {}).get('days_to_earnings'))
        return {'session': session, 'period': period, 'kind': kind, 'ticker': ticker,
                'side': side, 'rank': rank, 'recorded_at': stamp,
                'etf': exposure.position_exposure(ticker, sectors)['etf'],
                'earnings_days': '' if days is None else int(days),
                'wire_release': '' if wire is None else int(ticker in wire)}

    out = []
    live = [r for r in rows if r.get('session') == session and r.get('model') == 'top2'
            and r.get('kind') == 'pick']
    for i, r in enumerate(live, 1):
        g, why, days = gate(r['side'], r.get('invalid_at'), r.get('entry'), atr.get(r['ticker']))
        out.append({**base('live', r['ticker'], r['side'], i),
                    'invalid_at': _num(r.get('invalid_at')), 'entry': _num(r.get('entry')),
                    'atr_pct': atr.get(r['ticker']), 'reach_atr': days, 'gate': g,
                    'reason': why})
    for kind, chosen in (('round1', round1_picks(council)), ('final', final_picks(council))):
        for i, p in enumerate(chosen, 1):
            out.append({**base(kind, p['ticker'], p['side'], i),
                        'invalid_at': _num(p.get('invalid_at'))})
    added, filled = _merge(out, path) if out else (0, 0)
    return {'session': session, 'period': period, 'live': len(live),
            'round1': sum(1 for r in out if r['kind'] == 'round1'),
            'final': sum(1 for r in out if r['kind'] == 'final'),
            'council': bool(council), 'added': added, 'filled': filled}


# ── outcomes, from the record ───────────────────────────────────────────────

def outcomes(rows=None):
    """{(session, ticker, side): r_pct} from every scored table row (09:45 → close)."""
    import model_picks as M
    rows = M.read() if rows is None else rows
    out = {}
    for r in rows:
        if r.get('kind') in TABLE_KINDS and _num(r.get('r_pct')) is not None:
            out.setdefault((r['session'], r['ticker'], r['side']), _num(r['r_pct']))
    return out


def _scored(path, outs, period):
    """[(session, kind, row, y)] for one period's rows with a known outcome."""
    out = []
    for r in read(path):
        if r.get('period') != period:
            continue
        y = outs.get((r['session'], r['ticker'], r['side']))
        if y is not None:
            out.append((r['session'], r['kind'], r, y))
    return out


# ── the statistics (pure) ───────────────────────────────────────────────────

def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def two_group(picks):
    """picks: [(session, y, kept)] -> (kept mean - dropped mean, its
    session-clustered t). Each pick sits in its session's cluster."""
    k = [y for _, y, g in picks if g]
    d = [y for _, y, g in picks if not g]
    if not k or not d:
        return None, None
    mk, md = _mean(k), _mean(d)
    diff = mk - md
    score = collections.defaultdict(float)
    for s, y, g in picks:
        score[s] += (y - mk) / len(k) if g else -(y - md) / len(d)
    n = len(score)
    if n < 3:
        return diff, None
    var = n / (n - 1) * sum(v * v for v in score.values())
    return diff, (diff / math.sqrt(var) if var > 0 else None)


def _halves(sessions_rows, stat):
    half = len(sessions_rows) // 2
    return [stat(sessions_rows[:half]), stat(sessions_rows[half:])]


def arm_a(picks, *, draws=DRAWS, seed=SEED):
    """picks: [(session, y, kept)] for one look's sessions."""
    diff, t = two_group(picks)
    by = collections.defaultdict(list)
    for p in picks:
        by[p[0]].append(p)
    order = [by[s] for s in sorted(by)]
    halves = _halves(order, lambda part: two_group([p for ps in part for p in ps])[0])
    labels = [g for _, _, g in picks]
    ys = [y for _, y, _ in picks]
    rng = random.Random(seed)
    hits = 0
    for _ in range(draws):
        rng.shuffle(labels)
        k = [y for y, g in zip(ys, labels) if g]
        d = [y for y, g in zip(ys, labels) if not g]
        if k and d and diff is not None and _mean(k) - _mean(d) >= diff:
            hits += 1
    p = hits / draws if diff is not None else None
    kept = sum(1 for g in labels if g)
    groups_ok = kept >= MIN_GROUP and len(labels) - kept >= MIN_GROUP
    passed = (diff is not None and diff > 0 and t is not None and t >= BAR and p < PLACEBO_P
              and all(h is not None and h > 0 for h in halves) and groups_ok)
    status = 'PASS' if passed else 'FAIL' if diff is not None and diff <= 0 else 'UNDERPOWERED'
    return {'status': status, 'diff': diff, 't': t, 'placebo_p': p, 'halves': halves,
            'kept': kept, 'dropped': len(labels) - kept, 'sessions': len(order),
            'kept_mean': _mean([y for _, y, g in picks if g]),
            'dropped_mean': _mean([y for _, y, g in picks if not g])}


def arm_b(ds, *, draws=DRAWS, seed=SEED):
    """ds: [d] per qualifying session, in date order."""
    m = _mean(ds)
    t = None
    if len(ds) > 2:
        sd = math.sqrt(sum((x - m) ** 2 for x in ds) / (len(ds) - 1))
        t = m / (sd / math.sqrt(len(ds))) if sd else None
    halves = _halves(ds, _mean)
    rng = random.Random(seed)
    hits = sum(1 for _ in range(draws)
               if abs(_mean([x if rng.random() < 0.5 else -x for x in ds])) >= abs(m))
    p = hits / draws
    passed = (t is not None and abs(t) >= BAR and p < PLACEBO_P
              and all(h is not None and h * m > 0 for h in halves))
    return {'status': ('ADDS' if m > 0 else 'SUBTRACTS') if passed else 'UNDERPOWERED',
            'mean': m, 't': t, 'placebo_p': p, 'halves': halves, 'sessions': len(ds),
            'same': sum(1 for x in ds if x == 0)}


# ── the arms on the ledger ──────────────────────────────────────────────────

def a_picks(path=LEDGER, outs=None, period='test'):
    outs = outcomes() if outs is None else outs
    return sorted((s, y, r['gate'] == 'kept') for s, kind, r, y in _scored(path, outs, period)
                  if kind == 'live' and r.get('gate') in ('kept', 'dropped'))


def b_sessions(path=LEDGER, outs=None, period='test'):
    """[(session, d, round1 picks, final picks)] where both arms hold a scored pick."""
    outs = outcomes() if outs is None else outs
    arms = collections.defaultdict(lambda: collections.defaultdict(list))
    for s, kind, r, y in _scored(path, outs, period):
        if kind in ('round1', 'final'):
            arms[s][kind].append((r['side'], r['ticker'], y))
    out = []
    for s in sorted(arms):
        r1, fin = arms[s]['round1'], arms[s]['final']
        if r1 and fin:
            out.append((s, _mean([y for *_, y in fin]) - _mean([y for *_, y in r1]), r1, fin))
    return out


def verdict(path=LEDGER, outs=None, *, draws=DRAWS, seed=SEED):
    """The registered decision on both arms (PREREGISTER_day140_fixpack.md)."""
    outs = outcomes() if outs is None else outs
    picks = a_picks(path, outs)
    sessions = sorted({p[0] for p in picks})
    if len(sessions) < DECISION:
        a = {'status': 'NOT_DUE', 'sessions': len(sessions), 'picks': len(picks)}
    else:
        def at(n):
            keep = set(sessions[:n])
            return {**arm_a([p for p in picks if p[0] in keep], draws=draws, seed=seed),
                    'look': n}
        a = at(DECISION)
        if a['status'] == 'UNDERPOWERED' and len(sessions) >= FINAL:
            a = at(FINAL)
        a['final'] = a['status'] != 'UNDERPOWERED' or a['look'] == FINAL
    bs = b_sessions(path, outs)
    if len(bs) < DECISION:
        b = {'status': 'NOT_DUE', 'sessions': len(bs)}
    else:
        b = {**arm_b([d for _, d, *_ in bs[:DECISION]], draws=draws, seed=seed), 'look': DECISION}
        if b['status'] == 'UNDERPOWERED' and len(bs) >= FINAL:
            b = {**arm_b([d for _, d, *_ in bs[:FINAL]], draws=draws, seed=seed), 'look': FINAL}
            if b['status'] == 'UNDERPOWERED':
                b['status'] = 'NULL'
        b['final'] = b['status'] != 'UNDERPOWERED'
    return {'A': a, 'B': b}


def describe(path=LEDGER, outs=None, period='test'):
    """The recorded facts beside the arms, for one period. Never a verdict."""
    outs = outcomes() if outs is None else outs
    scored = _scored(path, outs, period)
    live = [(s, r, y) for s, kind, r, y in scored if kind == 'live']

    def split(test):
        yes = [y for _, r, y in live if test(r) is True]
        no = [y for _, r, y in live if test(r) is False]
        return {'yes': len(yes), 'yes_mean': _mean(yes), 'no': len(no), 'no_mean': _mean(no)}
    by_session = collections.defaultdict(list)
    for s, r, y in live:
        by_session[s].append((r, y))
    capped = [s for s, ps in by_session.items() if len(ps) == 2
              and ps[0][0]['side'] == ps[1][0]['side'] and ps[0][0]['etf'] == ps[1][0]['etf']]
    bs = b_sessions(path, outs, period)
    only = collections.defaultdict(list)
    for _, _, r1, fin in bs:
        a, b = {(x[0], x[1]) for x in r1}, {(x[0], x[1]) for x in fin}
        only['round1'] += [y for side, t, y in r1 if (side, t) not in b]
        only['final'] += [y for side, t, y in fin if (side, t) not in a]
    return {
        'period': period, 'live': len(live),
        'gate': split(lambda r: {'kept': True, 'dropped': False}.get(r.get('gate'))),
        'any_level': split(lambda r: _num(r.get('invalid_at')) is not None),
        'earnings': split(lambda r: None if r.get('earnings_days') in ('', None)
                          else 0 <= int(float(r['earnings_days'])) <= CATALYST_SESSIONS),
        'wire_release': split(lambda r: None if r.get('wire_release') in ('', None)
                              else r['wire_release'] == '1'),
        'cap_binds': len(capped),
        'b_sessions': len(bs), 'b_same': sum(1 for _, d, *_ in bs if d == 0),
        'b_mean': _mean([d for _, d, *_ in bs]),
        'round1_only': {'n': len(only['round1']), 'mean': _mean(only['round1'])},
        'final_only': {'n': len(only['final']), 'mean': _mean(only['final'])},
    }


# ── the review's lines ──────────────────────────────────────────────────────

def _pct(x):
    return '—' if x is None else '%+.2f%%' % x


def line(path=LEDGER, outs=None):
    outs = outcomes() if outs is None else outs
    v = verdict(path, outs)
    a, b = v['A'], v['B']
    d = describe(path, outs)
    ga = d['gate']
    parts = ['Fix pack (day-140 test): arm A, a stop within reach — kept %d picks %s, dropped %d '
             '%s, over %d session(s)' % (ga['yes'], _pct(ga['yes_mean']), ga['no'],
                                          _pct(ga['no_mean']), a.get('sessions', 0))]
    if a['status'] != 'NOT_DUE':
        parts.append('decision on the first %d: %s (kept minus dropped %s, t = %s, placebo p = '
                     '%.3f)' % (a['look'], a['status'], _pct(a['diff']),
                                'n/a' if a['t'] is None else '%.2f' % a['t'], a['placebo_p'] or 0))
    parts.append('arm B, Round 1 against the deliberated picks — %d session(s) with both, %d the '
                 'same, deliberated minus Round 1 %s a session' % (
                     d['b_sessions'], d['b_same'], _pct(d['b_mean'])))
    if b['status'] != 'NOT_DUE':
        parts.append('decision on the first %d: %s (t = %s, placebo p = %.3f)' % (
            b['look'], b['status'], 'n/a' if b['t'] is None else '%.2f' % b['t'], b['placebo_p']))
    return '; '.join(parts) + ('; each decided at %d sessions (PREREGISTER_day140_fixpack.md).'
                               % DECISION)


def section(session, report=None, path=LEDGER, *, state_dir=STATE, picks_rows=None):
    """The evening review's block: record today, then print it. Never raises."""
    try:
        got = record_session(session, report, picks_rows=picks_rows, path=path,
                             state_dir=state_dir)
        outs = outcomes(picks_rows)
        today = [r for r in read(path) if r['session'] == session]

        def one(r):
            y = outs.get((r['session'], r['ticker'], r['side']))
            return '%s %s %s' % (r['side'], r['ticker'], 'not scored' if y is None else _pct(y))
        live = [r for r in today if r['kind'] == 'live']
        out = ['', '## The fix pack, in shadow (day-140 test)',
               'Two questions about the Top 2, judged on the record (09:45 → close): does a pick '
               'whose stop is within one normal day beat one without, and does the discussion '
               'beat Round 1\'s two blind ballots? Not sized, not in the email.']
        if live:
            out.append('Today\'s Top 2 at the gate: ' + '; '.join(
                '%s — %s' % (one(r), 'kept' if r['gate'] == 'kept' else
                             ('dropped, %s' % r['reason']) if r['gate'] == 'dropped'
                             else 'not judged yet (%s)' % r['reason']) for r in live) + '.')
        else:
            out.append('Today\'s Top 2 held no pick.')
        if got['council']:
            r1 = [one(r) for r in today if r['kind'] == 'round1']
            fin = [one(r) for r in today if r['kind'] == 'final']
            out.append('Round 1 alone: %s. The deliberated council: %s.' % (
                ', '.join(r1) or 'no consensus', ', '.join(fin) or 'no consensus'))
        out.append(line(path, outs))
        return '\n'.join(out) + '\n'
    except Exception as exc:
        return f"\nThe fix-pack readout is unavailable ({type(exc).__name__}).\n"


# ── the councils before the test (descriptive) ──────────────────────────────

def backfill(db, path=LEDGER, *, chart=None, now=None):
    """Record the frozen councils before START as period 'before'. A name with
    no ATR in its frozen council gets one from daily bars cut before the
    session (daily_technicals, Yahoo); a failure leaves its gate unjudged."""
    import sqlite3
    import model_picks as M
    rows = M.read()
    con = sqlite3.connect(db)
    done = []
    for session, body in con.execute('select session, body from reports order by session'):
        if session >= START:
            continue
        report = json.loads(body)
        council = (report.get('intraday') or {}).get('council')
        live = [r for r in rows if r.get('session') == session and r.get('model') == 'top2'
                and r.get('kind') == 'pick']
        if not isinstance(council, dict) and not live:
            continue
        frozen = (council or {}).get('moves') or {}
        atr = {r['ticker']: _bars_atr(r['ticker'], session, chart) for r in live
               if _num((frozen.get(r['ticker']) or {}).get('atr_pct')) is None}
        done.append(record_session(session, report, picks_rows=rows, brief={}, atr=atr,
                                   path=path, now=now))
    return done


def _bars_atr(ticker, session, chart=None):
    """ATR as % of the last close before `session`, from daily bars (the
    brief's own computation), or None."""
    import daily_technicals
    import news_desk
    try:
        _, frame = (chart or news_desk.daily_chart)(ticker)
        day = dt.date.fromisoformat(session)
        f = frame[[i.date() < day for i in frame.index]]
        got = daily_technicals.from_series(
            [i.date() for i in f.index], list(f['Close']), list(f['Volume']),
            now=dt.datetime.combine(day, dt.time(9, 0), tzinfo=ET),
            opens=list(f['Open']), highs=list(f['High']), lows=list(f['Low']))
        return _num((got or {}).get('atr_pct'))
    except Exception:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--session')
    p.add_argument('--report', default=str(STATE / 'latest' / 'report.json'))
    p.add_argument('--backfill', metavar='DB')
    p.add_argument('--verdict', action='store_true')
    p.add_argument('--line', action='store_true')
    a = p.parse_args(argv)
    if a.backfill:
        print(json.dumps(backfill(a.backfill), indent=1))
        return 0
    if a.session:
        report = json.loads(Path(a.report).read_text())
        if report.get('session') != a.session:
            print('the report is for %s, not %s' % (report.get('session'), a.session),
                  file=sys.stderr)
            return 2
        print(json.dumps(record_session(a.session, report)))
        return 0
    if a.verdict:
        print(json.dumps(verdict(), indent=1, default=str))
        return 0
    if a.line:
        print(line())
        return 0
    p.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
