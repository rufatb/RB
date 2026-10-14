# PREREGISTER day-119c — a debate between the models before they finalize

Registered 2026-09-29, before any debate was run or scored.

## The owner's idea

"Orchestrate multiple language models to agree … like a mini argument between
themselves before they finalize." `debate.py`, three rounds, fixed now:

1. **Proposals.** Each model's own first answer, with who proposed it and why:
   DeepSeek's selections, Jev's selections and its forced long and short, and,
   live only, Claude's sealed selections.
2. **Cross-examination (DeepSeek, deepseek-v4-pro, thinking off).** DeepSeek
   sees every proposal, its proposer and reason, and the proposed names' rows.
   For each proposal it argues for and against from the supplied values only,
   then rules KEEP or REJECT with its own confidence. It is told a coin flip is
   the base rate and that rejecting everything is allowed.
3. **Adjudication (Jev).** Jev sees the proposed names' rows plus DeepSeek's
   rulings and arguments. For each side it answers a choice among that side's
   proposals, or NONE.

**Final:** a proposal DeepSeek KEPT whose Jev probability beats Jev's own NONE
on that side. At most two, ordered by Jev's probability. When none survive the
section says the debate finalized nothing; it is never padded.

## The test — the replay, before the section ships

The same 59 sessions (2026-07-06 → 09-28), the same pools with the wire
releases, and cached first answers: DeepSeek v4-pro (day-119) and Jev
(day-118). Scored by the production scorer (09:45 bar close → 15:55 bar
close). Claude cannot be replayed blind and is absent from the replay.

**The bar (day-117's):**
* the session-clustered mean per pick is > 0 with t ≥ 2.0;
* the hit rate beats random picks from the same session pools, with the same
  long/short counts, at p < 0.05;
* the sign is the same in both halves of the sessions.

**Also reported:**
* how many sessions finalized anything;
* DeepSeek's round-1 selections on the same sessions, for comparison;
* the planted-oracle / anti-oracle controls.

## Whatever the result

The debate ships as its own section (Part 5), with its replay record printed
beside it, because the owner is testing sections in parallel. It is recorded
(`model_picks` model `debate`, kind `final`) and judged forward at 40 live
sessions on the same bar. Nothing is sized from it. The prompts are not
re-tuned against this replay.

## Amendment — retired by the owner (2026-10-14, day-132c)

The owner retired Part 5 after the day-132b review of an outside read of the
scoreboard.

* **Why.** It failed this registration's own replay (21/43, 49%; KEEP 24/49
  against REJECT 77/147). Live it was the weakest row: 2/8, −0.65%. And it was
  routinely mistaken for the four-model council, which is a different
  mechanism.
* **What stops.** Nothing stages it (`morning_full.sh`), nothing publishes it
  (`brief.py` freezes `debate: None`), and the scoreboard drops its row.
* **What is kept.** `debate.py`, its tests and every recorded `debate/final`
  row. An older publication that carries the section still renders it.
* **No verdict.** The forward test this registration set up was not resolved
  at its 40-session decision point; it was stopped by the owner, not failed.
