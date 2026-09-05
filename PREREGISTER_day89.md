# Pre-registration — day-89, entry time × hold duration, jointly

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

## Why re-run something already rejected

Day-39 rejected alternative entry times (#29) and day-51 rejected per-pick hold
duration (#32). Both were rejected SEPARATELY and neither on this data:

| | day-39 entry | day-51 duration | day-89 (this) |
|---|---|---|---|
| names | 21 TSX / 20 twins | 21 TSX | **258 US** |
| sessions | 35 / 288 | 719 | **490** |
| grid | entry only | duration only | **entry × duration, jointly** |

The joint grid is the part that has never been run. Entry and duration push in
opposite directions — a later entry gives a longer momentum window in `r0` and
more volume to judge `vp` against, but leaves less session to capture, and a
longer hold changes both what is being predicted and how much noise it carries.
Testing them one at a time cannot find an interaction, and an interaction is
precisely what "is 9:46-to-close the right box?" is asking about.

## THE DANGER, which is the reason this document is long

**A 7 x 5 grid is 35 cells, and the best of 35 noisy cells looks good by
chance.** This is the trap that killed day-39's apparent 9:50 winner: its
+0.1034% was beaten by the placebo's own MEDIAN winner at +0.1212%. Reporting
the best cell against zero would manufacture a result here with near-certainty.

**Registered rule: the statistic is the BEST CELL versus the PLACEBO'S BEST
CELL, not versus zero.** The placebo runs the identical 35-cell grid on
shuffled picks, records its maximum, and repeats. A real winner must beat the
placebo's max distribution at the 95th percentile. Nothing else counts as a
pass, whatever any individual cell's `|t|` says.

## Panels, and the wall one of them hits

**Panel A — hourly, long window.** `data/us_hourly.csv`: 123,772
ticker-sessions, 258 names, 490 sessions, entry at each hourly close (10:30,
11:30, 12:30, 13:30, 14:30). This is the LONG-WINDOW arm and it decides.

**Panel B — 5-minute, 60 days.** Yahoo caps 5m bars at 60 days and that cap is
not negotiable, so the fine grid (09:35 / 09:40 / 09:45 / 09:50 / 10:00 /
10:30) can only be tested on ~41 sessions. **Stated before running: this is the
window length that has manufactured six separate mirages in this repo** — the
61% ramp-fade, the 68% selector, the 67% gradient, the crowding gate, breadth,
and day-21's cross-sectional reversal, every one of which evaporated on a
longer sample. Panel B can REFUTE a claim; it cannot establish one. If A and B
disagree, A wins.

That asymmetry is registered now so it cannot be re-argued after seeing which
way they fall.

## Hypotheses

**H1 — entry time.** Tide-relative capture per leg by entry time, engine
walk-forward re-fitted at each entry (the features change when the entry
changes; reusing one fit would test the clock, not the engine).

**H2 — hold duration.** Entry fixed at the panel's first bar; exits at same-day
close, +1, +2, +3, +5 sessions. Market-relative, block-bootstrapped at
block = horizon, because forward returns computed on every date overlap.

**H3 — the joint grid.** All entry x duration cells. **This is the arm the
question is really about**, and the one the placebo-max rule governs.

## Statistics and bars

- **Statistic.** Tide-relative capture per leg. Hit rate reported beside it and
  does not decide — a hit rate can rise while capture falls.
- **Bar.** `|t| >= 3` AND the same sign in all four contiguous blocks AND
  beating the placebo's MAX at the 95th percentile. All three.
- **Clustering.** By SESSION for same-day exits; block bootstrap at
  block = horizon for multi-day holds.
- **Positive control.** A planted edge of stated size must register in the
  grid, measured as `edge / sd`, never `(mean + edge) / sd`.
- **MDE always reported** (rule 10).
- **Cost.** A later entry does not change the spread, but a longer hold pays
  overnight risk: day-24 measured 2x volatility and day-87 measured a 2.48x
  worse worst-day. Any multi-day cell is reported with that attached, and a
  cell that wins on mean while worsening the 5th percentile is a VARIANCE
  TRANSFER and is labelled one.

## What may be adopted

A change to the run time or a stated hold duration, **only** if the winning
cell beats the placebo max, clears `|t| >= 3`, holds its sign across four
blocks, and survives its cost. Otherwise 09:46-to-close stands — not because it
is special, but because nothing displaced it.

## Forbidden

Reporting the best cell against zero. Choosing the grid after seeing results.
Letting Panel B override Panel A. Quoting a same-day-exit cell and a multi-day
cell as if they carried the same cost. Dropping H2 if H1 fails.

## Expected outcome, recorded in advance

I expect no cell to beat the placebo max. The prior is day-39 (entry, p=0.640
and 0.940), day-51 (duration, tide-relative accuracy flat at 49.6-50.0% across
to-close/+1d/+2d/+3d/+5d) and day-43 (the features carry no signal at any
horizon, AUC 0.5022). If the features are inert, moving the box they are
evaluated in cannot make them informative.

What I think this CAN establish, and the reason it is worth running: a
MEASURED bound on how much is available from re-timing at all, on a sample
twelve times wider than the one that settled it before. "No better time exists"
is a more useful answer with 258 names behind it than with 21.
