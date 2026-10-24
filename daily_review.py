#!/usr/bin/env python3
"""THE EVENING REVIEW — every pick in the day's email, scored and explained.

The owner, 2026-09-29: "score every single section, every pick … by language
model … profit and loss … why were the wrong picks wrong and why were the right
picks right … keep learning."

For the frozen report of a session this scores EVERY pick the email printed —
Top 2, the three desks (Jev forced too), the engine's abstained legs, the gap
signal, the debate's finals and REJECTED proposals, and the factor layer's
leans — on one yardstick (09:45 bar close → 15:55 bar close, no costs), and
records the context that explains the result:

  gap      today's open vs the prior close, signed to the pick's side
  first15  open → 09:45 entry, signed: how much moved before the pick could act
  mfe/mae  best and worst point after entry, signed
  crossed  the pick's own "wrong if" was already crossed at the 09:45 price
  sector   the 09:45 → close move of the name's sector peers in the pool

Each day's rows are appended to data/reviews/YYYY-MM-DD.json, and the LEARNING
section recomputes, over EVERY reviewed day so far, the questions a single day
tempts you to answer from one example: do picks do better when the open agrees
with them, when the first 15 minutes agree, when their "wrong if" is not already
crossed — and does the debate's KEEP beat its REJECT? A pattern is called a
lesson only when it holds across days at a clustered |t| ≥ 3.0 (the house bar);
until then it is printed as what it is, a count. Its sector's move is printed
too, but it is measured over the trade itself, so it is never a lesson.

    python daily_review.py --session 2026-09-29 [--report .rb-state/latest/report.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVIEWS = ROOT / 'data' / 'reviews'
LESSON_T = 3.0
MIN_DAYS = 20
SECTOR_QUESTION = 'its sector moved its way over the same 09:45 → close (known only afterwards)'
SAME_WINDOW = 'same window as the result, never a lesson'
SECTOR_PEERS = 6
SECTORS = ROOT / 'data' / 'tsx_sectors.json'


def _sector_map(path=SECTORS):
    """{ticker: sector}; empty when the map is missing (the sector column is then blank)."""
    try:
        return {t: v.get('sector') for t, v in json.loads(Path(path).read_text())['sectors'].items()}
    except (OSError, ValueError, KeyError) as e:
        print(f'sector map unavailable: {type(e).__name__}', file=sys.stderr)
        return {}


def picks_of(report):
    """Every pick the email printed, with the section and model it came from."""
    i = report.get('intraday') or {}
    out = []

    def add(section, model, side, pick, shares=None, extra=None):
        if not isinstance(pick, dict) or pick.get('ticker') is None or side not in ('LONG', 'SHORT'):
            return
        conf = pick.get('confidence', pick.get('probability', pick.get('jev_probability')))
        out.append({'section': section, 'model': model, 'side': side, 'ticker': pick['ticker'],
                    'confidence': conf, 'shares': shares, 'invalid_at': pick.get('invalid_at'),
                    **(extra or {})})

    for p in (i.get('top_two') or {}).get('picks') or []:
        add('Top 2', '+'.join(p.get('models') or []), p['side'], p, extra={'agreement': p.get('agreement')})
    ru = (i.get('top_two') or {}).get('runner_up')      # day-129: printed, never a pick
    if isinstance(ru, dict):
        add('Runner-up (not a pick)', '+'.join(ru.get('models') or []), ru['side'], ru,
            extra={'agreement': ru.get('agreement')})
    # Day-135c: positions the big-mover switch passed over; scored in their own
    # section, kept out of the lessons (which read named sections only).
    for p in (i.get('top_two') or {}).get('passed_movers') or []:
        add('Passed over (big mover)', '+'.join(p.get('models') or []), p['side'], p,
            extra={'agreement': p.get('agreement')})
    for p in (i.get('top_two') or {}).get('passed_wild') or []:            # day-137
        add('Passed over (high volatility)', '+'.join(p.get('models') or []), p['side'], p,
            extra={'agreement': p.get('agreement')})
    # Amendment 2 to day-129: the models' forced nominations, scored in their own
    # section and kept out of the lessons (which read named sections only).
    for model, got in ((i.get('council') or {}).get('nomination_picks') or {}).items():
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in got.get(key) or []:
                add('Nominated (forced)', model, side, pick)
    for d in i.get('desks') or []:
        for leg in d.get('legs') or []:
            add('Desk', d.get('id'), leg['side'], leg,
                shares=None if leg.get('status') == 'ABSTAIN' else leg.get('baseline_shares'))
    jev = i.get('jev') or {}
    for side in ('LONG', 'SHORT'):
        add('Desk', 'jev forced', side, jev.get('forced_' + side.lower()))
    for leg in i.get('legs') or []:
        add('Engine', 'k-NN', leg.get('side'), leg, extra={'status': leg.get('status')})
    for p in (i.get('gap_signal') or {}).get('picks') or []:
        add('Gap signal', 'rule', p['side'], p)
    deb = i.get('debate') or {}
    for p in deb.get('final') or []:
        add('Debate final', 'deepseek+jev', p['side'], p)
    for v in deb.get('rulings') or []:
        add('Debate ruling', v.get('verdict', '?'), v.get('side'), v)
    for a in (i.get('deepseek') or {}).get('assessments') or []:
        lean = a.get('directional_lean')
        if lean in ('BULL', 'BEAR'):
            add('Factor lean', 'deepseek', 'LONG' if lean == 'BULL' else 'SHORT', a)
    return out


def day_path(bars, day):
    """Prior close, open, 09:45 entry (the 09:40 bar's close), close, high/low after entry."""
    prior = bars[[x.date() < day for x in bars.index]]
    f = bars[[x.date() == day for x in bars.index]]
    tm = [x.time() for x in f.index]
    if prior.empty or dt.time(9, 40) not in tm or dt.time(15, 55) not in tm:
        return None
    k = tm.index(dt.time(9, 40))
    after = f.iloc[k + 1:tm.index(dt.time(15, 55)) + 1]
    return {'prev': float(prior['Close'].iloc[-1]), 'open': float(f['Open'].iloc[0]),
            'entry': float(f['Close'].iloc[k]), 'close': float(f['Close'].iloc[tm.index(dt.time(15, 55))]),
            'hi': float(after['High'].max()), 'lo': float(after['Low'].min())}


def score(p, x, sector=None):
    s = 1 if p['side'] == 'LONG' else -1
    e = x['entry']
    lvl = p.get('invalid_at')
    return {**p,
            'r_pct': round(s * (x['close'] / e - 1) * 100, 3),
            'gap': round(s * (x['open'] / x['prev'] - 1) * 100, 3),
            'first15': round(s * (e / x['open'] - 1) * 100, 3),
            'mfe': round(((x['hi'] / e - 1) if s == 1 else (1 - x['lo'] / e)) * 100, 3),
            'mae': round(((x['lo'] / e - 1) if s == 1 else (1 - x['hi'] / e)) * 100, 3),
            'crossed': (None if not isinstance(lvl, (int, float)) else (e < lvl if s == 1 else e > lvl)),
            'sector_r': None if sector is None else round(s * sector, 3),
            # Day-120b: the pick against its own sector, so a good name in a
            # falling sector is not read as a bad pick (2026-09-30, TD).
            'vs_sector': None if sector is None else round(s * ((x['close'] / e - 1) * 100 - sector), 3),
            'pnl_cad': round(s * (x['close'] - e) * p['shares'], 2) if p.get('shares') else None,
            'entry': round(e, 4), 'close': round(x['close'], 4)}


def why(row):
    """One plain sentence on what happened, from measured facts only."""
    bits = []
    if row['gap'] <= -0.3:
        bits.append(f"the open went {abs(row['gap']):.1f}% against it before entry")
    elif row['gap'] >= 0.3:
        bits.append(f"the open had already moved {row['gap']:.1f}% its way")
    if row.get('crossed'):
        bits.append("its own 'wrong if' level was already crossed at the 09:45 price")
    if row['r_pct'] <= 0 and row['mfe'] >= 0.75:
        bits.append(f"it was up {row['mfe']:.1f}% at best and gave it all back")
    if row.get('sector_r') is not None and abs(row['sector_r']) >= 0.5:
        bits.append(f"its sector moved {row['sector_r']:+.1f}% its way" if row['sector_r'] > 0
                    else f"its sector moved {abs(row['sector_r']):.1f}% against it")
    if row.get('vs_sector') is not None:
        bits.append(f"against its sector it {'beat' if row['vs_sector'] > 0 else 'trailed'} by "
                    f"{abs(row['vs_sector']):.2f}%")
    verdict = 'RIGHT' if row['r_pct'] > 0 else 'WRONG'
    return f"{verdict} {row['r_pct']:+.2f}%" + (': ' + '; '.join(bits) if bits else '')


# ── the learning section: across every reviewed day ─────────────────────────

def _clustered(rows):
    by = {}
    for r in rows:
        by.setdefault(r['session'], []).append(r['r_pct'])
    means = [st.mean(v) for v in by.values()]
    if len(means) < 3 or not st.stdev(means):
        return None, len(means)
    return st.mean(means) / (st.stdev(means) / math.sqrt(len(means))), len(means)


def lessons(all_rows):
    """Split the scored picks by each question, across every reviewed day."""
    # One row per (session, name, side): HBM as a DeepSeek pick, the Top 2 and the
    # debate's final is ONE outcome, and counting it three times fakes a sample.
    # The desk row is kept first: it carries the model's own "wrong if" level.
    order = ('Desk', 'Gap signal', 'Top 2', 'Debate final')
    seen, picks = set(), []
    for r in sorted((r for r in all_rows if r['section'] in order), key=lambda r: order.index(r['section'])):
        k = (r['session'], r['ticker'], r['side'])
        if k not in seen:
            seen.add(k)
            picks.append(r)
    # Each test returns True / False, or None when the question does not apply
    # (a pick with no "wrong if" level, a name with no sector reading).
    # Day-120 E2: a name the desks put on both sides the same session.
    sides = {}
    for r in all_rows:
        if r['section'] == 'Desk':
            sides.setdefault((r['session'], r['ticker']), set()).add(r['side'])
    # The last element says whether the question is answered by 09:45, when the
    # pick is entered. Its sector's move is measured over the trade itself
    # (09:45 → close), so it is part of the result: it describes, and is never a
    # lesson however large its t (t = 4.0 over 10 days on 2026-10-14, day-132c).
    splits = [
        ("the desks did NOT put the name on both sides (day-120 E2)",
         lambda r: len(sides.get((r['session'], r['ticker']), ())) < 2, True),
        ("today's open agreed with the pick", lambda r: r['gap'] > 0, True),
        ('the first 15 minutes agreed with the pick', lambda r: r['first15'] > 0, True),
        ("its 'wrong if' was NOT already crossed at entry (day-120 E1)",
         lambda r: None if r.get('crossed') is None else not r['crossed'], True),
        (SECTOR_QUESTION, lambda r: None if r.get('sector_r') is None else r['sector_r'] > 0, False),
    ]
    out = []
    for name, test, at_entry in splits:
        yes = [r for r in picks if test(r) is True]
        no = [r for r in picks if test(r) is False]
        diff = [dict(session=s, r_pct=(st.mean([r['r_pct'] for r in yes if r['session'] == s])
                                       - st.mean([r['r_pct'] for r in no if r['session'] == s])))
                for s in {r['session'] for r in yes} & {r['session'] for r in no}]
        t, days = _clustered(diff)
        out.append({'question': name, 'yes': _rate(yes), 'no': _rate(no), 'days': days,
                    't': None if t is None else round(t, 2),
                    'verdict': (SAME_WINDOW if not at_entry
                                else 'LESSON' if t is not None and abs(t) >= LESSON_T and days >= MIN_DAYS
                                else 'not established')})
    keep = [r for r in all_rows if r['section'] == 'Debate ruling' and r['model'] == 'KEEP']
    reject = [r for r in all_rows if r['section'] == 'Debate ruling' and r['model'] == 'REJECT']
    out.append({'question': "the debate's KEEP vs its REJECT", 'yes': _rate(keep), 'no': _rate(reject),
                'days': len({r['session'] for r in keep + reject}), 't': None,
                'verdict': 'counted, not tested'})
    return out


def _rate(rows):
    if not rows:
        return {'n': 0}
    return {'n': len(rows), 'right': sum(r['r_pct'] > 0 for r in rows),
            'mean_pct': round(st.mean(r['r_pct'] for r in rows), 3)}


# ── the report ──────────────────────────────────────────────────────────────

def markdown(session, rows, market, learn, replay_note):
    out = [f'# Evening review — {session}',
           f"Every pick the email printed, 09:45 bar close → 15:55 bar close, no costs. "
           f"XIU.TO over the same window: {market:+.2f}%." if market is not None else '', '']
    groups = {}
    for r in rows:
        groups.setdefault((r['section'], r['model']), []).append(r)
    out += ['## By section and model',
            'Vs sector is each pick against the median of its sector peers over the same window: '
            'it separates picking the wrong name from the whole sector moving.',
            '| Section | Model | Picks | Right | Mean | Beat its sector | Mean vs sector | P&L (sized) | per $10k each |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for (sec, model), v in groups.items():
        pnl = [r['pnl_cad'] for r in v if r.get('pnl_cad') is not None]
        rel = [r['vs_sector'] for r in v if r.get('vs_sector') is not None]
        out.append(f"| {sec} | {model} | {len(v)} | {sum(r['r_pct'] > 0 for r in v)} | "
                   f"{st.mean(r['r_pct'] for r in v):+.2f}% | "
                   f"{f'{sum(x > 0 for x in rel)}/{len(rel)}' if rel else '—'} | "
                   f"{f'{st.mean(rel):+.2f}%' if rel else '—'} | {('%+.2f CAD' % sum(pnl)) if pnl else '—'} | "
                   f"{sum(r['r_pct'] for r in v) * 100:+.0f} |")
    out += ['', '## Every pick, and why it went the way it did',
            '| Section | Model | Pick | Result | Best / worst after entry | Why |', '|---|---|---|---:|---|---|']
    for r in rows:
        out.append(f"| {r['section']} | {r['model']} | {r['side']} {r['ticker']} | {r['r_pct']:+.2f}% | "
                   f"{r['mfe']:+.2f}% / {r['mae']:+.2f}% | {why(r)} |")
    out += ['', '## Learning — across every reviewed day, not just today',
            f'A pattern becomes a LESSON only at a clustered |t| ≥ {LESSON_T} over at least {MIN_DAYS} days, '
            'and only from what is known at the 09:45 entry; a question measured over the trade itself never is.',
            '| Question | When yes | When no | Days | t | Verdict |', '|---|---|---|---:|---:|---|']
    for q in learn:
        fmt = lambda s: (f"{s['right']}/{s['n']} right, {s['mean_pct']:+.2f}%" if s.get('n') else '—')
        out.append(f"| {q['question']} | {fmt(q['yes'])} | {fmt(q['no'])} | {q['days']} | "
                   f"{'—' if q['t'] is None else q['t']} | {q['verdict']} |")
    if replay_note:
        out += ['', replay_note]
    return '\n'.join(out) + '\n'


REPLAY_NOTE = ('Replay check (2026-09-29, 649 picks over 59 past sessions): the open agreeing with a '
               'pick 52% right vs 51% against; the first 15 minutes agreeing 53% vs 49%; a "wrong if" '
               'already crossed at entry 47% vs 49%; the debate\'s KEEPs 49% vs REJECTs 52%. None is '
               'a lesson. A single day that looks decisive on one of these is the thing to distrust.')


def review(session, report, *, bars_for=None, root=REVIEWS, market_ticker='XIU.TO', sector_map=None):
    import model_picks
    bars_for = bars_for or model_picks._yahoo_bars
    day = dt.date.fromisoformat(session)
    picks = picks_of(report)
    cache = {}
    failures = {}

    def path(t):
        if t not in cache:
            try:
                cache[t] = day_path(bars_for(t), day)
            except Exception as e:  # counted and reported, never silent
                failures[t] = type(e).__name__
                cache[t] = None
        return cache[t]
    # Sector: the median 09:45 -> close move of up to SECTOR_PEERS other names in
    # the pick's sector (data/tsx_sectors.json), UNSIGNED here and signed per pick.
    smap = _sector_map() if sector_map is None else sector_map
    sectors = {}
    for t in {p['ticker'] for p in picks}:
        sec = smap.get(t)
        if not sec:
            continue
        moves = []
        for peer in sorted(n for n, s2 in smap.items() if s2 == sec and n != t)[:SECTOR_PEERS]:
            x = path(peer)
            if x is not None:
                moves.append((x['close'] / x['entry'] - 1) * 100)
        if len(moves) >= 2:
            sectors[t] = st.median(moves)
    rows = []
    unscored = []
    for p in picks:
        x = path(p['ticker'])
        if x is None:
            unscored.append(f"{p['side']} {p['ticker']}")
            continue
        rows.append({**score(p, x, sectors.get(p['ticker'])), 'session': session})
    mk = path(market_ticker)
    market = None if mk is None else round((mk['close'] / mk['entry'] - 1) * 100, 3)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / f'{session}.json').write_text(json.dumps({'session': session, 'rows': rows,
                                                        'unscored': unscored, 'market_pct': market,
                                                        'fetch_failures': failures},
                                                       indent=1, default=str))
    all_rows = []
    for f in sorted(root.glob('*.json')):
        all_rows += json.loads(f.read_text()).get('rows') or []
    learn = lessons(all_rows)
    md = markdown(session, rows, market, learn, REPLAY_NOTE)
    if unscored:
        md += f"\nNot scored (no complete bars): {', '.join(unscored)}.\n"
    if failures:
        md += f"\nBar fetches failed for {len(failures)} name(s): " + ', '.join(
            f'{t} ({e})' for t, e in sorted(failures.items())) + '.\n'
    (root / f'{session}.md').write_text(md)
    return {'rows': rows, 'learn': learn, 'markdown': md, 'unscored': unscored, 'failures': failures}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--session')
    p.add_argument('--report', default=str(ROOT / '.rb-state' / 'latest' / 'report.json'))
    p.add_argument('--backfill-council-tables', metavar='DB',
                   help='add the day-137 council table to reviewed days from a reports.sqlite3')
    a = p.parse_args(argv)
    if a.backfill_council_tables:
        print(json.dumps(backfill_council_tables(a.backfill_council_tables)))
        return 0
    if not a.session:
        p.error('--session is required')
    report = json.loads(Path(a.report).read_text())
    if report.get('session') != a.session:
        print(f"the report is for {report.get('session')}, not {a.session}", file=sys.stderr)
        return 2
    out = review(a.session, report)
    md = (out['markdown'] + lab_section() + memory_section(a.session, report)
          + table_section(a.session, report) + preopen_section(a.session))
    (REVIEWS / f'{a.session}.md').write_text(md)
    print(md)
    return 0


def lab_section(update=None, table=None):
    """Day-130: the execution lab, filled from the scored record and appended to
    the review. It never costs the review, and a failure says so."""
    import execution_lab
    try:
        got = (update or execution_lab.update)()
        lines = (table or execution_lab.table)()
    except Exception as exc:
        return f"\nExecution lab unavailable ({type(exc).__name__}).\n"
    if got.get('fetch_failures'):
        lines.append('Lab bar fetches failed for: ' + ', '.join(
            f'{t} ({e})' for t, e in sorted(got['fetch_failures'].items())) + '.')
    return '\n' + '\n'.join(lines) + '\n'


def preopen_section(session, path=None):
    """Day-139: the news desk asked before the open, judged open → close
    against XIU (PREREGISTER_day139_newsdesk_open.md). A forward test; it
    never costs the review, and a failure says so."""
    import news_desk
    try:
        path = path or news_desk.LEDGER
        today = [r for r in news_desk.read(path)
                 if r.get('arm') == news_desk.PREOPEN_ARM and r.get('session') == session]
        line = news_desk.preopen_line(path)
    except Exception as exc:
        return f"\nThe pre-open news desk readout is unavailable ({type(exc).__name__}).\n"

    def one(r):
        v = r.get('w_day')
        return '%s %s %s' % (r['side'], r['ticker'],
                             'not scored' if v in (None, '') else '%+.2f%%' % float(v))
    out = ['', '## The news desk asked before the open (day-139 test)',
           "Part 6's FULL-arm question, asked at about 09:20 on the releases out by then, scored "
           'from the open to the close against XIU. Not sized, not in the Top 2.',
           ('Today: ' + ', '.join(one(r) for r in sorted(today, key=lambda r: r['ticker'])) + '.')
           if today else 'Today: no pre-open call was recorded.',
           line]
    return '\n'.join(out) + '\n'


def memory_section(session, report, lines=None):
    """Day-130 step 3: the council with memory beside the live one. A shadow;
    it never costs the review, and a failure says so."""
    import council_memory
    try:
        got = (lines or council_memory.review_lines)(session, report)
    except Exception as exc:
        return f"\nThe memory council's readout is unavailable ({type(exc).__name__}).\n"
    return '\n' + '\n'.join(got) + '\n'


# ── day-137 M1: is the council choosing better than its own table? ──────────
# PREREGISTER_day137_council.md. Every position on the morning's frozen table
# is already recorded (a desk's selection, a nomination or Jev's forced pick),
# so the table is scored from data/model_picks.csv on the record's yardstick.
# The council's picks here are its own, BEFORE any pass-over rule.

TABLE_KINDS = ('selected', 'nominated', 'forced', 'pick')
TABLE_DECISION = 40


def council_table(report, ledger_rows):
    """{'positions': [...], 'members': n} for the session's frozen council, or
    None when none sat. A position the record never scored keeps r_pct None."""
    c = (report.get('intraday') or {}).get('council')
    if not isinstance(c, dict) or not (c.get('tally') or {}).get('rows'):
        return None
    session = report.get('session')
    scored = {}
    for r in ledger_rows:
        if (r.get('session') == session and r.get('kind') in TABLE_KINDS
                and (r.get('r_pct') or '').strip()):
            scored.setdefault((r['ticker'], r['side']), float(r['r_pct']))
    members = len(c['tally'].get('members') or [])
    picks = set(c.get('picks') or [])
    return {'members': members, 'positions': [
        {'id': t['id'], 'side': t['side'], 'ticker': t['ticker'], 'picked': t['id'] in picks,
         'unanimous': members >= 2 and len(t.get('endorse') or []) == members,
         'r_pct': scored.get((t['ticker'], t['side']))}
        for t in c['tally']['rows']]}


def table_record(root=REVIEWS):
    """Across every reviewed day: the council's picks against its whole table,
    per session, and the unanimous positions against the rest."""
    picked, unanimous = [], []
    for f in sorted(Path(root).glob('*.json')):
        doc = json.loads(f.read_text())
        t = doc.get('council_table')
        if not t:
            continue
        s = doc.get('session') or f.stem
        pos = [p for p in t['positions'] if p.get('r_pct') is not None]
        mine = [p['r_pct'] for p in pos if p['picked']]
        if mine and len(pos) > len(mine):
            picked.append({'session': s, 'r_pct': st.mean(mine) - st.mean(p['r_pct'] for p in pos),
                           'picks': mine, 'table': [p['r_pct'] for p in pos]})
        yes = [p['r_pct'] for p in pos if p['unanimous']]
        no = [p['r_pct'] for p in pos if not p['unanimous']]
        if yes and no:
            unanimous.append({'session': s, 'r_pct': st.mean(yes) - st.mean(no), 'yes': yes, 'no': no})
    return picked, unanimous


def table_section(session, report, root=REVIEWS, ledger_rows=None):
    """Day-137 M1, appended to the review: today's table and the running record.
    It never costs the review, and a failure says so."""
    import model_picks
    try:
        rows = model_picks.read() if ledger_rows is None else ledger_rows
        today = council_table(report, rows)
        path = Path(root) / f'{session}.json'
        if today is not None and path.exists():
            doc = json.loads(path.read_text())
            doc['council_table'] = today
            path.write_text(json.dumps(doc, indent=1, default=str))
        picked, unanimous = table_record(root)
    except Exception as exc:
        return f"\nThe council-against-its-table readout is unavailable ({type(exc).__name__}).\n"
    out = ['', '## The council against its own table (day-137, M1)',
           'Every position on the morning\'s table, 09:45 → close, against the council\'s own picks '
           'before any pass-over rule. A council choosing well beats its own table.']
    if today:
        pos = [p for p in today['positions'] if p['r_pct'] is not None]
        mine = [p for p in pos if p['picked']]
        if pos:
            out.append('Today: the council picked %s; the table of %d averaged %+.2f%%.' % (
                ', '.join('%s %s %+.2f%%' % (p['side'], p['ticker'], p['r_pct']) for p in mine) or 'nothing',
                len(pos), st.mean(p['r_pct'] for p in pos)))
    if picked:
        t, n = _clustered(picked)
        mine = [x for d in picked for x in d['picks']]
        table = [x for d in picked for x in d['table']]
        verdict = ('no verdict before %d sessions' % TABLE_DECISION if n < TABLE_DECISION else
                   'the council chooses WORSE than its own table' if t is not None and t <= -2 else
                   'the council\'s choice adds something' if t is not None and t >= 3 else
                   'no evidence either way')
        out.append('Record: %d session(s); its picks %+.2f%% (%d of %d right), the table %+.2f%% '
                   '(%d of %d right); picks minus table %+.2f%% a session, t = %s — %s.' % (
                       n, st.mean(mine), sum(x > 0 for x in mine), len(mine), st.mean(table),
                       sum(x > 0 for x in table), len(table), st.mean(d['r_pct'] for d in picked),
                       '—' if t is None else '%.2f' % t, verdict))
    if unanimous:
        t, n = _clustered(unanimous)
        yes = [x for d in unanimous for x in d['yes']]
        no = [x for d in unanimous for x in d['no']]
        out.append('Positions every member endorsed: %+.2f%% (%d of %d right); the rest %+.2f%% '
                   '(%d of %d right); %d session(s), t = %s. Counted, not a rule.' % (
                       st.mean(yes), sum(x > 0 for x in yes), len(yes), st.mean(no),
                       sum(x > 0 for x in no), len(no), n, '—' if t is None else '%.2f' % t))
    return '\n'.join(out) + '\n'


def backfill_council_tables(db, root=REVIEWS):
    """Day-137: add the council table to the days reviewed before M1 existed,
    from the frozen publications. Adds the block only where it is missing."""
    import sqlite3
    import model_picks
    rows = model_picks.read()
    con = sqlite3.connect(db)
    added = []
    for session, body in con.execute('select session, body from reports order by session'):
        path = Path(root) / f'{session}.json'
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        if 'council_table' in doc:
            continue
        t = council_table(json.loads(body), rows)
        if t is not None:
            doc['council_table'] = t
            path.write_text(json.dumps(doc, indent=1, default=str))
            added.append(session)
    return {'added': added}


if __name__ == '__main__':
    sys.exit(main())
