# Day102: grounded DeepSeek evidence and report correction

## Observed problem and scope

September 14's descriptive after-close review found an ENB positive opening gap
(+0.419662 percent) described as down and a TRP positive MACD histogram
(+0.177746 quote-currency units) described as negative. These are factual
contradictions, independent of whether the eventual direction won or lost.
Evergreen investment commentary and multi-year stories also lacked an explicit
remaining-session interpretation; macro levels were available without measured
change references. This correction does not explain every adverse move or prove
that a different trade would have won.

The engineering contract was preregistered in local commits `1314767` and
`8b6aa77`, before implementation/evaluation, against main
`6b7fa8604e29693dd947929c0ec8ec3e018e2697`. The observed losing-day examples are
post-hoc development examples and cannot be confirmation observations.

## Changes

- `factor_grounding.py` supplies exact dated Python facts with units/signs,
  per-ticker public evidence IDs and a remaining-session horizon. New SDK
  responses must cite supplied IDs and the requested horizon. Technical prose
  and directional opinions supported only by explicit commentary/multi-year
  titles are excluded per ticker; independent valid siblings survive.
- `adapters/deepseek_adapter.py` retains the archived four-field parser and adds
  the six-field grounded contract. Displayed rationales are deterministic;
  original bounded provider prose stays in private receipts. Syntax/identity
  errors remain envelope failures. There is no alternative-model fallback.
- `grounded_records.py`, preparation and loading reconstruct requests and replay
  projections before accepting a receipt. Changing an assessment or its inputs
  and resealing outer JSON cannot retain the old request/projection. These hashes
  are consistency checks, not cryptographic authentication of provider truth.
- `factor_news.py` deduplicates before the eight-headline cap and labels explicit
  commentary/multi-year titles. Issuer role, novelty and first disclosure remain
  unknown; a ticker news feed is not proof of material issuer exposure.
- `factor_macro.py` and `factor_inputs.py` preserve absolute levels and add a
  change only with an actual dated daily-bar reference. Range-start previous-close
  fields are not accepted as prior-session evidence. Missing references retain
  healthy levels with explicit unavailable-change context.
- `daily_render.py` shows grounded exclusions, actual evidence hyperlinks and
  Python facts from the existing Digest. Sanitization preserves separately
  validated public source URLs while removing private free text. No acquisition,
  reranking or LLM pass was added to text/HTML/concise-email rendering.
- `probe_deepseek.py` preserves the original hashed inputs when outcome-specific
  grounding gaps are added and keeps its diagnostic receipt separate from any
  morning attempt or publication. Fully excluded semantic batches do not stop
  later independent batches as if the provider had failed.

## Validation

A real synthetic contract probe on September 14 at 18:49:06 ET used the existing
explicit `deepseek-flash` setting. All 25 synthetic names passed the new schema,
evidence-reference and horizon contract in 19.595 seconds, with zero grounding
exclusions. It did not acquire new stock evidence, rerun today's predictions,
change a morning attempt or send email. The credential-free receipt and private
provider rows are retained separately in operational diagnostics.

Automated checks cover the ENB/TRP contradictions; wrong/cross-ticker IDs;
commentary-only support; missing proofs; changed inputs and projections; valid
partial siblings and later waves; URL/title deduplication; dated macro changes;
secret handling; preserved evidence links; and preparation through single-Digest
email rendering. Full-suite and runtime results are recorded below after the
final verification gate.

## Limits and preserved invariants

This is a finite protocol and conservative title classifier, not a general
natural-language fact checker. Its prohibited vocabulary can reject otherwise
benign phrasing. Unclassified news is neither certified material nor certified
novel. Daily macro references are explicitly previous observed bars, not live
quotes or proof of the immediately preceding exchange close. API/transport and
public feed failures can still occur and remain visible.

The 21-name baseline, K=60/M=20, selection/allocation, six protected modules,
ledgers, historical reports and deliveries, rejected experiments and 0.50
research threshold are unchanged. Expanded TSX research, H1/H2 and factor scores
remain unadopted; bounded scores are not calibrated probabilities. No historical
accuracy or P&L was rewritten. Numerical MDE and benefit are unavailable until
adequate matched forward data, costs and untouched confirmation exist. No new
email or automatic replacement was sent for this fix.

## Operational history

The existing database passed SQLite integrity checking and retained five reports,
five delivery records and one replacement, with an unchanged logical dump hash.
The attempt to persist the new diagnostic receipts and descriptive review failed
at file transfer; the canonical archive remains version 27. The local receipts
exist, but a durable save is not claimed. This does not substitute an empty
archive or overwrite existing credentials, attempts or publication history.

## Final local verification

- Full suite: **2,172 passed**, six existing calendar/Pandas deprecation warnings,
  in 234.40 seconds, using the isolated checkout's installed virtual environment.
- `runtime_check.py`: READY, no failed imports, using that same interpreter.
- Canonical `brief.py --offline --format json --output ...`: completed with valid
  JSON and all independent top-level sections; no email or state publication.
- `git diff --check`: clean. The six protected modules are byte-identical to the
  reviewed base. Changed/new source files were checked against both configured
  private API values: no matches.
- The actual synthetic API result remains 25/25 READY; it is not market evidence.
