# Day-98 — why the losing days keep happening

Written after 2026-09-11, the second session in three where the long side lost
on a flat tape. Diagnostic only. **Nothing here is adopted, and one plausible
explanation is refuted below rather than acted on.**

## What actually happened on 2026-09-11

Measured 09:46 → close, tide removed using XIU.TO:

| leg | side | raw | tide | selection |
|---|---|---:|---:|---:|
| TRP.TO | LONG | −1.45% | −0.13% | **−1.32%** |
| ENB.TO | LONG | −1.24% | −0.13% | **−1.11%** |
| NTR.TO | SHORT | +0.74% | +0.13% | +0.61% |
| T.TO | SHORT | +0.94% | +0.13% | +0.81% |
| **book** | | **−0.25%** | 0.00% | **−0.25%** |

**This was not a tape event.** XIU moved −0.13%, the universe median −0.15%,
and 12 of 21 names fell — an ordinary session. The book is two long and two
short, so the tide cancels and essentially all of −0.25%/leg is selection.

Same shape as 2026-09-09: tide +0.065%, mean −0.190%/leg. Twice now.

## The explanation that FAILED — sector concentration

TRP and ENB are both in `peer_groups.energy`, and the engine picked them as the
two longs on 09-09 *and* 09-11. A tempting story: the book held one bet twice.

The record does not support it.

| side composition | scored legs | hit rate |
|---|---:|---:|
| two legs sharing a peer group | 26 | **57.7%** |
| diversified across groups | 81 | 45.7% |

Concentrated sides did **better**, and at n=26 the 12pp gap is ~1.2 SE — noise.
This is also already-settled ground: day-34 tested forcing the two legs of a
side apart (**rejection #23**) and it bought nothing — NET std 0.517 → 0.517,
the mean got worse, 2 of 4 quarters improved.

`r945.book_concentration` should keep *disclosing* concentration, because the
reader deserves to know two legs are one bet. It must not become a gate.

## Where the money actually goes

| | n | hit rate | mean/leg | mean win | mean loss |
|---|---:|---:|---:|---:|---:|
| LONG | 49 | 42.9% | **−0.174%** | +0.814% | −0.915% |
| SHORT | 58 | 53.4% | +0.041% | +0.809% | −0.840% |
| all | 107 | 48.6% | −0.058% | +0.811% | −0.878% |

Two separate facts, and they are usually confused:

**1. Magnitude, not direction.** Win/loss ratio is **0.92**. At a 48.6% hit
rate the ratio required merely to break even is **1.06**. A system that called
direction perfectly 50% of the time would still bleed at this ratio. Hit rate
is the headline metric in the ledger and it is not the metric that is losing.

**2. The long side, with its own base rate applied** (rejection #16's required
control — if the tape drifts, one side wins with no skill involved):

| side | n | hit | naive base | skill | |
|---|---:|---:|---:|---:|---|
| LONG | 49 | 42.9% | 53.0% | **−10.1pp** | −1.42 SE |
| SHORT | 58 | 53.4% | 47.0% | +6.4pp | +0.98 SE |

The tape drifted UP on these sessions (53.0% of names rose), so the long
weakness is not a drift artifact — the control makes it look worse, not better.

**But neither is significant, and this claim has already been refused once.**
Rejection #16 tested "one side is structurally broken", found the deep set and
the true 5-minute set said OPPOSITE things, and noted the true-horizon data
would have had us cut the LONGS. It failed the four-quarter bar.

## The structural problem, stated plainly

To resolve a 10pp side effect at the repo's own |t| ≥ 3 bar requires
SE ≤ 3.3pp, i.e. **≈230 legs per side**. There are 49 long legs. At ~1.2 long
legs per session that is **~190 more sessions, roughly nine months**.

So: iterating on the directional signal cannot be validated at this sample
size. Any change adopted on 49 legs is adopted on noise, which is how a
repository accumulates 41 rejections.

## What follows

Three honest options, and no fourth:

1. **Do not trade the directional board.** It has no demonstrated edge — day-43
   reached AUC 0.5022 on 122,234 out-of-sample rows, the live record is 48.6%
   on 107 legs, and the report already prints "No demonstrated predictive edge"
   above every pick.
2. **Attack magnitude, not direction.** The win/loss ratio of 0.92 is the
   arithmetic that loses money, and it does not require predictive skill to
   change. Day-90 H3 (fixed earlier exits) is the registered shadow for this.
   NOTE: rejection #24 already found no exit beat the close on the data then
   available, and a stop cannot be tested honestly without intraday paths —
   free 5-minute history caps at ~41 sessions (day-93).
3. **Pre-register the long-side question and let it accrue**, with the MDE
   stated up front so there is a date on which it becomes answerable rather
   than an open invitation to re-litigate every bad day.

What must NOT happen is a change adopted because two sessions felt bad. That
is precisely the mechanism this file exists to interrupt.
