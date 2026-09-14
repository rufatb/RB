# Day-100: review of `kimi/day95-record-integrity`, and the DeepSeek credential

Two jobs, both prompted by four consecutive unrecorded sessions (2026-09-09,
09-10, 09-11, 09-14) and by `provenance.py` reporting NOT CLEAN.

---

## 1. The branch is NOT mergeable. Its best idea is, and is now ported.

`origin/kimi/day95-record-integrity`, 17 commits, +1862/−215 across 21 files.

### Why it cannot be merged as-is

Its merge base is `3935984` (PR #4). Main has since taken PRs #5–#12, including
the day-97 scheduler fixes, day-98 and day-99. Three consequences, each fatal
on its own:

1. **It would resurrect `adapters.py`.** The branch predates day-99's
   conversion of that module into the `adapters/` package. Main deletes the
   file; the branch still carries it. A merge brings it back and puts a module
   and a package of the same name in the same tree.
2. **Its `CLAUDE.md` destroys thirteen sections of ours** — including *House
   rules, learned the hard way* (the numbered ten), *Read-only, always*, *Pairs
   trading was REJECTED (#41)*, *Is main everything?*, and both day-98
   sections — replacing them with the pre-day-90 `House rules / Commands /
   Architecture` structure. The commit message says it "keeps main's Day-95
   section", and that is true only relative to *its* eight-PR-old main.
3. **It rewrites `morning.sh`, `brief.py`, `daily_job.py`, `deliver_report.py`,
   `execution.py` and `r945.py`** — every one of which has moved substantially
   since its base.

### What is genuinely right in it, and verified independently

`ledger.missing_sessions` anchors on `max(dates)` — the ledger's LAST entry —
and walks forward. Reproduced on this repository's own ledger:

```
missing_sessions(rows, 2026-09-14)                     → ['2026-09-09','2026-09-10','2026-09-11']
missing_sessions(rows + [{'date':'2026-09-11'}], ...)  → []
```

An interior hole is visible only while the record ends at the hole. The instant
any later session publishes, the anchor jumps past it and the warning goes
silent **exactly when the record starts looking healthy again**. That is a real
defect and the diagnosis is Kimi's.

**PORTED** (`ledger.record_gaps`, `ledger.load_prints`, `ledger.record_gap_line`,
wired through `brief._compute` into both renderers, 16 tests, mutation-checked):

- anchored on today, walking backward, so interior gaps persist;
- print-aware, so it separates *the run never happened* (`missing`) from *the
  run happened and picked nothing* (`zero_pick`) — the second is a result, not
  a gap, and is reported without an alarm;
- surfaced **beside the hit rate in the email**, not in a diagnostics appendix.
  A 48.6% computed over a record with holes in it is a rate over what survived,
  and the reader cannot discount it without being told. It was already
  computable before this; it never reached the inbox, which is the only place
  it gets read at 09:46;
- wrapped so a failure costs the line and not the morning. This protects the
  RECORD, not the bet — the opposite trade from the coverage guards.

### What is DELIBERATELY NOT ported

**C1, the four-minute publication window** (`PUBLISH_WINDOW_MINUTES = 4`,
`in_publish_window`, `eligible=True` for 09:47–09:50). Its motive is sound and
its evidence is real — 2026-09-09 was emailed, went 1/4, and was never
recorded. But it sets `eligible=True`, and `eligible` is what licenses a *fresh
morning entry claim*. Three objections:

- a leg "entered" at 09:49 is not a leg entered at 09:46, and the board prints
  09:46 prices beside it;
- it contradicts day-99's `deepseek_factors.exact_spread`, which hard-requires
  `'%H:%M' == '09:46'` at BOTH the quote and the clock. Under C1 a 09:48 run is
  eligible while every leg fails exact-spread — eligible rows with no cost
  evidence, which is the shape of the problem, not the fix;
- the diagnosed failure was *the miss was frozen and never recorded*. That is
  fixed by recording the miss, which is C2/C3. Widening the entry window is a
  separate change that needs its own argument, and loosening an execution
  contract to make a missed run look on-time is the wrong direction.

**C2's `send_report` unfrozen-alarm path.** The NOT RECORDED email is sent with
no Store row, so `claim_delivery` cannot apply and a re-run sends again. The
branch acknowledges this ("a duplicate alarm email is acceptable; a silent
unrecorded day is not") and the trade is defensible — but it bypasses the
day-97 idempotency design wholesale, and on a unit with `Restart=` it is an
email loop. Not adopted without a bounded-retry design.

**H1/H2 (`shadow_vp.py`, `validate_residual.py`).** Registered shadow research,
honestly marked BLOCKED-in-sandbox. No adoption question arises. Left on the
branch; it is preserved there, not lost.

`origin/kimi/day98-eodhd-lab` — not reviewed this session. Two documents,
`AUDIT_day98_eodhd_entitlement.md` and `LAB_day98_kimi.md`, plus the same stale
`adapters.py`. Same base problem.

---

## 2. DeepSeek credential — installed and verified live

Key at `${RB_STATE_DIR}/secrets/deepseek_api_key`, mode 0600; model at
`${RB_STATE_DIR}/deepseek_model.txt`. Both gitignored (`.gitignore:32`,
`.rb-state/`); a tracked-file grep for the key returns nothing.

Account `/models` returned exactly:

```
['deepseek-flash', 'deepseek-v4-pro']
```

**`deepseek-chat` — the code default — is absent.** The explicit
`deepseek-flash` setting is required, not a preference; there is no automatic
fallback and an unset model fails preparation every morning.

A live probe through the real `adapters.deepseek_adapter.evaluate_batch` path
on clearly-labelled synthetic evidence:

```
status: READY   model sent: deepseek-flash   model served: deepseek-flash
TRP.TO  NO_EDGE  0.0
ENB.TO  NO_EDGE  0.0
```

This verifies **credentials, model access, JSON-mode handling and schema
parsing only**. It is not market-data coverage, not entitlement to anything
else, and not evidence of accuracy. Returning NO_EDGE on deliberately vague
evidence is the correct answer and is mildly reassuring about confabulation; it
is not a result.

`prepare_deepseek.prepare` correctly refuses at or after 09:30 ET, so a full
preparation could not be run this session (13:52 ET). The first real snapshot
is `rb-deepseek.timer` at 09:15, once the host is installed.

**Nothing here is adopted.** No factor output selects, sizes, or ranks into the
baseline board, and no accuracy gain is claimed or implied.
