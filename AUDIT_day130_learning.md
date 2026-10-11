# AUDIT day-130 — what last week's picks teach, and what to build

2026-10-11. The owner asked for:
* an analysis of last week's picks and how they were picked and executed;
* new ways to make the picks and the council better and more live;
* a step-by-step plan that cannot break the stable system.

Every test below was registered first, in `PREREGISTER_day130_learning.md`
(9742583, amendments c73c52f and 2163980).

## 1. Last week (10-05 to 10-09), as executed

**Top 2: 3 right of 7, mean −0.17% per pick** (09:45 → close).

| Day | Pick | Result | What drove it |
|---|---|---:|---|
| 10-05 | LONG TECK-B.TO | +0.89% | morning move; gave back 0.52% after noon |
| 10-05 | SHORT CVE.TO | −2.21% | the open was already 0.99% against it; oil rallied |
| 10-06 | SHORT CVE.TO | −0.17% | moved with XEG; vs its sector +1.03% |
| 10-07 | LONG CCO.TO | −1.33% | gapped −2.06%; it was a uranium bet |
| 10-07 | SHORT EMA.TO | +0.64% | |
| 10-08 | SHORT TD.TO | −0.41% | the buyback approval came after the close |
| 10-09 | LONG TD.TO | +1.37% | the same name, the other side |

Desk picks that week: 44 rows, 34% right, −0.05% per pick. Nothing
distinguishes them from a coin flip.

The losses had one shape: **sector and macro bets.** CVE.TO (oil) and
CCO.TO (uranium) moved with their sector. The council reads WTI and the macro
block, and four models then agreed on the same macro story.

## 2. The same picks, executed other ways

The execution lab (`execution_lab.py`) re-ran each pick under other rules:
* the replay: 379 picks over 59 sessions, the production pool, the live
  prompts' answers;
* the live record: 93 model picks from 09-17 to 10-09.

| Rule | Replay: vs scored | Replay: sd | Live: vs scored | Verdict (H3 bar) |
|---|---:|---:|---:|---|
| As scored, 09:45 → close (mean −0.04%) | — | 1.69 | — | coin flip |
| **Exit at noon** | **+0.08%** | **1.43** | +0.03% | **passes everywhere** |
| Stop at its own "wrong if" | +0.02% | 1.38 | −0.16% | mixed |
| Stop at 0.5 ATR | +0.05% | 1.48 | −0.10% (t −2.9) | fails live |
| Hold to the next close | −0.25% | 2.87 | −0.34% | worse |
| Hold 3 sessions | −0.68% vs XIU (t −2.2) | 4.36 | | worse |

The afternoon (12:00 → close) lost 0.08% in the replay (t −1.7). The picks'
little movement, when there is any, comes in the morning.

## 3. The registered tests

| Test | Result | Verdict |
|---|---|---|
| H1 weekly reversal (2 years, 117 names) | gross +0.03% per week, net −0.37%, placebo p 0.40 | **fail** (MDE 0.68%) |
| H2 hedge with the sector ETF | replay: swing −18% but mean −0.11%; live: mean +0.25%, swing −6% | **fail** both bars |
| H3 noon exit | no worse, swing −15% (replay), −15% (Top 2) | **pass**: shown, never applied |
| H3 "wrong if" and ATR stops | mixed or worse live | fail |
| H4 live intraday news | 37 releases on pool names in 3 months, mostly routine | **not testable** |
| H5 first half hour → last half hour | +0.0002% over 6,511 name-days | **fail** |
| H6 intraday drift | +0.08% a session (up, not down) | **fail** |
| H7 learn which picks to trust | out-of-sample AUC 0.44, placebo p 0.85 | **fail** |
| H8 size by 1/ATR | session swing −11.7% (bar 15%) | **fail** |

Summaries: `data/replay_day130_{reversal,intraday,metalabel,exits}.json`.

**What this says.** Public pre-open information, read by any model or
reduced to any simple quant rule, does not predict the 09:45 → close move in
this pool. Day-117 found the same. The one improvement that survives is about
risk, not accuracy: the afternoon adds variance and nothing else. No rule here
raises accuracy, and none is claimed.

## 4. What was built (none of it changes a pick)

1. **The execution lab** (`execution_lab.py`). Every evening, inside
   `daily_review.py` (which the 16:20 job already runs, so no Routine
   changes), it measures every scored pick under ten rules:
   * the open entry, the noon exit;
   * the "wrong if" stop and two ATR stops;
   * the sector-ETF hedge;
   * holds of 1, 3 and 5 sessions.

   It writes `data/reviews/execution_lab.csv` and appends the comparison to
   the review. It is the system learning from its results, in the open, at
   the registered bar.
2. **The exit note.** One line under the council's picks (flash, email,
   page), quoting H3. Display only.
3. **The noon check** (`noon_check.py`, tested). At 12:00 ET it sends one
   email with each council pick's move since 09:45, whether its "wrong if" was
   crossed, and its sector ETF's move. **It is not switched on:** that needs a
   new 12:00 Routine, which is the owner's decision.

## 5. The plan, step by step

Each step is shadow-first. The live picks and the record stay exactly as they
are until a step clears its bar and the owner says yes.

1. **Now:** the lab runs every evening. Nothing to decide.
2. **The owner's yes:** a 12:00 ET Routine in the owner's session runs the
   noon check and emails it. Existing Routines are untouched.
3. **Two to four weeks, shadow:** a council with memory. A second council
   runs in parallel and does not decide anything. It gets a factual box:
   * the last five sessions' Top 2 and how each ended;
   * each position's sector ETF and beta ("SHORT CVE.TO is a crude-oil bet,
     β 1.1");
   * the lab's table.

   The aim is fewer stacked macro bets and stale theses (CVE.TO twice, TD.TO
   flipped). It needs a planted control first, and it ships only if its picks
   do no worse than the live council over 20 sessions.
4. **Next registered test, new information:** report-day drift. On
   an earnings day, does the 09:30 → 10:00 reaction predict 10:00 → close? FMP
   has the report dates and 5-minute bars back to 2024, about 600 sessions.
   This is the one place where information arrives that the open has not
   fully priced.
5. **~2026-11-30 (40 sessions):** the decision point.
   * the council against the counted shadow;
   * whether the nominations helped;
   * every lab rule at its bar.

   Anything that passes can be promoted, by the owner.

**Not to rebuild** (failed here): a weekly-reversal sleeve, intraday
momentum, a pick filter learnt from the record, ATR stops, holding overnight,
volatility sizing.
