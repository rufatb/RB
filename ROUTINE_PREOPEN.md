# The pre-open desk — one Routine in the owner's session (day-149)

The owner, 2026-11-09: "I can trade US shares also yes", then "Build all that
are missing ... schedule them when it makes sense to get into the trade".
`us_preopen.py` reads the overnight releases on names that also trade in New
York and records DeepSeek's side with the New York price at the read.
Registered in `PREREGISTER_day149_us_preopen.md`: a forward shadow, judged at
40 sessions from the read to the 09:30 open.

| Field | Value |
|---|---|
| Name | `RB pre-open desk — 08:12 ET: read and record the overnight releases (shown in the 09:00 email)` |
| Schedule | `CRON_TZ=America/New_York 12 8 * * 1-5` |
| Target | the owner's session (`persistent_session_id`) |
| Live id | `trig_011Fphbey8QMAHSv4jbMmnDC`, created 2026-11-09; prompt replaced 2026-11-10 (day-150) |

It needs the DeepSeek and FMP keys already in `.rb-state/secrets/`. After a
container reset they are gone until the 08:50 morning Routine writes them, so
that morning's 08:12 read is FAILED; the morning job's own second read (about
08:52, `morning_full.sh`) is then the first. Keep this file in sync with the
live Routine.

**Day-150 (owner, 2026-11-10): it sends no email.** The owner asked for one
decision at 09:00, so the desk's calls are shown in the "RB Morning Decision"
email (`council_flash`), and this Routine only reads, records and pushes
(`us_preopen.EMAIL = False`; amendment 2 of the registration). Every read also
keeps the feed's releases in `data/newswire/press/`, which the desks'
headlines read.

---

RB PRE-OPEN DESK (08:12 ET). Read the overnight releases on names that also trade in New York and record the calls. It sends NO email: the calls are shown in the 09:00 "RB Morning Decision" email, which the 08:50 morning Routine sends (day-150, the owner's request of 2026-11-10). Work without asking. Finish before 08:45.
A. Today = the current America/New_York date. `cd /home/user/RB`. If `python -c "import dashboard,datetime as d,zoneinfo;print(dashboard.is_trading_day(d.datetime.now(zoneinfo.ZoneInfo('America/New_York')).date()))"` prints False, stop silently.
B. `timeout 90 python newswire.py --collect >> .rb-state/newswire.log 2>&1` — the wire, so the desk sees this morning's releases. Any exit code: go on.
C. `python us_preopen.py --state-dir .rb-state --build`. Exit 0 (RECORDED) or 3 (NOTHING or TOO_LATE): go to D. Exit 1 (FAILED): keep its reason for the last line, then go to D. Send no email from this Routine, whatever it prints.
D. The record, only when `git status --porcelain data/us_preopen_calls.csv data/newswire/` prints something: `git add data/us_preopen_calls.csv data/newswire/ && git commit -q -m "record: <today> pre-open desk" && git push -q origin main && git push -q -f origin main:claude/session-rw51c2` (retry a push up to 4 times, 2/4/8/16 s apart, on a network error only). Record files only, never code.
E. One line to the owner: how many calls were recorded and how many of them are material (from the JSON it printed), that they will be in the 09:00 email, or that there was nothing to read, or the failure and its reason.
Never create, modify, enable, disable or delete any Routine. Never call a call a prediction: this desk is a test with no record. Nothing here changes a pick, a size, the morning report or any other record.
