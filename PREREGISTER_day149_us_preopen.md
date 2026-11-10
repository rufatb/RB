# Day-149 — the pre-open desk: an overnight release, read before the bell, on the New York listing (owner, 2026-11-09)

Registered BEFORE the first call was made. Nothing here changes a pick, a
size, the Top 2, the morning report or any other record. Council lab item 9.

## Why

* **The one measured signal on this record.** DeepSeek, reading an overnight
  release, takes the side of the gap it causes more often than chance:
  +0.21% a call, t = 2.7, placebo p = 0.004, on 420 releases (day-122).
* **Why it earned nothing.** The TSX open has priced the release. From the
  open to the close the same reads made +0.09% (t = 0.71); from 09:45, +0.11%
  (t = 0.83). Day-142 asked about the open directly: +0.11%, t = 0.99.
* **What is left to test.** A name that also trades in New York trades from
  04:00 ET. Between the moment the model reads the release and the 09:30
  open, is anything left?
* **The owner's answers.** 2026-11-09: "I can trade US shares also yes", then
  "Build all that are missing ... schedule them when it makes sense to get
  into the trade".

## What runs

* **When.** 08:12 ET on TSX trading days, a Routine in the owner's session
  (`ROUTINE_PREOPEN.md`). The wire is collected first, then
  `us_preopen.py --build`.
  * By 08:15, 78% of the overnight releases on these names are out (235
    releases, 2026-07 → 11-09; 72% by 07:45, 83% by 08:30). A release after
    the read is not in the test.
  * The run ends before the 08:50 morning Routine.
* **The names.** `data/us_twins.json`, captured 2026-11-09: 81 of the 150
  listed names whose own ISIN also trades on NYSE, NASDAQ or NYSE American
  (FMP `profile` and `search-isin`). The match is the ISIN, never the
  letters: IAG in New York is IAMGOLD, IAG in Toronto is iA Financial.
  * The map changes only by `us_preopen.py --build-twins`, in a commit.
* **The releases.** Published after 16:00 ET on the last TSX trading day and
  before the moment of asking, from two sources, one row per title, the last
  three per name:
  * FMP's press feed for the US symbol, kept only when the title starts with
    the company's name (or the name it titles its releases with,
    `us_preopen.ALIASES`). The feed files a release under every symbol it
    mentions and under look-alike symbols, so a symbol in the text proves
    nothing;
  * the Canadian wire archive (`data/newswire/`), where a release is filed by
    the listing its lead names.
  * A law firm's notice about the company (`us_preopen.NOTICE`) is left out
    and counted.
* **The read.** DeepSeek v4-pro, the day-122 prompt byte for byte
  (`news_desk.SYSTEM_PROMPT`), the FULL-arm item form, asked once.
  * It reads each release's title and summary, not its full text: the release
    pages refuse automated readers (HTTP 403), and nothing is bypassed.
  * Every answered name is recorded. The model's own `material` flag marks
    the calls the test counts.
  * Prompt version `day122-v1+day149-us-preopen`.
* **The price at the read,** taken after the model answers, in this order:
  1. the mid of the New York listing's extended-hours quote, when the quote is
     stamped within the last 10 minutes and is no wider than 1%;
  2. else its last extended-hours trade, when made within the last 30 minutes
     (FMP's trade feed, or failing that the close of its last one-minute
     extended-hours bar);
  3. else no price.
  * Never a price stamped before 04:00 ET today, and never one stamped before
    the newest release: that would hand the test the whole reaction.
  * SPY's price is taken the same way at the same moment.
  * The bid and ask are recorded whenever the quote is today's.
* **The guards.** It refuses at or after 09:30. A call answered at or after
  09:30 is dropped (`ANSWERED_AFTER_THE_OPEN`). On a rerun the first recorded
  answer stands and is not asked again.
* **The record.** `data/us_preopen_calls.csv`, one row per name and session.
  The Routine pushes it after sending; the evening job scores it
  (`us_preopen.py --score`), filling blanks only.
* **The email.** "RB Pre-Open Desk — DATE — …", sent once a day, only when
  the model marked a release as material. Its subject never contains "RB
  Daily Report — ".
* **Never:** sized, in the Top 2, on the desks' scoreboard, in a prompt, or in
  the morning report. No order is placed by anything here.

## The measure

* **y** = the call's side × ((the New York listing's 09:30 open ÷ its price
  at the read − 1) − (SPY's 09:30 open ÷ SPY's price at the read − 1)), in %.
  * The open is the open of FMP's 09:30 five-minute bar.
* **The trade it stands for:** the New York listing bought or sold short
  before the bell at the price at the read, and closed at the 09:30 open.
* **Who counts:** calls the model marked material that have a price at the
  read. A call with no price is recorded, counted and never scored.
* **One number a session:** the mean y of its calls.
* **The cost:** each call's own half-spread at the read (from the recorded
  bid and ask; 0.10% when no quote was recorded), averaged, plus 0.05% for
  the exit at the open.

## The bar

`us_preopen.py --verdict`, at the 40th session that holds a counted call.
* **PASS needs all of:**
  * a mean of the session means above 0 with t ≥ 3.0;
  * a sign-flip placebo p < 0.01 (each session's sign drawn at random, 2,000
    draws, seed 149);
  * both halves of the sessions positive;
  * a mean above the cost.
* **A mean ≤ 0 at 40 sessions** → FAIL, a numbered rejection, and the desk
  stops.
* **A positive mean short of the bar** → the test runs on to 80 sessions with
  a call, for one final look at the same bar. Short again, it is
  UNDERPOWERED when a planted 0.5% does not show at t ≥ 3 on those sessions'
  own noise, else FAIL.
* **The bar does not move,** and nothing is tuned in between: no prompt, no
  window, no filter and no price rule.
* **A PASS goes to the owner as a proposal.** It changes nothing by itself.

## Recorded beside it, never a verdict

* The same call held to 09:45 and to the close on the New York listing
  (`w_0945`, `w_close`).
* The routine calls, and the calls with no price.
* How far the price had already moved since the US close at the read.
* Evening-before releases against same-morning ones.

## Said before the first call

* **Do not expect a pass.** The +0.21% was measured from the prior close.
  By the morning read the US after-hours and pre-market sessions have already
  traded the release, and the pre-market spread on many of these names is
  wider than what could be left.
* **The question and the measure differ,** as on day-139: the prompt asks for
  a side from 09:45 to the close and says the open will price the release.
  It is kept byte for byte because that read is the one that was measured.
* **Title and summary are less than the full text.** On day-122 the title
  alone called the gap at t = 1.7 against 2.7 for the full release.
* **No history test came first.** The wire archive starts 2026-07 and holds
  about 75 pre-market releases on interlisted names: enough to see only a
  large effect. That replay is lab item 9's own step; whatever it shows, this
  forward bar does not move.
* **A US holiday on a TSX trading day** leaves every call without a price.
  They are counted and not scored.
* **The price feeds were checked after hours only.** FMP's extended-hours
  quote and trade endpoints answered at 20:00 ET on 11-09; its one-minute
  bars held that morning's pre-market (55 bars on EQX from 05:07). Whether
  the first two answer before the bell is seen on the first morning. A call
  none of the three can price is counted and not scored.
