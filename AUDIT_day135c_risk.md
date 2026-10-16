# Day-135c audit — two risk rules for the Top 2 (owner, 2026-10-15)

Registered first: `PREREGISTER_day135c_risk.md` (00eeb8d). Script:
`risk_rules.py`. Summary: `data/risk_day135c.json`.

## The question

After 10-15 (SHORT CLS.TO and SHORT CCO.TO, both lost), the owner asked what
can stop "today's type of insane wipeouts", and for a predictor that does not
"just carry last day's pattern into the next one … unless it's a recovery".

Day-132 (rejection #47) already answered the direction: after a move of
≥ 1 ATR, neither following it nor fading it carries an edge from 09:45. So two
SIZE rules were registered, both blind to direction:
* **R1**, at most one position per side;
* **R2**, skip a name that moved ≥ 1 ATR in the last session.

## The data

* **Coverage.** 150 names, 2,706 sessions (2016-01-04 → 2026-10-14), 389,034
  name-days with both bars. No fetch failed.
* **Bars.** FMP dividend-adjusted daily bars, from the day-135b cache.
* **The trade proxy** is the session's open → close. The live trade enters at
  09:45, which daily bars cannot see.
* **The prior move** is `move_atr` exactly as `daily_technicals.context`
  computes it: the last session's close-to-close move over the mean true range
  of the 14 sessions ending there.

## R1 — one position per side: FAIL (rejection #51)

From 20,000 random sessions of random pairs (seed 135):

| Book | sd of the session's sum | worst 5% of sessions |
|---|---:|---:|
| two picks, same side | 3.31% | −5.00% |
| two picks, one long and one short | 2.94% | −4.33% |
| one pick | 2.21% | −3.16% |

* **Correlation.** Two names correlate 0.12 on an average session, and 0.25 on
  a session when XIU moves 1% or more.
* **The verdict.** The same-side book swings 1.13× wider than the long/short
  book, below the registered 1.15. **FAIL.**
* **What stays.** The day-135 one-direction warning, which is display only.

## R2 — skip the last session's big movers: PASS

| Next session after… | name-days | sd | sd vs XIU | moved > 3% | worst 1% |
|---|---:|---:|---:|---:|---:|
| a move of ≥ 1 ATR | 49,295 | 2.67% | 2.56% | 16.0% | −7.29% |
| a smaller move | 336,787 | 2.15% | 2.05% | 11.1% | −5.95% |

* **Swing.** The movers swing 1.24× wider, against a bar of 1.15.
* **Lean.** The return signed by the move (following it is positive, against
  XIU) is −0.005%, with a date-clustered t of −0.24. The bar was |t| < 2.
* **The verdict.** **PASS.** R2 changes the size of the swing, not the bet.
* **Control** (house rules 4 and 10; reported after the verdict):
  * a planted 0.10% lean would show at t = 4.48;
  * the smallest detectable lean is 0.063%.

  The null on the lean is powered.

## Descriptive (added after the verdicts; no verdict)

* **The same name, not just volatile names.**
  * Each name's own swing after its big moves, against its other days: median
    1.21×.
  * 96% of names swing wider after their own big moves.
* **Every year.** The ratio is 1.12–1.32 in each year from 2016 to 2026.
* **Bigger moves.** After a move of ≥ 2 ATR the swing is 1.59× wider.
* **"Unless it's a recovery."** The next session against XIU:

  | After | n | mean | t |
  |---|---:|---:|---:|
  | a fall of ≥ 1 ATR | 22,800 | +0.009% | 0.25 |
  | a fall of ≥ 2 ATR | 2,295 | −0.147% | −1.04 |
  | a rise of ≥ 1 ATR | 26,495 | −0.002% | −0.08 |
  | a rise of ≥ 2 ATR | 2,640 | +0.027% | 0.34 |

  There is no bounce to bet on. A bounce bet also swings just as wide: it is
  the same name on the same day, held the other way.
* **How many names it touches.** On a median session 11% of the 150 are big
  movers, and 23% at the 90th percentile. On 10-15 it was 52 of 150 (35%),
  after a big day.

## The live Top 2 since 10-05 (descriptive, too few to judge)

* **The picks.** 13 picks over 8 sessions; 10 were on big movers. For 10-15's
  CLS and CCO, the moves come from that morning's brief.
* **All 10 FOLLOWED the move.** The council's Top 2 has never once bet on a
  bounce.

| Top 2 picks | n | right | mean, 09:45 → close |
|---|---:|---:|---:|
| on a big mover | 10 | 4 | −0.58% |
| the rest | 3 | 1 | −0.33% |

The ten-year measure is the test; thirteen picks are an anecdote.

## On 10-15

* **The council's table.** Every position the council agreed on was a big
  mover:
  * CLS −1.51 ATR;
  * CCO −1.46;
  * HUT −1.30.

  EFR (−1.69) was short of consensus.
* **What happened.** As shorts they lost 3.6%, 4.2%, 11.2% and 7.3% from
  09:45.
* **With the switch on**, the dry run on that morning's sealed council printed
  "The council agreed only on the last session's big movers — passed over,
  nothing to act on". It named EFR as unable to stand as runner-up.
* **With the switch off**, the flash would have carried two cautions, "Both
  picks are SHORT…" and "The last session's big movers: SHORT CLS.TO follows a
  fall of 1.5 normal days · SHORT CCO.TO follows a fall of 1.5 normal days".

## What ships

1. **The caution, always on (display only).** "⚠ The last session's big
   movers: … follows a fall of 1.5 normal days …":
   * under the picks in every Top 2 table (flash, report, picks-only, late);
   * in the email's and the flash's heroes;
   * above the page's table.

   Only picks trigger it; a runner-up never does.
2. **The switch, `council.SKIP_MOVERS`: OFF until the owner says yes.** On:
   * **The picks.** The Top 2 is the council's agreed positions in tally order,
     passing over any name that moved ≥ 1 ATR in the last session. The moves
     are `council.json`'s `moves`, copied from the brief's rows, so they are
     the same `move_atr` every member read. A name with no measured move is
     not passed over.
   * **No runner-up.** A big mover is never the runner-up.
   * **Shown and recorded.** The passed-over positions are printed, and
     recorded as `top2mover/pick`. That is a shadow: scored, never sized,
     never pooled, never on the scoreboard. The evening review scores it in
     its own section, outside the lessons.
   * **The record.** It splits at rule_version `+day135c-movers`. The 09:46
     entry check still applies afterwards.
   * **The memory council** follows the same switch, so its paired test is
     still memory or no memory.
3. **Why a passed-over slot is refilled and a 09:46 void is not.** The move is
   known before the council sits; it is in the rows every member read. So R2
   decides which agreed positions are eligible. E1 checks positions already
   chosen, at 09:46.

## Not claimed

* **No pick is made more likely to be right.** The lean is −0.005%. What
  changes is that the Top 2 stops holding the names that swing widest the
  next day.
* **It is not every protection.** Two same-side picks still share one
  exposure; R1 failed, so that stays a warning.
* **It can empty the Top 2.** On a day like 10-15, when a third of the list
  moved big, the result is "nothing to act on".
* **The test is a proxy.** It measures open → close; the live trade enters at
  09:45.
* **The other lever is the noon exit** (day-130 H3: no worse, 15% less swing),
  shown and never applied. On 10-15: CLS −0.79% at noon against −3.61% at the
  close; CCO −3.64% against −4.17%.
