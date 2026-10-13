# PREREGISTER day-129 — every model nominates; a labelled runner-up; repeats flagged

Registered 2026-10-09, before any of it ran. Amendment 3 to
`PREREGISTER_day124_council.md`. The owner chose all three parts on
2026-10-09.

## Why

On 2026-10-09 the council's table held four positions:
* Gemini's two selections (LONG TD.TO, SHORT SU.TO);
* Jev's two forced picks (LONG SHOP.TO, SHORT NA.TO).

Claude and DeepSeek selected nothing. Their prompt says "fewer is correct when
the evidence is thin", and they followed it. The council turned down three
positions and one remained.

The owner expected each model to bring its best ideas and the council to argue
over them. The table was built from the desks' GATED picks, so when two desks
abstained there was little to debate. Gemini had proposed TD on both 10-08
(SHORT) and 10-09 (LONG).

## 1. Nominations (table version `day129-nominations`)

**Who is asked.** Inside `council.py --stage`, before the table is built:
* DeepSeek (`deepseek-v4-pro`, thinking disabled);
* Gemini (`gemini-3.8-flash`);
* Claude (`anthropic/claude-opus-5.5` via OpenRouter, stateless).

**How.** Each is asked ONCE, single-shot, with no research round.
* The question is the desks' own brief payload (`claude_brief.json`).
* The prompt is the desk prompt's field documentation, byte for byte
  (everything before "Rules you must follow:"), followed by nomination rules:
  * exactly TWO longs and TWO shorts, best first;
  * no abstaining; the committee decides whether any is worth doing;
  * an honest confidence, where low is fine;
  * a one-sentence reason, a basis and an invalid_at, as the desks give them.

**Validation.**
* Answers pass the desks' `_clean`, `check_levels` and `check_basis`.
* A ticker one model nominates on both sides is dropped from both.

**Jev.** It nominates the top two of its existing FORCED distribution per
side. It is asked no new question.

**The table.**
* It holds selections, then nominations, then Jev's forced top two.
* It is deduplicated by (ticker, side); each proposer is labelled `selected`,
  `nominated` or `forced`.
* At most 16 positions.
* The web scout's cap rises from 8 positions to 16.

**Unchanged:**
* the desks' prompts, their sealed picks and the desk scoreboard;
* the council prompt (`day124-council-v2`), its rounds and the frozen
  consensus rule;
* the 09:46 entry check, and "at most two, never padded".

A failed nomination costs only that model's nominations, and it is named in the
council's `errors`.

## 2. The runner-up (display, plus a shadow record)

**When it is shown.** When fewer than two positions reach consensus after the
09:46 entry check, the runner-up is the best remaining position in the tally's
own order (top-two seats, then E, then fewest O, then weakest endorser) that
meets all of these:
* at least one endorsement, and more endorsements than objections (E ≥ 1 and
  E > O);
* not on a ticker already picked;
* not past its own "wrong if" at entry.

**How it prints.** "Runner-up — no consensus: SIDE TICKER (E of V endorse,
O object)", with its lead reason and its "wrong if".

**What it is not.** It is NOT a council pick:
* it is never recorded as `top2/pick`;
* it is recorded as `top2runner/pick`, a shadow that never appears on the
  scoreboard, so its record can be judged on its own.

**When none qualifies,** the section says "No runner-up: every other position
drew at least as many objections as endorsements."

## 3. Repeats flagged (display only)

**What is flagged.** A Top 2 pick or the runner-up whose ticker was a Top 2
pick on the previous recorded session.

**How it prints.** "Also the previous session's Top 2: SIDE TICKER", then
either its scored result (09:45 → close) or "not scored yet".

**Rules.**
* The lookup happens when the section is computed, from
  `data/model_picks.csv`, and is frozen with the section. Renderers never read
  the ledger.
* No name is excluded for repeating. A fresh catalyst (10-09: the buyback
  approved after Thursday's close) is exactly what such a rule would hide.

## Controls (house rule 4), before it goes live

**Nominations.** The day-110 planted universe goes through each model's
nomination path, 5 runs per model.
* Clean = CTLUP.TO among the LONG nominations and CTLDN.TO among the SHORT
  nominations, with neither planted name on the wrong side.
* The bar is 4 clean runs of 5.
* A model under the bar ships WITHOUT nominations (its selections still go on
  the table), and that is reported.

**Jev.** On its existing control, both planted names must head its forced top
two.

**Dry run.** One run on 2026-10-09's state, reported: table size, timings and
outcome. It is not used to tune anything.

## What is recorded and claimed

**Records.**
* Top 2 rows carry `rule_version` `day124-council+day129-nominations`, so the
  council's record splits at this change.
* The 40-session council test (~2026-11-30) keeps its bar.
* The runner-up shadow is scored by the evening job like every other row.

**Not claimed.** This gives the council real choices and should fill both
slots more often. It is NOT shown to make any pick more accurate. Every source
on the record is still a coin flip, and the email keeps saying so.

## Amendment 1 (2026-10-09, before the first live run)

Two cases the text above left open, settled in code before any live morning:
* A position whose ticker the council SPLIT on (both sides agreed) is never
  the runner-up; day-124 takes neither side.
* "The best remaining position" includes an AGREED position ranked below the
  two the council chose, when one of those two is void at 09:46. It is
  labelled "agreed, ranked below the picks", never "no consensus". It is still
  not a pick; day-124's "never padded" stands.

When nothing qualifies, the note names any position that won the votes but
could not stand (the other side of a pick, or void at 09:46). Otherwise it is
the registered sentence.

## Amendment 2 (owner, 2026-10-13, before any code for it ran)

The owner saw Claude's and DeepSeek's desks print "No pick today" again, and
asked whether that hurts the picks and the council. Measured first:
* **How often they pick.** Claude's desk (stateless since 10-06) has selected
  nothing on its 5 live mornings; DeepSeek selected nothing on 10-09 or
  10-13. Both returned valid, empty lists, as their prompt allows, with no
  reason given.
* **The council is not starved.** 10-13 was the first live morning with
  nominations:
  * the table held 11 positions;
  * both picks were Claude's nominations: LONG ATZ.TO, and SHORT CCA.TO, which
    Gemini also nominated;
  * both models voted on every position.
* **Nothing measurable is lost.** Their selections so far are coin flips
  (Claude 5/9, DeepSeek 10/26), and day-117 found the inputs carry no edge.

**What changes** (display and a separate record; no prompt, rule or size
changes):
1. **On a no-pick day, the desk shows its model's nominations.** Under its "No
   pick today" line the desk prints each nomination: side, ticker, the model's
   own confidence, "wrong if", and what the council did with it. It is
   labelled forced (the model had to name two per side), not a selection, not
   sized.
2. **`council.json` keeps the full nominations** in `nomination_picks`:
   confidence, reason, "wrong if" and basis. The existing ticker lists in
   `nominations` are unchanged.
3. **Every nomination is recorded as `<model>/nominated`:** all three models,
   every day.
   * It is scored by the same scorer.
   * It is shown on the scoreboard as "<Model> (nominated, forced)" once
     scored rows exist.
   * It is never sized and never pooled with selections.
   * It is never in the counted Top 2, and it is kept out of the lessons and
     the execution lab's pool.
4. **No decision is attached.** At the 40-session review the nominations are
   read beside the selections and random picks from the same pools.

**A display fix, the same day.** The council section printed the counted
rule's split list ("The models took opposite sides of: ATZ.TO — left out") on
a morning the council PICKED LONG ATZ.TO. From now on the council section
lists only the council's own splits, as day-124 defines them: both sides
reached consensus, so neither is taken.

The desk prompts are not changed to force picks (day-127/128).
