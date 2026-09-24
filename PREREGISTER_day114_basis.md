# Pre-registration — day 114: does a pick's declared BASIS predict its outcome?

Registered 2026-09-24, before a single pick carried a `basis`. Nothing below may
be changed once the first basis-tagged pick is scored; an amendment is a new,
dated section that says what changed and why, and it cannot move the bar.

## Why

On 2026-09-24 (late picks, asked after the open) the two models split along one
line. DeepSeek's two winning shorts rested on company news (WSP withdrew its
Arcadis offer, +1.11%; Aritzia's relative weakness, +2.78%). Claude's two
biggest losers rested on technical readings (SU.TO long on an oil move already
in its opening gap, −0.81%; SSRM.TO short on RSI 72 after the flush, −1.79%).
That is four picks on one day — an anecdote, not a finding. This registers the
question so it can be answered instead of argued about after the next bad day.

## What is recorded

Every Claude and DeepSeek pick declares `basis` ∈ {`news`, `technical`, `macro`}
(`deepseek_opportunities.SYSTEM_PROMPT`, prompt `day114-v3`). The declaration is
CHECKED against what the model was shown: `news` on a name with no supplied
headline or catalyst tag is recorded as `technical`
(`deepseek_opportunities.check_basis`), so the tested group cannot be inflated
by an unsupported claim. `data/model_picks.csv` records it; `model_picks.py
--score` scores it on the existing yardstick (09:45 bar close → session close,
no costs); `model_picks.basis_card()` tabulates it.

## Population

Claude and DeepSeek `selected` picks only, pre-open, from prompt `day114-v3`
onward. Excluded: Jev (it gives no reasons), forced picks, `late` picks (a
different instrument, recorded separately), the engine's board, and any pick
with no basis.

## Hypothesis and bar

H1: `news`-basis picks have a higher hit rate than `technical`-basis picks.

Evaluated ONCE, when BOTH hold: at least 60 sessions since registration, and at
least 100 scored picks in each of the two groups. Not before — an interim look
is descriptive and moves nothing.

H1 is SUPPORTED only if all four hold:
1. hit-rate difference (news − technical) ≥ 10 percentage points;
2. session-clustered z ≥ 2.0 for that difference (picks on one session are not
   independent — day-91's lesson);
3. the difference has the same sign in the first and second half of the
   sessions, split by date;
4. a placebo that shuffles basis labels WITHIN each session 1,000 times beats
   the observed difference in fewer than 5% of draws.

Mean return per pick is reported beside the hit rate every time, because a hit
rate above 50% with a win/loss ratio below break-even still loses money
(day-98's 0.92 vs 1.06).

`macro` is reported descriptively and is not part of H1.

## Positive control (house rule 4)

Before the evaluation is run, the same code must detect a PLANTED difference:
relabel picks so that a known 15pp gap exists on a synthetic set of the same
size and clustering, and confirm criteria 1–4 pass. If the control fails, the
result is UNDERPOWERED, not a null.

## What a result would change

SUPPORTED: the prompt may REQUIRE a news basis for a pick (a new, dated,
registered change). NOT SUPPORTED: nothing changes, and this family is recorded
in STRATEGY.md as tested. Either way no rule is adopted from a partial sample,
and nothing here sizes, places or advises an order.
