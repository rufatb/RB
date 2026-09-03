# Pre-registration — day-83b, post-announcement drift in SHARES

Committed BEFORE any result is computed. Bars fixed here and do not move.

## Why this, given the constraint

The portfolio manager trades **shares only, long or short, on a morning
recommendation, with a suggested hold duration.** That rules out the option
expression tested in PREREGISTER_day83.md, which is withdrawn unrun.

It also collides with day-51, which rejected exactly this shape (#32):
per-pick hold duration, 38,402 picks over 719 sessions. Tide-relative accuracy
was **flat at 49.6–50.0% across to-close, +1d, +2d, +3d and +5d**; the raw
hit-rate creep was entirely market drift; volatility went 4x and the worst
trade from −16% to −80%; nothing predicted which picks deserved a longer hold
(max |corr| = 0.026); and the apparent oracle prize of +2.34%/trade was
**smaller than pure noise produces (+2.85%)**.

Its closing sentence is what makes this study different:

> *Real event capture requires knowing WHEN events occur — earnings, guidance,
> news. This engine has no such feed. Without one, a longer hold is not event
> capture; it is a longer random exposure. A duration field cannot manufacture
> event awareness out of OHLCV bars.*

**The engine now has that feed.** `data/catalyst_events.csv` carries 1,097
dated FDA decisions with an announcement date and a known OUTCOME. So the two
things day-51 could not supply are both present:

- **the duration is a fact, not a prediction** — it runs from the announcement,
  not from a horizon someone has to guess
- **the direction is known at entry** — the 8-K states approval or rejection
  before the position is opened

This is therefore not "predict the binary". The binary has already resolved and
is public. The question is only whether the market finishes repricing it on the
day, which is the classic post-announcement drift question, and it is
expressible in shares with a defined hold.

## Disclosure that weakens this study, stated first

`validate_catalyst.window_returns` has computed an `after5` column since day-68
and prints a "post-event 5d drift" line. **The number has been computable, and
possibly seen, before this pre-registration was written.** It has never been
written up in STRATEGY.md and no result from it has ever been quoted, but this
is a re-analysis of an existing column rather than a virgin test, and it does
not carry the evidential weight of one. Any adoption on this basis is
provisional until confirmed on data collected after today.

## Sample, counted before any outcome was inspected

1,097 events; 727 with a resolvable ticker; **684 inside the 3,600-day window
that returns true daily bars** (day-72) — **618 approvals, 66 CRLs**, 195 names.

The CRL arm is small and that is stated now, not after seeing it.

## Hypotheses

**H1 — drift after a REJECTION.** Mean 5-session return following a CRL
announcement, entered at the close of the announcement window and held 5
sessions.

**H2 — drift after an APPROVAL.** The same, following an approval.

Each is tested SEPARATELY. They are different events and pooling them would
average a possible fall against a possible rise.

## Statistics and bars

- **Statistic.** Mean 5-session return, and the same measured **relative to the
  market** over the identical window. The relative figure is the one that
  decides: day-38 and day-51 both found that an apparent multi-day gain was
  market drift collected by a long-biased book, and this study is built to fail
  the same way if it is going to.
- **Bar.** The standing `|t| >= 3` on the MARKET-RELATIVE mean.
- **Clustering.** Bootstrap resampling **NAMES**, not events. 684 events come
  from 195 names and one biotech contributes many decisions.
- **Placebo.** The same holding period on **random dates in the same names**.
  If the placebo reproduces a material share of the effect it is a
  company-type or regime artefact, not an announcement effect.
- **Positive control.** Plant a known drift of a stated size and confirm the
  harness registers it, measured as `edge / sd`, never `(mean + edge) / sd`.
- **MDE reported always.** An observed effect smaller than `bar x SE` is
  **UNDERPOWERED**, not refuted (rule 10).
- **Granularity asserted.** Every price series must pass `is_daily`; rejects
  are counted and reported (day-72).

## Cost, which is not optional

Any adopted effect must survive the round-trip share spread. The measured
median for this book is used, and the verdict reports both gross and net. An
effect that only exists gross is not an effect a portfolio manager can have.

## What may be adopted

A recommendation with a stated hold duration **only** if the market-relative
mean clears |t| >= 3, survives the placebo, and remains positive net of the
round-trip spread. Otherwise this is written up as REJECTED or UNDERPOWERED and
the morning report continues to make no multi-day directional recommendation.

## Forbidden

Pooling the CRL and approval arms. Reporting a raw return without its
market-relative twin. Choosing the holding period after seeing the results —
5 sessions is fixed here because it is the column that already exists.
Adopting on the strength of a re-analysed column without prospective
confirmation.
