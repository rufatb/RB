# ACCURACY — the definitions, fixed before anything is optimised against them

Written on day-82 under §3 of the master instruction. **These definitions do
not change once a study has been run against them.** Changing a definition
after seeing a result is the same offence as moving a pre-registered bar, and
it is harder to notice.

---

## 1. Intraday hit

A leg is **entered at the 9:46 print** (`p945`, the price the board publishes)
and **marked at the 15:59 close** of the same session. It is a HIT when the
close is on the side the call named:

    LONG   hit  ⇔  close > p945
    SHORT  hit  ⇔  close < p945

Two hit rates are reported, always both, never one alone:

- **all legs** — a pure sign test. A leg finishing +0.015% counts exactly as
  much as one finishing +1.5%.
- **decisive legs** — legs whose absolute capture clears
  `ledger.DECISIVE_PCT`. Scratches are excluded and counted.

**A scratch is excluded, not counted as a miss.** Day-35 measured 11% of pair
legs finishing inside the threshold, with 4 of 5 landing on the winning side of
zero — inflating the headline by about 3pp. Excluding them is deliberately the
*less* flattering treatment: it removes an artefact rather than adding one.
Scoring a scratch as a miss would be a different and equally defensible choice,
and it is not the one this repo made; what matters is that the choice is fixed
and the count is printed.

`DECISIVE_PCT = 0.10` is a **DESIGN** constant, not a measurement. It is
registered in `constants.py` so it cannot drift silently.

## 2. Accuracy net of cost

A hit rate is not a P&L claim. Every accuracy figure is reported alongside:

- **mean capture per leg** — `r1` signed by side, in percent
- **mean capture net of the round-trip spread**

Net capture uses the spread **stored on the leg at publish time**
(`ledger.spread_bps`, added day-82). Where a historical row predates that
column, the net figure for that row is **not computed and the row is counted as
unpriced**, and the reported net is labelled with how many rows it covers.

**It is never back-filled from today's spread.** The spread on the day a leg
was published is not recoverable later, and substituting a current quote would
print a number about one day using data from another — the same fault as the
board that re-picked its own names on a re-read.

## 3. Tide-adjusted

Direction accuracy must be separated from market exposure. A long-biased book
on an up day is exposed, not accurate. Reported as the existing decomposition:

- **TIDE** — the return attributable to net market exposure, target ≈ 0
- **SELECTION** — the return attributable to the picks

These sum to the book-weighted return. A change that improves the headline hit
rate while moving TIDE has not improved selection.

## 4. Pharma / catalyst

A catalyst expression **resolves at the FDA decision**, not at a fixed horizon.
Accuracy is scored by `catledger.py` against the outcome that `resolved.py`
reads from the 8-K — **never against the tape**. A price that moved the right
way before a decision that has not yet landed is not a resolved call.

Outcomes: APPROVED / REJECTED / UNCLEAR / NO FILING / PENDING / UNKNOWN. Only
the first two are scoreable; the rest are reported as unresolved and never
folded into a rate.

## 5. Weekly

Not yet built. When it is: entry, exit and horizon are declared **before** any
test, and it is scored on the same clustered, cost-aware basis as the intraday
book, against a **matched random holding of the same length in the same names**.
A weekly strategy that merely captures drift is drift, not skill.

---

## What "improved accuracy" is allowed to mean

Only one of these, stated explicitly, with its pre-registered bar:

1. a higher **decisive** hit rate on the same population, or
2. the same hit rate with a higher **mean net capture**, or
3. the same hit rate and net capture with **lower variance** — the family that
   produced all three adopted changes to date.

Not permitted as evidence: a higher hit rate on a subset chosen after the fact,
an improvement that moves TIDE rather than SELECTION, or any figure gross of
the spread when a net figure is computable.
