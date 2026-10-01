# AUDIT day-120b — the 0/2 Top 2 of 2026-09-30, tested on the replay

Registered first (`PREREGISTER_day120b_pick_quality.md`, commit 8102f83). The
data is the same 59 sessions and 341 model picks (DeepSeek selected, Jev
selected and forced) as day-117. Numbers: `data/replay_day120b.json`.

## H1 — score each pick against its sector: a measurement, not an improvement

|              | Hit         | Mean    | Per-pick sd | Correlation with the market |
|---|---|---|---|---|
| Raw          | 174/341 (51.0%) | −0.05% | 1.66 | 0.24 |
| Vs sector    | 163/341 (47.8%) | −0.10% | 1.56 | 0.05 |

Hedging removes the market from the result: the correlation drops from 0.24 to
0.05. It cuts per-pick sd by only 6.1%, against the 15% bar, and the picks are
no better at choosing names than at choosing direction.

* **Not adopted** as the Top 2's expression.
* **Printed as a measurement** in the evening review. "Mean vs sector" and
  "beat its sector" sit beside every pick, so a sector-wide move (TD on 09-30:
  −0.75% raw, −0.12% against its sector) is not read as a bad pick.

## H2 — "chasing yesterday": the wrong sign and underpowered

| Group | Picks | Hit | Mean |
|---|---:|---:|---:|
| Picks continuing a ≥ 1 ATR prior move | 136 | 68 (50%) | +0.10% |
| The rest | 205 | 106 (52%) | −0.14% |

* **Clustered difference:** +0.29%, t = +1.29 over 47 sessions. Chasing did
  slightly BETTER, not worse.
* **Placebo:** p = 0.89 for "worse".
* **Planted −0.5%:** detected only at t = −0.97. **UNDERPOWERED**: this replay
  cannot see an effect of that size.
* **Whole panel:** continuation after a ≥ 1 ATR move was right 53.7% of the
  time, at +0.20%, t = 1.12, over 711 name-days.

WSP on 09-30 was a bounce. The replay does not say bounces are the rule.

* No E3 filter.
* No flag either. The registration allowed a flag, but one printed beside a
  pick would read as a warning the data contradicts.

## H3 — single-source agreement: display only

When a Top 2 name has a same-morning issuer release, its agreement column now
reads "… — all saw the same release, not independent". All three models were
handed the same fact, so "3 of 3" there is one reading, not three.

## What this means

0/2 happens one day in four to a coin flip. Nothing measurable before 09:45
sorted the picks (day-117), and neither of the two fixes the day suggested
survives the replay. The changes are about reading the result honestly, not
about making it better.
