# Pre-registration — day-85, five US strategies at two horizons

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

Data availability and universe construction were inspected first, since they
decide whether runnable studies exist. **No return, capture, hit rate or drift
has been looked at through any of these five lenses.**

## What changed, and what it licenses

The portfolio manager has lifted the Canadian restriction. Two consequences,
both material:

**1. Rejection #33 no longer binds.** Day-52 rejected `scaled` even though it
cleared the bar on 500 US names in 4 of 4 quarters, because it was dead on the
TSX — "shipping a feature that measurably does nothing in the only market the
book touches." The book can now touch US names, so a US-only result is
adoptable on its own terms. That rejection is NOT being reversed here (it was
about a specific feature) but its governing objection is retired.

**2. The earnings blocker is gone.** `earnings.py` has carried this admission
since day-53: Yahoo returns fiscal quarter-END dates for TSX names, so "there
is no free source of historical announcement dates for TSX names, and therefore
no way to measure whether excluding these rows would have helped." For US
issuers the SEC publishes it directly. **8-K Item 2.02** is "Results of
Operations and Financial Condition" — the earnings announcement itself — and
`acceptanceDateTime` timestamps it to the minute, so before-open, in-session
and after-close are separable rather than lumped. This is authoritative,
free, point-in-time, and it is the feed day-43 named and never acquired.

## The bias that contaminates three of these five, stated first

The universe is **today's** ticker list. Names that fell and delisted are
ABSENT. `validate_events.py` already carries this and it cannot be removed
with free data — a point-in-time universe with dead tickers is a paid product.
The direction is what matters and it is not uniform:

- **Buying losers is contaminated FAVOURABLY.** H4 (weekly reversal) ranks into
  the loser decile, which is exactly where the missing delistings would have
  been. Day-32's single "finding" was a gap-DOWN bounce and this is why it was
  never trusted.
- **Buying winners is contaminated CONSERVATIVELY.** H5 (52-week-high
  momentum) and the positive arm of H2 lean the other way; survivorship works
  against them, so a positive result there is the more credible one.
- **H1 and H3 are roughly neutral**, being within-name decompositions rather
  than cross-sectional sorts.

Any H4 result MUST additionally clear day-32's three dissolving tests — median
and win rate as well as mean (not tail-carried), market-up versus market-down
days (not beta), and all four liquidity quartiles (size-robust). H4 is the one
hypothesis here that has a known route to a false positive, and it gets the
extra hurdle rather than the benefit of the doubt.

## The five hypotheses

Each is tested SEPARATELY and all five are written up whatever happens. No arm
may be dropped for failing and none may be promoted for succeeding.

**H1 — overnight versus intraday decomposition.** *Intraday.* Split each
name-day into overnight (prior close -> open) and intraday (open -> close),
both market-relative. Statistic: the difference in mean market-relative return
between the two windows, and each window's win rate. **Why it matters more than
it looks:** the engine trades 9:46 -> close, which is inside the intraday
window. If the intraday component is structurally flat while the overnight
component carries the drift, then the live 49% record is a property of the
window chosen, not of the picks — and that reframes every remaining question.
Cost note fixed in advance: an overnight expression pays the spread at the
close and again at the open, and day-24 measured that one night doubles
volatility with a 2.3x worse tail. Both are netted before any verdict.

**H2 — post-earnings-announcement drift.** *Weekly.* Entry at the first
tradable close after an Item 2.02 filing, signed by the announcement reaction
(a positive reaction is a long, a negative one a short). Hold 5 and 10
sessions, market-relative. The direction is known at entry and the duration is
a fact, which is the same standard that legitimised day-83b.

**H3 — earnings-gap continuation versus fade.** *Intraday.* On the session
following an Item 2.02 filing accepted after the prior close, measure
open -> close signed by the gap. This asks whether the engine's OWN window has
an edge on event days specifically — the case day-32 could not isolate because
it had no event feed and tested unconditional gaps.

**H4 — cross-sectional weekly reversal.** *Weekly.* Rank by prior-week
market-relative return; long the bottom decile, short the top; hold 5 sessions.
Carries the extra hurdle above.

**H5 — 52-week-high proximity momentum.** *Weekly.* Rank by price divided by
the trailing 252-day high; long the top decile, short the bottom; hold 5 and 20
sessions.

## Statistics and bars — identical for all five

- **Statistic: MARKET-RELATIVE return.** Day-18, day-38 and day-51 each found
  an apparent multi-day gain that was market drift. Every raw figure is printed
  beside its market-relative twin and the bar applies to the relative one.
- **Bar: |t| >= 3 AND the same sign in all four contiguous blocks.** Both, not
  either. Unchanged from day-22 onward.
- **Clustering.** Cross-sectional arms (H1, H4, H5) bootstrap by **DATE**,
  since every name shares that day's market move. Event arms (H2, H3) bootstrap
  by **NAME**, since one issuer contributes many announcements.
- **Placebo, mandatory.** For event arms, the same holding period on random
  dates in the same names. For sorted arms, the feature shuffled across names
  within each date. If the placebo reproduces the effect, the effect is the
  arithmetic.
- **Positive control, mandatory.** Plant a known edge of a stated size and
  confirm detection, computed as `edge / sd` and never `(mean + edge) / sd`.
- **MDE always reported.** An effect smaller than `bar x SE` is UNDERPOWERED,
  not refuted (rule 10).
- **Granularity asserted.** Every series must pass a daily-bar check and
  rejects are counted (day-72: Yahoo answers a daily request with weekly,
  monthly or quarterly bars and no error).
- **Cost.** A stated round-trip spread is subtracted and both gross and net are
  reported. H1's overnight arm additionally pays two crossings, not one.

## What may be adopted

A recommendation with a stated hold duration, on US names, for whichever arms
clear the bar. If none clears, the answer to "which is the highest-accuracy
strategy" is **none of them at this sample size**, stated plainly with each
arm's MDE so the reader knows what could still be hiding.

An arm that clears on VARIANCE rather than accuracy is written up as a variance
result and labelled as one. It is not an accuracy claim and must never be
presented to the portfolio manager as better picks.

## Forbidden

Dropping an arm that fails or promoting one that succeeds. Moving the decile or
tercile cuts after seeing results. Reporting a raw return without its
market-relative twin. Pooling the long and short sides of H4 or H5 without also
reporting them separately. Treating the H4 result as adoptable without the
three dissolving tests. Quoting any of this at the live TSX book, which is a
different market and is not what was measured.

## Expected outcome, recorded in advance

H1 confirms the documented overnight/intraday split and is the most likely of
the five to clear, but it is a DIAGNOSTIC before it is a strategy, and its
executable form is the one most likely to be eaten by two spread crossings and
gap risk. H2 is the most likely genuine strategy to survive, on the strength of
its published prior. H3 I expect to be underpowered. H4 I expect to look good
and then dissolve under the three tests, exactly as day-32 did. H5 I expect to
be weak but honest. If H4 is the only survivor I will treat that as evidence of
survivorship bias rather than as a finding.
