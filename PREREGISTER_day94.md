# Pre-registration — day-94: new information sources (attention forward-collection; cross-market proxy)

Committed BEFORE any outcome is computed. Bars fixed here and do not move.

## Why this exists

Day-43's verdict — accuracy cannot come from rearranging `r0`/`gap`/`vp`, only
from NEW INFORMATION — named four candidates: L1/L2 depth (paid, open),
point-in-time overnight news (partially acquired via 8-K 2.02; general news
open), sector/index futures state at 9:45 (open, pre-refuted on a tide-beta
argument, never a registered test), and short interest (closed, day-84 bounded
null). Social media, Google search attention, and every other alternative-data
source have **never been collected, tested, or registered** in this project
(verified by full-repo and full-journal search, day-94).

The user has asked for new sources, including social and search data. This
registration puts that request through the same machinery as the 40 rejections
that came before it. Nothing here enters `r945`, `scan`, or the published
report. Everything below is shadow research.

## Arm A — social/search attention (FORWARD COLLECTION ONLY; no inference today)

**Sources (free, keyless):** StockTwits public symbol streams (message volume
and author sentiment tags, timestamped); Google Trends daily attention
(unofficial endpoint — fragile and explicitly revisable).

**Why forward collection only.** Neither source offers point-in-time history:
StockTwits history is not served, and Google re-normalizes Trends values on
every pull, so a "historical" Trends download is not the series that was
observable at the time (rule 9). A backtest on revisable data would
manufacture the exact look-ahead this repo exists to exclude. So:

- `build_social.py` collects one dated snapshot per session (09:20 ET) into
  `data/social/YYYY-MM-DD.json`. Fail-closed: fetch errors are counted and
  recorded per name, never retried-into-silence (rule 1). TSX tickers map to
  their US-listed equivalents via an explicit config map; each mapping is
  verified against the returned quote name and unmapped names are recorded as
  UNMAPPED, never guessed.
- **Coverage gate, declared now:** after 20 collected sessions, measure median
  messages/day per name. If fewer than 8 of the 21 universe names have usable
  daily attention (median >= 1 message/day), the family is reported
  **UNRUNNABLE for this universe** — the day-93 outcome, not a null. The
  honest prior is that TSX large-cap social coverage is thin; that is a
  finding, not an inconvenience to route around.
- **Registered inference design (runs only after >= 120 sessions):** paired
  out-of-sample AUC of `[r0, gap]` vs `[r0, gap, attention]` under the
  day-91/day-93 corrected harness — session-clustered influence values,
  shifted expanding medians, planted-edge positive control, MDE printed
  always. Attention feature = log message-count change vs trailing 20-session
  median, plus sentiment share where present. No result on fewer than 120
  sessions is anything but a coverage report.

## Arm B — cross-market overnight state (runnable now; DAILY-BAR PROXY)

**Question:** does the prior-session state of US market/sector/macro proxies
carry out-of-sample information about same-day TSX large-cap returns, beyond
`[r0, gap]`? The journal's "pre-refuted" note rests on pair tide-beta (+0.12)
and was never a registered test with the corrected harness. This is that test.

**Contract honesty, stated first:** at 09:46 ET the knowable state is the
proxies' PRIOR completed session. The target measurable on free daily bars is
same-day open-to-close, which contains 09:30–09:46 — sixteen minutes the real
engine does not see. Every result of this arm is therefore labelled
**DAILY-BAR PROXY** and cannot certify the 09:46–15:59 execution contract,
whatever the point estimates say.

**Data:** Stooq daily split-adjusted OHLCV, 2015-01-01 through 2025-12-31
(development) and 2026-01-01 through the last completed session
(confirmation), for the 21-name configured TSX universe plus SPY, XLF, XLE,
USO and USDCAD. Fallback source Yahoo; provenance and input hashes recorded.
Granularity asserted (rule 9); sessions missing any name or proxy are
rejected and counted, never bridged. The universe is today's list: all 21 are
surviving mega-caps, so delisting bias is small but is DISCLOSED, not assumed
away.

**Exactly 3 arms, no parameter search.** Baseline learner: the day-91 parity
k-NN on `[r0, gap]`, entry at session open (daily-bar stand-in for the third
5-minute bar). Each arm adds ONE feature group:

- B1: SPY prior-session close-to-close return.
- B2: sector-matched proxy prior-session return (XLF for financials, USO for
  energy producers, SPY otherwise; mapping fixed in the harness code).
- B3: USDCAD and USO prior-session returns jointly.

**Statistics and bars.** Paired out-of-sample AUC difference vs baseline,
influence values aggregated within session (day-91 correction). Deterministic
circular block bootstrap, 20-session blocks, 2,000 draws, seed 94. Report 95%
intervals, SE, and 80%-power MDE = (3.5 + 0.8416212336) × SE in AUC points —
always, including on failure (rule 10). Four consecutive chronological
development blocks, all printed. Holm correction across the 3 arms. A planted
+2 AUC-point synthetic edge must be detected as edge/SE (never
(mean+edge)/SE); if not, the verdict is UNDERPOWERED, not null (rule 10).
Zero-mean session sign-flip placebo must be beaten at its 95th percentile.

**What any result licenses.** A positive, Holm-surviving, confirmation-
replicated result licenses exactly one thing: a registered replication using
intraday proxy state at 09:46 (which requires the sub-hourly history day-93
showed is unavailable free — so in practice, likely nothing further without a
paid dataset). **No outcome of this arm adopts anything.** A null is reported
with its MDE and control power.

## Forbidden

Running inference on revisable attention history. Counting failed fetches as
zero attention. Moving any bar after seeing outcomes. Dropping the coverage
gate because it is inconvenient. Presenting a DAILY-BAR PROXY as evidence
about the 09:46 contract. Quoting any day-94 result as evidence the engine has
an edge. Any change to r945, scan, selection, sizing, or the published report.

## Expected outcome, recorded in advance

Arm A: coverage gate fails for most TSX names — UNRUNNABLE is the likely
honest verdict, and the collector then exists for the day the universe or the
sources change. Arm B: small AUC differences, intervals containing zero after
clustering, Holm-surviving nothing. Prior: day-43's two-feature ceiling, the
tide-beta of +0.12, and 40 rejections.
