# Pre-registration — day-84, short interest as a selection input

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

Feed availability and the FEATURE's own distribution were inspected before
writing this (they are what decide whether a runnable study exists). **No
return, capture, hit rate or ledger outcome has been looked at through this
lens.** The line between those two is the line this document is written on.

## Disclosures that weaken this study, stated first

**1. It is the wrong listing line.** The book trades `.TO`. FINRA measures the
**US** line of each dual-listed name. Short interest on the NYSE line of RY is
not short interest on the TSX line of RY.TO — the position is split across two
lines and only one of them is visible here. Everything below is therefore a
**proxy** for the quantity that would actually matter, and must be described
that way in any write-up, adopted or not.

**2. The cadence is almost certainly fatal, and this is the main objection.**
The feature updates on ~24 settlement dates a year. The trade is one session,
9:46 to the close. A number that moves twice a month is very nearly a constant
over the horizon it is being asked to inform. If this study fails, this is the
reason it will fail, and stating it now means the failure cannot later be
dressed up as a surprise.

**3. Publication lag is a look-ahead trap of the day-72 class.** The settlement
date is not the publication date; FINRA posts roughly eight business days
after settlement. A session may only use a report **already public on that
session's date**. Using the settlement date as if it were the availability date
would manufacture an edge out of nothing, and it would look real.

**4. One name has no data at all.** AC.TO has no US listing. Per rule 2 it is
carried as **UNKNOWN and excluded from the sorted set** — never as zero. Zero
short interest is a claim; absent data is not.

**5. The Canadian source — the correct one — could not be fetched.** CIRO's
Consolidated Short Position Report covers the `.TO` line itself and would not
need disclosure 1. Both the report index and a direct media URL returned
**HTTP 403** on 2026-09-04. That is recorded as two failed requests, not
silently routed around (rule 1). If CIRO becomes reachable, this study should
be re-run on it and the FINRA version treated as the proxy it is.

**6. The prior is bad.** Thirty-seven rejections stand against three adoptions,
and all three adoptions were variance results. Nothing here earns an exemption.

## What was checked before the bar was set, and what it changed

Feed, on 2026-08-14's file: free, unauthenticated, **22,482 US symbols**, with
`currentShortPositionQuantity`, `previousShortPositionQuantity`,
`averageDailyVolumeQuantity`, `daysToCoverQuantity`, `changePercent` and
`settlementDate`. History reaches at least 2020-04-15 via the API endpoint.
Universe coverage **20 of 21**.

**I expected the feature to be flat across this universe and it is not.**
Days-to-cover on 2026-08-14 spans **1.12 (SHOP) to 17.29 (CM)** — roughly
fifteen-fold. The a-priori objection I had raised myself, that large-cap
Canadian names carry no meaningful short positioning and so offer no sort to
make, is refuted by the data before any outcome was involved. That is the only
reason this study is being written rather than declined.

Note that days-to-cover here is short position over the **US line's** average
volume. Both legs of that ratio come from the same population and the same
file, which is what rule 7 requires; it is internally consistent, and it is
still the US line.

## The feasibility gate — pre-registered, and it looks only at the feature

Run **before** any outcome is touched. If it fails, the study is written up as
NOT RUN and no return data is inspected.

**Rank persistence.** Compute the Spearman rank correlation of days-to-cover
across consecutive settlement reports for the 20 covered names.

- If **rho >= 0.90**, the sort is effectively a permanent name label. Any
  apparent effect would then be a name fixed effect — "banks behave differently
  from miners" — wearing a short-interest costume. In that case the study
  proceeds **only** in name-demeaned form (each name against its own trailing
  median), and the raw-level version is abandoned unrun.
- If **rho < 0.90**, both the level and the demeaned form are admissible.

This is pre-registered because it is exactly the failure that produced
rejection #23's cousin: a cross-sectional sort that turns out to be sorting on
something structural rather than on the quantity named.

## Hypotheses

Tested separately. The long and short legs are **never pooled**: the proposed
mechanism is asymmetric — a crowded short can squeeze, a crowded long has no
symmetric counterpart — so averaging them would hide whichever one exists.

**H1 — level.** Does days-to-cover separate per-leg tide-relative capture
cross-sectionally? Top tercile versus bottom tercile, cut at the **tercile
boundaries of the session's own cross-section**, fixed here.

**H2 — the usable form.** Does excluding the highest days-to-cover name from
the **short** side improve the book? This is the only form that is directly
expressible as a morning rule, and it is an exclusion, not a prediction.

**H3 — flow rather than level.** Does the **change** in short position between
consecutive reports carry what the level does not? This is the one hypothesis
whose cadence objection is weaker: a change is news on a known date, whereas a
level is a standing fact. If anything survives, the prior says it is this.

## Statistics and bars

- **Decisive statistic: tide-relative capture per leg.** Not raw capture. The
  standing live figure is −0.081%/leg over 95 legs; day-38 and day-51 both
  found an apparent gain that was market drift, and this study is built to fail
  the same way if it is going to. Hit rate is reported beside it but does not
  decide — a hit rate can improve while capture falls.
- **Bar: |t| >= 3 on tide-relative capture AND the same sign in all four
  quarters.** Both, not either. This is the standing protocol from day-22
  onward and it is not relaxed for a study I proposed.
- **Clustering: bootstrap by SESSION.** Legs within one session share that
  day's move and are not independent observations.
- **Placebo, mandatory.** Random exclusion of the same number of legs, and a
  random re-assignment of days-to-cover ranks across names. If the placebo
  reproduces a material share of the effect, the effect is the exclusion
  arithmetic and not the feature. Day-51's "oracle gap" of +2.34%/trade was
  smaller than what pure noise produced (+2.85%); that is the standard being
  applied here.
- **Positive control, mandatory.** Plant a known edge of a stated size and
  confirm the harness registers it, computed as `edge / sd` and never as
  `(mean + edge) / sd`.
- **MDE always reported.** An observed effect smaller than `bar x SE` is
  **UNDERPOWERED**, not refuted (rule 10). Given ~24 feature updates a year,
  UNDERPOWERED is the single most likely verdict and saying so now is part of
  the registration.
- **Point-in-time, asserted by test.** A test must fail if any session uses a
  report whose publication date is after that session. This is not a review
  item; it is a test that ships with the harness.
- **Cost.** Any surviving effect is reported gross and net of the measured
  round-trip spread. An effect that exists only gross is not an effect a
  portfolio manager can have.

## What may be adopted

An **exclusion rule only** — a name the short side may not take — and only if
the tide-relative capture clears |t| >= 3 with consistent sign across four
quarters, survives both placebos, and stays positive net of spread.

If it clears on **variance** rather than capture, it is written up as a
variance result and labelled as one. That is the family all three adopted
changes came from, and it must not be presented to the portfolio manager as
improved accuracy. Anyone who reads a variance result as "better picks" has
misread it, and the write-up carries that sentence.

## Forbidden

Using any report before its publication date. Moving the tercile cuts after
seeing results. Pooling the long and short legs. Reporting raw capture without
its tide-relative twin. Treating AC.TO's absent data as zero. Widening the
universe to manufacture sample size — day-14 and rejection #30 both closed that
door. Reporting a null without its positive control. Dropping H3 if H1 and H2
fail, or dropping H1 and H2 if H3 succeeds — all three are registered and all
three get written up.

## Expected outcome, recorded in advance

UNDERPOWERED on H1 and H2, on the cadence argument in disclosure 2. H3 is the
only arm I would give better than negligible odds, and I would not put those
above one in five. Recording this now means a positive result has to survive
the fact that I did not expect it, and a negative one cannot be recast as
having been obvious all along.
