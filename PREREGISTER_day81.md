# Pre-registration — day-81 fair-value diagnostics

Written and committed BEFORE running the diagnostics on any live name.
Bars set from synthetic controls only (rule 3: pre-register, never move).

## What went wrong on day-80

`cross_check` shipped with this claim in its warning text:

> the empirical figure resamples this name's own history, so a single past
> crash inflates it

**That is backwards.** Measured on planted controls (900 days, σ=0.8%/day):

| planted defect              | estimator gap | mean window return | σ drop when trimmed |
|-----------------------------|---------------|--------------------|---------------------|
| clean (no drift, no crash)  |  12%          | +0.05%             |  3%                 |
| drift, −40% over history    |  60%          | −1.13%             |  3%                 |
| one −55% day                |  22%          | −1.24%             | 63%                 |

- The **gap** between the two estimators does not identify a cause. Both
  mechanisms open one, and they **subtract**. Measured on controls that vary
  one thing each (drift forced to its target after the crash is planted):

  | control                 | gap  | mean window return | σ drop |
  |-------------------------|------|--------------------|--------|
  | clean                   |   4% | +0.05%             |  3%    |
  | drift only              |  43% | −1.13%             |  3%    |
  | tail only               |  44% | +0.04%             | 71%    |
  | tail **and** its level shift | **14%** | −2.84%     | 71%    |

  Each defect alone clears the 0.40 bar. A name carrying **both** reads at
  14% — under it — because the crash's level shift lifts the empirical leg
  while the crash's fat tail lifts the lognormal leg. **The worst case looks
  like the cleanest.** That is the whole argument against a single tolerance,
  and it is why the first table below (measured before the controls were
  properly isolated) showed the crash case at only 22%.
- A **single crash inflates the LOGNORMAL**, not the empirical estimate. σ is
  a second-moment statistic and one day out of 900 dominates it; the empirical
  put value is a first moment and one day carries ~1/900 of the weight.
  The crash case does not even clear the 0.40 gap bar (22%), and the gap it
  does produce points the wrong way.
- `trimmed_fv` trims the *window returns of the empirical estimator*, which is
  the leg that was already robust. It moves 1% on the clean control and 1% on
  the crash control. It was testing the estimator that did not need testing,
  which is why no live name tripped it.

So day-80's report that "no name trips the tolerance" was not evidence the
book is clean. It is what a diagnostic pointed at the wrong mechanism returns.

## Bars, fixed now

Set from the control table above, chosen to sit well clear of the clean
control and well below the planted defect. Not to be moved after seeing live
names.

- `DRIFT_TOL = 0.010` — |mean window return| above 1.0% of spot means the
  empirical fair value embeds a historical trend rather than a distribution.
  Clean control: 0.05%. Drift control: 1.13%.
- `TAIL_TOL = 0.25` — σ falling more than 25% when the extreme 2% of days are
  winsorised means a handful of days carries the volatility, so the LOGNORMAL
  leg is the unreliable one. Clean control: 3%. Crash control: 63%.
- `DISAGREE_TOL = 0.40` — unchanged in value, changed in meaning. It flags
  that the two estimators diverge, and ONLY when neither mechanism accounts
  for it. It is no longer permitted to assert a cause on its own, and a
  reading under the bar is no longer evidence of health.

Where both mechanisms fire, BOTH are reported. Naming only the first match
would narrow the finding silently — the same fault as day-80, one layer down.

### Amendment, same day, bars untouched

The rationale above originally read "the gap is driven by drift, not by
tails", inferred from a crash control whose level shift had not been removed.
Isolating the controls showed each defect opens a ~43% gap on its own. The
three bars are exactly as first registered — 0.40 / 0.010 / 0.25, none moved —
and the correction makes the case for them stronger, not weaker. Recorded here
rather than edited away.

## Positive control, required to stay green

`tests/test_fairvalue.py` plants each defect and asserts the matching
diagnostic fires while the other stays quiet, and asserts the clean control
trips nothing. A diagnostic that cannot detect a planted defect cannot report
a null (rule 4, rule 10).

## What this does NOT establish

Nothing about whether the fair values are right — only that the warnings
attached to them name a mechanism they can actually detect. Whether trading
the gap between fair value and market price makes money remains unbacktested
and untestable with free data.
