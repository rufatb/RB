# Day 91 — second-pass research correctness and 48 fixed ETF simulations

Registered September 8, 2026, before acquiring or evaluating this study's price
panel. Baseline code: `c5f13153d276985fd87bd9aedccd67d31dd21bf6`.
The user requested broader simulated research. This registration extends research
scope; it does not change the production selector, published records, biotech
rules, delivery schedule, day-90 gates, or authorize brokerage orders.

## Prior knowledge and question

All RB days 1–90, including 40 rejections, are known discovery evidence. Their
results remain intact. The historical 107 selected legs and near-chance density
results have already been inspected. Repeating those rows is not a holdout.
The ceiling harness's historical k-NN implementation differs from live smoothing;
the entry-time harness uses a full-panel volume median; both require correction.
Correcting those bugs is not evidence of an investable edge.

Question: do lagged cross-sector trends or reversals yield repeatable returns
under a different, explicitly simulated daily/overnight/weekly contract? This
does not test the exact 09:46 TSX stock engine or establish individual-stock skill.
No outcome from the new ETF panel has been evaluated at registration.

## Data and fixed universe

Use Massive daily split-adjusted OHLCV and split-adjusted cash distributions.
Nine sector ETFs are fixed in advance: XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV,
XLY. SPY is a separate matched-window benchmark, never a candidate. No ticker
replacement after seeing results. These surviving funds are a selected universe;
they mitigate constituent-list reconstruction but do not eliminate selection
bias or certify a survivorship-free stock universe. Sector definitions can change.

Request 2015-09-01 through 2025-12-31 for development. If the provider denies
that history, make one fixed shorter request: 2025-01-01 through 2025-12-31.
The shortened result is a feasibility study, never a substitute for long-history
validation. Minimum 120 complete joint sessions; otherwise market study BLOCKED.
Select the development leader and persist its identity before fetching the
confirmation block 2026-01-01 through 2026-09-04. September 8 and incomplete
sessions are excluded. This is historically unseen by this run, not prospectively
unseen market history. Date boundaries cannot be moved after observing outcomes.

Require finite positive consistent OHLC, unique ticker/session, positive volume,
and actual NYSE sessions. All nine funds and SPY must be observed on each used
session. Missing prices within any held window invalidate that window; do not
bridge gaps or carry forward prices. Report each error and missing count.
Cash dividends are credited to longs and debited to shorts on ex-date when
the holding crosses the entitlement boundary. Missing/denied distribution
history means PRICE-ONLY PROXY, cannot certify total/net returns. Never silently
substitute zero for an unavailable feed. Persist request provenance/input hashes.

## Exactly 48 strategies, no parameter tuning

Eight signals: cross-sectional rank of trailing total return over 1, 5, 20 or
60 completed sessions, in either momentum or reversal direction. Stable ticker
ordering breaks ties. Choose two longs and two shorts, four distinct names.
Two sizing rules: equal 25% gross allocation per leg; inverse trailing 20-session
daily total-return volatility, normalized separately to 50% long and 50% short.
No leverage beyond 100% gross; finite vol required. No signal uses information
after the preceding session close, including for a close-entry overnight trade.

Three horizons:
1. Intraday proxy: enter session D open, exit D close; signal as of D-1 close.
2. Overnight proxy: enter D close, exit next session open; signal as of D-1 close.
3. Weekly proxy: enter D open, exit D+4 close. Non-overlapping 5-session slots
   start at the first eligible session of each evaluation block. Signals use
   D-1 close. No overlapping deployment of the same capital.

Thus 4 lookbacks × 2 directions × 2 sizing rules × 3 horizons = 48 arms.
Do not add filters, exits or models after seeing a favorable result.

## Accounting and measurements

Primary scenario: assumed 10 bps round-trip commission/spread/slippage per leg
plus 3% annual simple borrow on short notional for actual calendar holding days.
Stress scenarios: 5 and 25 bps round-trip with the same borrow assumption.
These are declared simulations, not measured execution costs or confirmed borrow.
Always report gross and all three cost scenarios, turnover/holding count,
net and decisive (absolute return >=0.10%) leg hit rates, average book return,
drawdown on non-overlapping marked trade endpoints, long-minus-short return,
and SPY over matching windows. Equal dollar long/short is not beta neutrality;
also report each side's benchmark-relative return and do not call their combined
return residual alpha. Actual beta/sector attribution remains unverified.

Development: four consecutive chronological blocks, using all eligible years
up to 2025-12-31; print all block results. Rank all 48 arms by primary-scenario
mean book return per occupied session (weekly trade return divided by 5;
intraday/overnight divided by 1). Persist the winner and complete table before
confirmation access. Evaluate all predeclared arms in confirmation for full
disclosure; only the frozen development winner is the primary confirmation test.
No replacing a failed winner with the best confirmation arm.

## Uncertainty, repeated testing and controls

Resample consecutive blocks of 20 trading sessions (20 consecutive trade slots
for weekly arms) with 2,000 deterministic circular block-bootstrap draws, seed91.
Report 95% intervals, SE, and 80%-power minimum detectable effect
(3.5 + 0.8416212336) × SE in bps per occupied session and net-hit percentage points.
With fewer than 40 trade slots, label inference UNDERPOWERED; fewer than two
slots means MDE unavailable, never zero. Use two-sided normal approximate
p-values based on clustered/bootstrap SE and Holm correction across all 48 arms
within each evaluation period; report the full family, including failed arms.

Positive control adds a known +5 bps per occupied session to a centered synthetic
copy of book returns; detectability is 5/SE, never (observed mean+5)/SE. Report
whether target power is adequate. A zero-mean randomized session-block sign
placebo checks the evaluation machinery. Synthetic controls are not market data.
Also report all-negative/no-data fixtures, horizon gap rejection, prior-only
features and cash-dividend long/short arithmetic tests. No optional stopping.

## Interpretation and deliverables

An exploratory candidate must have positive primary-scenario means in all four
development blocks, positive confirmation, Holm p<0.05 and z>=3.5 in confirmation,
and a positive 25bps stress result. Report MDE and control power even on failure.
Passing is eligibility for further research, never automatic production adoption:
the universe, assumed costs, short availability, limited confirmation span and
different contract prevent certification under day90. No guaranteed win rate.

Deliver corrected research code, tests, all 48 results, input provenance, the
frozen development choice, confirmation results and a readable second-pass audit.
Keep raw market inputs and private runtime state out of GitHub; preserve raw
research data separately for reproducibility. Document failures without erasing
earlier studies. Reconcile legacy present-tense accuracy claims with later
evidence; maintain their original historical numbers and dates.
