# Day-149b — the commodity nowcast against consensus: the history cannot see it, and the feed's consensus is half wrong (rejection #65, council lab item 13, 2026-11-09)

Registered first: `PREREGISTER_day149_nowcast.md`. The script was committed
before it ran: `nowcast_history.py` (239afff). One look; summary
`data/nowcast_day149.json`. FMP only, cached under
`.rb-state/nowcast_cache/`: no model call, nothing spent.

## The question

The owner's pasted engine compares an "independent estimate" with consensus
and names no source for one. For a gold or silver producer there is one:
last quarter's revenue × (this quarter's average metal price ÷ last
quarter's), public weeks before the report (`nowcast.py`). When it stands 3%
or more above or below consensus, do the shares react that way?

## What was measured

* **The names:** the 19 gold and silver producers on the list that also
  trade in New York, where FMP's rows are in US dollars as reported.
* **The quarters:** 830 with a nowcast and a consensus since 2012. On 606 of
  them FMP has a row for both listings, and **the two rows agree on the
  revenue surprise (within 3 points) on only 269**. The test used those 269.
  * 264 had prices for the whole window. 159 took a side: 64 LONG, 95 SHORT.
    86% of them are from 2022 on.
* **The measure:** the Toronto listing from the close before FMP's report
  date to the close three sessions after it, against XGD.TO, around the mean
  of all 264 report windows. Its standard deviation is 7.3%.

## The verdict: UNDERPOWERED (rejection #65)

| | Registered test | All 825 priced quarters, consensus as it stands (reported) |
|---|---:|---:|
| Sided quarters | 159 over 83 weeks | 398 over 168 weeks |
| Mean | −0.20% | +0.05% |
| Net of 0.13% | −0.33% | −0.08% |
| t, clustered by week | −0.34 | 0.16 |
| Placebo p | 0.63 | 0.44 |
| Halves | −1.23%, +0.81% | −0.23%, +0.34% |
| Right | 73 / 159 (46%) | 193 / 398 (48%) |
| Planted 1.0% shows at | t = 1.67 | t = 2.90 |
| Smallest detectable effect | 2.56% | 1.48% |

* **The nowcast's side did not sort the reaction.** 46% right, −0.20%, and
  the halves disagree.
* **The test could not have seen less than about 2.6% a report.** A planted
  1.0% reaches t = 1.67. The registration said UNDERPOWERED was the likeliest
  verdict.
* **On the wider population,** where a planted 1.0% nearly shows (t = 2.90),
  there is nothing either: +0.05%, t = 0.16.

## Reported with it

* **The nowcast knows a little about the revenue surprise.** Its side matched
  the surprise's sign on 91 of 154 sided quarters (59%), t = 2.37 against a
  half. That is short of the bar.
* **Knowing the surprise would not have paid either.** Siding each of those
  quarters by the revenue surprise that was later reported makes +0.41%,
  t = 0.72, 84 of 154 right. Revenue against consensus is not what moves
  these shares over four sessions.
* **By side:** LONG −0.36% (29 of 64), SHORT −0.10% (44 of 95).
* **By size of gap:** 10% or more +0.25% (t = 0.31); under 10% −0.65%
  (t = −0.73).
* **By period:** 2012–2021 −3.14% on 22 quarters; 2022–2026 +0.27% on 137
  (t = 0.45).
* **The 20 sessions before the entry,** signed the same way: −0.10%,
  t = −0.14. The price had not moved the nowcast's way beforehand either.

## What it means

* **A price-only nowcast is mostly noise against consensus.** Consensus
  already has the metal price. The gap's quartiles are −11% and +7%: that is
  ounces, which the nowcast does not know. Kinross's 2026 Q3 read LONG
  (+8.1%) and reported 10% below consensus because it sold less.
* **The stronger form is not in any feed.** On Equinox (11-09) the estimate
  that beat consensus was ounces already announced × the average price. That
  needs each company's production release read, and the price had it anyway.
* **A trap, caught.** On the 825 quarters with the consensus as FMP gives it,
  the nowcast "calls" the revenue surprise 68% of the time (t = 7.3). That
  reads the feed's errors: where a consensus row is wrong, last quarter's
  revenue beats it. On the corroborated rows it is 59%. **Never test a
  consensus signal on FMP's revenue estimates without checking them against
  the other listing.**
* **So:** no shadow is proposed for it, and nothing live changes. The event
  desk shows the nowcast as one labelled fact where both listings agree on
  the consensus (`nowcast.for_report`); it carries no side there.

## One departure from the registration

The registration's reported arm said "all 606 quarters" (those with a row on
both listings). The script kept every quarter with a nowcast and a consensus
on the New York rows, 830, of which 825 had prices. It is a reported arm and
no verdict rests on it.

## Not claimed

That the nowcast has no value: the history cannot say. That any pick is
better for it: nothing here shows that.
