# AUDIT day-121b — agreement and an at-the-open entry, tested on the replay

Registered first (`PREREGISTER_day121b_agreement_and_open.md`, commit 57964a5).
The data is the day-117 replay: 59 sessions, DeepSeek and Jev. Numbers are in
`data/replay_day121b.json`.

## T1 — agreement does not pick better names

| Top 2 rule | Sessions with a name | Right | Mean per pick | Clustered t |
|---|---:|---:|---:|---:|
| Agreement only (shipped 2026-10-01) | 50 / 59 | 35/76 (46%) | −0.13% | −0.94 |
| Old filled rule | 59 / 59 | 53/117 (45%) | −0.18% | −1.06 |

| DeepSeek selections | Right | Mean per pick |
|---|---:|---:|
| Jev also backs it | 42/86 (49%) | −0.06% |
| DeepSeek alone | 67/135 (50%) | −0.09% |

* **Difference:** −0.14%, t = −0.58, placebo p = 0.70.
* **Planted +0.5%:** shows only at t = 1.44, so this comparison is
  UNDERPOWERED below about 1% per pick.

Two things follow.
* The models agree on 50 of 59 sessions, because they read the same brief and
  are drawn to the same names. Agreement here is not independent evidence (as
  day-119 registered), and it is not more accurate.
* Agreement-only remains what it was adopted as: a rule about what a Top 2 slot
  CLAIMS, not an accuracy filter.

## T2 — entering at the open is not a lever (a powered null)

| Window | Right | Mean per pick | Clustered t |
|---|---:|---:|---:|
| Open → 09:45 | 177/334 (53%) | +0.07% | +1.08 |
| 09:45 → close | 170/334 (51%) | −0.05% | −0.36 |
| Open → close | 175/334 (52%) | +0.02% | +0.44 |

* **Random same-pool picks, open → close:** median +0.00%, p = 0.42.
* **Planted +0.5%:** detected at t = 3.74.

The picks are not being priced in the first 15 minutes. They carry nothing
from the open either, so sending them before 09:30 would not help. This joins
#29 and #40 (the engine's entry times), now for the LLM picks.

## Verdict

Both nulls; nothing adopted; nothing tuned. Rejections stay at 44: these were
diagnostics of rules already in place or proposed, not new strategies.
