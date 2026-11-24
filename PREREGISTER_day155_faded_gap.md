# PREREGISTER day-155: the faded gap, Claude's short thesis (council lab item 17)

Registered 2026-11-24 in the council-lab slot, before any return in it was
computed. The script, `faded_gap.py`, is committed in its own commit before it
runs, next weekday, and it gets one look. It reads cached bars only
(`.rb-state/report_day_cache`, day-143's download), so it costs nothing.

## The question

* **Why.** On 11-24 both of Claude's shorts rested on one setup:
  * SHORT HUT.TO: "+19.4% gap faded from the 82.00 high to close 73.80, below
    vwap";
  * SHORT CLS.TO: "+13.8% gap reversed from 337.32 to close 306.77, below
    vwap".

  The setup is a name that gapped a normal day or more at the open, then
  closed back against its gap. The brief shows it to every model as
  `gap_atr` with the prior session's open and close.
* **Does following the fade earn anything the next session?** That means
  SHORT after a faded up-gap and LONG after a faded down-gap, from 09:45 to
  the close against XIU.
* **If it does,** it could break ties among Claude's nominations. **If it
  reverses,** a remove-only pass-over could be proposed: drop a Claude pick
  that follows a faded gap. Either goes to the owner as a proposal, never
  live from this slot.
* **What the record says so far.**
  * Day-132 (#47): following a ≥ 1 ATR close-to-close move into 09:45 → close
    was null, powered.
  * Day-152 (#67): a name's 20-session intraday habit leaned toward reversal
    (t = −2.52), short of the bar.
  * Day-117's field scan found nothing in the gap fields or the VWAP
    distance, each taken alone.
  * The faded gap (the gap and the intraday leg in opposite directions) has
    not been tested.

## The definitions

These use the brief's own arithmetic (`daily_technicals.context`) on
dividend-adjusted daily bars.

* **The prior session** is d−1, the market's session before d. d−2 is the
  one before that.
  * The name's bars on the 14 sessions ending at d−1 must be the market's
    consecutive sessions; otherwise the name is skipped on d.
* **ATR** is the mean of the 14 true ranges ending at d−1 (d−1 included),
  each against its own prior close.
* **The gap:** `gap_atr = (open(d−1) − close(d−2)) / ATR`.
* **The setup:**
  * **a faded up-gap:** gap_atr ≥ 1 and close(d−1) < open(d−1). Side:
    SHORT;
  * **a faded down-gap:** gap_atr ≤ −1 and close(d−1) > open(d−1). Side:
    LONG.

  The cache keeps four prices per session (open, 09:45, noon, close), so
  "below vwap" cannot be computed. The close against the open stands in for
  it.
* **The outcome** on session d:
  `y = side × (the name's 09:45 → close − XIU's 09:45 → close)`, in %.
  * The 09:45 price is the close of the 09:30 fifteen-minute bar.
  * The close is the session's last bar (the record's window).
  * Each (name, session) is one event, and each event is one pick.

## The data (all cached; no API call)

* **Primary.**
  * The 150 names: `data/report_day143_names.json`.
  * FMP 15-minute session prices, 2024-01-02 → 2026-10-29, for the outcome.
  * FMP dividend-adjusted daily bars for the setup.
  * **Counted at registration** (prior-session prices only; no price on d
    was read):
    * 1,209 events: 512 SHORT and 697 LONG;
    * on 357 of 707 sessions, across all 150 names;
    * 159 of them from a gap of 2 ATR or more.
* **Secondary, signs only.** The outcome is open → close on d against the
  market's open → close, because daily bars have no 09:45 price.
  * **(a) The same 150 names over ten years**, 2016-01-04 → 2026-10-29,
    against XIU. Counted: 4,218 events on 1,599 sessions (1,972 SHORT).
  * **(b) The point-in-time S&P 500**, against SPY. This is the survivor
    check (day-138's rule): it counts only members on d, by day-138's
    membership intervals. Counted: 14,303 events on 2,360 sessions (6,805
    SHORT), on 661 names.

## The bar (seed 155)

* **The statistic** is the mean of y over the events, with a
  session-clustered t (`replay_fmp_analyst.clustered`).
* **FOLLOWS (supports a tie-break by the setup)** needs all of:
  * mean > 0 with t ≥ 3;
  * all four blocks positive. The blocks are equal numbers of events in date
    order;
  * a placebo p < 0.01, one-sided. Each event moves to a random session of
    the same name at least 5 sessions away, keeping its side, and the mean is
    recomputed. There are 2,000 draws, and p is the share at or above the
    observed mean;
  * the per-pick edge above the measured cost: mean − 0.13% > 0;
  * both secondary panels' means positive.
* **REVERSES (supports a remove-only pass-over)** needs:
  * mean < 0 with t ≤ −3;
  * all four blocks negative;
  * the placebo p < 0.01 the other way: the share of draws at or below the
    observed mean;
  * both secondary panels' means negative.
* **The control.** A planted 0.30% an event must show at t ≥ 3. It is
  computed as 0.30 / se, never (mean + 0.30) / se. Otherwise the verdict is
  UNDERPOWERED. The smallest effect detectable at 80% power (2.8 × se) is
  printed beside it.
  * 0.30% is chosen as the smallest edge that would matter: it clears the
    0.13% round trip with room to spare.
* **Everything else is NULL.** Anything but FOLLOWS or REVERSES is rejection
  #70.

## Beside the verdict (descriptive, never a verdict)

* **The two legs apart:** SHORT after a faded up-gap; LONG after a faded
  down-gap. The LONG leg is a long rule on today's list (day-138), so read it
  beside the S&P 500 panel.
* **Gaps of 2 ATR or more.**
* **A full reversal:** close(d−1) back beyond close(d−2), against the gap.
* **The held gap:** gap_atr ≥ 1 with the close at or beyond the open in the
  gap's direction, following the gap.
* **Other windows on d:**
  * open → 09:45, before the entry;
  * 09:45 → noon.
* **By year:** 2024, 2025, 2026.
* **Hit rates** beside every mean.
* **The live record.** Claude's council nominations since 2026-10-14
  (`data/model_picks.csv`, kind `nominated`) whose side follows a faded gap on
  the prior session:
  * the count, the hit rate and the mean `r_pct`, against Claude's other
    nominations;
  * the prior sessions come from FMP daily bars fetched at the run (no model),
    because the cache ends 10-29;
  * far too few to judge.

## What a result changes

* **Nothing live.**
  * A FOLLOWS goes to the owner as a proposed tie-break among Claude's
    nominations.
  * A REVERSES goes as a proposed remove-only pass-over of a Claude pick that
    follows a faded gap.
  * Either goes live only with the owner's yes, under its own registration
    and a forward shadow.
* A NULL or UNDERPOWERED is rejection #70. Nothing is built from it.

## Not blind, said plainly

* **The related results above** (#47, #67 and day-117's field scan) are
  known. No split of the faded gap against a next-session return has been
  computed on any panel.
* **The live record's totals are known:** "Claude (nominated, forced)" reads
  65/108, +0.22% gross, on the 11-24 scoreboard.
* **11-24's HUT.TO and CLS.TO** prompted this. Their outcome was not known at
  registration, and the session is outside every window here.

## Cost

* None: cached bars, plus about 60 FMP daily calls for the descriptive live
  record. No model.
