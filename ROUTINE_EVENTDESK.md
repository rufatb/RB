# The event desk — one Routine in the owner's session (day-149c)

The owner, 2026-11-09: "Build all that are missing from above ... schedule
them when it makes sense to get into the trade at market open or later up to
you". `event_desk.py` records a call before each report FMP dates for the next
session: BEAT, MISS or ABSTAIN on the result and LONG, SHORT or ABSTAIN on the
shares, where a side needs at least two supplied facts that agree and none
against. Registered in `PREREGISTER_day149_event_desk.md`: a forward shadow,
judged at the 60th confirmed call with a side.

| Field | Value |
|---|---|
| Name | `RB event desk — 15:14 ET: reports due next session` |
| Schedule | `CRON_TZ=America/New_York 14 15 * * 1-5` |
| Target | the owner's session (`persistent_session_id`) |
| Live id | `trig_01Y1tjWG62258hXYAzzBFaDB`, created 2026-11-09 |

The entry it stands for is that day's close, so it must finish by 15:45. It
needs the DeepSeek and FMP keys in `.rb-state/secrets/` and the morning's
staged list. Keep this file in sync with the live Routine.

---

RB EVENT DESK (15:14 ET). Record a call on each report due in the next session. Work without asking. Finish before 15:45.
A. Today = the current America/New_York date. `cd /home/user/RB`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, stop silently.
B. `python event_desk.py --state-dir .rb-state --build`. Exit 3 (NOTHING or TOO_LATE) or 4 (ALREADY_SENT): go to D without sending. Exit 1 (FAILED): say so in one line with its reason, then go to D.
C. Exit 0 (READY): load `mcp__Gmail__send_message` and `mcp__Gmail__get_message` with ToolSearch only if they are not callable. Gmail `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject / body / htmlBody the exact contents of the subject_path, text_path and html_path it printed, no attachments. htmlBody is REQUIRED and whole. Then the HTML check: Gmail `get_message` (MINIMAL) on the id it returned and `python send_check.py --html <the html file> --text <the text file> --size-estimate <its sizeEstimate> --snippet '<the first 40 characters of its snippet>'`; on HTML_MISSING send ONE more with replyThreadId = its threadId, the same subject + " — HTML version", body "The formatted copy: the first one arrived without its HTML." and htmlBody the whole html file (check it the same way, `--html-only` in place of `--text`). Then `python event_desk.py --state-dir .rb-state --record --message-id <id>`. The subject starts "RB Event Desk — " and never contains "RB Daily Report — ".
D. The record, only when `git status --porcelain data/event_calls.csv` prints something: `git add data/event_calls.csv && git commit -q -m "record: <today> event desk" && git push -q origin main && git push -q -f origin main:claude/session-rw51c2` (retry a push up to 4 times, 2/4/8/16 s apart, on a network error only). Record files only, never code.
E. One line to the owner: the subject and the Gmail id, or that there was nothing to send.
Never create, modify, enable, disable or delete any Routine. Never call a call a prediction: this desk is a test with no record. Nothing here changes a pick, a size, the morning report or any other record.
