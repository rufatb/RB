# The council lab: one registered improvement step a weekday

The owner, 2026-10-24: "Continue creative improvements for council picks
logic every morning."

## The slot

* **When.** Weekdays at 10:10 ET, after the morning's email is out, a
  scheduled task in this session ("RB council lab") runs one step of this
  file.
* **Until when.** The step ends by 11:40 ET, so the noon check (11:58) never
  waits behind it.
* **What a step is:** one of
  * write and commit a registration;
  * run a registered test on history;
  * write up a result.

  An idea that needs more than one slot carries on the next weekday.
* **If the morning's delivery is not done** when the slot fires, the slot does
  nothing until it is.

## The rules (the house rules, restated for the slot)

1. **Register first** (`PREREGISTER_*.md`, committed before any return is
   computed). The bar never moves: t ≥ 3 by session plus a placebo, a planted
   control, the smallest detectable effect stated, net of the 0.13% round
   trip.
2. **History before forward.** Test on what is already held:
   * the day-117 replay pools;
   * the day-122 release archive;
   * FMP 5- and 15-minute bars from 2024;
   * ten years of daily bars.

   A forward shadow is only for an idea that passes, or one history cannot
   test.
3. **Never judge a long-only or event rule on today's list** (day-138). Use the
   point-in-time check.
4. **Nothing live changes from the slot.**
   * A passing idea goes to the owner as a proposal.
   * Only a remove-only rule the owner approves goes live, under its own
     registration, as on day-135d and day-137.
   * Prompts are never re-worded against a replay.
5. **No OpenRouter spend without the owner's yes.** That means Claude, the web
   scout and other models. The credit is nearly gone and the mornings need
   it. DeepSeek, FMP and the cached data are fine to use.
6. **Every result is written to:**
   * STRATEGY.md (numbered as a rejection or an adoption);
   * an `AUDIT_` file;
   * CLAUDE.md's top section;
   * the table below.

   Then main is pushed, the session branch mirrors it, and the owner gets a
   five-line note.

## The backlog

Ordered by what a result could change, then by cost.

| # | Idea | Why it might help | What is already known | Test | Cost | Status |
|---|---|---|---|---|---|---|
| 1 | **A stop within reach, on the record** | Day-140 arm A's question on 172 picks instead of ~60 | The forward test can detect only ~1.5–1.9% a pick | The record's desk picks (Claude, DeepSeek, Gemini; selected and nominated; 09-17 → 10-23, 10-15 left out): own level within 1 ATR of the 09:45 entry vs not | None | Done: FAIL, rejection #57 (`AUDIT_day141_reach_history.md`) |
| 2 | **Ask the news desk about the open** | The prompt asks 09:45 → close; day-139 scores open → close | The day-122 reads from the open: +0.09%, t = 0.71 | One registered re-worded prompt, one look, on the 419-release archive (the bodies are refetched from the wire; the probe found no memory of prices) | DeepSeek, ~130 calls (one per session and wording) | Done: NULL, rejection #58 (`AUDIT_day142_newsdesk_open_prompt.md`) |
| 3 | **Skip a pick the open already paid** | The owner's day-138 rule: "the price shouldn't already have changed" | Continuation after a further gap was null (day-132); never tried as a remove-only gate | The record's desk picks whose open gap ran ≥ 1 ATR their way, vs the rest | None | Closed without a test: the record cannot judge it (1 of 189 positions opened ≥ 1 ATR its way), and history (#42) leans against it |
| 4 | **A report-day size rule** | A name reporting before the open swings wider; skipping it is a size rule, like day-137's | Report-day direction was null (#46); size untested | Ten years of daily bars, volume-confirmed report dates (day-135b): next-session sd on report days vs others | None | Done: FAIL, rejection #59 (`AUDIT_day143_report_day.md`): the window swings 1.55× (S&P 500 2.06×), but leans long (t = 2.81) and its placebo reads 1.18× |
| 5 | **One pick a day** | Half the cost, and no same-side stacking | One position per side failed as a size rule (#51); the top pick alone vs two is untested | As written, the record's counted Top 2 (`top2count`): the first slot vs the second. Re-scoped (day-145) to every model's nominations: first-named vs second-named, per model and side, 10-14 → 11-03 | None | Done: NULL, rejection #60 (`AUDIT_day145_best_first.md`): first minus second +0.20% a pick, t = 0.94; a planted 1.0% shows at t = 4.75. Claude's first-named did worse than its second (−0.45%, t = −1.68), not significantly |
| 6 | **Round 1 against the discussion, on history** | Arm B forward needs 40 sessions where both arms pick | The 14 councils before the test (day-140 backfill) show how often the arms differ | A council replay of Round 1 alone, once the day-117 pools are rebuilt (their cache is gone). The backfill: the arms differed on 5 of 12 sessions | DeepSeek and Gemini calls; the discussion's Claude and Jev seats are OpenRouter | Parked (owner, 11-03: Claude leads, so a result would change only a shadow). Day-140 arm B runs on forward |
| 7 | **Weight the desks by their record** | The review's point 5 | No desk's record is beyond \|t\| = 1.1 | — | — | Not before a desk clears a bar |
| 8 | **Claude's reads over longer holds** | The owner, 11-03: "direction didn't come true". A read priced by the open may still be right over days | Holding overnight was worse on the replay (day-130); weeks after earnings, no edge since 2012 (day-135b) | Claude's recorded nominations (10-14 →), scored from the 09:45 entry to the close 1, 3 and 5 sessions later (FMP daily bars), against the same day's close. One registered look | None (FMP) | Done: UNDERPOWERED, rejection #63 (`AUDIT_day147_holds.md`): the pooled model picks (189 over 26 sessions) at three sessions +0.075%, t = 0.17, 95 right; a planted 1.0% shows only at t = 2.50 (smallest detectable 1.73%). One session −0.02%, t = −0.09 (powered); five +0.74%, t = 1.60, all on the short side. Held three sessions against the same day's close: +0.03%, t = 0.30 |
| 9 | **The release on a US listing, before the TSX open** | The one measured signal: a model reading an overnight release calls the gap (+0.21% a call, t = 2.7, day-122), and the TSX open prices it before entry. Interlisted names trade in the US from 04:00 ET | Day-137b sizing: about 75 interlisted pre-market releases from 2026-07 to 10-21; FMP serves US extended-hours 5-minute bars. Liquid names may reprice within minutes, and pre-market spreads are wider | The wire archive's pre-open releases on interlisted names, bodies refetched; Claude (or DeepSeek) reads each; entry on the US listing's first bar after the read, exit at 09:30 (primary), 09:45 and the close; net of a registered pre-market cost | Claude reads about $5 of OpenRouter, or DeepSeek | **Forward desk live from 11-10** (day-149: `us_preopen.py`, `PREREGISTER_day149_us_preopen.md`, the 08:12 ET Routine): DeepSeek's read of each overnight release on the 81 names with a New York listing, with the New York price at the read; judged at 40 sessions with a call, from the read to the 09:30 open. The history replay is registered 11-12 (`PREREGISTER_day151_us_preopen_history.md`; population pinned in `data/us_preopen_history_day151.json` by `us_preopen_history.py --population`): the forward desk's own filter on a clock cut at each morning's read, 2026-07-02 → 11-09, 530 events over 89 sessions on all 81 names (FMP's press feed by month plus the wire archive; 508 read at 08:15, 22 at 08:55). DeepSeek reads each as live; entry the last one-minute extended-hours bar within 30 minutes of the read, exit the 09:30 open, against SPY; the forward bar at seed 151, net of 0.15% a call. **Run 11-13: NULL, rejection #66** (`AUDIT_day151_us_preopen_history.md`): 209 material, priced calls over 72 sessions, read → 09:30 open against SPY −0.27% a session, t = −1.88, placebo p = 0.97, both halves negative; a planted 0.5% shows at t = 3.51. The forward bar is unchanged |
| 10 | **Claude's nominations with reasoning on** | The live Top 2 is one Claude call with reasoning off (`council.ask_claude_openrouter`, max_tokens 4000) | R1 (a reasoning model) and Sonnet 5.5 were no better on the day-117 replay (day-134b); the inputs carry no signal after the open (day-117) | The day-117 replay rebuilt (59 sessions); Claude's nomination question with reasoning on against off, on the day-117 bar; a forward shadow only if it passes | About $35 of OpenRouter | Waiting for the owner: a top-up and a yes |
| 11 | **A council veto on Claude's picks** | Since day-144 the council votes on Claude's picks and cannot replace them; on 11-06 three of four members opposed the long | The council's own choice adds nothing over its table (day-137 M1, t = 0.05); opposition as a gate is untested | Every council position, those with two or more objections against the rest, 09:45 → close; a remove-only proposal if it passes | None | Sized and registered 11-09 (`PREREGISTER_day148_veto.md`; tallies pinned in `data/veto_day148_positions.json`): 239 positions over 23 sessions (10-05 → 10-21 from day-137's tables, 10-26 → 11-09 from the frozen reports), 106 with two or more objections, both groups every session. Not blind: day-137 reported the one-objection split for 10-05 → 10-21. Done 11-11: UNDERPOWERED, rejection #64 (`AUDIT_day148_veto.md`): rest minus vetoed −0.82% a session, t = −2.28, placebo lower p = 0.016, both halves negative; the vetoed positions made +0.50% a session (+0.37% net); a planted 1.0% shows only at t = 2.80 (smallest detectable 1.37%). A veto would have removed winners |
| 12 | **A name's own intraday habit** | Large and published on US data: a stock's past intraday returns persist intraday, and its past overnight returns reverse intraday (Lou, Polk & Skouras 2019). It is known before the open, so it could break ties among Claude's nominations | Untested here. Day-117's field scan had no such field; the level split (overnight against intraday) was rejected on cost (day-87). Expect a few hundredths of a percent a day at best on large caps | The 150 names' cached 15-minute bars (2024-01 → 2026-10): each name's mean 09:45 → close return against XIU over the prior 20 sessions, top fifth against bottom fifth, next session; the overnight version beside it; the point-in-time S&P 500 check on daily bars | None (cached) | Added 11-09 evening (the owner asked for deeper ideas). **Registered 11-16** (`PREREGISTER_day152_intraday_habit.md`): each name's prior-20-session mean 09:45 → close against XIU, top fifth minus bottom fifth on the next session; PERSISTENCE needs t ≥ 3, four blocks, a within-session shuffle placebo p < 0.01 (seed 152), a per-pick edge above 0.13% and both secondary panels positive; a planted 0.10% must show. Anything else is rejection #67. **Done 11-17: UNDERPOWERED, rejection #67** (`AUDIT_day152_intraday_habit.md`): −0.090% a session over 692 sessions, t = −2.52, all four blocks negative (a lean toward reversal, not persistence); a planted 0.10% shows only at t = 2.79. The overnight version +0.02%; the point-in-time S&P 500 +0.006% |
| 13 | **The commodity nowcast** | The owner's pasted "Information Surprise" engine needs an independent estimate; for a commodity producer one exists: last quarter's revenue scaled by the quarter's average commodity price. On 11-09 Equinox's pre-announced ounces times the quarter's gold average gave US$1,068M against a US$987M consensus; it reported US$1,050M | One example, and the shares were flat after hours: the market had done the arithmetic. A surprise's sign matches the reaction 61% of the time (day-148b). FMP holds revenue estimates and actuals back to 2007 for the older names | Miners and oil and gas producers on the list, 2012 → 2026: the side of (nowcast − consensus) beyond a registered threshold, else abstain; the reaction against the sector fund from the close before FMP's date to the close after it; each leg judged alone (day-138's survivor warning) and a point-in-time check on US producers | None (FMP) | Done 11-09 night, at the owner's go: UNDERPOWERED, rejection #65 (`AUDIT_day149_nowcast.md`). Gold and silver producers with a New York listing only (19 names): 159 sided quarters −0.20% a report, t = −0.34; a planted 1.0% shows at t = 1.67 (smallest detectable 2.56%). The nowcast's side matched the revenue surprise 59% of the time (t = 2.37). FMP's revenue consensus agrees between a company's two listings on only 269 of 606 quarters. Oil and copper not tested: no WTI or copper series on the plan |
| 14 | **An event desk with an abstain rule, in shadow** | The pasted engine as a forward test: for each report due in the evening note, a model states consensus, its own estimate and the reason they differ, or abstains | Before a report nothing tested gives a side (previous surprise, peers, run-up: day-138, day-148b). A replay is contaminated for older reports; DeepSeek showed no memory of 2026-07 → 10 (day-122) | Forward: recorded each evening, scored on the surprise's sign and on the reaction against XIU; never sized, never in the Top 2; decided at a registered count of non-abstained calls | DeepSeek; Claude through OpenRouter only with the owner's yes | **Live in shadow from 11-10** (day-149c: `event_desk.py`, `PREREGISTER_day149_event_desk.md`, the 15:14 ET Routine): every report FMP dates for the next session; the model sees no name and no price; a side needs two supplied facts that agree and none against, enforced in code. Judged at the 60th confirmed call with a side, from the close before the report to the close of the session after it. Planted control 5 of 5 with the gate (3 of 5 without it) |
| 15 | **The noon exit, on the live record** | Every Top 2 section prints day-130's note that closing at 12:00 ET "was no worse than holding to the close and swung 15% less", from the day-117 replay; the owner trades the live picks | Day-130 H3 passed on 379 replay picks; the execution lab has measured every live pick's noon exit since 10-11 (and back to 09-17), and the evening review has printed its running comparison | The lab's live positions (pooled kinds, no engine, no shadows), 09-17 → 11-17, each once: 179 positions over 37 sessions. Noon minus close, clustered: mean ≥ −0.05% with t > −2; swing ratio ≥ 1.15 with a session-bootstrap 5th percentile above 1.0; both halves; a planted 0.20% cost must show at t ≥ 3 | None (the committed lab file) | **Registered 11-18** (`PREREGISTER_day153_noon_exit_live.md`). Anything but CONFIRMED is rejection #68; a wording change to the note goes to the owner as a proposal. **Done 11-19: UNDERPOWERED, rejection #68, WORSE flag up** (`AUDIT_day153_noon_exit_live.md`): noon minus close −0.230% a position, t = −2.45, both halves negative; swing ratio 1.22 (bootstrap 5th percentile 1.085); a planted 0.20% shows only at t = 2.13. The afternoon added +0.23%, mostly on shorts. A wording correction to the note is proposed to the owner |
| 16 | **The quality floor, on Claude's past nominations** | The day-150 floor is live and judged forward (harm at 20 sessions with a dropped pick, decision at 40): months away. The record already holds every Claude nomination since 10-14 with its own confidence and its council tally | Day-145c: first-named no better than second, the confidence gap ranks nothing. Day-148: positions with two or more objections did better; every-member endorsement did worst | Claude's nominations 10-14 → 11-19 with a surviving tally (10-22, 10-23 have none): 92 positions over 23 sessions, 67 kept and 25 dropped by the live rule (`council.clears_floor`). Kept minus dropped by day-140's arm A at seed 154; the dropped must lose money net of 0.13%; a planted 1.0% must show at t ≥ 3 | None (the record, the day-148 pin, the frozen reports) | **Registered 11-20** (`PREREGISTER_day154_floor_history.md`; population pinned in `data/floor_day154_positions.json` by `floor_history.py --pin`, no return read). SORTS, REMOVES_WINNERS (dropped beat kept at t ≥ 2, told to the owner), or rejection #69. Runs next weekday; the run code is committed first |

**2026-11-20: item 16 added and registered** (`PREREGISTER_day154_floor_history.md`).
* No free row was left, so the slot added one: does the day-150 quality floor,
  which is live, sort Claude's past nominations?
* The population is pinned from the record and the councils' tallies: 92
  positions over 23 sessions, 67 kept and 25 dropped by `council.clears_floor`.
  Counts only, no return read.
* The run code is committed in its own commit before it runs, next weekday.

**2026-11-19: item 15 ran — UNDERPOWERED, rejection #68, with the WORSE flag up.**
* `noon_exit_live.py` was committed first (5cb0c94), then run once on the
  committed lab file (0.9 s, no cost).
* On the live picks noon swings 18% less, as the replay said, but it gave up
  0.23% a position (t = −2.45), most of it on shorts. A planted 0.20% shows
  only at t = 2.13.
* Day-130's note overstates on the live record. A wording correction goes to
  the owner as a proposal; nothing live changes.
* **Next:** no free row is left again. The next slot proposes a new free item
  and registers it before any return.

**2026-11-18: item 15 added and registered** (`PREREGISTER_day153_noon_exit_live.md`).
* No free row was left (6 parked, 7 waiting for a desk, 10 waiting for the
  owner's yes), so the slot added one: does day-130's noon exit, printed
  under every Top 2, hold on the live picks?
* The committed execution lab only, 179 positions over 37 sessions. Counts
  read, no return.
* `noon_exit_live.py` is committed before it runs, next weekday.

**2026-11-17: item 12 ran — UNDERPOWERED, rejection #67.**
* `intraday_habit.py` was committed first (1973c20), then run once on the
  cached bars (23 s, no cost).
* A name's 20-session habit does not persist from 09:45; it leans slightly
  toward reversal (t = −2.52), short of the bar, and the planted 0.10% shows
  only at t = 2.79.
* **Next:** the backlog has no free row left. Item 10 waits for the owner's
  yes and a budget; item 6 is parked; item 7 waits for a desk to clear a bar.
  The next slot proposes a new free item and registers it before any return.

**2026-11-16: item 12 registered** (`PREREGISTER_day152_intraday_habit.md`).
* A name's own 20-session intraday habit, sorted across the 150 names: does
  the top fifth beat the bottom fifth from 09:45 to the close the next
  session? Cached bars only.
* `intraday_habit.py` is committed before it runs, next weekday.

**2026-11-13: item 9's history replay ran — NULL, rejection #66.**
* The slot fired at 10:26 ET, after the morning's emails had gone out late
  (the connectors were down; CLAUDE.md, Day151b). The run code was committed
  first (3f6f887), then run once.
* By the 08:15 read the US pre-market has traded the release; the rest to
  the open runs slightly against the read (−0.27% a session, t = −1.88).
* **Next:** item 12 (a name's own intraday habit), on the cached bars.

**2026-11-11: item 11 ran — UNDERPOWERED, rejection #64.**
* The machine was down 08:18 → 09:20 ET; the slot ran at 10:14 after the
  morning was delivered.
* The positions two or more members objected to did better, not worse
  (−0.82% a session for the rest against them, t = −2.28). Below the bar
  both ways; no rule.
* **Next:** item 9's history replay (the release on a US listing before the
  TSX open), then item 12.

**2026-11-10: the slot was missed, and the owner changed the Top 2 rule.**
* A worker restart held this session from about 09:50 to 13:31 ET, past the
  slot's 11:40 end. Item 11's run (`council_veto.py`, day-148) carries to
  11-11.
* Outside the lab, at the owner's "Yes": a quality floor on Claude's Top 2
  from 11-11 (day-150: Claude 0.50 or higher, or two council members
  endorsing). It is the owner's decision and does not use item 11's result.
  Item 11's population is pinned and ends 11-09, so the floor does not touch
  it. If item 11 passes, its proposal is weighed against the floor already in
  place.

**2026-11-09 night: the owner said "Build all that are missing from above"**
(day-149). Items 9 (its forward desk), 13 and 14 were built outside the slot,
each registered before its first number:
* **Item 13** ran once: UNDERPOWERED, rejection #65.
* **Items 9 and 14** are forward shadows with their own Routines (08:12 and
  15:14 ET) and their own bars. Nothing live changes from either.
* **The slot's order is unchanged:** item 11 (day-148, #64 if it fails) on
  11-10, then item 9's history replay, then item 12.

**2026-11-09 evening: the owner asked to "think deeper" about opportunities.**
A descriptive pass over 11-09, US CPI days, report days and sentiment found
nothing new on direction (CLAUDE.md, Day148b). Item 12 was added from it.
Item 11 still runs first, on 11-10.
* **The owner can trade US shares**, so item 9 is unblocked and goes next,
  before item 12.
* **OpenRouter** was topped up: $14.30 left at 17:31 ET on 11-09, about 17
  mornings. Item 10 still needs its own yes.

**2026-11-03: the owner keeps Claude leading and the guardrails off, and
wants Claude's picks more accurate.** The backlog is re-aimed at Claude's
picks: item 5 (day-145) ran 11-04 (NULL, #60); 8 (free, day-147) ran 11-06
(UNDERPOWERED, #63); 9 and 10 wait for the owner's answers; 6 is parked; 11 was
registered 11-09 and runs next. OpenRouter credit stood at $8.00 on 11-03,
about 10 mornings at $0.82 a session.

**2026-11-02: Claude leads the Top 2, and the guardrails are off (owner,
day-144).** The council's own choice is now a recorded shadow (`top2council`).
* **Item 4** still runs as registered: its filter is part of its
  registration. A PASS goes to the owner as information, since they chose
  against size rules on 10-30.
* **Items 5 and 6** test the council's own choice, which is now a shadow.
* **The live question** is day-144's forward comparison (`claude_leads.py`).

**2026-10-26: the replay caches are gone.** The container reset wiped
`.rb-state`, including the day-117 replay cache and the FMP caches. The
backlog now uses the committed record, or refetches.

## Done

| Date | Step | Result |
|---|---|---|
| 2026-10-24 | Day-140 registered and fixed (`PREREGISTER_day140_fixpack.md`) | Forward from 10-26; no result yet |
| 2026-10-24 | Day-140 backfill: the 23 live picks before the test (descriptive) | Stop in reach: 7 picks +0.47%, the 16 without −0.80% (t = 1.8, with 10-15 among them). The discussion changed the picks on 5 of 12 sessions: its own 0.00%, Round 1's −0.52% |
| 2026-10-26 | Item 1 registered on the record (`PREREGISTER_day141_reach_history.md`), since the replay cache was wiped | Runs next slot |
| 2026-10-27 | Item 1 run (`reach_history.py`, `data/reach_day141.json`) | FAIL, powered (rejection #57): kept 39 picks −0.05%, dropped 119 +0.12%, t = −0.72; a planted 1% shows at t = 4.17. With 10-15 put back: +0.12%, t = 0.32 |
| 2026-10-28 | Item 2 registered (`PREREGISTER_day142_newsdesk_open_prompt.md`): day-122's prompt with its window moved to the open, on the day-122 releases, judged by day-139's bar (seed 142) | Runs next slot |
| 2026-10-29 | Item 2 run (`replay_news_open.py`, `data/replay_day142_open_prompt.json`; 133 DeepSeek calls) | NULL, powered (rejection #58): 418 calls +0.11% open → close against XIU, t = 0.99, placebo p = 0.19; a planted 0.5% shows at t = 4.41. Day-122's prompt re-asked: +0.05%; paired difference +0.06%, t = 0.46 |
| 2026-10-30 | Item 3 sized before any test (gaps and ATR only; no outcome read): of the record's 189 positions (09-17 → 10-29, each name, side and day once), the open ran ≥ 1 ATR the pick's way once, ≥ 0.5 ATR 15 times (8 sessions), ≥ 0.25 ATR 43 times | Closed without a test. A gate at 1 ATR cannot be judged on the record. On history a ≥ 1 ATR gap continues slightly from the open (#42, t = 2.63), the opposite of the premise. Not a numbered rejection |
| 2026-10-30 | Item 4 registered (`PREREGISTER_day143_report_day.md`; names pinned in `data/report_day143_names.json`) | Runs next slot |
| 2026-10-31 | Day-144 registered (`PREREGISTER_day144_claude_leads.md`): the owner's decision, Claude leads the Top 2 and the guardrails come off, with the council's own choice kept as a shadow | Forward comparison from 11-02 (`claude_leads.py`); harm check at 20 sessions, decision at 40. Before (descriptive): Claude's first-named picks 24, 58% right, −0.11%; the printed Top 2 −0.98%; per session +0.43%, t = 1.02 |
| 2026-11-02 | Item 4 run (`report_day.py`, `data/report_day143.json`; FMP calls only) | FAIL (rejection #59): the window swings 1.55× the rest (bootstrap 1.45–1.64; S&P 500 point in time 2.06×), but leans long against XIU (+0.15%, t = 2.81) and the 20-session placebo reads 1.18×. Control detected; it could tell 1.135 from 1.00 |
| 2026-11-03 | Item 5 sized before any test (counts only, no outcome read): the counted Top 2 filled both slots on 6 of 16 sessions, with the slot order surviving for one (11-02), and the printed Top 2 on 11 of 18 | Closed as written (an MDE of about 2.5–3% a pick); not a numbered rejection. Re-scoped and registered as day-145 (`PREREGISTER_day145_best_first.md`): each model's first-named nomination against its second, 84 scored pairs over 14 sessions now, 90 over 15 with 11-03. Every model put its higher confidence first (30 of 30 each). Runs next slot |
| 2026-11-04 | Item 5 run (`best_first.py`, 857ff4d; `data/best_first_day145.json`; no API call) | NULL, powered (rejection #60): 90 pairs over 15 sessions, first-named minus second-named +0.20% a pick, t = 0.94, placebo p = 0.18, halves +0.25% and +0.15%; a planted 1.0% shows at t = 4.75 (smallest detectable 0.81%). By model: Claude −0.45% (t = −1.68), DeepSeek +1.36% (t = 2.40), Gemini −0.32%. Next: item 8 |
| 2026-11-05 | Item 8 registered (`PREREGISTER_day147_holds.md`): the pooled model picks (189 over 26 sessions, 09-17 → 10-29), held from the 09:45 entry to the close 3 sessions later against XIU (H = 1 and 5 reported), day-145's bar at seed 147, a planted 1.0%, net of 0.13%; Claude's 48 nominations descriptive. Counts only, no return read | Runs next slot |
| 2026-11-05 | Outside the backlog, the owner's "fix the main root problem": day-147c registered and run (`PREREGISTER_day147c_market_direction.md`, `market_direction.py`, `data/market_direction_day147c.json`; cache and FMP only) | NULL, powered (rejection #62): following XIU's move from the prior close to 09:45 into the rest of the day, 707 sessions, −0.030%, t = −1.41, placebo p = 0.16; SPY's own t = −0.72; a planted 0.10% shows at t = 4.62. All six side arms (sectors included) Holm p = 1.0 |
| 2026-11-06 | Item 8 run (`holds_history.py`, 414d24a; `data/holds_day147.json`; FMP bars only) | UNDERPOWERED (rejection #63): at three sessions +0.075% a session, net −0.055%, t = 0.17, placebo p = 0.43, halves +0.69% and −0.54%, 95/189 right; a planted 1.0% shows at t = 2.50. One session: −0.02%, t = −0.09 (control t = 4.05). Five: +0.74%, t = 1.60, placebo p = 0.066 (shorts +2.28%, longs −0.66%). Claude's first-named 24: −0.21% at three sessions. Next: item 11, sized first |
| 2026-11-09 | Item 11 sized and registered (`PREREGISTER_day148_veto.md`, population pinned in `data/veto_day148_positions.json`; counts only, no return read): every council position with a surviving tally, positions two or more members objected to against the rest, 09:45 → close against XIU, day-145's bar at seed 148, a planted 1.0% | 239 positions over 23 sessions, 106 vetoed; smallest detectable effect near 1% a position. Runs next slot |
| 2026-11-09 | Outside the slot, at the owner's "Build all that are missing": item 9's forward desk registered (`PREREGISTER_day149_us_preopen.md`, `us_preopen.py`, `data/us_twins.json`: 81 names matched by ISIN) | Live from 11-10 at 08:12 ET. Judged at 40 sessions with a material, priced call: from the New York price at the read to the 09:30 open against SPY, net of each call's own half-spread and 0.05%. Dry run on 11-09's evening releases: LONG EQX.TO and LONG AAUC.TO; it also caught another company's results filed under a look-alike symbol and five law-firm notices, both now excluded |
| 2026-11-09 | Item 13 registered and run once (`PREREGISTER_day149_nowcast.md`, `nowcast_history.py` 239afff, `data/nowcast_day149.json`; FMP only) | UNDERPOWERED (rejection #65): 159 sided quarters over 83 weeks, −0.20% a report against XGD.TO, t = −0.34, placebo p = 0.63, halves −1.23% and +0.81%, 73 right; a planted 1.0% shows at t = 1.67. Information check: the side matched the revenue surprise on 91 of 154 (59%, t = 2.37). Siding by the reported surprise itself: +0.41%, t = 0.72 |
| 2026-11-09 | Item 14 registered (`PREREGISTER_day149_event_desk.md`, `event_desk.py`); planted control run before the first call | Live in shadow from 11-10 at 15:14 ET. Control: 3 clean of 5 with the abstain rule left to the prompt (noise names sided in 2 runs), 5 of 5 once the rule became code. Dry run for 11-11's reports: LONG BDT.TO and CAE.TO, three abstained |
| 2026-11-12 | Item 9's history replay registered (`PREREGISTER_day151_us_preopen_history.md`; population pinned in `data/us_preopen_history_day151.json` by `us_preopen_history.py --population`, b0ac033) | Runs next slot |
| 2026-11-13 | Item 9's history replay run (`us_preopen_history.py --run`, 3f6f887; `data/us_preopen_history_day151_result.json`; ~108 DeepSeek requests, FMP bars) | NULL, powered (rejection #66): 209 material, priced calls over 72 sessions, −0.27% a session from the read to the 09:30 open against SPY, t = −1.88, placebo p = 0.97, halves −0.19% and −0.34%; a planted 0.5% shows at t = 3.51 (smallest detectable 0.40%); probe median miss 36.6%. Next: item 12 |
| 2026-11-16 | Item 12 registered (`PREREGISTER_day152_intraday_habit.md`; no return computed) | Runs next slot on cached bars (`intraday_habit.py`, committed first) |
| 2026-11-17 | Item 12 run (`intraday_habit.py`, 1973c20; `data/intraday_habit_day152.json`; cached bars only) | UNDERPOWERED (rejection #67): top fifth minus bottom fifth by the 20-session habit −0.090% a session over 692 sessions, t = −2.52, blocks −0.04/−0.09/−0.04/−0.19%; a planted 0.10% shows at t = 2.79 (smallest detectable 0.100%). Secondary: the list's ten-year daily panel +0.095% (t = 4.34), the point-in-time S&P 500 +0.006%. Next: no free row left |
| 2026-11-18 | Item 15 added and registered (`PREREGISTER_day153_noon_exit_live.md`; counts only, no return read) | Runs next slot on the committed lab file (`noon_exit_live.py`, committed first) |
| 2026-11-19 | Item 15 run (`noon_exit_live.py`, 5cb0c94; `data/noon_exit_live_day153.json`; the committed lab only) | UNDERPOWERED (rejection #68), WORSE flag up: 179 positions over 37 sessions, noon minus close −0.230%, t = −2.45, halves −0.14% and −0.35%; swing ratio 1.22 (bootstrap 5th percentile 1.085); a planted 0.20% shows at t = 2.13 (smallest detectable 0.26%). Shorts −0.43%, longs −0.01%; the Top 2's own 42 −0.04%. Next: no free row left |
| 2026-11-20 | Item 16 added and registered (`PREREGISTER_day154_floor_history.md`; `data/floor_day154_positions.json` pinned by `floor_history.py --pin`; counts only, no return read) | 92 positions over 23 sessions, 67 kept, 25 dropped. Runs next slot (run code committed first) |
