"""Part 3 — the owner's strategy: 1–2 names the models agree on, confirmed at the open.

OWNER, 2026-09-26. One more section at the end of the daily email that always
names one or two stocks — "there's no way to have nothing" — by this rule:

  1. FILTER  names flagged on the SAME side by more than one model (Claude,
             DeepSeek, Jev — Jev's selected, forced or top-ranked names all
             count as a Jev flag, because Jev rarely clears its own gate).
  2. CONFIRM LONG only if price > VWAP and rvol > 1.2; SHORT only if
             price < VWAP and rvol > 1.2.
  3. MODEL   Claude's sealed pre-open pick leads when it is among the flags;
             otherwise DeepSeek's, confirmed by the opening volume surge.

WHAT "PRICE", "VWAP" AND "RVOL" MEAN HERE — measured at the report, from the
completed five-minute bars stamped 09:35 and 09:40 (continuous trading
09:35–09:45):

  price  close of the 09:40 bar — the 09:45 price, the SAME entry reference the
         scoreboard uses, so this section is scored on the desks' yardstick
  VWAP   volume-weighted typical price of those bars
  rvol   today's 09:35–09:45 volume / the MEDIAN 09:35–09:45 volume of up to 20
         prior sessions (at least 5 required)

WHY NOT THE 09:30 BAR (MEASURED 2026-09-26). Yahoo's 09:30 TSX bar reports ZERO
volume on most sessions and the whole opening auction on a few: CP.TO read 0 on
23 of 25 sessions and 1,017,019 on 09-18; NTR.TO 1,637,051 on 09-22. Counting
it made a mean baseline read most mornings as rvol 0.2–0.6 and one as rvol 51.
A number that swings on the provider's auction bookkeeping is not a volume
surge. The median is used for the same reason: one auction day is not a norm.

The staged `rvol`/`vwap` the models were shown are the PREVIOUS session's
(factor_grounding: "completed session volume … not current opening RVOL"). The
owner's rule is about the open, so it is measured at the open; the staged
figures are never substituted for it. A name whose opening bars could not be
fetched is NOT MEASURED — never "confirmed" by default.

NEVER EMPTY, NEVER DRESSED UP. Two names are always named when two candidates
exist. Each carries its tier, and a name that did not meet the rule says RULE
NOT MET in capitals: the rule says do not enter it, and it is printed only
because the owner asked that the section never be blank. Both are recorded in
data/model_picks.csv as model `consensus`, kind `rule_met` or `rule_not_met`,
and scored separately — pooling them would hide whether the rule does anything.

THE CLAIMED EDGE IS NOT EVIDENCE. The owner's "above 80%" and "4/4" come from
two sessions and a handful of picks; the Wilson interval on 4/4 runs from 51%
to 100%. PREREGISTER_day115_consensus.md states the bar the scored record must
clear before this section is described as anything but an observation.

No share count. The desks above are the sized boards; this is an overlay on
them, and nothing here places, modifies or cancels an order.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from diagnostics import safe_detail

ET = ZoneInfo('America/New_York')
RVOL_MIN = 1.2                      # owner, 2026-09-26, both sides
OPEN_BARS = (dt.time(9, 35), dt.time(9, 40))     # see the module note on 09:30
READY_AT = dt.time(9, 46)
BASELINE_MAX, BASELINE_MIN = 20, 5
PICKS = 2
MODELS = ('claude', 'deepseek', 'jev')
NAMES = {'claude': 'Claude', 'deepseek': 'DeepSeek', 'jev': 'Jev'}
MAX_MEASURED = 16                   # names fetched at 09:46; the rest are NOT MEASURED
TIERS = {
    'A': 'CONSENSUS + CONFIRMED',
    'B': 'ONE MODEL + CONFIRMED',
    'C': 'CONSENSUS — RULE NOT MET',
    'D': 'FILLER — RULE NOT MET',
}
RULE = ('Flagged by two or more models on the same side; LONG only above today\'s VWAP, '
        'SHORT only below it, and opening rvol > %.1f either way.' % RVOL_MIN)


# ── candidates ──────────────────────────────────────────────────────────────

def _usable(snap):
    return (snap or {}).get('status') in ('READY', 'NO_OPPORTUNITY')


def flags(claude, deepseek, jev, engine_legs=()):
    """Every (ticker, side) any source put forward, with who flagged it. Pure."""
    out = {}

    def add(model, kind, side, pick, strength=None):
        if not isinstance(pick, dict) or not isinstance(pick.get('ticker'), str):
            return
        out.setdefault((pick['ticker'], side), []).append({
            'model': model, 'kind': kind,
            'strength': strength if strength is not None
            else pick.get('confidence', pick.get('probability')),
            'invalid_at': pick.get('invalid_at'), 'reason': pick.get('reason')})

    for model, snap in (('claude', claude), ('deepseek', deepseek)):
        if _usable(snap):
            for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
                for pick in snap.get(key) or []:
                    add(model, 'selected', side, pick)
    if _usable(jev):
        for side, key in (('LONG', 'longs'), ('SHORT', 'shorts')):
            for pick in jev.get(key) or []:
                add('jev', 'selected', side, pick)
            add('jev', 'forced', side, jev.get('forced_' + key[:-1]))
            for pick in jev.get(key[:-1] + '_ranked') or []:
                add('jev', 'ranked', side, pick)
    for leg in engine_legs or []:
        if leg.get('side') in ('LONG', 'SHORT'):
            add('engine', 'board', leg['side'], {'ticker': leg.get('ticker'),
                                                 'confidence': leg.get('p_sided')})
    return out


def names_from(snaps):
    """The tickers worth measuring, most-flagged first, capped at MAX_MEASURED."""
    counted = {}
    for (ticker, _side), who in flags(*snaps).items():
        counted[ticker] = max(counted.get(ticker, 0),
                              len({w['model'] for w in who if w['model'] in MODELS}))
    return [t for t, _ in sorted(counted.items(), key=lambda kv: (-kv[1], kv[0]))][:MAX_MEASURED]


def staged_names(state_dir, now):
    """The candidates' tickers from the three sealed snapshots — known before
    09:46, so they are fetched beside the quote request. Pure file reads."""
    snaps = []
    for module in ('claude_opportunities', 'deepseek_opportunities', 'jev_opportunities'):
        try:
            snaps.append(__import__(module).load_prepared(state_dir, now))
        except Exception:
            snaps.append({})
    return names_from(snaps)


# ── confirmation at the open ────────────────────────────────────────────────

def opening(bars, day):
    """Price, VWAP and rvol from the completed opening bars. Pure.

    Returns {'status': 'OK', ...} or {'status': <why not measured>}."""
    if bars is None or getattr(bars, 'empty', True):
        return {'status': 'NO_BARS'}
    local = bars.tz_convert(ET)
    by_day = {}
    for ts, row in local.iterrows():
        if ts.time() in OPEN_BARS:
            by_day.setdefault(ts.date(), {})[ts.time()] = row
    today = by_day.get(day) or {}
    if set(today) != set(OPEN_BARS):
        return {'status': 'OPENING_BARS_INCOMPLETE'}
    rows = [today[t] for t in OPEN_BARS]
    volume = sum(float(r['Volume'] or 0) for r in rows)
    if not volume > 0:
        return {'status': 'NO_OPENING_VOLUME'}
    vwap = sum((float(r['High']) + float(r['Low']) + float(r['Close'])) / 3 * float(r['Volume'] or 0)
               for r in rows) / volume
    price = float(rows[-1]['Close'])
    prior = [sum(float(b[t]['Volume'] or 0) for t in OPEN_BARS)
             for d, b in sorted(by_day.items()) if d < day and set(b) == set(OPEN_BARS)]
    prior = [v for v in prior if v > 0][-BASELINE_MAX:]
    if len(prior) < BASELINE_MIN:
        return {'status': 'RVOL_BASELINE_SHORT', 'price': round(price, 4), 'vwap': round(vwap, 4),
                'baseline_sessions': len(prior)}
    baseline = statistics.median(prior)
    if not all(math.isfinite(x) for x in (price, vwap, baseline)):
        return {'status': 'NON_FINITE'}
    return {'status': 'OK', 'price': round(price, 4), 'vwap': round(vwap, 4),
            'price_vs_vwap_pct': round((price / vwap - 1) * 100, 3),
            'open_volume': volume, 'baseline_volume': round(baseline, 1),
            'baseline_sessions': len(prior), 'rvol': round(volume / baseline, 3)}


def passes(side, measured):
    """(met, why) for the owner's rule. A name not measured never meets it."""
    if (measured or {}).get('status') != 'OK':
        return False, 'not measured (%s)' % (measured or {}).get('status', 'NO_DATA')
    above = measured['price'] > measured['vwap']
    below = measured['price'] < measured['vwap']
    surge = measured['rvol'] > RVOL_MIN
    where = ('above' if above else 'below' if below else 'at') + ' VWAP'
    text = '09:45 %.2f %s %.2f (%+.2f%%), rvol %.2f' % (
        measured['price'], where, measured['vwap'], measured['price_vs_vwap_pct'], measured['rvol'])
    ok = surge and (above if side == 'LONG' else below)
    return ok, text


def measure(tickers, now, *, fetch=None, delay=0.0, budget=12.0, workers=4):
    """Opening measurements for `tickers`. Read-only; bounded; one 429 stops it.

    `delay` lets the engine's own acquisition go first — these requests share
    its egress IP. A name that fails is NOT MEASURED with its class, never
    silently dropped (house rule 1)."""
    if not tickers:
        return {}
    local = now.astimezone(ET)
    if local.time() < READY_AT:
        # The 09:40 bar is still forming until 09:45 (the same guard as r945):
        # its close would be a live price, not the 09:45 print.
        return {t: {'status': 'BEFORE_09:46'} for t in tickers}
    if delay:
        time.sleep(delay)
    deadline = time.monotonic() + budget
    if fetch is None:
        from adapters import YahooDirectAdapter
        adapter = YahooDirectAdapter(timeout=8)
        adapter.chart_deadline = deadline

        def fetch(t):
            return adapter._bars_df(adapter._chart(t, '5m', '1mo'))
    stop = {'why': None}

    def one(t):
        if stop['why']:
            return t, {'status': stop['why']}
        if time.monotonic() >= deadline:
            return t, {'status': 'BUDGET_EXHAUSTED'}
        try:
            return t, opening(fetch(t), now.date())
        except Exception as exc:
            if 'RateLimit' in type(exc).__name__:
                stop['why'] = 'RATE_LIMITED'
            return t, {'status': 'FETCH_FAILED: ' + type(exc).__name__}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as ex:
        return dict(ex.map(one, tickers))


# ── the selection ───────────────────────────────────────────────────────────

def _lead(who):
    """Step 3 of the rule: Claude's sealed pick leads, else DeepSeek's, else Jev's."""
    for model, kinds in (('claude', ('selected',)), ('deepseek', ('selected',)),
                         ('jev', ('selected', 'forced', 'ranked')), ('engine', ('board',))):
        for kind in kinds:
            hit = next((w for w in who if w['model'] == model and w['kind'] == kind), None)
            if hit:
                return hit
    return who[0]


def _lead_label(lead):
    return {'claude': 'Claude — sealed before the open',
            'deepseek': 'DeepSeek — confirmed by the opening volume',
            'jev': 'Jev (%s)' % lead['kind'],
            'engine': 'baseline engine (k-NN)'}[lead['model']]


def select(claude, deepseek, jev, engine_legs=(), measured=None, *, measured_note=None):
    """The section: up to PICKS names, never zero while any candidate exists. Pure."""
    measured = measured or {}
    everything = flags(claude, deepseek, jev, engine_legs)
    sides = {}
    for ticker, side in everything:
        sides.setdefault(ticker, set()).add(side)
    conflicts = sorted(t for t, s in sides.items() if len(s) > 1)
    rows = []
    for (ticker, side), who in everything.items():
        if ticker in conflicts:
            continue
        models = sorted({w['model'] for w in who if w['model'] in MODELS}, key=MODELS.index)
        m = measured.get(ticker) or {'status': 'NOT_FETCHED'}
        met, why = passes(side, m)
        agree = len(models) >= 2
        tier = ('A' if met and agree else 'B' if met and models else
                'C' if agree else 'D')
        lead = _lead(who)
        level = next((w['invalid_at'] for w in who
                      if w['model'] in ('claude', 'deepseek') and w.get('invalid_at') is not None), None)
        past = None
        if level is not None and m.get('status') == 'OK':
            past = m['price'] < level if side == 'LONG' else m['price'] > level
        rows.append({'ticker': ticker, 'side': side, 'tier': tier, 'tier_label': TIERS[tier],
                     'rule_met': met, 'confirmation': why, 'measured': m,
                     'models': [NAMES[x] for x in models],
                     'flags': ['%s %s%s' % (NAMES.get(w['model'], 'Engine'), w['kind'],
                                            '' if w['strength'] is None else ' %.2f' % float(w['strength']))
                               for w in who],
                     'lead': _lead_label(lead), 'lead_model': lead['model'],
                     'confidence': lead.get('strength'),
                     'invalid_at': level, 'past_invalid_at_entry': past,
                     'reason': lead.get('reason')})
    rows.sort(key=lambda r: (r['tier'], -len(r['models']), 'Claude' not in r['models'],
                             'DeepSeek' not in r['models'], -(r['measured'].get('rvol') or 0),
                             -(float(r['confidence']) if r['confidence'] is not None else 0),
                             r['ticker']))
    picks = rows[:PICKS]
    measured_ok = sum(1 for v in measured.values() if v.get('status') == 'OK')
    out = {'status': 'READY' if picks else 'UNAVAILABLE', 'rule': RULE, 'rvol_min': RVOL_MIN,
           'picks': picks, 'considered': len(rows), 'conflicts': conflicts,
           'rule_met_count': sum(r['rule_met'] for r in rows),
           'measured': '%d of %d candidate names measured at the open' % (
               measured_ok, len({r['ticker'] for r in rows})),
           'measured_note': measured_note}
    if not picks:
        out['reason'] = ('no model and no engine produced a candidate today — every source '
                         'above is unavailable, so there is nothing to confirm')
    return out


# ── rendering (one text implementation, used by the email and the full report) ──

def lines(section):
    out = ['', '## Part 3 — Strategy picks · consensus + open confirmation']
    if not section:
        return out + ['Not computed in this publication.']
    out.append(section['rule'] + ' ' + section.get('measured', '') + '.')
    if section.get('measured_note'):
        out.append(section['measured_note'])
    if not section.get('picks'):
        return out + ['No pick: ' + section.get('reason', 'no candidate') + '.']
    out += ['| Tier | Name / side | Flagged by | At the open | Wrong if |', '|---|---|---|---|---:|']
    for p in section['picks']:
        level = '—' if p['invalid_at'] is None else '%.2f' % float(p['invalid_at'])
        if p.get('past_invalid_at_entry'):
            level += ' (already past)'
        out.append('| %s | %s %s | %s | %s | %s |' % (
            p['tier_label'], p['ticker'], p['side'], '; '.join(p['flags']),
            p['confirmation'], level))
    for p in section['picks']:
        verdict = ('meets the rule' if p['rule_met']
                   else 'RULE NOT MET — the rule says do not enter; shown so this section is never empty')
        reason = safe_detail(p.get('reason') or '', 150)
        out.append('- %s %s: %s. Lead: %s.%s' % (
            p['side'], p['ticker'], verdict, p['lead'], (' ' + reason) if reason else ''))
    if section.get('conflicts'):
        out.append('Excluded, models on opposite sides: ' + ', '.join(section['conflicts']) + '.')
    out.append('No share count: an overlay on the desks above, scored separately. The '
               'claimed hit rates behind this rule rest on two sessions; its own record '
               'is the scoreboard line.')
    return out

