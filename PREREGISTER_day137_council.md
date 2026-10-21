# Day-137 — what the council's agreement selects, and three rules that could follow (owner, 2026-10-21)

Registered BEFORE any history below was fetched or computed. The live audit
in "Why" was computed first and is disclosed; it chose the questions, and
its sessions are kept out of the tests.

## Why

The owner, after the 10-21 Top 2 (SHORT CLS.TO) lost 0.70%: "the council is
not selecting the best picks — identify what it is and try implementing the
enhancements to council picks."

`council_audit.py` (descriptive) scored every position on the twelve frozen
council tables, 2026-10-05 → 10-21: 108 positions, from 09:45 to the close.
* **The council's choice adds nothing over its own table.** Its 20 picks
  (before the big-mover rule) averaged −0.30%, 8 of 20 right; the whole
  table −0.31%, 46 of 108.
* **Agreement selects the most obvious continuation story.**
  * The picks followed the name's last-session move 85% of the time (the
    table 75%), its move against its sector 85% (72%), and a move of at
    least 1 ATR 70% (32%).
  * The more the members agreed, the worse the outcome: positions endorsed by
    every member −1.09% (6 of 17 right), positions with at least one
    objection +0.17% (26 of 51).
* **The sector decides most results.** On the picks, the sector fund's part
  of the move averaged −0.54% and the stock's own part −0.15%.

Twelve sessions resolve nothing. Two of those habits have a testable
history:
* following a name's move against its sector;
* following a sector's move against the market.

A third trait, the name's own volatility, sets the size of every miss. The
10-15 and 10-21 CLS picks moved 6.8% and 7.3% on a normal day.

**Already answered, not re-tested.** Following the name's own move (raw or
against XIU) after 09:45 is null at every size. Day-132 (#47) found:
* ≥ 1 ATR: −0.013%, t = −0.44;
* below 1 ATR: +0.0002%, t = 0.02;
* against XIU: −0.025%, t = −0.77.

## Data

* **Names:** the 150 names of the 10-21 list (`factor_pool_history/2026-10-21`).
  XIU.TO is the market.
* **Sectors:** the `sector` labels of `data/tsx_sectors.json`, the ones that
  build `rel_sector_pct` for the models. A sector needs ≥ 3 members with
  data that session, as `prepare_factor_pool.MIN_SECTOR_MEMBERS`.
* **Primary bars:** FMP 15-minute bars, 2024-01-02 → 2026-10-02.
  * Entry is the 09:30 bar's close (09:45); exit is the 15:45 bar's close
    (16:00), as day-132.
  * The live audit's sessions (from 10-05) are excluded.
* **Prior-session moves:** FMP daily bars. Move % = close D−1 / close D−2 − 1.
  ATR14 is as `daily_technicals`.
* **Secondary, ten years:** the day-135b cache of FMP dividend-adjusted daily
  bars, 2016-01-04 → 2026-10-02. The yardstick there is open → close; daily
  bars cannot see 09:45. Reported beside each primary result, never in place
  of it.
* **Exclusions:** a name-day without both bars, or with fewer than 16 prior
  sessions, is excluded and counted.

## H1 — following the move against the sector (the council's main habit)

* **Signal:** rel = the name's last-session move % minus the median
  last-session move % of its sector, the name included. This is
  `prepare_factor_pool.sector_context`'s `rel_sector_pct`.
* **Population:** name-days with |rel| ≥ 1.0%. CLS on 10-21 was −3.03%.
* **The position follows:** side = sign(rel).
* **Outcome (primary):** the stock's own part. sign(rel) × (the name's
  09:45 → close return − its sector's median 09:45 → close return), in %.
* **Also reported:** the raw outcome signed the same way, and against XIU.

## H2 — following the sector's move against the market

* **Signal:** S = the sector's median last-session move % minus XIU's
  last-session move %.
* **Population:** sector-sessions with |S| ≥ 0.5%.
* **Outcome:** sign(S) × (the sector's median 09:45 → close − XIU's
  09:45 → close), in %.

## Statistics and bars, H1 and H2

* **t:** clustered by session.
* **Blocks:** four equal time blocks.
* **Placebo:** each observation's sign is replaced by the sign of the same
  name's (H1) or sector's (H2) signal on a random other session, at least 5
  sessions away. 2,000 draws, seed 137; two-sided p.
* **Control:** a planted 0.10% must show at t ≥ 3, or the verdict is
  UNDERPOWERED.
* **Verdicts:**
  * **REVERSAL:** mean < 0, t ≤ −3, all four blocks negative, placebo
    p < 0.05.
  * **CONTINUATION:** mean > 0, t ≥ 3, all four blocks positive, placebo
    p < 0.05.
  * **NULL:** neither, with the control passing.

## H3 — wild names (size, not direction)

* **Wild:** ATR14 as % of the prior close at or above the 90th percentile of
  the 150 names that session. That is the 15 widest-swinging names of the
  morning.
* **(a) Swing:** the sd of the raw 09:45 → close return of wild name-days is
  at least 1.15× the rest. 1.15 is the house's variance bar (day-120b,
  day-130 H8, day-135c R2).
* **(b) No lean.** On wild name-days, both of these show |t| < 2 (clustered
  by session):
  * the position that follows the last-session move, against XIU;
  * the LONG position, against XIU.

  Otherwise removing them changes a bet, not a size.
* **PASS:** (a) and (b).

## What a result changes

The owner asked on 10-21 for the enhancements to be implemented, so a
passing rule ships ON. Every rule follows the day-135d pattern:
* **Remove-only.** The Top 2 is the council's own picks minus the positions
  the rule names. Nothing is added; an emptied slot stays empty.
* **Never the runner-up.** A named position cannot stand as runner-up
  either.
* **Shown and recorded.** The passed-over positions print as passed over and
  are recorded as their own shadow, out of the pooled row.
* **Labelled.** The record splits at a new rule_version.
* **Reversible.** `False` restores today's rule.

| Result | What ships |
|---|---|
| H1 REVERSAL | `SKIP_RELATIVE`: pass over a position that follows its name's last-session move against the sector by ≥ 1% |
| H2 REVERSAL | `SKIP_SECTOR_CHASE`: pass over a position that follows its sector's last-session move against XIU by ≥ 0.5% |
| H3 PASS | `SKIP_WILD`: pass over a position on one of the morning's 15 widest-swinging names; the morning's threshold is recorded in `council.json` |
| CONTINUATION, NULL, FAIL | nothing switches; reported |

A CONTINUATION would mean the council's habit is right on history. It
adds no rule: the rule never adds a trade.

None of these is claimed to make a pick right. H3 is a size rule by
construction.

## Forward measurement, M1 (no switch)

The question the owner asked: is the council choosing better than its own
table?
* **What the evening review prints, every session:**
  * the council's picks, before any rule, against every position on that
    morning's table, both from 09:45 to the close;
  * the cumulative per-session difference, clustered;
  * the same split for positions every member endorsed against the rest.
* **At 40 council sessions:**
  * t ≤ −2 → the owner is told the council chooses worse than a random draw
    from its own table;
  * t ≥ 3 → the choice adds something;
  * otherwise, no evidence either way.

## Scripts

* `council_audit.py` (live, descriptive) → `data/council_audit_day137.json`
* `council_history.py` (H1–H3) → `data/council_history_day137.json`

---

## Results (added after the run; the text above is unchanged)

Read `AUDIT_day137_council.md`. The primary data were 150 names, 667
sessions and 98,597 name-days. No call failed and none was capped. The
secondary had 2,699 sessions and 390,343 name-days.

* **H1, following the move against the sector: NULL (rejection #53).**
  * −0.044% a name-day, t = −2.75, 46.8% right (n = 38,438).
  * The blocks were +0.017 / −0.138 / −0.036 / −0.022.
  * Placebo p = 0.000; a planted 0.10% shows at t = 6.21.
  * The mean leans toward reversal, but t is above −3 and the first block is
    positive, so it misses the registered bar. The bar does not move.
  * Ten years of daily data say the same: −0.016%, t = −1.61.
* **H2, following the sector against the market: NULL (rejection #54).**
  * −0.007%, t = −0.44 (n = 3,519); a planted 0.10% shows at t = 6.13.
  * Ten years: −0.0003%, t = −0.03.
* **H3, wild names: PASS (adoption #5, a size rule).**
  * Wild name-days swing 2.46× the rest: sd 3.79% against 1.54%.
  * 26.5% of them move more than 3% after 09:45, against 5.5%.
  * Leans: following the last move −0.023% (t = −0.47); long +0.073%
    (t = 1.15).
  * The morning's cut has a median of 4.59% ATR (p10 3.89%, p90 6.34%).
  * Ten years, open → close: 2.16×. Following the last move on wild names
    leans negative there (−0.071%, t = −2.53). That is reported beside the
    verdict and does not decide it.

**What ships:** `council.SKIP_WILD`, ON from the 2026-10-22 morning. Nothing
for H1 or H2.

**On the live Top 2** (descriptive), the rule would have passed over three
picks:
* SSRM.TO on 10-14 (+1.20%);
* CLS.TO on 10-15 (−3.61%, already a big mover);
* CLS.TO on 10-21 (−0.70%).
