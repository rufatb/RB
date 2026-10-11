# The noon check — one Routine in the owner's session (day-130)

The owner chose to switch on the noon check on 2026-10-11 ("go on for all").
`noon_check.py` reports where each council pick stands at 12:00 ET. Registered
as H3 in `PREREGISTER_day130_learning.md`: on 379 replay picks, closing at
noon was no worse than holding to 15:55 and swung 15% less.

| Field | Value |
|---|---|
| Name | `RB noon check — 12:00 ET: where the council's picks stand` |
| Schedule | `CRON_TZ=America/New_York 58 11 * * 1-5`; the script waits for 12:00 |
| Target | the owner's session (`persistent_session_id`) |

It needs no credential: the bars come from Yahoo. Keep this file in sync with
the live Routine.

---

RB NOON CHECK (12:00 ET). Tell the owner where today's council picks stand. Work without asking.
A. Today = the current America/New_York date. `cd /home/user/RB`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, stop silently.
B. `python noon_check.py --state-dir .rb-state --wait 600`. Repeat while it prints STILL_WAITING. NOTHING, TOO_LATE or ALREADY_SENT: stop silently. FAILED: say so in one line and stop.
C. READY: load `mcp__Gmail__send_message` and `mcp__Gmail__get_message` with ToolSearch only if they are not callable. Gmail `send_message` ONCE to ["rufat.baghirov97@gmail.com"], subject / body / htmlBody the exact contents of the subject_path, text_path and html_path it printed, no attachments. htmlBody is REQUIRED and whole. Then the HTML check: Gmail `get_message` (METADATA_ONLY) on the id it returned and `python send_check.py --html <the html file> --text <the text file> --size-estimate <its sizeEstimate>`; on HTML_MISSING send ONE more with replyThreadId = its threadId, the same subject + " — HTML version", body "The formatted copy: the first one arrived without its HTML." and htmlBody the whole html file (check it with `--html-only`). Then `python noon_check.py --state-dir .rb-state --record --message-id <id>`.
D. One line to the owner: the subject and the Gmail id.
Never create, modify, enable, disable or delete any Routine. Never call a pick a prediction. Nothing here changes a pick, a size or the record.
