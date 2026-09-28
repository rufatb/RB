# PREREGISTER day-118 — does a timestamped issuer release give the desks a direction?

Registered 2026-09-28, after the wire archive was collected and BEFORE any
release was joined to a price, a pick or a return. Nothing below has been run.

## Why

Day-117 (`AUDIT_day117_accuracy.md`, rejection #43): DeepSeek 49.3% and Jev
forced 53.4% over 59 replayed sessions, both indistinguishable from random
picks from the same pools, and no input field carries rank information about
the 09:45 → close move. The only news the desks ever saw was Yahoo RSS
commentary with no disclosure time and no verified issuer. The owner approved
adding the one source that has both: the issuer's own press release on the
Canadian wire (newswire.ca, `newswire.py`).

newswire.ca's release list paginates back months, so the question can be asked
on the SAME 59 sessions as day-117 instead of waiting ~40 sessions — and then
forward, where nothing can have been fitted.

## Definitions (fixed now)

* **Archive**: `data/newswire/*.jsonl`, collected by `newswire.py --collect
  --since 2026-07-01` from the wire's own pages. A release names a symbol only
  in its LEAD (first 700 characters of the body). The dissemination time is the
  page's `<meta name='date'>`.
* **Event name** on session D: a pool name with at least one archived release
  naming it, disseminated in `newswire.window(D)` = the prior weekday's 16:00 ET
  → D 09:30 ET. (News the open can already have traded, the only kind a 09:45
  entry can use.)
* **Pools**: the day-117 cached pools, unchanged (`.rb-state/replay/pools/`).
  Each candidate gains the headlines the LIVE staging would have given it:
  `newswire.headlines(T, D 08:55, hours=72)` through the production validator
  (`factor_inputs._evidence`), so each carries `ISSUER_RELEASE`,
  `issuer_verified` and `first_disclosed` exactly as live. Yahoo headlines are
  not retrievable historically and are absent, as in day-117.
* **Models**: DeepSeek `deepseek_opportunities.rank` and Jev
  `jev_opportunities.rank` at prompt `day118-v1` (the only change from
  day-117's prompt is the description of the ISSUER_RELEASE class), asked once
  per session. Scored by `model_picks.score_one` (09:45 bar close → 15:55 bar
  close, no costs), as day-117.

## Controls — run FIRST; nothing is reported if they fail

* Day-117's oracle / anti-oracle on the same pools (100% / 0%).
* The direction statistic below must PASS on planted picks that take the
  realized sign on every event name and FAIL on picks with a random side.
* Leakage: no release disseminated at or after D 08:55 reaches a D candidate
  (tested in `tests/test_newswire.py`).

## Primary — H1: DeepSeek's selected picks ON EVENT NAMES

Skill on the news is claimed ONLY if ALL hold:
  1. session-clustered mean return per event pick > 0 with t ≥ 2.0;
  2. the event-pick hit rate beats a SIDE-FLIP placebo — 2,000 draws, each
     pick given a random side, same names and sessions — at p < 0.05
     (reading a release can only add a DIRECTION; the name is given);
  3. the same sign in both halves of the sessions (by date).
If there are fewer than 30 event picks the verdict is UNDERPOWERED, not null,
stated with the minimum detectable effect, and the forward test decides.

## Secondary

* **H2** Jev forced picks on event names, the same bar.
* **H3 (precondition, model-free)**: do event names MOVE more after 09:45?
  Per session, mean |r| of event names minus mean |r| of the other pool names;
  clustered t ≥ 2.0. If event names do not move more than the rest after
  09:45, the open has already absorbed the release and there is little left
  for any reader to get right — that is reported as the reason, not hidden.

## Descriptive only (no inference)

All DeepSeek selected picks with the wire vs day-117's 49.3% on the same
pools; how often the models chose event names; hit rate by release time
(before 08:00 / 08:00–09:30 / previous evening); by `basis` = news.

## Forward (the test that cannot be fitted)

From 2026-09-29 the live desks see the same class. Every recorded pick on an
event name (by the archive and `newswire.window`) is scored by the evening job
as usual. The same H1 bar is applied at 40 live sessions (about 2026-11-24),
whatever the replay says. Claude is judged ONLY here: the session route cannot
be replayed blind.

## What may NOT follow

A prompt changed after seeing this replay and scored on it proves nothing (the
day-117 rule). If H1 fails, the news section is kept as information and the
desks' base-rate line says so; nothing is re-sized or promoted. If H1 passes,
nothing is adopted until the forward test also passes — a replay of 59 sessions
chosen by what Yahoo still serves is not the live contract.
