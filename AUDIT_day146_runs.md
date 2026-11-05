# Day-146 — three days one way: following a three-day run does no worse on day four (rejection #61)

The owner asked for this on the evening of 2026-11-04, after 11-04's CLS.TO
long lost 5.21%. It ran the same evening in one look.
* **Registered** in `PREREGISTER_day146_runs.md` (4498c81), before any return
  was computed.
* **Script:** `runs_history.py` (ee98ee8), committed before the run.
* **Summary:** `data/runs_day146.json`.
* **Data:** day-143's cached bars, with no API call for the test. The live
  record's split read FMP daily closes.

## The owner's reading

A pick that bets a run carries on is the one that loses: a short after three
falls meets a rebound, and a long after three rises meets profit-taking, "even
though the technicalities were correct".

## The definitions

* **A run** is three completed sessions closing the same way in a row, close to
  close. A flat close breaks it.
* **Following a run** is LONG after three rises, SHORT after three falls.
* **The measure** is the fourth day from 09:45 to the close, against XIU over
  the same window, signed by the run.

## The verdict: NULL, powered

| Bar | Registered | Result | |
|---|---|---|---|
| Size and sign | mean < 0, t ≤ −3 | **−0.021% a name-day, t = −0.96** | not met |
| Blocks | all four negative | +0.05%, −0.07%, −0.06%, +0.00% | not met |
| Placebo | p < 0.01 | p = 0.12 | not met |
| Ten years, TSX (daily open → close) | mean < 0 | −0.011%, t = −0.80 | met |
| Point-in-time S&P 500 (daily) | mean < 0 | −0.012%, t = −1.18 | met |
| Control | a planted 0.10% at t ≥ 3 | t = 4.57 | detected |

* **The primary panel:** 24,915 name-days with a run, over 707 sessions
  (2024-01-02 → 2026-10-29), on the 150 names. 49.5% went the run's way.
* **The smallest detectable effect is 0.061% a pick.** A reversal larger than
  that would have shown. The one measured is a third of it, and it changes
  sign between blocks.
* **Rejection #61.** "A three-day run turns on day four" is not something the
  record can see. Every panel leans very slightly the owner's way, but none
  comes near the bar.

## Beside the verdict (descriptive, never a verdict)

* **By run length.**
  * Exactly 3 days: +0.019%.
  * 4 or more: −0.063% (t = −2.07).
  * 5 or more: −0.063% (t = −2.02).
  * None reaches t = 3, and nothing here is tuned to 4 days.
* **By side.**
  * LONG after an up run: +0.000% (t = 0.01). Profit-taking does not show.
  * SHORT after a down run: −0.052% (t = −1.70). A slight rebound, short of
    any bar.
  * On the S&P 500 it is the other way round: longs −0.020%, shorts −0.002%.
* **By size.** The three days' total move, in normal days, shows no gradient:
  under 1 −0.030%, 1–2 −0.022%, 2 or more −0.013%.
* **Before the entry.** From the open to 09:45 the run carries on slightly
  (+0.043%, t = 3.17), and open → close is +0.022%. What little happens is
  over by the entry.
* **By year** (TSX, ten years): both signs, between −0.12% and +0.05%.
* **The live record** (2026-09-17 → 11-04, 228 unique scored picks; the
  record's yardstick, raw):

  | | Picks | Right | Mean |
  |---|---:|---:|---:|
  | Following a three-day run | 53 | 28 (53%) | +0.01% |
  | Not | 175 | 88 (50%) | +0.00% |

* **The owner's examples.**
  * Two picks fit: 11-03's SHORT SHOP.TO (three falls, −1.18%) and 11-04's
    DeepSeek SHORT SHOP.TO (four falls, −3.42%).
  * Others that followed runs won: 11-03's LONG FTS.TO (+0.77%), LONG TRI.TO
    (+1.46%) and SHORT CCO.TO (+2.75%).
  * 11-04's CLS.TO long followed one up day after a month's fall, so it was
    not a three-day run.

## The rule, as the owner asked (decided in the registration)

The registration said the rule would be built whatever the result, and
switched on at the owner's request on REVERSAL or NULL. It is on from the
2026-11-05 morning (`council.SKIP_RUNS = True`, rule `day146-runs`).
* **How it works.**
  * `council.stage` records each name's run from FMP's daily closes
    (`runs.py`).
  * A Claude pick that follows a run gives way to Claude's next nomination on
    that side. If both follow runs, that side is empty.
  * The council's own Top 2 is remove-only.
* **The record.** Passed-over picks are recorded as `top2run/pick`, a shadow,
  and the review scores them.
* **The forward judgement** comes at 40 sessions with a passed-over pick: the
  passed-over picks against what stood in their place.
* **The dry run on the three Claude-led sessions** (the sealed councils, with
  FMP closes as of each prior session):
  * **11-02:** no change. Neither pick followed a run.
  * **11-03:** both picks change.
    * LONG FTS.TO (+0.77%) gives way to LONG BAM.TO (+0.27%).
    * SHORT SHOP.TO (−1.18%) gives way to SHORT WCP.TO (−1.14%).
    * The session would have read −0.44% a pick against −0.21% as printed.
  * **11-04:** no change. CLS.TO had risen one session; OVV.TO had fallen two.
* **What it costs.** On this evidence, nothing on average. It changes which
  picks are made, not how often they are right. A few sessions will look
  better or worse by luck either way.

## So

* **Rejection #61.** "A three-day run turns on day four" is not something the
  record can see.
* **The rule is on because the owner asked for it,** labelled as not shown to
  raise accuracy on history.
* **It would not have changed 11-04's CLS.TO loss.**
