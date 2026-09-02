# MASTER INSTRUCTION — codebase review, accuracy program, and the 9:46 pane of glass

Paste this whole document as the task. It is written to be executed over many
sessions. Do not skip Section 0; every later section depends on it.

---

## 0. PRIME DIRECTIVE, AND THE ONE WAY YOU CAN FAIL BADLY

Your objective is to **increase the proportion of calls that resolve the way
they were called** — a LONG pick that rises from the 9:46 entry to the 15:59
close, a SHORT pick that falls over the same window, a pharma expression that
pays — and to deliver a **single, clean, error-free, tactical dashboard** at
09:46 ET each trading day that a portfolio manager can act on without reading
anything else.

**The way you fail is by producing apparent accuracy instead of real accuracy.**
This repository has a live record of **44/93 (47%)** on intraday pair legs and a
measured ceiling: gradient boosting with ~100x the shipped k-NN's capacity
reaches **AUC 0.5022 on 122,234 out-of-sample rows**, while the identical
harness detects a planted 52% coin at **z=15**. Thirty-eight changes have been
tested and rejected; three were adopted and **all three were variance results,
none improved accuracy**. An agent told "increase accuracy" will, if careless,
deliver a backtest that looks excellent and is an artefact of selection,
look-ahead, survivorship, a moved goalpost, or a window that happened to work.
That outcome is **worse than no change**, because it will be traded.

Therefore: **"I tested N ideas and none cleared the bar" is a SUCCESSFUL
outcome of this instruction** and must be reported as such, in full, with the
minimum detectable effect stated. Do not manufacture a win. Do not soften a
null. Do not move a bar after seeing a result.

---

## 1. READ BEFORE YOU TOUCH ANYTHING

1. `CLAUDE.md` — the ten house rules. They are not style guidance; each was
   written after a specific failure and several cost live money or shipped a
   wrong number into a live report for days.
2. `STRATEGY.md` — the complete running record: 38 rejections, 3 adoptions,
   and every defect found. **Almost every "obvious improvement" in this space
   has already been measured here and refuted.** Before proposing anything,
   search this file for it. If it has been tested, say so and say what was
   found, and only re-test it if you can name what is materially different
   (more data, a fixed defect, a different population) — and say that too.
3. `PREREGISTER_day77.md`, `PREREGISTER_day78.md`, `PREREGISTER_day81.md` —
   the format your own pre-registrations must follow.
4. The eleven-day defect log, because it tells you what kind of bug this
   codebase actually produces: silently-wrong NUMBERS, not crashes. Yahoo
   serving monthly bars for a daily request; a classifier missing two thirds of
   approvals through an un-decoded HTML entity; a put fair value counting one
   branch of its payoff and undercounting 2.5x; a point estimate printed
   outside its own confidence interval; a diagnostic whose warning named a
   mechanism it could not detect; a board re-picking different NAMES between
   two reads minutes apart. Every one ran without error.

**Non-negotiable invariants.** Nothing in this repo places, sizes, or cancels
an order — keep it that way. `positions.py` records what the PM says they did.
Never swallow an exception silently. Fail closed on data. The report must
always print its own live record beside any pick. Never delete or bypass the
ledgers (`ledger.py`, `catledger.py`, `advice.py`) or the guards in
`sanity.py`, `constants.py`, `resolved.py`, `validate_catalyst.is_daily`.

---

## 2. CODEBASE REVIEW AND CLEANUP

Audit every module. Produce, before changing anything, a written inventory:
**what each file does, what depends on it, whether it is reachable from
`brief.py`, and whether its claims are still true.** Then:

- **Delete dead code, not load-bearing code.** Anything unreachable from
  `brief.py`, the validators, or the test suite is a candidate. Anything that
  encodes a REJECTION or a caveat is not dead — it is the record, and removing
  it is how a refuted claim comes back.
- **Find duplicated computation.** One was already found — the view and the
  full page each downloaded 120 days of bars for every ticker, 12 seconds of
  duplicate network per run. Look for more. The rule is **one computation, two
  renderings**: `brief.build()` fills a digest, every renderer draws from it,
  and no renderer recomputes anything.
- **Find every place a number is written down twice.** A literal copied into a
  second file is an uncheckable copy of a measured value. `constants.py` exists
  for this; register anything you find and make the second site derive it.
- **Reconcile the docstrings with the code.** Several docstrings in this repo
  have asserted things the code did not do — a note claiming share counts came
  from the published board while they were being recomputed; a warning naming
  outlier inflation in the leg that was robust to it. Treat a docstring that
  cannot be verified as a bug and either fix the code or fix the sentence.
- **Consolidate the option/quote path.** Quote failures are the single largest
  source of missing output today (on a recent run 6 of 13 calendar names were
  unpriceable). Build one quote layer with explicit validation, retry, and a
  typed failure reason, and make every caller use it.
- **Kill the fluff in the output layer.** See Section 6.
- Keep the test suite green at every commit (**currently 651 passing**). Add
  tests with every change; never delete a test to make a change pass — if a
  test is wrong, say why in the commit and replace it with one that asserts
  the same intent.

---

## 3. WHAT "ACCURACY" MEANS HERE — DEFINE IT BEFORE YOU OPTIMISE IT

Write these definitions into a file and use them unchanged throughout.

- **Intraday hit.** A leg entered at the 9:46 print and marked at the 15:59
  close, direction-correct. State explicitly whether a scratch (|move| below
  the round-trip spread) counts as a miss — the current ledger reports both
  "all legs" and "decisive legs" and you must keep both.
- **Accuracy net of cost.** The current pair starts $2–$27 behind on spread
  before the market moves. A hit rate that ignores this is not a P&L claim.
  Report **hit rate, mean return per leg, and mean return net of the measured
  round-trip spread**, always together.
- **Tide-adjusted.** Long-minus-short must be measured against the day's market
  move. A book that is long-biased on an up day is not accurate, it is exposed.
  Keep and extend the existing TIDE / SELECTION attribution.
- **Pharma.** A catalyst expression resolves at the FDA decision, not at a
  fixed horizon. Its accuracy is scored by `catledger.py` against the outcome
  from `resolved.py` (the 8-K), never against the tape.
- **Weekly.** If you build weekly ideas, define entry, exit, and horizon
  before testing, and score them on the same clustered, cost-aware basis.

---

## 4. MEASUREMENT PROTOCOL — MANDATORY FOR EVERY CLAIM

No change ships without all of the following, in this order:

1. **Pre-register.** Commit a `PREREGISTER_dayNN.md` naming the hypothesis, the
   population, the exact statistic, the sample, and the adoption bar (`|t| ≥ 3`
   is the standing bar; a different one must be justified in advance). Commit
   it BEFORE running the test. **The bar never moves afterwards.**
2. **Positive control.** Plant a known edge of a stated size and show the
   harness detects it. A harness that cannot see a planted effect cannot report
   a null. Measure `edge / sd`, never `(mean + edge) / sd`.
3. **Minimum detectable effect.** Report `bar × SE` alongside the result. If
   the observed effect is smaller than the MDE, the answer is **UNDERPOWERED,
   not refuted** — say so in exactly those terms.
4. **Placebo.** Re-run on random dates/windows/labels. If the placebo
   reproduces a material share of the effect (one prior test reproduced 76%),
   the effect is a company-type or regime artefact, not a timing signal.
5. **Clustered resampling.** Bootstrap by NAME and by SESSION, not by row.
   605 events came from 184 names; treating rows as independent understates
   every interval.
6. **Out-of-sample and walk-forward.** No parameter may be chosen on the data
   it is then scored on. State the split before fitting.
7. **Four quarters, both markets.** A result that holds in one window or one
   market is a window artefact. This is the standing adoption bar and it has
   killed several otherwise attractive results.
8. **Verify the data you got, not the data you asked for.** Assert daily
   granularity on every price series; count and report what you reject. This
   single class of defect shipped a wrong number into four live reports.
9. **Sanity-gate every published number** through `sanity.py` before it prints.
10. **Register every new constant** in `constants.py` with its provenance
    (MEASURED with a named re-derivation script / CITED / DESIGN), and write
    the script that re-derives it. A measured number with no script is a claim,
    not a measurement.

---

## 5. WHERE TO GO DEEPER — THE RESEARCH PROGRAM

Do these as separate, individually pre-registered studies. Report each as
ADOPTED / REJECTED / UNDERPOWERED with its MDE. Expect most to be rejected.

**5a. Intraday (9:46 entry → 15:59 exit).** The direction call is measured at
zero and further feature engineering on `r0`/`gap`/`vp` is refuted — do not
re-litigate it without new information. The unexplored surface is:
- **Selection, not prediction.** The engine currently emits a pair every
  session. Test whether an ABSTENTION rule — trade only when some pre-declared
  condition holds, stand down otherwise — produces a higher hit rate on the
  subset it does trade, and whether that subset is large enough to matter.
  Post-hoc subset-hunting is the classic overfit here, so the condition must be
  named and pre-registered before it is measured.
- **Cost-aware sizing and name selection.** Spread is a certain cost against a
  zero edge. Ranking candidates by expected cost rather than by density is a
  VARIANCE and COST improvement that does not require an edge to be real — the
  three adopted changes were all of this type, and this is the most promising
  family.
- **Exit timing.** 15:59 is an assumption, not a finding. Test alternative
  exits (time-stopped, volatility-scaled) with the same protocol.
- **The tide.** Test whether enforcing tighter long/short balance reduces
  variance without touching the hit rate.
- **New information, not new models.** The one thing that has ever moved this
  problem is a genuinely new input. Candidates already in the repo:
  `data/insider_buys.csv.gz`, 8-K filings, AdCom votes, earnings dates. Each
  needs a look-ahead audit (key on FILING date, never transaction date).

**5b. Pharma / catalyst.** This is where the measured effects actually live —
the CRL leg separates at t=−6.83, the approval leg at t=+2.61 (below the bar).
Priorities:
- **Fix coverage first.** Roughly half of scheduled decisions are currently
  unpriceable (bad or missing option quotes) and one has no resolvable ticker
  at all. Coverage is worth more than a new signal; an opportunity you cannot
  price is an opportunity you do not have.
- **Resolve the P(rejection) contradiction.** `BASE_RATE_FIRST_CYCLE = 0.70`
  (CITED, implies 30%) and the measured 11.7% [8.5%, 15.9%] both reach the
  reader today. They describe different populations. Measure the announcement
  bias directly (do companies announce CRLs less readily than approvals?), and
  either produce one defensible number for the population the screen actually
  covers, or make the report state which applies where. **Do not average them.**
- **Fair value.** The tercile structure was withdrawn as underpowered; the
  single 2.45x multiple stands with [1.95, 3.00]. Widening the event sample is
  the only honest way to resolve the tercile question — the current MDE is
  1.09x against an observed 0.76x.
- **The long side.** Approval reaction is positive but below the bar. More data
  is the only route; do not lower the bar.

**5c. Weekly.** Treat as a new asset class, not an extension. Pre-register the
universe, the entry, the horizon, and the exit. Test against a matched random
holding of the same length in the same names — a weekly strategy that merely
captures drift is drift, not skill.

---

## 6. THE 09:46 PANE OF GLASS — ZERO ERRORS, ZERO FLUFF

`TZ=America/Toronto python brief.py` is the one command. Requirements:

- **It must never show an error to the PM.** Every failure is either recovered
  (retry) or converted into a stated, bounded consequence: which name, what is
  unavailable, what the PM should do instead. "Unpriceable" is an acceptable
  output; a traceback, a bare warning, or a silently missing section is not.
  Fail closed and SAY SO — never hide a failure to keep the page clean.
- **One screen.** Current output is ~45 lines and must not grow. Enforce it
  with tests on line count and column width, against a deliberately busy day.
- **Ordered by decision, not by topic.** BOOK → DO TODAY → OPPORTUNITIES →
  WATCH → RECORD. Anything that does not change what the PM does today belongs
  in `--full`.
- **Every actionable line carries the action**: side, ticker, size, limit, and
  what it costs to express. A headline that names a ticker without a side or a
  size is not an instruction.
- **The board published at 9:46 is the instruction.** Re-reads display the
  published board — names, sides and sizes — never a fresh computation.
- **Concision may drop DETAIL, never DOUBT.** Every caveat the long page
  carries must survive in a mark or a line. Collapse repetition; never
  collapse a warning out of existence.
- **The live record prints beside the advice, every time.** Never present a
  47% engine's pick as a prediction.
- Auto-score the previous session before printing the record. A record that
  requires a human to remember is not a record.

---

## 7. DEFINITION OF DONE

- Full test suite green, with new tests for every change and positive controls
  for every diagnostic.
- `python brief.py` completes with zero errors and zero tracebacks on a normal
  day, a holiday, a day with no qualifying pair, a day with a stale quote, and
  a day with the network refusing — all five exercised by tests.
- Every published number registered in `constants.py` with a working
  re-derivation script; `python constants.py` reports no unprovenanced
  measured values and no unexplained tensions.
- `STRATEGY.md` updated with every study: hypothesis, pre-registered bar,
  result, MDE, and verdict — including and especially the rejections.
- A written summary to the PM stating: what was cleaned up, what was tested,
  what was adopted, what was rejected, what is still underpowered, and **what
  the live accuracy is now versus 44/93 (47%) at the start** — with the honest
  statement that if nothing cleared the bar, nothing was adopted.

---

## 8. FORBIDDEN

Selecting a window, universe, or threshold after seeing results. Moving a
pre-registered bar. Reporting a null without a positive control. Reporting an
underpowered result as a refutation. Dropping a caveat to shorten the page.
Removing a rejection from `STRATEGY.md`. Presenting a backtest with no
out-of-sample split. Averaging two numbers that describe different populations.
Silently swallowing an exception. Carrying a position at cost when it cannot be
marked. Promising improved accuracy from the intraday direction engine, which
is measured at zero and expected to stay there.
