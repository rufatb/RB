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

```bash
# Single brief now (default source = Yahoo, free & DELAYED)
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

## Files

| File          | Purpose                                                        |
|---------------|----------------------------------------------------------------|
| `dashboard.py`| Entry point: guard → metrics → decision → render → schedule    |
| `adapters.py` | Pluggable data layer (Yahoo, manual, real-time stubs)          |
| `metrics.py`  | All real, timestamped measurements + labelled proxies          |
| `risk.py`     | Risk-first position sizing, margin & gap-risk math             |
| `config.yaml` | All tunables                                                    |
| `tests/`      | Guardrail tests                                                |

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
