# Day-109: a positive control for the factor layer, and what NO_EDGE means

The day-99 factor layer had returned `NO_EDGE` at sentiment `0.00` on every
assessed name for three consecutive sessions — 29/29 on 09-16, 7/7 on 09-17.
House rules 4 and 10 are explicit: *a harness that cannot detect a planted edge
cannot report a null*, and *a control that cannot detect a planted edge means
UNDERPOWERED, not NULL*. Until a planted edge was shown to survive the whole
path, none of those NO_EDGE readings meant anything.

## The first control was confounded, and it was mine

The planted evidence carried the words `SYNTHETIC CONTROL, NOT REAL NEWS` in
the headline text itself. The model refused all three arms, and its raw reply
named exactly that reason:

> All five supplied headlines are UNCLASSIFIED synthetic control items with the
> identical placeholder guidance text, unverified issuer relevance and no
> first-disclosure timing, so no genuine intraday catalyst or directional
> opinion can be established.

That is correct behaviour on evidence labelled fake. It is not a finding about
the harness, and reporting it as one would have been a false negative produced
by the control's own design.

## The corrected control passes, in both directions

Same candidate (AC.TO), same UNCLASSIFIED metadata the real feed supplies, same
production path through `adapters.deepseek_adapter.evaluate_batch`. Only the
headline wording and technicals were planted, and realistically:

| Arm | Raw model reply | After grounding |
|---|---|---|
| REAL, unchanged | `NO_EDGE / 0.00` | `NO_EDGE / 0.00` |
| PLANTED BULL | `BULL / +0.30` | `BULL / +0.30` |
| PLANTED BEAR | `BEAR / −0.60` | `BEAR / −0.60` |

Two things follow, and the second was a live hypothesis until this ran:

1. **The harness detects a planted edge in both directions.** The NO_EDGE
   stream is therefore a real reading of the evidence, not an artifact. Those
   sessions are informative nulls.
2. **`factor_grounding` did not flatten the lean.** Raw equals final on both
   planted arms, so the grounding layer is not overwriting model opinion with
   `NO_EDGE`. That was the more worrying of the two possible causes and it is
   ruled out by direct observation of the raw response.

## Why the real names abstain: the feed carries commentary, not events

The model's reason on the untouched candidate is specific and checkable:

> All supplied Air Canada items are UNCLASSIFIED commentary (a stock-pick
> column, an executive award, and unrelated Canadian policy/class-action
> pieces) with unverified issuer relevance…

The real headline behind that was *"Air Canada Stock Just Might Be the
Best-Kept Secret Hiding in Plain Sight on the TSX"* — a stock-pick column.
`factor_news.classify_headline` labels every Yahoo RSS item `COMMENTARY` or
`UNCLASSIFIED`, with `first_disclosed_at: None`, `issuer_role: UNVERIFIED`,
`novelty: UNVERIFIED`, `primary_source_verified: False`, because the feed
supplies no structured disclosure metadata. Catalyst tags were zero across all
130 names.

So the binding constraint on the factor layer is **evidence quality, not the
model and not the roster size**. Widening 60 → 130 names moved assessed from 23
to 29 and produced no additional lean, which is consistent: more names carrying
the same commentary are still commentary.

## What this does and does not license

- It does NOT establish any predictive skill. A lean is a reading of public
  evidence; the layer remains unadopted and enters no selection, size or
  threshold.
- It does NOT mean a lean would have produced a board. A `BULL / +0.30` on
  AC.TO still fails the gate: combined = 0.8(0.504) + 0.2(0.5 + 0.15·0.30) =
  0.512, sided 0.512, below the 0.55 threshold. The lean gate and the score
  gate are independent and both must pass.
- It DOES mean that `NO_EDGE` printed in the report is a tested abstention,
  which is what `deepseek_factors` has always claimed it to be, and that claim
  is now supported rather than assumed.

## Reproducing

Isolated diagnostic state only; planted evidence is never written to report
state and never published. Build the payload with
`factor_inputs.build_from_state(..., diagnostic=True)`, strip each candidate to
`adapters.deepseek_adapter.CANDIDATE_KEYS` (the staged rows carry an extra
`technical_provenance` key that `public_payload` rejects), then call
`evaluate_batch` with a client wrapper that captures
`choices[0].message.content` so the raw reply can be compared with the grounded
output.
