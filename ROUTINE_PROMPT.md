# The morning Routine — runs IN THE OWNER'S SESSION

**Why it lives here now (2026-09-28).** The report used to fire a FRESH session
at 08:50. Twice in four mornings (09-24, 09-28) that session ended its turn two
or three minutes in; an idle scheduled session's container is reclaimed and the
background job died with it — no staging, no page, no email, `last_run`
SUCCEEDED. A fresh session also has no Gmail (a Routine made with
`create_trigger` stores no connectors), so even a healthy run needed a second
session to send it.

The owner's interactive session has Gmail, can push, and keeps background work
alive across turns (a one-hour biotech build ran to completion after its turn
ended, 09-27). So the Routine now fires INTO that session
(`persistent_session_id`), which runs the job, answers as the Claude desk,
decides what to send with ONE command (`delivery_plan.py`), sends it, and
pushes the record. Two more Routines in the same session are the safety net —
the 09:38 watchdog and the 09:50 bridge, in `ROUTINE_FALLBACKS.md`.

| Field | Value |
|---|---|
| Name | `RB Daily Report — 08:50 ET in the owner's session: run, seal, email by 09:50` |
| Schedule | `CRON_TZ=America/New_York 50 8 * * 1-5` — Eastern time, so it needs no DST shift. |
| Target | the owner's session (`persistent_session_id`), NOT a fresh session |
| Old fresh-session Routine | `trig_01YZ2smjbMZXJvWKBxU4JfWj` — DISABLED 2026-09-28, kept for its history |

Keep this file in sync with the live Routine. The two `<...>` placeholders in
STEP 2 are the only difference: the live prompt carries the real keys, and this
public repository never does.

---

RB DAILY REPORT — run it, seal Claude's picks, and get an email into the owner's inbox BEFORE 10:00 ET. Work autonomously; do not ask questions.
YOUR TURN ENDS ONLY AFTER STEP 10. While this turn runs, the 09:38 watchdog and the 09:50 bridge wait in the queue behind it; they are the fallback if this turn dies, so do not end it early and do not wait on them.

You fire at 08:50 ET. The report publishes at 09:46 ET and `morning_full.sh` holds itself there. Do not shorten the hold and never run `morning.sh` directly: the staging jobs refuse at or after 09:30 and `wait_for_publication` refuses to wait more than 120 seconds — calling `morning.sh` at 08:50 dies on the second guard with nothing published (2026-09-17).

CONTEXT
The owner is a portfolio manager. This is read-only research: nothing here submits, modifies or cancels a brokerage order, and hypothetical allocation is a research calculation. You are in the rufatb/RB checkout at /home/user/RB; obey CLAUDE.md — especially the house rules, "Read-only, always", and never presenting picks as predictions.

STEP 1 — sync and tools
  cd /home/user/RB && git fetch origin && git checkout main && git pull --ff-only
  pip install -q -r requirements.txt
If the pull refuses because of local changes, `git stash push -m morning-$(date +%F)`, pull again, and say so in the summary.
If dashboard.is_trading_day says today is not a trading day, stop and report "not a trading day — nothing to run". That is a success. Send no email.
Load the Gmail tools NOW: if `mcp__Gmail__send_message` is not callable, run ToolSearch `select:mcp__Gmail__send_message,mcp__Gmail__search_threads`. Loading a deferred tool pauses the turn until "Tool loaded." arrives — at 08:50 that costs nothing; at 09:50 it cost the 09-28 email fourteen minutes. Load nothing else later in the morning.

STEP 2 — credentials (a container restart wipes .rb-state, so write them every morning)
  export RB_STATE_DIR=.rb-state DEEPSEEK_MODEL=deepseek-v4-pro
  mkdir -p .rb-state/secrets && chmod 700 .rb-state/secrets
  printf '%s' '<DEEPSEEK_API_KEY>' > .rb-state/secrets/deepseek_api_key
  printf '%s' '<OPENROUTER_API_KEY>' > .rb-state/secrets/openrouter_api_key
  printf '%s' '<GEMINI_API_KEY>' > .rb-state/secrets/gemini_api_key
  printf '%s' '<FMP_API_KEY>' > .rb-state/secrets/fmp_api_key
  chmod 600 .rb-state/secrets/deepseek_api_key .rb-state/secrets/openrouter_api_key .rb-state/secrets/gemini_api_key .rb-state/secrets/fmp_api_key
  printf 'deepseek-v4-pro\n' > .rb-state/deepseek_model.txt
The DeepSeek account carries ONLY `deepseek-flash` and `deepseek-v4-pro`; the owner chose `deepseek-v4-pro` on 2026-09-29. Jev is `typesafe/jev-1.13` on OpenRouter at POST /api/alpha/decisions; the same OpenRouter key answers Claude's desk and ballot (`anthropic/claude-opus-5.5`, stateless) and the web scout (`perplexity/sonar-pro`). Gemini is `gemini-3.8-flash` on the Gemini API (owner, 2026-10-03). FMP Premium (owner, 2026-10-06) feeds analyst changes, earnings and today's releases into the brief, and the research tools. Do not "correct" any model name.

STEP 3 — start the morning job IN THE BACKGROUND
  ./morning_full.sh > .rb-state/morning_full.log 2>&1
Bash run_in_background with timeout 7200000, exactly ONE copy (check `pgrep -f morning_full.sh` first). The timeout is required: the default background limit is 30 minutes and killed the job at 09:21 on 2026-10-02, before it could publish. It stages the cache, the biotech universe, the factor pool, the issuers' wire releases (newswire.py), the news, the FMP context (day-125: analyst rating changes, earnings, today's scheduled releases — in every model's rows), writes CLAUDE'S BRIEF and has it answered statelessly through OpenRouter (day-126: Claude and Gemini look things up with read-only FMP tools before they answer; DeepSeek answers single-shot), waits for a seal until 09:24, asks DeepSeek, Jev and Gemini, stages the biotech calls, the gap signal, the debate and the post-earnings drift signals, convenes THE COUNCIL (day-124: the four models deliberate on the Top 2, with a web scout's dated, sourced news on each position; Claude's ballot is cast through OpenRouter, yours only as the fallback in STEP 4), reads every overnight release after 09:30 (Part 6, the news desk), holds to 09:44 and hands to `morning.sh`.
Exit codes are morning.sh's own: 0 published; 3 not a trading day; 4 the engine REFUSED on an integrity guard; 5 published but late; 6 published, provenance not clean; 1 failed. Never re-run it and never override a guard — STEP 5 decides what the owner receives whatever the code.
`morning.sh` WILL log "DELIVERY: NOT EMAILED — no SMTP credential". That is expected: a container cannot reach smtp.gmail.com. You send the email in STEP 7 through the Gmail connector.

STEP 4 — CLAUDE'S PICKS (fallback only since day-126), then wait by command
Claude's desk is answered STATELESS through OpenRouter by `morning_full.sh` (day-126: the same brief as DeepSeek and Gemini, the same research round as Gemini, no memory of this session). You answer only if that route fails.
  python claude_opportunities.py --state-dir .rb-state --wait-brief 100
Repeat while it prints STILL_WAITING. NOTHING_TO_ANSWER: the desk is already sealed (normally by the OpenRouter route) — go to the council ballot. PAST_CUTOFF: skip to the wait and say so in the summary.
On READY:
  python claude_opportunities.py --state-dir .rb-state --wait-sealed 200
SEALED: the OpenRouter route answered — go to the council ballot. NOT_SEALED: answer it yourself as the fallback. Read `.rb-state/claude_brief.txt` IN FULL (page through it with offset/limit). Answer exactly as it instructs: at most 2 LONG and 2 SHORT, only its tickers, fewer when the evidence is thin, `confidence` your own honest number (0.5 is a coin flip), one-sentence `reason` naming the supplied values, `basis`, and `invalid_at` from THAT row's own levels on the losing side of its `last`. Use ONLY that file — no other snapshot, report, earlier conversation about today's names, web page, price feed or FMP connector call before you seal.
  python claude_opportunities.py --state-dir .rb-state --check .rb-state/claude_answer.json
  python claude_opportunities.py --state-dir .rb-state --seal .rb-state/claude_answer.json
Seal before 09:24 ET; the first sealed answer stands.
Then THE COUNCIL BALLOT (day-124): the models deliberate on the Top 2 and you are a member.
  python council.py --state-dir .rb-state --wait-ballot 100
Repeat while it prints STILL_WAITING. CLOSED: Claude's ballot was already cast statelessly through OpenRouter (day-126), or the council closed — skip to the wait. On READY (the OpenRouter ballot failed), read `.rb-state/council_brief.txt` IN FULL and answer it exactly as it instructs: a stance on EVERY position id (ENDORSE / OPPOSE / ABSTAIN), conviction 0.5–1 (null for ABSTAIN), one-sentence argument, and top_two. Judge each position on the supplied rows and the other members' arguments; use ONLY that file. Write `.rb-state/claude_ballot_answer.json`, then:
  python council.py --state-dir .rb-state --check-ballot .rb-state/claude_ballot_answer.json
  python council.py --state-dir .rb-state --seal-ballot .rb-state/claude_ballot_answer.json
Seal before 09:27 ET; the first sealed ballot stands.
Then THE COUNCIL FLASH (owner, 2026-10-06): the council's decision by email the moment it is sealed, ahead of the report.
  python council_flash.py --state-dir .rb-state --wait 100
Repeat while it prints STILL_WAITING. READY: Gmail `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject / body / htmlBody the exact contents of the subject_path, text_path and html_path it printed, no attachments; then `python council_flash.py --state-dir .rb-state --record --message-id <id>`. NOTHING, TOO_LATE, ALREADY_SENT or FAILED: send nothing and go on. The flash never replaces the report and never delays it.
Then WAIT BY COMMAND:
  python morning_wait.py --log .rb-state/morning_full.log --timeout 540
RUNNING: run it again immediately. DONE <code>: go to STEP 5 with that code. NOT_STARTED: start STEP 3 now. STALLED: go to STEP 5.
NEVER END YOUR TURN WHILE IT SAYS RUNNING. The one exception is the clock: at 09:50 ET or later (`TZ=America/New_York date +%H:%M`), stop waiting and go to STEP 5 whatever it says — the inbox deadline outranks the job.

STEP 5 — DECIDE WHAT TO SEND, by command
  python delivery_plan.py --state-dir .rb-state --reason "<one phrase: e.g. morning.sh exit 4 — integrity refusal / job still running at 09:50 / job STALLED>"
(Omit --reason when the job exited 0, 5 or 6.) It prints `mode`:
  REPORT      today's report published; `subject_path`, `text_path`, `html_path` are the email → STEP 7
  PICKS_ONLY  no report, but the desks' picks were sealed before the open → the same three paths → STEP 7
  LATE        nothing was sealed → STEP 6
If it says the delivery was ALREADY_ATTEMPTED and Gmail already has today's report, send nothing and continue to STEP 10.

STEP 6 — LATE PICKS (only when STEP 5 said LATE)
  python late_picks.py --state-dir .rb-state/late-$(date +%F) --stage
It takes 3–10 minutes. Read `.rb-state/late-<date>/claude_brief.txt` IN FULL, answer it the same way as STEP 4, write the JSON, then:
  python late_picks.py --state-dir .rb-state/late-<date> --check .rb-state/late-<date>/claude_answer.json
  python late_picks.py --state-dir .rb-state/late-<date> --seal .rb-state/late-<date>/claude_answer.json
The email is `.rb-state/late-<date>/late/{subject.txt,report.txt,report.html}` → STEP 7. If late_picks fails outright, STEP 7 sends the NOT PUBLISHED notice instead.

STEP 7 — EMAIL IT. This is the delivery the owner reads.
Gmail `search_threads` with `subject:"RB Daily Report — <today>"`. If an email for today already exists, send nothing and say so. Otherwise `send_message` ONCE:
  to: ["rufat.baghirov97@gmail.com"]
  subject / body / htmlBody: the exact contents of the subject, text and html files STEP 5 or STEP 6 named. Never reword the subject — it carries the board state.
  no attachments.
For a REPORT email, then record it: `python gmail_delivery.py --record --message-id <id>` (or `--failed` if the send failed).
THE 09:58 RULE: if it is 09:58 ET or later and nothing has been sent, send NOW whatever is ready; if nothing is, send ONE email with subject "RB Daily Report — <today> — ⛔ NOT PUBLISHED" stating what you observed (the job's exit code or last log line, and what delivery_plan said), then carry on and send the picks as a second email when they are ready. The owner must never have an empty inbox at 10:00.

STEP 8 — publish the page (REPORT mode only; skip otherwise)
  - Artifact tool, action "read", url https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9
  - Artifact tool, publish to that url, file_path .rb-state/latest/report_page.html, files:
      "delivery/subject.txt" -> .rb-state/dispatch/subject.txt
      "delivery/report.txt" -> .rb-state/dispatch/report.txt
      "delivery/report.html" -> .rb-state/dispatch/report.html
      "delivery/full_report.html" -> .rb-state/dispatch/full_report.html
      "record/report.json" -> .rb-state/latest/report.json
If `report_page.html` is missing: `python report_page.py --report .rb-state/latest/report.json --output .rb-state/latest/report_page.html`. Never hand-edit it. Retry a failed publish up to three times; it never delays the email, which went first.

STEP 9 — push the record (this session can push; nothing else will)
  python model_picks.py --record-report .rb-state/latest/report.json     (REPORT mode only; it also records Part 3's gap signals)
  git add ledger.csv universe_prints.csv data/model_picks.csv data/biotech_calls.csv data/newswire/ data/gap_calls.csv data/pead_calls.csv data/news_calls.csv
  git commit -m "record: <today> morning (report run)" && git push origin main
Only those files, never code. Retry the push up to 4 times (2/4/8/16 s) on network errors only.

STEP 10 — finish with a SHORT summary, in this order:
  - DELIVERY, one line, never omitted: "emailed <mode> at HH:MM ET, Gmail id <id>" or the exact failure.
  - FLASH, one line: "council flash at HH:MM ET, Gmail id <id>", or why none went out.
  - the job's exit code, and what broke if anything, in plain words (including whether the FMP context was staged, and whether Claude's desk and ballot came through OpenRouter or from you).
  - TOP 2 — the council's decision at the top of the email: side, ticker, its vote ("3 of 4 endorse, 1 object"), who endorsed, who was absent; or "no consensus" with the closest positions. If the council did not sit, say so and give the counted rule's names.
  - PART 1 — each desk in order, Claude, DeepSeek, Gemini, Jev: its picks (side, ticker, status, share count, own confidence, wrong-if, and the wire release beside it if there was one) or its reason. Jev: forced picks only, with "below its own none" where true. Then the scoreboard rows, and the engine's legs as comparison only.
  - PART 2 — each biotech call (ticker, event, side, own confidence).
  - PARTS 3, 4 and 5 — the gap signals, the post-earnings drift signals (new and still held) and the debate's final picks, or why there were none.
  - PART 6 — the news desk: how many overnight releases it read and its MATERIAL calls (side, ticker, own confidence), or why it is unavailable.
  - the link: https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9
Never call a pick a prediction, never average the models, never present agreement as confirmation.

DO NOT TOUCH THE SCHEDULE
Never create, modify, enable, disable or delete any Routine, including this one. If the schedule looks wrong, say so in the summary. The only authorised schedule change is the twice-yearly DST task, which has its own instructions.

IF SOMETHING FAILS
Say so plainly. Never fabricate a board, never re-run a refused publication, never replace a same-day published board, never push code. A DeepSeek, Gemini, Jev, FMP, OpenRouter, scout, council or biotech failure costs its own section — never the email.
