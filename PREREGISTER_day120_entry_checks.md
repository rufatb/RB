# PREREGISTER day-120 — two entry checks on the Top 2 and the debate's final

Registered 2026-09-29 (evening), BEFORE any session has run with the rules.
The owner said "do it all and make it ready for tomorrow's report" after the
2026-09-29 evening review offered these two rules.

## The rules (live from 2026-09-30)

Both rules are applied at 09:46, when the quotes exist. They apply to the Top 2
(`top_picks.select`) and to Part 5's final (`debate.entry_filter`) only. The
three desks, the engine, Parts 2–4 and every recorded desk row are UNCHANGED.

**E1 — void at entry.** A pick has a "wrong if" level (`invalid_at`) from the
model that proposed it. If the 09:46 mark (the validated quote's mid, status
OK or CORROBORATED) is already past that level, the pick has failed by its own
stated terms before it can be entered:
* a LONG with mark < level;
* a SHORT with mark > level.

Without a usable quote, or without a level, the check is NOT CHECKED and the
pick stands. A missing quote is never read as a pass or a fail.

**E2 — conflict.** A name the models put on opposite sides the same morning is
not a pick; long and short together net to zero before costs.
* The Top 2 already excluded it (day-119: SPLIT, last).
* The debate now drops a final whose name was PROPOSED on both sides.

## What happens to a flagged pick

* **Top 2:** a VOID AT ENTRY pick sorts after every clean candidate, the way a
  SPLIT one does. The Top 2 stays at two whenever two names exist (the owner's
  rule). A void pick that must still fill a slot says VOID AT ENTRY in capitals.
* **Debate:** a flagged final is removed and listed under "Dropped at entry"
  with its reason. The debate is never padded (day-119c), so it may finalize
  fewer names.

## What this claims, and what it does not

These are CONSISTENCY rules, not signals. E1 honours the model's own
invalidation; E2 is arithmetic. Neither is claimed to raise accuracy.

The 59-session replay (2026-09-29, 649 picks) found:
* a "wrong if" already crossed at entry: 47% right, against 49% otherwise;
* no measured difference either way.

## The forward test

Population: every Claude and DeepSeek desk pick in `data/model_picks.csv` from
2026-09-30. Desks are unaffected, so every flagged pick is still recorded and
scored. The groups are:
* E1 — crossed at the 09:45 entry, against not crossed. Picks without a level
  are excluded.
* E2 — names on both sides, against the rest.

The evening review (`daily_review.py`) prints both splits every day.

**Decision at 40 sessions (~2026-11-24):**
* If the dropped group beats the kept group at a session-clustered t ≥ 3.0, the
  rule is costing money and is withdrawn.
* Otherwise it stays. Its lack of accuracy gain is expected, and says nothing
  against it.

The bar does not move and the rules are not re-tuned against this record.

Top 2 rows are recorded with `prompt_version = day120-entry`. Debate finals get
`day119-debate-v1+day120-entry`. Rows before 2026-09-30 carry the old rules.
