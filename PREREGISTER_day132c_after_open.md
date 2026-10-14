# Day-132c phase 3 — ask after the open: does a model reading the first thirty minutes pick better? (owner, 2026-10-14)

Registered BEFORE it ran. The owner chose this from day-132b's list. It tests
the one untested piece of the outside read's claim C3: "reacting to new
information beats predicting from old."

Every earlier test of acting on the open was a RULE:
* #42, gap continuation;
* day-130 H5, first-half-hour momentum;
* #46, a report day's first half hour;
* day-121b, entering at the open.

No model has been ASKED after the open at scale; the live "late" picks are 2
sessions.

## Population and model

* **Sessions.** The 59 replay sessions (2026-07-06 → 2026-09-28), with their
  stored pools and macro (`.rb-state/replay/pools`). Those pools are the
  production pool builder's rows, cut off before each session.
* **Model.** DeepSeek v4-pro (production), through `council.ask_deepseek`
  (JSON mode, thinking disabled). It is asked once per arm per session.
* **Validation.** `nominations.clean`: the desks' `_clean`, `check_levels`,
  `check_basis`, and a name on both sides is dropped.

## The two arms (same sessions, same model, same forced question)

* **Arm A, before the open.** The prompt is `nominations.prompt()` unchanged:
  exactly two LONG and two SHORT, best first. The payload is
  `deepseek_opportunities.build_request(pool)` (entry 09:46). The outcome is
  side × [(close / p0945 − 1) − (XIU close / XIU p0945 − 1)] × 100.
* **Arm B, after the open.** The payload is A's plus TODAY's first thirty
  minutes. Every candidate row gains `open30`:
  * `gap_pct`: today's open against the prior close;
  * `r30_pct`: the 10:00 price against the open;
  * `x30_pct`: `r30_pct` minus XIU.TO's;
  * `rvol30`: the 09:30–10:00 volume against its median over the prior 20
    sessions;
  * `vwap30_gap_pct`: the 10:00 price against the 09:30–10:00 VWAP;
  * `range30_pos`: where 10:00 sits in the first thirty minutes' range, from
    0 (low) to 1 (high).

  Elsewhere in the payload:
  * `macro.xiu_open30` holds XIU's `gap_pct` and `r30_pct`;
  * `entry` becomes `10:01 ET`;
  * `data_dates.open30` reads `<session> 09:30–10:00 ET`.

  The outcome is side × [(close / p1000 − 1) − (XIU close / XIU p1000 − 1)]
  × 100.

  The prompt is A's with exactly these edits:
  1. "from 09:46 ET to 15:59 ET today" → "from 10:01 ET to 15:59 ET today".
  2. In the shared field documentation, "The entry is 09:46 ET and the exit
     is 15:59 ET on the SAME day." → "The entry is 10:01 ET and the exit is
     15:59 ET on the SAME day." This was found while writing the script,
     before anything ran or the registration was committed. Two later
     mentions of 09:46 (the analyst-change note, and economic releases
     "at or after 09:46") are left as they are.
  3. The sentence beginning "Everything supplied describes the PREVIOUS
     completed session" is replaced by: "The rows describe the PREVIOUS
     completed session, EXCEPT `open30`, which is TODAY's first thirty minutes
     (09:30 → 10:00 ET), measured before you answer. The entry is 10:01 ET.
     Say in the reason why the move is not already priced in, or do not rely
     on it."
  4. Appended, as the last paragraph, with each field's definition exactly as
     listed above: "open30 (TODAY, 09:30 → 10:00 ET): gap_pct …;
     macro.xiu_open30 carries XIU.TO's own gap_pct and r30_pct."

## Data

FMP bars, with times marking bar starts:
* **15-minute bars:**
  * the 09:30 bar gives the open, and its close is the 09:45 price;
  * the 09:45 bar's close is the 10:00 price;
  * the 15:45 bar's close is the 16:00 price.
* **Volumes** for `rvol30` come from the 09:30 and 09:45 bars, over the prior
  20 sessions.
* **EOD** gives the prior close.

XIU.TO is measured the same way.

## The model control (must pass before the test is run)

The planted universe has twelve names with the SAME pre-open rows (the day-110
noise rows), so nothing stands out before the open. The plant is ONLY in
`open30`:

| Name | `x30_pct` | `rvol30` | `vwap30_gap_pct` | `range30_pos` |
|---|---:|---:|---:|---:|
| `CTLUP.TO` | +2.4 | 4.2 | +0.9 | 0.97 |
| `CTLDN.TO` | −2.9 | 4.0 | −1.0 | 0.03 |
| the ten noise names | ±0.3 | ~1.0 | ~0 | ~0.5 |

Clean means both planted names nominated on their sides. **Bar: 4 of 5
clean** (day-129's nomination bar). If it fails, the model does not read the
fields and T2 is not run.

## T2 — the registered test (Arm B)

* **Statistic.** The mean outcome over Arm B's picks, clustered by session.
* **Bar:**
  * mean > 0 with t ≥ 3;
  * random-pick placebo p < 0.05: 2,000 draws, each session drawing as many
    longs and shorts as Arm B picked there, at random from its names with
    bars, scored the same way; one-sided;
  * a planted 0.5% must show at t = 0.5 / se ≥ 3, else UNDERPOWERED.

## Descriptive (no bar, never a rule)

* Arm A against the same placebo, at its own 09:45 entry.
* B − A, paired by session.
* The mechanical rule on the same pool: the two highest `x30_pct` long and the
  two lowest short, from 10:00 to the close.
* The share of Arm B picks whose side follows `x30_pct`.
* Hit rates and the long/short split.

## What follows

* **PASS:** the after-open question has replay support. A forward shadow (a
  10:00 desk asked live, recorded and scored apart, never sized) may be
  PROPOSED to the owner, with its own registration.
* **FAIL or UNDERPOWERED:** C3 stays unsupported, and nothing changes.

Script `replay_after_open.py`; summary `data/replay_day132c_after_open.json`.
About 123 DeepSeek calls.
