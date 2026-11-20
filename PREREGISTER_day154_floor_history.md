# PREREGISTER day-154: the quality floor on Claude's past nominations (council lab item 16)

Registered 2026-11-20 in the council-lab slot, before any return in it was
computed. The population is pinned in `data/floor_day154_positions.json`,
written by `floor_history.py --pin` (committed with this file). The run code
is added to `floor_history.py` in its own commit before it runs, next
weekday, and it gets one look. No model, no API call, no cost.

## Why

* **The floor is live.** Since 11-11 a pick of Claude's stands only when
  Claude rates it 0.50 or higher, or two or more council members endorse it
  on the final tally (day-150, the owner's rule; `council.FLOOR`).
* **It is judged forward,** over sessions with a dropped pick: a harm check
  at 20 and a decision at 40. That takes months.
* **The record already holds the inputs.** Every Claude nomination since
  10-14 is in `data/model_picks.csv` with Claude's own confidence. Its council
  tally survives in the day-148 pin and in the frozen reports. So the same
  rule can be applied to the past nominations now, on history, before the
  forward look.
* **The backlog had no free row** (6 parked, 7 waiting for a desk, 10 waiting
  for the owner's yes). This is the next free question, and it bears on a
  rule that is live.

## The population (pinned)

* **Every Claude nomination** (`claude/nominated`), each (session, ticker,
  side) once, sessions 2026-10-14 → 2026-11-19, whose council's final tally
  survives:
  * 10-14 → 10-21 and 10-26 → 11-09 from `data/veto_day148_positions.json`;
  * 11-10 → 11-19 from the frozen reports (`intraday.council.tally.rows`).
* **Left out:** 10-22 and 10-23. No tally from those councils survives, so the
  floor's second leg cannot be applied there.
* **The counts at registration** (no return read):
  * 92 positions over 23 sessions;
  * every one was on the council's table;
  * **KEPT by the floor: 67. DROPPED: 25.**
* **The rule as live** (`floor_history.floor_kept`): confidence ≥ 0.50, or
  endorse ≥ 2 on the final tally, Claude's own ballot included.

## The outcome

Each nomination's own `r_pct` in `data/model_picks.csv`: the record's
yardstick, 09:45 → close, signed to the pick, gross. The 0.13% round trip is
applied where the bar says.

## The test (seed 154)

Day-140's arm-A machinery (`fixpack.arm_a`), as day-141 used it:
* kept minus dropped, a pick-level difference with a session-clustered t;
* a label-shuffle placebo (one-sided, kept ≥ observed), `fixpack.DRAWS` draws;
* both halves in session order;
* at least 10 picks in each group (`fixpack.MIN_GROUP`).

## The bar

**SORTS** needs all of:
* `fixpack.arm_a` reads PASS: kept minus dropped > 0, t ≥ 3, placebo
  p < 0.01, both halves positive, both groups ≥ 10;
* the dropped nominations lose money net of the round trip: their mean
  below +0.13%;
* the control: a planted 1.0% added to the kept picks shows at t ≥ 3,
  computed as edge / se, never (mean + edge) / se. Otherwise the verdict is
  UNDERPOWERED. The smallest effect detectable at 80% power (2.8 × se) is
  printed beside it.

**REMOVES_WINNERS** (the forward harm check's direction, read now): dropped
minus kept with t ≥ 2. Named as such and told to the owner.

**Anything else** is rejection #69, labelled NULL or UNDERPOWERED.

## Beside the verdict (descriptive, never a verdict)

* Each leg alone, on the same 92:
  * confidence ≥ 0.50 against below;
  * two or more endorsements against fewer.
* LONG and SHORT apart.
* First-named against second-named (day-145c's split, for reference).
* The live shadow, `top2floor/pick`, 11-11 → 11-19: the picks the floor
  actually dropped from the Top 2, and what stood instead.
* Net of the 0.13% round trip, by group.

## What a result changes

* **Nothing live.** No pick, size, record or rule changes.
* The floor is the owner's decision with its own forward bar
  (`PREREGISTER_day150_morning_decision.md`), and this test does not replace
  it. Every result goes to the owner as information.
* A REMOVES_WINNERS reading is told to the owner at once, as the forward harm
  check would be.

## Not blind, said plainly

* **Day-145c:** a model's first-named nomination does no better than its
  second, and the confidence gap ranks nothing within a side.
* **Day-148:** positions with two or more objections did better than the rest
  (a veto would have removed winners), and every-member endorsement did worst.
  That bears on the floor's endorsement leg.
* **The scoreboard** prints "Claude (nominated, forced)" every day, pooled.
* **11-19's review** showed one floor-dropped short (SHORT LUN.TO) at +5.11%.
* **Counts read today:** the confidence split of Claude's scored nominations
  (50 at or above 0.50, 50 below), and the kept/dropped counts above. No
  return.
* The bar is day-141's arm A, plus day-148's net condition and planted
  control, fixed before any split was computed.

## Cost

None: the committed record, the day-148 pin and the frozen reports. No API
call, no model.
