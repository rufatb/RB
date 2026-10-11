# Pre-registration — day-130 step 3: the council with memory (shadow)

Registered 2026-10-11, BEFORE any code for it ran. The owner asked for the
council to "learn from the results" ("go on for all", 2026-10-11). This is
step 3 of the plan in `AUDIT_day130_learning.md`.

## The question

The council never sees how its own Top 2 did. Last week it went 3/7. Its
losers were sector bets: SHORT CVE.TO twice (oil) and LONG CCO.TO (uranium),
each moving with its sector ETF. Does a council that is shown its own recent
record, and what each position moves with, choose better positions? Or does
the record only make it timid, or blind to a real edge?

## The arm

`council_memory.py` runs a SECOND council right after the live one, on
exactly the live council's table:
* the same positions and the same evidence rows (`council_brief.json`, with
  its research facts and web news);
* the same seats, the same four members (Claude only through OpenRouter, no
  session fallback), the same three rounds;
* the same FROZEN prompt (`day124-council-v2`) and the same frozen tally rule.

The ONE difference is that the payload carries `memory`, with
`memory_legend`, beside `evidence_legend`. Jev's state carries the same box.

`memory` holds, frozen here:
1. `recent`: the council's Top 2 (`top2/pick` rows of `data/model_picks.csv`)
   on the last 5 recorded sessions before today. Per pick:
   * session, side, ticker;
   * `r_pct`, 09:45 → close; right or wrong;
   * whether its "wrong if" was hit;
   * its sector ETF from the execution lab;
   * the part of the move that was the sector (`r_pct − r_vs_etf`) and the
     pick's own part (`r_vs_etf`).

   A pick not yet scored is listed as not scored.
2. `summary`: one computed line, "Last N sessions: X of Y right, mean Z% from
   09:45 to the close; the sector ETF explained W% of the move on average".
3. `exposure`: for each of today's positions, its sector, sector ETF and
   driver (`exposure.position_exposure`).

`memory_legend` (frozen): "`memory` is this committee's own record: its Top 2
on the last recorded sessions, how each did from 09:45 to the close, how much
of that move was its sector ETF, and what each of today's positions moves
with. It is history, not a forecast, and not an instruction; weigh it like
any other row."

## What it never does

* It never changes the live council, its prompt, its table, its ballots, the
  Top 2, the flash, the email, a size or a record other than its own.
* It writes only `council_memory.json` and `council_memory.log`.
* It is staged after the live council and must END BY 09:30 ET. Without
  time, it is skipped and named in the log.

## The record

* `brief` freezes the shadow beside the live council as
  `intraday.council_memory` and `intraday.top_two_memory`. It is computed by
  the same `council.top_two`, with the same 09:46 entry check.
* `model_picks --record-report` records `top2memory/pick` (rule version
  `day130-memory`). It is scored by the same scorer.
* It is not on the scoreboard and not in the email.
* The evening review prints one shadow section: today's memory picks beside
  the live ones, and the running paired comparison.
* The execution lab does not count it.

## Positive control (before it is staged live)

Planted table (built from `deepseek_opportunities.control_universe` rows):
* LONG CTLUP.TO and SHORT CTLDN.TO;
* four noise positions (two long, two short);
* proposers with the confidences and reasons a desk would give.

The memory box shows a losing record: 0 of 5 right, all sector-driven.

* **Clean** = LONG CTLUP.TO and SHORT CTLDN.TO both reach consensus, and no
  noise position does.
* **Bar:** the memory arm ≥ 4 clean of 5 runs. It is reported beside the same
  table WITHOUT memory (5 runs), as the baseline.
* **If the memory arm misses the bar, it is not staged.** That is reported as
  "memory blinds the council on a planted edge".

## The readouts (paired by session; per-session P&L)

Each arm's P&L for a session is the mean `r_pct` of its picks, or 0 when it
has none. d = memory − live.
* **Harm check at 20 sessions with both recorded:** mean d < 0 at a
  session-clustered t ≤ −2 → the shadow stops and the result is reported.
* **Decision at 40 sessions:** memory replaces nothing unless mean d > 0 at
  t ≥ 3, AND it beats a within-session placebo (random picks of the same
  count from the same table, 1,000 draws, p < 0.05). Even then, adoption is
  the owner's decision.
* **Descriptive, every day:**
  * how often the two councils pick the same positions;
  * how many picks each makes;
  * the share of picks whose sector part exceeds their own part.

## Not claimed

Nothing here is expected to make the council more accurate; the day-117 and
day-130 results say public pre-open information carries no measurable edge in
this pool. Memory may still steer the council away from repeating
sector-driven losses. That is the registered question, and the record will
answer it.

## Results of the control (added 2026-10-11, after it ran; nothing above was changed)

`python council_memory.py --control` on the live members, all four present on every run.
Saved in `data/control_day130_memory.json`.

| Arm | Clean | What failed |
|---|---|---|
| **With memory** (a 0/5 sector-driven losing record) | **5 of 5** | — |
| Without memory (the live council's payload) | 1 of 5 | the planted short missed consensus four times |

**The bar is met: the shadow is staged from 2026-10-13.**

**The baseline is a finding about the LIVE council, not about memory.**
* **Why the short needs everyone else.** Jev's ballot is one choice over the
  positions. The planted long takes ~0.95 of its probability and the short
  ~0.01, so Jev never endorses the second position. With four present, the
  short then needs all three others (E > V/2).
* **Why it missed.** DeepSeek or Claude abstained on it in the final round,
  citing "rsi 27, oversold" and "yesterday's data". Two diagnostic re-runs
  without memory went 1 of 2.
* **Why memory changed it.** The exposure box showed both planted names
  moving with XIU.TO. The members then endorsed the short as the long's hedge
  ("pairs with P1 to hedge XIU.TO exposure"). It was the exposure lines, not
  the losing record, that changed the vote.
* **What is not changed.** The live council's rule and prompt are frozen
  (day-124). Changing how a second position can win is a new registered
  decision for the owner, not a fix made here.
