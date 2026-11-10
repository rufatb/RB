# The pre-open desk — one Routine in the owner's session (day-149)

The owner, 2026-11-09: "I can trade US shares also yes", then "Build all that
are missing ... schedule them when it makes sense to get into the trade".
`us_preopen.py` reads the overnight releases on names that also trade in New
York and records DeepSeek's side with the New York price at the read.
Registered in `PREREGISTER_day149_us_preopen.md`: a forward shadow, judged at
40 sessions from the read to the 09:30 open.

| Field | Value |
|---|---|
| Name | `RB pre-open desk — 08:12 ET: overnight releases on New York listings` |
| Schedule | `CRON_TZ=America/New_York 12 8 * * 1-5` |
| Target | the owner's session (`persistent_session_id`) |
| Live id | `trig_011Fphbey8QMAHSv4jbMmnDC`, created 2026-11-09 |

It needs the DeepSeek and FMP keys already in `.rb-state/secrets/`. After a
container reset they are gone until the 08:50 morning Routine writes them, so
that morning's desk reads FAILED and sends nothing. Keep this file in sync
with the live Routine.

---

RB PRE-OPEN DESK (08:12 ET). Read the overnight releases on names that also trade in New York. Work without asking. Finish before 08:45.
A. Today = the current America/New_York date. `cd /home/user/RB`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, stop silently.
B. `timeout 90 python newswire.py --collect >> .rb-state/newswire.log 2>&1` — the wire, so the desk sees this morning's releases. Any exit code: go on.
C. `python us_preopen.py --state-dir .rb-state --build`. Exit 3 (NOTHING or TOO_LATE) or 4 (ALREADY_SENT): go to E without sending. Exit 1 (FAILED): say so in one line with its reason, then go to E.
D. Exit 0 (READY): load `mcp__Gmail__send_message` and `mcp__Gmail__get_message` with ToolSearch only if they are not callable. Gmail `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject / body / htmlBody the exact contents of the subject_path, text_path and html_path it printed, no attachments. htmlBody is REQUIRED and whole. Then the HTML check: Gmail `get_message` (MINIMAL) on the id it returned and `python send_check.py --html <the html file> --text <the text file> --size-estimate <its sizeEstimate> --snippet '<the first 40 characters of its snippet>'`; on HTML_MISSING send ONE more with replyThreadId = its threadId, the same subject + " — HTML version", body "The formatted copy: the first one arrived without its HTML." and htmlBody the whole html file (check it the same way, `--html-only` in place of `--text`). Then `python us_preopen.py --state-dir .rb-state --record --message-id <id>`. The subject starts "RB Pre-Open Desk — " and never contains "RB Daily Report — ".
E. The record, only when `git status --porcelain data/us_preopen_calls.csv data/newswire/` prints something: `git add data/us_preopen_calls.csv data/newswire/ && git commit -q -m "record: <today> pre-open desk" && git push -q origin main && git push -q -f origin main:claude/session-rw51c2` (retry a push up to 4 times, 2/4/8/16 s apart, on a network error only). Record files only, never code.
F. One line to the owner: the subject and the Gmail id, or that there was nothing to send.
Never create, modify, enable, disable or delete any Routine. Never call a call a prediction: this desk is a test with no record. Nothing here changes a pick, a size, the morning report or any other record.
