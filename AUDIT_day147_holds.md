# Day-147 — held for days: the models' reads come true no more often, and the record cannot see 1% (rejection #63, council lab item 8, 2026-11-06)

Registered first: `PREREGISTER_day147_holds.md` (85d9a54, amendment 1 for the
number). The script was committed before it ran: `holds_history.py`
(414d24a). One look; summary `data/holds_day147.json`. FMP daily and
five-minute bars only, cached under `.rb-state/holds_day147_cache/`: no
OpenRouter, no model call, nothing spent.

## The question

The owner, 11-03: "direction didn't come true." Every pick is scored from the
09:45 entry to the same day's close, and on that window every source is a coin
flip. A read the open has priced might still come true over a few days.
Does it?

## What was measured

* **The population.** The scoreboard's "All model picks together"
  (`model_picks.pooled_card`'s rule), sessions 09-17 → 10-29: 189 picks over
  26 sessions (95 long, 94 short, 67 names). That is the count the
  registration made, to the pick.
  * By first recorded model: DeepSeek 66, Claude 57, Gemini 36, Jev 21,
    debate 8, Top 2 1.
  * All 189 were scored. None was left out for a missing close, and none for a
    mismatch between FMP's close and the recorded exit (the 5% guard). FMP
    failures: none.
* **The measure.** y_H = side × (the pick's return − XIU's return), from the
  recorded 09:45 entry to FMP's close H sessions later. XIU's 09:45 price is
  the close of FMP's 09:40 five-minute bar.
  * Unadjusted closes: a dividend inside the hold is a small bias against
    longs. Borrow on a short held overnight is not charged.
* **The verdict** is H = 3, on day-145's machinery: t over the session means,
  a sign-flip placebo (10,000 draws, seed 147), both halves, and the mean net
  of the 0.13% round trip. The control centres every y₃ on zero and adds 1.0%
  to every pick.

## The verdict: UNDERPOWERED (rejection #63)

| | H = 3 (the verdict) | H = 1 (reported) | H = 5 (reported) |
|---|---:|---:|---:|
| Mean of the session means | +0.075% | −0.024% | +0.742% |
| Net of 0.13% | −0.055% | −0.154% | +0.612% |
| t over 26 sessions | 0.17 | −0.09 | 1.60 |
| Placebo p (upper) | 0.43 | 0.54 | 0.066 |
| Halves | +0.69%, −0.54% | −0.04%, −0.01% | +0.74%, +0.75% |
| Right | 95 / 189 (50%) | 93 / 189 (49%) | 102 / 189 (54%) |
| Planted 1.0% shows at | t = 2.50 | t = 4.05 | t = 2.04 |
| Status | **UNDERPOWERED** | NULL | UNDERPOWERED |
| Smallest detectable effect | 1.73% | 0.95% | 1.78% |

* **At three sessions** the picks are right 50% of the time. The mean is
  t = 0.17 and its halves disagree. A planted 1.0% reaches only t = 2.50: a
  three-session hold swings about 1.8 times a single day, and 26 sessions
  cannot see 1% at that spread. The registration said this was likely.
* **At one session**, where the test has power, there is nothing: −0.02%,
  t = −0.09.
* **At five sessions** the mean is +0.74%, with both halves positive, but
  t = 1.60, placebo p = 0.066, and the control is not detected either. It is
  reported, not judged.

## Beside the verdict (descriptive, never a verdict)

* **Holding against closing the same day.** The same picks closed at the same
  day's FMP close (y₀): −0.07% a pick (t = −0.56), 95 right. The paired
  difference y₃ − y₀ is +0.03% (t = 0.30): holding three sessions does no
  better than closing at the close. The record's own `r_pct` (09:45 → 15:55):
  −0.06%, 93 right.
* **Raw, not against XIU:** −0.06% at H = 3; +0.80% at H = 5 (t = 1.51).
* **By side** (per pick):

  | | y₀ | y₁ | y₃ | y₅ |
  |---|---:|---:|---:|---:|
  | Longs (95) | +0.03% (59 right) | −0.02% (51) | −0.26% (51) | −0.66% (50) |
  | Shorts (94) | −0.17% (36) | −0.04% (42) | +0.17% (44) | +2.28% (52, t = 1.79) |

  The five-session lean is the shorts' alone; the longs lose ground against
  XIU the longer they are held.
* **By first recorded model** (y₃ per pick): DeepSeek −0.03% (34/66), Claude
  −0.07% (29/57), Gemini −0.46% (18/36), Jev +0.68% (9/21), debate +0.45%
  (5/8). At five sessions DeepSeek reads +1.38% (t = 1.33). None is near a
  bar.
* **Claude's own reads.**
  * Its 48 nominations (10-14 → 10-29, 12 sessions): y₀ −0.02% (30 right),
    y₁ −0.05% (25), y₃ −0.22% (25), y₅ +0.81% (30, t = 0.69).
  * Its first-named long and short, the live Top 2's rule (24 picks): y₃
    −0.21% (12 right), y₅ +0.98% (16 right, t = 1.11).

## So

* The models' reads do not come true more often over days on this record. At
  one session there is nothing to find, at three the record cannot see 1%, and
  holding does no better than closing the same day.
* The five-session lean (+0.74%, all of it on the short side) is below every
  bar and was not the question. Testing it now on these sessions would be a
  second look. To see 0.74% at five sessions the record would need about 150
  sessions, some six months more, so no forward test is proposed.
* **Nothing changes.** No `hold3` shadow is proposed, as registered for any
  verdict but DRIFT.
* Day-130 (holding overnight was worse on the replay) and day-135b (weeks after
  earnings, no edge since 2012) stand.

## Not claimed

That any pick, held for any length of time, is more often right. Every horizon
here contains 50%.
