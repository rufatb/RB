# Pre-registration — day-130 step 4: report-day drift

Registered 2026-10-11, BEFORE any data for it was fetched. Step 4 of the plan
in `AUDIT_day130_learning.md`; the owner said "go on for all".

## The question

Every public pre-open input tested here has been priced by the open
(day-117, 118, 122, 125). An earnings report is the one event whose
information keeps arriving after the open: the call, the analysts' notes, the
first block trades. **On a company's earnings reaction day, does its first
half hour (09:30 → 10:00), against the market, predict the rest of the day
(10:00 → close) in the same direction?**

## Population (frozen)

* **Names:** the 117 `.TO` names in the morning pool staged on 2026-10-09
  (`.rb-state/deepseek_candidates.json`). Today's pool, so survivorship is
  possible; disclosed.
* **Reports:** every FMP `earnings` row for those names with `epsActual`
  present and a date from 2024-01-02 to 2026-10-09.
* **The reaction session (causal; FMP gives no time of day).** The candidates
  are D0, the first session on or after the FMP date, and D1, the session
  after it.
  * The event session is the first candidate whose opening gap,
    |open / prior close − 1|, is at least twice the name's median absolute
    gap over the 20 sessions before D0 (daily bars).
  * Each candidate is judged at its own 09:30 with nothing from later.
  * A report where neither candidate qualifies is excluded and counted.
* **Prices.** FMP 5-minute bars and the XIU.TO bars for the same sessions.
  * open = the 09:30 bar's open;
  * 10:00 = the 09:55 bar's close;
  * close = the 15:55 bar's close.

  A session missing any of these is dropped and counted.

## The signal and the outcome (frozen)

* x30 = (10:00 / open − 1) − the same for XIU.TO.
* s = sign(x30); an x30 of exactly 0 is dropped.
* **Outcome** y = s × [(close / 10:00 − 1) − the same for XIU.TO], in %.
  Gross, no costs.

## The bar (ALL must hold)

1. Mean y > 0 with a session-clustered t ≥ 3.
2. The same sign in each of the four date-quartiles of the events.
3. **Placebo p < 0.05.** In each of 2,000 draws, every event is replaced by a
   random non-report session of the same name:
   * drawn from its fetched window (D0 − 14 days … D1 + 3 days);
   * never D0 − 1 … D1 + 1;
   * the same x30 → y computation.

   p = the share of draws whose mean ≥ the observed mean.
4. **Positive control.** A planted +0.5% on every event's y must show at
   t ≥ 3, with the observed dispersion (edge / se, house rule 10). The 80%
   minimum detectable effect, 2.8 × se, is printed. If the control fails, the
   result reads UNDERPOWERED, not null.
5. **Net of costs.** Mean y − 0.10% (a round trip on liquid TSX names) > 0.

## Descriptive only (no bar, nothing adopted from them)

* Events with |x30| ≥ 1% against the rest.
* Whether s agrees with the gap's direction.
* The 10:00 → 12:00 window (the noon exit) instead of the close.
* The count of reports excluded at each step.

## What a pass would and would not mean

A pass licenses only a further registration: a forward, shadow "report-day
alert" at 10:00, decided with the owner. Nothing goes live from this test,
and no existing section changes.

A fail is added to the rejections, and the family is not re-opened without
new data.

Output: `data/replay_day130_drift.json`; script `replay_drift.py`.
