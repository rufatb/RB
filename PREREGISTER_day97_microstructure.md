# Day97 — recipient-proposed microstructure gates, retrospective audit

Registered before this reanalysis of gate/outcome relationships. The user has
already observed losses and earlier exit research exists: these observations
are development data, NEVER an untouched confirmation set. No production
selection, allocation, exit, publication or delivery changes are authorized by
a favorable retrospective result. Preserve all rejected studies and day97's
separate feature-comparison registration.

## Fixed dataset and timing

Use only already cached completed native TSX five-minute OHLCV and original
published pair rows, with exact names/sides retained. Do not refit or repick.
Metadata inspected before registration: cache covers 60 dates, 2026-06-15 to
2026-09-09, with 115 published pair records across 41 covered dates. Exclude
today, short sessions, incomplete/invalid bars and records whose recorded
09:45 reference does not match the completed opening-bar close within 0.01.
Require 20 immediately preceding valid exchange sessions of opening volume;
never backfill an absent session or use future/full-day volume as a feature.
Use the same complete original board/dates for every arm; report every exclusion.

Start-labelled bars at 09:30/09:35/09:40 form the completed opening range.
VWAP is explicitly an HLC3-times-volume bar approximation, not trade VWAP.
Opening RVOL is first-15-minute volume divided by the arithmetic mean of the
same window over the preceding 20 exchange sessions; this differs from live
vp's historical median. The user's 2.5 threshold is fixed, not optimized.

Baseline entry proxy is the 09:45 bar OPEN, exit is the 15:55 bar CLOSE.
Neither is an exact 09:46/15:59 fill. Breakout confirmation uses the completed
09:45 bar CLOSE and can first act at the 09:50 bar OPEN. A bar close strictly
above opening-range high and cumulative approximate VWAP confirms a long;
strictly below both opening-range low and VWAP confirms a short. No trigger
touch inferred from intrabar highs/lows. One check at 09:50, no chasing later.

## Seven fixed arms

1. baseline_proxy: original published side, 09:45 open to regular close.
2. delay_only: same selections at 09:50 open to regular close.
3. rvol_2p5: baseline entry/exit only when opening RVOL >= 2.5.
4. orb_vwap: 09:50 entry only on confirmed directional ORB + VWAP.
5. orb_vwap_rvol: arm 4 plus opening RVOL >= 2.5.
6. exit_1130: baseline entry, full exit at 11:30 bar open.
7. half_exit_1130: baseline entry, half at 11:30 open and half regular close.

No threshold/entry/stop/target sweep, inverse adoption, after-the-fact pairing,
news subset selection, or low-volume fallback. The user's 'stagnant' and
'partial profits' lack mechanical definitions; arm 7 is an unconditional 50%
time exit, not a test of an undefined discretionary rule. Stops and targets
are not simulated: five-minute bars cannot resolve which was touched first.

## Metrics and limits

Report admitted count/percentage, conditional gross hit rate, mean win/loss,
conditional gross expected value and per-original-leg capacity gross return
(abstentions stay zero). Equal unit capacity per original leg is a diagnostic
normalization, NOT a change to recorded production shares or allocation.
Compute daily averages before uncertainty so same-session names are not
independent observations. No actual portfolio P&L is claimed.

For six fixed arm-minus-baseline daily differences: 2,000 noncircular
five-session moving-block bootstrap draws, seed 9702; report bootstrap SE,
95% normal approximate intervals and MDE80=(3.5+0.8416212336)*SE in basis points
of normalized gross daily return. Report a fixed +5 bps additive-effect
sensitivity control. This verifies statistical sensitivity only, not alpha
learning or order-fill realism. Fewer than 20 eligible sessions or degenerate
SE means no inferential statistic. All results remain descriptive development
evidence, even if a statistic exceeds its threshold.

Show 5/10/20 bps assumed proportional round-trip friction sensitivities,
debited on admitted capacity. These are scenarios, not observed net returns;
the half exit assumes proportional costs and omits extra fixed ticket fees.
Missing BBO, slippage, fees, borrow and same-window index data block actual
net/index alpha and its MDE. Report break-even cost on admitted capacity.

A promotion requires a separately frozen prospective confirmation, at least
60 independent OOS dates and the existing four-quarter/two-market gates, with
verified costs/index, positive-control and multiple-comparison procedures
registered before obtaining that confirmation. This short retrospective
current-universe sample cannot certify a >55% engine or a universal 09:46 sweep.
