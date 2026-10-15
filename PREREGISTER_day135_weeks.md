# Day-135b — do TSX names drift for weeks after earnings and rating changes? (owner, 2026-10-15)

Registered BEFORE any return below was computed. The FMP earnings and rating
histories were checked for coverage only (fields, depth); no price was read
for any event.

## Why

The owner: the 09:45 → close trade "is a little bit too much of a gamble …
maybe a couple of weeks hold … depending on the events and macro variables and
company specifics, maybe earnings surprises and reports … something that gives
you an edge."

The record agrees about the intraday window. Every registered test of 09:45 →
close is null (day-117, rejections #43–#49), and a 0.13% round trip turns a
coin flip into a slow loss. What has NOT been tested is a multi-week hold that
starts from a company event on the names the desks actually trade:

* Day-85 (US, 578 names, 2016–2026) signed post-earnings drift by the price
  reaction only, held 5 and 10 sessions: −0.000% and +0.075% (t = 1.36).
  It never used the surprise against consensus, a 20-session hold, or TSX names.
* Day-125 and day-130 tested rating changes and report days within the same
  session only. The open prices them; what follows over weeks is untested.
* Rejection #28 held the ENGINE's picks for 3 and 5 days: the "gain" was
  market drift collected by a mostly-long book, and hedged it vanished. #40
  was intraday entry times and durations. Nothing here holds a model's pick;
  every position is defined by an event, and every return is market-adjusted.

## What the literature leads me to expect (recorded in advance)

* Post-earnings drift has largely disappeared in large US stocks since about
  2006 (Martineau 2022, "Rest in Peace Post-Earnings Announcement Drift";
  disputed by two 2025 papers).
* Canada, 1994–2009: a long-short on analyst-based surprise deciles earned
  about 6% over 60 days (Chudek, Truong and Veeraraghavan 2011). That is an
  older, less arbitraged period.
* A reaction-based signal (the announcement return) drifted more than the
  surprise itself in older US samples (Brandt et al.).
* Post-revision drift after analyst rating changes was not different from zero
  in 2003–2010 (Altinkilic, Hansen and Ye 2016). It survives in some samples
  for downgrades, and for changes that come with estimate revisions.

**Expected:** W1, W2 and W4 NULL on these liquid names, with any drift
concentrated before 2012. If anything passes, the most likely is W3 (surprise
and reaction agree), and on its short side.

## Population and data

* **Names:** the 150 names of the 2026-10-15 TSX list (`tsx_universe.json`,
  the day-101 rule). Market: XIU.TO.
* **Survivorship (unfixable here):** these are TODAY's most traded names; every
  one survived and grew. Signals are balanced terciles (below), so a common
  survivor drift cancels in the signed mean; the long and short legs are
  reported apart so it can be seen.
* **FMP Premium:**
  * `earnings` (date, epsActual, epsEstimated, revenueActual,
    revenueEstimated): back to 2002 on the large names;
  * `grades` (date, action upgrade / downgrade / maintain): back to 2012;
  * `historical-price-eod/dividend-adjusted` (returns) and
    `historical-price-eod/full` (the unadjusted close that scales a surprise).
* **Checks (rule 9):** daily granularity per series (no duplicate dates,
  median gap ≤ 3 calendar days); every rejected series and every event dropped
  for a missing bar is counted and printed. Sessions are XIU.TO's trading
  dates; a name's missing bar on a required date drops the event.

## Events and entries (causal: everything is known at the entry close)

**Earnings (W1–W3).** R = FMP's report date (it carries no time of day).
* P0 = the last session strictly before R.
* D1 = the first session strictly after R. A pre-open report on R and an
  after-close report on R are both public by D1's close.
* **Entry: the close of D1.**

**Rating changes (W4).** G = FMP's grade date; D0 = G if G is a session, else
the next session. Day-125 measured that FMP's date is the reaction day (the
open moved the rating's way 87% of the time).
* One event per (name, D0): net = upgrades − downgrades that day; 0 is dropped.
  "maintain" is never an event.
* **Entry: the close of D0.**

**Exit:** the close of the H-th session after entry, **H = 10 (primary)**,
and 5 and 20 (secondary).

**Outcome:** y = sign × 100 × [(adjClose_exit / adjClose_entry − 1) −
(XIU adjClose_exit / XIU adjClose_entry − 1)], in % per trade, market-adjusted.

## The four signals

A signal is "high" or "low" against the ROLLING distribution of the same
quantity over all events (all 150 names) whose entry falls in the 365 calendar
days strictly before this event's entry. Above the 70th percentile is long;
below the 30th is short; the middle is no trade. An event needs at least 100
earlier events in its window (the burn-in).

* **W1, the surprise.** SUE = (epsActual − epsEstimated) / unadjusted close
  at P0.
* **W2, the reaction.** EAR = (adjClose_D1 / adjClose_P0 − 1) − the same for
  XIU.TO.
* **W3, both agree.** Long when W1 and W2 are both long; short when both are
  short; otherwise no trade.
* **W4, the rating change.** Long on a net upgrade, short on a net downgrade.
  No percentile.

## Statistics

* **The mean of y, with a conservative t:** the smaller |t| of two
  bootstraps (2,000 draws each, seed 135):
  * by NAME (one issuer contributes many events; day-85's event rule);
  * by CALENDAR BLOCKS of H sessions of entry date (block = horizon: day-85
    showed overlapping windows inflate a single-date bootstrap).
* **Placebo:** 1,000 draws (seed 135). Each event keeps its name and sign and
  moves to a random session of the same name within ±250 sessions, never
  within 10 sessions of a real event of its family. Two-sided p = share of
  draws with |mean| ≥ the observed |mean|.
* **Positive control:** a planted 0.50% per trade must show at
  t = 0.50 / se ≥ 3 at H = 10 (house rule 10: edge / sd, never
  (mean + edge) / sd). MDE at the bar = (3.0 + 0.84) × se.
* **Blocks:** four chronological blocks of equal event count.
* **Tail:** the median's sign against the mean's.
* **Cost:**
  * 0.13% a round trip (day-132b's measured 09:46 spread plus commission; a
    close-auction order is usually cheaper, so this is conservative);
  * plus borrow on short legs at 0.5% a year: 0.01%, 0.02% and 0.04% at
    H = 5, 10 and 20.

## Verdicts (fixed now; decided at H = 10)

| Verdict | Needs all of |
|---|---|
| DRIFT (a candidate) | mean > 0; conservative t ≥ 3; placebo p < 0.01; ≥ 3 of 4 blocks > 0; median > 0; net mean > 0 |
| REVERSAL | mean < 0; t ≤ −3; placebo p < 0.01; ≥ 3 of 4 blocks < 0; median < 0 |
| NULL | neither, with the control passing |
| UNDERPOWERED | neither, with the control failing |

H = 5 and 20 are reported with the same arithmetic. A pass there alone is
SECONDARY ONLY: it cannot rescue a failed H = 10 and would need its own test.
Four signals at one primary horizon with a t ≥ 3 bar keep the family's
chance of a false pass small; nothing is added after the results are seen.

## Descriptive splits (printed, no verdict, never a rule)

* long and short legs apart;
* 2002–2011 against 2012–2026 (the decay the literature reports);
* liquidity terciles of the list;
* sector (energy, materials and mining, financials, technology, the rest);
* the market at entry: XIU.TO above or below its 50-session average (the
  owner's "macro variables");
* busy days: ten or more of the 150 names reporting the same day, against
  fewer (investor inattention);
* W4 within two sessions after an earnings report, against the rest;
* W1 with the revenue surprise on the same side, against not.

## What a result changes

* **DRIFT:** a registered forward shadow desk ("multi-week event drift"). It
  records each qualifying event from FMP as it happens, holds H sessions on
  paper, and is scored by the evening job. Nothing is sized or traded from a
  replay; the owner decides after the forward record.
* **NULL:** rejection #50. The record says which window, signals and periods
  were tried, with the MDE, so the next idea is not this one again.

Script: `replay_weeks.py`. Summary: `data/replay_day135_weeks.json`. Audit:
`AUDIT_day135_weeks.md`.
