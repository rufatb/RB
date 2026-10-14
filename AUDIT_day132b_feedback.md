# Day-132b — an outside read of the scoreboard, tested (owner, 2026-10-14)

Registered first: `PREREGISTER_day132b_feedback.md` (82ac6f2). The harness was
committed before its result (889d631). Script: `feedback_review.py`; summary:
`data/review_day132b_feedback.json`.

| Claim | Verdict |
|---|---|
| C1 costs make it a slow bleed | **Right.** Gross is zero, so net is minus the costs. "Borrow" is wrong for a same-day short. |
| C2 the debate destroys signal; take the top-conviction pick | **Not supported.** The 25% row is Part 5, not the council. The council is the best row of its sessions. Conviction does not rank picks. |
| C3 reacting to the open beats predicting | **Not supported.** "DeepSeek late" is 2 sessions; the wire row is not green; four registered tests of the open are null. |
| C4 nine sessions prove nothing | **Right, and stronger:** 60 sessions resolve only an edge of ≥ 0.33% per pick. |
| C5 prior-day momentum is picked over | **Right.** #47, measured today. |
| C6 biotech is the likelier place | **Plausible and untested.** 1 of 31 events resolved; it can only be judged forward. |

## C1 — costs: right in substance

* **Entry spreads at 09:46, measured.** 54 sized legs over 11 publications.
  Median 9.2 bps; interquartile 4.3–14.9; max 33.5.
* **Round trip: 0.07% to 0.19%.**
  * Low: half the spread in, the closing auction out, 0.01% commission a
    side.
  * High: the full spread, 0.05% commission a side (not measured).
* **Borrow:** a short opened and closed the same day carries no overnight
  borrow fee.
* **The negatives are not the market.** The books are near balanced (the Top 2
  is 8 long, 7 short). XIU rose 0.06% per session from 09:45 to the close
  over these 15 sessions. The market's part of the Top 2 mean is +0.02%.
* **Pooled.** Every unique pre-open model pick (61 picks, 14 sessions)
  averages −0.15% gross, t = −0.88, 41% right. That is zero gross, so net is
  −0.22% to −0.34%.

A strategy with no edge loses its costs on every trade. "Coin flip" describes
the gross; the net is a slow bleed of roughly 0.1–0.2% a trade.

## C2 — the consensus step: not supported

* **The 25% row is Part 5's debate,** not the four-model council. In it,
  DeepSeek cross-examines and Jev judges. It went 2/8 over 5 sessions (95%
  range 7–59%), and it already failed its own 59-session replay (21/43).
* **The council is the Top 2 row.** On its own sessions (10-05 → 10-13):

| Source, same 6 sessions | Picks | Right | Mean | vs XIU |
|---|---:|---:|---:|---:|
| **Council Top 2** | 9 | 44% | **+0.02%** | −0.02% |
| Gemini selected | 14 | 36% | −0.29% | −0.29% |
| DeepSeek selected | 5 | 20% | −0.14% | −0.11% |
| Jev forced | 10 | 30% | +0.06% | +0.06% |
| Engine | 19 | 32% | −0.36% | −0.29% |
| Debate final (Part 5) | 5 | 20% | −0.86% | −0.98% |
| Highest-confidence desk pick | 6 | 33% | +0.02% | +0.01% |

* **The highest-confidence desk pick was Gemini's every time.** Its
  confidences run higher; they are on its own scale. Paired against the
  council: −0.06%, t = −0.2, MDE 0.82%.

**T1 (registered): does a model's own confidence rank its picks?** The data
are 479 replay picks: 154 (run, session) units over 59 sessions and four runs.
* **Statistic.** The top-confidence pick minus the rest: **−0.20%**, t = −1.14.
  The top picks were 44% right; the others 52%.
* **Placebo.** p = 0.91 (one-sided, for "better").
* **Rank correlation.** −0.02 (95% −0.11 to +0.08).
* **Per run.** flash −0.34, research −0.32, v4-pro −0.27, single +0.47.
* **Verdict: UNDERPOWERED** by the registered rule: the planted 0.5% shows at
  t = 2.91, just under 3. The estimate sits on the wrong side, and the
  correlation's interval excludes anything above +0.08.

Choosing by conviction picks by a number that does not sort. And the council
is not destroying a signal: there is none to destroy.

## C3 — reacting to the open: not supported

* **DeepSeek late:** 8 picks on 2 sessions (09-24 and 09-28), 5/8, +0.65%.
  * Its books were 4 long / 4 short, so the market's part is exactly zero.
  * On both days its shorts won and its longs lost.
  * Claude, asked the same mornings, went 2/6 (−0.05%); Jev 1/4. All late
    picks: 18 on 2 sessions.
* **The wire row** is 2/5 at −0.14%: not green.
* **Every registered test of acting on the open is null:**
  * #42, gap continuation: t = 2.63, failed its bar;
  * day-130 H5, first-half-hour momentum: +0.0002% on 6,511 name-days;
  * #46, the first half hour on report days: t = 0.50;
  * day-121b, entering at the open: t = 0.44;
  * day-125 and day-122: analyst changes and releases are priced by the open.
* **Untested:** a model ASKED after the open, at scale. That can be registered
  on the 59 replay sessions.

## C4 — sample size: right, and stronger than stated

The per-pick sd is 1.30%. At t = 3:

| Edge per pick | Picks needed | Sessions at 2 a day |
|---:|---:|---:|
| 0.3% | 169 | 85 |
| 0.2% | 380 | 190 |
| 0.1% | 1,517 | 760 |

The MDE80 is 0.41% at 40 sessions and 0.33% at 60. Sixty sessions can rule
out only a large edge. The costs (0.07–0.19%) are below what they can resolve.

## C5 — prior-day momentum: right

Day-132 (#47): 10,332 moves of ≥ 1 ATR. Continuation after 09:45 was
−0.01%, t = −0.44, and the test was powered.

## C6 — biotech: plausible, untested, and only testable forward

* **The record.** 31 events, one resolved (IVVD, SHORT, +3.9%). Four more
  close in October, 2 in November, 19 in December and 5 in March 2027.
* **The calls are re-made daily.** There are 171 calls on 31 events; the
  first calls are 19 LONG and 12 SHORT.
* **No honest replay.** A historical replay is contaminated: the models may
  remember how past readouts went.
* **What a fair forward test needs:**
  * an XBI-relative score for each window;
  * an always-long baseline;
  * a bar registered before the ~25 events resolve.

## Today (10-14), from FMP bars to the 15:55 close (the evening job scores officially)

| Pick | Since 09:45 | vs XIU | vs its sector ETF |
|---|---:|---:|---:|
| Top 2 SHORT SSRM.TO | +1.20% | +0.77% | −0.57% (XGD) |
| Top 2 LONG CNQ.TO | −0.46% | −0.03% | −0.10% (XEG) |
| Gemini SHORT CCO.TO | +3.85% | +3.42% | +3.49% (XEG) |
| Gemini LONG SHOP.TO | −3.53% | −3.10% | −1.15% (XIT) |
| DeepSeek SHORT AC.TO | +1.63% | +1.20% | — |
| DeepSeek SHORT EMA.TO | −2.42% | −2.85% | −1.90% (XUT) |
| Jev forced LONG RBA.TO / SHORT OTEX.TO | −0.43% / +1.06% | | |
| Engine SHORT CP.TO / MFC.TO | −0.80% / −0.23% | | |

XIU fell 0.43% from 09:45 to the close. The Top 2 averaged +0.37% before
costs. SSRM "won" because gold fell: against XGD, the short lost 0.57%.
