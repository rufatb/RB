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
| 9 | **The release on a US listing, before the TSX open** | The one measured signal: a model reading an overnight release calls the gap (+0.21% a call, t = 2.7, day-122), and the TSX open prices it before entry. Interlisted names trade in the US from 04:00 ET | Day-137b sizing: about 75 interlisted pre-market releases from 2026-07 to 10-21; FMP serves US extended-hours 5-minute bars. Liquid names may reprice within minutes, and pre-market spreads are wider | The wire archive's pre-open releases on interlisted names, bodies refetched; Claude (or DeepSeek) reads each; entry on the US listing's first bar after the read, exit at 09:30 (primary), 09:45 and the close; net of a registered pre-market cost | Claude reads about $5 of OpenRouter, or DeepSeek | Unblocked 11-09: the owner can trade US shares ("I can trade US shares also yes"). Next after item 11, with DeepSeek's reads unless the owner approves the OpenRouter spend |
| 10 | **Claude's nominations with reasoning on** | The live Top 2 is one Claude call with reasoning off (`council.ask_claude_openrouter`, max_tokens 4000) | R1 (a reasoning model) and Sonnet 5.5 were no better on the day-117 replay (day-134b); the inputs carry no signal after the open (day-117) | The day-117 replay rebuilt (59 sessions); Claude's nomination question with reasoning on against off, on the day-117 bar; a forward shadow only if it passes | About $35 of OpenRouter | Waiting for the owner: a top-up and a yes |
| 11 | **A council veto on Claude's picks** | Since day-144 the council votes on Claude's picks and cannot replace them; on 11-06 three of four members opposed the long | The council's own choice adds nothing over its table (day-137 M1, t = 0.05); opposition as a gate is untested | Every council position, those with two or more objections against the rest, 09:45 → close; a remove-only proposal if it passes | None | Sized and registered 11-09 (`PREREGISTER_day148_veto.md`; tallies pinned in `data/veto_day148_positions.json`): 239 positions over 23 sessions (10-05 → 10-21 from day-137's tables, 10-26 → 11-09 from the frozen reports), 106 with two or more objections, both groups every session. Not blind: day-137 reported the one-objection split for 10-05 → 10-21. Runs next slot; its rejection, if any, is #64 |
| 12 | **A name's own intraday habit** | Large and published on US data: a stock's past intraday returns persist intraday, and its past overnight returns reverse intraday (Lou, Polk & Skouras 2019). It is known before the open, so it could break ties among Claude's nominations | Untested here. Day-117's field scan had no such field; the level split (overnight against intraday) was rejected on cost (day-87). Expect a few hundredths of a percent a day at best on large caps | The 150 names' cached 15-minute bars (2024-01 → 2026-10): each name's mean 09:45 → close return against XIU over the prior 20 sessions, top fifth against bottom fifth, next session; the overnight version beside it; the point-in-time S&P 500 check on daily bars | None (cached) | Added 11-09 evening (the owner asked for deeper ideas); to register after item 11 runs |
| 13 | **The commodity nowcast** | The owner's pasted "Information Surprise" engine needs an independent estimate; for a commodity producer one exists: last quarter's revenue scaled by the quarter's average commodity price. On 11-09 Equinox's pre-announced ounces times the quarter's gold average gave US$1,068M against a US$987M consensus; it reported US$1,050M | One example, and the shares were flat after hours: the market had done the arithmetic. A surprise's sign matches the reaction 61% of the time (day-148b). FMP holds revenue estimates and actuals back to 2007 for the older names | Miners and oil and gas producers on the list, 2012 → 2026: the side of (nowcast − consensus) beyond a registered threshold, else abstain; the reaction against the sector fund from the close before FMP's date to the close after it; each leg judged alone (day-138's survivor warning) and a point-in-time check on US producers | None (FMP) | Proposed 11-09; waits for the owner's go |
| 14 | **An event desk with an abstain rule, in shadow** | The pasted engine as a forward test: for each report due in the evening note, a model states consensus, its own estimate and the reason they differ, or abstains | Before a report nothing tested gives a side (previous surprise, peers, run-up: day-138, day-148b). A replay is contaminated for older reports; DeepSeek showed no memory of 2026-07 → 10 (day-122) | Forward: recorded each evening, scored on the surprise's sign and on the reaction against XIU; never sized, never in the Top 2; decided at a registered count of non-abstained calls | DeepSeek; Claude through OpenRouter only with the owner's yes | Proposed 11-09; waits for the owner's go |

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
