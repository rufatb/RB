"""Part 1's headline board: the owner's chosen primary source, sized.

OWNER DECISION, 2026-09-22. The baseline k-NN engine leads Part 1 no longer. Its
own walk-forward research is 809 legs at 50.1% and -0.005% per leg, its live
record is 48.6% over 107 legs with average win smaller than average loss, and on
2026-09-22 it went 0 for 4 at -1.56% per pick. The owner chose DeepSeek's own
picks as the headline instead, sized with share counts, and the engine becomes a
scored comparison row beneath them.

What this does NOT change, and why each matters:

- Eligibility is exactly the engine's. A leg is sized only when the 09:46 quote
  is venue-validated (OK) or CORROBORATED with the owner's acceptance switch on,
  and only inside the eligible clock. Anything else ABSTAINS with its reason and
  renders NO share count — a row with a size is an order ticket whatever the
  status column says.
- Nothing is placed, modified or cancelled. The size is a hypothetical
  equal-dollar split of the same book the engine uses (`risk.account_equity` x
  `risk.max_position_pct`).
- DeepSeek's confidence stays its OWN number. The headline carries the source's
  scored forward record beside the picks, every day, so the choice can be judged
  on outcomes rather than on how the picks read.

The verifiable record when this was built is in the commit message: 3 of 9 for
DeepSeek and 3 of 12 for the engine on the same yardstick — neither has shown an
edge yet. The leaderboard exists so that stops being a matter of opinion.
"""
from __future__ import annotations

import math

from quotes import CORROBORATED, number

PRIMARY_LABEL = 'DeepSeek'


def staged_tickers(state_dir, now):
    """Tickers the staged DeepSeek snapshot picked — known before 09:46, so they
    can ride in the ONE equity quote request. A pure file read; never raises."""
    try:
        import deepseek_opportunities
        snap = deepseek_opportunities.load_prepared(state_dir, now)
    except Exception:
        return set()
    return {p['ticker'] for key in ('longs', 'shorts') for p in snap.get(key) or []
            if isinstance(p, dict) and isinstance(p.get('ticker'), str)}


def build(evidence, quotes, cfg, clock, shadow):
    """The sized headline board from the primary source's SELECTED picks."""
    evidence = evidence or {}
    status = evidence.get('status')
    out = {'source': PRIMARY_LABEL, 'model': evidence.get('model'), 'status': status,
           'legs': [], 'reason': None, 'sizing': None}
    if status not in ('READY', 'NO_OPPORTUNITY'):
        out['reason'] = evidence.get('reason') or 'the primary ranking was not available'
        return out
    picks = [('LONG', p) for p in evidence.get('longs') or []] + \
            [('SHORT', p) for p in evidence.get('shorts') or []]
    if not picks:
        out['reason'] = 'the model returned no pick on either side'
        return out
    risk = cfg.get('risk') or {}
    book = number(risk.get('account_equity'), positive=True)
    pct = number(risk.get('max_position_pct'), positive=True)
    per_leg = (book * pct / 100 / len(picks)) if book and pct else None
    out['sizing'] = ({'book': book * pct / 100, 'per_leg': per_leg, 'legs': len(picks),
                      'rule': 'equal-dollar split of the engine\'s book, in each listing\'s own currency'}
                     if per_leg else None)
    accept = bool((cfg.get('execution') or {}).get('accept_corroborated_bbo'))
    for side, pick in picks:
        ticker = pick['ticker']
        q = (quotes or {}).get(ticker) or {}
        reasons = []
        if not clock.get('eligible'):
            reasons.append(clock.get('status') or 'outside the entry window')
        if q.get('status') == 'OK' or (q.get('status') == CORROBORATED and accept):
            pass
        else:
            reasons.append(q.get('reason') or 'no validated 09:46 quote for this name')
        fill = number(q.get('ask' if side == 'LONG' else 'bid'), positive=True)
        if fill is None and not reasons:
            reasons.append('no executable side of the book')
        if per_leg is None and not reasons:
            reasons.append('no book size configured')
        shares = math.floor(per_leg / fill) if not reasons else 0
        if not reasons and shares < 1:
            reasons.append('one share exceeds the per-leg allocation')
        out['legs'].append({
            'ticker': ticker, 'side': side, 'role': 'primary',
            'status': 'ABSTAIN' if reasons else ('SHADOW' if shadow else 'ELIGIBLE'),
            'reasons': reasons, 'quote': q,
            'entry_reference': fill, 'entry_spread_bps': number(q.get('spread_bps')),
            'currency': q.get('currency') or ('CAD' if ticker.endswith('.TO') else 'USD'),
            'baseline_shares': 0 if reasons else shares,
            'baseline_alloc': 0 if reasons else round(shares * fill, 2),
            'confidence': pick.get('confidence'), 'invalid_at': pick.get('invalid_at'),
            'reason': pick.get('reason')})
    return out


LEADERBOARD = (('deepseek_selected', 'DeepSeek (primary)'),
               ('engine_board', 'Baseline engine (k-NN)'),
               ('jev_selected', 'Jev (selected)'),
               ('jev_forced', 'Jev (forced)'))


def leaderboard(card):
    """Every source on ONE yardstick: 09:45 bar close to session close, no cost."""
    rows = []
    for key, name in LEADERBOARD:
        c = (card or {}).get(key)
        rows.append({'source': name, 'picks': (c or {}).get('picks', 0),
                     'hits': (c or {}).get('hits', 0), 'rate': (c or {}).get('rate'),
                     'mean_r_pct': (c or {}).get('mean_r_pct'),
                     'sessions': (c or {}).get('sessions', 0),
                     'ci95': (c or {}).get('ci95')})
    return rows
