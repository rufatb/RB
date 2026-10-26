# Day-141 — a stop within reach, tested on the record (council lab item 1)

**Registered 2026-10-26, before any return in this test was computed.** It is
the history test of day-140 arm A's gate. Nothing here changes a live pick, a
size, the Top 2, a prompt or the email.

## Why

* **Day-140 arm A** judges, forward, whether a Top 2 pick whose own "wrong if"
  is within one normal day of the 09:45 entry beats one without. With about 60
  picks by its 40th session, it can see only a difference of about 1.5–1.9% a
  pick.
* **The day-117 replay was meant to answer it faster.** Its cache was in
  `.rb-state/replay` and the container reset of 2026-10-26 wiped it.
* **The committed record is the next-largest population.**
  `data/model_picks.csv` holds every desk pick since 2026-09-17, each with its
  own "wrong if", its 09:45 entry and its scored result.

## The population

* **The picks.** Every scored pick of the three desks that state levels
  (Claude, DeepSeek, Gemini), kinds `selected` and `nominated`, in sessions
  2026-09-17 → 2026-10-23. That is 172 picks over 21 sessions; 85 carry a
  level.
* **Left out:**
  * Jev's forced picks, which never carry a level, so the gate would only
    compare Jev with the others;
  * late picks, which are scored from a later entry;
  * the engine, the Top 2 rows and the shadows. Their positions are already
    in the population as desk picks.
* **2026-10-15 is left out of the primary test.** Its two out-of-reach
  shorts are the case that suggested the rule (day-135), so they are not
  evidence for it. It is reported beside the result.
* **The unit** is the desk pick, with its own level. A position two desks
  proposed counts twice, with the same outcome. Picks are clustered by
  session, so that is honest. The unique-position version is reported
  beside it.

## The gate (the open check's rule, day-135, unchanged)

* **KEPT** when `council_flash.reach(side, invalid_at, entry, atr_pct)` says
  the level is within `REACH_ATR` (1) normal day of the entry.
* **DROPPED** when there is no level, the level is out of reach, or the level
  is already crossed at the entry.
* **The entry** is the record's own (the 09:45 bar's close).
* **The ATR** is the brief's computation, `daily_technicals.from_series` (the
  mean true range of the last 14 sessions over the last close), on daily bars
  cut before the session. A pick whose ATR cannot be computed is excluded and
  counted.

## The measure and the bar

* **y** is the record's `r_pct`: the 09:45 bar's close to the close, signed
  to the side. Kept and dropped picks pay the same 0.13% round trip, so their
  difference is the same gross or net. The kept picks' net mean is reported.
* **The statistic** is the kept picks' mean minus the dropped picks' mean,
  with a session-clustered t (`fixpack.two_group`, day-140's).
* **PASS needs all of:**
  * a difference > 0 with t ≥ 3.0;
  * a placebo p < 0.01: the kept and dropped labels shuffled among the same
    picks, counts kept, 2,000 draws, seed 141. p is the share of draws at or
    above the real difference;
  * the same sign in both halves of the sessions, by date;
  * at least 10 picks in each group.
* **Otherwise:** a difference ≤ 0 is a FAIL; anything else is NULL (this
  history has no second look). Either is rejection #57.
* **Planted control** (house rule 10: `edge / sd`, never
  `(mean + edge) / sd`).
  * Each group is centred on zero by subtracting its own mean, 1.0% is added
    to every kept pick, and the test is re-run.
  * It must show at t ≥ 3, or the verdict is UNDERPOWERED rather than NULL.
  * The smallest detectable effect (80% power at t = 3) is reported.

## Reported beside the verdict (descriptive, never a verdict)

* the same test with 10-15 included;
* the unique-position version: a position is kept when any of its proposers'
  levels is within reach;
* by model, and by kind;
* the plain split: any level against none;
* how many picks were excluded for want of an ATR.

## What follows

* **PASS:** the reach gate goes to the owner as a proposed live remove-only
  rule for the Top 2, under its own registration. Day-140 arm A runs on
  unchanged either way.
* **FAIL or NULL:** rejection #57, recorded in `STRATEGY.md`. No rule.
* **The script** is `reach_history.py`. Its summary is
  `data/reach_day141.json`.
