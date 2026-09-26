# PREREGISTER day-115 — Part 3 strategy picks (consensus + open confirmation)

Registered 2026-09-26, before the first live session carrying the section
(2026-09-28). Nothing below is to be moved after a result is seen.

## The rule, exactly as the code runs it (`consensus_picks.py`)

1. **Candidates.** Every (ticker, side) flagged by Claude (sealed selected),
   DeepSeek (selected) or Jev (selected, forced or top-ranked), plus the
   engine's board as a last-resort filler. A ticker flagged on BOTH sides by
   any sources is excluded.
2. **Confirmation at the open**, from the completed 5-minute bars stamped 09:35
   and 09:40: price = 09:40 bar close; VWAP = volume-weighted typical price of
   those bars; rvol = their volume / the median of the same over up to 20 prior
   sessions (≥ 5 required). LONG needs price > VWAP and rvol > 1.2; SHORT needs
   price < VWAP and rvol > 1.2. A name not measured never meets the rule.
3. **Tiers.** A = ≥ 2 models + rule met; B = 1 model + rule met; C = ≥ 2 models,
   rule not met; D = the rest. Within a tier: more models, then Claude among
   them, then DeepSeek, then higher rvol, then the lead model's own number.
4. **Two names, every day** while any candidate exists. Recorded in
   `data/model_picks.csv` as model `consensus`, kind `rule_met` or
   `rule_not_met` (tier in `prompt_version`), scored by `model_picks --score`:
   09:45 bar close to the 15:55 bar close, no costs.

The 1.2 threshold is the owner's, for both sides (an earlier note said 1.5 for
shorts; the owner's summary said 1.2, and 1.2 is registered). The 09:30 bar is
excluded because Yahoo reports it as 0 volume on most TSX sessions and as the
whole opening auction on a few (CP.TO: 0 on 23 of 25 sessions, 1,017,019 on
09-18). That choice was made to fix a measurement defect, before any outcome
was examined under it.

## What was claimed, and what the record shows

The owner's premise: DeepSeek is "above 80%" when the rule is met, and Claude
is 4/4 pre-open. Replayed on every recorded pick 2026-09-17 → 09-25 (38 picks,
the real `opening()` on real bars — descriptive only):

| Population | Right | Mean per pick |
|---|---:|---:|
| Rule met (all sources) | 3/7 | −0.40% |
| Rule not met (all sources) | 17/31 | +0.01% |
| DeepSeek, rule met | 2/4 | −0.11% |
| Claude, rule met | 0/0 | — |
| Claude, rule not met | 5/5 | +0.69% |

K.TO (09-25) met the rule (below VWAP, rvol 2.86) and lost; AC.TO long did not
(below VWAP at 09:45, rvol 13.8) and won +3.53%; all five Claude winners failed
it. Seven picks resolve nothing — the Wilson interval on 3/7 is 16%–75% — and
this table is not evidence for or against the rule. It is why the rule is
scored rather than adopted.

## The bar

Evaluate ONCE, when BOTH hold: ≥ 60 sessions carrying the section and ≥ 60
scored `rule_met` picks. The rule is described as having an edge only if ALL of:

1. `rule_met` hit rate exceeds `rule_not_met` by ≥ 10 percentage points,
   session-clustered z ≥ 2.0;
2. `rule_met` mean r > 0 with a session-clustered 95% interval excluding 0;
3. the same sign in both halves of the sample (by date);
4. a placebo that shuffles the rule_met flag WITHIN each session beats the
   observed difference in < 5% of 2,000 draws;
5. a positive control run first: the same harness on a planted panel in which
   rule-met picks win 65% must detect it (house rule 4). If it cannot, the
   result is UNDERPOWERED, not a null (house rule 10).

Otherwise the section stays what it is today: an observation printed because
the owner asked for one every morning. The threshold, the bars and the tiers do
not change after a losing day (the day-98 lesson).
