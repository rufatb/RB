# Day-142 — the news desk asked about the window it is scored on (council lab item 2)

**Registered 2026-10-28, before any call in this test was made or any return
computed.** Nothing here changes a live pick, prompt, size or the email. The
day-139 forward test runs on unchanged, whatever this finds.

## Why

* **Day-139's question and measure differ.** The pre-open news desk asks
  day-122's prompt byte for byte: a side "from 09:45 ET to the close", with
  "the opening price will already reflect what the release says by 09:45".
  It is scored from the open to the close against XIU (`w_day`). Day-139
  disclosed this and kept the registered design. A prompt about the open was
  to be its own registration; this is it.
* **What history already says.**
  * Day-122's FULL arm, read from the open: +0.09% a call, t = 0.71 (419
    calls, 63 sessions).
  * It reads which way a release points: the overnight gap the release
    caused, +0.21% a call, t = 2.71. The open has priced that.
* **This test asks the question the measure scores, once,** on the same
  releases.
* **It does not re-word a live prompt against a replay.** One wording is fixed
  here before any call. It gets one look, and no other wording follows on
  any result.

## The prompt

`PROMPT_VERSION` is `day122-v1+day142-open`. It is day-122's `SYSTEM_PROMPT`
(`news_desk.py`) with exactly three substitutions, each of which must occur
exactly once:

1. "from 09:45 ET to the close of the same trading day" → "from the opening
   trade at 09:30 ET to the close of the same trading day"
2. "will already reflect what the release says by 09:45." → "will already
   reflect what the release says."
3. "why the move should continue or reverse after that." → "why the move
   should continue or reverse after the open."

Everything else is byte for byte: the materiality paragraph, the confidence
line, the untrusted-data line and the JSON shape. The script asserts the three
substitutions, and that the result no longer contains "09:45".

The first two paragraphs then read:

> You read Canadian company press releases that came out overnight, before the
> 09:30 ET open of the Toronto Stock Exchange. For EACH item, decide which side
> you would take in that company's shares from the opening trade at 09:30 ET
> to the close of the same trading day: LONG or SHORT. You must choose a side
> for every item; there is no abstain.
>
> The opening price will already reflect what the release says. Your reason
> must say, from the release itself, why the move should continue or reverse
> after the open. Judge only what the release says: whether it is good or bad
> news for the shareholders, how large it is relative to the company, and how
> much of it was already expected.

## The population

* **Day-122's.** The news desk's event rule (`news_desk.events`) on every
  session from 2026-07-02 to 2026-10-01, with the holidays of 08-03 and
  09-07 left out, on the committed wire archive. Day-122 found 420 events
  over 63 sessions.
* **Rebuilt now from the same rule and archive.**
  * Yahoo's daily bars are refetched, so a few liquidity decisions may
    differ. The count and any difference from 420 are reported, and the
    population is what the rule gives today.
  * A name whose chart cannot be fetched now (delisted or renamed since) is
    excluded and counted.
  * The calls are two-sided and judged against XIU, so this is not a
    long-only rule on today's list (day-138). The count lost this way is
    reported anyway.
* **The bodies are refetched from newswire.ca.** The cache went with the
  10-26 reset. A failed fetch leaves the item with its title only, and is
  counted.
* **Unchanged from news_desk:**
  * the items, batches (12) and body cut (3,000 characters);
  * the model: `deepseek-v4-pro`, thinking off, JSON mode;
  * the parser.

## The measure and the bar

* **y is `w_day`:** the name's signed open → close minus XIU's, from daily
  bars (`news_desk.outcomes`).
* **The decision is day-139's,** `news_desk._preopen_bar`, over every session
  with a scored call, seed 142, 2,000 draws.
  * PASS needs all of:
    * a mean above 0.13% (the round trip);
    * a session-clustered t ≥ 3;
    * a sign-flip placebo p < 0.01;
    * both halves of the sessions, by date, positive.
  * FAIL: a mean ≤ 0.
  * Otherwise NULL, or UNDERPOWERED if the planted control fails.
* **The planted control** (house rule 10). Every call is centred on the sample
  mean and 0.5% is added; the same t must reach 3. The smallest detectable
  effect at 80% power is reported.
* **The contamination probe** is day-122's: 12 items, asking each name's
  closing price on its session. VOID when the median error is under 2%.
* **One look.**

## Beside the verdict (descriptive, never a verdict)

* **Day-122's prompt, re-asked** on the same items on the same day:
  * its `w_day`;
  * the paired difference, open wording minus 09:45 wording, by event and
    session-clustered;
  * how often the side changes.
* **The gap** (prior close → open) of the new calls: does the new wording
  still read the release's direction?
* The long share; material against routine; confidence ≥ 0.6.

## What follows

* **PASS:** it goes to the owner as a proposal for a second pre-open arm,
  forward and in shadow, under its own registration. Day-139's arm runs on
  unchanged either way.
* **FAIL or NULL:** rejection #58. Day-139's disclosure gets its answer: the
  wording of the window does not change what the desk earns from the open.
* **Files:** the script is `replay_news_open.py`. The summary is
  `data/replay_day142_open_prompt.json`, and the answers are cached in
  `.rb-state/replay/news_open/`.
* **Cost:** about 130 DeepSeek calls (two wordings over about 63 sessions,
  plus the probe). No OpenRouter.
