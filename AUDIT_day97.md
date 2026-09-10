# Day97: provider integration and contributor review

Base: e55e7763952322700d3d7caa18c9a6bc9cb32010. The current main pairs
reselection-placebo correction remains intact. All previous rejected studies,
registrations, immutable reports and delivery semantics are preserved.

Subsequently integrated main b9f0847 sequentially. Its per-arm cross-market
coverage fix keeps the registered three-hypothesis correction while retaining
available B1/B2 results and blocked FX B3. The reported verdict remains
UNDERPOWERED, with negative observed AUC differences and no adoption. No new
daily-bar outcome is presented as validation of the 09:46 execution contract.

Reviewed Kimi's `kimi/day95-record-integrity` through 4bb0f99. Integrated the
density sample-size correction and finite-input rejection idea with focused
regressions. The healthy-data k-NN calculation and seed remain identical.
Unscorable live rows now carry a reason instead of disappearing silently.
No alpha, share allocation, exposure or horizon change is adopted.

Not integrated wholesale:

- The proposed four-minute publication window and unfrozen-outage class would
  alter the reviewed single-publication/delivery contract.
- The vp shadow comparison changes both normalization and the available
  training rows (20-session warm-up). It does not isolate a normalization
  effect. Normalization fitted only to the decision's historical training
  window is not itself proof of future-data leakage at that decision.
- The residual harness uses sample covariance and population variance in the
  same beta ratio, accepts duplicate index dates by dropping them, and permits
  only five overlapping observations despite the nominal 60-session window.
  These need explicit review before treating its output as the registered test.
  Residual features remain a separate unadopted hypothesis, not a refuted idea.

`PREREGISTER_day97.md` precedes the new opening-path analysis. It separates the
day93 volume-pace question from a fixed two-feature opening-path extension.
Both use paired whole-session chronological folds, block-aware uncertainty,
finite-draw joint placebo probabilities and an explicit OOS floor. A statistical
sensitivity control is not mislabelled as an end-to-end planted predictor.
Costs, execution and index-relative P&L remain unmeasured by these proxy labels.

EODHD qualification is isolated from the baseline and quotes. Its account and
provider errors are sanitized; tokens are loaded from private host state only.
Preflight and the single report computation read prepared diagnostics; rendering
does not access a provider or re-open the state file. Missing optional EODHD
coverage never removes the baseline board or independently reviewed calendar.

The first real cached-history diagnostic found 57 common complete sessions,
36 usable after warm-up/finite-row checks, and zero OOS sessions under the
registered 120-session training requirement. The result is BLOCKED, not a null
and not evidence of improvement. Nine ticker-session gaps were counted; partial
universe dates were excluded from all arms together. No threshold was reduced.

Outbound EODHD access in this interactive runtime was blocked before a provider
entitlement response. The credential is therefore not claimed valid, invalid,
intraday-entitled or denied. Official free-plan documentation is not a substitute
for the pending endpoint check. Local fixture tests validate software behavior,
not access, prediction accuracy, live readiness or delivery timing.
