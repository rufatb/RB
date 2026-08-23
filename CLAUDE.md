# Working notes for this repo

## "run report" means one command

```bash
TZ=America/Toronto python brief.py      # 09:46 ET, once per trading day
```

When the user says **"run report"**, run `brief.py`. It renders the whole
morning page AND writes the day's permanent record via `r945.publish()`.
Do not run `r945.py --book` instead — it publishes the same rows but prints
only the pair, without positions, the FDA calendar, or catalyst arithmetic.

After the close: `python ledger.py --score`.

## Before touching anything, read STRATEGY.md

It is the running record of every change tested — **36 rejections, 3
adoptions**. Almost every "obvious improvement" in this space has already been
measured here and refuted. Check before proposing.

The three adopted changes were all VARIANCE results. None improved accuracy.

## The constraint that governs the intraday engine

`r0`/`gap`/`vp` carry no usable signal. Gradient boosting with ~100x the
shipped k-NN's capacity reaches **AUC 0.5022 on 122,234 out-of-sample rows**,
while the identical harness detects a planted 52% coin at **z=15** (day-43).
The live record is a coin flip and is expected to stay one.

Do not promise better accuracy from this engine. Do not present its picks as
predictions. The report prints its own record beside every pick for this
reason.

## House rules, learned the hard way

1. **Never swallow an exception silently.** Day-29: a bare `except: pass` hid
   a `NameError` and no universe prints were written at all. Day-55: the same
   pattern hid 2,214 consecutive HTTP 403s. Count failures and report them.
2. **Fail closed on data.** Missing coverage, an unmarkable position, a stale
   print — say so and exclude it. Never carry a position at cost; absence of
   data is not absence of movement (day-42).
3. **Pre-register the bar before running the test**, and do not move it
   afterwards. Four quarters on both markets, or it is a window artifact.
4. **Every null needs a positive control.** A harness that cannot detect a
   planted edge cannot report a null. Day-51 and day-56 were both caught this
   way, and day-46's own bar turned out to be unsatisfiable for this reason.
5. **Placebo anything that looks like a prize.** Day-51's "oracle gap" of
   +2.34%/trade was smaller than pure noise produced (+2.85%).
6. **Sync before working.** The container resets between turns; `git fetch` and
   fast-forward first. A stale clone once put a wrong record in a live report
   (day-42).
7. **A ratio needs both legs from one population.** Day-71: P(CRL) is only
   meaningful because rejections AND approvals come from the same harvest, the
   same classifier and the same window. Mixing an EDGAR numerator with a
   Drugs@FDA denominator would have produced a confident number describing
   nothing. Where a leg might be undercounted, MEASURE the undercount and show
   the correction beside the raw figure rather than folding it in.
8. **A rate over a population is never a forecast for one name.** Print
   UNCONDITIONAL next to it every single time. It is the prior you argue away
   from.
9. **Verify the data you got, not the data you asked for.** Day-72: Yahoo
   answers `interval="1d", range="max"` with WEEKLY, MONTHLY or QUARTERLY bars
   and no error, so day-68's "3-day event window" was three months on some
   names and shipped for four days. Assert granularity, count what you reject.
10. **A control that cannot detect a planted edge means UNDERPOWERED, not
   NULL.** Day-72's run-up study can only resolve a drift above 6.2pp; "no
   effect found" there would be a claim the data cannot support. And build the
   control to measure `edge / sd`, never `(mean + edge) / sd`.

## Read-only, always

Nothing in this repo places, sizes, or cancels an order. `positions.py` records
what the user says they did. Keep it that way.
