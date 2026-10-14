# Day-132 — chasing yesterday's move: is it look-ahead bias, and does it cost anything? (owner, 2026-10-14)

Registered first: `PREREGISTER_day132_chasing.md` (d63a3f5). The harness
was committed before its result (21cb729). Script: `replay_chasing.py`;
summary: `data/replay_day132_chasing.json`.

**Verdict: NULL, and powered.** The models do chase yesterday's movers, about
eight times as often as a random pick would. On 10,332 such moves over two
and three-quarter years, the move carries nothing past 09:45 the next session,
in either direction.

## The question

The council's 10-14 Top 2 was SHORT SSRM.TO and LONG CNQ.TO. Both had already
moved hard the pick's way on 10-13:

| Pick | 10-13 move (`move_atr`) | 10-13 against its sector | Other inputs |
|---|---:|---:|---|
| SHORT SSRM.TO | −1.62 ATR (−6.48%) | −5.51% | acquisition news, rvol 1.79 |
| LONG CNQ.TO | +1.95 ATR | +2.29% | 52-week high, WTI +1.66% pre-market |

The owner asked whether picking such names is "look-backward bias", or fine.

## A — there is no look-ahead bias

Look-ahead bias means using information that did not exist when the decision
was made. Checked on 10-14's own state:

* **The inputs.** The brief's `data_dates` reads rows_describe 2026-10-13,
  today 2026-10-14, written 08:56 ET. Every row describes the prior session
  (day-127).
* **The decision.** Claude's desk sealed at 08:56:23 ET through OpenRouter.
  The council sat 08:57:48 → 08:58:54 ET. Staging refuses at or after 09:30.
* **The scoring.** The record scores from the close of the bar stamped 09:40
  (the completed 09:45 bar) to the 15:55 bar (`model_picks.ENTRY_BAR`,
  `EXIT_BAR`). Nothing after the decision reaches a model.

What the owner saw is something else: a SELECTION habit. The picks lean on
yesterday's biggest movers, on the side they moved.

## M1 — the picks do chase

A pick CHASES (day-120b's definition) when its side agrees with the prior
session's `move_atr` and |`move_atr`| ≥ 1. The base rate is a pick drawn at
random from the same pool on the same sessions.

| Who | Picks | Chasing | Share | Base | Ratio (95%) |
|---|---:|---:|---:|---:|---|
| All model picks | 129 | 58 | 45% | 5.7% | 7.9× (5.6–10.8) |
| Council Top 2 | 17 | 9 | 53% | 5.6% | 9.5× (5.1–13.1) |
| Desk selections | 58 | 21 | 36% | 5.9% | 6.1× (4.0–9.2) |
| Jev forced | 22 | 10 | 45% | 4.8% | 9.4× (4.6–16.3) |
| Nominations (10-14 only) | 12 | 8 | 67% | 12.4% | 5.4× |
| Engine (k-NN, not a language model) | 54 | 5 | 9% | 5.6% | 1.7× (0–3.5) |

The council's Top 2 chased on 8 of its last 11 picks. On 10-13 and 10-14
every pick chased: ATZ.TO +4.34, CCA.TO −2.80, CNQ.TO +1.95 and SSRM.TO
−1.62 ATR. The language models do it; the engine, which reads only the
first fifteen minutes, barely does.

## H1 — a ≥ 1 ATR move carries nothing past 09:45

* **Population.** 117 pool names, 79,453 name-days, 695 sessions
  (2024-01-02 → 2026-10-13). There were 10,332 moves of at least one ATR:
  5,478 up and 4,854 down, on 687 sessions.
* **Result.** The move continued after 09:45 by **−0.013%** per event
  against XIU, **t = −0.44**, right 49.5% of the time.
* **Stability.** The four chronological blocks were +0.14 / −0.17 / −0.08 /
  +0.06: no sign holds.
* **Placebo.** p = 0.47, two-sided.
* **Power.** A planted 0.10% shows at t = 3.39. The minimum detectable effect
  is 0.083%. **A POWERED NULL:** neither continuation nor reversal, to within
  less than one round-trip cost.

## Where the move goes

Every window is signed by the prior move and measured against XIU.

| Window | Mean | t | Right |
|---|---:|---:|---:|
| Overnight gap (close → open) | −0.05% | −1.02 | 49.0% |
| Open → 09:45 | −0.00% | −0.17 | 50.1% |
| 09:45 → noon | +0.00% | 0.04 | 49.0% |
| 09:45 → close (the scored window) | −0.01% | −0.44 | 49.5% |
| 09:45 → close four sessions later | −0.01% | −0.06 | 49.3% |

| Split (09:45 → close) | Events | Mean | t |
|---|---:|---:|---:|
| Moves of ≥ 2 ATR | 1,003 | −0.06% | −0.85 |
| Moves of 1–2 ATR | 9,329 | −0.01% | −0.28 |
| Moves under 1 ATR (no chase) | 69,121 | +0.00% | 0.02 |
| Up-moves (a LONG chase) | 5,478 | +0.02% | 0.49 |
| Down-moves (a SHORT chase) | 4,854 | −0.05% | −1.11 |
| Moved ≥ 1 ATR against XIU (its own move) | 9,431 | −0.02% | −0.77 |
| The move was a report day | 880 | +0.00% | 0.06 |
| Opened further the same way (SSRM on 10-14) | 5,064 | −0.04% | −0.87 |
| Opened against it | 5,253 | +0.01% | 0.30 |

None of these shows anything. A move does not even reliably continue
overnight. By the time a pick is entered, nothing is left of it in either
direction: it does not matter how big it was, which side it was on, whether
it came on a report day or the name's own news, or whether the open carried
it further.

## M2 — the live record (descriptive, too short)

| Picks | Chasing | The rest |
|---|---|---|
| All model picks | 43 picks, 35% right, −0.34% | 60 picks, 38% right, −0.14% |
| Council Top 2 | 3/7 right, +0.03% | 3/8 right, −0.33% |

The within-session difference is −0.02%, t = −0.05. Its MDE is 1.15%:
the live record cannot tell them apart, and the replay above says there is
nothing to tell.

## What this means

* **No look-ahead bias.** Every input predates the decision. Scoring starts
  after it.
* **There is a selection habit, and it is measured.** The language models pick
  yesterday's movers about eight times as often as chance; the council about
  nine and a half times.
* **The habit costs nothing and earns nothing.** On 10,332 moves in this pool,
  yesterday's move says nothing about 09:45 → close. A chasing pick is a coin
  flip like every other pick here.
* **"It already moved a lot" is not a reason in either direction.** Do not
  read it as momentum, and do not read it as exhausted (a fade). When a
  pick's reason is only yesterday's move, it carries no information about
  today.
* **Nothing changes,** as registered for a NULL. No flag, no filter, no
  prompt change; day-120b's "no flag" stands.

Caveats: the names are today's pool (survivorship); the population is every
pool name, not only those the models would choose, though the report-day
and own-move splits cover part of what they read; and FMP's 15-minute bars
are read at the same instants the record scores.
