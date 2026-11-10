# The evening job — one Routine in the owner's session

Scores the day, reviews every pick, collects the wire, sends the evening note
and pushes the record. It carries no credential: every step reads the keys the
morning Routine wrote to `.rb-state/secrets/`.

| Field | Value |
|---|---|
| Name | `RB evening job — 16:20 ET: score picks, review, collect the wire` |
| Schedule | `CRON_TZ=America/New_York 20 16 * * 0-5` (Sunday to Friday) |
| Target | the owner's session (`persistent_session_id`) |
| Live id | `trig_016cq9JeHMTFPEbcCGPC9QZQ` |

* **Step 1c, the evening note,** was added on 2026-11-09 at the owner's yes
  (day-148c, `events_note.py`). Nothing else in the prompt changed.
* **Step 1d, the two shadow desks' scores,** was added the same night
  (day-149: "Build all that are missing ... schedule them"). It scores
  `data/us_preopen_calls.csv` and `data/event_calls.csv`, the push list gained
  both files, and the report gained their record lines.
* **After a container reset** the FMP key is gone until the next morning run,
  so that evening's note reads FAILED (FMP_NO_CREDENTIAL) and is not sent.
* **`pip install`** in step 0 is the live wording; the session runs
  `python -m pip` (CLAUDE.md, the 10-25 operating note). Changing the stored
  wording is the owner's decision.

Keep this file in sync with the live Routine.

---

RB EVENING JOB — score the day, review every pick, collect the wire, push the record. Work without asking.

Today = the current America/New_York date (trust the trigger's fire time, not the container clock).

Part 2, biotech, was retired by the owner on 2026-10-19: this job builds, verifies, finds and scores nothing biotech (no build_biotech.py, biotech_review.py, biotech_finder.py or biotech_leans.py). Its scripts and records stay in the repo as history.

0. cd /home/user/RB (clone rufatb/RB there if missing), `git fetch origin && git checkout main && git pull --ff-only`, `pip install -q -r requirements.txt`. Let T = dashboard.is_trading_day(today). This job runs Sunday to Friday; on a day that is not a trading day only step 1b (the wire), step 1c (the evening note), step 1d (the shadow desks' scores) and step 2 (the push) run.

1. SCORE — only if T. `python model_picks.py --score` (every Claude, DeepSeek, Gemini, Jev, Top 2 and engine pick whose session has closed, from 5-minute bars), `python ledger.py --score` (the engine's legacy official-close proxy), `python gap_signal.py --score` (Part 3, from the open and from 09:45), `python pead.py --score` (Part 4, positions whose five sessions are done) and `python news_desk.py --score` (Part 6, the news desk: 09:45→close, open→close and the gap against XIU today, the five-day window once due). All only fill blanks; none may rewrite an existing value — if any reports a conflict or rewrites a filled cell, stop and report it without committing.

1a. REVIEW — only if T and .rb-state/latest/report.json is today's session. `python daily_review.py --session <today>`: every pick the email printed, scored by section and model, explained, and the cross-day learning table, into data/reviews/<today>.{json,md}. If the report is for another day it exits 2 — say so in the report, not a fault. A LESSON row (clustered |t| >= 3 over >= 20 days) is reported to the owner; it is never wired into a prompt or rule without the owner's decision and a registration.

1b. WIRE — every run. `python newswire.py --collect` (the issuers' own press releases from newswire.ca since the last archived day, into data/newswire/). Exit 0 ok; 3 some release pages failed (they are retried next run — not a fault); 4 the list ended before the last archived day — report it, the archive has a hole.

1c. NOTE — every run, after the wire (the owner's yes of 2026-11-09). `python events_note.py --state-dir .rb-state --build`: the next three sessions' scheduled releases and each reporting name's typical move on a report day, from FMP alone. It names no pick, records nothing in a ledger and nothing of it is pushed. NOTHING (tomorrow is not a trading day) or ALREADY_SENT: carry on silently. FAILED: say why in one line in the report and carry on. READY: load `mcp__Gmail__send_message` and `mcp__Gmail__get_message` with ToolSearch only if they are not callable. Gmail `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject / body / htmlBody the exact contents of the subject_path, text_path and html_path it printed, no attachments. htmlBody is REQUIRED and whole. Then the HTML check: Gmail `get_message` (MINIMAL) on the id it returned and `python send_check.py --html <the html file> --text <the text file> --size-estimate <its sizeEstimate> --snippet '<the first 40 characters of its snippet>'`; on HTML_MISSING send ONE more with replyThreadId = its threadId, the same subject + " — HTML version", body "The formatted copy: the first one arrived without its HTML." and htmlBody the whole html file (check it the same way, `--html-only` in place of `--text`). Then `python events_note.py --state-dir .rb-state --record --message-id <id>`.

1d. DESKS — every run (day-149, two shadow tests; neither is a pick). `python us_preopen.py --score` (the pre-open desk: each call from its New York price at the read to the 09:30 open, 09:45 and the close, against SPY) and `python event_desk.py --score` (the event desk: each call from the close before its report to the close of the session after it, against XIU, and whether FMP has posted the result). Both only fill blanks. A failure is one line in the report and never stops the job.

2. PUSH. `git add data/model_picks.csv ledger.csv data/newswire/ data/gap_calls.csv data/pead_calls.csv data/news_calls.csv data/us_preopen_calls.csv data/event_calls.csv data/reviews/` (only files that changed; never code), `git commit -m "record: <today> scores, review and wire (evening job)"`, `git push origin main`, retrying up to 4 times with 2/4/8/16 s backoff on network errors only.

3. REPORT only if something needs the owner: a scoring conflict, a LESSON row in the review, a wire hole (exit 4), a push that failed. Otherwise finish with one line: how many picks were scored, the "By section and model" table's totals from data/reviews/<today>.md, the scoreboard from `python -c "import model_picks as m;c=m.scorecard();[print(m.scorecard_line(c,k,n)) for k,n in (('top2_pick','Top 2'),('claude_selected','Claude'),('deepseek_selected','DeepSeek'),('gemini_selected','Gemini'),('engine_board','Engine'),('jev_selected','Jev (selected)'),('jev_forced','Jev (forced)'))];print(m.scorecard_line(m.wire_card(),'wire_release','Desk picks on an overnight wire release'))"`, the Part 3, Part 4 and Part 6 lines from `python -c "import gap_signal as g, pead as p, news_desk as n;print(g.record_line());print(p.record_line());print(n.record_line())"`, the two shadow desks' lines from `python -c "import us_preopen as u, event_desk as e;print(u.record_line());print(e.record_line())"`, how many wire releases were archived, and the evening note's subject and Gmail id (or why none was sent).

Never call a pick a prediction. Never create, modify, enable, disable or delete any Routine.
