# Day-135d — after a broad big-move day, do the movers turn back? (owner, 2026-10-16)

Registered BEFORE any return below was computed. Breadth has not been
measured or looked at for any session in this data.

## Why

Two Top 2s in a row followed the previous session's big move:
* **10-15:** SHORT CLS.TO and SHORT CCO.TO, after falls of about 1.5 ATR on
  10-14. That session 52 of the 150 names moved ≥ 1 ATR. Both names rose
  after 09:45, and the shorts lost 3.6% and 4.2%.
* **10-16:** LONG L.TO and LONG WCN.TO, after rises of about 2.5 ATR on 10-15.
  WCN was −0.72% at noon.

The owner: the picks extend the day before's direction, and the names had
"already decreased in the recovery". Their reading is that big movers turn
back the next day.

## Already known (not re-tested here)

* **Day-132 (rejection #47).** A ≥ 1 ATR move does not continue from 09:45 to
  the close: −0.013%, t = −0.44, on 10,332 moves, 2024–2026.
* **Day-135c R2** (daily open → close, 2016–2026).
  * The signed mean is −0.005% (t = −0.24).
  * After falls it is +0.009% (t = 0.25); after rises −0.002%.
  * After ≥ 2 ATR, falls are −0.15% (t = −1.04) and rises +0.03%.
* **Not computed: breadth.** None of these were split by how many names moved
  big the same day.

## The question

After a BROAD day, when an unusually large share of the 150 names moved
≥ 1 ATR, do that day's movers reverse the next session? It is read two ways:
* **RAW** (the primary): the owner's book is not hedged, so a market-wide
  bounce counts here;
* **AGAINST XIU:** the part specific to the stock.

## Data

* **The panel.** Day-135c's daily panel (`risk_rules.Daily`): the 150 names
  and XIU.TO, FMP dividend-adjusted bars, 2016-01-04 → 2026-10-14.
* **The trade proxy** is the session's open → close. The live entry is 09:45,
  which daily bars cannot see; this is stated, not hidden.
* **The move.** move_atr(D−1) as `daily_technicals.context` computes it,
  identical to day-135c.

## Definitions (all causal)

* **Breadth** B(D−1) is the share of names with a valid move on D−1 whose
  |move_atr| ≥ 1.
* **A broad day.** B(D−1) is at or above the 90th percentile of B over the 250
  sessions strictly before D−1. It needs 250 prior sessions, so the test
  starts in 2017.
* **Population P:** name-days D where D−1 was broad and the name's
  |move_atr(D−1)| ≥ 1.
* **Comparison C:** name-days D where D−1 was NOT broad and
  |move_atr(D−1)| ≥ 1.
* **Outcomes,** in % with continuation positive:
  * y_raw = sign(move) × r(D), the name's open → close;
  * y_adj = sign(move) × (r(D) − r_XIU(D)).

## Statistics

* **The mean of y over P,** with a t clustered by the date D (the names moving
  together on one day are one draw, not many).
* **P − C:** the difference of the two means, its standard error from the two
  date-clustered standard errors.
* **Placebo:** 1,000 draws (seed 135). Each relabels which sessions are broad,
  keeping their number and choosing among sessions that have movers. Two-sided
  p is the share of draws with |mean| ≥ the observed |mean|.
* **Blocks:** four chronological blocks of the broad sessions, and the sign of
  the mean in each.
* **Positive control** (house rules 4 and 10): a planted reversal of −0.30% on
  y over P must show at t = −0.30 / se ≤ −3; otherwise UNDERPOWERED.
  MDE80 = (3 + 0.84) × se.
* **The market itself** (no verdict, n ≈ 260): XIU's own open → close on D,
  signed by the direction of D−1's movers (the sign of their median
  move_atr). Reported with its t and MDE.

## Verdicts (on RAW; the adjusted reading beside it)

| Verdict | Needs all of |
|---|---|
| REVERSAL | mean < 0; t ≤ −3; placebo p < 0.01; ≥ 3 of 4 blocks < 0; median < 0 |
| CONTINUATION | mean > 0; t ≥ 3; placebo p < 0.01; ≥ 3 of 4 blocks > 0; median > 0 |
| NULL | neither, with the control passing |
| UNDERPOWERED | neither, with the control failing |

## What a result changes

* **REVERSAL:** a switch offered to the owner. After a broad day, the Top 2
  never takes a position in the direction of the prior move, and the
  passed-over chase is recorded as a shadow. The forward record decides; it
  is not a new desk and is not sized.
* **CONTINUATION:** the same, mirrored, offered the same way.
* **NULL:** no rule. R2 (skip big movers) stays the tested answer. The owner
  is told that after broad days neither chasing nor fading has carried an
  edge.

Script: `breadth_reversal.py`. Summary: `data/breadth_day135d.json`.
