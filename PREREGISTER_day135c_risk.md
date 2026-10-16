# Day-135c — can the Top 2's bad days be made smaller? Two risk rules (owner, 2026-10-15)

Registered BEFORE either measurement ran. Nothing below has been computed.

## Why

On 2026-10-15 the Top 2 was SHORT CLS.TO and SHORT CCO.TO. Both had fallen
about 1.5 normal days (ATR) the day before, and both lost when the market
turned up: −3.61% and −4.17% from 09:45 to the close. HUT and EFR, the other
shorts the system named, lost −11.2% and −7.3%. The owner asked what can stop
"insane wipeouts", and for a predictor that does not just carry yesterday's
pattern into today "unless it's a recovery".

**What is NOT re-tested.** Whether yesterday's move continues or recovers
after 09:45 was answered by day-132 (rejection #47): 10,332 moves of ≥ 1 ATR,
−0.013%, t = −0.44, and a planted 0.10% showed at t = 3.39. Neither chasing
nor fading carries an edge. No momentum or fade rule is proposed here.

**What IS asked: SIZE, not direction.** Can a rule make the bad days smaller
without making the average worse? Two candidates, both direction-blind.

## Data

* **Names:** the 150 names of the TSX list; XIU.TO as the market.
* **Bars:** FMP dividend-adjusted daily bars, cached by day-135b
  (`.rb-state/weeks_cache`).
* **Window:** 2016-01-04 → 2026-10-14, the last ten years.
* **The trade proxy:** open → close of the session (adjOpen → adjClose). The
  live trade enters at 09:45, after the open; daily bars cannot see 09:45.
  This is stated, not hidden.
* **The prior move:** move_atr = (close D−1 − close D−2) / ATR14 at D−1,
  computed as `daily_technicals.context` does.
* **Exclusions:** a name-day without both bars or 15 prior sessions is
  excluded, and counted.

## R1 — one position per side

Two picks on one side share the market's move.
* **ρ:** the average same-session correlation of two different names'
  open → close returns, over random pairs (20,000 pairs, seed 135).
* **Session swing for two picks of equal size**, from 20,000 random sessions
  of random pairs:
  * both on the SAME side;
  * one long and one short;
  * a single pick.
* **PASS:** the same-side swing (sd of the session's summed return) is at
  least 15% larger than the long/short swing. The 15% is the house's variance
  bar (day-120b H1, day-130 H8). The worst 5% of sessions is reported beside
  it.

## R2 — skip yesterday's big movers

A pick on a name that moved ≥ 1 ATR yesterday, in either direction.
* **Swing:** the sd of next-session open → close returns (raw, and against
  XIU) for |move_atr| ≥ 1 against < 1, with the share of sessions moving more
  than 3% either way.
* **The mean:** the open → close return signed by the prior move
  (continuation positive), movers only, with a date-clustered t. Day-132 says
  it is near zero; it must not show |t| ≥ 2 here either, or R2 is changing a
  bet, not a size.
* **PASS:** the movers' raw sd is at least 15% larger than the non-movers'
  (so skipping them cuts a pick's swing by ≥ 13%), and the signed mean shows
  |t| < 2.

## Also reported (no verdict)

* **How often each rule would have changed the live Top 2:** the sessions
  since 2026-10-05 in `data/model_picks.csv` (`top2/pick`), with each pick's
  move_atr from the same bars.
* **The noon exit** (day-130 H3, passed: no worse, 15% less swing), on
  10-15: CLS −0.79% at noon against −3.61% at the close; CCO −3.64% against
  −4.17%.

## What a result changes

Nothing switches on by itself. A PASS goes to the owner as a switch:
* **R1:** the Top 2 holds at most one position per side; a second same-side
  position is shown as a labelled runner-up, never a pick.
* **R2:** a position on a ≥ 1 ATR mover is passed over for the Top 2, and
  shown as such.

The record splits at the rule version the day a switch is turned on. Neither
rule is claimed to make a pick right.

Script: `risk_rules.py`. Summary: `data/risk_day135c.json`.

---

## Results (added after the run; the text above is unchanged)

Read `AUDIT_day135c_risk.md`. 150 names, 2,706 sessions, 389,034 name-days;
no fetch failed.
* **R1: FAIL (rejection #51).**
  * The same-side book swings 1.13× the long/short book (sd 3.31% against
    2.94%), below the 1.15 bar.
  * ρ is 0.12, and 0.25 when XIU moves 1% or more.
* **R2: PASS.**
  * After a move of ≥ 1 ATR the next session's sd is 2.67%, against 2.15%
    (1.24×, n = 49,295).
  * The signed mean is −0.005% (t = −0.24).
  * A planted 0.10% would show at t = 4.48 (reported after the verdict).

As registered, nothing switched on. R2 ships as the owner's switch
(`council.SKIP_MOVERS`, off). A caution line naming a pick on a big mover is
always printed; it is display only.
