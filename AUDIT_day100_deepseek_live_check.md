# Day100 follow-up: real DeepSeek inputs and failure visibility

2026-09-14, based on reviewed main d1a5173. This repairs input/output handling
and adds an explicit diagnostic. It does not change baseline selection,
allocation, the 60-name research target or any registered factor threshold.

## Confirmed defects

The response parser treated every period followed by whitespace as a sentence
boundary. A valid rationale such as “U.S. demand supports the disclosed
expansion.” therefore rejected the entire strict response batch. Common
financial abbreviations now receive a bounded continuation check; returned
text is not rewritten. Genuine multiple sentences, control characters,
missing/duplicate tickers, extra fields and invalid scores remain rejected.
Sentence detection is a punctuation heuristic, not a semantic grammar proof.

A sealed preparation failure with `model: null` was replaced at loading by
“invalid model identifier,” hiding its original explanation. The reader now
retains the original credential-free cause only when status is UNAVAILABLE
and both assessments and batch receipts are empty. Hash, time, input and
pre-open validation still apply. A success or recorded request without a valid
model remains rejected. The existing pure concise/full renderers display the
retained cause without fetching data.

## Actual current-time check, not a retrospective morning result

Public inputs were collected at 11:19 ET on September 14. All four macro
references validated. Of the 21 baseline names, 14 had complete timestamped
Python technicals and linked current headlines. Six lacked usable current
headlines, including one HTTP failure; AEM.TO lacked complete momentum/volume
technicals because the validated contiguous history was insufficient.

At 11:21:34 ET, the explicitly configured `deepseek-flash` received those 14
complete records. It returned all 14 strict assessments in 20.748 seconds,
with no API error. This exercised real stock inputs, unlike the previous
synthetic schema probe. The API status was READY; overall pool coverage was
PARTIAL (14/21). Exact inputs, real clocks, response identifier, hashes and
assessments remain in private diagnostic receipts.

Eleven assessments were NO_EDGE. ENB.TO, CNQ.TO and SHOP.TO had positive
contextual scores of 0.40, 0.35 and 0.30. None reached the existing 0.50
research-watchlist threshold. No threshold was lowered to manufacture names.
These are current-time model interpretations of supplied evidence, not price
forecasts, verified entries or measured alpha. No outcome comparison was run.

The original September 14 failed pre-open attempt and sent report remain
unchanged. This diagnostic cannot establish what the model would have said
before the open or that tomorrow's providers will be available.

## Reusable diagnostic boundary

`probe_deepseek.py --state-dir PRIVATE_STATE --input PUBLIC_INPUT_JSON` checks
one supplied batch of at most 25 names at the actual current clock. It uses
the same strict public-input validator, compatible SDK adapter, explicit model
and 30-second killable API budget. Only fully validated names are submitted;
requested, eligible and assessed counts remain separate. It neither fetches
prices/news nor pads or samples an oversized pool.

The diagnostic saves its attempt before calling the API, plus inputs and an
explicitly non-morning result in a unique diagnostics directory. It does not
write `deepseek_snapshot.json`, the original attempt, a report database or any
delivery claim. The production snapshot reader rejects diagnostic artifacts.
The default synthetic command remains available. Neither probe is scheduled
on the 09:46 path. Normal next-session preparation remains the sole producer
of eligible morning factor snapshots.

The adapter retains the provider's documented
[JSON output contract](https://api-docs.deepseek.com/guides/json_mode/) and
[explicit thinking-mode parameter](https://api-docs.deepseek.com/guides/thinking_mode/).
No key, authenticated URL, private ledger or model chain of thought is logged.

Regression tests cover abbreviated finance prose, whole-batch preservation,
unavailable-model diagnostics through all renderers, missing/invalid inputs,
bounded API failure, immutable morning records and diagnostic rejection by
the production reader. Full suite and deployment evidence are recorded in
the pull request. All six protected modules and earlier registrations remain
unchanged. MDE and accuracy improvement remain unestablished.
