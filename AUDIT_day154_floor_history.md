# AUDIT day-154 — the quality floor on Claude's past nominations: UNDERPOWERED (rejection #69)

Council lab item 16, registered 2026-11-20
(`PREREGISTER_day154_floor_history.md`), run once on 2026-11-23 by
`python floor_history.py --run` (485e447, committed before it ran). Summary:
`data/floor_day154.json`. Population pinned in
`data/floor_day154_positions.json` (no return read when it was pinned).

## The question

Since 11-11 a pick of Claude's stands only when Claude rates it 0.50 or higher,
or two or more council members endorse it on the final tally (day-150, the
owner's rule; `council.clears_floor`). The floor is judged forward, months away.
Applied to Claude's past nominations, does it keep the better ones?

* **The population:** every Claude nomination 10-14 → 11-19 whose council's
  final tally survives (10-22 and 10-23 have none), each (session, ticker,
  side) once.
  * 92 positions over 23 sessions; every one was on the council's table.
  * KEPT by the floor: 67. DROPPED: 25.
  * All 92 were scored; none was missing its outcome.
* **The outcome:** each nomination's own `r_pct` in `data/model_picks.csv`,
  09:45 → close, signed to the pick, gross.
* **The test:** day-140's arm A (`fixpack.arm_a`), seed 154, 2,000 label
  shuffles: kept minus dropped with a session-clustered t, a one-sided
  placebo, both halves in session order, at least 10 in each group.
* **Choices fixed in the code before the run,** where the registration left
  them open:
  * the outcome is the r_pct of the same ledger row the pin took;
  * the order of labels: SORTS, then REMOVES_WINNERS (named whatever the
    control says), then UNDERPOWERED, then NULL;
  * se for the smallest detectable effect is the planted control's diff / t;
  * first-named / second-named is ledger order within each session and side.

## Result: UNDERPOWERED

| Leg | Bar | Value | Met |
|---|---|---:|---|
| Kept minus dropped, clustered | > 0 with t ≥ 3 | **−0.20%**, t = **−0.39** | no |
| Placebo (one-sided, kept ≥ observed) | p < 0.01 | 0.654 | no |
| Halves (the first 11 sessions, the last 12) | both > 0 | −0.09%, −0.24% | no |
| Groups | ≥ 10 each | 67 kept, 25 dropped | yes |
| The dropped lose money net of 0.13% | dropped mean < +0.13% | +0.27% (net +0.14%) | no |
| Planted 1.0% on the kept: 1.0 / se | t ≥ 3 | **1.92** | no |
| Smallest effect detectable at 80% power (2.8 × se) | printed | 1.46% | |
| REMOVES_WINNERS (dropped minus kept, t ≥ 2) | named if met | t = +0.39 | no |

* **Arm A reads FAIL:** the kept nominations did not beat the dropped ones.
  Kept +0.07% a position (net −0.06%), dropped +0.27% (net +0.14%).
* **The control decides the label.** A planted 1.0% a kept pick shows only at
  t = 1.92, so the record cannot see anything below about 1.5% a position.
  As registered, the verdict is UNDERPOWERED, rejection #69.
* **Not REMOVES_WINNERS.** The dropped did better, but at t = 0.39, far from
  the harm check's t ≥ 2.

## Beside it, never judged

| Split (same 92) | Yes | No | Yes minus no | t |
|---|---|---|---:|---:|
| Claude's confidence ≥ 0.50 | 47: −0.06%, 28 right | 45: +0.32%, 26 right | −0.38% | −0.92 |
| Two or more endorsements | 46: −0.17%, 25 right | 46: +0.42%, 29 right | −0.59% | −1.33 |
| First-named on its side | 46: −0.06%, 23 right | 46: +0.31%, 31 right | −0.37% | −0.92 |
| LONG: kept vs dropped | 36: −0.09% | 10: −0.50% | +0.41% | +0.56 |
| SHORT: kept vs dropped | 31: +0.26% | 15: +0.79% | −0.53% | −0.63 |

* **Each leg alone points the same way as the whole:** the nominations Claude
  rated higher, and those the council endorsed, did a little worse, not
  better. Neither is near any bar.
* **This matches the earlier lab results.** Day-145c found a model's
  first-named nomination no better than its second (Claude's first-named did
  worse, t = −1.68). Day-148 found the positions with two or more objections
  did better (a veto would have removed winners). The endorsement leg reads
  the same here.
* **All 92 together:** +0.13% a position gross, 54 right, −0.005% net.
* **The live floor's own drops** (`top2floor/pick`, 11-11 → 11-19), with
  nothing standing on that side either day:
  * LONG CNQ.TO, 11-17: −1.94% (dropping it saved that);
  * SHORT LUN.TO, 11-19: +5.11% (dropping it cost that).

  Two drops are an anecdote.

## What it says

* On the record so far, the floor does not sort Claude's nominations: the
  kept ones did slightly worse than the dropped ones, and no leg of the rule
  points the right way.
* The record is too small to see an effect below about 1.5% a position, so
  this neither confirms the floor nor shows that it removes winners.

## What changes

* **Nothing live.** No pick, size, record or rule changes. The floor is the
  owner's decision with its own forward bar
  (`PREREGISTER_day150_morning_decision.md`), and this test does not replace
  it.
* The result is information for the owner: on history the floor's legs lean
  the wrong way, below any bar.

## Not blind, said plainly

Day-145c, day-148, the scoreboard's pooled "Claude (nominated, forced)" row
and 11-19's LUN.TO review were all known before the registration, as it says.
No split in this file was computed before the run.

## Cost

None: the committed record and the pinned file, 0.1 s, no API call, no model.

## Not claimed

That any rule makes a pick right more often. Say so plainly when asked.
