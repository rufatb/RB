# Day-139 — the news desk asked before the open (owner, 2026-10-24)

Registered BEFORE the first pre-open call was made. Nothing here changes a
pick, a size, the Top 2 or the email.

## Why

The owner's spreadsheet read the news desk as the best source: 52 of 91 right,
+0.67% a call (`AUDIT_day138b_picks_sheet.md`). That lead is measured from the
09:30 open, but the news desk calls at 09:35–09:43, once the overnight window
closes.
* **On the window its calls can trade** (09:45 → close, against XIU): 41 of
  88 right, +0.10%.
* **The difference:** about +0.35% fell between 09:30 and 09:45, and about
  +0.2% was the market.
* **On the day-122 replay** (419 releases, 2026-07 → 10-01), the same reads
  from the open made +0.09% against XIU (t = 0.71). The replay gives no
  reason to expect this to pass.

The owner chose to test the one change that makes the open tradable: ask
before the open, enter at the open.

## What runs

* **When and what.** At 09:20 ET, `news_desk.py --stage-preopen` asks DeepSeek
  v4-pro the FULL-arm question, the day-122 prompt byte for byte
  (`day122-v1`).
* **On which releases.** Each liquid TSX name's releases from the prior
  weekday 16:00 to the time asked. That is day-122's event rule, cut at the
  moment of asking.
* **The guard.** It refuses at or after 09:30, so every call it records existed
  before the open.
* **The record.** Each call goes in `data/news_calls.csv` as arm `preopen`,
  with `asked_at` and prompt version `day122-v1+day139-preopen`.
  * It is never sized, never in the Top 2, never in a prompt and never in the
    email.
  * The full report's Part 6 and the evening review print its running record.
* **A failure** costs this test only, and is logged in `news_desk.log`.

## The measure

* **y** = the call's side × (the stock's open → close minus XIU's open →
  close), in %. That is news_desk's `w_day`, filled by the evening scorer from
  daily bars.
* **The trade it stands for:** a market-on-open order placed before 09:30,
  out at the close.
* **Cost:** the measured 0.13% round trip. An auction order usually costs less;
  0.13% is the conservative figure.

## The bar

* **Decision at 40 sessions** that hold at least one pre-open call (about
  2026-12-18).
* **PASS needs all of:**
  * a mean y > 0 with session-clustered t ≥ 3.0;
  * a sign-flip placebo p < 0.01, with each call's side drawn at random,
    2,000 draws;
  * the same sign in both halves of the sessions;
  * a mean above the 0.13% cost.
* **Power.** At 40 sessions the smallest effect it can detect is about 0.6% a
  call (the replay's sd of session means is 1.04%).
* **Otherwise:**
  * a mean ≤ 0 at 40 sessions → FAIL, stop;
  * a positive mean short of the bar → UNDERPOWERED. The test runs on to 80
    sessions, for one final look at the same bar.
* **The bar does not move,** and nothing is tuned in between: no prompt, no
  window and no filter.

## Descriptive only (never a verdict)

* the same calls' 09:45 → close (`w945`) and five-session (`w5d`) windows;
* material against routine calls;
* agreement with the 09:31 FULL arm on the same releases;
* the releases published 09:20–09:30, which this arm cannot see, counted.

## What follows

* **PASS.** A pre-open news email at about 09:22, and the reads as a council
  input, are proposed to the owner and registered separately.
* **FAIL, or UNDERPOWERED at 80 sessions.** The arm is retired as a rejection.
