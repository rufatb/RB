# The morning rescue — a fresh session, on its own machine (2026-11-11)

**STATUS: CREATED; LIVE CONFIGURATION AND TEST NOT YET VERIFIED.** The owner
approved all three setup steps on 2026-11-11. The existing backup's ID is
`trig_0149j21hvLZnN8zKTBV7NzaQ`; update that Routine rather than creating another.
At the owner's last report, Gmail, the repository and the pinned model were not
configured. The approved repository permission file and five source-prompt
stand-down lines are included in this change. Editing these source files alone
does not update the five stored live prompts or prove the backup works.

**Why it exists.** The morning runs in the owner's persistent session
(`ROUTINE_PROMPT.md`). On 2026-11-11 that session's machine was down from about
08:18 to 09:20 ET: the 08:50 Routine waited in the queue, the morning job
started at 09:23, every staging step was skipped for want of time, and the
09:46 report went out with no model picks. The 09:38 watchdog and 09:50 bridge
are in the same session, so they were down too. Nothing in the code failed.

This Routine fires a FRESH session on a fresh machine. It runs the whole
morning only when the owner's session is not delivering it:

* no "RB Morning Decision", "RB Council Flash", "RB Daily Report" or "RB Morning
  Rescue" email for today in Gmail, **and**
* the owner's session is not connected (`get_session`), or it is connected but
  has sent nothing by 09:12 ET.

When it acts, it first sends a one-line "RB Morning Rescue — DATE" email. That
email is the signal: every Routine in the owner's session searches for it and
stands down (starts nothing, sends nothing, pushes nothing), so the two
machines never both deliver. Before each of its own sends the rescue searches
again, and stands down if the owner's session sent first.

| Field | Value |
|---|---|
| Name | `RB morning rescue — 08:56 ET, fresh session: runs the morning only if the owner's session is down` |
| Schedule | `CRON_TZ=America/New_York 56 8 * * 1-5` (08:56 ET is 05:56 PT, outside the 06:00–09:00 PT window where runs can be delayed) |
| Target | a fresh session per fire (`create_new_session_on_fire`), Gmail connector attached |
| Repository | `rufatb/RB`, reviewed `main`; explicitly clone it if a fresh machine has no checkout |
| Model | `claude-opus-5-5`, as explicitly selected by the owner |
| Its record | pushed if this session can push; always published on the artifact (`record/…`), where the owner's 16:20 evening job imports it (`record_import.py`) |

**What it cannot do.** It cannot answer a council ballot or the Claude desk as
the session (both go through OpenRouter, statelessly, as on any morning). It
cannot run the noon check (the owner's session does, from the imported report).
Its record files that are not on the artifact (`data/news_calls.csv`,
`data/us_preopen_calls.csv`, the wire archive) are lost for that day if its
push is refused; the evening job's own collectors fill the wire again.

**Permission prompts.** The owner approved `.claude/settings.json` with
`permissions.allow` entries for `Bash`, `Artifact`, `mcp__Gmail__search_threads`,
`mcp__Gmail__get_message` and `mcp__Gmail__send_message`. It contains the exact
approved allow-list; it does not attach Gmail or override organization policy.

**One setup test.** A manual verification run sends one message with subject
`RB Morning Rescue TEST — <today>` and a complete HTML body, then reads it back
through the same backup session's Gmail connector. It starts no market research,
publishes no record and sends no takeover announcement. Verify the actual run
and Gmail message IDs before calling the backup ready. The five stand-down
guards explicitly ignore this test subject.

Keep this file in sync with the live Routine. The `<...>` placeholders are the
only difference: the live prompt carries the real keys.

---

RB MORNING RESCUE (08:56 ET, a fresh session on its own machine). The owner's morning runs in their own session at 08:50. If that session is down, you run the morning instead, so the owner still gets picks before the open. Work autonomously; do not ask questions. Never create, modify, enable, disable or delete any Routine. Never call a pick a prediction, never average the models.

A. SYNC. If `/home/user/RB/.git` is missing, `git clone https://github.com/rufatb/RB.git /home/user/RB`; then `cd /home/user/RB` (or the attached rufatb/RB checkout). `git fetch origin && git checkout main && git pull --ff-only`, then `python -m pip install -q -r requirements.txt`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, end with one line. Load the tools NOW with ToolSearch: `select:mcp__Gmail__send_message,mcp__Gmail__search_threads,mcp__Gmail__get_message`, and the session lookup (`get_session`, claude-code-remote) if it is not callable. If Gmail cannot search, read and send from this fresh session, stop with `BACKUP NOT READY: GMAIL UNAVAILABLE`; do not announce a takeover or run research.

B. IS THE OWNER'S SESSION DELIVERING? today = the America/New_York date.
  1. Gmail `search_threads`: `subject:"RB Morning Decision — <today>" OR subject:"RB Council Flash — <today>" OR subject:"RB Daily Report — <today>" OR subject:"RB Morning Rescue — <today>"`. Any result → end with one line: "the owner's session is delivering; nothing to do".
  2. `get_session` with session_id `session_01EJ4EpBx1ragA9hkDR3MMvm`. If its `connection_status` is "connected": run `python rescue_wait.py --seconds 110` and repeat B.1 after each call, until `TZ=America/New_York date +%H:%M` reads 09:12 or later. A result at any point → end with one line. Not connected, or 09:12 with nothing sent → C.

C. ANNOUNCE (this email is the signal the owner's session stands down on). Gmail `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject `RB Morning Rescue — <today> — the scheduled session did not answer; a backup run is preparing today's picks`, body: "Started <HH:MM> ET on a fresh machine because the owner's session was <not connected / connected but had sent nothing by 09:12>. The 09:00 decision, the 09:31 open check and the 09:46 report follow from this run, labelled as usual. Read-only research, not orders." No htmlBody (exempt from the HTML check). Note its message id.

D. CREDENTIALS (this machine has none).
  export RB_STATE_DIR=.rb-state DEEPSEEK_MODEL=deepseek-v4-pro
  mkdir -p .rb-state/secrets && chmod 700 .rb-state/secrets
  printf '%s' '<DEEPSEEK_API_KEY>' > .rb-state/secrets/deepseek_api_key
  printf '%s' '<OPENROUTER_API_KEY>' > .rb-state/secrets/openrouter_api_key
  printf '%s' '<GEMINI_API_KEY>' > .rb-state/secrets/gemini_api_key
  printf '%s' '<FMP_API_KEY>' > .rb-state/secrets/fmp_api_key
  chmod 600 .rb-state/secrets/*
  printf 'deepseek-v4-pro\n' > .rb-state/deepseek_model.txt

E. THE MORNING. Read `ROUTINE_PROMPT.md` (in the checkout) from "THE HTML CHECK" to the end and follow it exactly — STEP 3 to STEP 10 — with these changes:
  - STEP 1 and STEP 2 are done (A and D above).
  - BEFORE EVERY SEND (the decision in STEP 4, the open check in STEP 4, the email in STEP 7): Gmail-search today's subject of that email (`RB Morning Decision — <today>`, `RB Open Check — <today>`, `RB Daily Report — <today>`). If one exists that you did not send, the owner's session is delivering after all: send nothing more, `pkill -f morning_full.sh`, push nothing, and end with one line saying so.
  - STEP 8: publish to the artifact as written, and add `"record/ledger.csv" -> ledger.csv` and `"record/universe_prints.csv" -> universe_prints.csv` to its files. The owner's evening job imports `record/` from there.
  - STEP 9: try the push once with the retries it describes. If it is refused (not a network error), say so in the summary: the artifact copy is the record.
  - STEP 10: start the summary with "RESCUE RUN" and the announcement's Gmail id.
YOUR TURN ENDS ONLY AFTER STEP 10. Ending it earlier gets this machine reclaimed and kills the morning job (2026-09-24).
