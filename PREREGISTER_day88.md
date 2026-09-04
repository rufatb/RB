# Pre-registration — day-88, the earnings filter earnings.py could never test

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

## The claim being tested, quoted from the module that makes it

`earnings.py` has carried this since day-53:

> *"Yahoo returns fiscal QUARTER-END dates rather than announcement dates — so
> there is no free source of historical announcement dates for TSX names, and
> therefore **no way to measure whether excluding these rows would have
> helped**. Claiming an accuracy benefit here would be exactly the unbacked
> assertion this repo has spent 35 rejections removing."*

So the module WARNS about earnings and deliberately never GATES on them, because
the benefit of gating was unmeasurable. Day-85 acquired **61,217 SEC 8-K Item
2.02 announcements across 1,857 US names, timestamped to the minute**. The
measurement is now possible, and this is it.

**This is not a new feature.** It is a FILTER — removing rows the model has no
business predicting on. That matters because day-43 settled that `r0`/`gap`/`vp`
carry no usable signal (AUC 0.5022 on 122,234 rows), and a filter does not
contradict that finding. It asks a different question: is the coin flip WORSE
on days when real information lands inside the window, and does removing those
days leave a better remainder?

## The control that makes this study worth running

Item 2.02 timestamps separate three cases, and one of them is a **built-in
placebo**:

| timing | lands | can it move an open->close leg? |
|---|---|---|
| BEFORE_OPEN | before 09:30 ET | **yes** — inside the window |
| IN_SESSION | 09:30-16:00 | **yes** — inside the window |
| AFTER_CLOSE | after 16:00 | **NO** — the leg is flat by 15:55 |

An AFTER_CLOSE announcement **cannot** affect a leg that is closed before it
lands. So excluding those rows must show **no effect**. If it does show one,
the study is measuring the act of dropping rows, not earnings — and the whole
result is void.

This control is free, it is exact rather than statistical, and it is the reason
this study can produce a usable answer rather than another underpowered shrug.

## Panel

Hourly bars for roughly 200 liquid US names over 720 days, entry at the first
hourly close, features and walk-forward identical to `validate_twins` — which
is to say identical to the live engine except for the entry bar.

**The standing caveat is not weakened here:** entry is 10:30, not 9:45. This is
a MECHANISM sample. It can refute or support how a rule behaves; it cannot
certify live 9:46 levels. The ledger's PAIR line remains the arbiter.

## Hypotheses

**H1 — the filter helps.** Per-leg tide-relative capture and hit rate on legs
REMAINING after excluding names with a BEFORE_OPEN or IN_SESSION announcement
that day, against the unfiltered baseline on the same sessions.

**H2 — the excluded rows are actually worse.** The dropped legs measured
directly. H1 can only improve if these are worse than average; if they are not,
any H1 gain is arithmetic.

**H3 — THE PLACEBO. Excluding AFTER_CLOSE announcement days must do nothing.**
Same filter, same count of dropped rows, on announcements that land after the
leg is flat. **A significant effect here voids H1 and H2.**

## Statistics and bars

- **Statistic.** Tide-relative capture per leg, paired BY SESSION against the
  unfiltered baseline — the filter and the baseline share the same days, so an
  unpaired comparison would measure the days rather than the filter. Hit rate
  is reported beside it and does not decide.
- **Bar.** `|t| >= 3` on the paired difference AND the same sign in all four
  contiguous blocks. Both.
- **Clustering.** Bootstrap by SESSION.
- **MDE always reported.** Rule 10.
- **Positive control.** A planted edge of a stated size must register, computed
  as `edge / sd`, never `(mean + edge) / sd`.
- **Cost.** A filter that trades FEWER legs saves spread rather than paying it,
  so cost works in this rule's favour and is reported separately from the
  accuracy claim so the two cannot be conflated. An accuracy claim must stand
  on accuracy.

## What may be adopted

A gate in `earnings.py` — moving it from warning to blocking — **only** if H1
clears the bar, H2 confirms the dropped rows were genuinely worse, and **H3
shows nothing**. All three. Any adoption would be proposed to the portfolio
manager, not shipped silently, and would carry the 10:30 mechanism caveat until
confirmed on live 9:46 legs.

## Forbidden

Dropping H3 or reporting it after H1. Reporting the filtered hit rate without
the paired difference. Pooling the three timing classes. Treating a spread
saving as an accuracy result. Quoting any of this at the live TSX book, which
has no earnings feed and is a different market.

## Expected outcome, recorded in advance

I expect H1 to be POSITIVE but small, and probably underpowered — earnings days
are perhaps 1.5% of ticker-sessions, so the filter removes very few rows and a
small improvement on a small subset is hard to resolve. I expect H2 to show the
dropped rows are genuinely worse, because a binary landing inside the window is
exactly the case the 60-day training pool does not represent. I expect H3 to
show nothing, and if it does not, I will report the whole study as void rather
than salvage H1.

The honest prior after 39 rejections is that this fails too. It is worth running
because it is a documented gap rather than a new guess, the control is exact,
and the answer is useful either way — a null closes a question the codebase has
had open since day-53.
