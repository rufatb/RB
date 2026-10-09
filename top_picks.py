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

The names with the most backing models lead, ties broken by the strongest kind
of backing (a selection, then a forced pick, then a ranked name), then by Jev's
rank, then by the strongest single model's own number (never an average — house
rule), then alphabetically.

AGREEMENT ONLY (owner's decision, 2026-10-01, after a "1 of 3" filler slot was
traded and lost): a name fills a slot only when at least TWO models back it on
the same side, at least one of them with a real selection, the models did not
split on it, and it is not void at entry (day-120). At most two, NEVER padded:
on a day with no agreement the section says so in place of a name, and the
email hero says "no agreement — nothing to act on". The earlier rule ("exactly
two every day", 2026-09-29) filled empty slots with one model's forced pick,
labelled "1 of 3"; those recorded rows stay as they are.

The three models read the SAME brief, so agreement is not independent
confirmation, and day-117's replay found each of them no better than random on
these inputs. The section is recorded (model `top2`, `prompt_version`
day121-agreement) and scored on the same yardstick as every desk
(PREREGISTER_day119_top2.md and its 2026-10-01 amendment).
"""
from __future__ import annotations

from consensus_picks import flags

# Gemini joined as the fourth model on 2026-10-03 (owner). The rule is
# unchanged: a slot needs at least TWO models on the same side.
MODELS = ('claude', 'deepseek', 'gemini', 'jev')
NAMES = {'claude': 'Claude', 'deepseek': 'DeepSeek', 'gemini': 'Gemini', 'jev': 'Jev'}
PICKS = 2                      # at most; never padded (2026-10-01)
RULE_VERSION = 'day121-agreement'
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


def select(claude, deepseek, jev, *, gemini=None, wire=None, prices=None, session=None):
    """The section as a dict: up to two names the models AGREE on, never padded.

    `prices` ({ticker: 09:46 mark}) turns on the day-120 entry check: a pick
    whose lead model's own "wrong if" is already crossed is VOID AT ENTRY and
    sorts after every clean name, as a SPLIT one does. Without prices (the
    picks-only and late emails) nothing is checked and nothing moves.
    """
    import entry_checks
    # No leader (day-124 amendment): whose reason and "wrong if" a shared name
    # shows rotates daily; without a session it is the old fixed order.
    import council
    order = council.lead_order(session)
    snaps = {'claude': claude, 'deepseek': deepseek, 'gemini': gemini, 'jev': jev}
    answered = [m for m in MODELS if _answered(snaps[m])]
    flagged = flags(claude, deepseek, jev, gemini=gemini)
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
        lead = next((m for m in order if m in support), 'jev')
        candidates.append({
            'ticker': ticker, 'side': side, 'split': split,
            'votes': len(support), 'models': [m for m in MODELS if m in support],
            'backing': [_describe(m, support[m], rank) for m in MODELS if m in support],
            'selected': selected, 'best_kind': best_kind, 'jev_rank': rank, 'strength': strength, 'lead': NAMES[lead],
            'reason': support[lead].get('reason'), 'invalid_at': support[lead].get('invalid_at'),
            'confidence': support[lead].get('strength')})
        if prices is not None:
            c = candidates[-1]
            c['entry_price'] = prices.get(ticker)
            c['entry_check'] = entry_checks.check(side, c['invalid_at'], c['entry_price'])
    candidates.sort(key=lambda c: (c['split'], c.get('entry_check') == 'VOID', -c['votes'], c['best_kind'],
                                   c['jev_rank'] or 99, -c['strength'], c['ticker']))
    # AGREEMENT ONLY (owner's decision, 2026-10-01): a slot is filled only by a
    # name at least two models back on the same side, one of them a real
    # selection, not split and not void at entry. A day without one prints
    # that there is no agreement; it is never filled with one model's pick.
    picks, seen = [], set()
    for c in candidates:
        if c['ticker'] in seen or not _agreed(c):
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
           'rule_version': RULE_VERSION + ('+' + entry_checks.RULE_VERSION if prices is not None else ''),
           'status': ('READY' if len(picks) == PICKS else 'PARTIAL' if picks
                      else 'NO_AGREEMENT' if answered else 'UNAVAILABLE')}
    passed_over = [c for c in candidates if c.get('entry_check') == 'VOID' and c['votes'] >= 2]
    if passed_over:
        out['void_at_entry'] = [f"{c['side']} {c['ticker']}" for c in passed_over]
    split = sorted({c['ticker'] for c in candidates if c['split']})
    if split:
        out['split'] = split
    # SINGLE-MODEL PICKS (owner, 2026-10-03): on a day without full agreement
    # the email points at each model's own SELECTED names, labelled as one
    # model only. Pointers, never slots: they are not recorded as top2 rows
    # and never fill the section. Jev's forced and ranked names are not
    # selections and are not listed here.
    if len(picks) < PICKS:
        taken = {p['ticker'] for p in picks}
        out['single'] = [{'side': c['side'], 'ticker': c['ticker'], 'by': c['backing'][0]}
                         for c in candidates
                         if c['votes'] == 1 and c['selected'] and not c['split']
                         and c.get('entry_check') != 'VOID' and c['ticker'] not in taken]
    if not answered:
        out['reason'] = 'No model answered today, so there is no name to put here.'
    elif not picks:
        out['reason'] = ('No agreement today: no two models backed the same name on the same side, '
                         'so there is nothing here to act on. Each model\'s own picks are in Part 1, '
                         'and a single model\'s pick has not beaten random picks on the replay.')
    elif len(picks) < PICKS:
        out['reason'] = ('Only one name had agreement today; the second slot is left empty rather '
                         'than filled with one model\'s pick.')
    return out


def _agreed(c):
    return (c['votes'] >= 2 and c['selected'] and not c['split']
            and c.get('entry_check') != 'VOID')


def _verdict(p, answered):
    n = len(answered)
    if p.get('council'):            # day-124: the room's own count, after two rounds
        return p['verdict'] + (' — all saw the same release, not independent' if p.get('wire') else '')
    if p['split']:
        return 'SPLIT — models took opposite sides'
    if p.get('entry_check') == 'VOID':
        return 'VOID AT ENTRY — already past its own "wrong if"'
    # Day-120b H3: models that all had the same issuer release in front of them
    # are one reading of one fact, not independent opinions (2026-09-30, TD).
    same = ' — all saw the same release, not independent' if p.get('wire') else ''
    if p['votes'] == n and n > 1:
        return f'ALL {n} AGREE{same}'
    if p['votes'] >= 2:
        return f"{p['votes']} of {n} agree{same}"
    return f'1 of {n} — no agreement on this slot'


def single_line(section):
    """One line naming each model's own picks on a day without full agreement,
    or None when the publication predates the field (2026-10-03)."""
    if 'single' not in (section or {}):
        return None
    s = section['single']
    if not s:
        return 'Single-model picks: none — no model picked a name on its own today.'
    return ('Single-model picks (one model only, no agreement): '
            + ' · '.join(f"{x['side']} {x['ticker']} ({x['by']})" for x in s) + '.')


def table(section, concise=False):
    """The section as text lines, one table. Used by every email and view.
    `concise` is the email (owner, 2026-10-03): one line of rule, no caveats."""
    if not section:
        return []
    if section.get('council'):
        return _council_table(section, concise)
    if concise:
        out = ['## Top 2 — where the models agree',
               'Only names at least two models back on the same side.']
    else:
        out = ['## Top 2 — where the models agree',
               'A name appears only when at least two of the models (Claude, DeepSeek, Gemini, Jev on the '
               'same brief) back it on the same side. Agreement is not confirmation: they read the '
               'same inputs, and none has beaten random picks on the replay.']
    picks = section.get('picks') or []
    single = single_line(section)
    if not picks:
        if concise and section.get('status') == 'NO_AGREEMENT':
            head = 'No agreement today — nothing to act on.'
        else:
            head = section.get('reason') or 'No pick today.'
        return out + ['', head] + ([single] if single else []) + _notes(section)
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
    if single and section.get('single'):
        out.append(single)
    return out + _notes(section)


def _council_table(section, concise):
    """Day-124: the council chose. Who sat, what won, who objected and why."""
    import council
    out = ['## Top 2 — the council\'s decision',
           'The four models argued over every proposed position for two rounds; a position is '
           'here only when most of those present endorsed it and at most one objected.']
    if not concise:
        out.append('Consensus is not confirmation: the members read the same brief, and none has '
                   'beaten random picks on the replay. Convictions are never averaged.')
    sat = section.get('answered') or []
    absent = section.get('absent') or []
    out.append('Sat: %s%s.' % (', '.join(sat) or 'nobody',
                               ('; absent: ' + ', '.join(absent)) if absent else ''))
    picks = section.get('picks') or []
    near = council.near_line(section)
    # Day-129: the runner-up (never a pick) and the previous session's repeats.
    runner = council.runner_up_line(section)
    repeats = [line for line in (council.repeat_line(x) for x in
                                 picks + ([section['runner_up']] if section.get('runner_up') else []))
               if line]
    if not picks:
        head = (section.get('reason') or 'No pick today.' if not concise else
                'No council pick survived the 09:46 entry check.' if section.get('void_at_entry') else
                'No consensus today — no council pick.' if section.get('runner_up') else
                'No consensus today — nothing to act on.')
        return (out + ['', head] + ([runner] if runner else []) + repeats
                + ([near] if near else []) + _notes(section))
    out += ['', '| # | Pick | Council vote | Endorsed by | Wrong if | Wire release | Why (lead proposer) |',
            '|---|---|---|---|---|---|---|']
    for i, p in enumerate(picks, 1):
        wrong = (f"{'below' if p['side'] == 'LONG' else 'above'} {p['invalid_at']:g}"
                 if isinstance(p.get('invalid_at'), (int, float)) else '—')
        w = p.get('wire')
        release = f"{w['at']} {w['title']}"[:90].replace('|', '/') if w else '—'
        why = str(p.get('reason') or ('gives probabilities, not reasons' if p['lead'] == 'Jev'
                                      else '—')).replace('|', '/')[:200]
        out.append(f"| {i} | {p['side']} {p['ticker']} | {_verdict(p, sat)} | "
                   f"{', '.join(p['backing'])} | {wrong} | {release} | {p['lead']}: {why} |")
    out += council.council_lines(section, concise=concise)
    proposed = council.proposed_line(picks)      # day-129: selected, nominated or forced
    if proposed:
        out.append(proposed)
    try:                                         # day-127: what each position is a bet on
        import exposure
        line = exposure.exposure_line(picks)
    except Exception:                            # display only; never costs the section
        line = None
    if line:
        out.append(line)
    if section.get('reason'):
        out.append(section['reason'])
    if runner and len(picks) < 2:
        out.append(runner)
    out += repeats
    if near:
        out.append(near)
    return out + _notes(section)


def _notes(section):
    out = []
    if section.get('council_note'):
        out.append(section['council_note'])
    if section.get('split'):
        out.append('The models took opposite sides of: ' + ', '.join(section['split']) + ' — left out.')
    if section.get('void_at_entry'):
        out.append('Passed over at 09:46, already past their own "wrong if": '
                   + ', '.join(section['void_at_entry']) + '.')
    if section.get('repeat_note'):
        out.append(section['repeat_note'])
    return out
