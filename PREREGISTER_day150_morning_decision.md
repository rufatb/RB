# Day-150 — one decision at 09:00, one check at 09:31 (owner, 2026-11-10)

Registered on 2026-11-10 at about 14:00 ET, before any of it ran on a live
morning. The first live morning is 2026-11-11. Nothing here is a test of
accuracy, and none is claimed.

## The owner's words

After the 09:00 flash of 11-10 (LONG AC.TO, Claude 0.40, council 0 of 4; SHORT
SU.TO, Claude 0.38, council 3 of 4) and the 08:23 pre-open desk email:

> "i got this at 9am, i dont think these are good picks, and the 8:12 am was
> much more elaborate and better quality picks whats going on here? and can we
> combine them so that i get one good quality decision by 9am? and another at
> 9:31 because it would look at the data points and technicals at market open
> to adjust if needed in case it already spiked or tanked that would affect our
> decision tree and trading for intraday."

I set out four changes and asked one decision: whether a weak pick should be
dropped, which reverses part of the 10-30 choice (day-144). The owner: "Yes".

## 1. The quality floor (`council.FLOOR = True`, rule `day150-floor`)

* **Where.** Only on the Top 2 led by Claude (`council.claude_top_two`), after
  the three-day-run rule has chosen Claude's pick on each side.
* **The rule.** A pick stands when either holds:
  * Claude's own confidence in that nomination is 0.50 or higher
    (`FLOOR_CONFIDENCE`);
  * two or more members endorse it on the council's final tally
    (`FLOOR_ENDORSE`; the count the email prints as "N of 4 endorse", Claude's
    own ballot included).
* **Otherwise that side reads "no pick".** Nothing stands in its place:
  Claude's second nomination is not tried. Day-145c found a first-named
  nomination no better than a second.
* **A morning the council did not sit:** only the confidence leg can apply.
* **The council's own Top 2** (Claude's picks missing) and the counted
  fallback already need two models, and are unchanged.
* **Kept on the record.** A dropped pick is shown ("below the quality floor")
  and recorded as `top2floor/pick`: a shadow, never sized, never pooled, out
  of the lab and the scoreboard. The review scores it in its own section.
* **Splits from 2026-11-11.** The `top2` rows carry `+day150-floor`. Day-144's
  comparison and day-140 arm A read the same rows; split them by
  `prompt_version`.
* **Judged forward.** Over sessions with a dropped pick, the dropped picks'
  mean from 09:45 to the close, clustered by session:
  * harm check at 20 such sessions: t ≥ 2 (the floor is removing winners) →
    tell the owner;
  * at 40: t ≤ −3 with a sign-flip placebo p < 0.01 (seed 150) and both halves
    negative → the floor removes losers; anything else → it has only made the
    Top 2 smaller.
* **Not claimed:** that it raises accuracy. On 11-10 it would have dropped
  LONG AC.TO and kept SHORT SU.TO.

## 2. The press feed in the desks' and the council's inputs

* **The gap.** The desks, the nominations and the council read headlines from
  Yahoo and from the newswire.ca archive. The pre-open desk's source, FMP's
  press feed for a name's New York symbol, never reached them.
* **The archive.** `data/newswire/press/YYYY-MM-DD.jsonl`
  (`press_feed.py`), one row per release: url, title, published_at (FMP's
  time, ET), the Toronto ticker, the feed's summary. A row is kept only when
  it passes the pre-open desk's two tests: the title starts with the
  company's name (`us_preopen._names_issuer`) and it is not a third party's
  notice (`us_preopen.notice`). It is written whenever the pre-open desk reads
  the feed.
* **Into the headlines.** `prepare_deepseek.refresh_public_inputs` merges each
  name's press rows of the last 72 hours into the staged headlines, after the
  wire's. The class is recomputed, never trusted:
  `factor_news.classify_headline` labels a headline ISSUER_RELEASE when the
  press archive holds that URL with that exact title, with the feed's time as
  `first_disclosed`.
* **Unchanged.** The prompts, byte for byte; the headline fields; the cap per
  name. The models read the title, as they do for a wire release.
* **The registered populations do not move.** The wire card, the news desk
  (Part 6 and day-139) and PEAD read `data/newswire/*.jsonl` only; the press
  rows sit in a subdirectory those readers never open.
* **Coverage.** The 81 names with a New York listing. FMP's feed answers
  nothing for a Toronto symbol (checked 11-10 on six names).
* **Not claimed:** any accuracy gain. Day-118/122/142: the open prices a
  release.

## 3. The pre-open desk (amendment 2 to `PREREGISTER_day149_us_preopen.md`)

* **No email of its own** (`us_preopen.EMAIL = False`). The 08:12 Routine
  reads, records and pushes as before. Its calls are shown in the 09:00 email.
* **A second read at about 08:52,** inside the morning job, for names with a
  release published since the first read. The first recorded answer on a name
  still stands and is never re-asked. Each call keeps its own read time and its
  own New York price at that read.
* **Unchanged:** the question, the price rule, the measure (side × the New York
  09:30 open ÷ the price at the read − 1, less SPY's), the bar and the
  decision at 40 sessions.

## 4. The 09:00 email (`council_flash.COMBINED = True`)

* **Subject:** "RB Morning Decision — DATE — …". It never contains "RB Daily
  Report — ".
* **On top, the decision:** each side's pick that stands, or "no long today" /
  "no short today" with the reason; then the overnight releases with a call,
  named as a separate read.
* **Then one table:** Claude's picks (standing or dropped) with the council's
  vote, and each overnight release with a material call: the call, the
  release, the New York price just before the email and its move since the US
  close, and the council's vote where that position was on its table.
* **Under it:** the lines the flash carried (the cautions, the members' votes,
  the council's own choice, exposure, passed-over picks).
* **The New York prices** are read again when the email is composed. The
  ledger keeps the price at the read; the record is unchanged.
* **Fallbacks.**
  * The council's own Top 2 stands (Claude's picks missing): its table as
    before, and the releases in a table below.
  * No council by 09:20: the email goes with the releases alone and says so.
  * No release with a call: the decision alone.
* **Display only:** it records nothing and changes no pick.

## 5. The 09:31 email

* **Subject:** "RB Open Check — DATE — KEEP LONG X · DROP SHORT Y".
* **One verdict per pick,** by fixed rules on FMP's live quote (stamped today
  at or after 09:30), in this order:
  1. no live quote → CAUTION (not checked);
  2. the price is past the pick's own "wrong if" (day-120's E1) → DROP;
  3. the price has moved one normal day (ATR, from the morning's brief) or
     more from the prior close, either way → CAUTION ("already moved its way:
     an entry now does not get that part", or "already moved against it");
  4. otherwise → KEEP.
  With no normal range for the name, rules 1, 2 and 4 apply and the row says
  so.
* **Each row shows** the open against the prior close, the price now, both in
  normal days, the move against its sector fund, and how far its "wrong if"
  is.
* **The overnight releases** get no verdict. Their own window ended at the
  open. Each row says where the Toronto listing opened against the read.
* **KEEP is not a forecast.** On this record a move already made is a reason
  in neither direction (day-132), and the email says so.
* **Recorded,** one row per pick, in `data/reviews/open_checks.csv` (the
  evening push carries `data/reviews/`). At 40 sessions the picks' 09:45 →
  close is read by verdict, as a description. No rule follows from it without
  its own registration.
* **Nothing is voided:** the 09:46 report keeps every pick the 09:00 email
  named (day-144).

## What does not change

* The desks, their prompts, the council's prompt, rounds and tally.
* The three-day-run rule, the hedge line, the cautions.
* The report at 09:46, apart from the floor in its Top 2.
* The sizes: the Top 2 is never sized.

## Tests

`tests/conftest.py` runs the suite with the three switches as they were
(`council.FLOOR`, `council_flash.COMBINED`, `us_preopen.EMAIL`). Tests marked
`day150` run on the production values.
