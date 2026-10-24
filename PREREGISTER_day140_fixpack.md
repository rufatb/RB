# Day-140 — the fix pack, in shadow (DRAFT)

**Status: draft, prepared 2026-10-24 at the owner's request after the
day-138/139 review (GitHub issue #18). This becomes the registration when
the owner commits it before the first shadow session. Until then nothing
here runs, and nothing here changes a live pick, a size, the Top 2 or the
email.**

## Why

The full-history audit (owner's, Sep 8 – Oct 23) and the day-137 council
audit agree on where the accuracy goes:

* the council's candidate table itself averaged −0.31% a position, and its
  picks −0.30% — selection adds nothing over its own table;
* 85% of picks followed the name's last move and its move against its
  sector, after the open had priced it; unanimous positions were the worst
  group (−1.09%);
* on the picks, the sector fund's component averaged −0.54% against
  −0.15% for the stock's own component — the Top 2 is mostly an unlabelled
  sector bet;
* slots are filled because the format demands two, including positions
  with no dated catalyst and no stated wrong-if (2026-10-21, SHORT CLS.TO).

Three changes follow, each aimed at one of those leaks. All three run in
**shadow**: they produce a parallel record and parallel picks that are
scored exactly like the live ones and never shown to a model, never sized
and never in the email.

## What runs (shadow only)

1. **Abstention is a first-class outcome.** A candidate may enter the
   shadow Top 2 only if its proposal carries (a) a dated, stock-specific
   catalyst and (b) a machine-checkable wrong-if (a price level or a named
   event outcome). A candidate with neither is recorded as an abstention,
   with the reason. The shadow Top 2 may therefore hold 0, 1 or 2
   positions where the live Top 2 holds 2.
2. **Round-1 ballots are frozen and scored separately.** Each desk's
   independent first-round ballot (before any discussion) is written to
   the ledger before the council convenes and scored on the same window
   and yardstick as the final Top 2. The deliberation delta — final minus
   Round-1-majority picks, per session — is printed in the evening review.
3. **Sector-neutral ranking.** Shadow candidates are ranked by the stock's
   expected residual against its sector ETF (the decomposition already
   computed in `council_audit.py`), and the shadow Top 2 holds at most one
   position per sector per side per session.

## The measure

* **y** for every pick, live and shadow: side × (stock − XIU), entry on the
  same basis the live board already uses, open → close, minus the 0.13%
  round trip (plus borrow on shorts where the live board charges it).
  One basis, one ledger, for every arm in this test.
* **Primary comparison:** per-session mean y of the shadow Top 2 minus the
  live Top 2, paired by session (sessions where the shadow abstains on
  both slots count as y = 0 for the shadow — standing aside is a result,
  not a missing row).
* **Descriptive only:** Round-1 vs final per-desk records; a monthly
  calibration table (desk × confidence bucket × material flag); the
  abstention rate and the live picks the shadow rules would have refused,
  with their outcomes.

## The bar

* **Decision at 40 sessions** with at least one live Top 2 pick.
* **ADOPT (each change judged on its own paired record, then proposed to
  the owner as a live rule change under a new registration) needs all of:**
  * shadow mean y > 0 net of costs;
  * paired shadow-minus-live difference > 0 with paired t ≥ 2.0;
  * the same sign in both halves of the sessions.
* **Otherwise the change is retired as a rejection** and the shadow arm
  stops. No threshold, filter or weight is tuned mid-test; a change that
  misses is not re-cut on the same sessions.
* **Desk weighting is explicitly out of scope here.** Round-1 scoring
  exists to test whether deliberation helps; any weighting of desks by
  trailing scored expectancy is a separate registration that names its
  window and weights in advance.

## What follows

* Any change that clears the bar is proposed to the owner, with its paired
  record, and goes live only under its own registration.
* The live council, its prompts and its rules are untouched by this test,
  whatever the shadow shows.
