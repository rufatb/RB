# AUDIT day-151 — the pre-open desk on history: NULL (rejection #66)

Council lab item 9's history replay, registered 2026-11-12
(`PREREGISTER_day151_us_preopen_history.md`), run once on 2026-11-13 by
`python us_preopen_history.py --run` (3f6f887, committed before it ran).
Summary and every call: `data/us_preopen_history_day151_result.json`.

## The question

The forward pre-open desk's question, asked of 2026-07-02 → 11-09:
* a TSX name that also trades in New York;
* an overnight company release;
* DeepSeek reading it before the bell (08:15 ET, or 08:55 for a name first seen
  after 08:15).

Between the read and the 09:30 open, does the New York listing move the read's
way more than SPY?

## What ran

* **Population.** The pinned file: 530 events over 89 sessions on all 81
  names, read at 108 reads.
* **The model.** DeepSeek (`deepseek-v4-pro`, thinking off), day-122's prompt
  byte for byte through `news_desk.answer`, each read's events asked together.
  * 525 of 530 answered. The other 5 were lost to malformed replies: 6
    entries answered twice and 2 confidences out of range, counted per entry.
  * No batch was re-asked.
* **Price at the read.** The US listing's last one-minute extended-hours bar
  that ends:
  * at or before the read;
  * within 30 minutes of it;
  * after the last release.

  SPY is priced the same way.
* **The exit.** The 09:30 five-minute bar's open (`us_preopen.session_marks`),
  measured with `us_preopen.outcomes`.
* **Cost.** About 108 DeepSeek requests. FMP bars cached under
  `.rb-state/us_preopen_history_cache/`. No OpenRouter. About ten minutes.

## Result: NULL, powered

Material calls with a price: 209 calls over 72 sessions.

| Measure | Value |
|---|---:|
| Mean of the session means, read → 09:30 open, against SPY | **−0.27%** |
| t (session means) | −1.88 |
| Sign-flip placebo p (10,000 draws, seed 151; upper) | 0.97 |
| Halves, in date order | −0.19%, −0.34% |
| Net of 0.15% a call | −0.42% |
| Planted 0.5%: t | 3.51 (detected) |
| Smallest effect detectable at 80% power | 0.40% |
| Calls right | 94 of 209 (45%) |
| Contamination probe (30 events, seed 151) | median miss 36.6%: not void |

The plant shows, so the null is powered. The mean is negative, so the bar is
not met. Anything but PASS is rejection #66.

## Beside it, never judged

* **The later windows.**
  * Read → 09:45: −0.15%, 100 of 209 right.
  * Read → the close: +0.20%, 110 of 209 right.
* **The overnight gap on the US listing** (day-122's measure moved to New
  York; prior close → open, against SPY): +0.01% over 319 material calls.
  * On titles and summaries, DeepSeek does not call the New York gap.
  * Day-122's +0.21% was the TSX gap with the full release body.
* **By side.** LONG 168 calls, −0.33%. SHORT 41 calls, 0.00%.
  * The model went long on 260 of 329 material reads.
* **By read.** 08:15: 198 calls, −0.29%. 08:55: 11 calls, +0.21%.
* **By source.** FMP's feed: 190 calls, −0.31%. The wire: 19 calls, +0.17%.
* **By month.**

  | Month | Mean |
  |---|---:|
  | July | −0.09% |
  | August | −0.29% |
  | September | −0.23% |
  | October | −0.41% |
  | November | −0.50% |

* **Routine calls:** 84 calls, −0.17%.
* **Unpriced: 232 of 525 answered calls (44%).**

  | Reason | Calls |
  |---|---:|
  | no bar in the 30 minutes before the read | 214 |
  | no bar after the release | 8 |
  | no one-minute bars at all | 5 |
  | no 09:30 bar | 5 |

  Many listings do not trade in the US pre-market at 08:15.

## What it says

* By the morning read the US pre-market has already traded the release.
* What is left to the 09:30 open runs slightly **against** the read: the read
  agrees with a move that partly fades by the open.
* This is the same finding as day-118/122/125, one step earlier. The price has
  the news before a model can act on it.
* The forward desk's first three mornings (11-10 → 11-12, outside this window)
  read 0 of 6 to the open, −1.11% a call. That is consistent, and an
  anecdote.

## What changes

* **Nothing live.** The forward desk keeps its own registered bar (40 sessions
  with a material, priced call) and runs on unchanged.
* Whether it should keep running is the owner's call.
* The prompt is not re-worded against this replay.

## Not claimed

That any pick, read or desk is more accurate. Say so plainly when asked.
