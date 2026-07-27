# Pre-Open Brief — Intraday Decision-Support Dashboard

A command-line tool that runs around **09:31 ET** each trading day and prints an
**honest, calibrated intraday decision-support brief** for a configurable ticker
(default `AC.TO`, Air Canada on the TSX).

> This is **decision support, not a predictor.** It exists because confident
> intraday "calls" that flip with the price are worse than useless. Read the
> Design Philosophy before you change anything.

---

## Design philosophy (hard requirements — do not strip)

These constraints are commented throughout the code so future edits don't
"helpfully" remove them:

1. **No fabricated data, ever.** If a metric needs data the source doesn't
   provide (e.g. true bid/ask aggressor *order-flow delta*), the tool computes a
   clearly **labelled proxy** (e.g. "price held above open & VWAP ⇒ net-buy
   *proxy*") or prints `unavailable`. A proxy is never dressed up as real order
   flow. See `metrics.net_buy_proxy`.
2. **No confidence inflation.** Open-to-close direction for a single stock is
   near a coin flip. `p(close > open)` **defaults to 0.50** and is **clamped to
   [0.35, 0.65]** for an intraday open-to-close call. It moves off 0.50 only for
   specific, *named* structural factors, and **never** exceeds 0.65. Conflicting
   signals or a mid-range price → `NO EDGE — WAIT`. Enforced by
   `dashboard.clamp_probability` (assertion) and `tests/test_guardrails.py`.
3. **Data integrity is checked first.** Free feeds (Yahoo included) routinely
   serve cached/stale data — sometimes months old — with no error. Every quote
   carries a `source` + `as_of` timestamp. The guard validates freshness and
   **refuses a directional read** on data that fails, printing a loud banner.
4. **Levels over predictions.** The actionable output is **invalidation levels
   and confirmation triggers**, not a verdict. "Wait for X to break/hold" beats
   "it will go up."
5. **Risk-first.** Position size is derived from **stop distance** and account
   risk %, never conviction. Includes overnight gap-risk and margin-carry math.
6. **Read-only.** The tool never places orders.

---

## Install

```bash
pip install -r requirements.txt
```

Python 3.11+ required (uses `zoneinfo`).

## Run

**The one command (9:31 morning report — recommended):**

```bash
python report.py            # preflight all APIs → scan the TSX → ranked longs/shorts
python report.py --check    # preflight only: verify every configured API & key
```

`report.py` is the single entry point that runs the whole pipeline in working
order: API preflight → data-integrity guard → full-universe evaluation
(structure + deep-history analogs + sector×crude macro + optional sentiment) →
cross-lens selection → **calibrated** EOD probabilities → entry/invalidation
levels → capped position sizing. Schedule it for one minute after the open:

```cron
31 9 * * 1-5  cd /path/to/repo && TZ=America/Toronto python report.py >> report.log 2>&1
```

Other entry points:

```bash
# Single-ticker brief (default source = Yahoo, free & DELAYED)
python dashboard.py --once

# Plain text instead of rich terminal output
python dashboard.py --once --no-rich

# Different ticker
python dashboard.py --once --ticker SHOP.TO

# Include top-3 headlines (context, not signal)
python dashboard.py --once --headlines
```

### Manual broker Level-1 (recommended at 09:31)

At the open the free feed may be ~15 min behind. If you can see your broker's
live Level-1, paste it. Manual input is tagged `source=manual` and **bypasses
the staleness fail** (you are vouching for it). It does **not** fabricate
correlated/context data — those print `unavailable` in manual mode.

```bash
python dashboard.py --manual \
  --m-open 20.50 --m-last 21.10 --m-high 21.30 --m-low 20.40 \
  --m-volume 850000 --m-prior-close 20.30
```

---

## Use a real-time feed (strongly preferred for live decisions)

**For genuine 9:31 live decisions, a real-time broker or paid feed is strongly
preferred over Yahoo.** Yahoo TSX quotes are ~15-min delayed and occasionally
stale/cached — fine for context, dangerous for a live read (hence the guard).

The data layer is a pluggable adapter (`adapters.py`). To add a real feed,
implement the `DataAdapter` interface:

```python
class DataAdapter(ABC):
    def get_quote(self, ticker) -> Quote: ...          # full L1 + timestamp + session date
    def get_intraday_bars(self, ticker, interval="1m") -> DataFrame: ...
    def get_daily_bars(self, ticker, lookback_days) -> DataFrame: ...
    def get_quote_simple(self, ticker) -> Quote: ...    # correlated tickers (still timestamped)
```

Documented stubs are already present (raise `NotImplementedError` with install
hints) so you only fill in the fetch logic:

| Adapter            | Source                         | Notes                                   |
|--------------------|--------------------------------|-----------------------------------------|
| `YahooAdapter`     | `yfinance` (default, free)     | ~15-min delayed; **guard mandatory**    |
| `ManualAdapter`    | pasted broker L1               | trusted by user vouch; tagged `manual`  |
| `IBKRAdapter`      | Interactive Brokers `ib_insync`| real-time L1/L2 if subscribed           |
| `QuestradeAdapter` | Questrade REST API             | OAuth refresh token                     |
| `PolygonAdapter`   | Polygon.io (paid)              | US-centric; limited TSX coverage        |
| `AlpacaAdapter`    | Alpaca market data             | US equities                             |

Register a new source in `adapters.build_adapter` and pass `--source <name>`.
Whatever you wire in, **always populate `Quote.as_of` and `Quote.session_date`** —
the freshness guard depends on them. A quote with no timestamp is treated stale.

---

## What's in the brief

1. **Data integrity** — pass/fail, timestamps, source, trade age, source-conflict.
2. **Verdict** — `BULL LEAN` / `BEAR LEAN` / `NO EDGE — WAIT` (default WAIT).
3. **Probability** — honest `p(close > open)`, default 0.50, clamped [0.35, 0.65],
   with the **named factors** that moved it off 0.50.
4. **Conviction** — `None` / `Low` / `Medium`. `High` is **unavailable for
   intraday by design**; `Medium` requires explicit multi-factor confluence.
5. **Opening structure** — ORB(1m & 5m) position, volume pace vs ADV, VWAP,
   net-buy **proxy**, spike-fade flags.
6. **Levels (the actionable part)** — invalidation event, bull/bear triggers +
   target shelves, and the mid-range **no-trade zone**.
7. **Context** (marked *context only*) — crude % (surfaced first: dominant fuel
   lever), TSX %, CAD/USD %, VIX %, peer-avg %, relative strength.
8. **Risk** — for a hypothetical entry at a trigger with stop at invalidation:
   position size from `risk_per_trade_pct`, $ risk, R-multiples to targets,
   overnight margin cost = `borrowed × (cad_prime + margin_spread)/100 / 365`,
   and a gap-risk table (1% / 2% gap ⇒ $ on position).
9. **Headlines** (optional) — top 3, tagged *context, not signal*.

### The Spike–Fade detector

From the open it locates the session extreme in the first *K* minutes (the
"opening drive"), then measures retracement of that drive:

- retrace > 50% → **FADE WARNING**
- retrace ≈ 100% (back to open) → **OPENING DRIVE NEUTRALIZED — momentum gone**
- lower-highs after the extreme → **FAILED-BREAKOUT STRUCTURE**

These usually precede chop, not continuation, so they **veto** a continuation
verdict and are surfaced prominently. This is the specific pattern that caused
the whipsaw this tool was built to resist.

---

## Configuration

All tuning lives in `config.yaml`: ticker & timezone, correlated set, risk
inputs (`account_equity`, `risk_per_trade_pct`, `is_margin`, `cad_prime`,
`margin_spread`), guard thresholds (`max_stale_minutes`, `source_conflict_pct`),
level-detection windows, and the probability clamps. The clamp values are
guardrails — see Design Philosophy before widening them.

---

## Scheduling (auto-run 09:31 America/Toronto, weekdays, skip holidays)

**Option A — built-in (`schedule` library):**

```bash
python dashboard.py --schedule
```

Fires at 09:31 server-local time on trading days; TSX holidays are skipped via
`pandas_market_calendars` (falls back to a weekday check if unavailable).

**Option B — system cron (more robust).** Set the server TZ or use a TZ-aware
cron. Example (America/Toronto):

```cron
# m h dom mon dow   command
31 9 * * 1-5  cd /path/to/repo && TZ=America/Toronto /usr/bin/python dashboard.py --once >> brief.log 2>&1
```

The holiday skip still applies through the data guard: on a holiday the feed
won't be live and the brief refuses a directional read.

---

## Tests

```bash
python -m pytest tests/ -q
```

`tests/test_guardrails.py` locks in the honesty constraints: probability clamp,
WAIT defaults, stale/conflict/missing-timestamp refusals, manual bypass,
proxy-not-orderflow labelling, and risk-from-stop-distance sizing. **If a future
change breaks a guardrail, these fail — don't delete them to make CI green.**

---

## Multiple data sources & cross-checking

The data layer is multi-source. A **primary** serves all metrics; each
**cross-check** source is pulled independently so the integrity guard can raise
`SOURCE CONFLICT` when prices diverge beyond `source_conflict_pct`.

| Source | Key needed | Intraday bars | Notes |
|--------|-----------|---------------|-------|
| `yahoo_direct` (default) | none | yes | Raw chart endpoint via `requests`; reliable (the `yfinance` library hangs behind some proxies). ~15-min delayed. |
| `yahoo_yf` | none | yes | Original `yfinance` adapter, kept as fallback. |
| `stooq` | none | no | Free cross-check; **no TSX coverage** (returns `unavailable` for AC.TO rather than guessing). |
| `finnhub` | `FINNHUB_API_KEY` | (premium) | Real-time quote; independent cross-check. |
| `twelvedata` | `TWELVEDATA_API_KEY` | yes | Real-time quote **+ intraday bars + volume**; the recommended paid upgrade for genuine 9:31 data. |
| `manual` | — | no | Paste broker L1; trusted by user vouch. |

```bash
# Live AC.TO via the reliable Yahoo-direct endpoint, cross-checked against stooq:
python dashboard.py --once --source yahoo_direct --cross-check stooq

# Real-time primary once you have a key (export TWELVEDATA_API_KEY=...):
python dashboard.py --once --source twelvedata --cross-check yahoo_direct
```

Configure defaults under `data_sources` in `config.yaml`. Missing-key sources
are skipped silently — never fabricated.

> **Verified:** the default `yahoo_direct` source returns live AC.TO data
> (e.g. $24.51 CAD, 52-week range 16.45–24.95) through the agent proxy.

## Deep historical patterns (`patterns.py`)

Mines **as much history as the source returns** for base-rate context a casual
reader wouldn't compute by hand. Every statistic carries its **sample size** and
a confidence tag (`ok` / `low` / `anecdotal`):

- **Gap base rates** — after a gap up/down, how often AC closes above its open and how often the gap fills.
- **Analog days** — a nearest-neighbour search for historical sessions whose *setup* (gap %, prior-day move, position in the trailing range) resembles today, then the **distribution** of what those days did open-to-close. This is the "patterns others wouldn't think of" piece — a base rate conditioned on the actual setup, not a blanket average.
- **Crude-oil correlation regime** — rolling AC↔WTI return correlation, so you know whether you're in a fuel-cost-sensitive or decoupled regime.
- **Weekday seasonality** & **gap continuation**, both labelled as usually-noise.

These feed the verdict only as **weak, named factors**, only when structure
already agrees, and **never** past the `[0.35, 0.65]` clamp. Base rates are not
forecasts — the output says so.

## Claude analysis layer (`analyst.py`)

An **optional** advisory layer (`claude-opus-4-8`, adaptive thinking) reads the
fully-computed brief and writes pattern/level/risk notes. It is **read-only by
design**:

- It **cannot set or override** the verdict or probability — those stay
  deterministic and clamped. Its system prompt forbids emitting its own
  probability or telling you to override the capped read; the calling code never
  lets it mutate the decision (enforced by tests).
- It is **skipped** when the data-integrity guard fails (no analysis on
  unverified data) and when no key is set.

Enable by exporting a key and using the flag (or `claude.enabled` in config):

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # your own key
python dashboard.py --once --analyst
```

Without a key, the section prints a clear "set `ANTHROPIC_API_KEY`" stub and the
rest of the brief is unaffected. (Note: the tool needs *your* Anthropic API key —
a key is read from the `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` environment,
never hardcoded.)

## TSX opportunity scanner (`scan.py`)

Don't want to assume AC.TO is the best use of risk? The scanner runs the **same
honest engine** across a universe of liquid TSX names and ranks them by how
confident an open-to-close call can be — long or short — then makes an explicit
call: *"AC.TO is a no-go; better opportunity → TICKER LONG/SHORT"*, or
**STAND DOWN** when nothing clears `WAIT`.

```bash
python scan.py --source yahoo_direct          # rank the TSX, recommend the best
```

It inherits every guardrail: probability stays capped at `[0.35, 0.65]`
("more confident" only means strongest multi-factor confluence, never a
manufactured high-conviction call), each candidate must pass the data-integrity
guard to be ranked, and macro (crude/TSX/CAD/VIX) is shared context, not signal.
Designed to be re-run on a **5-minute cadence** — the structure (opening range,
VWAP, spike-fade) only exists *after* the open, so a pre-open scan honestly
returns mostly `WAIT`/STAND DOWN and sharpens 5–15 min into the session.
Universe is configurable under `scan.universe`.

## Backtest (`backtest.py`)

Evaluates how the tool would have performed on intraday open-to-close direction,
with explicit guards against hindsight/lookahead bias:

- **Expanding window** — for day *t*, every statistic uses only days **strictly before** *t*; day *t* is never in its own candidate pool.
- **Decision-time information only** — the call uses just the open, the first 1–5 minutes of bars, the gap, and prior days. Today's high/low/close are used **only to score**, never to decide.
- **No tuning on test data**; shipped defaults throughout.
- **Honest data limits** — free feeds only return ~7 days of 1-minute bars, so the full intraday engine is replayed over a handful of recent sessions (Tier B, flagged anecdotal); long history (Tier A) tests the daily-derivable pattern engine. No intraday history is fabricated to pad the sample. A no-lookahead unit test proves predictions for early days don't change when future data is altered.

```bash
python backtest.py --ticker AC.TO --days 2000
```

## Deep validation without a paid key (`validate_twins.py`)

The four-quarter protocol that decides whether a rule ships. Yahoo caps 5-minute
bars at 60 days — and 60-day windows have manufactured six separate "edges" that
later evaporated — so this builds a **2-year** sample from hourly bars on the 20
US dual-listings (~9,651 ticker-sessions, ~2x the original paid-data study) and
replays the pair machinery walk-forward.

```bash
python validate_twins.py                      # rebuild + run (no API key)
python validate_twins.py --cache twins.csv    # build once, re-use
```

**Caveat that must not be stripped:** its entry is 10:30 (the first hourly bar),
not the live 9:45. It is a *mechanism* sample — it can refute or support how a
rule behaves; it can never certify live 9:45 levels. The ledger's PAIR line
remains the arbiter of live performance.

### Equal-risk leg weighting

On a two-leg day the pair is sized **inversely to each name's trailing
entry→close volatility** (capped 35/65), not equal-dollar. Validated on 333
two-legged sessions: NET volatility −11.8% with **lower volatility in all four
quarters**, worst day −2.22% → −1.52%, mean return unchanged. It reduces the
**size** of bad days, **not their frequency** — the hit rate is untouched,
because it changes only how much of each leg you hold, never which leg is
picked. Disable with `pair.risk_weight: false`.

**Representative AC.TO result (≈2,400 evaluated days):**

| Metric | Raw (pre-calibration) | Shipped (smoothing + shrinkage 0.5) |
|--------|-----------------------|--------------------------------------|
| Directional hit rate on leans | ~52.8% (p≈0.01) | ~52.6% (unchanged, as expected) |
| Brier score (0.25 = say-nothing baseline) | 0.257 — **worse than saying nothing** | **0.2507** — at the baseline |
| Confident bin (p≈0.6) | predicted 0.62, realized **0.51** | predicted 0.59, realized **0.57** |

The raw analog probabilities measured **overconfident**, so the shipped engine
now (a) **distance-weights** analog neighbours, (b) **shrinks** the green rate
toward 50% with a Beta prior (`analogs.smoothing_m`), and (c) **compresses** the
stated probability via `probability.shrinkage` (compress-only — it can never
amplify, and the hard clamp still applies). After calibration the stated
probabilities match realized frequencies far more closely.

*Honest caveat:* the calibration re-run is **in-sample validation** — the
overconfidence was diagnosed on this same dataset, so treat the improvement as
"the stated numbers are now consistent with history", not out-of-sample proof.

**Interpretation:** this is the design working, not failing. Single-name
open-to-close direction is ~random; the marginal pattern tilt does **not**
justify confident calls, which is exactly why the tool defaults to `WAIT`, caps
probability at `[0.35, 0.65]` (config can only narrow the band, never widen it),
and treats history as weak context. A high hit rate here would more likely
indicate a lookahead bug than a real edge.

## Files

| File          | Purpose                                                        |
|---------------|----------------------------------------------------------------|
| `report.py`   | **The 9:31 entry point**: API preflight → scan → calibrated ranked report |
| `scan.py`     | TSX universe evaluation, cross-lens at-open selection, legacy 5-min mode |
| `dashboard.py`| Single-ticker brief: guard → metrics → patterns → decision → analyst → render |
| `adapters.py` | Pluggable multi-source data layer (Yahoo-direct, Stooq, Finnhub, Twelve Data, manual, real-time stubs) + cross-check aggregator |
| `metrics.py`  | All real, timestamped measurements + labelled proxies + EOD alignment |
| `patterns.py` | Deep historical mining (analog days w/ smoothing, gap base rates, crude regime) + calibrated EOD probability |
| `sentiment.py`| Optional relevance-gated headline lens (off by default)        |
| `analyst.py`  | Optional Claude advisory layer (read-only; never sets the verdict) |
| `risk.py`     | Risk-first position sizing (equity-capped), margin & gap-risk math |
| `backtest.py` | Lookahead-safe backtest (expanding window, decision-time info only) |
| `validate_twins.py` | **Deep validation, free & re-runnable**: builds ~9,651 ticker-sessions (2yr, 20 US dual-listings, Yahoo hourly) and runs the pre-registered four-quarter protocol — no paid key |
| `config.yaml` | ALL tunables — universe, sectors, thresholds, clamps, risk (no hardcoding) |
| `STRATEGY.md` | Trading post-mortems + the rules encoded from them             |
| `tests/`      | 78 tests: guardrails, patterns, adapters, analyst, backtest, scan, review |

---

## Limitations (read these)

- **Yahoo is delayed and sometimes stale.** The guard catches stale data but
  cannot make a delayed feed live. Use a real-time adapter or manual L1 for
  actual 9:31 decisions.
- **No order-flow / Level-2.** Anything resembling aggressor delta here is a
  labelled proxy, not real order flow.
- **Single-name intraday direction is near random.** That's why the verdict
  defaults to WAIT and the probability is capped. The levels and risk math are
  the parts you should actually use.
- **Not financial advice. Read-only. It never places orders.**
