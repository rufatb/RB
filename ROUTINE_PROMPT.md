# The morning Routine, as created in the claude.ai Routines UI

**Why this file exists.** A Routine created through the `create_trigger` MCP
tool stores NO connectors — the server says so outright — so the session it
fires has no Gmail and cannot email the report, however the code is arranged.
A Routine created in the claude.ai Routines UI CAN carry Gmail. That is the
only difference, and it is the whole reason the report reaches an inbox.

Keep this file in sync with the live Routine. If someone edits the Routine in
the UI and not here, this file becomes a confident description of something
that no longer exists.

## Settings to choose in the UI

| Field | Value |
|---|---|
| Name | `RB Daily Report — 09:05 stage, 09:46 publish, email` |
| Schedule | Weekdays (Mon–Fri), **9:05 AM**, timezone **America/New_York** |
| Repository / source | `rufatb/RB`, branch `main` |
| Connectors | **Gmail — enabled.** This is the point of using the UI. Attach NOTHING else: a report task with scheduled-task tools can rewrite its own schedule unattended, and one with Docs tools can create documents nobody asked for. Least privilege, and the prompt forbids both as a second line of defence. |
| Environment | **Must match the environment holding the rb checkout** (`env_01WF9g5xRVHtN38pSVeknCz4`). A task created without it starts with no repository and dies at the `cd` in STEP 1 — verified 2026-09-21: a UI copy's stored `session_request` carried no `environment_id` at all while the original's did. Confirm it before enabling. |
| Auto-approve | **On.** A Gmail send that waits for approval at 09:47 with nobody watching is no email. |
| Session | New session each run |
| Notifications | Push and/or email, as preferred (this channel has never delivered; the Gmail step is the real one) |

**Pick the timezone, not a UTC offset.** The cron behind it does not know about
DST: the existing MCP Routine needs a one-shot correction every March and
November precisely because it is stored as UTC. A timezone-aware schedule in
the UI removes that whole class of failure.

If you do that, the DST correction task will find a schedule it does not
recognise and **change nothing, reporting what it read** — that is the correct
outcome, not a fault, and nobody should later "fix" that task to force a shift
onto a schedule that does not need one. Leave it in place: it is the guard for
the day someone recreates the report on a UTC cron again.

**Disable the old Routine `trig_01YZ2smjbMZXJvWKBxU4JfWj` once this one runs
clean**, or two sessions will race for the same publication minute. The second
will find the session already published — `brief.compute` is publish-once and a
same-day published board wins over a fresh selection — so the record is safe,
but the artifact and the inbox would get two versions of the same morning.

## The prompt

Everything below the line is the prompt, **except** the two `<...>` credential
placeholders in STEP 2. Substitute the real keys when pasting into the UI: the
Routine's own prompt is private storage, this file is a public repository, and
"private credentials and diagnostics stay outside git" is a standing rule here.
GitHub push protection caught the first version of this file with both live
keys in it, which is exactly the rule doing its job.

---

Run the RB daily report for today's session, publish it, update the owner's page, and email it. Work autonomously; do not ask questions.

You fire at 09:05 ET. The report publishes at 09:46 ET, so this session stays alive for about forty minutes and `morning_full.sh` holds it there. THAT HOLD IS THE POINT — do not shorten it, do not background it, do not run `morning.sh` directly. Two guards sit 41 minutes apart and both are correct: the staging jobs refuse at or after 09:30, and `wait_for_publication` refuses to wait more than 120 seconds. A run that calls `morning.sh` at 09:05 dies on the second guard with nothing published and throws away every staged snapshot — that is exactly what happened on 2026-09-17.

CONTEXT
The owner is a portfolio manager. This is read-only research: nothing here submits, modifies or cancels a brokerage order, and hypothetical allocation is a research calculation. cd to the rufatb/rb checkout, then read CLAUDE.md and obey it — especially the ten house rules, "Read-only, always", and the rule never to promise accuracy or present picks as predictions.

STEP 1 — sync
  git fetch origin && git checkout main && git pull --ff-only
  pip install -q -r requirements.txt
If dashboard.is_trading_day says today is not a trading day, stop and report "not a trading day — nothing to run". That is a success. Send no email.

STEP 2 — credentials (never committed; .rb-state is gitignored, so a fresh container has NONE)
  export RB_STATE_DIR=.rb-state DEEPSEEK_MODEL=deepseek-flash
  mkdir -p .rb-state/secrets && chmod 700 .rb-state/secrets
  printf '%s' '<DEEPSEEK_API_KEY>' > .rb-state/secrets/deepseek_api_key
  printf '%s' '<OPENROUTER_API_KEY>' > .rb-state/secrets/openrouter_api_key
  chmod 600 .rb-state/secrets/deepseek_api_key .rb-state/secrets/openrouter_api_key
  printf 'deepseek-flash\n' > .rb-state/deepseek_model.txt
The DeepSeek account carries ONLY `deepseek-flash` and `deepseek-v4-pro` — `deepseek-chat` and `deepseek-reasoner` DO NOT EXIST on it. Jev is `typesafe/jev-1.13` on OpenRouter, reached at POST /api/alpha/decisions, NOT /chat/completions; `typesafe/jev-latest` is NOT a valid id. Do not "correct" either model name — a floating alias that 400s every morning looks exactly like an outage.

STEP 3 — stage, hold, publish. ONE command, and it will take about forty minutes:
  ./morning_full.sh
It stages the intraday cache, the biotech universe, the 130-name factor pool, the news/macro refresh, the DeepSeek factor snapshot, the DeepSeek opportunity ranking and the Jev ranking while that is still permitted, holds the session to 09:44, then hands over to `morning.sh`. Let it run to completion.
Exit codes are morning.sh's own: 0 published; 3 not a trading day; 4 the engine REFUSED on an integrity guard; 5 published but missed the window (informational); 6 published but provenance was not clean; 1 failed. On exit 4 do NOT re-run and do NOT override the guard — report the reason and stop.
A staging step exiting 2 means partial coverage, which is the ordinary result, not a fault. Exiting 3 means it correctly refused because its pre-open cutoff had passed — report it, do not retry. A step logged SKIPPED means an upstream step overran and ate its share of the 09:05–09:30 budget; name which one, because that is a different cause from a provider outage.
`morning.sh` WILL log "DELIVERY: NOT EMAILED — no SMTP credential". THAT IS EXPECTED AND IS NOT THE EMAIL. A Claude Code container cannot reach smtp.gmail.com on 25, 465 or 587 — measured 2026-09-20; the agent proxy tunnels HTTPS only. Do NOT try to fix it and do NOT write an app password. You send the email in STEP 7 through the Gmail connector.

STEP 4 — the page is written BY THE JOB, never by hand
`daily_job` writes `.rb-state/latest/report_page.html` itself. Use that file. If and only if it is missing:
  python report_page.py --report .rb-state/latest/report.json --output .rb-state/latest/report_page.html
Do NOT hand-edit its output and do NOT write your own HTML. This renderer enforces every rule that matters: no share count or dollar allocation on an ABSTAIN leg, the not-an-entry banner, the factor section, the DeepSeek opportunities section, the Jev opportunities section, the gap lines. If something looks wrong, say so in the summary and leave it — a hand-edited page is how a size reaches an abstained row, and that has been acted on twice.

STEP 5 — build the email payload from the frozen publication
  session=$(TZ=America/Toronto date +%F)
  python gmail_delivery.py --prepare --session "$session"
It prints `subject`, `subject_path`, `text_path`, `html_path`, `attachments[]`, `unsendable_attachments[]` and `gaps[]`, and CLAIMS the delivery so a re-run cannot send twice. An attachment lands in `unsendable_attachments` when its base64 is too large for a tool call to carry — which is the normal case for the full report, ~464k characters. When that happens the step has ALREADY appended a labelled delivery note to `report.txt` and `report.html` saying there is no attachment and where the full report is, so send those files as they now stand and send NO attachment. Do not try to paste a large `.b64` file: it cannot fit, and a truncated attachment is worse than an absent one. Exit 4 means ALREADY_ATTEMPTED — do not send, report it, SKIP STEP 7 ENTIRELY and continue to STEP 8 (the summary). STEP 7 is the send; routing an already-attempted delivery into it sends the morning twice, which is the whole thing the claim exists to prevent. It refuses before 09:46 ET by design. If it fails outright, say so and still do STEP 6 so the page is published.

STEP 6 — publish the page and the payload to the owner's artifact, same URL:
  - Artifact tool, action "read", url https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9
  - Artifact tool, publish with that same url, file_path .rb-state/latest/report_page.html, and files:
      "delivery/subject.txt"      -> .rb-state/dispatch/subject.txt
      "delivery/report.txt"       -> .rb-state/dispatch/report.txt
      "delivery/report.html"      -> .rb-state/dispatch/report.html
      "delivery/full_report.html" -> .rb-state/dispatch/full_report.html
Reading first is required before publishing to an artifact this session did not create. If the publish fails, retry up to three times; if it still fails, say so as the FIRST line of the summary and carry on to the email.

STEP 7 — EMAIL IT. This is the delivery the owner actually reads.
Call the Gmail `send_message` tool ONCE:
  to: ["rufat.baghirov97@gmail.com"]
  subject: the exact contents of `.rb-state/dispatch/subject.txt`. Do not add a prefix, do not reword it, do not rebuild it. It carries the board state — "⛔ DO NOT TRADE — all N legs ABSTAINED", "SCAN UNAVAILABLE", "INFORMATIONAL" — derived from the frozen report by `subject_state`. A sender that writes its own subject is a second implementation of that rule, and a neutral-looking subject over a board nobody should act on is the exact failure it exists to prevent.
  body: the exact contents of `.rb-state/dispatch/report.txt`
  htmlBody: the exact contents of `.rb-state/dispatch/report.html`
  attachments: ONE ENTRY PER ROW OF `attachments[]` ONLY — filename from its `filename`, mimeType from its `mime_type`, content = the exact contents of its `.b64` file, which is ALREADY base64: do not re-encode it, do not truncate it, do not summarise it. If `attachments[]` is empty, SEND NO ATTACHMENTS AND DO NOT MENTION ONE; the rows in `unsendable_attachments[]` are too large for a tool call to carry, the body already says so and links the published copy, and a truncated or summarised attachment is a corrupted record. Never hand-build base64 and never paste part of a file.
Then record the outcome:
  python gmail_delivery.py --record --session "$session" --message-id <the id the tool returned>
If the send fails: `python gmail_delivery.py --record --session "$session" --failed`, and say so plainly. A missing row and a failed send are different facts.
If the Gmail tool is not available to you at all, say that as the FIRST line of the summary — it means this Routine lost its connector grant and the owner must re-attach Gmail in the Routines UI.

STEP 8 — finish with a SHORT summary. In this order:
  - published on time / informational-late / refused, and the exit code
  - DELIVERY, one line, never omitted: "emailed to rufat.baghirov97@gmail.com, Gmail id <id>", or the exact failure. The owner went weeks receiving nothing while runs reported success; a summary without this line is how that happened.
  - every leg: ticker, side, status, 09:45 reference price. If all are ABSTAIN, say plainly there is no actionable entry today.
  - DEEPSEEK OPPORTUNITIES — read `.rb-state/latest/report.json` at `intraday.opportunities`. Name each pick: side, ticker, its self-reported confidence, and whether the engine agreed (`comparison.rows[].verdict`, or "engine comparison unavailable"). Say in the same breath that the confidence is SELF-REPORTED and NOT a calibrated win probability — no track record, never scored against an outcome. Give `evidence`: how many names carried news and which macro fields were shown, because a ranking made on prices alone and one made with the morning's tape are different readings. NO_OPPORTUNITY is a tested abstention, not a failure; UNAVAILABLE means quote the reason verbatim.
  - JEV OPPORTUNITIES — read `intraday.jev`. Jev is a second model and a DECISIONS model: the option set IS the candidate list, and a name is SELECTED only when it beat the probability Jev itself assigned to picking nothing. Report BOTH of these, and never merge them:
      (a) SELECTED — `longs` and `shorts`. For each: side, ticker, its probability AND that abstain probability, plus `versus_deepseek.rows[].verdict`.
      (b) RANKED — `long_ranked` and `short_ranked`, which are present EVERY day including days nothing is selected. For each: position, ticker, probability, the abstain probability, and `cleared_gate`. Introduce them as "Jev's highest-ranked names — a ranking, NOT a selection", and say plainly of any row with `cleared_gate: false` that Jev rated it BELOW its own "none of these" option. A ranked name is not a pick and must never be reported as one.
      (c) FORCED — `forced_long` and `forced_short`, ALWAYS present and never null on a healthy run. This is the answer to a SECOND, DIFFERENT question, whose option set had no "none of these" in it, so Jev had to name something. Give the ticker, its `probability`, the `gated_abstain_probability` beside it, and `cleared_gated_abstain`. Introduce it as "forced choice — the best of the set, which on a quiet day is the least bad of a bad set", and when `cleared_gated_abstain` is false say outright that Jev rated this below its own abstain and would rather have done nothing. NEVER present a forced pick as a selection, never merge it into (a), and never drop the caveat to make the section read more decisively.
    State that these are Jev's OWN numbers, not calibrated win probabilities. Then one line: how many names the two models agreed on, contradicted on, and `versus_deepseek.deepseek_only`. If Jev selected nothing on both sides, say so, say it is the registered gate working — the gate has no dial — and still give the ranking. NEVER average the two models: averaging two unmeasured opinions makes a third that looks better than either.
  - the population in one line: how many names were staged into the pool and how many carried complete technicals. Before day-111b this was 38 names, identical day after day, because the MACD warm-up — not the roster — was the binding constraint. If it reads 38 again, SAY SO: it means the daily-bar pass did not run.
  - the factor layer in one line: model, how many of the pool were assessed, how many cleared the threshold. If none cleared, say so — that is the normal result. BUT if the assessed count is a small fraction of the pool (2026-09-21 assessed 4 of 273), that is NOT a normal abstention and must be flagged: quote the `DeepSeek batch unavailable:` gap VERBATIM. It now names the exact check that refused — `MULTI_SENTENCE_RATIONALE`, `ROW_COUNT`, a quoted condition — instead of just `ResponseSchemaError`, and the reason decides whether it is a style rule costing coverage or a real provider fault. Same for `headline acquisition failed:` lines, which now carry `RSS_CHANNEL_IDENTITY_MISMATCH`, `RSS_SIZE_LIMIT` and the like rather than a bare `INVALID_PUBLIC_DATA`.
  - the record in one line: hits/legs and rate, and whether the 95% interval still contains 50%.
  - anything that genuinely broke, in plain words.
  - the link: https://claude.ai/artifact/28ZfvwVZG1A2yagxJ4Hyt9
No padding, no encouragement. Never call a pick a prediction, never imply either model or the engine has demonstrated an edge, and never present agreement between the two models as confirmation. If the board is empty, say so and say why.

DO NOT TOUCH THE SCHEDULE
You may have scheduled-task tools (Claude_Code_Remote) attached alongside Gmail. DO NOT USE THEM. Never create, modify, enable, disable or delete any Routine, including this one. If the schedule looks wrong — wrong fire time, a duplicate report task, a cron you did not expect — say so plainly in the summary and STOP. An unattended job that can rewrite its own schedule can also disable itself at 09:05 and nobody would find out until the reports stopped arriving. The ONLY authorised schedule change is the twice-yearly DST correction, and that is a separate one-shot task with its own instructions.
Likewise, do not create documents. The report is the page and the email; nothing else.

IF SOMETHING FAILS
Report it plainly and stop. Never fabricate a board, never re-run a refused publication, never replace a same-day published board with a fresh selection, never push code — only the record CSVs, which morning.sh stages narrowly itself. A DeepSeek, Jev or biotech failure costs its own section and must never stop the report or the email.
