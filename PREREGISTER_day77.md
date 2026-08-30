# PRE-REGISTRATION — day-77: is the approval reaction real?

**Written and committed BEFORE the expanded sample is built or measured.**
Rule 3 of this repo: pre-register the bar before running the test, and do not
move it afterwards.

## Why this test exists

The corrected base rate (day-74) moved P(CRL) from 23.4% to 8.5–15.9%. That
flips the sign of the only tradeable proposition here:

    E[hold a long through an announced FDA decision]
      = P(approval) x approval_reaction + P(CRL) x CRL_reaction

    at P(CRL) = 8.5%-15.9%, with approval +5.21% and CRL -18.48%:
      +1.45% to +3.20% per event   — IF the approval reaction is real
      -1.57% to -2.94% per event   — if it is truly zero

The CRL leg is settled (t = -5.64, n = 57). **The entire sign of the trade
rests on the approval leg, which currently measures t = +2.42 on n = 173 and
does NOT clear this repo's |t| >= 3 bar.**

That measurement uses 173 usable price windows out of 977 approvals in the
harvest — 18% of the available sample. The bottleneck is price coverage, not
the effect. This test recovers the sample and re-measures.

## The hypothesis, stated as one claim

> The mean event-window return following an 8-K that ANNOUNCES an FDA approval
> is positive and distinguishable from random windows on the same tickers.

ONE hypothesis, ONE window, ONE bar. Not a sweep.

## The window, unchanged from day-68/72

`close(t-2) -> close(t+1)`, where t is the 8-K filing date. Unchanged so the
result is comparable to the existing CRL measurement. An 8-K filed the morning
after an after-close announcement puts the reaction on t-1, which is why the
window opens at t-2.

## What I will do to expand the sample

1. Resolve tickers for filings the SEC current-registrant file misses
   (`build_catalyst.py --resolve-delisted`). Currently 63% resolve.
2. Fetch daily bars with explicit period1/period2 so the 2015-2016 events are
   covered. The current 10-year lookback silently drops them, and day-72
   established that `range=max` returns weekly/monthly bars.
3. Assert daily granularity on every series (median gap <= 4 days) and count
   what is rejected, per day-72.

## The bar, fixed now

**ADOPT** only if ALL of:
- approval windows beat random windows on the same tickers by **|t| >= 3.0**,
  under an EVENT-DATE-clustered bootstrap;
- the positive control detects a planted effect of the size claimed (+5%);
- the placebo (random windows, same tickers, same counts) shows |t| < 3.0.

**REJECT** otherwise. A t between 2 and 3 on a larger sample is a REJECTION,
not "nearly there" — that is precisely the number this test exists to resolve.

**UNDERPOWERED** is a distinct third outcome: if the minimum detectable effect
(3.0 x the bootstrap SE) exceeds the +5.21% currently claimed, the sample still
cannot answer the question and I will say so rather than reporting a null.

## What each outcome means, decided in advance

| result | conclusion | action |
|---|---|---|
| ADOPT | there is a systematic long-into-decision edge of ~+2%/event | size it off the measured tail (p10 -60%, worst -75%): small, and diversified across events, never concentrated |
| REJECT | the +5.21% was noise; E[hold long] is NEGATIVE at every base rate | stop trading this system; it becomes research and monitoring only |
| UNDERPOWERED | the question is not answerable with free data | same as REJECT for capital purposes, and say why |

## Biases I already know about and am not going to discover later

- **Survivorship.** Delisted names lose price history, and failures delist.
  Recovering delisted tickers helps the CRL leg more than the approval leg, so
  it biases the approval estimate UP relative to a complete sample. Report the
  attrition.
- **This is not an independent replication.** It is the same test on more of
  the same data; the n=173 estimate is a subset, not a prior. The expanded
  result SUPERSEDES it rather than confirming it.
- **Partner announcements** (day-74, ZYME/Jazz) mean one decision can be
  announced by two filers. That double-counts events and is a real
  contaminant; dedupe is by (cik, kind) and will not catch it across CIKs.
