# AUDIT day-118 — the issuer's own press release, and what the open does to it

The owner, 2026-09-28: "Yes to press-release feed, and drop what is proven not
to work." Registered in `PREREGISTER_day118_wire.md` (commit 817cd97) after the
collector existed and before any release was joined to a price.

## 1. The feed

`newswire.py` reads newswire.ca's paginated release list — the Canadian wire,
100 per page — and each release page: the wire's own dissemination time
(`<meta name='date'>`, with offset) and every TSX / TSX-V symbol named in the
lead. The RSS feed is not used: it is PR Newswire's global channel, 20 items,
and carried no TSX symbol in the releases sampled.

Archive `data/newswire/`, 2026-07-01 → 2026-09-28: **8,477 releases, 1,522
naming a TSX symbol, 266 naming a replay-pool name**; every weekday has at
least 20 releases; one page lacked a date and is counted, not archived.

A headline is `ISSUER_RELEASE` only when the ARCHIVE holds that URL with that
title. The class is recomputed at validation, never read from a staged claim.
`issuer_verified` is true only when the release names the candidate's symbol,
and `first_disclosed` is the wire time. The prompts (`day118-v1`) describe the
class in two sentences. Positive controls after the change:
* DeepSeek found both planted names in 2 of 3 runs and abstained in the third,
  picking no noise name;
* Jev: CTLUP 0.73, CTLDN 0.51.

## 2. The replay (registered)

The day-117 pools, unchanged, now carry the releases the live staging would
have shown at 08:55. The live prompts were asked once per session, over 59
sessions, and scored by the production scorer (09:45 → 15:55). An EVENT name is
one with a release in the prior weekday's 16:00 → 09:30 window.

Controls: oracle 100% / anti-oracle 0%; the direction statistic passes planted
picks and fails a coin on the same 146 event name-days.

| | picks | right | mean / pick | clustered t | side-flip p | verdict |
|---|---:|---:|---:|---:|---:|---|
| **H1** DeepSeek on event names | 20 | 8 (40%) | −0.96% | −1.09 | 0.87 | UNDERPOWERED (< 30; MDE80 ≈ 2.2%) |
| **H2** Jev forced on event names | 10 | 6 | −0.52% | −0.44 | 0.38 | UNDERPOWERED |
| DeepSeek, all picks, with the wire | 213 | 114 (53.5%) | −0.04% | −0.23 | 0.17 | FAIL (day-117: 109/221, −0.08%) |

**H3, the model-free precondition:** do event names MOVE more after 09:45?
Over 51 sessions and 146 event name-days, their mean |return| exceeded the rest
of the pool by **+0.15%, t = 0.73**. That FAILS the bar. An excess above about
0.6% (the MDE80) is ruled out; a smaller one is not.

## 3. Why — the open has already done it

The releases are real news, and the market prices them at the open. The
biggest event gaps were:
* Intact's Q2 results: −8.1%
* TELUS's Q2 results with a dividend reset: −7.3%
* Aritzia's Q1 results: +4.6%
* Lundin Gold's Q2 results: +4.4%
* Dollarama's Q2 results: +4.1%

Releases whose title mentions results gapped 1.23% on average, including the
many that only announce a date; the rest gapped 0.75% (unregistered,
descriptive). Across ALL event names — most releases are routine: dividends,
date notices, AGM votes, NCIBs — the gap excess is +0.10% (t = 0.96).

Then, by the 09:45 entry, there is no excess movement left to read (H3). A
09:46 entry buys the release after the auction has priced it. That is the
priced-in warning the prompts have carried since day-114, now measured rather
than assumed.

Registered descriptives, 20 picks, anecdotes:
* DeepSeek chose event names for 20 of 213 picks.
* Releases out 08:00–09:30 went 4/4 (+0.36%); before 08:00, 2/8 (−2.30%); the
  previous evening, 2/8 (−0.28%).
* DeepSeek's basis = news: 5/13 on event names (−1.21%) and 10/16 on names
  with no release (+0.14%).

## 4. What follows

* **Nothing is adopted.** H1 and H2 are UNDERPOWERED. The registered forward
  test decides H1 at 40 live sessions (~2026-11-24), where Claude is judged for
  the first time. At ~0.3–1 event pick per session across the desks it may
  still be underpowered then, and it will say so rather than read a null.
* The feed stays in the desks' inputs. It is the only verified, timestamped
  news they have, and it costs ~15 s in the morning. Every desk table shows the
  release beside a pick, and the scoreboard prints the forward population
  ("Desk picks on an overnight wire release").
* The email's base-rate line now says this in one sentence.
* **What could use this archive** (owner's call, each its own registration):
  * the days AFTER a results release — post-announcement drift is a multi-day
    effect, and the archive dates every release since July;
  * entering at the 09:30 auction instead of 09:46, which is a different
    execution contract.
  Neither is a same-session 09:45 question, and neither is promised.
