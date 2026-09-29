"""TOP 2 — the two names the language models agree on most, at the top of the email.

The owner, 2026-09-29: "at the top ... two stock picks, long and/or short, that
all language models agree are the opportunities of the day ... not more than
two and not less than two, every day."

Agreement cannot be forced, so it is COUNTED. Each (ticker, side) put forward by
a desk collects the models that back it:

  Claude    its sealed selection
  DeepSeek  its selection
  Jev       its selection, its FORCED pick for that side, or a name in its own
            top-ranked list for that side (Jev ranks every name; a place in its
            ranked list is its stated preference, labelled as a rank)

The two DISTINCT names with the most backing models lead, ties broken by
the strongest kind of backing (a selection, then a forced pick, then a ranked
name), then by Jev's rank, then by the strongest single model's own number (never an
average — house rule), then alphabetically. A name two models put on OPPOSITE
sides is excluded while any other name remains, and labelled SPLIT if it has
to fill a slot.

Exactly two whenever two names exist at all. When all three models are down
there are none, and the section says why rather than inventing a name. Every
pick says how many of the models that answered back it: "3 of 3" is the
owner's case; "1 of 3" is printed as such, with who, because a slot filled by
one model is not agreement. The three models read the SAME brief, so agreement
is not independent confirmation, and day-117's replay found each of them no
better than random on these inputs. The section is recorded (model `top2`) and
scored on the same yardstick as every desk (PREREGISTER_day119_top2.md).
"""
from __future__ import annotations

from consensus_picks import flags

MODELS = ('claude', 'deepseek', 'jev')
NAMES = {'claude': 'Claude', 'deepseek': 'DeepSeek', 'jev': 'Jev'}
PICKS = 2
KIND_ORDER = {'selected': 0, 'forced': 1, 'ranked': 2}


def _answered(snap):
    return isinstance(snap, dict) and snap.get('status') in ('READY', 'NO_OPPORTUNITY')


def _support(who):
    """model -> its strongest backing entry for this (ticker, side)."""
    best = {}
    for w in who:
        if w['model'] not in MODELS:
            continue
        cur = best.get(w['model'])
        if cur is None or KIND_ORDER[w['kind']] < KIND_ORDER[cur['kind']]:
            best[w['model']] = w
    return best


def _jev_rank(jev, ticker, side):
    ranked = (jev or {}).get(side.lower() + '_ranked') or []
    for i, p in enumerate(ranked, 1):
        if isinstance(p, dict) and p.get('ticker') == ticker:
            return i
    return None


def _describe(model, w, rank):
    s = w.get('strength')
    num = f' {s:.2f}' if isinstance(s, (int, float)) else ''
    if model == 'jev':
        if w['kind'] == 'forced':
            return f'Jev forced{num}'
        if w['kind'] == 'ranked':
            return f'Jev ranked #{rank}' if rank else 'Jev ranked'
    return NAMES[model] + num


def select(claude, deepseek, jev, *, wire=None):
    """The section as a dict: exactly two picks whenever two names exist."""
    snaps = {'claude': claude, 'deepseek': deepseek, 'jev': jev}
    answered = [m for m in MODELS if _answered(snaps[m])]
    flagged = flags(claude, deepseek, jev)
    sides_of = {}
    for (ticker, side), who in flagged.items():
        if _support(who):
            sides_of.setdefault(ticker, set()).add(side)
    candidates = []
    for (ticker, side), who in flagged.items():
        support = _support(who)
        if not support:
            continue
        rank = _jev_rank(jev, ticker, side)
        split = len(sides_of.get(ticker, ())) > 1
        strength = max((w['strength'] for w in support.values()
                        if isinstance(w.get('strength'), (int, float))), default=0.0)
        selected = any(w['kind'] == 'selected' for w in support.values())
        best_kind = min(KIND_ORDER[w['kind']] for w in support.values())
        lead = next((m for m in ('claude', 'deepseek') if m in support), 'jev')
        candidates.append({
            'ticker': ticker, 'side': side, 'split': split,
            'votes': len(support), 'models': [m for m in MODELS if m in support],
            'backing': [_describe(m, support[m], rank) for m in MODELS if m in support],
            'selected': selected, 'best_kind': best_kind, 'jev_rank': rank, 'strength': strength, 'lead': NAMES[lead],
            'reason': support[lead].get('reason'), 'invalid_at': support[lead].get('invalid_at'),
            'confidence': support[lead].get('strength')})
    candidates.sort(key=lambda c: (c['split'], -c['votes'], c['best_kind'],
                                   c['jev_rank'] or 99, -c['strength'], c['ticker']))
    picks, seen = [], set()
    for c in candidates:
        if c['ticker'] in seen:
            continue
        seen.add(c['ticker'])
        picks.append(c)
        if len(picks) == PICKS:
            break
    for p in picks:
        p['agreement'] = f"{p['votes']} of {len(answered)}"
        if wire and wire.get(p['ticker']):
            p['wire'] = wire[p['ticker']]
    out = {'picks': picks, 'answered': [NAMES[m] for m in answered],
           'status': 'READY' if len(picks) == PICKS else 'SHORT'}
    if len(picks) < PICKS:
        out['reason'] = ('No model answered today, so there is no name to put here.'
                         if not answered else
                         f'Only {len(picks)} name(s) were put forward by any model today.')
    return out


def _verdict(p, answered):
    n = len(answered)
    if p['split']:
        return 'SPLIT — models took opposite sides'
    if p['votes'] == n and n > 1:
        return f'ALL {n} AGREE'
    if p['votes'] >= 2:
        return f"{p['votes']} of {n} agree"
    return f'1 of {n} — no agreement on this slot'


def table(section):
    """The section as text lines, one table. Used by every email and view."""
    if not section:
        return []
    out = ['## Top 2 — where the models agree',
           'Ranked by how many of the models back each name (Claude, DeepSeek, Jev on the '
           'same brief). Agreement is not confirmation: they read the same inputs, and none '
           'has beaten random picks on the replay.']
    picks = section.get('picks') or []
    if not picks:
        return out + [section.get('reason') or 'No pick today.']
    answered = section.get('answered') or []
    out += ['', '| # | Pick | Agreement | Backed by | Wrong if | Wire release | Why (lead model) |',
            '|---|---|---|---|---|---|---|']
    for i, p in enumerate(picks, 1):
        wrong = (f"{'below' if p['side'] == 'LONG' else 'above'} {p['invalid_at']:g}"
                 if isinstance(p.get('invalid_at'), (int, float)) else '—')
        w = p.get('wire')
        release = f"{w['at']} {w['title']}"[:90].replace('|', '/') if w else '—'
        why = str(p.get('reason') or ('gives probabilities, not reasons' if p['lead'] == 'Jev'
                                      else '—')).replace('|', '/')[:200]
        out.append(f"| {i} | {p['side']} {p['ticker']} | {_verdict(p, answered)} | "
                   f"{', '.join(p['backing'])} | {wrong} | {release} | {p['lead']}: {why} |")
    if section.get('reason'):
        out.append(section['reason'])
    return out
