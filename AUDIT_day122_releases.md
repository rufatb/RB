# AUDIT day-122 — a model reads the whole release: it understands the news, and the open has priced it

Registered first: `PREREGISTER_day122_releases.md` (commit bc85a4f), before any
body was fetched for scoring or any answer existed. Run by `replay_news.py`
with `news_desk.py`'s event rule, frozen prompt (`day122-v1`) and arithmetic.
Summary: `data/replay_day122_releases.json`. Release bodies, bars and answers
are cached in `.rb-state/replay/news/` (not committed).

## The population

* 64 sessions, 2026-07-02 → 2026-10-01; 833 overnight releases whose first
  lead symbol is a TSX name.
* The registered liquidity filter leaves **420 events on 63 sessions**.
  Excluded: traded value under C$3M a day 287, price under C$2 74, fewer than
  21 prior sessions 20, not quoted in CAD 13, not an equity 9, no bar for the
  session 4, bars failed 6.
* 446 release bodies fetched, none failed.
* Answers: FULL 419 of 420 (one id answered twice, dropped), HEADLINE 416
  (four confidences out of range, dropped).
* The primary window, W945, exists on 59 sessions (Yahoo's five-minute
  history), 381 FULL calls.

## The primary result (FULL arm, 09:45 → close, against XIU) — FAILS

| | Right | Mean per call | Clustered t | Placebo p | Blocks |
|---|---:|---:|---:|---:|---|
| FULL | 200/381 (52.5%) | +0.11% | 0.83 | 0.158 | +0.06, +0.11, +0.08, +0.17 |

**Powered:** a planted +0.5% per call shows at t = 4.56. This is a powered
negative at the registered bar (t ≥ 3, p < 0.01), not an underpowered shrug.
The four blocks are all positive, but each is small and the whole is t = 0.83.
That is the shape noise around a small positive mean takes. It is not a
signal hiding under the bar, and the bar does not move.

**Contamination probe:** asked for 12 closing prices on the event dates, the
model's median error was 39% (49% on the rerun). It does not remember the
outcome period, so the result is not VOID.

## Reported, never promoted

| FULL arm | Right | Mean | t |
|---|---:|---:|---:|
| W_day, open → close | 213/419 (51%) | +0.09% | 0.71 (placebo p 0.27) |
| W_5d, close → fifth close | 181/387 (47%) | −0.02% | −0.07 |
| MATERIAL only, W945 | 129/256 (50%) | +0.04% | 0.20 |
| confidence ≥ 0.6, W945 | 123/222 (55%) | +0.06% | 0.34 |
| **C_gap, prior close → open (NOT tradable)** | 217/419 (52%) | **+0.21%** | **2.71 (placebo p 0.0035)** |

| HEADLINE arm (title only) | Right | Mean | t |
|---|---:|---:|---:|
| W945 | 201/380 (53%) | +0.05% | 0.39 |
| W_day | 230/416 (55%) | +0.18% | 1.24 |
| C_gap | 214/416 (51%) | +0.13% | 1.70 |

* FULL − HEADLINE on the same events, W945: +0.06%, t = 0.45. The two arms
  took the same side 74.5% of the time.
* The FULL arm went LONG 64% of the time and HEADLINE 59%: issuers write
  releases to sound good.

## What it means

The comprehension check is the one number that moved. Reading the text, the
model calls the direction of the overnight move the release caused better
than chance: +0.21% per call, t = 2.7, placebo p = 0.004. The title alone does
it at t = 1.7. So **it does understand which way a release points**, and the
full text helps it do so.

That move happens between the prior close and the open. By 09:45, and already
by the open, it is gone: nothing is left for the model to call afterwards.
This is day-118's finding ("the open prices a release") reached from the
other side, now with a model that reads.

This closes the obvious next idea: more text does not create a tradable edge
after the open on these names. The only window where this understanding is
worth anything is before the open. Pre-market trading is outside this
system's data and execution contract (the 09:46 entry). Any such test would
need new data and a new registration, and is the owner's decision.

## Rejection #45

**Full-text release reading as a 09:45 → close signal on liquid TSX names.**
Powered negative: t = 0.83 against a registered 3.0, placebo p = 0.16, with a
planted control at t = 4.56. The forward test (Part 6) still runs as the
owner asked. It is labelled with this result every day and decides at 40 live
sessions. Do not re-word the prompt against this replay.

## Test 3 — the biotech catalyst finder (coverage, not accuracy)

`biotech_finder.py`, first run 2026-10-02 00:30 ET:
* 60 leads; 41 issuer releases read (19 pages without a wire dateline were
  leads only).
* 11 candidates after 6 superseded by a newer release.
* Refused: quote states no timing 8; quote does not name its event 5; window
  outside 0–6 months 6; quote not on the page 2; kind not added 1.

Two events were merged; one was then REMOVED by hand. TPST's quote, "first
patient dosing anticipated in the fourth quarter of 2026 and initial clinical
data expected in the first half of 2027", carries two timings, and the model
took the dosing one for a data window. Nothing downstream could catch that:
the quote was verbatim and the window valid. The finder now refuses any quote
stating more than one timing, and a test pins that sentence.

Kept: **AIM — Ampligen DURIPANC topline, Q1 2027** ("…advances toward topline
results expected in the first quarter of 2027."). Part 2 now holds six
reviewed events.

The dry run before the real one accepted six events: four were the same few
with stale or wrong timings. The two mechanical rules came from reading them:
* the quote must name what its kind claims;
* the newest release supersedes older ones for the same asset.

Coverage is the measure; no accuracy is claimed.
