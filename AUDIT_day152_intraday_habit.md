# AUDIT day-152 — a name's own intraday habit: UNDERPOWERED (rejection #67)

Council lab item 12, registered 2026-11-16
(`PREREGISTER_day152_intraday_habit.md`), run once on 2026-11-17 by
`python intraday_habit.py` (1973c20, committed before it ran). Summary:
`data/intraday_habit_day152.json`.

## The question

Lou, Polk & Skouras (2019) found on US stocks that a stock's past intraday
returns persist intraday. Does that hold on the 150 TSX names?

* **The habit:** each name's mean 09:45 → close against XIU over the prior
  20 sessions (15 of 20 needed; never the session itself).
* **The sort:** each session, the names are ranked by habit.
* **The measure:** y = the top fifth's 09:45 → close against XIU minus the
  bottom fifth's, the same session.
* Persistence predicts y > 0. A positive result could break ties among
  Claude's nominations.

## What ran

* **The data:** cached bars only (day-143's download), so no API call and no
  model.
* **The population:** 692 sessions, 2024-01-02 → 2026-10-29, a median of 147
  names a session. No session was short of 25 names.
* **Runtime:** 23 seconds.

## Result: UNDERPOWERED

| Measure | Value |
|---|---:|
| Mean y a session (top fifth minus bottom fifth) | **−0.090%** |
| t on the session series | −2.52 |
| Four blocks, in date order | −0.04%, −0.09%, −0.04%, −0.19% |
| Per-pick edge (y / 2), against the 0.13% cost | −0.045% |
| Within-session shuffle placebo (2,000 draws, seed 152), one-sided for persistence | p = 1.00 |
| The same placebo, one-sided for reversal | p < 0.0005 |
| Planted 0.10% a session: t | **2.79 (below 3)** |
| Smallest effect detectable at 80% power | 0.100% |
| Secondary (a): the same names, daily open → close, 2016 → | +0.095%, t = 4.34 |
| Secondary (b): the point-in-time S&P 500, daily open → close | +0.006%, t = 0.34 |

* **Not PERSISTENCE.** The mean is negative, so every leg of that bar fails.
* **Not REVERSAL either.** All four blocks are negative and the placebo says
  reversal, but t = −2.52 is short of −3.
* **The control decides the label.** A planted 0.10% shows at t = 2.79, below
  3. As registered, the verdict is UNDERPOWERED, rejection #67.

## Why the placebo disagrees with the t

The shuffle keeps each session's outcomes and redraws only which names sit
in the fifths. So it measures the sort's luck within a day, and not how the
spread varies from one day to the next. Its spread is narrow: the draws'
standard deviation is 0.017%, against a standard error of 0.036% on the
session series. The t is the binding test. A Newey-West t (5 lags) gives
−2.46, close to the plain t.

## Beside it, never judged

* **The lean is reversal, not persistence.**
  * The fifths, from the weakest habit to the strongest: +0.05%, +0.04%,
    +0.03%, +0.01%, −0.04%. They fall in order.
  * Both legs carry it: the top fifth lagged XIU by 0.04% and the bottom
    fifth beat it by 0.05%.
  * This matches day-137 H1 (#53, following the move against the sector:
    t = −2.75). That lean was known before this test.
* **By year:**

  | Year | Mean y | t |
  |---|---:|---:|
  | 2024 | −0.04% | −0.67 |
  | 2025 | −0.05% | −0.92 |
  | 2026 | −0.20% | −2.55 |

* **The overnight version.** LPS predict that a name's past overnight
  returns reverse intraday. Here it reads +0.02%, t = 0.32: not seen.
* **A 60-session habit:** −0.01%, t = −0.15.
* **Open → 09:45, before the entry:** +0.04%, t = 1.54.
* **The ten-year daily panel (secondary a)** leans toward persistence:
  * +0.095%, t = 4.34 on open → close;
  * positive in every year 2016–2024, then −0.03% in 2025 and −0.17% in
    2026;
  * it is today's list (day-138's survivor warning);
  * on the point-in-time S&P 500 the same sort reads +0.006%.
* **The live record.** Within each session and side, did the Claude
  nomination whose habit pointed its way more strongly do better?
  * 8 of 23 pairs, 10-14 → 10-29 (the cache ends 10-29).
  * A count only, never a verdict.

## What it says

* On these names, from 09:45 a name's own 20-session habit does not persist.
* If anything it reverses slightly, and most in 2026. The record cannot tell
  that from noise at the registered bar.
* A tie-break by habit among Claude's nominations has no support.

## What changes

* **Nothing live.** No proposal goes to the owner.
* The reversal lean is not a finding: by the registration, a rule from it
  would need its own registration. Nothing is built from it.

## Cost

None: cached bars, no API call, no model.

## Not claimed

That any pick, sort or habit is more accurate. Say so plainly when asked.
