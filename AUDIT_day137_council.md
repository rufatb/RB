# Day-137 audit — why the council's picks lose, and what changes (owner, 2026-10-21)

Registered in `PREREGISTER_day137_council.md` (f7b7040) before the history
ran. Scripts: `council_audit.py` (the live tables) and `council_history.py`
(the registered test). Summaries: `data/council_audit_day137.json` and
`data/council_history_day137.json`.

## 10-21: SHORT CLS.TO, −0.70%

* **The thesis was the prior session's weakness.** All four members endorsed
  it. On 10-20 CLS fell 3.4% in its first fifteen minutes and finished 3.0%
  behind its sector, which rose 2.6%. Its own close-to-close move was a
  twentieth of a normal day.
* **The open went the other way.** CLS opened at 439.33, 4% above its 422.22
  close, then fell to 425.28 by 09:45, where the record enters.
* **After entry it drifted up with tech,** to 428.27 at the close. The tech
  fund's part was −0.42% for the short and the stock's own part −0.28%. The
  best the short reached after entry was +0.61%; the worst was −1.48%.
* **It had no stop.** None of its three proposers gave a "wrong if", so
  neither the 09:46 entry check nor the 09:31 open check could act.
* **It was the widest swinger of the council's picks:** a normal day of
  7.3%. The morning's 90th percentile was 5.1%.

## What the council selects (the live tables, descriptive)

There are 12 sessions, 2026-10-05 → 10-21, and 108 positions on the
tables, scored from 09:45 to the close.

| Group | Positions | Right | Mean |
|---|---:|---:|---:|
| The whole table | 108 | 46 | −0.31% |
| The council's picks (before any rule) | 20 | 8 | −0.30% |
| Endorsed by every member | 17 | 6 | −1.09% |
| At least one objection | 51 | 26 | +0.17% |

* **The council's choice adds nothing over its own table.** Per session the
  picks beat the table by +0.01% (t = 0.05).
* **Agreement gathers on the most visible continuation story.**
  * The picks followed the name's last move 85% of the time and its move
    against its sector 85%.
  * 70% followed a move of at least 1 ATR, against 32% of the table.
* **The unanimous positions did worst,** but clustered by session that is
  t = −0.55: nothing.
* **The sector's move decided most results.** On the picks the sector
  fund's part averaged −0.54% and the stock's own part −0.15%.

## The registered test on history

The 150 names, 09:45 → 16:00 from FMP 15-minute bars, 2024-01-02 →
2026-10-02, with the live audit's sessions excluded. The secondary is ten
years of daily open → close.

| | Primary (2.7 years, 09:45 →) | Ten years (open →) | Verdict |
|---|---|---|---|
| H1 follow the move against the sector (≥ 1%) | −0.044%, t = −2.75, 46.8% right | −0.016%, t = −1.61 | NULL (#53) |
| H2 follow the sector against XIU (≥ 0.5%) | −0.007%, t = −0.44 | −0.0003%, t = −0.03 | NULL (#54) |
| H3 the morning's 15 widest swingers | sd 2.46× the rest; leans t = −0.47, +1.15 | 2.16× | PASS (adoption #5) |

**H1, the council's main habit, has had no edge.**
* The estimate leans the wrong way (reversal), more so for bigger moves:
  * 1–2%: −0.024%;
  * 2–4%: −0.061%;
  * ≥ 4%: −0.096%.
* Shorting a laggard, the 10-21 CLS case, was −0.059% (t = −2.75).
* It does not reach the registered bar (t ≤ −3, all four blocks negative),
  so no rule follows from it.

**H3 is size.**
* A wild name moves more than 3% after 09:45 on 26.5% of days, against 5.5%
  for the rest.
* Neither following its last move nor buying it has an edge.
* Removing it cuts the size of a miss without changing what a pick is worth.

## What changes

`council.SKIP_WILD` is ON from the 10-22 morning. It is remove-only, like the
big-mover rule:
* **The morning's cut.** The council records the 90th percentile of ATR %
  over every name the desks read (`council.json` `wild`).
* **Passing over.** A council pick on a name at or above the cut is passed
  over. Nothing is added; it is never the runner-up.
* **Display and record.** It prints as passed over and is recorded as
  `top2wild/pick`, a shadow kept out of the pooled row and the scoreboard.
* **Labels.** rule_version gains `+day137-wild` only for a council that
  recorded the cut.

The counted fallback gets the same rule, with the cut from the brief.

**On the live Top 2** it would have passed over:
* SSRM.TO on 10-14 (+1.20%);
* CLS.TO on 10-15 (−3.61%, already a big mover);
* CLS.TO on 10-21 (−0.70%).

**The forward question, M1.** The evening review now prints the council
against its own table every session, and the unanimous positions against the
rest. A verdict comes at 40 sessions.

## Not claimed

No pick is made righter. Including today's CLS, 23 Top 2 picks are 9
right (39%). Every registered test of what the models read (54 now) has
found no edge after 09:45.

The levers that work are on loss size:
* the big-mover rule;
* the high-volatility rule;
* not stacking a side;
* the noon exit;
* the size the owner trades.
