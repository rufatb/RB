# Day-113 review — what the "senior analyst" prompt library actually offers us

The owner supplied eleven institutional-desk prompt templates (Goldman screener,
Morgan Stanley DCF, Bridgewater risk, JPMorgan earnings, BlackRock allocation,
Citadel technicals, Harvard dividends, Bain competitive, Renaissance patterns,
McKinsey macro) and asked which would deepen and strengthen what we do.

This is the review. It is not an adoption, and nothing here is wired in.

## The filter that decides almost everything

**We hold for six hours.** Entry 09:46, exit 15:59, same session. Any input whose
signal resolves over quarters cannot inform that decision, however good it is.

That single test disqualifies most of the library outright:

| Prompt | Verdict for us |
|---|---|
| Morgan Stanley DCF (5-yr FCF, WACC, terminal value) | **No.** A fair-value estimate says nothing about the next six hours. |
| Harvard dividend safety, payout ratios, DRIP compounding | **No.** Multi-year income strategy; we hold no position overnight. |
| BlackRock asset allocation, ETF mix, rebalancing schedule | **No.** We do not allocate a portfolio; `positions.py` records what the owner says he did. |
| Bain competitive moat, market share, SWOT | **No** as a signal. Sector *structure* moves over years. |
| Goldman screener (P/E vs sector, 5-yr revenue growth, moat rating) | **No** as a signal, and see the refusals below. |
| Renaissance seasonality, day-of-week effects | **Refused — see below.** |
| JPMorgan earnings-day analysis | **Partly yes** — the *date*, not the thesis. |
| Bridgewater correlation and concentration | **Yes** — and we already compute most of it and fail to use it. |
| McKinsey macro regime | **Partly yes** — we pass four fields; the sector layer is missing. |
| Citadel multi-timeframe technicals | **Yes, in part** — from bars already on disk. |

## The refusals, and why they are not conservatism

Every prompt in the library asks the model to emit a **12-month price target, a
risk rating 1–10, a buy/sell/strong-buy verdict, an entry zone and a stop-loss.**
Those are the outputs of the family this repo exists to not produce.

- A price target from a model with **no track record and no scored outcome** is
  an unmeasured number that reads as a forecast. `CLAUDE.md`: do not present
  picks as predictions.
- "Risk rating 1–10" and "moat rating weak/moderate/strong" are ordinal scores
  with nothing behind them. We already print two unmeasured self-reported
  numbers and label them heavily; a third, on a scale that *looks* calibrated,
  is worse than none.
- "Entry price zones and stop-loss suggestions" is an order ticket. An ABSTAIN
  leg renders no share count precisely because a row carrying a size was acted
  on twice.
- **Seasonality and day-of-week mining is the single most dangerous item in the
  library.** Our record is 107 legs over 39 sessions with an **MDE80 of 23.84
  percentage points**. A day-of-week study on that record cannot resolve
  anything smaller than a 24pp effect; it would return a "best day" every time
  it ran, and it would be noise. `STRATEGY.md` carries 40 rejections, several of
  this exact shape, and day-51's "oracle gap" of +2.34%/trade was smaller than
  what pure noise produced (+2.85%).

None of these is a gap in ambition. Adding them would make the report look more
authoritative while making it less true, which is the failure mode the whole
repo is built against.

## What IS worth taking, ranked by value per unit of work

### 0. Before any of it: the factor layer assessed 5 of 276 today

2026-09-22 gap line, verbatim:

> `DeepSeek batch unavailable: INVALID_SCHEMA (MULTI_SENTENCE_RATIONALE: the rationale had more than one sentence, which fails the entire batch on a style rule)`

**Our own punctuation rule discarded ~98% of the factor layer's coverage.** No
new data field comes close to a 55× coverage recovery, and it costs nothing but
splitting the batch or relaxing a style check that was never load-bearing. This
is priority one and is not in the library at all.

### 1. Normalise the numbers we already send (Citadel, partly)

`_row()` sends `gap`, `r0`, `rvol`, `macd_hist` as **raw percentages**. The model
is currently comparing `+0.85%` on STN.TO against `+1.99%` on IVN.TO as if they
were the same size of event. They are not: a 0.85% gap in a quiet name can be a
three-sigma move and a 2% gap in a volatile miner can be noise.

Add, from daily bars **already on disk** since day-111b:

- **ATR(14) and gap expressed in ATRs** — the single most valuable line item here.
- **Prior-session high / low / close**, and where the open sits relative to them.
  "Gapped above yesterday's high" is the most-used intraday reference there is
  and we do not supply it.
- **SMA50 / SMA100 / SMA200 and the current distance to each**, which is the
  honest part of the Citadel prompt: trend context, not a crossover signal.

Cost: arithmetic over bars we already fetch. No new network call.

### 2. Sector context the model cannot currently see (McKinsey, Bain)

We pass `sector` as a **label** and four macro fields (`cadusd`, `tsx`, `vix`,
`wti`). The model knows SU.TO is Energy. It does **not** know what Energy did
this morning — it infers it from WTI, which is a proxy for one sector only.

Add the morning move of the relevant TSX sector ETF (XEG energy, XFN financials,
XGD gold, XIT tech, …) and each name's return **relative to its own sector**.
`_opening_detail` already computes `sector_relative_return_pct` for the opening
context and it never reaches either model.

Cost: a handful of ETF quotes in the pre-open window, plus wiring.

### 3. Earnings proximity — the date only (JPMorgan)

A name reporting this morning or tonight is a different instrument for six
hours. We tell neither model. Supply **days to next scheduled report** and
**whether it reported before the open today** as facts, and nothing else — no
estimate, no whisper number, no expected move, no "my recommended play".

Cost: low. Point-in-time and auditable, because a date is a fact.

### 4. Common exposure across the *model* picks (Bridgewater)

We already compute concentration — `risk_evidence.concentration`, with the line
"these names can lose together" — and we compute it **only over the engine's
board**.

Look at today's email. DeepSeek shorted **SU.TO and CNQ.TO**, and gave the same
reason for both: *"WTI −5.98% overnight."* That is one oil bet expressed twice,
and nothing in the report said so. Jev's ranking has the same exposure.

Running the existing concentration helper across each model's picks and printing
one line — *"both shorts are Energy on the same WTI move; this is one bet, not
two"* — is the highest-value item in this list that requires **no new data at
all**. It is the genuine content of the Bridgewater prompt, and it is the one
place where these templates identified something we are actually missing.

### 5. Structured, falsifiable pick fields (Goldman/Bain format, Morgan Stanley discipline)

The one thing worth stealing from the *output* side. Today's rationales are free
text of varying shape, so they cannot be compared across names or across days.
Require a fixed field set per pick:

- the level it is above/below (from §1),
- the macro or sector driver it is citing (from §2),
- **what would invalidate this today** — lifted from the DCF prompt's "key
  assumptions that could break the model", which is the only genuinely rigorous
  idea in the library.

The last one matters because it is **falsifiable within the session**. A pick
that says "invalid below VWAP" can be scored at 15:59. A pick that says "strong
momentum" cannot. That converts the model sections from opinion into something
with a future track record — which is the only honest route to ever claiming
either model adds anything.

## The constraint none of this removes

Day-109 established that the binding constraint is **evidence quality**, not
model capability and not prompt sophistication: every Yahoo RSS item classifies
as COMMENTARY or UNCLASSIFIED, catalyst tags are zero across TSX names, and
widening the roster 60 → 130 moved assessed 23 → 29 and produced **no extra
lean**. More fields on a thin prior is still a thin prior.

So, per house rules 3 and 4, and before any of §1–§5 is claimed to have helped:

1. **Pre-register the bar first.** Which section improves, by what measure, over
   what window, decided before the run.
2. **Every addition gets a positive control.** A field that cannot be shown to
   change the answer when the answer should change is not adding information —
   it is adding tokens.
3. **Adding a field is not an accuracy claim.** The engine's 95% interval still
   contains 50% after 107 legs. Nothing here changes that, and nothing here may
   be reported as if it had.
