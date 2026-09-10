# Day97 microstructure audit — measured, not adopted

Reviewed production base: c632b14bd538d77157728be680aaf8e606d51151.
Registration committed before this reanalysis:
[b9cbccc](https://github.com/rufatb/RB/commit/b9cbccc6da2b6abd6f288a83704c8d2724960c87).
Source: the existing completed-session cache and original published pair records.
No new market data, strategy fitting, repicking, orders or email delivery.

## What was tested

The fixed rules in PREREGISTER_day97_microstructure.md cover delayed entry,
opening-range/VWAP confirmation, opening RVOL >= 2.5, an 11:30 full exit and
an unconditional half exit. Current main's selector already uses first-15-minute
return, opening gap and relative opening volume in a numerical nearest-neighbor
model. It is not an LLM news-sentiment selector. RB already distinguishes a
completed 09:45 opening reference from an executable 09:46 quote.

The cache contained 60 dates (June 15–September 9), intersecting 115 recorded
pair legs across 41 dates. Requiring a complete original board, valid full
sessions and 20 preceding valid opening-volume windows retained **103 legs
across 36 dates, July 14–September 9**. Five boards were excluded: July 13
(insufficient warm-up), July 17/23/28 (missing prior-session bars), and
September 8 (AEM missing bars). No missing data were filled.

This is retrospective development evidence. These losses and previous exit
studies were already observed. It is not fresh out-of-sample confirmation.

## Fixed outcomes on the matched sample

Gross returns below use bar-price proxies. The baseline enters at the 09:45
bar OPEN; delayed/confirmed arms at the 09:50 bar OPEN. Close is the 15:55
bar CLOSE. None is an exact 09:46–15:59 executed return.

| Arm | Admitted / 103 | Gross hit rate | Mean gross per admitted leg |
|---|---:|---:|---:|
| Baseline proxy | 103 | 46.6% | -0.106% |
| Delay only to 09:50 | 103 | 43.7% | -0.073% |
| RVOL >= 2.5 only | 0 | unavailable | unavailable |
| ORB + approximate VWAP at 09:50 | 6 | 33.3% | -0.400% |
| ORB + VWAP + RVOL >= 2.5 | 0 | unavailable | unavailable |
| Full exit at 11:30 | 103 | 39.8% | -0.210% |
| Half exit at 11:30, half at close | 103 | 43.7% | -0.158% |

The 2.5 threshold would eliminate every matched selection from this engine.
That does not say no high-volume stock existed in the market: this is a gate
on the unchanged baseline's names, not a new high-volume universe selector.
The maximum observed opening RVOL among these 103 selections was 2.204.
Six ORB trades cannot establish that the rule works or fails generally.

All trading arms have negative conditional gross EV in this sample, before
spread, fees, slippage or borrow. Their break-even positive friction budget is
therefore absent. The 5/10/20 bps proportional friction scenarios in the private
results only worsen these returns. They are not verified net P&L.

For the baseline, the average winner was +0.767% and the average loser -0.868%.
A hypothetical 55% win rate and 1.5:1 average payout would yield +0.375 risk
units before costs, but those are assumptions, not this engine's measured
payout distribution. Profit targets do not guarantee realized average payouts.

## Paired uncertainty and retained opportunity capacity

For comparability, one unit of each original leg's capacity is retained;
abstentions contribute zero, and daily means are formed before uncertainty.
This is a diagnostic normalization, not actual recorded portfolio allocation.
The following quantities are bps of normalized gross daily return.

| Arm vs baseline | Difference | 95% approximate interval | MDE80 |
|---|---:|---:|---:|
| Delay to 09:50 | +3.33 | -0.74 to +7.39 | 9.00 |
| RVOL >= 2.5 | +12.42 | -11.89 to +36.73 | 53.86 |
| ORB + VWAP | +10.31 | -15.03 to +35.64 | 56.12 |
| ORB + VWAP + RVOL | +12.42 | -11.89 to +36.73 | 53.86 |
| Full exit 11:30 | -9.66 | -22.29 to +2.97 | 27.97 |
| Half exit 11:30 | -4.83 | -11.14 to +1.48 | 13.99 |

The apparent improvement for an all-abstain gate is avoiding a losing sample,
not finding profitable trades. Every interval spans zero. All fixed +5 bps
statistical sensitivity controls fail the preregistered 3.5-SE threshold.
This audit cannot resolve a small economic improvement. MDE for actual
net/index alpha remains unavailable because matched execution costs and index
observations are absent.

The full 11:30 exit reduced normalized daily standard deviation from 64.67
to 54.97 bps while lowering average gross return. The half exit reduced it to
56.66 bps. Lower variability and higher expected return are separate goals;
neither partial profits nor a lunch exit is automatically an edge.

## September 9 specifically

| Recorded selection | Opening RVOL | 09:50 ORB/VWAP confirmed? |
|---|---:|---|
| TRP.TO long | 0.535 | No |
| ENB.TO long | 0.657 | No |
| SLF.TO short | 0.201 | No |
| BCE.TO short | 0.850 | No |

The gates would have skipped that day's three losing proxies and one winning
proxy. That one-day hindsight saving is not enough to adopt them, especially
when the strict volume gate rejects the entire matched sample.

## Timing and mechanism corrections

For start-labelled five-minute data, 09:30/09:35/09:40 bars define the first
15-minute range. The next completed breakout confirmation arrives at 09:50.
This audit pays the next bar's opening price, including any gap; it never
fills a confirmed breakout at an earlier threshold or at 09:46.

VWAP calculated from OHLCV is a bar approximation. Level-2 depth, cancellations,
queue position and maker hedging cannot be reconstructed from it. The saved
bars do not establish a universal 09:45–09:50 stop-hunting/liquidity sweep.

Research documents time-of-day volume patterns and their changes across
periods. That supports normalizing RVOL by the same elapsed session window,
but it does not establish 2.5 as optimal or 11:30 as the best exit for TSX
baseline selections.
[Graczyk and Queiros, intraday volume seasonality](https://arxiv.org/abs/1810.12099).

The old exit study is preserved as historical evidence. Its hourly US-twin
sample and coarse trade-price timings prevent treating its conclusion as
universal proof; this newer native five-minute audit also fails to establish
a profitable time-exit change.

## What changes in production

Nothing. The research runner and tests are standalone and never imported by
brief.py, r945.py, the delivery renderer or a scheduled job. Tomorrow retains
the reviewed report fixes and original selection/allocation. No result is
promoted into an executable signal.

Next valid work is forward confirmation of precisely frozen gates with
timestamped execution/cost/index observations. A later-entry engine must report
conditional opening setups at 09:46 and confirm them later; it cannot put a
09:50 fact into the morning email. A separate high-RVOL event universe would
be a new preregistered selector, not a silent fallback after this gate rejects
everything.
