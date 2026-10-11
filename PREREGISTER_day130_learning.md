# PREREGISTER day-130 — learning from the record: reversal, hedged expression, exits

Registered 2026-10-11, before the tests below ran. The owner asked for an
analysis of last week's picks and of how they were executed, and for new ways
to improve the picks and the council without making the stable system worse.

## What prompted it (descriptive, already measured)

The execution lab (`execution_lab.py`) re-ran every pick under other entries,
exits, hedges and holding periods:
* the day-117 replay: 379 picks over 59 sessions, on cached bars;
* the live record: 93 model picks from 09-17 to 10-09.

As scored (09:45 → close), nothing beats a coin flip. Three patterns stood
out, none at the house bar:
* **Holding past the close loses.** In the replay, holding 3 sessions lost
  0.68% per pick against XIU (clustered t −2.2), on longs and shorts alike.
  Live, holding to the next close lost 0.34% (Top 2: −0.61%).
* **The council's picks are sector bets.** Last week's two big losers, SHORT
  CVE.TO (oil) and LONG CCO.TO (uranium), moved with their sector. On the 13
  live Top 2 picks, measuring each against its sector peers cut the
  pick-to-pick sd from 1.11% to 0.54%.
* **The afternoon fades the pick.** In the replay, 12:00 → close lost 0.08%
  (t −1.7); 09:45 → 12:00 made +0.04%.

## H1 — short-term reversal in the pool (the quant layer)

The models pick names that have just moved, and those names then gave back.
The equity literature calls this short-term (weekly) reversal. Is it in our
pool?
* **Data:** two years of daily bars for the 125 names in
  `data/tsx_sectors.json`.
* **Signal:** each name's 5-session return to the prior close, minus its
  sector's median (sector-relative), ranked across the pool each day.
* **Trade:** long the bottom fifth, short the top fifth, equal weight, entered
  at the next open and held 5 sessions. Rebalanced every 5th session, so the
  periods never overlap.
* **Costs:** 0.10% per side per name.
* **Bar (all must hold):**
  * t ≥ 3 on the non-overlapping periods, net of costs;
  * the same sign in each of the last four quarters;
  * a shuffled-signal placebo at p < 0.01;
  * a planted +0.5% per period edge is detected at t ≥ 3 (house rule 4).
* **Caveat, stated up front:** the pool is today's names, so the test has
  survivorship bias. A pass is a reason for a forward test, not for money.

If H1 passes, the reversal rank becomes:
1. a recorded shadow sleeve (Part 7), long losers and short winners for five
   sessions, never sized;
2. later, and only after its own control, a context field the models see.

If it fails, neither is built.

## H2 — the hedged expression of a pick

* **Hedge:** each pick against its sector ETF (`exposure.position_exposure`),
  with a beta from the prior 60 daily returns, over the same 09:45 → close
  window.
* **Populations:** the replay picks and the live picks, the Top 2 apart.
* **Bar:**
  * the sd of the hedged return is at least 15% below the raw sd (day-120b's
    bar);
  * the mean is not worse by more than 0.10% per pick (non-inferiority).

If H2 passes on the Top 2, the email prints the hedged version beside each
council pick, as display only. The execution lab records it.

## H3 — exits

* **Rules:**
  * the pick's own "wrong if" as a stop, filled at the close of the crossing
    5-minute bar;
  * a noon exit;
  * a 0.5 ATR stop.
* **Bar for any rule:** the mean is not worse than holding to the close by
  more than 0.05%, and the sd is lower. If a rule passes it is shown and
  recorded, never applied to the scored record.

## H4 — live intraday news (not run)

Releases on pool names during the session (09:45–15:00): 37 in July to
October, mostly routine. That is too few to test, so it is not run.

## What is recorded and claimed

**Recorded.** The execution lab runs in the evening review. It writes every
pick's alternative returns to `data/execution_lab.csv`, so the comparison
grows every day. Nothing it computes changes a pick, a size or the scored
record.

**Not claimed.** Nothing here is shown to make any pick more accurate.

## Amendment 1 (2026-10-11, before H5 and H6 ran)

H1 failed (gross +0.03% per week; see `data/replay_day130_reversal.json`).
H2 failed both bars. Of the exits, only the noon exit passed in every
population. Two further tests are registered here, before they run.

**H5 — intraday momentum into the close.** In the literature, the first
half hour predicts the last half hour on the index (Gao, Han, Li and Zhou,
2018).
* **Population:** the 125 names, 60 sessions of 5-minute bars.
* **Signal:** the 09:30 → 10:00 return.
* **Trade:** the last half hour, 15:25 → 15:55, on the signal's side, for
  every name whose signal is beyond ±0.25%.
* **Bar:**
  * session-clustered t ≥ 3;
  * same sign in each of the three months;
  * net of 0.10% per side;
  * placebo by shuffling the signal across names within a session,
    p < 0.01.
* XIU alone is reported as a description; 60 sessions cannot test it.

**H6 — intraday vs overnight drift in the pool.** Two years of daily bars,
125 names: the mean open → close return (intraday) and the mean close → next
open return (overnight), per session averaged across names.
* **Bar:** intraday mean below zero at session-clustered t ≤ −3, and below
  zero in each of the last four quarters.
* **If it passes:** a short side gets a structural tailwind intraday. That is
  printed beside the scoreboard as context; no pick rule changes.
