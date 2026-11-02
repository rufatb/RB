# Day-143 — a name on its report day, a size rule: FAIL (rejection #59)

Council lab item 4, run 2026-11-02 in one look. Registered 2026-10-30
(`PREREGISTER_day143_report_day.md`); the script (`report_day.py`, 8602c5d)
was committed before any return was computed. Summary:
`data/report_day143.json`. Cost: FMP calls only.

## The question

Does a name swing wider from 09:45 to the close in its report window (D0 and
D1 around FMP's report date) than on its other days? The comparison counts
only the name-days the two live size rules would not already pass over, and
the window must not lean either way.

## The data

* **Primary.** The 150 pinned names, FMP 15-minute bars, 2024-01-02 →
  2026-10-29.
  * 104,025 name-days. The two live rules pass over 23,065 of them: 14,043
    big movers (day-135c) and 9,022 widest swings (day-137). That leaves
    80,960.
  * 1,658 reports fall in the window, and 13 have no bar on D0 or D1.
* **Point in time.** The S&P 500 as it stood on each date, 2016-01-04 →
  2026-10-29.
  * 716 names were members in the window, and 703 have FMP bars.
  * 27,160 reports. The rows are daily open → close against SPY.
* **The download.** No failed or capped calls. The membership rebuild counted
  59 glitches in FMP's change history (as day-138), and none were guessed.

## The verdict: FAIL

| Bar | Registered | Result | |
|---|---|---|---|
| 1. Size | window sd ≥ 1.15× the rest | 2.24% against 1.45%: **1.55×** (bootstrap 95% 1.45–1.64) | met |
| 2. No lean | both \|t\| < 2 | continuation +0.05% against XIU, t = 1.01; **long +0.15% against XIU, t = 2.81** | **not met** |
| 3. Placebo | dates moved 20 sessions earlier: below 1.15 | **1.18×** | **not met** |
| 4. Point in time | the S&P 500 ratio also ≥ 1.15 | 2.67% against 1.30%: **2.06×** | met |

* **The planted control was detected.** A random pseudo-window of the same
  size (2,298 name-days) read 1.007 unscaled and 1.259 scaled by 1.25.
* **The test could see much less than this.** It could tell a ratio of 1.135
  from 1.00, and the effect it measured is far larger.
* **FAIL is anything short of all four.** This is rejection #59.

## What the two misses mean

* **The window leans long on today's list.** It is +0.15% against XIU a
  name-day, t = 2.81, 53% up.
  * This is day-138's finding again: on survivors, report days look long. E1
    (+0.37% a report, t = 3.78) was that artifact, and it vanished on the
    point-in-time S&P 500.
  * Skipping report days would remove a slice that leans one way. That makes
    the rule a bet, not a size rule.
* **A window with no report swings wider too.** Moved 20 sessions earlier, it
  reads 1.18×.
  * Part of the ratio belongs to which names and sessions the windows pick.
    Reports cluster in seasons, and a season's other news travels with them.
    The report itself does not explain all of it.
  * The registered bar cannot give the report the 1.55×.

## Beside the verdict (descriptive, never a verdict)

* **D0 and D1 apart.** D0 reads 1.40× and D1 1.71×. D1 is the reaction day
  for a report after the close.
* **Without the live-rule filter:** 1.46×.
* **Within names:** the median of each name's own ratio is 1.48× (144 names).
* **Moving more than 3% after 09:45:** 15.0% of window name-days, against
  4.6% of the rest.
* **The volume-confirmed reports** read 1.67× (1,468 window name-days). This
  is flagged: selecting on the volume spike inflates the ratio.
* **Ten years of daily open → close on the TSX list:** 1.72×. Every year from
  2016 to 2026 sits between 1.35× (2020) and 2.12× (2023).
* **The record's council positions, 10-05 → 10-29.** Two of 32 sat in a
  report window: SHORT CLS.TO on 10-27 and SHORT CP.TO on 10-29. One name was
  not on the list.

## So

* **Rejection #59.** No rule is proposed, and nothing live changes.
* **The swing is real and large:** every year, both markets, within names.
  What failed is the claim that skipping it is a size rule and nothing else.
  * On the TSX list the window leans long.
  * A window with no report swings wider as well.
* **The bar does not move.** A later test of the same idea would be its own
  registration, with a placebo that matches the season, and it is not
  queued. The owner chose against size rules on 10-30 (day-144).
