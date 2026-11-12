# PREREGISTER day-151 — the pre-open desk on history (council lab item 9)

Registered 2026-11-12 in the council-lab slot, before any return was computed.
The population is pinned in `data/us_preopen_history_day151.json` (titles,
times and summaries only: no price and no return). The script that runs the
test is committed in its own commit before it runs, next weekday.

## The question

The forward desk (`us_preopen.py`, `PREREGISTER_day149_us_preopen.md`, live
from 2026-11-10) asks it day by day. This asks the same question of the
sessions before the desk existed.

* **The question.** A TSX name that also trades in New York, an overnight
  company release, and DeepSeek reading it before the bell. Between the read
  and the 09:30 open, does the New York listing move the read's way more than
  SPY?
* **Why it matters.** It is the one measured signal on this record. DeepSeek
  calls the gap a release causes (+0.21% a call, t = 2.7, day-122), and the
  TSX open prices it before any entry. The New York listing trades from 04:00
  ET.

## The population (pinned before any price was read)

* **Window.** The 90 TSX sessions from 2026-07-02 to 2026-11-09, the day
  before the forward desk's first morning.
* **Names.** The 81 names in `data/us_twins.json`: the same shares (one
  ISIN) listed on NYSE, Nasdaq or NYSE American.
* **Releases.** The forward desk's own filter (`us_preopen.releases`), run
  on a clock cut at each morning's read:
  * FMP's press feed for the US symbol, fetched by month and served as it
    stood at the read (the newest 15 rows at or before it, `AsOf`);
  * the Canadian wire archive (`data/newswire/`);
  * the title must start with the company's name (`_names_issuer`), and a
    law firm's notice is dropped (`notice`; 348 dropped);
  * at most the newest three releases per name per morning.
* **Reads.** Two per morning, as the live desk does:
  * 08:15 ET, for releases since the prior session's 16:00 close (the 08:12
    Routine);
  * 08:55 ET, for a name first seen after 08:15 (`morning_full.sh`'s second
    read). The first read stands.
* **Counts.** 530 (session, name) events: 508 at 08:15 and 22 at 08:55.
  * They cover 89 of the 90 sessions (median 5 a session, at most 21) and all
    81 names.
  * 466 events have one release, 49 two and 15 three.
  * Of the releases, 538 came from FMP's feed and 71 from the wire archive.
* **Times.** FMP's `publishedDate` is read as Eastern time, as the live desk
  reads it. On the 245 titles found in both sources, FMP's minute equals the
  wire's on 231.
* **Built by** `python us_preopen_history.py --population`: about 4.5
  minutes, about 490 FMP calls, no model call.

## The read

* **The function.** `news_desk.answer(events, 'full', texts)`, with day-122's
  prompt byte for byte (`news_desk.SYSTEM_PROMPT`). This is the forward
  desk's call, prompt version `day122-v1+day149-us-preopen`.
* **What the model reads:** the title and the feed's summary (600
  characters), as live. The release pages refuse automated readers.
* **The model:** `deepseek-v4-pro`, thinking off, as `news_desk.ask` sends it.
  Each read's events are asked together, in the same batches as live.
* **What is kept:** its side (LONG or SHORT), its confidence and whether it
  marked the release material. Asked once; a failed batch is counted, never
  re-asked.

## The price at the read, and the outcome

* **Entry.** The close of the US listing's last one-minute extended-hours
  bar (FMP `historical-chart/1min`, `extended=true`) that ends:
  * at or before the read;
  * no more than 30 minutes before it;
  * after the last release's time, and not before 04:00.

  This is the live desk's third price source. History has no quotes, so its
  first two sources (a quote's mid, the last trade) cannot be replayed. With
  no such bar the call is **unpriced**: counted, never scored. SPY is priced
  the same way at the same read.
* **Exit, the 09:30 open.** The open of the listing's 09:30 five-minute bar,
  and SPY's, via `us_preopen.session_marks`. 09:45 and the close are recorded
  beside it.
* **The measure.** `us_preopen.outcomes`:
  `w_open = side × (open / entry − 1 − (SPY open / SPY entry − 1))`, in %.
  `w_0945` and `w_close` sit beside it.

## The bar (the forward desk's `us_preopen.verdict`, applied once to history)

* **Population.** Material calls with a price whose title is not a notice.
* **Statistic.** The mean of the session means of `w_open`.
* **PASS needs all of these:**
  * t ≥ 3 on the session means;
  * a sign-flip placebo p < 0.01 (10,000 draws, seed 151);
  * both halves of the sessions, in date order, positive;
  * a mean above the cost. History has no recorded quotes, so the cost is
    the desk's own default half-spread (`DEFAULT_HALF`, 0.10%) plus the
    exit's 0.05% (`EXIT_COST`): 0.15% a call.
* **The planted control** (`verdict`'s own): the session means centred and
  moved to +0.5%. If they do not show at t ≥ 3, the verdict is UNDERPOWERED,
  whatever else holds. The smallest effect detectable at 80% power
  (2.8 × the standard error) is printed beside it.
* **Contamination probe** (day-122's `replay_news.probe`, seed 151):
  * DeepSeek is asked the TSX closing price of 30 sampled events on their
    session;
  * a median miss under 2% makes the run VOID;
  * day-122 and day-142 found no memory of 2026-07 → 10 (medians 39–49%).
* **Verdicts:**
  * PASS;
  * NULL: the plant shows but the bar is not met;
  * UNDERPOWERED: the plant does not show;
  * VOID: the probe fails.

  Anything but PASS is rejection #66.

## Beside it, never judged

* `w_0945` and `w_close`.
* The overnight gap on the US listing: side × (open / the prior US close − 1),
  against SPY. This is day-122's measure, moved to New York.
* Splits: material against routine; 08:15 against 08:55; FMP's feed against
  the wire; LONG against SHORT; by month.
* The unpriced share, and why each was unpriced.

## What a result changes

* **Nothing live.** The forward desk keeps its own registered bar (40
  sessions with a call, from the read to the 09:30 open). This replay does
  not move it, shorten it or stop it.
* A PASS goes to the owner as evidence that the forward question has an
  answer on history.
* A NULL or UNDERPOWERED says history does not show it. Whether the forward
  desk runs on is the owner's call, as it was when it was built.

## Not blind, said plainly

* **11-09 is inside the window.** Day-149's dry run asked about 11-09's
  evening releases with a mocked clock (LONG EQX.TO, LONG AAUC.TO). No
  outcome of those calls was computed, but day-148b noted that Equinox's US
  shares were flat after hours on 11-09. Both are re-asked here like every
  other event.
* **The forward desk's first three mornings** (11-10 → 11-12: 0 of 6 right
  to the open, −1.11% a call) are outside the window and are not part of
  this test.

## Cost

* **DeepSeek:** about 110 requests (one per read with an event, batched as
  live).
* **FMP:** about 1,150 bar calls: one-minute and five-minute bars for each
  priced event and SPY per session.
* **No OpenRouter.**
