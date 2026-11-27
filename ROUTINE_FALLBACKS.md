# The morning's safety net — two Routines in the owner's session

The 08:50 run (`ROUTINE_PROMPT.md`) is the primary. These two fire into the
SAME session. While the 08:50 turn is alive they wait in the queue behind it
and, when it ends, find the email already sent and stop. They only do work
when the primary died — and then they are the reason the owner still has an
email before 10:00.

| Routine | Cron (Eastern) | Job |
|---|---|---|
| RB morning watchdog — 09:38 ET | `CRON_TZ=America/New_York 38 9 * * 1-5` | primary dead? start late picks NOW so they are ready by ~09:48 |
| RB morning bridge — 09:50 ET | `CRON_TZ=America/New_York 50 9 * * 1-5` | nothing sent yet? `delivery_plan.py` and send, by the 09:58 rule |
| RB bridge warm-up — 09:47 ET | `CRON_TZ=America/New_York 47 9 * * 1-5` | loads the Gmail tools, `get_message` included since day-130 |

Placeholders `<DEEPSEEK_API_KEY>` / `<OPENROUTER_API_KEY>` / `<GEMINI_API_KEY>` / `<FMP_API_KEY>` stand in for the keys
the live prompts carry. Keep this file in sync with them.

## Watchdog prompt

RB MORNING WATCHDOG (09:38 ET). Make sure the owner gets picks before 10:00 even if the 08:50 run died. Work without asking.
RESCUE STAND-DOWN: Before starting, and before every email or record push, search Gmail for `subject:"RB Morning Rescue — <today>"`, where today is the America/New_York date; if a returned subject begins exactly `RB Morning Rescue — <today> —`, stop this Routine without starting, sending or pushing. A subject beginning `RB Morning Rescue TEST` is only a test and never a takeover.
A. Today = the current America/New_York date. `cd /home/user/RB`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, stop silently.
B. Gmail `search_threads` `subject:"RB Daily Report — <today>"` (load `mcp__Gmail__send_message`, `mcp__Gmail__search_threads` and `mcp__Gmail__get_message` with ToolSearch only if they are not callable). If an email for today exists, stop silently — the morning run delivered.
C. If `pgrep -f morning_full.sh` finds the job, stop silently: it is alive and the 09:50 bridge will send whatever it produces.
D. Otherwise the morning run is dead. Write the credentials exactly as the 08:50 prompt's STEP 2 does (DeepSeek `<DEEPSEEK_API_KEY>`, OpenRouter `<OPENROUTER_API_KEY>`, Gemini `<GEMINI_API_KEY>` to `.rb-state/secrets/gemini_api_key`, FMP `<FMP_API_KEY>` to `.rb-state/secrets/fmp_api_key`, mode 0600, `.rb-state/deepseek_model.txt` = deepseek-v4-pro). Run `python delivery_plan.py --state-dir .rb-state --reason "the 08:50 run died before publication"`. If it says PICKS_ONLY, send that email now (step F). If it says LATE and `.rb-state/late-<today>` does not exist, run `python late_picks.py --state-dir .rb-state/late-<today> --stage` (3–10 minutes; foreground is fine, it is under ten).
E. You are the Claude desk: read `.rb-state/late-<today>/claude_brief.txt` IN FULL, answer it exactly as it instructs, `--check`, fix, `--seal` (late_picks.py). Use only that file.
F. Gmail search again. When the primary is unclaimed and nothing arrived, send once with the complete subject, text and HTML from the selected fallback files, without attachments. Read the sent message with Gmail `get_message` (MINIMAL) and run `python send_check.py --html <HTML file> --text <text file> --size-estimate <sizeEstimate> --snippet '<first 40 characters of snippet>'`. If the check fails, surface it with the original message ID and keep the primary claim in effect.
G. Push the record: `git add data/model_picks.csv && git commit -m "record: <today> fallback picks" && git push origin main` (only those files). Then tell the owner in three lines what died, what was sent (with the Top 2) and the Gmail id.
Never create, modify, enable, disable or delete any Routine. Never call a pick a prediction.

## Bridge prompt

When the delivery plan returns `RECONCILE`, the primary report has a durable
send claim. Search Sent first; if it is there, verify it and record its id.
If it is not, retry only when `gmail_called` is false: the 08:50 turn that
made the claim has ended by the time this runs, and no Gmail call was ever
started for the report. An empty Sent search alone is never enough. Otherwise
send nothing and flag the delivery to the owner for review.

RB MORNING BRIDGE (09:50 ET). The inbox must have today's email before 10:00. Work without asking.
RESCUE STAND-DOWN: Before starting, and before every email or record push, search Gmail for `subject:"RB Morning Rescue — <today>"`, where today is the America/New_York date; if a returned subject begins exactly `RB Morning Rescue — <today> —`, stop this Routine without starting, sending or pushing. A subject beginning `RB Morning Rescue TEST` is only a test and never a takeover.
A. Today = the current America/New_York date. `cd /home/user/RB`. Not a trading day (same check as the watchdog) → stop silently.
B. Gmail `search_threads` `subject:"RB Daily Report — <today>"`. If an email for today exists, stop silently.
C. If `pgrep -f morning_full.sh` finds the job still running, run `python morning_wait.py --log .rb-state/morning_full.log --timeout 240` ONCE.
D. Write the credentials (a container restart wipes them): `mkdir -p .rb-state/secrets && chmod 700 .rb-state/secrets`, DeepSeek `<DEEPSEEK_API_KEY>` to `.rb-state/secrets/deepseek_api_key`, OpenRouter `<OPENROUTER_API_KEY>` to `.rb-state/secrets/openrouter_api_key`, Gemini `<GEMINI_API_KEY>` to `.rb-state/secrets/gemini_api_key`, FMP `<FMP_API_KEY>` to `.rb-state/secrets/fmp_api_key`, all mode 0600, and `deepseek-v4-pro` to `.rb-state/deepseek_model.txt`. Run `python delivery_plan.py --state-dir .rb-state` (add `--reason "<what you observed>"` when the job did not exit 0, 5 or 6).
   REPORT or PICKS_ONLY → step E with the three paths it printed.
   RECONCILE → the rule above (the 08:50 prompt's STEP 5): Sent first; a retry only with `gmail_called` false, then step E with the three paths it printed; anything else, send nothing and flag it in step G.
   LATE → if `.rb-state/late-<today>/late/subject.txt` exists, use those files; else if `.rb-state/late-<today>/claude_brief.txt` exists, answer, check and seal it as the Claude desk; else run `python late_picks.py --state-dir .rb-state/late-<today> --stage` first, then answer, check and seal.
E. Gmail search again and follow the main routine’s STEP 7 with the exact subject, text and HTML: for REPORT (and a RECONCILE retry), `python gmail_delivery.py --calling` immediately before the send, and send only when it prints CALLING. Read the sent message with Gmail `get_message` (MINIMAL) and run `python send_check.py --html <HTML file> --text <text file> --size-estimate <sizeEstimate> --snippet '<first 40 characters of snippet>'`. For REPORT, record the message ID and verify the actual received News Desk HTML as STEP 7 does (`get_message` RAW, `python received_html.py`, `python news_edition.py verify-delivery`). A failed HTML check is a delivery alert for the existing message.
   THE 09:58 RULE: honour the primary claim, then use the main routine’s single-send fallback rule. The status-only subject is “RB Daily Report — <today> — ⛔ NOT PUBLISHED”. Publish recovered picks on the website.
F. REPORT mode: do the 08:50 prompt's STEP 8 (publish the page) and STEP 9 (record and push). Other modes: `git add data/model_picks.csv`, commit, push.
G. Tell the owner in a few lines: mode, Gmail id, the Top 2 (side, ticker, how many models back each), each desk's picks — Claude, DeepSeek, Gemini, Jev (forced only) —, anything that broke.
Never create, modify, enable, disable or delete any Routine. Never call a pick a prediction, never average the models.
