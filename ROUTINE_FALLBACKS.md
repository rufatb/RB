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
| RB bridge warm-up — 09:47 ET | `CRON_TZ=America/New_York 47 9 * * 1-5` | loads the Gmail tools (unchanged) |

Placeholders `<DEEPSEEK_API_KEY>` / `<OPENROUTER_API_KEY>` stand in for the keys
the live prompts carry. Keep this file in sync with them.

## Watchdog prompt

RB MORNING WATCHDOG (09:38 ET). Make sure the owner gets picks before 10:00 even if the 08:50 run died. Work without asking.
A. Today = the current America/New_York date. `cd /home/user/RB`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, stop silently.
B. Gmail `search_threads` `subject:"RB Daily Report — <today>"` (load the Gmail tools with ToolSearch only if they are not callable). If an email for today exists, stop silently — the morning run delivered.
C. If `pgrep -f morning_full.sh` finds the job, stop silently: it is alive and the 09:50 bridge will send whatever it produces.
D. Otherwise the morning run is dead. Write the credentials exactly as the 08:50 prompt's STEP 2 does (DeepSeek `<DEEPSEEK_API_KEY>`, OpenRouter `<OPENROUTER_API_KEY>`, mode 0600, `.rb-state/deepseek_model.txt` = deepseek-v4-pro). Run `python delivery_plan.py --state-dir .rb-state --reason "the 08:50 run died before publication"`. If it says PICKS_ONLY, send that email now (step F). If it says LATE and `.rb-state/late-<today>` does not exist, run `python late_picks.py --state-dir .rb-state/late-<today> --stage` (3–10 minutes; foreground is fine, it is under ten).
E. You are the Claude desk: read `.rb-state/late-<today>/claude_brief.txt` IN FULL, answer it exactly as it instructs, `--check`, fix, `--seal` (late_picks.py). Use only that file.
F. Gmail search again; if still nothing for today, `send_message` ONCE to ["rufat.baghirov97@gmail.com"] with the subject / body / htmlBody files VERBATIM (`late/` or `picks_only/`), no attachments. Both carry the Top 2 section at the top.
G. Push the record: `git add data/model_picks.csv data/biotech_calls.csv && git commit -m "record: <today> fallback picks" && git push origin main` (only those files). Then tell the owner in three lines what died, what was sent (with the Top 2) and the Gmail id.
Never create, modify, enable, disable or delete any Routine. Never call a pick a prediction.

## Bridge prompt

RB MORNING BRIDGE (09:50 ET). The inbox must have today's email before 10:00. Work without asking.
A. Today = the current America/New_York date. `cd /home/user/RB`. Not a trading day (same check as the watchdog) → stop silently.
B. Gmail `search_threads` `subject:"RB Daily Report — <today>"`. If an email for today exists, stop silently.
C. If `pgrep -f morning_full.sh` finds the job still running, run `python morning_wait.py --log .rb-state/morning_full.log --timeout 240` ONCE.
D. Write the credentials (a container restart wipes them): `mkdir -p .rb-state/secrets && chmod 700 .rb-state/secrets`, DeepSeek `<DEEPSEEK_API_KEY>` to `.rb-state/secrets/deepseek_api_key`, OpenRouter `<OPENROUTER_API_KEY>` to `.rb-state/secrets/openrouter_api_key`, both mode 0600, and `deepseek-v4-pro` to `.rb-state/deepseek_model.txt`. Run `python delivery_plan.py --state-dir .rb-state` (add `--reason "<what you observed>"` when the job did not exit 0, 5 or 6).
   REPORT or PICKS_ONLY → step E with the three paths it printed.
   LATE → if `.rb-state/late-<today>/late/subject.txt` exists, use those files; else if `.rb-state/late-<today>/claude_brief.txt` exists, answer, check and seal it as the Claude desk; else run `python late_picks.py --state-dir .rb-state/late-<today> --stage` first, then answer, check and seal.
E. Gmail search again; if still nothing, `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject / body / htmlBody VERBATIM from the files, no attachments. For REPORT, `python gmail_delivery.py --record --message-id <id>`.
   THE 09:58 RULE: at 09:58 ET or later with nothing sent, send at once whatever is ready; if nothing is, send "RB Daily Report — <today> — ⛔ NOT PUBLISHED" with what you observed, then send the picks when ready.
F. REPORT mode: do the 08:50 prompt's STEP 8 (publish the page) and STEP 9 (record and push). Other modes: `git add data/model_picks.csv data/biotech_calls.csv`, commit, push.
G. Tell the owner in a few lines: mode, Gmail id, the Top 2 (side, ticker, how many models back each), each desk's picks (Jev forced only), the biotech calls, anything that broke.
Never create, modify, enable, disable or delete any Routine. Never call a pick a prediction, never average the models.
