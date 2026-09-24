# LAB_day98 (Kimi): exploratory lab findings - NOT validation, NOT registration

Two exploratory sprints run 2026-09-10 on free 5-minute Yahoo bars
(41 sessions x 9 liquid TSX names + XIU.TO tide; 360 feature rows, 180
walk-forward eval rows over ~20 sessions). Everything here is LAB: tiny,
multiply-compared, clustered. The value of this note is negative-result
documentation and hypothesis triage, not evidence.

## 1. Opening-path / microstructure screen (point-in-time safe)

Spearman rho vs 09:46->15:59 return (sign of each extreme-tercile trade):

- vwap_dev (price vs opening-15min VWAP):  +0.175  MOMENTUM (61.8% extreme hit)
- or_pos (position in opening range):      +0.128  FADE extremes (56.6%)
- tide (XIU first-15min):                  -0.109  FADE the tide (56.5%)
- tide_resid:                              +0.106  weak momentum
- vp (volume pace vs 20-session mean):     +0.080  noise standalone
- of_ratio / signed_v (uptick volume share, signed volume): +0.076/+0.082 - DEAD.
  Adding signed_v to the best combo changed walk-forward accuracy 57.8% -> 57.8%.
- rng (opening range %):                   +0.007  DEAD.
- prev_day daily return:                   +0.044  noise.

Walk-forward k-NN (train=past sessions only, K=30, n=180, uncorrected p):
- [r0,gap] (production parity):            55.0% (p=0.09)
- [r0,gap,vp]:                             57.2% (p=0.026) - first hint vp helps
- [vwap_dev,or_pos,tide_resid]:            57.8% (p=0.018)
- kitchen sink:                            55.6%

Abstention on the lab combo (extreme-prob third): 68.8% dir acc (n=48),
+30bps/leg GROSS. Mirage-prone: selection fitted on the same window.

Relation to PREREGISTER_day97: day97's registered opening-path features
(third-minus-first bar return; net opening return / sum |within-bar returns|)
are the same FAMILY as vwap_dev/or_pos - convergent lab support for that
direction, NOT a substitute for the registered test, which remains blocked on
history depth.

## 2. EODHD daily-context features: REJECTED (lookahead trap documented)

Daily-context features from 1y EOD (ret5, ret20, vol20, dist20h, adv_r,
gap_prev) screened TWO ways:

- WITH the classic leak (same-day close in the feature): rho up to +0.31 -
  a mirage strong enough to ship if unexamined.
- Point-in-time safe (prior close only): all |rho| <= 0.10; daily-context
  k-NN 48.9%; adding ret5/dist20h to the intraday combo DILUTED it
  (57.8% -> 55.6%).

Verdict: do not spend a registered study on daily-context features for the
09:46->15:59 contract. EODHD free's value is as a reference-close second
source, not a signal source. (This closes a whole family cheaply.)

## 3. Gap-fill dynamics: REJECTED

P(gap fills by 15:59) = 48.9% for |gap| >= P50, 50.0% for |gap| >= P75;
negative gross both ways. Overnight gap is a fair coin intraday here.

## 4. Pairs spread convergence: one lab survivor, superseded by day96

Fixed +40bps a-priori threshold on 09:46 opening spreads, 40 sessions:
ENB/TRP 80% hit (n=15, +27.8bps gross ~= +12bps net of two-leg spread);
CNQ/SU +15.2bps gross (~breakeven net); TD/RY, MFC/SLF dead.
n=15 inside 40 sessions; pair list was data-selected. PREREGISTER_day96's
placebo-max pair-grid study is the correct test of this family; treat this
as motivation, not evidence. If day96's family survives, ENB/TRP is the
candidate pair this lab flags first.

## 5. What this lab does NOT claim

No validated edge. No production change. No certification of the 09:46
execution contract. 5-minute Yahoo bars are a trade-price proxy; no BBO,
fees, slippage or borrow. All accuracy figures uncorrected for the ~15
comparisons run across both sprints.
