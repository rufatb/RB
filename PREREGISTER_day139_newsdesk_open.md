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

## Review note (2026-10-24, before the first live call; the bar is unchanged)

Muse's review (issue #18) found that the running line printed a per-call mean
beside a t computed on session means. PR #19 made the t test the printed
mean. What the decision computes is pinned here, before any live call is
recorded.
* **The statistic** is the mean of y over calls. t is that mean over its
  session-clustered (cluster-robust) standard error (`preopen_record`,
  PR #19). With equal calls per session it equals the t of the session means.
  The replay figures above (+0.09%, t = 0.71, and the 1.04% sd) were computed
  on session means (`replay_news.clustered`). Where sessions hold unequal
  numbers of calls they are close to this statistic, not the same.
* **The sessions** are the first 40, in date order, that hold at least one
  scored call. If those are UNDERPOWERED, the final look is on the first 80.
* **The placebo** flips each call's sign at random (its side drawn at random)
  and recomputes the same mean: 2,000 draws, seed 139. p is the share of
  draws at or above the real mean.
* **The halves** are the calls of the first and of the last 20 sessions (40
  at the final look), each on the same mean.
* **The cost:** the same mean must exceed 0.13%.

`news_desk.preopen_verdict` (and `news_desk.py --verdict`) computes exactly
this. From the 40th session, the running line prints its verdict.

Two things the text above does not say:
* **The command** is `news_desk.py --preopen`, not `--stage-preopen`. It was
  renamed so that `--stage` still names only the 09:31 step in
  `morning_full.sh`. Nothing else differs.
* **The question and the measure differ.** The day-122 prompt asks for the
  side from 09:45 to the close, and says the open will already reflect the
  release. This test scores the open to the close. Keeping the prompt byte for
  byte is the registered design, so the arm is judged on a window it was not
  asked about. A prompt that asks about the open would be a separate
  registration.

The engineering dry run (10-23's releases, a mocked 09:20 clock, a scratch
ledger) is in `data/dryrun_day139_preopen.json`. It is not a record and not
part of this test.
