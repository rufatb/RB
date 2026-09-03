# INVENTORY — every module, what it does, and whether it may be deleted

Built mechanically (AST import graph from `brief.py`, plus the test suite),
then annotated. Regenerate the graph portion any time; the verdicts are
judgement and must be re-made by hand.

## The headline finding, and it reverses the obvious cleanup

A reachability analysis says **23 of 70 modules are unreachable** from
`brief.py` and from the tests. Every single one of them is a **study harness
that encodes a rejection or a measured result**, and several are the only
thing that can re-derive a constant the live report prints today.

**None of them is dead code. Deleting them would erase the record**, which is
how a refuted claim comes back and gets re-adopted. `CLAUDE.md` rule: check
STRATEGY.md before proposing anything — that check is only possible because
these files still exist and still run.

They are classified **STUDY** below, not "orphan". The correct treatment is to
document them so nobody mistakes them for dead weight and nobody re-runs a
study that already returned a verdict.

## Tiers

| tier | count | lines | meaning |
|------|------:|------:|---------|
| LIVE  | 35 | 14,085 | reachable from `brief.py`; runs every morning |
| TEST  | 12 |  3,212 | exercised only by the test suite |
| STUDY | 23 |  3,885 | research harnesses; the reproducibility layer |


## Verified, not asserted: can the STUDY layer actually re-run?

The claim above — that these files are the reproducibility layer — is only
worth making if they still execute. Checked, and it was **false for four of
them**:

| harness | was | now |
|---|---|---|
| `paired_time`, `validate_universe` | `FileNotFoundError` on a scratchpad path belonging to a session that ended weeks ago | **BLOCKED**, with a message naming `TD_DATA_DIR` and saying the 5-minute cache was never committed |
| `validate_events`, `validate_events_bias` | `FileNotFoundError: daily.csv` | import cleanly; missing input names the rebuild command |

**The 5-minute bar cache is genuinely unrecoverable from this repository.** It
was never committed (large, paid feed), and the default path is an ephemeral
container directory. Those two studies are reproducible only against a rebuilt
cache, and now say so instead of emitting a bare traceback. That is a real hole
in the record and it is recorded here rather than papered over.

### A harvest that ran on import

`validate_events_build.py` executed its harvest at **module level**: importing
it fired 133 threaded HTTP requests and wrote a 38 MB CSV. The inventory pass
that imported every module to see which still load therefore triggered a full
ten-year download as a side effect — and produced `daily.csv` by accident,
which is how a dataset ends up in a repo with nobody able to state its
provenance. The harvest now lives in `build()` under `__main__`, and
`daily.csv` is gitignored as rebuildable.

Rule this generalises: **importing a module must never touch the network or
write a file.** Any module-level I/O is a defect regardless of whether it
currently works.

---

## LIVE — reachable from brief.py

Changes here reach the morning report. Every one needs a test.

| module | lines | what it is | imported by |
|---|---:|---|---|
| `adapters` | 750 | pluggable data layer. | `advice`, `backtest`, `brief`, `build_pool` +17 |
| `adcom` | 261 | FDA Advisory Committee meetings: scheduled ones, and how votes went. | `brief`, `validate_adcom` |
| `advice` | 192 | a record of what the SYSTEM said to do, so its advice can be scored. | `view` |
| `analyst` | 170 | optional Claude-powered analysis layer. | `dashboard` |
| `baserate` | 671 | P(CRL), the number every breakeven in this repo has been missing. | `advice`, `build_insider`, `constants`, `sanity` +5 |
| `brief` | 742 | the single morning page. One command, four layers, honest labels. | — |
| `build_catalyst` | 361 | a survivorship-free FDA catalyst dataset from FREE sources. | `brief`, `resolved` |
| `catalyst` | 273 | arithmetic guardrails for binary-event (PDUFA/AdCom) theses. | `brief`, `constants`, `sanity`, `screen` +1 |
| `catledger` | 204 | the scored record for catalyst trades. The thing that was missing. | `brief` |
| `classify` | 200 | is this 8-K ANNOUNCING the event, or merely mentioning it? | `build_catalyst`, `resolved` |
| `constants` | 411 | provenance for every published number, and a diff when one moves. | `brief`, `view` |
| `cost` | 216 | what the intraday pair costs to express, which nobody has ever measured. | `brief` |
| `dashboard` | 969 | Pre-Open Brief entry point. | `backtest`, `brief`, `confirm`, `earnings` +18 |
| `earnings` | 160 | the event risk the 9:45 engine is structurally blind to. | `brief` |
| `fairvalue` | 422 | what protection SHOULD cost, measured, per name. | `screen`, `validate_eventmult`, `view` |
| `fundamentals` | 172 | the balance sheet behind a catalyst, free from SEC XBRL. | `brief`, `screen` |
| `ledger` | 524 | the permanent learning record ("learn every single day"). | `brief`, `cost`, `r945`, `view` |
| `metrics` | 439 | all the real, timestamped measurements. | `backtest`, `dashboard`, `scan` |
| `newsflow` | 227 | what changed overnight, for the names you hold and are watching. | `brief` |
| `partners` | 202 | does this company OWN the application, or is it someone else's? | `pdufa`, `screen` |
| `patterns` | 388 | deep historical pattern mining over as much history as the data | `backtest`, `dashboard`, `midday`, `scan` |
| `pdufa` | 283 | a forward FDA decision calendar, built free from company filings. | `adcom`, `brief`, `validate_adcom` |
| `positions` | 217 | what you are actually holding, carried across days. | `brief` |
| `r945` | 1271 | the 9:45→close engine (run at/after 9:45 ET). | `brief`, `report_html`, `validate_deep`, `validate_entry` +9 |
| `report_html` | 379 | the visual 9:46 board. | `r945` |
| `resolved` | 215 | did the binary already settle, and which way? | `brief` |
| `risk` | 153 | risk-first sizing and cost math. | `dashboard`, `report` |
| `sanity` | 321 | hard bounds on every published number, asserted before it prints. | `brief`, `screen` |
| `screen` | 989 | catalyst OPPORTUNITIES, not just a calendar of dates. | `brief` |
| `sixk` | 203 | the one thing day-70 measured about the intraday universe. | `brief`, `resolved` |
| `validate_catalyst` | 390 | what FDA decisions actually do to a share price, and | `fairvalue`, `screen`, `validate_eventmult`, `validate_insider` +1 |
| `validate_ceiling` | 284 | is the ceiling the MODEL or the FEATURES? | `validate_catalyst`, `validate_features`, `validate_scaled` |
| `validate_exit` | 599 | is there a better exit than 15:59? (day-36) | `adcom`, `baserate`, `brief`, `build_catalyst` +20 |
| `validate_twins` | 274 | the deep validation, rebuilt FREE and 2x bigger (day-22). | `validate_entry`, `validate_exit` |
| `view` | 553 | the short page. One screen, ordered by what you have to decide. | `brief` |

## TEST — reached only by the test suite

Not on the morning path. Candidates for consolidation, NOT deletion: several are CLI entry points the PM may still invoke by hand.

| module | lines | what it is | imported by |
|---|---:|---|---|
| `backtest` | 301 | honest, lookahead-safe evaluation of the Pre-Open Brief. | — |
| `confirm` | 74 | "am I allowed to enter yet?" live trigger confirmation. | — |
| `hold` | 190 | mid-session hold-to-close check (conditional, from HERE). | `midday` |
| `midday` | 141 | gated from-NOW-to-close selection (run any time after ~10:00). | — |
| `report` | 325 | THE single 9:31 entry point. | — |
| `scan` | 563 | TSX opportunity scanner. | `midday`, `report` |
| `sentiment` | 110 | best-effort, HONEST headline sentiment (an optional lens). | `scan` |
| `validate_entry` | 270 | is 9:46 the right time to run the report? (day-39) | — |
| `validate_pool` | 312 | does a universe of HUNDREDS of names beat 21? (day-40) | — |
| `validate_runup` | 317 | is there a WEEK-to-MONTH trade before an FDA decision? | — |
| `validate_shape` | 275 | the SHAPE of the bet (day-38): how many picks, when to sit | — |
| `validate_sweep` | 334 | the holistic sweep (day-37). Every knob at once, plus the | — |

## STUDY — research harnesses (the record)

**Do not delete.** Each encodes a rejection, a measured constant, or a dataset build. Re-run to re-derive; read the docstring for the verdict.

| module | lines | what it is | imported by |
|---|---:|---|---|
| `build_insider` | 177 | open-market insider PURCHASES, from the SEC's bulk datasets. | — |
| `build_pool` | 149 | fetch the wide TSX universe once and cache its feature tables. | `build_rich` |
| `build_rich` | 221 | a WIDE feature panel from bars we already download for free. | — |
| `paired_time` | 43 | PAIRED test: 9:40 vs 9:45 decision. Where both times pick the SAME | — |
| `validate_adcom` | 199 | does an advisory-committee vote predict the FDA's decision? | — |
| `validate_deep` | 133 | the deep-data validation (day-13/14): ~1 year of 5-minute | `paired_time`, `validate_time_deep`, `validate_universe` |
| `validate_density` | 167 | does the DENSITY selector systematically pick the names | — |
| `validate_eventmult` | 269 | re-measure the event multiple, WITH per-tercile intervals. | — |
| `validate_events` | 94 | the day-32 event/swing-trade study. RESULT: NO EDGE FOUND. | — |
| `validate_events_bias` | 47 | Is the gap-down bounce REAL, or is it survivorship bias + market beta? | — |
| `validate_events_build` | 69 | Event-study dataset: 10 years of DAILY bars across a broad liquid US universe. | — |
| `validate_exdiv` | 167 | does the ex-dividend date poison the `gap` feature? | — |
| `validate_features` | 223 | do RICHER features, built from bars we already have, | `validate_density`, `validate_horizon`, `validate_scaled`, `validate_target` |
| `validate_horizon` | 212 | should each pick carry its OWN suggested hold length? | — |
| `validate_insider` | 262 | TEST A: does insider buying precede FDA outcomes? | — |
| `validate_pair` | 204 | the day-9 experiment behind THE PAIR's selection rule. | `paired_time`, `validate_deep`, `validate_time_deep`, `validate_universe` |
| `validate_priorcrl` | 152 | TEST B: is P(CRL) conditional on the sponsor's history? | — |
| `validate_scaled` | 161 | the four-quarter test on the ONE candidate still standing. | — |
| `validate_sixk` | 320 | does a company FILING something change the intraday leg? | — |
| `validate_target` | 209 | train on CROSS-SECTIONAL rank instead of absolute direction? | — |
| `validate_time` | 139 | is 9:45 the right decision time, or does another time | — |
| `validate_time_deep` | 133 | is 9:45 the right decision time? (YEAR data version) | `paired_time` |
| `validate_universe` | 135 | day-14: should the universe grow from 21 to 61 names? | — |
