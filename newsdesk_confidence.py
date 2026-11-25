#!/usr/bin/env python3
"""Day-155b (PREREGISTER_day155b_newsdesk_confidence.md): does the news desk's
own score sort its calls?

  H1  the email's first two rows (material first, then the model's own
      confidence, then ticker; `news_desk.lines`' key) against the rest of the
      same morning, paired over sessions with day-145's machinery
      (`best_first`: t over session means, a one-sided sign-flip placebo,
      halves, a planted 1.0%).
  H2  material against routine, day-140's arm A (`fixpack.arm_a`) with a
      planted 1.0% on the material calls.

The outcome is the ledger's w945: side x (the name's 09:45 -> close minus
XIU's), in %. The committed ledger only; no network, no model.

    python newsdesk_confidence.py        # writes data/newsdesk_confidence_day155b.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import statistics as st
import sys
from pathlib import Path

import best_first as B
import fixpack
from replay_fmp_analyst import clustered

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / 'data' / 'news_calls.csv'
OUT = ROOT / 'data' / 'newsdesk_confidence_day155b.json'
FIRST, LAST = '2026-10-02', '2026-11-24'
SEED = 156
DRAWS = 10000              # H1, as day-145
H2_DRAWS = fixpack.DRAWS   # arm A's own 2,000
PLANT = 1.0
BAR_T = 3.0
BAR_P = 0.01
COST = 0.13
TOP = 2
BUCKETS = ((0.65, 9.0, '>= 0.65'), (0.60, 0.65, '0.60-0.64'), (0.55, 0.60, '0.55-0.59'),
           (0.0, 0.55, 'below 0.55'))


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _material(v):
    return v is True or str(v).strip().lower() == 'true'


def email_key(r):
    """`news_desk.lines`' own sort: material first, then confidence (highest
    first), then ticker."""
    return (not _material(r.get('material')), -float(r['confidence']), r['ticker'])


def read(path=LEDGER):
    path = Path(path)
    return list(csv.DictReader(io.StringIO(path.read_text()))) if path.exists() else []


def population(rows, *, arm='full', first=FIRST, last=LAST):
    """One row per (session, ticker) of one arm, in the window. Returns
    (rows, duplicates dropped)."""
    seen, out, dup = set(), [], 0
    for r in rows:
        if r.get('arm') != arm or not (first <= r.get('session', '') <= last):
            continue
        k = (r['session'], r['ticker'])
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        out.append(r)
    return out, dup


def ranked(rows):
    """{session: that session's calls in the email's order}, sessions ascending."""
    by = {}
    for r in rows:
        by.setdefault(r['session'], []).append(r)
    return {s: sorted(v, key=email_key) for s, v in sorted(by.items())}


def pairs(rows, *, key='w945', top=TOP):
    """[{session, d, top, rest}] for each session with a scored top-two call and
    a scored other call; d = mean(top) - mean(rest). The top two are chosen
    from every call the email printed, scored or not. Returns (pairs, skipped)."""
    out, skipped = [], 0
    for s, rs in ranked(rows).items():
        t = [x for x in (_num(r.get(key)) for r in rs[:top]) if x is not None]
        o = [x for x in (_num(r.get(key)) for r in rs[top:]) if x is not None]
        if not t or not o:
            skipped += 1
            continue
        out.append({'session': s, 'd': st.mean(t) - st.mean(o), 'top': t, 'rest': o})
    return out, skipped


def control_h1(ds):
    """House rule 10: every d centred on zero, PLANT added, the same t
    (edge / se, never (mean + edge) / se)."""
    if len(ds) < 3:
        return {'planted_pct': PLANT, 't': None, 'detected': False}
    m = st.mean(ds)
    t = B.t_stat([d - m + PLANT for d in ds])
    return {'planted_pct': PLANT, 't': None if t is None else round(t, 2),
            'detected': t is not None and t >= BAR_T}


def h1(prs, *, draws=DRAWS, seed=SEED):
    """The registered H1 decision over the session series of d."""
    ds = [p['d'] for p in prs]
    n = len(ds)
    t = B.t_stat(ds)
    half = n // 2
    halves = [st.mean(ds[:half]), st.mean(ds[half:])] if half else []
    p_up = B.placebo(ds, tail='upper', draws=draws, seed=seed)
    p_down = B.placebo(ds, tail='lower', draws=draws, seed=seed)
    ctl = control_h1(ds)
    sd = st.stdev(ds) if n > 1 else None
    tops = [x for p in prs for x in p['top']]
    rests = [x for p in prs for x in p['rest']]
    top_mean = st.mean(tops) if tops else None
    better = (t is not None and st.mean(ds) > 0 and t >= BAR_T and p_up is not None
              and p_up < BAR_P and bool(halves) and all(h > 0 for h in halves)
              and top_mean is not None and top_mean > COST)
    worse = (t is not None and t <= -BAR_T and p_down is not None and p_down < BAR_P
             and bool(halves) and all(h < 0 for h in halves))
    status = ('TOP2_BETTER' if better else 'TOP2_WORSE' if worse else
              'UNDERPOWERED' if not ctl['detected'] else 'NULL')
    return {'status': status, 'sessions': n,
            'mean_d': None if not ds else round(st.mean(ds), 3),
            't': None if t is None else round(t, 2),
            'placebo_p_upper': None if p_up is None else round(p_up, 4),
            'placebo_p_lower': None if p_down is None else round(p_down, 4),
            'halves': [round(h, 3) for h in halves],
            'top_two': {'calls': len(tops), 'right': sum(x > 0 for x in tops),
                        'mean': None if top_mean is None else round(top_mean, 3),
                        'net': None if top_mean is None else round(top_mean - COST, 3)},
            'rest': {'calls': len(rests), 'right': sum(x > 0 for x in rests),
                     'mean': None if not rests else round(st.mean(rests), 3)},
            'control': ctl,
            'mde': round((BAR_T + 0.84) * sd / math.sqrt(n), 3) if sd else None,
            'by_session': [{'session': p['session'], 'd': round(p['d'], 3)} for p in prs]}


def h2_picks(rows, *, key='w945'):
    return [(r['session'], _num(r.get(key)), _material(r.get('material')))
            for r in rows if _num(r.get(key)) is not None]


def control_h2(picks):
    """Each group centred on zero, PLANT added to every material call, then
    `fixpack.two_group` (floor_history's control)."""
    k = [y for _, y, g in picks if g]
    d = [y for _, y, g in picks if not g]
    if not k or not d:
        return None, None
    mk, md = st.mean(k), st.mean(d)
    planted = [(s, y - mk + PLANT, True) if g else (s, y - md, False) for s, y, g in picks]
    return fixpack.two_group(planted)


def h2(rows, *, key='w945', draws=H2_DRAWS, seed=SEED):
    picks = h2_picks(rows, key=key)
    got = fixpack.arm_a(picks, draws=draws, seed=seed)
    c_diff, c_t = control_h2(picks)
    detected = c_t is not None and c_t >= fixpack.BAR
    km = got['kept_mean']
    better = got['status'] == 'PASS' and km is not None and km > COST and detected
    status = ('MATERIAL_BETTER' if better else 'UNDERPOWERED' if not detected else 'NULL')
    rnd = lambda x, k=3: None if x is None else round(x, k)
    return {'status': status, 'arm_a': got['status'],
            'material_minus_routine': rnd(got['diff']), 't': rnd(got['t'], 2),
            'placebo_p': rnd(got['placebo_p'], 4), 'halves': [rnd(h) for h in got['halves']],
            'material': {'calls': got['kept'], 'mean': rnd(km),
                         'net': rnd(None if km is None else km - COST)},
            'routine': {'calls': got['dropped'], 'mean': rnd(got['dropped_mean'])},
            'sessions': got['sessions'],
            'control': {'planted_pct': PLANT, 't': rnd(c_t, 2), 'detected': detected},
            'mde': rnd(None if not c_t else 2.8 * c_diff / c_t)}


# ── beside the verdicts (descriptive) ─────────────────────────────────────────

def arm_stats(pairs_sv):
    """{calls, right, mean, t} for [(session, value)], session-clustered."""
    xs = [(s, v) for s, v in pairs_sv if v is not None]
    if not xs:
        return {'calls': 0}
    mean, se, t = clustered(xs) if len(xs) >= 2 else (xs[0][1], None, None)
    return {'calls': len(xs), 'right': sum(v > 0 for _, v in xs),
            'mean': round(mean, 3), 't': None if t is None else round(t, 2)}


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return round(num / den, 3) if den else None


def buckets(rows, key='w945'):
    out = {}
    for lo, hi, name in BUCKETS:
        out[name] = arm_stats([(r['session'], _num(r.get(key))) for r in rows
                               if lo <= float(r['confidence']) < hi])
    return out


def xiu_945(r):
    """XIU's 09:45 -> close on the row's session, from the row's two outcomes:
    sign x (raw - w945)."""
    raw, w = _num(r.get('w945_raw')), _num(r.get('w945'))
    if raw is None or w is None:
        return None
    return (1 if r['side'] == 'LONG' else -1) * (raw - w)


def market(rows):
    by = {}
    for r in rows:
        x, raw = xiu_945(r), _num(r.get('w945_raw'))
        if x is None or raw is None:
            continue
        by.setdefault(r['session'], {'xiu': [], 'raw': []})
        by[r['session']]['xiu'].append(x)
        by[r['session']]['raw'].append(raw)
    days = [(s, st.mean(v['xiu']), st.mean(v['raw'])) for s, v in sorted(by.items())]
    up = [raw for _, x, raw in days if x > 0]
    down = [raw for _, x, raw in days if x <= 0]
    xs, ys = [x for _, x, _ in days], [raw for _, _, raw in days]
    corr = None
    if len(days) >= 3 and st.pstdev(xs) and st.pstdev(ys):
        mx, my = st.mean(xs), st.mean(ys)
        corr = round(sum((a - mx) * (b - my) for a, b in zip(xs, ys))
                     / math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)), 3)
    return {'sessions': len(days), 'corr_session_raw_with_xiu': corr,
            'xiu_up_sessions': {'n': len(up), 'mean_raw': None if not up else round(st.mean(up), 3)},
            'xiu_down_sessions': {'n': len(down),
                                  'mean_raw': None if not down else round(st.mean(down), 3)}}


def disagreement(full, headline):
    hl = {(r['session'], r['ticker']): r['side'] for r in headline}
    same, diff = [], []
    for r in full:
        h = hl.get((r['session'], r['ticker']))
        y = _num(r.get('w945'))
        if h is None or y is None:
            continue
        (same if h == r['side'] else diff).append((r['session'], y))
    return {'arms_agree': arm_stats(same), 'arms_disagree_full_side': arm_stats(diff)}


def describe(rows, headline, preopen):
    sv = lambda key, rs: [(r['session'], _num(r.get(key))) for r in rs]
    scored = [r for r in rows if _num(r.get('w945')) is not None]
    raw_prs, _ = pairs(rows, key='w945_raw')
    hl_prs, _ = pairs(headline, key='w945')
    pre_prs, _ = pairs(preopen, key='w_day')

    def paired(prs):
        ds = [p['d'] for p in prs]
        t = B.t_stat(ds)
        return {'sessions': len(ds), 'mean_d': None if not ds else round(st.mean(ds), 3),
                't': None if t is None else round(t, 2)}

    longs = [r for r in rows if r['side'] == 'LONG']
    return {
        'confidence_buckets_w945': buckets(rows),
        'confidence_buckets_raw': buckets(rows, key='w945_raw'),
        'spearman_confidence_w945': spearman([float(r['confidence']) for r in scored],
                                             [_num(r['w945']) for r in scored]),
        'top_two_on_raw': paired(raw_prs),
        'material_on_raw': {'material': arm_stats(sv('w945_raw', [r for r in rows if _material(r['material'])])),
                            'routine': arm_stats(sv('w945_raw', [r for r in rows if not _material(r['material'])]))},
        'all_calls': {'w945': arm_stats(sv('w945', rows)), 'raw': arm_stats(sv('w945_raw', rows))},
        'sides': {'long_share': round(len(longs) / len(rows), 3) if rows else None,
                  'LONG': {'w945': arm_stats(sv('w945', longs)), 'raw': arm_stats(sv('w945_raw', longs))},
                  'SHORT': {'w945': arm_stats(sv('w945', [r for r in rows if r['side'] == 'SHORT'])),
                            'raw': arm_stats(sv('w945_raw', [r for r in rows if r['side'] == 'SHORT']))}},
        'market': market(rows),
        'full_vs_headline': disagreement(rows, headline),
        'headline_arm_top_two': paired(hl_prs),
        'preopen_arm': {'top_two_w_day': paired(pre_prs),
                        'material': arm_stats(sv('w_day', [r for r in preopen if _material(r['material'])])),
                        'routine': arm_stats(sv('w_day', [r for r in preopen if not _material(r['material'])])),
                        'confidence_buckets_w_day': buckets(preopen, key='w_day')},
        'session_2026_11_24': [
            {'rank': i + 1, 'call': f"{r['side']} {r['ticker']}", 'confidence': float(r['confidence']),
             'material': _material(r['material']), 'w945': _num(r.get('w945')),
             'raw': _num(r.get('w945_raw'))}
            for i, r in enumerate(ranked(rows).get('2026-11-24', []))],
    }


def run(path=LEDGER, out=OUT):
    all_rows = read(path)
    full, dup = population(all_rows)
    headline, _ = population(all_rows, arm='headline')
    preopen, _ = population(all_rows, arm='preopen')
    prs, skipped = pairs(full)
    result = {
        'registered': 'PREREGISTER_day155b_newsdesk_confidence.md',
        'window': [FIRST, LAST], 'seed': SEED,
        'population': {'full_calls': len(full), 'scored': sum(1 for r in full if _num(r.get('w945')) is not None),
                       'sessions': len({r['session'] for r in full}),
                       'sessions_paired': len(prs), 'sessions_skipped': skipped,
                       'duplicates_dropped': dup},
        'h1_top_two': h1(prs),
        'h2_material': h2(full),
        'descriptive': describe(full, headline, preopen),
    }
    Path(out).write_text(json.dumps(result, indent=1) + '\n')
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--ledger', default=str(LEDGER))
    p.add_argument('--out', default=str(OUT))
    a = p.parse_args(argv)
    r = run(a.ledger, a.out)
    print(json.dumps({'h1': r['h1_top_two']['status'], 'h2': r['h2_material']['status'],
                      'population': r['population']}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
