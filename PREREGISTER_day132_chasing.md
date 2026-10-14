# Day-132 — do the picks chase yesterday's move, and is anything left after 09:45? (owner, 2026-10-14)

Registered BEFORE any of it ran. Nothing below has been computed on the
population named here; day-120b's H2 (711 replay name-days, t = 1.12) is the
only earlier reading, and it was underpowered.

## Why

On 2026-10-14 the council's Top 2 was SHORT SSRM.TO (it fell −6.48% on 10-13,
−1.62 ATR, on acquisition news) and LONG CNQ.TO (it closed at its 52-week
high). The owner asked whether picking names that already moved hard in the
pick's direction is "look-backward bias", or still fine.

Two different things go by that name:

* **Look-ahead bias** — using information that did not exist at decision
  time. That is an audit of the pipeline, not a statistical question (A below).
* **Chasing** — a selection habit: preferring yesterday's biggest movers, on
  the side they moved. Whether it costs anything depends on what such names do
  AFTER 09:45 the next day. That is the test (H1).

## A — the look-ahead audit (mechanical checks, no bar)

* A1. Every model input describes the prior session and says so
  (`data_dates`, day-127); the brief is written before the open.
* A2. The desks and the council seal before 09:30 (staging refuses after it),
  and the flash states the decision time.
* A3. The record scores from the 09:45 bar close, after the decision, to the
  close; nothing after 09:45 reaches a model before it seals.

## M1 — how much do the picks chase? (a measurement, no bar)

* Picks: every `data/model_picks.csv` row from 2026-09-17 to 2026-10-14 that a
  model chose before the open — desk selections, nominations, Jev forced,
  `top2`, `top2count`, `top2memory`, `debate/final`. Late picks are excluded
  (asked after the open); the engine (not a language model) is reported apart.
* A pick CHASES (day-120b's definition, unchanged) when its side agrees with
  the sign of the prior session's `move_atr` and |`move_atr`| ≥ 1.0.
* Base rate: on the same sessions, every name of the 2026-10-14 pool on both
  sides — the chance a pick drawn at random from the pool chases.
* Reported: the picks' chasing share, the base share, and their ratio with a
  session-bootstrap 95% interval (2,000 resamples, seed 132).

## H1 — does a ≥ 1 ATR move carry past 09:45 the next session? (the test)

* **Names:** the 117 TSX names of the 2026-10-14 morning pool
  (`deepseek_candidates.json`), with XIU.TO as the market. Survivorship: these
  are today's names; names that left the pool earlier are absent.
* **Data:** FMP `historical-price-eod/full` (daily OHLC) and
  `historical-chart/15min`. Bar times are bar starts: the 09:30 bar's open is
  the session open and its close the 09:45 price; the 11:45 bar's close is
  noon; the 15:45 bar's close is the close — the same instants the record
  scores (09:45 bar close → 15:55 five-minute bar close).
* **Sessions D:** 2024-01-02 → 2026-10-13, where all four bars exist for the
  name and for XIU, and the name has 16 daily bars before D.
* **Signal:** m = `move_atr` of D−1, computed exactly as
  `daily_technicals.context`: (close D−1 − close D−2) / the mean true range of
  the 14 sessions ending D−1.
* **Event:** |m| ≥ 1.0.
* **Outcome:** y = sign(m) × 100 × [(close_D / p0945_D − 1) − (XIU close_D /
  XIU p0945_D − 1)]. Positive = the move continued after 09:45 (chasing
  paid); negative = it reversed (chasing cost).
* **Statistic:** the mean of y, clustered by session. Four chronological
  blocks of events.
* **Placebo:** each event's sign replaced by the sign of m on a random other
  session of the same name at least 5 sessions away; 2,000 draws, seed 132;
  two-sided p = share of draws whose |mean| ≥ the observed |mean|.
* **Positive control:** a planted 0.10% (one round trip) must show at
  t = 0.10 / se ≥ 3. Reported with MDE80 = 2.8 × se.

**Verdicts (fixed now):**

| Verdict | Needs all of |
|---|---|
| CONTINUATION (chasing pays) | mean > 0, t ≥ 3, all four blocks > 0, placebo p < 0.05, mean − 0.10 > 0 |
| REVERSAL (chasing costs) | mean < 0, t ≤ −3, all four blocks < 0, placebo p < 0.05 |
| NULL | neither, with the control passing |
| UNDERPOWERED | neither, with the control failing |

## Descriptive splits (printed, no verdict, never a rule)

1. Where the move goes: the gap (close D−1 → open D), open → 09:45,
   09:45 → noon and 09:45 → close, each signed by sign(m), excess of XIU.
2. Dose: |m| ≥ 2; 1 ≤ |m| < 2; |m| < 1.
3. Side: up-moves (a LONG chase) and down-moves (a SHORT chase).
4. Idiosyncratic: the prior move against XIU in ATR units, |m_x| ≥ 1.
5. Earnings: D−1 was an FMP report date or the first session after one,
   against the rest.
6. Gap agrees: D opened further in the move's direction (as SSRM on 10-14),
   against D opened against it.
7. Hold: 09:45 D → close D+4 (five sessions), excess of XIU.
8. Hit rate (y > 0) for each.

## M2 — the live record (descriptive)

Chasing picks against the rest on the recorded `r_pct` (the scoreboard's
yardstick), session-clustered difference, with its MDE. Expected to be
underpowered; reported as such.

## What each result leads to

* **CONTINUATION:** nothing changes; the habit points the right way.
* **REVERSAL:** reported to the owner with its size. A display line beside a
  chasing pick and a shadow arm may be PROPOSED; no prompt or rule changes
  without the owner's decision and its own registration and control
  (day-127/128).
* **NULL / UNDERPOWERED:** chasing is a habit that neither helps nor hurts
  after 09:45 at the measured resolution; nothing changes, and day-120b's
  "no flag" stands.

The bar does not move after the run. The script is `replay_chasing.py`; the
summary goes to `data/replay_day132_chasing.json`.

## Results (2026-10-14, after the run; nothing above was changed)

* **H1: NULL, powered.** There were 10,332 moves of ≥ 1 ATR on 687 sessions
  (79,453 name-days, 117 names).
  * The move continued after 09:45 by −0.013% against XIU, t = −0.44, right
    49.5% of the time.
  * Blocks +0.14 / −0.17 / −0.08 / +0.06; placebo p = 0.47; net of 0.10% it
    is −0.11%.
  * A planted 0.10% shows at t = 3.39 (MDE80 0.083%).
* **M1:** 58 of 129 model picks chased (45%), against a 5.7% base: 7.9×
  (95% 5.6–10.8). The council's Top 2 chased 9 of 17 (9.5×); the engine
  1.7×.
* **M2:** chasing 35% right (−0.34%), the rest 38% (−0.14%); the
  difference is t = −0.05 with an MDE of 1.15%. Uninformative.
* **Descriptive:** no window, dose, side, report-day, own-move or gap split
  reaches |t| = 1.2.

As registered for a NULL, nothing changes. Read `AUDIT_day132_chasing.md`.
