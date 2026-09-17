# Day-110 pre-registration: asking the model for its own picks

Committed before any forward observation is scored. House rule 3: the bar is
set here and is not moved afterwards.

## What this adds, and why it is not the day-99 factor layer

`deepseek_factors` asks one narrow question under the day-102 grounded
contract — *is there directional sentiment in these headlines* — and on a
Yahoo RSS feed that carries commentary rather than disclosure-timed events the
honest answer is almost always `NO_EDGE`. Day-109's planted control established
that this abstention is real: the harness returns `BULL +0.30` and
`BEAR −0.60` on planted catalysts and `raw == final`, so the null is
informative, not broken.

But nobody had ever asked the model the question the owner was actually asking:
**given these technicals, which names would you be long and short today, and how
sure are you?** That is an opinion, not a sentiment reading, so it gets its own
module (`deepseek_opportunities.py`), its own staged snapshot, and its own
report section beside the quantitative board.

## The instrument

- **Input.** At most 60 names from the staged factor pool, each carrying a
  complete set of Python-computed indicators (`rsi`, `macd_hist`, `rvol`,
  `last`, `vwap`, plus `r0`, `gap`, `open`, `orb_high`, `orb_low` when present),
  all from completed exchange sessions. The model computes nothing and sees no
  price after the previous close.
- **Output.** At most 2 LONG and at most 2 SHORT, each with a self-reported
  `confidence` in [0, 1] and a one-sentence reason. Fewer is permitted and an
  empty answer is explicitly valid.
- **Validation.** A returned ticker outside the supplied universe, a duplicate,
  a malformed confidence or a truncated reply is REJECTED, not repaired. The
  reader re-validates against the universe the snapshot itself records, so an
  edited file cannot put an unassessed ticker in front of a reader.
- **Clock.** Staged strictly before 09:30 ET, sealed with a SHA-256 over the
  canonical encoding, and readable only on the same session within six hours.
  Measured latency is ~54 s on 39 names, which is by itself disqualifying for
  the 09:46 window.

## What a confidence here is

The model's own stated number. It is **not** a calibrated win probability. It
has no track record, has never been scored against an outcome, and is **never
blended** with the engine's sided probability — averaging a measured quantity
with an unmeasured self-report launders the second into the first. Both are
printed; neither is combined.

## Positive control (house rule 4)

`run_control()` plants one unambiguous long (`r0 +2.9`, `gap +1.8`, `rsi 64`,
`macd_hist +0.42`, `rvol 3.10`, last above VWAP and the opening-range high) and
one unambiguous short (the mirror), among ten flat noise names. The planting is
in the NUMBERS ONLY — day-109's first control failed because it wrote
"SYNTHETIC CONTROL" into the evidence and the model correctly refused to lean on
material labelled fake.

Result on 2026-09-17, through the production `rank()` path:

| Arm | Returned | Confidence |
|---|---|---|
| Planted LONG | `CTLUP.TO` | 0.74 |
| Planted SHORT | `CTLDN.TO` | 0.63 |
| Ten noise names | none returned | — |

Both planted sides detected, no noise name selected. A `NO_OPPORTUNITY` reading
from this instrument is therefore an abstention, not a dead harness. This
control is re-runnable with `python deepseek_opportunities.py --control` and
must pass before any null from this module is reported.

## The registered forward question

**H1.** Over 120 sessions, do the model's self-reported confidences separate
outcomes at all — i.e. is the gross hit rate of picks at confidence ≥ 0.65
different from that of picks at confidence < 0.65?

**Bar.** |t| ≥ 3 on session-clustered standard errors, over four quarters, on
both sides. Below that it is not reported as a finding. At ~4 picks per session
and the engine's observed leg-level variance, a 10 pp separation needs roughly
230 picks per bucket; this is registered as **not answerable before ~2027-03**
and is not to be re-opened after a good day or a bad one.

**H2 (descriptive only, no bar).** How often does the model pick a name the
engine also picked, on the same side? On 2026-09-17 the answer was 0 of 4 — and
all four were outside the engine's 21-name universe, so that zero is a fact
about *coverage*, not about disagreement. Until the model is asked about names
the engine actually scores, agreement and disagreement are not measurable.

## What is NOT claimed

No predictive skill, no accuracy gain, no adoption. This ranking enters no
selection, no size, no threshold, no ledger row and no allocation. It cannot
place an order. The baseline board and its allocation are unchanged by the
presence or absence of this snapshot, and a failure to stage it is a reported
gap that never blocks publication.
