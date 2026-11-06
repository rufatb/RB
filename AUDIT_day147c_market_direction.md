# Day-147c audit — the market's direction after 09:45 cannot be read at 09:45 (rejection #62)

The owner, after 11-05: "Fix the main root problem." The picks win or lose
with the market's and the sector's move after the 09:45 entry. This test asked
whether that move can be seen coming at 09:45. Registered first
(`PREREGISTER_day147c_market_direction.md`, ca823c4); script
`market_direction.py` (fd7b142), committed before its one look; summary
`data/market_direction_day147c.json`. No model was asked.

## What was measured

* **707 TSX sessions**, 2024-01-02 → 2026-10-29, from the day-143 cache (FMP
  15-minute bars: the open, 09:45, noon and the close). None was left out.
* **The outcome:** XIU.TO from 09:45 to the close. It averaged +0.03% with an sd
  of 0.58%.
* **The primary predictor:** the market's move so far, XIU.TO's prior close →
  09:45. It was up on 58% of mornings.
* **y** = the sign of the morning's move × the rest of the day, per session.

## The verdict: NULL, powered

| | Sessions | Mean a session | t | Placebo p (two-sided) | Right |
|---|---:|---:|---:|---:|---:|
| **Primary: XIU's move so far** | 707 | −0.030% | −1.41 | 0.16 | 51.4% |
| SPY's own version (house rule 3) | 704 | −0.021% | −0.72 | 0.47 | 48.4% |

* **The blocks disagree:** −0.04%, −0.07%, +0.03%, −0.03%.
* **Each year leans slightly to fading the morning, never significantly:**
  2024 −0.04% (t = −1.40), 2025 −0.03% (t = −0.76), 2026 −0.02% (t = −0.39).
* **The control:** a planted 0.10% a session shows at t = 4.62. The smallest
  detectable effect at 80% power is 0.083% a session, a hit rate of about 57%.
  A lean that would matter to a pick would have shown.

## Beside the verdict (descriptive; Holm across six)

| Arm | Sessions | Mean | t | Holm p |
|---|---:|---:|---:|---:|
| S1 XIU's first fifteen minutes | 707 | −0.002% | −0.07 | 1.0 |
| S2 XIU's overnight gap | 707 | −0.015% | −0.71 | 1.0 |
| S3 SPY's move so far, for XIU | 688 | −0.024% | −1.07 | 1.0 |
| S4 XIU's prior session | 707 | −0.006% | −0.29 | 1.0 |
| S5 breadth at 09:45 (the 150) | 707 | −0.026% | −1.21 | 1.0 |
| A sector's move so far, for the same sector | 707 | +0.003% | +0.19 | 1.0 |

* **Big mornings** (the market already 0.5% or more either way by 09:45, 214
  sessions): −0.03%, t = −0.61, 52% right. Small mornings: −0.03%, t = −1.32.
* **Ten years of daily bars** (XIU's gap against its open → close, 2,864
  sessions from 2015): +0.005%, t = 0.37, 50.7% right.
* **The sector arm** is the one the record points at: a pick's sector moved
  against it on 125 of 216 reviewed picks and its way on 87 (−0.22% a pick). A
  sector neither
  keeps nor gives back its morning move (53% right, +0.003%), so nothing at
  09:45 says which side of its sector a pick should be on.

## So

* **Nothing known at 09:45 says which way the market or a sector will go next.**
  The rest of the day is a coin flip. It does not depend on the morning's own
  move, the overnight gap, the US market, breadth or the prior session, and big
  mornings are no different.
* **What it means for the picks:**
  * the part of a pick's result that comes from the market and its sector
    cannot be forecast from the morning;
  * the only protection on the record is not to bet on it: one long and one
    short together, which is Claude's Top 2 rule since 11-02.
* **Nothing changes.** Rejection #62. Day-147's lab item 8 takes #63 (its
  amendment 1).
* **Day-43's list of untested new information is now down to one source:** L1/L2
  order-book depth. Short interest was #38, overnight news day-118/122, and
  index state at 09:45 is this test.
