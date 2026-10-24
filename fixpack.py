#!/usr/bin/env python3
"""DAY-140 — THE FIX PACK, IN SHADOW (PREREGISTER_day140_fixpack.md).

Three changes to how the Top 2 is chosen, run in shadow against the live
council and judged paired against it at 40 sessions. Nothing here is sized,
nothing here is in the live Top 2, nothing here is fed to a member or shown
in the morning email. A failure here costs this test only.

  1. ABSTENTION IS A FIRST-CLASS OUTCOME. A position may enter the shadow
     Top 2 only if its proposal carries (a) a dated, stock-specific
     catalyst — operationalised as the name's earnings falling within
     CATALYST_SESSIONS sessions in the morning's own evidence rows
     (`days_to_earnings`, the dates the desks themselves read) — and
     (b) a machine-checkable wrong-if: the numeric `invalid_at` a proposer
     recorded on the position. A position with neither is an abstention,
     recorded with its reason; the shadow Top 2 may hold 0, 1 or 2.
  2. ROUND-1 BALLOTS ARE FROZEN AND SCORED. The blind Round-1 ballots
     (DeepSeek and Gemini, cast before any discussion) are sealed by
     council.stage into `round1.json` at the moment they are cast, copied
     here vote by vote, and tallied on their own with the council's own
     registered rule (`council.tally`) into a Round-1 Top 2 that is scored
     on the same yardstick as the final. The evening review prints the
     deliberation delta: final minus Round-1, per session.
  3. SECTOR-NEUTRAL RANKING. Shadow candidates are ranked by the strength
     of their independent support — proposers who SELECTED the position,
     then their mean confidence, then how far the name's own move runs
     ahead of its sector (`rel_sector_pct`, the stock-specific part) —
     and the shadow Top 2 holds at most one position per sector per side.

THE MEASURE (registered): y = side x (the stock's open -> close minus
XIU's open -> close), in %, minus the 0.13% round trip — news_desk's
`w_day` yardstick, one basis for every arm (shadow, live, Round-1). The
live arm is the council's sealed picks; sessions where the shadow holds
nothing count as y = 0 for the shadow (standing aside is a result).

    python fixpack.py --stage --state-dir .rb-state   # after the council sits
    python fixpack.py --score                          # evening: fill y
    python fixpack.py --line                           # the running record
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
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'fixpack_shadow.csv'
ROUND1_LEDGER = ROOT / 'data' / 'fixpack_round1.csv'
MARKET = 'XIU.TO'
COST = 0.13                    # the measured round trip, as registered
DECISION_SESSIONS = 40
CATALYST_SESSIONS = 5          # earnings within this many sessions = a dated catalyst
MAX_PICKS = 2

FIELDS = ('session', 'kind', 'ticker', 'side', 'sector', 'gate', 'reason',
          'rank', 'y', 'scored_at')
R1_FIELDS = ('session', 'model', 'ticker', 'side', 'stance', 'conviction', 'top_two')


# ── the ledgers (append-only in effect; rewrites are atomic) ────────────────

def read(path=LEDGER):
    path = Path(path)
    return list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []


def _write(rows, path, fields):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    for r in sorted(rows, key=lambda r: tuple(str(r.get(k) or '') for k in fields[:4])):
        w.writerow({k: '' if r.get(k) is None else r.get(k) for k in fields})
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


def _append(new_rows, path, fields, key):
    rows = read(path)
    seen = {key(r) for r in rows}
    added = [r for r in new_rows if key(r) not in seen]
    if added:
        _write(rows + added, path, fields)
    return added


# ── the gate and the ranking (pure) ─────────────────────────────────────────

def gate(position, days_to_earnings):
    """(ok, reason): the registered abstention gate for one table position."""
    missing = []
    if not isinstance(position.get('invalid_at'), (int, float)):
        missing.append('no machine-checkable wrong-if')
    if not (isinstance(days_to_earnings, (int, float))
            and 0 <= days_to_earnings <= CATALYST_SESSIONS):
        missing.append('no dated catalyst (earnings within %d sessions)' % CATALYST_SESSIONS)
    return (not missing), ('; '.join(missing) if missing else '')


def _rank_key(position, rel_sector_pct):
    props = position.get('proposers') or []
    selected = sum(1 for x in props if x.get('how') == 'selected')
    confs = [x['confidence'] for x in props if isinstance(x.get('confidence'), (int, float))]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    own = abs(rel_sector_pct) if isinstance(rel_sector_pct, (int, float)) else 0.0
    return (-selected, -mean_conf, -own, position['ticker'], position['side'])


def select_shadow(table, rows_by_ticker, sectors):
    """The shadow Top 2: gated positions only, ranked, one per sector+side.

    Returns (picks, verdicts): picks are position dicts with 'sector' and
    'rank' set; verdicts cover EVERY position (for the gate record), each
    {'ticker', 'side', 'sector', 'gate', 'reason'}.
    """
    ranked, verdicts = [], {}
    for p in table:
        row = rows_by_ticker.get(p['ticker']) or {}
        sector = row.get('sector') or sectors.get(p['ticker']) or p['ticker']
        ok, reason = gate(p, row.get('days_to_earnings'))
        verdicts[(p['ticker'], p['side'])] = {'ticker': p['ticker'], 'side': p['side'],
                                              'sector': sector, 'gate': 'pass' if ok else 'abstain',
                                              'reason': reason}
        if ok:
            ranked.append((p, sector, row.get('rel_sector_pct')))
    ranked.sort(key=lambda x: _rank_key(x[0], x[2]))
    picks, used = [], set()
    for p, sector, _rel in ranked:
        if (sector, p['side']) in used:
            verdicts[(p['ticker'], p['side'])]['reason'] = 'sector cap: %s already held on this side' % sector
            continue
        if len(picks) >= MAX_PICKS:
            verdicts[(p['ticker'], p['side'])]['reason'] = 'not selected: the shadow Top 2 was full'
            continue
        used.add((sector, p['side']))
        picks.append({**p, 'sector': sector, 'rank': len(picks) + 1})
    for p in picks:
        verdicts[(p['ticker'], p['side'])]['reason'] = ''
    return picks, [verdicts[k] for k in sorted(verdicts)]


def round1_top2(table, round1_ballots):
    """The Round-1 Top 2: the council's own tally rule over the blind
    Round-1 ballots alone (DeepSeek and Gemini). Empty when Round 1 won
    no consensus — never padded."""
    import council
    if not round1_ballots:
        return []
    result = council.tally(table, round1_ballots)
    by_id = {p['id']: p for p in table}
    return [by_id[r['id']] for r in result['rows'] if r['consensus']][:MAX_PICKS]


# ── staging (morning, after the council sits) ───────────────────────────────

def _evidence(state_dir, now, tickers):
    """The morning's rows for the table's names: sector, earnings distance,
    sector-relative move — the same rows the council read."""
    import council
    out = {}
    try:
        rows = council.evidence_rows(state_dir, now, tickers)
    except Exception:
        rows = []
    for r in rows:
        tech = r.get('technicals') if isinstance(r.get('technicals'), dict) else {}
        out[r['ticker']] = {
            'sector': r.get('sector') or tech.get('sector'),
            'days_to_earnings': r.get('days_to_earnings', tech.get('days_to_earnings')),
            'rel_sector_pct': r.get('rel_sector_pct', tech.get('rel_sector_pct')),
        }
    return out


def stage(state_dir, *, now=None, path=LEDGER, r1_path=ROUND1_LEDGER):
    """Record today's gate verdicts, shadow/live/Round-1 picks and the
    frozen Round-1 ballots. Idempotent per session. Never raises: a
    failure is a status, and it costs this test only."""
    import council
    now = now or dt.datetime.now(ET)
    try:
        snap = council.load(state_dir, now)
    except Exception as exc:
        return {'status': 'UNAVAILABLE', 'reason': type(exc).__name__}
    session = now.date().isoformat()
    table = snap.get('positions') or []
    if snap.get('session') != session or not table:
        return {'status': 'NO_COUNCIL', 'reason': snap.get('reason') or 'the council did not sit'}
    rows_by_ticker = _evidence(state_dir, now, {p['ticker'] for p in table})
    try:
        import exposure
        sectors = exposure.load_sectors()
    except Exception:
        sectors = {}
    picks, verdicts = select_shadow(table, rows_by_ticker, sectors)
    by_id = {p['id']: p for p in table}
    live = [by_id[i] for i in snap.get('picks') or [] if i in by_id]
    round1 = (snap.get('rounds') or {}).get('round1') or {}
    r1_picks = round1_top2(table, round1)

    out_rows = [{'session': session, 'kind': 'gate', **v} for v in verdicts]
    for kind, chosen in (('shadow', picks), ('live', live), ('round1', r1_picks)):
        for i, p in enumerate(chosen, 1):
            out_rows.append({'session': session, 'kind': kind, 'ticker': p['ticker'],
                             'side': p['side'],
                             'sector': p.get('sector') or rows_by_ticker.get(p['ticker'], {}).get('sector')
                             or sectors.get(p['ticker']) or p['ticker'],
                             'gate': '', 'reason': '', 'rank': i})
    added = _append(out_rows, path, FIELDS,
                    key=lambda r: (r['session'], r['kind'], r['ticker'], r['side']))

    votes = []
    for model, ballot in sorted(round1.items()):
        if not isinstance(ballot, dict):
            continue
        top = set(ballot.get('top_two') or [])
        for pid, v in sorted((ballot.get('votes') or {}).items()):
            p = by_id.get(pid)
            if p:
                votes.append({'session': session, 'model': model, 'ticker': p['ticker'],
                              'side': p['side'], 'stance': v.get('stance'),
                              'conviction': v.get('conviction'),
                              'top_two': 1 if pid in top else 0})
    r1_added = _append(votes, r1_path, R1_FIELDS,
                       key=lambda r: (r['session'], r['model'], r['ticker'], r['side']))
    return {'status': 'RECORDED', 'session': session, 'positions': len(table),
            'shadow': [(p['side'], p['ticker']) for p in picks],
            'live': [(p['side'], p['ticker']) for p in live],
            'round1': [(p['side'], p['ticker']) for p in r1_picks],
            'abstentions': sum(1 for v in verdicts if v['gate'] == 'abstain'),
            'added': len(added), 'ballots_added': len(r1_added)}


# ── scoring (evening) ───────────────────────────────────────────────────────

def score(path=LEDGER, *, now=None, chart=None):
    """Fill y on every unscored pick row: side x (stock - XIU) open ->
    close from daily bars (news_desk's yardstick), minus the round trip."""
    import news_desk
    chart = chart or news_desk.daily_chart
    now = now or dt.datetime.now(ET)
    rows = read(path)
    todo = [r for r in rows if r['kind'] in ('shadow', 'live', 'round1')
            and r.get('y') in (None, '')]
    if not todo:
        return 0
    cache, n = {}, 0

    def frame(t):
        if t not in cache:
            try:
                cache[t] = chart(t)[1]
            except Exception:
                cache[t] = None
        return cache[t]

    done_today = now.time() >= dt.time(16, 5)
    for r in todo:
        day = dt.date.fromisoformat(r['session'])
        if day > now.date() or (day == now.date() and not done_today):
            continue
        s1, m1 = frame(r['ticker']), frame(MARKET)
        if s1 is None or m1 is None:
            continue
        res = news_desk.outcomes(r['side'], day, None, s1, None, m1)
        if 'w_day' in res:
            r['y'] = round(res['w_day'] - COST, 4)
            r['scored_at'] = now.isoformat()
            n += 1
    if n:
        _write(rows, path, FIELDS)
    return n


# ── the running record ──────────────────────────────────────────────────────

def record(path=LEDGER):
    """Paired, per session: shadow vs live, and final (live) vs Round-1 —
    the deliberation delta. A session counts when the live arm held at
    least one scored pick; a shadow that stood aside scores 0 that day."""
    rows = read(path)
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        if r['kind'] in ('shadow', 'live', 'round1') and r.get('y') not in (None, ''):
            by[r['session']][r['kind']].append(float(r['y']))
    sessions = sorted(s for s, d in by.items() if d.get('live'))
    paired, delta = [], []
    for s in sessions:
        d = by[s]
        live_m = sum(d['live']) / len(d['live'])
        shadow_m = sum(d['shadow']) / len(d['shadow']) if d.get('shadow') else 0.0
        paired.append(shadow_m - live_m)
        if d.get('round1'):
            delta.append(live_m - sum(d['round1']) / len(d['round1']))

    def mean_t(xs):
        if not xs:
            return None, None
        m = sum(xs) / len(xs)
        if len(xs) < 2:
            return m, None
        sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
        return m, (m / (sd / math.sqrt(len(xs))) if sd else None)

    shadow_all = [y for d in by.values() for y in d.get('shadow', [])]
    live_all = [y for d in by.values() for y in d.get('live', [])]
    pm, pt = mean_t(paired)
    dm, dtn = mean_t(delta)
    return {'sessions': len(sessions),
            'shadow_mean': (sum(shadow_all) / len(shadow_all)) if shadow_all else None,
            'live_mean': (sum(live_all) / len(live_all)) if live_all else None,
            'paired_diff': pm, 'paired_t': pt,
            'deliberation_delta': dm, 'deliberation_t': dtn,
            'abstentions': sum(1 for r in rows if r['kind'] == 'gate' and r.get('gate') == 'abstain'),
            'gate_rows': sum(1 for r in rows if r['kind'] == 'gate')}


def line(path=LEDGER):
    r = record(path)
    if not r['sessions']:
        return ('Fix pack (day-140 test, shadow): no paired session scored yet; judged paired '
                'against the live Top 2 at %d sessions (PREREGISTER_day140_fixpack.md).'
                % DECISION_SESSIONS)
    return ('Fix pack (day-140 test, shadow): %d paired session(s), shadow %+.2f%% vs live '
            '%+.2f%% per pick (paired %+.2f%%%s); deliberation delta %s; %d gate abstention(s) '
            'so far; decision at %d sessions (PREREGISTER_day140_fixpack.md).' % (
                r['sessions'], r['shadow_mean'] or 0.0, r['live_mean'] or 0.0,
                r['paired_diff'] or 0.0,
                '' if r['paired_t'] is None else ', t = %.2f' % r['paired_t'],
                'n/a yet' if r['deliberation_delta'] is None else '%+.2f%% per session'
                % r['deliberation_delta'],
                r['abstentions'], DECISION_SESSIONS))


def section(session, path=LEDGER):
    """Today's shadow, for the evening review. Never costs the review."""
    try:
        score(path=path)
        rows = read(path)
        today = [r for r in rows if r['session'] == session]
        picks = [r for r in today if r['kind'] == 'shadow']
        refused = [r for r in today if r['kind'] == 'gate' and r.get('gate') == 'abstain']

        def one(r):
            v = r.get('y')
            return '%s %s %s' % (r['side'], r['ticker'],
                                 'not scored' if v in (None, '') else '%+.2f%%' % float(v))
        out = ['', '## The fix pack, in shadow (day-140 test)',
               'The registered gate (a dated catalyst and a machine-checkable wrong-if), '
               'Round-1 scored apart, and a sector cap — run beside the live Top 2, never '
               'instead of it. Not sized, not in the email.',
               ('Shadow Top 2: ' + ', '.join(one(r) for r in picks) + '.') if picks
               else 'Shadow Top 2: the gate passed nothing today — the shadow stood aside.',
               line(path)]
        if refused:
            out.append('Gate abstentions today: ' + '; '.join(
                '%s %s (%s)' % (r['side'], r['ticker'], r['reason']) for r in refused) + '.')
        return '\n'.join(out) + '\n'
    except Exception as exc:
        return f"\nThe fix-pack readout is unavailable ({type(exc).__name__}).\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--stage', action='store_true')
    p.add_argument('--score', action='store_true')
    p.add_argument('--line', action='store_true')
    p.add_argument('--state-dir', default=str(ROOT / '.rb-state'))
    a = p.parse_args(argv)
    if a.stage:
        print(json.dumps(stage(a.state_dir), indent=1, default=str))
        return 0
    if a.score:
        print('scored %d' % score())
        return 0
    if a.line:
        print(line())
        return 0
    p.error('one of --stage, --score, --line is required')


if __name__ == '__main__':
    raise SystemExit(main())
