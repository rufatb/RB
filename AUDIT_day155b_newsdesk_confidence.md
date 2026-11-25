# AUDIT day-155b — the news desk's top two by its own score: NULL (rejections #71, #72)

Registered 2026-11-24 at about 22:30 ET (`PREREGISTER_day155b_newsdesk_confidence.md`,
533672f). Run once the same night by `python newsdesk_confidence.py` (a7b3d5b,
committed before it ran). Summary: `data/newsdesk_confidence_day155b.json`.
The committed ledger only, 2.7 s, no cost.

## The question

The owner, after 11-24: which of the morning's calls are "actually tested to
be the most correct … maybe the top two news desk picks that will have a
highest score".
* The email orders the news desk's calls by material first, then the model's
  own confidence, then ticker. So the top two by score are its first two rows.
* **The population:** the FULL arm (what the email prints), 2026-10-02 →
  2026-11-24.
  * 221 calls over 35 sessions; 208 scored.
  * 32 sessions had a scored top-two call and a scored other call.
* **The outcome:** `w945`, side × (the name's 09:45 → close minus XIU's).

## Results

**H1, the top two against the rest of the morning: NULL** (rejection #71).

| Leg | Bar | Value | Met |
|---|---|---:|---|
| Top two minus the rest, mean a session | > 0 with t ≥ 3 | **+0.56%**, t = **1.93** | no |
| Placebo (sign flip, upper) | p < 0.01 | 0.033 | no |
| Halves | both > 0 | +0.63%, +0.50% | yes |
| The top two's own mean | above 0.13% | +0.60% (net +0.47%) | yes |
| Planted 1.0% | t ≥ 3 | 3.43 | yes: powered |
| Smallest detectable difference (80%) | printed | 1.12% | |

* The top two: 59 calls, 35 right (59%), +0.60% a call.
* The rest: 144 calls, 68 right (47%), −0.01%.

**H2, material against routine: NULL** (rejection #72).

| Leg | Bar | Value | Met |
|---|---|---:|---|
| Material minus routine, clustered | > 0 with t ≥ 3 | **+0.75%**, t = **2.88** | no |
| Placebo (label shuffle) | p < 0.01 | 0.005 | yes |
| Halves | both > 0 | +0.62%, +1.00% | yes |
| Groups | ≥ 10 each | 124 and 84 | yes |
| The material calls' own mean | above 0.13% | +0.45% (net +0.32%) | yes |
| Planted 1.0% | t ≥ 3 | 3.86 | yes: powered |

* Material: 124 calls, +0.45% a call. Routine: 84 calls, −0.29%.
* It misses the bar on t alone: 2.88 against 3. **The bar does not move.**

## Beside the verdicts, never judged

* **Confidence, 09:45 → close against XIU** (Spearman 0.17):

  | Confidence | Calls | Right | Mean |
  |---|---:|---:|---:|
  | ≥ 0.65 | 44 | 25 | +0.70% |
  | 0.60–0.64 | 61 | 36 | +0.52% |
  | 0.55–0.59 | 59 | 25 | −0.37% |
  | below 0.55 | 44 | 20 | −0.22% |

* **The replay disagrees.** On the 419 releases of July → October 1, the same
  prompt's confidence ≥ 0.6 made +0.06% a call (t = 0.34), and material calls
  +0.04%, no better than the whole (`AUDIT_day122_releases.md`). The live lean
  comes from 35 sessions, and the replay from 63 sessions, earlier.
* **Raw, unhedged** (the way the owner trades them):
  * the top two minus the rest +0.47% a session, t = 1.56;
  * material +0.50% a call (75 of 124 right), routine −0.01%.
* **The pre-open arm** (asked at 09:20, open → close against XIU, 18
  sessions):
  * top two minus the rest +1.47%, t = 2.33;
  * routine −0.58%; confidence below 0.55 −1.77% (19 calls, t = −2.2).
* **The title-only arm:** top two minus the rest +0.29%, t = 1.10.
* **When the full read and the title-only read take opposite sides** (the
  email's "From the title alone" column), the full read was right 26 of 59
  (44%, +0.04%). When they agree it was right 80 of 149 (54%, +0.20%).
* **The market does not explain the news desk.**
  * 64% of its calls are LONG.
  * Yet its daily result has no relation to XIU's own 09:45 → close
    (correlation −0.03 over 35 sessions).
  * Its raw result was +0.19% a call on sessions XIU rose after 09:45, and
    +0.13% on sessions it fell.
* **11-24 itself:**
  * the top two, GIB-A.TO (−0.43%) and CM.TO (+0.42%), averaged 0.00%;
  * the rest averaged −0.47%: JWEL.TO +0.37%, SCR.TO −1.01%, DOL.TO short
    +0.28%, TOY.TO (routine) −1.50%.

## What it says

* **On the live record so far,** the news desk's higher-ranked calls and the
  ones it marks material have done better than the rest. Each lean holds in
  both halves.
* **Neither clears the bar, and the earlier replay showed neither.** With six
  descriptive rows and two hypotheses, leans this size are within what chance
  gives.
* So the record does not show that the top two, or the material calls, are
  more accurate. It shows that they might be, and a fresh sample can decide.

## What changes

* **Nothing is selected by score.** The email already lists the highest scores
  first.
* **The owner is told the numbers as they are,** and the email's news desk
  section now prints them in one line each morning (display only; day-155b's
  clarity changes, CLAUDE.md).
* **Forward:** amendment 1 of the registration judges H1 and H2 again on
  sessions from 2026-11-25 only, with the same bar, at the 60th new session.
  Nothing live changes before then.

## Not blind, said plainly

The scoreboard total, the replay's splits and 11-24's six calls were known
before the registration, as it says. No other split was computed before the
run.

## Not claimed

That any news desk call, top two or otherwise, is right more often. Say so
plainly when asked.
