# Audit, day-138b: the owner's picks spreadsheet (2026-10-24)

The owner sent a spreadsheet of every pick from 2026-09-24 to 10-23 (307 rows,
21 sessions, by source) and read the news desk as doing better. They asked
which source or combination wins more, and how to change the council.

This is a descriptive read, not a registered test. Nothing here changes a
pick, a rule or a record.

## What the sheet measures

* **Returns are raw.** They are not measured against the market.
* **The news desk is scored from the 09:30 open.** Its calls are made at about
  09:35–09:43, once the overnight window closes, so the 09:30–09:45 move cannot
  be traded on its call.
* **Mixed windows.** Desk and Top 2 picks are partly scored from the 09:46
  report price and partly from the open.
* **LATE picks are scored from an open they came after.** These are the
  09-24 and 09-28 picks sent at about 10:05. They show 16 of 18 right
  (+0.92%) because they knew the first half hour.

## By source (LATE rows left out)

| Source | Picks | Right | Raw mean | vs XIU | t (by day) |
|---|---:|---:|---:|---:|---:|
| News desk (from the open) | 91 | 57% | +0.67% | +0.48% | +1.35 |
| Jev forced (from the open) | 29 | 52% | +0.69% | +0.69% | +1.70 |
| Claude | 37 | 51% | +0.30% | +0.33% | +0.48 |
| DeepSeek | 34 | 41% | −0.13% | −0.09% | −0.34 |
| Gemini | 26 | 50% | −0.17% | −0.08% | −0.80 |
| Council Top 2 | 23 | 43% | −0.30% | −0.16% | −0.39 |
| Engine | 23 | 39% | −0.12% | −0.10% | −0.27 |

## The news desk, on every window (our own `data/news_calls.csv`, FULL arm)

| Window | Calls | Right | Mean |
|---|---:|---:|---:|
| prior close → open, against XIU (the gap) | 91 | 52% | +0.12% |
| open → close, raw (the sheet's number) | 91 | 57% | +0.67% |
| open → close, against XIU | 91 | 57% | +0.45% |
| **09:45 → close, against XIU (tradable on its call)** | **88** | **47%** | **+0.10%** |

* **Where the sheet's +0.67% comes from:**
  * about +0.21% is the market rising on the days it was long (61 of its 91
    calls are LONG);
  * about +0.35% falls between 09:30 and 09:45, before a call exists;
  * +0.10% is after 09:45.
* **The larger sample says the open → close lead is noise.** On the day-122
  replay (419 overnight releases, 2026-07 → 10-01), the same reads from the
  open made +0.09% against XIU (t = 0.71, placebo p = 0.27). Its material calls
  made −0.05%.

## Combinations, on one yardstick (open → close against XIU, each name, side and day once)

| Group | Positions | Right | Mean | t |
|---|---:|---:|---:|---:|
| every position named | 238 | 50% | +0.15% | +0.43 |
| the news desk alone | 89 | 56% | +0.48% | +1.38 |
| 2+ model sources agreeing | 21 | 48% | +0.79% | +1.53 |
| one model source | 86 | 48% | −0.06% | −0.21 |
| Jev forced with another source | 10 | 60% | +1.55% | +1.92 |
| the council's Top 2 | 23 | 43% | +0.17% | +0.58 |

* **The news desk and the desks barely overlap:** two shared positions in 19
  days.
* **Nothing reaches t = 2, and many slices were tried.** With nine sources,
  the best reaching t ≈ 1.8 by chance happens about one time in three.

## So

* No source and no combination is distinguishable from chance on these 19
  sessions.
* The news desk's lead sits in a window it cannot trade, and is absent on 419
  replayed releases.
* The one change that would make its open → close number tradable is to ask it
  before the open and enter at the open.
  * The replay gives no reason to expect it to pass.
  * The system already records `w_day` for every call, so a forward test of it
    costs nothing.
  * It needs a registration and the owner's decision.
