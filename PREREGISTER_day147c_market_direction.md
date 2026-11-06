# Day-147c — can the market's direction after 09:45 be read at 09:45? (the owner, 2026-11-05)

**Registered 2026-11-05 evening, before any return in this test was computed.**
Nothing here changes a live pick, a size, the Top 2, a prompt or the email.

## Why

* **The owner, after 11-05:** "Fix the main root problem." Read as: the picks
  win or lose with the market's and the sector's move after the 09:45 entry.
  * 11-03: 7 of 8 longs right and 5 of 6 shorts wrong (XIU +0.17% after 09:45).
  * 11-05: 1 of 14 longs right and 8 of 10 shorts right (XIU −1.8%).
* **On the record** (every model pick reviewed 09-29 → 11-05, each name, side
  and day once; counted before this registration):
  * the stock's own move against its sector: 107 of 208 right, +0.19% a pick;
  * its sector's move: 87 of 216 the pick's way, −0.22% a pick;
  * the market's move: 107 of 218, −0.03%;
  * for the Top 2, the sector's move is 60% of a pick's variance.
* **Never tested here.** Day-43 listed "index futures state at 9:45" among the
  four untested sources of new information. Day-130's H5 was the first half
  hour against the last at the NAME level; day-137's H2 was the prior session's
  sector move. Neither asked whether the market itself, or a sector, keeps or
  gives back its morning move.
* **What is expected.** An index's direction is close to a coin flip; the
  published intraday-momentum result (the first half hour predicting the LAST
  half hour on the S&P 500) is about the last thirty minutes, not 09:45 → close.
  The likely answer is no, and then a long and a short together (Claude's rule
  since 11-02) is the only protection the record supports.

## The population (fixed now)

* **Sessions:** every TSX session in the day-143 cache
  (`.rb-state/report_day_cache/tsx/`, FMP 15-minute bars reduced to the open,
  the 09:45 price, noon and the close), 2024-01-02 → 2026-10-29, where XIU.TO
  has all four prices and its prior session's close. A session missing any of
  them is left out and counted.
* **09:45 price:** the close of the 09:30–09:45 bar. **Close:** the close of the
  last bar (15:45–16:00). **Prior close:** FMP's unadjusted daily close of the
  prior session (`eod`).
* **SPY:** FMP 15-minute bars and daily closes over the same months, fetched
  into `.rb-state/market_direction_cache/` by the script. SPY's prior close →
  09:45 contains the US overnight, pre-market and first fifteen minutes. A TSX
  session without a SPY session (a US holiday) is left out of the SPY arm only.
* **The sector arm:** the 150 names grouped by `data/tsx_sectors.json`'s
  `sector`; a sector's move is the median of its names with all prices that
  session, and a sector-session needs at least 3 names.

## The measure

* **The outcome:** XIU.TO's return from 09:45 to the close, in %.
* **The primary predictor, "the market's move so far":** XIU.TO's return from
  the prior close to 09:45.
* **y** = sign(predictor) × outcome, one per session (a predictor of exactly
  zero gives y = 0). The mean of y is the gain from following the morning's
  direction; a negative mean is the gain from fading it.

## The bar (seed 1473)

* **PREDICTABLE** (the morning's direction tells the rest of the day's) needs
  all of, on the primary:
  * |t| ≥ 3 over sessions (t = mean / sd × √n);
  * a two-sided sign-flip placebo p < 0.01: each session's y flipped as a unit,
    10,000 draws;
  * the four blocks of sessions (contiguous quarters in date order) all of the
    same sign;
  * the same sign on SPY's own version (SPY's prior close → 09:45 against its
    09:45 → close) with |t| ≥ 2 (house rule 3: both markets);
  * |mean| above 0.02%, XIU's round trip.

  Its sign says FOLLOWS (positive) or FADES (negative).
* **The control.** y is centred on zero and 0.10% added to every session. It
  must show at t ≥ 3, else the verdict is UNDERPOWERED. The smallest detectable
  effect at 80% power is printed.
* **Anything but PREDICTABLE is rejection #62.** Lab item 8 (day-147, written
  there as #62) then takes #63; its test is unchanged.

## Beside the verdict (descriptive; Holm across these six arms, never a verdict)

Each through the same machinery, with its own placebo; Holm-adjusted p printed.
* **S1** XIU's first fifteen minutes (open → 09:45).
* **S2** XIU's overnight gap (prior close → open).
* **S3** SPY's move so far (prior close → 09:45) predicting XIU's 09:45 → close.
* **S4** XIU's prior session (close to close).
* **S5** breadth at 09:45: the share of the 150 above their own prior close,
  minus one half.
* **The sector arm:** a sector's move so far against the same sector's 09:45 →
  close, pooled over sectors, the mean taken per session first.
* An arm that would clear the primary's bar (without the SPY check) at its
  Holm-adjusted two-sided placebo p is a lead for its own registration, never
  adopted from here.
* Also printed: the hit rates; each year; days whose move so far is at least
  0.5% either way; the ten-year daily proxy (XIU's gap against its open →
  close, 2015 →, FMP adjusted daily), which enters at the open, not 09:45.

## What follows, decided now

* **PREDICTABLE** goes to the owner as a proposal, not a rule: a forward shadow
  that prints the morning's direction beside the picks under its own
  registration. Nothing live changes from this test.
* **Anything else** is written up as rejection #62. Nothing changes; a long and
  a short together remains the record's answer to the market's swing.
* **The script** (`market_direction.py`) is committed before it runs and gets
  one look. It reads the cache and FMP (SPY): no model call, no OpenRouter.
