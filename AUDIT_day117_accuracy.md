# AUDIT day-117 — why the desks' accuracy is what it is

The owner, 2026-09-28: "The accuracy was not good okay for all LLMs and
sections — deep research why and let's try to fix it."

## 1. What the live record actually says (it cannot say much)

| source | right | mean / pick | sessions |
|---|---:|---:|---:|
| Claude, sealed pre-open | 5/5 | +0.69% | 2 |
| DeepSeek, selected | 6/12 | −0.11% | 3 |
| Jev, forced | 2/2 | +0.70% | 1 |
| Baseline engine | 7/19 | −0.32% | 5 |
| late picks (after the open) | 8/18 | +0.30% | 2 |

38 pre-open picks: 20 right, −0.07% each. The Wilson interval on the models'
pooled 13/19 runs 46%–83%: the record is consistent with a coin flip AND with a
decent picker. Descriptive diagnostics (`diagnose_record.py`) on those 38:

* **Longs 13/19 (+0.30%), shorts 7/19 (−0.43%).** Over 59 replayed sessions the
  two sides are equal (below), so this was the sample, not a side problem.
* **When the open had already gapped the pick's way, it did worse** — 11/23,
  −0.17% vs 9/15, +0.09% against. The shape of a thesis priced in by 09:45;
  far too few picks to say more.
* **The "wrong if" levels were noise.** Median 0.37 ATR from entry, 6 of 9
  inside half an ATR, 5 of 9 already crossed AT entry, 7 of 9 traded through
  on the day — winners included. They named ordinary wiggle, not a thesis
  failing.

## 2. The replay: a sample large enough to answer (registered)

`PREREGISTER_day117_replay.md`, committed before any replay pick existed.
`replay_models.py` rebuilt every session in Yahoo's five-minute history — 59,
2026-07-06 → 09-28 — with the PRODUCTION pool builder fed history cut off
before the session (tested: no bar dated on or after the session reaches a
pool), asked the LIVE DeepSeek and Jev prompts, and scored with the PRODUCTION
scorer. The 09-28 replay pool equals that morning's live brief field for field
(75 usable names; AC.TO's row identical to four decimals).

| | right | mean / pick | clustered t | random same-pool picks | registered bar |
|---|---:|---:|---:|---:|---|
| DeepSeek selected | 109/221 (49.3%) | −0.078% | −0.68 | 49.5%, p = 0.55 | FAIL |
| Jev forced | 62/116 (53.4%) | +0.002% | −0.09 | 49.4%, p = 0.20 | FAIL |

Controls: oracle 100% / anti-oracle 0% (the scoring is wired right); the
statistic passes a planted skill and fails a coin flip (house rule 4). DeepSeek
MDE80 ≈ 0.31% per pick — an edge that size would have shown. DeepSeek's stated
confidence carries no information (0.55–0.60: 59/135 = 44%; < 0.55: 34/59 = 58%).

**DeepSeek, asked this question on these inputs, is a random draw from the
list.** Jev likewise. Claude cannot be replayed blind — this session has seen
the outcomes — so its 5/5 stays unverified, with a ~50% prior from the rest.

## 3. Why — measured, not argued

Exploratory scan (not registered, 16 fields, so |t| < 3 is noise): the rank
correlation of every input with the 09:45 → 15:55 return, per session, over
4,601 name-days.

| field | mean IC | t |
|---|---:|---:|
| prior-session gap | +0.080 | 1.89 |
| gap in ATRs | +0.068 | 1.70 |
| today's gap | +0.051 | 1.11 |
| ATR % | +0.039 | 0.88 |
| every other field (move_atr, r0, RSI, MACD, rvol, SMA50/200 distance, 52-week position, last vs VWAP, today's first 15 min, today's VWAP position, opening rvol, sector-relative move) | within ±0.035 | within ±0.9 |

A planted IC of 0.045 is detected at t = 3.0, so the scan could see a real
signal of that size. **Nothing the desks are shown — nor anything measurable
by 09:45 — predicts the rest of the day's move on these names.** The gap family
is the only faint lean, and a vol-scaled gap was already tested and rejected as
#42. The models are not failing to read a signal; there is no signal in what
they read. Rewriting the prompt cannot change that; tuning it against the
replay would only fit noise.

## 4. The owner's VWAP / rvol rule (Part 3), on every name, not seven picks

LONG above today's VWAP, SHORT below, opening rvol > 1.2, at 09:45: **1,676
name-days, 48.3% right, −0.013% per flag, clustered t = −0.27, placebo
p = 0.90** (rvol > 1.5: 48.3%). A planted +0.10%/trade edge is detected at
t = 2.07 and +0.20% at t = 4.4, so this rules out anything that large. The
"above 80%" premise came from a handful of picks.

## 5. What changes now

* The email, full report and page print the replay's **base rate under the
  scoreboard every day** — "none beat random, so a day's hits and misses are
  noise" (house rule 8). A 5/5 week and a 0/4 day are both read against it.
* **A "wrong if" level closer than 0.5 ATR to the last close is dropped** with
  a gap line saying it was noise (`check_levels`, every desk).
* Recorded as rejections #43 (the LLM desks on these inputs) and #44 (the
  VWAP/rvol rule) in `STRATEGY.md`. Nothing is adopted, re-tuned or re-sized.

## 6. What could actually change accuracy — owner's decision

Only NEW INFORMATION can. Candidates, each a forward test, not a promise:

1. **Timestamped issuer news.** The live feed is Yahoo RSS commentary, zero
   verified catalysts on TSX names. A dated press-release wire is reachable
   (newswire.ca, PR Newswire's Canadian feed, checked 2026-09-28). Collect it
   forward, restrict picks to names with a fresh material release, register
   the test before looking. RSS keeps no archive, so it cannot be backtested:
   ~40 sessions of collection before an answer.
2. **A different question.** Open-to-close direction on liquid large caps is
   the hardest target there is; 44 rejections in this repo say so. A longer
   horizon, or event-driven names only, is a different product and would need
   its own registration.
3. **Keep the desks as they are, as a record.** They cost cents a day. The
   base-rate line makes clear what their picks are worth.

Part 3's rule is now a powered negative; whether to keep printing it is the
owner's call.
