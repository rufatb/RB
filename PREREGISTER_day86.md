# Pre-registration — day-86, an OUT-OF-SAMPLE test of H5

Committed BEFORE any new outcome is computed. The bar is inherited from
`PREREGISTER_day85.md` unchanged: **|t| >= 3 on the market-relative statistic
AND the same sign in all four contiguous blocks**, block-bootstrapped at
block = horizon, outside placebo, and — because H5's profitable orientation
buys losers — clearing day-32's three dissolving tests.

## Why this needs its own registration

Day-85 left H5 (52-week-high proximity) at **|t| = 2.46** on 2,313 sessions,
needing roughly 3,449. The obvious response is "add more names". Done naively
that is **not a confirmation**: the original 578 names would sit inside the
wider universe, so re-running would re-read the draw that produced the
hypothesis and report a tighter interval around the same numbers. Day-52
handled exactly this correctly — a TSX-generated hypothesis was taken to 500
S&P 500 names so it could be *confirmed* rather than re-read — and that is the
shape used here.

**The test is therefore on names the day-85 study never saw.** The original 578
are held out of the replication set entirely. Pooled figures may be reported as
a secondary line and are not what decides.

## The one thing that would make this look better for the wrong reason

Survivorship gets **worse** as the universe widens, because smaller names
delist more often and the delisted ones are absent. H5's profitable direction
is long the most beaten-down decile — precisely where those missing names would
have been. Day-85's own size test already shows the effect concentrating in
small caps: at 20 sessions it ran **−1.863 / −1.235 / −1.056 / −0.475** across
liquidity quartiles, more than 3.9x larger in the smallest than the largest.

**Registered in advance:** if the effect GROWS as the universe extends into
smaller names, that is the survivorship signature and is to be read as evidence
against H5, not for it. The replication set is therefore reported **split by
liquidity quartile as well as pooled**, and a result that lives only in the
small quartiles does not clear regardless of its `|t|`.

## Sample

Names ranked 601 and beyond in SEC's `company_tickers.json` ordering, subject
to the same day-85 filters: at least 500 sessions of history and a passing
daily-granularity assertion (rule 9). Target roughly 1,400 additional names.
The count that survives those filters is reported, not assumed.

## Hypotheses

**H5a — replication.** 52-week-high proximity, deciles, long top / short
bottom, holds of 5 and 20 sessions, market-relative, on the held-out names
only. The sign is PRE-COMMITTED to day-85's: **negative** (near-highs
underperform). A significant result with the OPPOSITE sign is a failed
replication, not a discovery, and is written up as such.

**H5b — the liquidity gradient.** The same effect by liquidity quartile on the
held-out names. Registered prediction above.

## Forbidden

Reporting the pooled figure as the headline. Treating a small-cap-only effect
as a pass. Re-deriving the decile cuts. Dropping H5b if it is unflattering.
Quoting any of this at the live TSX book.

## Expected outcome, recorded in advance

The point estimate replicates in sign — that much I expect, since the effect
was consistent across four blocks and both horizons. What I expect to decide it
is H5b: I expect the effect to be materially larger in the small-cap quartiles
of the held-out set, which under the rule above counts **against** H5. I do not
expect a clean pass.
