# Day-148 — a council veto on Claude's picks: UNDERPOWERED, and the estimate points the wrong way (rejection #64)

Council lab item 11. Registered in `PREREGISTER_day148_veto.md` (2026-11-09)
before any two-objection split was computed; `council_veto.py` (484b4f6) was
committed before its one look on 2026-11-11 at 10:15 ET. Summary:
`data/veto_day148.json`. FMP five-minute bars only (cached in
`.rb-state/veto_day148_cache/`); no model call, no OpenRouter.

## The question

Do the council positions two or more members object to do worse, from the
09:45 price to the 15:55 close against XIU.TO, than the rest of the same
morning's table? If so, a remove-only veto on Claude's picks could be
proposed.

## The population

The 239 pinned positions over 23 sessions (10-05 → 10-21 from day-137's tables,
10-26 → 11-09 from the frozen reports); 106 with two or more objections. All
239 had bars: none left out.

## The registered result: UNDERPOWERED (rejection #64)

| | |
|---|---|
| D = rest − vetoed, mean of 23 session means | **−0.82%** |
| t over the session means | −2.28 |
| sign-flip placebo (seed 148) | upper p = 0.98, lower p = 0.016 |
| halves (date order) | −0.85%, −0.79% |
| vetoed positions' own mean of session means | +0.50% gross, +0.37% net of 0.13% |
| planted 1.0% on centred D | t = 2.80 (**not detected**) |
| smallest detectable effect (80% power) | 1.37% a session |

* **VETO_SORTS fails on every count:** D is negative, and the vetoed positions
  made money after costs.
* **OBJECTIONS_BACKWARDS is not met either:** t = −2.28 against −3, placebo
  p = 0.016 against 0.01. The halves agree in sign.
* **The control was not detected (t = 2.80 < 3)**, so the verdict is
  UNDERPOWERED, not NULL. The record can see only an effect above about 1.4%
  a session.

**In plain words:** the positions the council objected to did *better*, not
worse, by about 0.8% a session, in both halves and in both sources. The record
is too short to call that real, but it rules out the premise: a veto on this
record would have removed winners.

## Beside the verdict (descriptive, never a verdict)

| Split (flagged against the rest) | Sessions | Flagged | D = rest − flagged | t | Flagged mean |
|---|---:|---:|---:|---:|---:|
| ≥ 2 objections (the test) | 23 | 106 | −0.82% | −2.28 | — |
| ≥ 1 objection | 23 | 128 | −0.60% | −1.88 | +0.29% (71 right) |
| every member endorsed | 21 | 40 | +0.60% | +1.68 | −0.56% (19 right) |
| ≥ 2 objections, raw (not against XIU) | 23 | 106 | −0.94% | −2.25 | +0.54% |
| longs only | 19 | 48 | −0.36% | −0.81 | +0.24% |
| shorts only | 20 | 58 | −1.05% | −1.72 | +0.68% |
| day-137's tables (10-05 → 10-21) | 12 | 45 | −0.81% | −1.71 | +0.19% |
| frozen reports (10-26 → 11-09) | 11 | 61 | −0.82% | −1.45 | +0.70% |

* **Claude's own proposals:** 73, of which 19 vetoed. The vetoed averaged
  +0.73%; the rest −0.06%.
* **The printed Top 2 on the frozen sessions:** 13 picks, 4 with two or more
  objections: FTS.TO long (+0.62%), OVV.TO short (+3.11%), HUT.TO short
  (+1.69%), ENB.TO long (−0.35%). The 9 without averaged −0.62%.
* It is day-137's finding seen from the other side: positions every member
  endorsed did worst (now −0.56%, 19 of 40 right), and the ones they argued
  against did best.

## What follows

* **Rejection #64.** Nothing changes. No veto is proposed, and no rule is
  built on the reverse: the reverse is below the bar too.
* **The day-150 quality floor** (owner, 11-10) keeps a pick when two members
  endorse it. This record does not support endorsement as a sign of a better
  pick either. That is the owner's decision and is judged forward under its
  own registration; this result is told to the owner beside it.
* **Next lab item:** 9's history replay (the release on a US listing before
  the TSX open), then 12.

**Not claimed:** that objections predict anything. UNDERPOWERED means the
record cannot tell.
