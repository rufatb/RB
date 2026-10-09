#!/usr/bin/env python3
"""THE NOMINATION ROUND — every model brings its best ideas to the council (day-129).

Registered in PREREGISTER_day129_nominations.md before it ran (amendment 3 to
the day-124 council). A desk answers "is anything worth a position today?", and
on a thin day the honest answer is no. On 2026-10-09 Claude and DeepSeek said
exactly that, and the council had four positions to debate and kept one.

This asks a DIFFERENT question, after the desks have sealed: name your two best
longs and two best shorts for the committee to argue over. It is the same move
as Jev's forced question (day-112): a different question, not a loosened gate.
The desks' own picks, prompts and scoreboard are untouched, and a nomination is
never a selection, never sized and never recorded as a desk pick.

    collect(payload, allowed, ask=...)   {model: {'longs', 'shorts', 'gaps'}}, errors
    control(model, ask)                  the planted universe through this path

Single-shot, no research round: the web scout already adds dated news to every
position on the table.
"""
from __future__ import annotations

import concurrent.futures as cf
import json

import deepseek_opportunities as O

VERSION = 'day129-nominations'
SPLIT = 'Rules you must follow:'
MODELS = ('claude', 'deepseek', 'gemini')

NOMINATION_RULES = """THIS IS A NOMINATION ROUND, NOT A TRADE. A four-member committee will debate
today's candidates before the open and needs every member's best ideas on the
table. From the supplied list, nominate the TWO names you would most want to be
LONG and the TWO you would most want to be SHORT from 09:46 ET to 15:59 ET today,
best first. You MUST nominate exactly two per side: the committee, not you,
decides whether any of them is worth doing, and it may reject them all. Use
everything supplied — the rows, the headlines and their classes, the issuers'
wire releases, analyst changes and earnings, the macro changes with their
windows, and today's scheduled releases.

Rules you must follow:
- Every name MUST come from the supplied list, by exact ticker, and no name may
  appear on both sides.
- confidence is YOUR OWN honest number from 0.0 to 1.0 that the nomination works
  today. 0.5 is a coin flip. A low number on a weak idea is the honest answer,
  not a failure to answer; do not inflate it.
- reason must be one sentence, under 200 characters, naming the specific
  indicator values or the specific cited evidence that drove the choice.
- Do not claim certainty, do not give price targets, do not mention risk
  management, position sizing or stop losses, and do not reference anything
  outside the supplied data.

- basis is what the reason RESTS ON, exactly one of "news" (a supplied headline
  or catalyst tag about THAT name), "technical" (the supplied indicator and
  level values) or "macro" (the supplied macro changes). "news" on a name with
  no supplied headline is recorded as "technical".
- Everything supplied describes the PREVIOUS completed session or pre-open
  levels, and the entry is 09:46 — AFTER the open. Say in the reason why it is
  NOT already priced in, or do not rely on it.

- invalid_at is ONE PRICE, in the row's currency, at which your own reason is
  proven wrong today: for a LONG, a trade BELOW it; for a SHORT, a trade ABOVE
  it. Anchor it to a supplied level (prev_low, vwap, orb_low, prev_high ...).
  It is used only to SCORE the claim after the close — it is not advice and
  not an order. Omit it rather than guess.

Return ONLY this JSON object and nothing else, two names per side, best first:
{"longs": [{"ticker": "X.TO", "confidence": 0.0, "reason": "...", "basis": "news", "invalid_at": 0.0}, {...}],
 "shorts": [{"ticker": "Y.TO", "confidence": 0.0, "reason": "...", "basis": "technical", "invalid_at": 0.0}, {...}]}"""


def prompt():
    """The desks' own field documentation, byte for byte, then the nomination
    rules in place of the desks' "Rules you must follow" section."""
    head, sep, _ = O.SYSTEM_PROMPT.partition(SPLIT)
    if not sep:
        raise ValueError('NOMINATION_PROMPT_SPLIT_MISSING')
    return head + NOMINATION_RULES


def clean(answer, allowed, rows):
    """The desks' validators, unchanged, plus one rule: a ticker one model
    nominates on both sides is dropped from both. Returns (longs, shorts, gaps)."""
    if not isinstance(answer, dict):
        return [], [], ['the reply was not a JSON object']
    longs, gaps = O._clean(answer.get('longs'), allowed, 'long')
    shorts, short_gaps = O._clean(answer.get('shorts'), allowed, 'short')
    gaps += short_gaps
    both = {p['ticker'] for p in longs} & {p['ticker'] for p in shorts}
    if both:
        longs = [p for p in longs if p['ticker'] not in both]
        shorts = [p for p in shorts if p['ticker'] not in both]
        gaps.append('nominated on both sides, dropped from both: ' + ', '.join(sorted(both)))
    gaps += (O.check_levels(longs, 'LONG', rows) + O.check_basis(longs, rows)
             + O.check_levels(shorts, 'SHORT', rows) + O.check_basis(shorts, rows))
    for p in longs + shorts:
        p['nominated'] = True
    return longs, shorts, gaps


def live_askers(clients=None, claude_post=None):
    """The three chat routes the council already uses for its ballots."""
    import council
    clients = clients or {}
    return {'claude': lambda s, u: council.ask_claude_openrouter(s, u, post=claude_post),
            'deepseek': lambda s, u: council.ask_deepseek(s, u, client=clients.get('deepseek')),
            'gemini': lambda s, u: council.ask_gemini(s, u, client=clients.get('gemini'))}


def collect(payload, allowed, *, ask):
    """Ask each model once, in parallel. `ask` maps model -> fn(system, user) -> dict.
    A failure costs that model's nominations only and is returned, named."""
    system = prompt()
    user = json.dumps(payload, sort_keys=True, allow_nan=False)
    rows = payload.get('candidates') or []
    out, errors = {}, {}

    def one(model):
        try:
            longs, shorts, gaps = clean(ask[model](system, user), allowed, rows)
            return model, {'longs': longs, 'shorts': shorts, 'gaps': gaps}, None
        except Exception as exc:          # named in the council's errors, never swallowed
            why = str(exc) if (str(exc).isupper() or isinstance(exc, ValueError)) else type(exc).__name__
            return model, None, why[:80]
    with cf.ThreadPoolExecutor(len(ask)) as pool:
        for model, result, why in pool.map(one, [m for m in MODELS if m in ask]):
            if result is not None:
                out[model] = result
            else:
                errors['nominations ' + model] = why
    return out, errors


def control(model, ask, runs=5):
    """House rule 4 through the nomination path: the day-110 planted universe.
    Clean = the planted long among the long nominations and the planted short
    among the short ones, neither on the wrong side."""
    import datetime as dt
    planted = O.control_universe()
    now = dt.datetime(2026, 9, 17, 9, 5, tzinfo=O.ET)
    req = O.build_request(planted, None, now)
    results = []
    for _ in range(runs):
        noms, errors = collect(req['payload'], req['allowed'], ask={model: ask})
        got = noms.get(model) or {}
        longs = [p['ticker'] for p in got.get('longs') or []]
        shorts = [p['ticker'] for p in got.get('shorts') or []]
        clean_run = (O.CONTROL_LONG in longs and O.CONTROL_SHORT in shorts
                     and O.CONTROL_LONG not in shorts and O.CONTROL_SHORT not in longs)
        results.append({'clean': clean_run, 'longs': longs, 'shorts': shorts,
                        'error': errors.get('nominations ' + model)})
    return results


def main(argv=None):
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default=os.environ.get('RB_STATE_DIR', '.rb-state'))
    parser.add_argument('--control', choices=MODELS + ('all',), required=True,
                        help='the planted universe through this nomination path')
    parser.add_argument('--runs', type=int, default=5)
    args = parser.parse_args(argv)
    import gemini_opportunities as G
    import jev_opportunities as J
    import prepare_deepseek
    for loader in (prepare_deepseek.load_private_key, J.load_private_key, G.load_private_key):
        loader(args.state_dir)
    askers = live_askers()
    ok = True
    for model in (MODELS if args.control == 'all' else (args.control,)):
        runs = control(model, askers[model], runs=args.runs)
        clean = sum(r['clean'] for r in runs)
        print(json.dumps({'model': model, 'clean': clean, 'of': len(runs), 'runs': runs}, sort_keys=True))
        ok = ok and clean * 5 >= 4 * len(runs)          # the registered bar: 4 clean of 5
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
