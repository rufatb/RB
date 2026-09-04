# The free-data ceiling — what it costs, and what it would buy

Written day-87, after eleven arms across three markets and 4.3M ticker-days
produced no adoptable strategy. This is not a shrug. Two of those failures were
caused by data limits rather than by absent effects, and both limits have a
price.

## The two binding constraints, in order of what they cost us

### 1. Survivorship — it manufactures effects, it does not merely widen intervals

The universe is TODAY's ticker list. Names that fell and delisted are absent,
so any sort into the loser decile is measuring a population the market did not
actually offer.

This is no longer theoretical. Day-86 measured it:

| | day-85 (578 names) | held-out (1,279 names) |
|---|---|---|
| 52w proximity, 20d | −1.165% | **−5.099%** |
| small-vs-large quartile ratio | 3.9x | **25.0x** |

The effect quadrupled as the universe extended into smaller names, and 25x of
it lived in the smallest liquidity quartile — exactly where the missing
delistings would have been. **This repo's own standard defence since day-32,
the size test, passed it**, because that test was sign-based and all four
quartiles shared a sign. That gap was open for 54 days and is now closed
(`SIZE_RATIO_MAX = 2.0`).

The lesson generalises: with free data, **any cross-sectional strategy that
buys losers is untestable here**. Not underpowered — untestable, because the
bias points the same way as the hypothesis.

**What fixes it:** a point-in-time universe including dead tickers, with
delisting returns. CRSP is the reference product; commercial vendors resell
equivalents. This is a paid dataset, and it is the single highest-value
acquisition on this list because it converts an entire family of hypotheses
from untestable to testable.

### 2. Intraday depth — the feature the engine has never actually had

Day-43 settled that `r0`/`gap`/`vp` are exhausted: gradient boosting with ~100x
the shipped model's capacity reached **AUC 0.5022 on 122,234 rows** while the
same harness caught a planted 52% coin at z=15. Accuracy cannot come from
rearranging those three.

`vp` is a Yahoo-derived proxy for volume pace. **True order-book imbalance and
real-time volume pace are a different measurement, not a better version of the
same one** — which is why they are not foreclosed by that AUC result. Day-43
ranked this most plausible of the four candidates it named.

**What fixes it:** an L1/L2 feed. IBKR or TMX for the Canadian line; several US
vendors. The catch is that it has **no history** — depth is not stored by these
feeds retrospectively, so this requires forward collection before a first
result. Budget months, not days, between paying and knowing.

## Scorecard of day-43's four candidates

| candidate | status |
|---|---|
| short interest / borrow | **CLOSED day-84.** Bounded null: an improvement of 0.10%/leg or more is excluded |
| L1/L2 depth and true volume pace | **OPEN.** Paid, and needs forward collection |
| point-in-time overnight news | **OPEN.** Partially addressed — SEC 8-K Item 2.02 acquired day-85 with minute timestamps, and PEAD came in at −0.000%. General news is still unacquired |
| sector/index futures state at 9:45 | **OPEN, low priority.** Largely pre-refuted: pair beta to the tide is +0.12 and calm-vs-windy days differ by 0.02%/day |

## What free data has already given, and its limit

Not nothing — days 84-87 acquired, at zero cost:

- 4,134 FINRA short-interest reports with the issuer-name integrity check that
  caught three ticker reassignments
- 61,217 SEC 8-K Item 2.02 earnings announcements, timestamped to the minute,
  separating before-open from after-close
- 4.3M ticker-days of daily bars across 1,857 US names

The limit is not volume. It is that **free universes are survivorship-biased
and free intraday data is a proxy.** More of the same buys tighter intervals
around the same biases.

## The recommendation

**Do not buy the depth feed first.** It is the more exciting candidate and the
worse first purchase: it is expensive, it needs months of forward collection
before it says anything, and its prior is one in five at best against 39
rejections.

**Buy the survivorship-free universe first, if anything.** It is cheaper, it
works retrospectively on data already held, and it would immediately re-open
the weekly-reversal and proximity families that day-86 had to reject as
untestable rather than refuted. It also retro-validates or kills day-85's H4,
which is currently sitting in limbo as tail-carried.

**And the honest option is to buy neither.** The live record is 49% on 105 legs
with selection contributing −0.140%/session. Nothing in days 84-87 suggests a
data purchase would change that, and the one certain lever remains cost — which
is why day-87's `TYPICAL_MOVE_PCT` correction, unglamorous as it is, is
probably worth more than either feed.
