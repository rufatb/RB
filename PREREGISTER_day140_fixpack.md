# Day-140 — the fix pack, in shadow

**Status: REGISTERED 2026-10-24, before the first shadow session
(2026-10-26).** The owner merged the draft (PR #19, after the day-138/139
review in issue #18) and its implementation branch, and asked for the fixes
below ("Fix it"). This text replaces the draft, whose wording is in git
history (04005cf). Nothing here changes a live pick, a size, the Top 2, a
prompt or the email.

## Why

* **The council's choice adds nothing over its own table** (day-137). The
  table averaged −0.31% a position and the picks −0.30%.
* **85% of the picks followed the name's last move.** Unanimous positions did
  worst (−1.09%, 6 of 17), but that is t = −0.55 by session: not evidence.
* **The sector decides most results.** On the picks, the sector fund's part
  averaged −0.54% and the stock's own part −0.15% (20 picks).
* **The Top 2 is never padded.** Since 10-01 it held no pick on 4 of 16 days
  and one pick on 5. What is forced is the nominations that feed the table.
* **On its record the live Top 2 is −0.54% a pick net** (23 picks,
  09:45 → close).
* **A stop out of reach is no stop** (day-135). On 10-15 the two shorts' "wrong
  if" levels sat 1.8 and 2.0 normal days (ATR) away, so nothing an ordinary
  day does could trip them. 10-21's SHORT CLS.TO had none at all.

## Arm A, judged: a pick needs a stop within reach

* **The population** is every live Top 2 pick as recorded (`top2/pick` in
  `data/model_picks.csv`, after the pass-over rules and the 09:46 check),
  from 2026-10-26.
* **The gate.** A pick is KEPT when its own "wrong if" (`invalid_at`) is
  within `council_flash.REACH_ATR` (1) normal day of the 09:45 entry:
  `council_flash.reach(side, invalid_at, entry, atr_pct)` gives
  `out_of_reach` False. The ATR is the morning brief's `atr_pct`, the rows
  every model read. A pick with no level, or with one out of reach, is
  DROPPED. It is the open check's own rule (day-135), unchanged and untuned.
  Everything it reads is known at 09:46.
* **The measure** is the record's own `r_pct` (the 09:45 bar's close to the
  session's close, signed to the side). Kept and dropped picks pay the same
  0.13% round trip, so their difference is the same gross or net.
* **The question:** are the dropped picks worse than the kept ones? A rule
  that drops picks at random also saves 0.13% each, so a saved cost is not
  evidence. The gate has to drop worse picks.
* **Known asymmetry.** A pick whose level the 09:46 mark had already crossed
  was voided (E1) and never reached the record; a pick with no level cannot
  be voided. The test is on the record as it stands, which is the population
  a live rule would act on.

## Arm B, judged: Round 1 against the deliberated council

* **Round 1** is the two blind ballots, DeepSeek's and Gemini's, cast before
  any member reads another. Claude and Jev ballot only after reading Round 1,
  so they have no blind ballot.
* **The Round-1 picks** come from `council.tally`, the frozen rule, over the
  two Round-1 ballots alone. A position needs both to endorse it and neither
  to oppose. At most two, in tally order, never padded.
* **The deliberated picks** are the council's own `picks`, taken BEFORE the
  live pass-over rules and the 09:46 check, so the comparison isolates the
  discussion.
* **The measure:** both arms' picks are positions on the morning's table, and
  every table position is recorded and scored on the record's yardstick
  (day-137 M1). On each session where both arms hold at least one scored
  pick, d = the deliberated picks' mean minus the Round-1 picks' mean. When
  both arms hold the same picks, d = 0.

## Recorded every day, never judged

* **The sector cap.** It counts how often the live Top 2 held two picks on one
  side in one sector fund (`exposure.position_exposure`'s `etf`), and what
  the second did. It is not judged:
  * it rarely binds (10-15's two shorts were in different funds);
  * the nearest tested rules failed: one position per side (#51) and the
    sector-fund hedge (day-130);
  * the execution lab already records each pick's hedged result.
* **No new ranking.** The draft's implementation broke ties on the size of
  the stock's move against its sector. That favours the last-move habit
  day-137 found leaning negative (t = −2.75), so it is gone.
* **Whether a pick had a dated catalyst:**
  * earnings within 0–5 sessions (the brief's `days_to_earnings`);
  * an issuer release in the morning's wire window (`newswire.window`, the
    archive).

  It is not part of the gate. Every catalyst tested here was priced by the
  open (#45, #46, #50, #56, day-125), and requiring one would leave almost
  nothing to judge.
* **The plain split:** picks with any level against picks with none. In the
  council era only 2 of 17 lacked one, so as a gate it would hardly bind.

## The bar

* **Each arm is decided at its 40th qualifying session.** For arm A that is a
  session with a scored live pick and a known gate. For arm B it is a session
  where both arms hold a scored pick. At about 75% of sessions holding a
  pick, arm A's 40th falls around mid-January 2027.
* **Arm A PASS needs all of:**
  * the kept picks' mean minus the dropped picks' mean > 0, with a
    session-clustered t ≥ 3.0 (each pick in its session's cluster);
  * a placebo p < 0.01: the kept and dropped labels shuffled among the same
    picks (the counts kept), 2,000 draws, seed 140. p is the share of draws
    at or above the real difference;
  * the same sign in the first and the last 20 sessions (40 at the final
    look);
  * at least 10 picks in each group.
* **Arm B is two-sided:** either direction is a result. It needs all of:
  * the mean of d with |t| ≥ 3.0 across sessions;
  * a sign-flip placebo p < 0.01 (2,000 draws, seed 140; p is the share of
    draws whose |mean| is at or above the real |mean|);
  * the same sign in both halves.

  d > 0 says the discussion adds; d < 0 says Round 1 alone chose better.
* **Otherwise:**
  * arm A with a difference ≤ 0 is a FAIL;
  * anything else short of the bar is UNDERPOWERED and runs on to the 80th
    session for one final look at the same bar. After that it is retired
    as a rejection, and arm B is NULL.
* **Power, said plainly.** A Top 2 pick's sd is 1.57%. With about 63 picks
  at 40 sessions, arm A can detect only a difference of about 1.5% a pick
  (split half and half) to 1.9% (four to one). Only a large effect can pass.
  The registered history test of the same gate is the better instrument; it
  is the first item in `COUNCIL_LAB.md`. Arm B's power depends on how often
  the arms differ, and is reported at its first look.
* **Adoption.** A passing arm is proposed to the owner as a live rule under
  its own registration. Arm A's rule would be remove-only. The live council,
  its prompts and its rules are untouched by this test.
* **Nothing is tuned in between:** no gate, threshold, window or ranking.
* **Desk weighting is out of scope.** No desk's record is beyond |t| = 1.1,
  so weights now would weight noise. A weighting is a separate registration
  that names its window and weights in advance.

## How it runs

* **In the evening.** `daily_review.py`, already in the 16:20 job, calls
  `fixpack.record_session`. It records each session's decisions from the
  frozen publication and the morning's brief into `data/reviews/fixpack.csv`,
  which the evening push already carries.
  * The ledger holds decisions only.
  * Outcomes come from `data/model_picks.csv` when the record is read, so
    there is one ledger of outcomes.
  * A rerun only fills blanks.
* **Nothing runs in the morning.** No step is in `morning_full.sh`. The
  council's own staging only adds a timestamped copy of the Round-1 ballots
  (`round1.json`), and a failure there is noted in the council's errors; it
  never stops the council.
* **The decision:** `fixpack.verdict()` (`python fixpack.py --verdict`)
  computes it exactly as above, and `fixpack.line()` prints the running
  record in the evening review.
* **Before the test (descriptive, never part of it):**
  `python fixpack.py --backfill .rb-state/reports.sqlite3` records the
  councils of 10-05 → 10-23 as period `before`.

## What changed from the draft, and why

1. **Abstention is judged on kept against dropped live picks.** The draft
   compared a shadow that scores 0 on the days it stands aside with the live
   Top 2. Scored that way, the live Top 2's losses would pass any rule that
   trades rarely.
2. **Each arm needs t ≥ 3 and a placebo,** as every adoption here has. The
   draft had a paired t ≥ 2 with none.
3. **The gate is a stop within reach**, the open check's rule. The dated
   catalyst is recorded beside it.
4. **One basis: the record's 09:45 → close.** The live arm's figures are
   then the scoreboard's. The draft said the live board scores open → close;
   it does not.
5. **The live arm is the recorded Top 2,** not the council's raw picks.
6. **The sector cap is recorded, not judged, and no ranking is added.**
7. **Round 1 is stated as two members.**
8. **Four defects in the first implementation are fixed:**
   * it read the sector map's entries as labels; they are dicts, so the first
     gated position would have raised;
   * its two ledgers were in no push list, so they would never have been
     committed, and every morning's provenance check would have read NOT
     CLEAN;
   * its morning step ran on a fixed timeout in the staging window;
   * its Round-1 copy could fail the live council.

## What follows

* A passing arm goes to the owner with its record and goes live only under
  its own registration.
* Whatever the shadow shows, the live council is unchanged by this test.
