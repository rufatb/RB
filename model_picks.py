#!/usr/bin/env python3
"""The models' track record: every pick recorded, every pick scored.

WHY THIS EXISTS. Every morning the report says of DeepSeek and Jev: "no track
record, never scored against an outcome". That was true, and it would have
stayed true forever, because nothing recorded their picks anywhere that
survived the container. Two models have been asked the owner's question every
day since 2026-09-17, and not one answer has ever been checked.

This keeps `data/model_picks.csv`, append-only, and scores each pick against
its own session from five-minute bars:

    entry  close of the bar stamped 09:40 — the completed 09:45 bar, the same
           reference the engine's own board uses
    exit   close of the bar stamped 15:55 — the session close
    r      signed: (exit/entry - 1) for a LONG, the negative for a SHORT
    hit    r > 0
    invalidated  for a pick carrying `invalid_at`: did the session trade
                 through its own stated level (below for LONG, above for SHORT)?

WHAT THIS IS NOT. It is a proxy — no spread, no fill, no cost — exactly like
the engine's legacy official-close proxy, and it is labelled that way wherever
it is printed. A handful of sessions resolves nothing: the scorecard prints its
own sample size and interval beside the rate, every time (house rule 8).

Forced Jev picks are recorded and scored SEPARATELY from selected ones. They
answer a different question, and pooling them would make the gate's abstentions
invisible in the record.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'model_picks.csv'
FIELDS = ('session', 'model', 'kind', 'side', 'ticker', 'confidence', 'abstain_probability',
          'invalid_at', 'prompt_version', 'source', 'entry', 'exit', 'r_pct', 'hit',
          'invalidated', 'scored_at', 'basis', 'entry_time', 'open_check', 'top_pick',
          'agreement')
# `basis` (day-114): what the pick's reason rests on — news / technical / macro,
# declared by the model and checked against what it was shown
# (deepseek_opportunities.check_basis). PREREGISTER_day114_basis.md compares
# them. `entry_time`: a LATE pick (asked after the open, late_picks.py) is
# scored from the bar it was asked in, never from 09:45 — a 09:45 entry would
# credit it with a move that happened before it existed.
# `open_check` (day-115): did the pick pass the owner's rule at 09:45 — LONG
# above VWAP / SHORT below it, opening rvol > 1.2 (consensus_picks.opening)?
# `met` / `not_met` / `not_measured`, filled at SCORING from the same bars, so
# every row is checked by one implementation, old rows included. `top_pick`:
# the desk's top pick as the 09:46 report named it (a decision made then, so
# recorded from the report, never recomputed).
KEY = ('session', 'model', 'kind', 'side', 'ticker')
ENTRY_BAR, EXIT_BAR = dt.time(9, 40), dt.time(15, 55)


# ── recording ───────────────────────────────────────────────────────────────

def rows_from_report(report, source='published_report'):
    """Every model pick in a frozen report, one row each. Pure."""
    session = report['session']
    intra = report.get('intraday') or {}
    out = []

    def add(model, kind, side, pick, **extra):
        if not isinstance(pick, dict) or not isinstance(pick.get('ticker'), str):
            return
        out.append({'session': session, 'model': model, 'kind': kind, 'side': side,
                    'ticker': pick['ticker'],
                    'confidence': pick.get('confidence', pick.get('probability')),
                    'abstain_probability': pick.get('abstain_probability',
                                                    pick.get('gated_abstain_probability')),
                    'invalid_at': pick.get('invalid_at'), 'basis': pick.get('basis'),
                    'source': source, **extra})

    # THE ENGINE ON THE SAME YARDSTICK. Its own ledger scores against the
    # official close; recording its board here too lets the leaderboard compare
    # every source with one scorer, one entry bar and one exit bar.
    for leg in intra.get('legs') or []:
        if leg.get('side') in ('LONG', 'SHORT'):
            add('engine', 'board', leg['side'], {'ticker': leg.get('ticker'),
                                                 'confidence': leg.get('p_sided')})
    tops = {(d.get('id'), l.get('side'), l.get('ticker'))
            for d in intra.get('desks') or [] for l in d.get('legs') or [] if l.get('top_pick')}
    has_tops = any(d.get('top_pick') is not None for d in intra.get('desks') or [])

    def top(model, side, pick):
        if not has_tops:
            return {}
        return {'top_pick': (model, side, (pick or {}).get('ticker')) in tops}
    cl = intra.get('claude') or {}
    if cl.get('status') in ('READY', 'NO_OPPORTUNITY'):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in cl.get(key) or []:
                add('claude', 'selected', side, pick, prompt_version=cl.get('route'),
                    **top('claude', side, pick))
    ds = intra.get('opportunities') or {}
    if ds.get('status') in ('READY', 'NO_OPPORTUNITY'):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in ds.get(key) or []:
                add('deepseek', 'selected', side, pick, prompt_version=ds.get('prompt_version'),
                    **top('deepseek', side, pick))
    gm = intra.get('gemini') or {}           # the fourth desk, from 2026-10-05
    if gm.get('status') in ('READY', 'NO_OPPORTUNITY'):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in gm.get(key) or []:
                add('gemini', 'selected', side, pick, prompt_version=gm.get('prompt_version'),
                    **top('gemini', side, pick))
    jev = intra.get('jev') or {}
    if jev.get('status') in ('READY', 'NO_OPPORTUNITY'):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in jev.get(key) or []:
                add('jev', 'selected', side, pick, **top('jev', side, pick))
        for side in ('LONG', 'SHORT'):
            add('jev', 'forced', side, jev.get('forced_' + side.lower()))
    # TOP 2 (top_picks, day-119): the two names the models agree on most. One
    # kind; how many models backed each is its own column, so the scoreboard
    # can split it without two kinds that change as models go up and down.
    for pick in (intra.get('top_two') or {}).get('picks') or []:
        add('top2', 'pick', pick.get('side'), pick, agreement=pick.get('agreement'),
            prompt_version=(intra.get('top_two') or {}).get('rule_version'))
    # Part 5's debate (debate.py): what survived cross-examination and the judge.
    for pick in (intra.get('debate') or {}).get('final') or []:
        add('debate', 'final', pick.get('side'),
            {'ticker': pick.get('ticker'), 'confidence': pick.get('jev_probability')},
            prompt_version='+'.join(x for x in ((intra.get('debate') or {}).get('prompt_version'),
                                                (intra.get('debate') or {}).get('entry_rule')) if x) or None)
    # Part 3's strategy picks (consensus_picks): a name that met the owner's rule
    # and one printed only so the section is never empty answer different
    # questions, so they are different kinds.
    for pick in (intra.get('consensus') or {}).get('picks') or []:
        add('consensus', 'rule_met' if pick.get('rule_met') else 'rule_not_met',
            pick.get('side'), pick, prompt_version=pick.get('tier'))
    return out


def read(path=LEDGER):
    path = Path(path)
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text())))


def write(rows, path=LEDGER):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore')
    writer.writeheader()
    for row in sorted(rows, key=lambda r: tuple(str(r.get(k) or '') for k in KEY)):
        writer.writerow({k: _cell(row.get(k)) for k in FIELDS})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(out.getvalue())
    tmp.replace(path)


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, float):
        return f'{value:.6g}'
    return str(value)


def _key(row):
    return tuple(str(row.get(k) or '') for k in KEY)


def append(new_rows, path=LEDGER):
    """Append-only. A recorded pick is never rewritten by a later record —
    a second publication of the same session cannot change what was picked."""
    existing = read(path)
    seen = {_key(r) for r in existing}
    added = [r for r in new_rows if _key(r) not in seen]
    if added:
        write(existing + added, path)
    return len(added)


# ── scoring ─────────────────────────────────────────────────────────────────

def _yahoo_bars(ticker):
    from adapters import YahooDirectAdapter
    adapter = YahooDirectAdapter(timeout=14)
    return adapter._bars_df(adapter._chart(ticker, '5m', '60d'))


def score_one(row, bars):
    """Score one pick against its session. Returns the fields to add, or None
    when the session's bars are not all there (never a partial score)."""
    day = dt.date.fromisoformat(row['session'])
    frame = bars[[ts.date() == day for ts in bars.index]]
    if frame.empty:
        return None
    local = frame.tz_convert(ET)
    times = [ts.time() for ts in local.index]
    entry_bar = ENTRY_BAR
    if row.get('entry_time'):
        entry_bar = dt.time.fromisoformat(row['entry_time'])
    if entry_bar not in times or EXIT_BAR not in times or entry_bar >= EXIT_BAR:
        return None
    entry = float(local['Close'].iloc[times.index(entry_bar)])
    exit_ = float(local['Close'].iloc[times.index(EXIT_BAR)])
    if not (math.isfinite(entry) and math.isfinite(exit_)) or entry <= 0:
        return None
    sign = 1 if row['side'] == 'LONG' else -1
    r = sign * (exit_ / entry - 1) * 100
    after = local[[entry_bar < t <= EXIT_BAR for t in times]]
    invalidated = None
    level = _float(row.get('invalid_at'))
    if level is not None and not after.empty:
        invalidated = (float(after['Low'].min()) < level if row['side'] == 'LONG'
                       else float(after['High'].max()) > level)
    return {'entry': round(entry, 4), 'exit': round(exit_, 4), 'r_pct': round(r, 4),
            'hit': r > 0, 'invalidated': invalidated}


def open_check(row, bars):
    """UNWIRED 2026-09-28 (rejection #44); kept as the record of what the
    recorded `open_check` values mean. The owner's rule at 09:45 for a pick entered at 09:45; None for a late
    pick (entered at a later bar, so a 09:45 check says nothing about it)."""
    if row.get('entry_time'):
        return None
    import consensus_picks
    measured = consensus_picks.opening(bars, dt.date.fromisoformat(row['session']))
    if measured.get('status') != 'OK':
        return 'not_measured'
    return 'met' if consensus_picks.passes(row['side'], measured)[0] else 'not_met'


def score(path=LEDGER, *, now=None, bars_for=None):
    """Score every unscored pick whose session has closed. Returns a count."""
    now = now or dt.datetime.now(ET)
    bars_for = bars_for or _yahoo_bars
    rows = read(path)
    cache, scored = {}, 0
    for row in rows:
        if row.get('scored_at'):
            continue
        session = dt.date.fromisoformat(row['session'])
        if session > now.date() or (session == now.date() and now.time() < dt.time(16, 5)):
            continue
        bars = _bars(cache, row['ticker'], bars_for)
        if bars is None:
            continue
        result = score_one(row, bars)
        if result:
            # The open check (rejection #44) is no longer filled at scoring
            # (2026-09-28); rows that carry one keep it, as recorded.
            row.update({k: _cell(v) for k, v in result.items()}, scored_at=now.isoformat())
            scored += 1
    if scored:
        write(rows, path)
    return scored


def _bars(cache, ticker, bars_for):
    if ticker not in cache:
        try:
            cache[ticker] = bars_for(ticker)
        except Exception:
            cache[ticker] = None
    return cache[ticker]


def _float(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ── the scorecard printed beside the picks ──────────────────────────────────

def scorecard(rows=None):
    """Per (model, kind): picks, hits, rate, mean r, sessions, 95% interval."""
    rows = read() if rows is None else rows
    out = {}
    for row in rows:
        if not row.get('scored_at'):
            continue
        key = f"{row['model']}_{row['kind']}"
        entry = out.setdefault(key, {'n': 0, 'hits': 0, 'r': [], 'sessions': set(),
                                     'invalid_n': 0, 'invalidated': 0})
        entry['n'] += 1
        entry['hits'] += row.get('hit') == '1'
        r = _float(row.get('r_pct'))
        if r is not None:
            entry['r'].append(r)
        entry['sessions'].add(row['session'])
        if row.get('invalidated') in ('0', '1'):
            entry['invalid_n'] += 1
            entry['invalidated'] += row['invalidated'] == '1'
    result = {}
    for key, e in out.items():
        n = e['n']
        rate = e['hits'] / n if n else None
        # Wilson interval: honest at small n, never outside [0, 1].
        z = 1.96
        lo = hi = None
        if n:
            centre = (rate + z*z/(2*n)) / (1 + z*z/n)
            half = z*math.sqrt(rate*(1-rate)/n + z*z/(4*n*n)) / (1 + z*z/n)
            lo, hi = max(0.0, centre-half), min(1.0, centre+half)
        result[key] = {'picks': n, 'hits': e['hits'], 'rate': rate,
                       'ci95': [lo, hi] if n else None,
                       'mean_r_pct': (sum(e['r'])/len(e['r'])) if e['r'] else None,
                       'sessions': len(e['sessions']),
                       'invalidation_checked': e['invalid_n'],
                       'invalidated': e['invalidated'],
                       'label': 'proxy: 09:45 bar close to session close; no spread, fill or cost'}
    return result


DESK_MODELS = ('claude', 'deepseek', 'jev')


def verification_card(rows=None):
    """The desks' SELECTED picks split by the open check, and the top picks —
    on the same scorer as everything else. Keys: check_met, check_not_met,
    check_top."""
    rows = read() if rows is None else rows
    desk = [r for r in rows if r.get('model') in DESK_MODELS and r.get('kind') == 'selected']
    split = [{**r, 'model': 'check', 'kind': r['open_check']} for r in desk
             if r.get('open_check') in ('met', 'not_met')]
    top = [{**r, 'model': 'check', 'kind': 'top'} for r in desk if r.get('top_pick') == '1']
    return scorecard(split + top)


def wire_card(rows=None, root=None):
    """The desks' pre-open picks on a name the issuer's own wire release named
    overnight (newswire.window: prior 16:00 -> 09:30), on the same scorer.
    PREREGISTER_day118_wire.md's forward population; one key, `wire_release`.
    A pick is placed by the ARCHIVE, never by what the model said its basis was."""
    import newswire
    rows = read() if rows is None else rows
    picked = [r for r in rows if (r.get('model'), r.get('kind')) in
              (('claude', 'selected'), ('deepseek', 'selected'), ('jev', 'forced'))]
    hit = []
    for r in picked:
        start, end = newswire.window(dt.date.fromisoformat(r['session']))
        if newswire.releases_for(r['ticker'], start, end, root):
            hit.append({**r, 'model': 'wire', 'kind': 'release'})
    return scorecard(hit)


def basis_card(rows=None, kinds=('selected',), models=('claude', 'deepseek')):
    """Hit rate by declared basis over the registered population
    (PREREGISTER_day114_basis.md). Descriptive until the registered bar is met."""
    rows = read() if rows is None else rows
    out = {}
    for row in rows:
        if (not row.get('scored_at') or row.get('model') not in models
                or row.get('kind') not in kinds or not row.get('basis')):
            continue
        e = out.setdefault(row['basis'], {'picks': 0, 'hits': 0, 'r': [], 'sessions': set()})
        e['picks'] += 1
        e['hits'] += row.get('hit') == '1'
        r = _float(row.get('r_pct'))
        if r is not None:
            e['r'].append(r)
        e['sessions'].add(row['session'])
    return {b: {'picks': e['picks'], 'hits': e['hits'],
                'rate': e['hits'] / e['picks'] if e['picks'] else None,
                'mean_r_pct': sum(e['r']) / len(e['r']) if e['r'] else None,
                'sessions': len(e['sessions'])} for b, e in out.items()}


REPLAY = ROOT / 'data' / 'replay_day117.json'
WIRE_REPLAY = ROOT / 'data' / 'replay_day118_wire.json'


def replay_line(path=REPLAY, wire_path=None):
    """The base rate the live scoreboard is read against (day-117 replay,
    house rule 8): the same question asked over 59 past sessions — and, from
    day-118, what adding the issuers' own wire releases did. One line, or None
    when the summary is missing — never an invented number."""
    try:
        r = json.loads(Path(path).read_text())
        ds, jev = r['deepseek_selected'], r['jev_forced']
    except (OSError, ValueError, KeyError, TypeError):
        return None
    line = ('Base rate — replay of %d past sessions, same question, technicals only: '
            'DeepSeek %d/%d (%.0f%%) vs %.0f%% for random picks from the same list; '
            'Jev forced %d/%d (%.0f%%) vs %.0f%%. '
            'None beat random, so a day\'s hits and misses are noise (%s).'
            % (r['sessions'], ds['hits'], ds['picks'], ds['hit_rate']*100, ds['placebo_hit_rate']*100,
               jev['hits'], jev['picks'], jev['hit_rate']*100, jev['placebo_hit_rate']*100, r['audit']))
    try:
        w = json.loads(Path(wire_path or WIRE_REPLAY).read_text())
        h1, h3 = w['H1_deepseek_event'], w['H3_event_names_move_more']
        line += (' With the issuers\' own overnight wire releases added: the open prices them — '
                 'names with a release moved no more after 09:45 than the rest (%+.2f%%, t = %.2f), '
                 'and DeepSeek\'s picks on them went %d/%d, too few to judge (%s).'
                 % (h3['mean_abs_r_diff_pct'], h3['clustered_t'], h1['hits'], h1['picks'], w['audit']))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return line


def scorecard_line(card, model_kind, name):
    c = (card or {}).get(model_kind)
    if not c or not c['picks']:
        return (f"{name} track record: no pick has been scored yet — recording began "
                "2026-09-22; the first scores arrive after the next close.")
    lo, hi = c['ci95']
    line = (f"{name} track record: {c['hits']}/{c['picks']} picks right ({c['rate']:.0%}) over "
            f"{c['sessions']} session(s), mean {c['mean_r_pct']:+.2f}% per pick; 95% interval "
            f"{lo:.0%}–{hi:.0%}")
    line += (' — contains 50%, so not distinguishable from a coin flip.' if lo <= 0.5 <= hi
             else ' — excludes 50%, on a sample this small still NOT evidence of skill.')
    if c['invalidation_checked']:
        line += (f" Its own invalidation level was hit on {c['invalidated']} of "
                 f"{c['invalidation_checked']}.")
    return line + ' Proxy: 09:45 bar to session close, no costs.'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--record-report', metavar='REPORT_JSON',
                   help='append every model pick in this frozen report')
    p.add_argument('--source', default='published_report')
    p.add_argument('--score', action='store_true', help='score every closed, unscored pick')
    p.add_argument('--ledger', default=str(LEDGER))
    a = p.parse_args(argv)
    out = {}
    if a.record_report:
        report = json.loads(Path(a.record_report).read_text())
        out['recorded'] = append(rows_from_report(report, a.source), a.ledger)
        if a.ledger == str(LEDGER):
            # Part 3's gap signals keep their own ledger (two entries, open and
            # 09:45); a failure there must not cost the desks' record.
            try:
                import gap_signal
                out['gap_recorded'] = gap_signal.record(report)
            except Exception as exc:
                out['gap_recorded'] = 'FAILED: ' + type(exc).__name__
    if a.score:
        out['scored'] = score(a.ledger)
    out['scorecard'] = scorecard(read(a.ledger))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
