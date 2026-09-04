# Pre-registration — day-87, the overnight expression

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

## What day-85 established, and what it did not

H1 measured, on 1,387,399 ticker-days over 2,517 sessions:

| window | per session | annualised | win rate |
|---|---|---|---|
| overnight (close -> open) | +0.0487% | ~+12.3% | 57.2% |
| intraday (open -> close) | +0.0259% | ~+6.5% | 54.5% |

SPY alone shows the same shape (+9.4%/yr overnight against +4.8%/yr intraday),
so this is not an artefact of the equal-weighted cross-section.

**What day-85 did NOT establish** is that the difference is tradeable. The
difference arm flipped sign across blocks (+0.037 / +0.056 / −0.035 / +0.033)
and was underpowered, and no cost was applied. That is the whole question here.

## The honest reason this is worth one more study

It is the only survivor of eleven arms tested across days 84-86, and it is the
one result that speaks directly to the live book: **the engine trades
9:46 -> close, which is the flatter half of the day.** If an overnight
expression survives its costs, the answer to "how do we raise the hit rate" is
not a better selector but a different window. If it does not survive, that
conclusion is closed and the remaining candidates are all paid-data
acquisitions.

## What is being tested, precisely

**H1c — the executable overnight strategy.** Buy the equal-weighted basket at
the close, sell at the next open, every session. Measured NET of:

1. **Two spread crossings, not one.** Entering at the close and exiting at the
   open crosses the spread twice, and the closing and opening auctions are the
   two widest moments of the session. A single round trip is the MINIMUM and is
   reported as the optimistic bound.
2. **Day-24's measured overnight penalty**, which this repo established and
   which is not in day-85's figure: one night at ~2x volatility with a 2.3x
   worse tail.

**H1d — the intraday complement.** The same basket bought at the open and sold
at the close, on the identical sessions and the identical cost model, so the
two windows are compared on one population (rule 7) rather than one being
costed and the other not.

## Statistics and bars

- **Statistic.** Mean per-session return of the basket, net of cost, and the
  win rate beside it.
- **Bar.** `|t| >= 3` on the NET mean AND the same sign in all four contiguous
  blocks. Both. Day-85's gross difference already failed the consistency half,
  so this arm starts behind and is expected to stay there.
- **Clustering.** Bootstrap by SESSION. No overlapping windows here — each
  session's overnight leg is disjoint from the next — so `block = 1` is correct
  and is asserted rather than assumed.
- **Cost grid, fixed now.** Net results are reported at **5, 10 and 20 bps**
  round trip. 5bps is the optimistic bound for large-cap US names; 20bps is a
  realistic close-and-open auction crossing. **The 10bps column decides.**
- **Positive control.** A planted edge of a stated size must register, measured
  as `edge / sd`, never `(mean + edge) / sd`.
- **MDE reported always.** Rule 10.
- **Survivorship.** Neutral for this arm — it is a within-name time
  decomposition, not a cross-sectional sort into the loser decile. The day-86
  gradient rule does not apply and is not invoked.

## The tail, which a mean will not show

Day-24 measured the overnight penalty as a TAIL property, so a mean net return
is not sufficient evidence on its own. Reported alongside, and any adoption
must survive them:

- the worst single session in each window
- the 5th percentile of session returns in each window
- the ratio of the two windows' standard deviations

An overnight edge that exists in the mean while doubling the worst day is a
variance transfer, not an improvement, and must be labelled as one.

## What may be adopted

A recommendation to hold the basket overnight rather than intraday, **only** if
the net mean at 10bps clears `|t| >= 3`, holds its sign in all four blocks, and
does not worsen the 5th-percentile session. Otherwise this is written up as
REJECTED or UNDERPOWERED and the answer to the window question is closed.

Nothing here changes `r945`, `brief.py` or any live recommendation on this run
regardless of outcome. An adoption would be a proposal put to the portfolio
manager, not a shipped change.

## Forbidden

Reporting the gross figure as the headline. Applying cost to one window and not
the other. Quoting day-85's 57.2% as if it were a net result. Dropping the tail
statistics if they are unflattering. Treating a variance transfer as an
accuracy improvement.

## Expected outcome, recorded in advance

I expect H1c to FAIL on cost. The gross gap between the windows is
+0.023%/session — **2.3bps** — and a single 10bps round trip is more than four
times that. For the overnight expression to win net, the gap would have to be
several times larger than measured. The 57.2% win rate is real and is not the
point: it is the win rate of a long position in a market that drifts up, and it
is available intraday too at 54.5%.

I am running it because that arithmetic deserves to be on the record with the
tail numbers beside it, not because I expect it to pass.
