# Day-149b — the commodity nowcast against consensus, on history (owner, 2026-11-09)

Registered BEFORE any price was read for this test. Council lab item 13. One
look. Nothing here changes a pick, a size, the Top 2 or any email.

## Why

The owner pasted another assistant's "Information Surprise Alpha" engine on
2026-11-09 and then said "Build all that are missing from above". The engine
compares an "independent estimate" with what the market expects and names no
source for the estimate. For a gold or silver producer one exists
(`nowcast.py`):

    nowcast = last quarter's revenue × (this quarter's average metal price
                                        ÷ last quarter's average)

The quarter's average price is public the day the quarter ends, weeks before
the report. The question: when the nowcast stands above or below the
consensus, do the shares react that way when the company reports?

## The population (counted before any price was read)

* **The names:** the 19 gold and silver producers on the 2026-11-09 list that
  also trade in New York (`data/tsx_sectors.json` industry Gold or Silver;
  `data/us_twins.json`): AAUC, ABX, AEM, AG, AGI, ARIS, AYA, BTO, CG, ELD,
  EQX, FNV, FVI, IMG, K, OGC, PAAS, SSRM, WPM. Their New York rows are in US
  dollars as reported.
* **The quarters:** each report dated 2012-01-01 → 2026-11-09 in FMP's
  `earnings` rows for the New York symbol, with a consensus revenue, the
  previous quarter's reported revenue, and both quarters' average metal price
  (FMP `GCUSD` or `SIUSD`, 55 or more daily prices a quarter).
  * A report covers the last calendar quarter that ended 14 or more days
    before its date. Two rows that map to one quarter are both left out.
* **The consensus must be corroborated.** FMP's revenue consensus disagrees
  between a company's two listings on more than half of these quarters
  (606 quarters; 269 agree). A quarter counts only when the Toronto row dated
  within 3 days gives a revenue surprise within 3 points of the New York
  row's. **269 quarters qualify**, 233 of them from 2022 on.
* **The sides** (`nowcast.side`): LONG when the nowcast is 3% or more above
  consensus, SHORT when 3% or more below, none inside 3%, and none beyond
  25% (a change in ounces, not in price). That gives **65 LONG, 98 SHORT**,
  54 inside and 52 beyond.
* A quarter whose prices do not cover the window below is left out and
  counted.

## The measure

* **r** = the Toronto listing's return from the last close before FMP's
  report date to the close three sessions after it, minus XGD.TO's over the
  same window (FMP dividend-adjusted closes). A date that is not a session
  stands as the next session.
  * FMP dates a third of reports early (day-135b). The entry is before FMP's
    date and the exit three sessions after it, so an early date still holds
    the reaction and a late one only dilutes it. No day is chosen by its
    volume.
* **y** = side × (r − r̄), where r̄ is the mean r over every qualifying
  quarter, sided or not. A premium common to report windows on today's list
  (day-138's survivor effect) cancels.
* **The statistic:** the mean y over the sided quarters, with a t clustered
  by the ISO week of the report date.

## The bar

`nowcast_history.py`, committed before it runs.
* **NOWCAST_SORTS needs all of:**
  * t ≥ 3.0;
  * a placebo p < 0.01: the sides shuffled among the sided quarters, 2,000
    draws, seed 149;
  * both halves of the quarters (by date) positive;
  * a mean above the 0.13% cost.
* **The control:** +1.0% planted on every sided quarter must show at t ≥ 3.
  If it does not, anything short of a pass is UNDERPOWERED, not NULL.
* **Otherwise NULL.** Anything but NOWCAST_SORTS is rejection #65.
* A pass would go to the owner as a proposal for a forward shadow. It would
  change nothing by itself.

## Reported with the verdict, never part of it

* **The information check:** on the sided quarters, how often the nowcast's
  side matched the sign of the revenue surprise (reported ÷ consensus − 1),
  with its clustered t against a half. A nowcast that cannot call the
  surprise is not an estimate.
* All 606 quarters with the New York row's consensus as it stands.
* LONG and SHORT apart; gaps above and below 10%; 2012–2021 against
  2022–2026.
* The 20 sessions before the entry, signed by the side: whether the price
  already had it.

## Said before the look

* **Power.** About 163 sided quarters. If a miner's four-session move against
  XGD.TO has a standard deviation near 5%, the smallest effect this can see
  is near 2% a report. The likeliest verdict is UNDERPOWERED. **Do not expect
  a pass.**
* **Not blind on two quarters.** While the function was written, Kinross's
  2026 Q3 read LONG (nowcast 8.1% above consensus) and its reported revenue
  came 10% below consensus; Equinox's 2026 Q3 read beyond the guard (a
  merger). Neither reaction was read. Equinox's window is not complete and is
  left out.
* **Ounces are not in it.** The nowcast carries last quarter's volume. The
  gap's quartiles are −11% and +7%, so most of it is volume the consensus
  knows about.
* **FMP's consensus has no vintage.** A row refreshed after the report would
  pull the consensus toward the reported figure, which works against the
  nowcast, not for it.
* **Today's list.** The names are survivors. The statistic is a difference
  between sides around a common mean; a long-only reading is never taken
  from it.
* **Oil and copper are not tested.** The FMP plan serves no WTI or copper
  series (HTTP 402), and the Canadian producers' rows are converted, not as
  reported.
