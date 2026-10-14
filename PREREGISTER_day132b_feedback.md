# Day-132b — an outside read of the scoreboard, tested (owner, 2026-10-14)

Registered BEFORE any of it was computed. The owner pasted a read of the 10-14
scoreboard and asked whether it holds and how the system can improve. Its
claims:

* **C1.** Every row is negative before costs; with spreads and borrow,
  −0.17% per pick is really −0.3% or worse — a slow bleed, not a coin flip.
* **C2.** The debate/consensus layer destroys signal: "Debate (final)" is 25%,
  the worst row. Test taking the highest-conviction single-desk pick instead.
* **C3.** Reacting to new information beats predicting from old: DeepSeek late
  (62%, +0.65%) and the wire-release picks.
* **C4.** Nine sessions prove nothing; keep it on paper until 60+.
* **C5.** Intraday TSX large caps from prior-day momentum is a picked-over
  edge. Day-132 (#47) already answered this: a powered null.
* **C6.** The likelier edge is the biotech catalyst table.

## Measurements (descriptive, no bar, never a rule)

* **M1, the market inside each row.** For every scored live pick
  (2026-09-17 → 2026-10-13), the row's raw mean is split into the market part
  (side × XIU 09:45 → close, from the day-132 FMP cache) and the rest, with
  each row's long/short mix.
* **M2, costs.** These are measured, not assumed:
  * the entry spreads recorded at 09:46 for sized legs in the stored
    publications (`.rb-state/reports.sqlite3`), plus the engine ledger's
    stored spreads;
  * a stated commission range;
  * what borrow costs a same-day short.

  Each row is restated net of the median measured round trip.
* **M3, council vs debate vs desks.** On the same sessions:
  * the council's Top 2 (10-05 →);
  * the debate final;
  * each desk;
  * the highest-confidence SELECTED desk pick of each session.

  Paired by session, with the MDE.
* **M4, late and wire picks.** Their records, intervals and sessions.
* **M5, power.** At the Top 2's measured sd: how many picks detect
  0.1 / 0.2 / 0.3% at t = 3, and the MDE80 at 40 and 60 sessions.
* **M6, biotech.**
  * The calls by side, events resolved, and the resolution schedule.
  * What earlier biotech research in `STRATEGY.md` found.
  * Why a historical replay of the calls would be contaminated.
* **M7, today's picks at midday.** Since 09:45, against XIU and against each
  pick's sector ETF.

## T1 — does a model's own confidence rank its picks? (registered test)

C2's remedy assumes conviction carries information. This tests it where the
data are deepest.

* **Population:** the four stored replay runs over the same 59 sessions
  (2026-07-06 → 2026-09-28):
  * DeepSeek flash (day-117, `.rb-state/replay/answers`);
  * v4-pro (day-119, `replay/v4pro`);
  * research and single-shot (day-126, `replay/research`).

  519 picks on 84 tickers, all in the day-132 bar cache.
* **Outcome:** the production yardstick, side × (09:45 bar close → close), in
  %, from FMP 15-minute bars. Against XIU is reported beside it.
* **Statistic:** for each (run, session) with at least two picks, the
  highest-confidence pick's outcome minus the mean of the others in that
  (run, session). The mean is taken over these units, clustered by session.
  Confidence ties are broken by order (longs first, as returned).
* **Bar:**
  * mean > 0 with t ≥ 3;
  * placebo p < 0.05, with confidences shuffled within each (run, session),
    2,000 draws, seed 132;
  * the planted control (+0.5% added to the top pick) must show at t ≥ 3,
    or the verdict is UNDERPOWERED.
* **Descriptive:** the session-clustered rank correlation of confidence with
  outcome, pooled and per run.
* **If it passes:** the remedy has support on replay, and a forward shadow
  ("highest-conviction single pick") may be registered.
* **If not:** conviction does not rank picks here, and the remedy is another
  draw from the same distribution.

## What follows

Nothing in the morning changes from this without the owner's decision. Any
change to a prompt, rule, section or the email needs its own registration and
control (day-127/128). The script is `feedback_review.py`; the summary goes to
`data/review_day132b_feedback.json`.

## Results (2026-10-14, after the run; nothing above was changed)

* **T1: UNDERPOWERED,** by the registered rule.
  * Over 154 units (479 picks), the top-confidence pick minus the rest is
    −0.20%, t = −1.14; placebo p = 0.91.
  * The planted 0.5% shows at t = 2.91.
  * Rank correlation −0.02 (95% −0.11 to +0.08).
  * The estimate is on the wrong side of the claim.
* **M1.** The books are near balanced, and the market's part of every row is
  about zero. Pooled unique model picks: −0.15%, t = −0.88.
* **M2.** Median 09:46 entry spread 9.2 bps; round trip 0.07–0.19%.
* **M3.** Over 10-05 → 10-13, the council's Top 2 went 4/9 at +0.02%. That
  is at or above every desk on the same sessions. The 25% row is Part 5's
  debate.
* **M4.** DeepSeek late: 8 picks on 2 sessions. The wire row: 2/5, −0.14%.
* **M5.** MDE80 0.41% at 40 sessions, 0.33% at 60.
* **M6.** 31 events, 1 resolved.

Read `AUDIT_day132b_feedback.md`. Nothing changes without the owner.
