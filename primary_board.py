"""Part 1's desks: Claude, DeepSeek and Jev, each sized from its own picks.

DAY-114. The owner asked for three parallel sections — Claude's picks, DeepSeek's
and Jev's — each from its own model and each sized, so they can be compared day
by day. `build` makes one desk; `brief` calls it three times with the same
quotes, clock and book, so no desk is advantaged by the sizing. The history
below is why the engine stopped leading.

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

The verifiable record when this was built is in the commit message: 3 of 8 for
DeepSeek and 3 of 12 for the engine on the same yardstick — neither has shown an
edge yet. The leaderboard exists so that stops being a matter of opinion.
"""
from __future__ import annotations

import math

from quotes import CORROBORATED, number

PRIMARY_LABEL = 'DeepSeek'


# THE THREE DESKS (owner, 2026-09-22): Claude, DeepSeek and Jev, each in its
# own section, each sized by the same rule from its own SELECTED picks. The
# order is the order they are printed. `key` is the report's evidence key.
DESKS = (('claude', 'Claude', 'claude'), ('deepseek', 'DeepSeek', 'opportunities'),
         ('jev', 'Jev', 'jev'))


def staged_tickers(state_dir, now):
    """Every desk's staged SELECTED picks — known before 09:46, so they ride in
    the ONE equity quote request. Pure file reads; a desk that fails costs only
    its own names and never raises."""
    out = set()
    for module in ('claude_opportunities', 'deepseek_opportunities', 'jev_opportunities'):
        try:
            snap = __import__(module).load_prepared(state_dir, now)
        except Exception:
            continue
        out |= {p['ticker'] for key in ('longs', 'shorts') for p in snap.get(key) or []
                if isinstance(p, dict) and isinstance(p.get('ticker'), str)}
    return out


def build(evidence, quotes, cfg, clock, shadow, source=PRIMARY_LABEL):
    """One desk's sized board from that source's SELECTED picks — never a
    ranked or forced name, which are not selections."""
    evidence = evidence or {}
    status = evidence.get('status')
    out = {'source': source, 'model': evidence.get('model'), 'status': status,
           'legs': [], 'reason': None, 'sizing': None}
    if status not in ('READY', 'NO_OPPORTUNITY'):
        out['reason'] = evidence.get('reason') or 'the primary ranking was not available'
        return out
    picks = [('LONG', p) for p in evidence.get('longs') or []] + \
            [('SHORT', p) for p in evidence.get('shorts') or []]
    if not picks:
        out['reason'] = 'no SELECTED pick on either side today'
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
            'ticker': ticker, 'side': side, 'role': 'desk', 'desk': source,
            'status': 'ABSTAIN' if reasons else ('SHADOW' if shadow else 'ELIGIBLE'),
            'reasons': reasons, 'quote': q,
            'entry_reference': fill, 'entry_spread_bps': number(q.get('spread_bps')),
            'currency': q.get('currency') or ('CAD' if ticker.endswith('.TO') else 'USD'),
            'baseline_shares': 0 if reasons else shares,
            'baseline_alloc': 0 if reasons else round(shares * fill, 2),
            # Jev reports a probability where the others report a confidence;
            # both are the model's own number and labelled so where printed.
            'confidence': pick.get('confidence', pick.get('probability')),
            'invalid_at': pick.get('invalid_at'),
            'reason': pick.get('reason')})
    return out


def headline_legs(intra):
    """The legs Part 1 leads with: every desk's, else the engine's.

    One function, because the subject line and the email hero must describe the
    same board — a subject computed from a different board than the one printed
    under it could say DO NOT TRADE over sized legs. A publication from before
    the desks existed carries `primary` (DeepSeek alone, 2026-09-22)."""
    intra = intra or {}
    legs = [l for d in intra.get('desks') or [] for l in d.get('legs') or []]
    legs = legs or (intra.get('primary') or {}).get('legs') or []
    return legs or intra.get('legs') or []


LEADERBOARD = (('claude_selected', 'Claude'),
               ('deepseek_selected', 'DeepSeek'),
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
