#!/usr/bin/env python3
"""THE EXECUTION LAB (day-130): every recorded pick under other entries, exits,
hedges and holding periods, measured each evening from the same 5-minute bars
the record is scored on.

Registered in PREREGISTER_day130_learning.md. The owner asked the system to
learn from its results. On 379 replay picks and 93 live ones, the scored
09:45 -> close record is a coin flip. Of the rules tested on it, only the noon
exit was no worse than holding and swung less (H3). Holding past the close,
hedging with the sector ETF and the ATR stops did not pass.

The lab keeps measuring all of them on every new pick, so the comparison grows
every day. It NEVER changes a pick, a size or the scored record
(`data/model_picks.csv`); a rule moves into the record only by the owner's
decision after 40 sessions at the registered bar.

    python execution_lab.py --update        fill the lab from the record (evening)
    python execution_lab.py --table         the comparison, as printed in the review

The lab lives in data/reviews/ so the evening job's existing push carries it.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import math
import statistics as st
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
ROOT = Path(__file__).resolve().parent
LAB = ROOT / 'data' / 'reviews' / 'execution_lab.csv'
ENTRY, NOON, EXIT = dt.time(9, 40), dt.time(11, 55), dt.time(15, 55)
KINDS = ('selected', 'forced', 'pick', 'final', 'board')
KEY = ('session', 'model', 'kind', 'side', 'ticker')
FIELDS = KEY + ('invalid_at', 'r', 'r_open', 'r_noon', 'r_stop_wrongif', 'wrongif_hit', 'atr_pct',
                'r_stop_half_atr', 'r_stop_1atr', 'etf', 'beta', 'r_vs_etf',
                'r_hold1d', 'r_hold3d', 'r_hold5d', 'measured_at')
HOLDS = (('r_hold1d', 1), ('r_hold3d', 3), ('r_hold5d', 5))
RULES = (('r', 'As scored: 09:45 → close'),
         ('r_open', 'Enter at the open'),
         ('r_noon', 'Exit at noon'),
         ('r_stop_wrongif', 'Stop at its own "wrong if"'),
         ('r_stop_half_atr', 'Stop at 0.5 ATR against'),
         ('r_stop_1atr', 'Stop at 1 ATR against'),
         ('r_vs_etf', 'Hedged with its sector ETF'),
         ('r_hold1d', 'Hold to the next close'),
         ('r_hold3d', 'Hold 3 sessions'),
         ('r_hold5d', 'Hold 5 sessions'))
# H3 on the replay and the live record (day-130): the one rule that passed.
NOON_NOTE = ('Exit note (day-130 test): on 379 replay picks, closing at 12:00 ET was no worse than '
             'holding to the close and swung 15% less; the afternoon added nothing. The live record '
             'is still too short to say either way. Not a forecast.')


def _float(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ── one pick on one session ─────────────────────────────────────────────────

def sessions(bars):
    """{date: [(time, open, high, low, close)]} in ET, 09:30 .. 15:55, from a
    5-minute DataFrame (model_picks._yahoo_bars) with Open/High/Low/Close."""
    out = {}
    local = bars.tz_convert(ET) if getattr(bars.index, 'tz', None) is not None else bars
    for ts, row in local.iterrows():
        t = ts.time()
        if not (dt.time(9, 30) <= t <= EXIT):
            continue
        vals = [_float(row.get(k)) for k in ('Open', 'High', 'Low', 'Close')]
        if None in vals:
            continue
        out.setdefault(ts.date(), []).append((t, *vals))
    return out


def _at(day_bars, t):
    for b in day_bars or ():
        if b[0] == t:
            return b
    return None


def _at_or_before(day_bars, t):
    """The last bar at or before `t`: a thin ETF may not trade in every bar."""
    got = [b for b in day_bars or () if b[0] <= t]
    return got[-1] if got else None


def _closes(days):
    """{date: 15:55 close} for complete sessions."""
    return {d: _at(b, EXIT)[4] for d, b in days.items() if _at(b, EXIT)}


def atr_pct(days, day, n=14):
    """ATR as % of the prior close, from the sessions before `day`."""
    prior = sorted(d for d in days if d < day and _at(days[d], EXIT))
    if len(prior) < n + 1:
        return None
    rows = [(max(b[2] for b in days[d]), min(b[3] for b in days[d]), _at(days[d], EXIT)[4]) for d in prior]
    trs = [max(h - l, abs(h - rows[i - 1][2]), abs(l - rows[i - 1][2]))
           for i, (h, l, c) in enumerate(rows) if i > 0][-n:]
    return st.mean(trs) / rows[-1][2] * 100


def beta(days, etf_days, day, n=40):
    a, b = _closes(days), _closes(etf_days)
    common = sorted(d for d in a if d < day and d in b)[-(n + 1):]
    if len(common) < 20:
        return None
    ra = [a[common[i]] / a[common[i - 1]] - 1 for i in range(1, len(common))]
    rb = [b[common[i]] / b[common[i - 1]] - 1 for i in range(1, len(common))]
    vb = st.pvariance(rb)
    if vb <= 0:
        return None
    ma, mb = st.mean(ra), st.mean(rb)
    return sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / len(ra) / vb


def measure(side, day, days, *, invalid_at=None, etf=None, etf_days=None):
    """The same-day rules for one pick. None when the session is incomplete."""
    today = days.get(day)
    e, x, o = _at(today, ENTRY), _at(today, EXIT), _at(today, dt.time(9, 30))
    if not (e and x and o):
        return None
    s = 1 if side == 'LONG' else -1
    entry = e[4]

    def pct(a, b):
        return s * (b / a - 1) * 100
    after = [b for b in today if ENTRY < b[0] <= EXIT]

    def stopped(level):
        for b in after:
            if (b[3] < level) if s > 0 else (b[2] > level):
                return pct(entry, b[4]), True          # that bar's close: conservative
        return pct(entry, x[4]), False
    out = {'r': pct(entry, x[4]), 'r_open': pct(o[1], x[4])}
    noon = _at(today, NOON)
    if noon:
        out['r_noon'] = pct(entry, noon[4])
    if isinstance(invalid_at, (int, float)) and invalid_at > 0:
        out['r_stop_wrongif'], out['wrongif_hit'] = stopped(invalid_at)
    a = atr_pct(days, day)
    if a:
        out['atr_pct'] = a
        out['r_stop_half_atr'] = stopped(entry * (1 - s * a / 200))[0]
        out['r_stop_1atr'] = stopped(entry * (1 - s * a / 100))[0]
    if etf and etf_days:
        be = beta(days, etf_days, day)
        et = etf_days.get(day)
        ee, ex = _at_or_before(et, ENTRY), _at_or_before(et, EXIT)
        if be is not None and ee and ex:
            out.update(etf=etf, beta=be, r_vs_etf=out['r'] - s * be * (ex[4] / ee[4] - 1) * 100)
    return out


def holds(side, day, days):
    """Holding past the close: the k-th later session's close, from the 09:45 entry."""
    e = _at(days.get(day), ENTRY)
    if not e:
        return {}
    s = 1 if side == 'LONG' else -1
    later = sorted(d for d in _closes(days) if d > day)
    return {key: s * (_closes(days)[later[k - 1]] / e[4] - 1) * 100
            for key, k in HOLDS if len(later) >= k}


# ── the ledger ──────────────────────────────────────────────────────────────

def read(path=LAB):
    path = Path(path)
    if not path.is_file():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text())))


def write(rows, path=LAB):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction='ignore')
    w.writeheader()
    for r in sorted(rows, key=lambda r: tuple(str(r.get(k) or '') for k in KEY)):
        w.writerow({k: _cell(r.get(k)) for k in FIELDS})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(out.getvalue())
    tmp.replace(path)


def _cell(v):
    if v is None:
        return ''
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, float):
        return '%.4f' % v
    return str(v)


def update(*, picks=None, lab=LAB, bars_for=None, now=None):
    """Add every scored pick not yet in the lab and fill blank holds. Never
    rewrites a filled cell. Returns counts; a name whose bars fail is counted."""
    import exposure
    import model_picks
    bars_for = bars_for or model_picks._yahoo_bars
    now = now or dt.datetime.now(ET)
    picks = model_picks.read() if picks is None else picks
    rows = read(lab)
    have = {tuple(r[k] for k in KEY): r for r in rows}
    cache, failed = {}, {}

    def days_of(t):
        if t not in cache:
            try:
                cache[t] = sessions(bars_for(t))
            except Exception as exc:          # counted and reported, never silent
                failed[t] = type(exc).__name__
                cache[t] = None
        return cache[t]
    added = filled = skipped = 0
    for p in picks:
        if p.get('kind') not in KINDS or p.get('entry_time') or not p.get('scored_at'):
            continue
        key = tuple(p.get(k) or '' for k in KEY)
        day = dt.date.fromisoformat(p['session'])
        row = have.get(key)
        if row is None:
            days = days_of(p['ticker'])
            if not days or day not in days:
                skipped += 1
                continue
            etf = exposure.position_exposure(p['ticker'])['etf']
            etf = etf if etf and etf != p['ticker'] else None
            m = measure(p['side'], day, days, invalid_at=_float(p.get('invalid_at')),
                        etf=etf, etf_days=days_of(etf) if etf else None)
            if m is None:
                skipped += 1
                continue
            row = {**{k: p.get(k) for k in KEY}, 'invalid_at': p.get('invalid_at') or '', **m,
                   'measured_at': now.isoformat(timespec='seconds')}
            rows.append(row)
            have[key] = row
            added += 1
        blanks = [k for k, _ in HOLDS if row.get(k) in (None, '')]
        if blanks:
            days = days_of(p['ticker'])
            got = holds(p['side'], day, days) if days else {}
            for k in blanks:
                if k in got:
                    row[k] = got[k]
                    filled += 1
    write(rows, lab)
    return {'added': added, 'holds_filled': filled, 'skipped': skipped, 'rows': len(rows),
            'fetch_failures': failed}


# ── the comparison ──────────────────────────────────────────────────────────

def _unique(rows):
    """One row per (session, side, ticker): a name picked by three models is one outcome."""
    seen = {}
    for r in rows:
        seen.setdefault((r['session'], r['side'], r['ticker']), r)
    return list(seen.values())


def _line(rows, key, label):
    pairs = [(_float(r['r']), _float(r.get(key))) for r in rows]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    if not pairs:
        return '| %s | 0 | — | — | — | — |' % label
    vals = [b for _, b in pairs]
    diff = st.mean(b - a for a, b in pairs)
    sd = st.pstdev(vals) if len(vals) > 1 else 0.0
    return '| %s | %d | %.0f%% | %+.2f%% | %s | %.2f |' % (
        label, len(vals), 100 * sum(v > 0 for v in vals) / len(vals), st.mean(vals),
        '—' if key == 'r' else '%+.2f%%' % diff, sd)


def table(rows=None):
    rows = read() if rows is None else rows
    models = _unique([r for r in rows if r['model'] not in ('engine', 'top2count', 'top2memory')])
    top2 = [r for r in rows if r['model'] == 'top2']
    out = ['## Execution lab — the same picks, executed other ways (day-130)',
           'Every scored pick, measured each evening. A rule is shown, never applied: the record '
           'and the picks are unchanged. "vs scored" is the same picks\' difference from holding '
           '09:45 → close. On the 379-pick replay only the noon exit was no worse with less swing.']
    for title, sub in (('Model picks (one row per name and side)', models), ('Top 2', top2)):
        sessions_ = len({r['session'] for r in sub})
        out += ['', '**%s** — %d picks over %d sessions' % (title, len(sub), sessions_), '',
                '| Rule | Picks | Right | Mean | vs scored | sd |', '|---|---:|---:|---:|---:|---:|']
        out += [_line(sub, k, label) for k, label in RULES]
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--update', action='store_true')
    p.add_argument('--table', action='store_true')
    a = p.parse_args(argv)
    if a.update:
        import json
        print(json.dumps(update(), indent=1))
    if a.table or not a.update:
        print('\n'.join(table()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
