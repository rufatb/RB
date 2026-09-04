# Decision record — day-87, the two standing contradictions

The portfolio manager delegated both. Written BEFORE either change is applied,
because a constant that moves without a recorded reason is the failure
`constants.py` exists to prevent.

Neither of these is settled by deciding which measurement is better. Both are
settled — or shown to be unsettleable — by **rule 7: a ratio needs both legs
from one population.**

---

## 1. TYPICAL_MOVE_PCT — RESOLVED, 0.97% -> 0.69%

### The two numbers

| | value | population |
|---|---|---|
| shipped, day-70 | **0.97%** | \|r1\| across the 21-name UNIVERSE, non-event sessions |
| re-derived, `validate_typicalmove.py` | **0.69%** [0.59, 0.80] | median \|capture\| over the 363 SCORED LEGS, 41 sessions, session-clustered |

The interval excludes 0.97% outright.

### Why this is a population question, not a measurement contest

Day-70's sample cannot be reconstructed, so "which study was better run" is
unanswerable and has been the reason this sat open. That question does not need
answering. The constant is a **denominator**, and its two use sites both fix
which population it must describe:

```
cost.share_of_move  =  spread(this pick) / TYPICAL_MOVE_PCT
cost.edge_bps       =  (p - 1/2) x 2 x E|move|
```

In the first, the numerator is the spread on **a pick the report is
recommending**. In the second, `p` is the **picks' hit rate** — the ledger's
own 49%. Both numerators come from the population of picks. A denominator drawn
from all universe prints is therefore the wrong leg of both ratios: it includes
names the engine never selected, and selection is not random with respect to
volatility (day-47 established that the density tag sorts by volatility, so
picks are drawn non-uniformly from the universe's volatility distribution).

**The ledger legs are the population the report describes. The denominator must
come from there.** That is rule 7 applied directly, and it does not require
day-70 to have been wrong about its own universe.

### Direction, stated plainly

This correction is **against us**. Too large a denominator makes the spread look
like a smaller share of a normal day's move than it is, so every cost line the
report has printed has **understated the drag**. Concretely: a 5bp spread read
as 5.2% of a typical move; it is really 7.2%.

### What changes

`cost.TYPICAL_MOVE_PCT = 0.69`, with `constants.py` re-pointed at the script
that derives it and the day-87 provenance. `validate_typicalmove.py` is NOT
edited — changing a constant inside the script that checks it defeats the
check, and a test enforces that.

The tension check is left armed. It should now fall silent because 0.69 sits
inside its own interval, and it must fire again if the ledger drifts away from
it. Silence earned by agreement, not by deleting the check.

### What this does NOT license

The re-derivation stands on **363 legs over 41 sessions**. It is the right
population, not a large one. It will move as the ledger grows, and the tension
check is what will say so.

---

## 2. P(rejection) — REMAINS OPEN, and the blocker is confirmed still standing

### Checked before concluding

Day-82 named the unblocker: "a ground-truth set of DECISIONS including
rejections. FDA did not publish complete response letters historically." FDA
has since moved toward publishing CRLs, so that was worth re-testing rather
than inheriting.

**It is not available.** `fda.gov/about-fda/transparency-initiatives/complete-response-letters`
returns **HTTP 404**; openFDA's `drugsfda` endpoint responds but carries
approvals only. One reachable endpoint, one dead one, both recorded rather than
routed around.

### The decision

**No change.** The two numbers describe genuinely different populations:

- **cited 30%** — first-cycle NME review, from FDA data. Anchors the guardrails
  in `catalyst.assess`.
- **measured 11.7%** [8.5, 15.9] — 291 single-asset decisions from one harvest,
  one classifier, one window. Divides every breakeven in the screen.

Both remain correct for their own use and neither may be substituted for the
other. The measured leg is biased **DOWN** for two named reasons — companies
announce approvals more readily than rejections, and this harvest includes
supplements which approve at higher rates — so a reader who takes 11.7% as the
probability for a specific PDUFA date is being optimistic.

Picking one now would mean either dropping a figure that has a published
interval and a positive control, or dropping one that covers the population the
guardrails actually anchor on. Neither is defensible, and rule 8 already
requires the report to print UNCONDITIONAL beside a population rate.

**The report keeps printing both and keeps saying they must never be mixed.**
That is the honest state, and it stays until a ground-truth decision set exists.
This is not a deferral for lack of effort; it is the third time the blocker has
been probed directly.
