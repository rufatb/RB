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
until then it is printed as what it is, a count.

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
    splits = [
        ("today's open agreed with the pick", lambda r: r['gap'] > 0),
        ('the first 15 minutes agreed with the pick', lambda r: r['first15'] > 0),
        ("its 'wrong if' was NOT already crossed at entry",
         lambda r: None if r.get('crossed') is None else not r['crossed']),
        ("its sector agreed with the pick",
         lambda r: None if r.get('sector_r') is None else r['sector_r'] > 0),
    ]
    out = []
    for name, test in splits:
        yes = [r for r in picks if test(r) is True]
        no = [r for r in picks if test(r) is False]
        diff = [dict(session=s, r_pct=(st.mean([r['r_pct'] for r in yes if r['session'] == s])
                                       - st.mean([r['r_pct'] for r in no if r['session'] == s])))
                for s in {r['session'] for r in yes} & {r['session'] for r in no}]
        t, days = _clustered(diff)
        out.append({'question': name, 'yes': _rate(yes), 'no': _rate(no), 'days': days,
                    't': None if t is None else round(t, 2),
                    'verdict': ('LESSON' if t is not None and abs(t) >= LESSON_T and days >= MIN_DAYS
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
    out += ['## By section and model', '| Section | Model | Picks | Right | Mean | P&L (sized) | per $10k each |',
            '|---|---|---:|---:|---:|---:|---:|']
    for (sec, model), v in groups.items():
        pnl = [r['pnl_cad'] for r in v if r.get('pnl_cad') is not None]
        out.append(f"| {sec} | {model} | {len(v)} | {sum(r['r_pct'] > 0 for r in v)} | "
                   f"{st.mean(r['r_pct'] for r in v):+.2f}% | {('%+.2f CAD' % sum(pnl)) if pnl else '—'} | "
                   f"{sum(r['r_pct'] for r in v) * 100:+.0f} |")
    out += ['', '## Every pick, and why it went the way it did',
            '| Section | Model | Pick | Result | Best / worst after entry | Why |', '|---|---|---|---:|---|---|']
    for r in rows:
        out.append(f"| {r['section']} | {r['model']} | {r['side']} {r['ticker']} | {r['r_pct']:+.2f}% | "
                   f"{r['mfe']:+.2f}% / {r['mae']:+.2f}% | {why(r)} |")
    out += ['', '## Learning — across every reviewed day, not just today',
            f'A pattern becomes a LESSON only at a clustered |t| ≥ {LESSON_T} over at least {MIN_DAYS} days.',
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
    p.add_argument('--session', required=True)
    p.add_argument('--report', default=str(ROOT / '.rb-state' / 'latest' / 'report.json'))
    a = p.parse_args(argv)
    report = json.loads(Path(a.report).read_text())
    if report.get('session') != a.session:
        print(f"the report is for {report.get('session')}, not {a.session}", file=sys.stderr)
        return 2
    out = review(a.session, report)
    print(out['markdown'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
