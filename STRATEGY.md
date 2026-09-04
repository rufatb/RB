# Strategy & Lessons Learned

A living record of what went wrong in live trading and the rules now **encoded in
the tool** so the same mistakes get caught automatically. The tool's job is to
enforce discipline the trader won't always enforce under pressure.

---

## Day 1 post-mortem (AC.TO / SHOP.TO / CVE.TO)

### What happened
- **SHOP.TO long @ 159.64** — entered *inside* the no-trade zone (158.52–161.00),
  **below** the stated trigger (5-min hold above 161.00), on a name that had a
  **FADE WARNING** and was below VWAP. It was the *snapshot* scan leader at 09:50
  and had decayed to WAIT within 5 minutes. Exited shortly after (≈ scratch).
- **CVE.TO short** — entered while CVE was a live **BULL LEAN** (+1.2% over open,
  above VWAP, at session highs). Justified by the day-long base rate (≈72%
  close-down) + crude headwind — but price was already **off-sample** (outside
  the analog range), so that base rate didn't apply. It spiked further against
  the short into the afternoon.

### Root causes
1. **No confirmation discipline** — both entries front-ran / fought the trigger.
2. **Snapshot-chasing** — the 5-min scan leader rotated 8× in 30 min; a single
   snapshot was treated as a signal.
3. **Horizon/lens mismatch** — trading 5-min opening structure while intending to
   hold to 4pm, and acting when the lenses (structure / base rate / macro)
   *conflicted*.
4. **Ignoring off-sample** — acted on a base rate when today was nothing like the
   sample it came from.

---

## Rules now encoded in the tool

| Lesson | Where it lives | What it does |
|--------|----------------|--------------|
| Don't chase the rotating snapshot | `scan.py` **persistence filter** | A name is "actionable" only after holding the same verdict for `scan.min_persistence` consecutive scans (default 2). Raw leaders that haven't persisted show as "forming", not recommended. |
| Don't trade conflicting lenses | `metrics.eod_alignment` + brief/scan **EOD alignment** line | Combines intraday structure, the day-long analog base rate, and (optional) macro. `conflicted` → stand down. This flagged the live CVE short as "⛔ CONFLICTED — SHOP/CVE failure mode". |
| Don't trust an off-sample base rate | `patterns.analog_days` **off_sample** flag | When today's setup is outside the historical neighbour range, the base rate is marked UNRELIABLE and surfaced in the brief/scan. |
| Confirmation over front-running | existing **triggers + no-trade zone** | The brief always states "wait for X to break & 5-min hold"; entries inside the no-trade zone are, by construction, not the setup. |
| Respect the cap | existing **[0.35, 0.65] clamp** + backtest | Open-to-close is ~coin-flip; the backtest showed the engine is mildly overconfident. ~0.59 = a lean, size small. |
| Overnight = gap risk | `risk.py` **gap-risk table + margin carry** | A short held overnight has open-ended up-gap risk; the tool quantifies 1/2/3% gap impact and borrow cost. Exit on thesis-break rather than holding-and-hoping. |

---

## Strategy pivot: once-at-open selection (replaces the 5-min loop)

The 5-minute babysitting loop was unrealistic and caused snapshot-chasing. The
**primary strategy is now a single run near the open** that ranks the whole TSX
for the day's best long/short holds:

```bash
python scan.py --open --source yahoo_direct    # top longs + shorts for the day
```

**What changed and why:**
- **Discipline filter shifts from time-persistence → cross-lens agreement.** With
  one run there's no streak to build, so precision comes from *lenses agreeing in
  that single snapshot* instead.
- **Base-rate-primary.** For a hold-to-close, the day-long **analog base rate**
  (historical close>open odds for today's setup) is the direct signal, so it sets
  direction. Opening structure, **sector×crude macro**, and **sentiment** must
  *confirm* (not net-oppose). This fixes the earlier over-reliance on 1-minute
  opening structure, which is the wrong lens for a full-day hold.
- **New lenses:** `macro_dir_for` (crude up → producers up, airlines down) and an
  optional `sentiment.py` headline lens (off by default — free feeds return
  non-ticker-relevant news, and fake sentiment is worse than none).
- **Conflicts and off-sample setups are dropped**, so the shortlist is small by
  design. On holidays / off-hours the guard rejects stale data → honest STAND DOWN.
- **The cap is unchanged.** This improves *selection*, not the ceiling —
  open-to-close is ~coin-flip (see backtest); the picks are best-confluence leans,
  sized small and spread across the shortlist.

## Full-codebase review (accuracy + workflow hardening)

A top-to-bottom review turned the pieces into one 9:31 workflow and fixed what
live use exposed:

- **`report.py` is now the single entry point** — preflight every configured
  API, then produce the ranked open-to-close report. `--check` verifies APIs
  alone. Cron it at 9:31 America/Toronto.
- **Calibration (measured, not vibes):** raw analog probabilities backtested
  overconfident (Brier 0.257 vs 0.25 baseline; the 0.62 bin realized 0.51).
  Now: distance-weighted neighbours + Beta smoothing toward 50%
  (`analogs.smoothing_m`) + compress-only probability shrinkage
  (`probability.shrinkage`). Re-run: Brier 0.2507, confident bin predicts 0.59
  / realizes 0.57. (In-sample validation — stated numbers now match history.)
- **Position cap** (`risk.max_position_pct`): a tight stop can no longer balloon
  size past equity (seen live: $102k position on $100k equity).
- **Target-beyond-trigger:** hypothetical targets must sit ≥0.3% past the
  trigger (kills the 0.00R "target = trigger" bug).
- **No hardcoding:** universe, sector×crude map, analog k/smoothing/thresholds,
  clamps, shrinkage, and the position cap all live in `config.yaml`. Probability
  bounds in config can only NARROW the hard [0.35, 0.65] band, never widen it
  (asserted + tested).

## Day-2 post-mortem (the 1-of-6 day — correlated board)

### What happened
The 9:31 report went 1-for-6 on raw direction (SHOP long won; AC long and four
energy shorts lost). The user rode an off-plan AC long (7,000 sh @ 24.83,
pre-trigger, 3.5× the cap, stop declined at −$140) to −$1,890. As-traded per
plan, the whole six-pick board lost ≈ −$1,150 with every loser stopped small
and one pick correctly never triggering.

### Root causes
1. **Hidden correlation.** With crude −1.5% at 9:31, five of six picks (airline
   long + four energy shorts) were ONE crude bet expressed five ways. Crude
   reversed to −0.4% intraday and they all died together. Ticker count is not
   diversification when qualification hinges on one macro lens.
2. **Macro treated as static.** The macro lens is a 9:31 snapshot; nothing
   re-validated it as the day evolved. The analog features (gap / prior day /
   range position) cannot see an intraday macro reversal — today's AC close
   landed outside the whole analog range.
3. **Stated odds worked as stated.** 0.62 loses ~38% of the time; the failure
   wasn't the number, it was concentration amplifying one bad draw — plus
   execution deviations turning a planned −$500 into −$1,890.

### Encoded fixes
| Lesson | Where |
|---|---|
| Flag when ≥50% of picks share the macro lens — "size as ONE bet" | `report.py` `macro_concentration` + concentration warning block |
| Re-validate crude live on every mid-session check; declare the morning macro confirmation VOID if reversed | `hold.py` MACRO CHECK section |
| Post-mortem culture: raw direction and as-traded are both reported after the close | this file + the report-card workflow |

## Day-3 post-mortem (SHOP win / MFC scratch — presentation bias)

### What happened
Midday (from ~9:57), the from-here engine picked SHOP.TO long (54.3% from-here
+ 71.7% day-shape, move unspent) and — because the user asked for a long AND a
short — the analysis crowned MFC.TO as "Best SHORT" despite it being 53%
(dead zone) and lens-conflicted (day-shape 77% bullish). Result: SHOP closed
+0.69% vs entry (WIN); MFC ramped in the last hour and closed a 3-cent scratch.

### The split
* **Variance:** a 53% short losing is expected 47% of the time — and the
  engine's medians were nearly exact (SHOP analog median +0.63% vs +0.78%
  actual; MFC from-here median −0.04% vs +0.03% actual). Calibration held.
* **Process error (the tool's):** ranking a sub-threshold, conflicted
  candidate as "Best X" invites the trade regardless of caveats underneath.
  Action bias by presentation.

### Encoded fix
`midday.py` — the gated from-here selection. A side qualifies only past the
strong from-here threshold, or in the soft band WITH day-shape backing; a
contradicting day-shape disqualifies. Sub-threshold names are NOT ranked —
the output says "⛔ NO QUALIFIED SHORT right now — don't force one."
Today's real numbers are the regression tests: SHOP(54.3, 71.7) must qualify,
MFC(46.8, 77.3) must be rejected. Gates configurable under `midday:`.

## Day-4: a 6/6 day + the anti-hindsight audit

### Scoreboard
All six picks closed in the called direction (longs AC +2.9%, BNS +0.8%,
CP +1.2%; shorts CNQ −0.9%, BCE −2.1%, SU −0.6%); every trigger fired. User
banked AC +0.64% and CNQ +0.48% with proper exits. NOTE: yesterday was 1/6,
today 6/6 — the long-run expectation stays ~52-53%. A 6/6 day is variance
exactly like a 1/6 day; do NOT size up because of it.

### Anti-hindsight audit (requested: "make sure it's not retrospective bias")
1. **Out-of-name validation.** Calibration was tuned on AC.TO only; backtests
   on SHOP/CNQ/RY (never used for tuning, ~2,400 days each) show hit rates
   49–53% and Brier ≈ the 0.25 baseline — the system performs out-of-sample
   exactly as claimed (honest coin-flip-plus), no hidden overfit edge.
2. **Real finding: short-side overconfidence.** On ALL four names, days
   predicted ~0.42 realized ~0.49–0.51. Bearish base rates overstate the edge
   (equities drift up). Encoded: `probability.short_shrinkage` (0.35) — extra
   compression for bearish leans; can only compress MORE, never less (tested).
3. **Structural safety argument.** Every day-derived rule (persistence,
   conflict gates, off-sample, concentration, midday gates, room) is a
   RESTRICTIVE filter — it can only remove trades, never add them. Overfit
   restrictive rules cost opportunity, not capital. Signal-generating logic
   remains the original, backtested base-rate engine.

### Also encoded
`room_spent_pct` — %% of the analog day-band already consumed at the current
price (hand-computed twice before; now first-class). Report flags picks ≥70%%
spent: "entering here bets on a tail day; prefer a pullback-hold."

## Day-5 post-mortem (MFC "loss" that was a WIN / CP the printed coin flip)

### Forensics (minute-bar reconstruction)
- **MFC.TO long — the PREDICTION WAS RIGHT.** It closed 58.80, +0.12%% ABOVE its
  open. The user's loss (entry 59.04 → exit 58.80) came entirely from entering
  BEFORE the trigger: the 5-min hold above 59.10 never occurred all day (one
  poke at 9:42, never held). The plan's answer was NO TRADE on MFC. 100%%
  process, 0%% prediction.
- **CP.TO short — a real miss, but a printed coin flip.** Closed +0.52%% above
  open. The pick was sided-P 0.52, tier Low, one lens — flagged "skippable" in
  prose, yet still PRINTED as TOP SHORT. Its trigger did fire and the plan's
  stop capped the loss at ≈ −$100; the actual exit at 126.10 took ~2.3× the
  planned stop.
- Board: 2/4 raw (MFC ✓, SLF ✓, SHOP ✗, CP ✗). Running live record across all
  morning boards: 9/16 = 56%% — in line with the stated ~52-53%%.

### Systematic causes → encoded fixes
1. **Presentation bias recurred in the MORNING report** (day-3 fixed it only
   in midday.py). → `report.presentable()`: a pick is printed only if sided
   P ≥ `report.min_sided_p` (0.55) AND tier Medium; below the bar the report
   says "NO QUALIFIED LONG/SHORT — do not force one" and lists the closest
   candidate explicitly marked NOT tradeable. CP's exact numbers are the
   regression test.
2. **Pre-trigger entries recurred (4 of 5 live days).** → `confirm.py`: a
   5-second live check — CONFIRMED / BROKE BUT NOT HELD / NOT BROKEN — to run
   BEFORE any fill. MFC's exact pattern (poke without hold) is the regression
   test.
3. **Resisted a retrospective fix:** adding railways to crude_victims was
   checked and REJECTED — with crude +1.6%% at 9:36 it would have CONFIRMED
   the failing CP short. A plausible-sounding rule that would have made the
   day worse is exactly the overfit trap.

## The 9:45→close engine (r945.py) — matching the model to the trade

The user's actual trade is "enter ~9:45, exit by close", so a dedicated engine
now predicts P(close > price@9:45) conditioned on the first 15 minutes (r0,
gap, relative volume), pooled across the universe on 60 days of 5-minute bars
(~1,240 ticker-sessions), k-NN + Beta smoothing, hard-clamped.

**Walk-forward validation (blind holdout, 420 ticker-days):** baseline 48.6%%
(true coin flip); model 54.4%% hit on 41%% of days at the 0.55 bar, ~67%% on
the rare ≥0.60 signals; Brier 0.2502. Strongest effect: first-15-min ramps
>+0.5%% FADE 61%% of the time (median −0.32%%) — early momentum does NOT
carry; down-openers show no bounce edge (47%%). Retro-check on ship day
(excluded from training): called AEM fade-short after its +1.1%% ramp (won
big) and CP long-from-9:45 (the user's failed short — engine had it right).

Modest measured edges are the honest ceiling; selectivity is the edge. No
5-minute outlooks — close-horizon only, presentation bar inherited.

## FINAL WORKFLOW: once daily at 9:46 (decided)

The user runs ONE command per day, enters immediately, closes everything by
3:55. Decision: **9:46 AM, the r945 engine** (`python r945.py --book`), not the
9:31 report. Why:
1. r945's prediction IS this trade — close vs the 9:45 price with immediate
   entry. The 9:31 report's probabilities assume trigger-confirmed entries;
   entering instantly at 9:31 is the pre-trigger pattern behind 4 of 5 losing
   days.
2. The walk-forward validation (54.4%% @ 41%% coverage, ~67%% on ≥0.60) was
   measured EXACTLY this way: enter at 9:45, hold to close, no stop.
3. It conditions on today's first 15 minutes (incl. the 61%% ramp-fade), not
   only yesterday's setup.

`--book` mode completes it: equal-weight share counts across all qualified
picks, total book capped at risk.max_position_pct of equity (sizing is the
ONLY risk control in a no-stop workflow), explicit BUY/SELL-SHORT lines, a
too-early guard (refuses before 9:46), and CLOSE-BY-3:55 stamped on the
output. On no-qualified days the honest answer stays: no trades.

The 9:31 report remains available as optional context; it is no longer the
action layer.

## Day-6: replication discipline (the calibration audit that walked things back)

### Live results
Board 3/5 (TRP +0.03, AEM −0.96, ABX −1.27 won; T −0.40, BCE −0.39 lost —
both gold shorts delivered, both quiet telecom longs lost small). User traded
T long (−0.40%%) and AEM short (+1.09%%): net positive day.

### Research on the holdout — three hypotheses tested, most FAILED
1. **"≥0.60 signals hit ~67%%" DID NOT REPLICATE** (n=9-18 bucket: 67%%→44%%
   across splits). Walked back in the r945 header: there is NO reliable
   hit-rate gradient above the 0.55 bar; every qualified signal is the same
   ~53-55%% lean. Do not overweight the "strongest" pick.
2. **Salience hypothesis REJECTED before encoding:** hit rate by feature
   salience was U-shaped (quiet 59%% / mid 40%% / salient 59%%) — noise. Had
   it been encoded, it would have cut the quiet bucket that actually wins.
3. **Neighbour-density: instrumented, not gated.** Dense estimates hit 63.5%%
   vs ~46%% elsewhere but the pattern was non-monotonic on one split. Each
   pick now carries an [estimate: dense/mid/sparse] tag; after ~20 live days
   the tag's live record decides whether it becomes a gate. Pre-registered:
   dense > mid/sparse.
4. **Kept (consistent across splits):** shorts hit slightly less often but
   capture ~2.7x more per win — down-moves are fat; noted in the header.

The meta-rule this day encodes: **a pattern is not real until it survives a
split it wasn't discovered on.** Most "improvements" fail that test; testing
before encoding IS the edge over intuition-driven tuning.

## Day-7: learning from a winning day + the permanent ledger

Board 8/10 (best live day); user's BMO long +0.70%% and NTR short +1.38%% both
won. Honest decomposition: the six financial longs won TOGETHER in a tight
+0.14..+0.70%% band — largely ONE sector bet that paid; the concentration flag
was right in kind even when the outcome was good. SHOP fade-short (−2.69%%
against, sparse tag) was the day's big loser — bounded to ~$135 by sizing.

**Encoded: `ledger.py` — the daily learning mechanism.** Every published pick
is recorded at 9:46 (before outcomes are knowable), scored after the close
(`python ledger.py --score`), and the cumulative report tracks hit rates
overall, by side, and by confidence tag. First reading (15 picks): ALL 73%%
(early sample — will regress toward ~54%%; do not size up), dense 6/7,
sparse 1/2 — consistent with the pre-registered density hypothesis, decision
still parked at ~20 tagged days. Winning days get the same audit as losing
days; the ledger makes that automatic and hindsight-proof.

## Day-8: two banks, opposite calls — peer blindness fixed

### What happened
Board 4/13 (the 84%%-long board on a fade day — the one-bet warning played
out). User's pair: BMO long +0.55%% (WIN) and TD short −1.18%% (LOSS — TD
closed +1.22%%, the strongest financial of the day). Ledger regressed from
73%% to exactly 54%% — the validated number; the system is performing as
stated.

### Why one bank long and one short (the user's exact question)
The engine evaluates names INDEPENDENTLY on (gap, first-15m, volume). TD was
the only board name that gapped DOWN (−0.46%%, dividend-sized) while six
financial peers gapped up and qualified LONG. "Small down-gap" neighbours
lean down → 0.553 → only short → TOP SHORT → forced execution under the
one-long-one-short daily rule. A lone bank falling in a bid banking sector
is classically mechanical/idiosyncratic, then pulled up by peers — laggard
catch-up, which is exactly what printed.

### Encoded fixes
1. **Peer-contradiction gate** (`r945.peer_gate`, config `peer_groups` +
   `peer_contradiction_min`): a qualified pick whose direction opposes ≥3
   qualified same-group picks is EXCLUDED with an explicit reason.
   Symmetric (lone long vs sector shorts too). Restrictive-only. TD's exact
   day-8 numbers are the regression test — the gate empties that short side.
2. **THE PAIR block** (`r945.pair_of_day`): the book now ends with the daily
   pair and per-leg quality (STRONG ≥0.58 / OK / WEAK-at-the-bar / NONE).
   When a leg is missing: "trade the other leg ONLY — a forced leg has no
   edge." The tool never invents a leg to satisfy the daily habit.
3. **Documented blind spot (not encoded):** ex-dividend gaps read as bearish
   information. Free feeds can't confirm ex-div dates; with a paid calendar,
   exclude names on their ex-div day.

## Day-9: THE PAIR is selected by DENSITY, not by P (methodology day)

### The question
The user's standing rule is one long + one short daily. Which selection-time
variable should pick the two legs? The old pair took the highest sided P per
side — but day-6 already established there is NO hit-rate gradient above the
0.55 bar, so max-P ranks noise.

### The experiment (`validate_pair.py`, committed and re-runnable)
Walk-forward replay of the 60d/5m dataset: train the pooled k-NN only on
sessions before day d, qualify at the bar, apply the live peer gate, then
(A) correlate every selection-time variable with hit across 496 qualified
picks, and (B) race top-1 selection rules — all on a chronological
discovery/confirm split PLUS an independent odd/even split, with a placebo.

### Findings (each held on BOTH splits or it didn't count)
- **Sided P: no gradient — reconfirmed.** Discovery lo/mid/hi terciles
  53/47/50%%; max-P top-1 scored 50.0%% on discovery. The number that
  qualifies a pick cannot rank picks.
- **Densest estimate wins.** The pick with the smallest k-NN neighbour
  distance hit **68.0%% discovery / 69.2%% confirm / 70.5%% odd / 66.7%%
  even**, symmetric by side (68.8%% L / 68.3%% S), n=89, p≈0.0007 vs the
  51%% board base. The 2nd-densest placebo collapses to 53.9%% — the effect
  is specifically about the MOST familiar setup. Only 25%% of densest legs
  coincide with the max-P leg. This confirms the density hypothesis
  PRE-REGISTERED on day-7 — a scheduled test, not a fishing trip.
- **Crowding is a warning, not a bonus.** Picks with ≥3 same-group
  same-direction companions hit 44%%/33%% (both splits); densest legs in
  crowded sectors hit 46%%. Peer CONFIRMATION must never be a ranking bonus
  (the gate stays restrictive-only, exactly as built on day-8).

### Encoded
1. **`r945.pair_of_day` selects each leg by min neighbour distance**; config
   `pair.selector` accepts only validated selectors (`densest`/`max_p`),
   anything else raises. Leg quality label = the density tag, not a P-based
   STRONG/OK/WEAK (which implied a gradient that doesn't exist).
2. **THE PAIR is the headline and the only sized output.** `--book`
   allocates the capped book across the two legs only (~market-neutral pair,
   but full single-name risk per leg — sizing is still the only risk
   control). The rest of the board prints as CONTEXT and is ledgered for
   learning, never sized.
3. **Ledger `role` column** (`pair` vs `board`): the executed pair now has
   its own cumulative line — the arbiter of whether the 68%%/69%% validation
   survives contact with live trading. Expectation stated up front: live
   will be LOWER (winner's-curse on rule selection is real even with
   splits); low-60s would be a very good outcome.
4. **Crowded-leg warning** printed on the pair (`pair.crowded_conf_warn`),
   instrumented but NOT a gate until live pair data decides.

### Addendum: is 9:45 the right run time? (`validate_time.py`)
Tested decision times 9:35→11:00 with the identical walk-forward pipeline
(features known at T, outcome T→close, densest pair, all four splits).
**9:45 dominated every alternative on hit rate AND capture, and was the only
stable time across all splits**: 68.5%% / +0.390%% vs 9:40's 48.9%% / +0.073%%
(pure noise — the opening rotation hasn't resolved) and 9:50's 58.9%% /
+0.096%%; later times trend into less remaining move (median |move| 0.70%%
at 9:45 → 0.53%% at 11:00) without gaining reliability. Honest caveat: all
hyperparameters were developed at 9:45, so alternatives ran with borrowed
settings — the test proves no alternative beats 9:45, not that 9:45 is
globally optimal. Decision: **the run time stays 9:46** (first moment the
9:45 bar is complete).

## Day-10: first live day of THE PAIR — 2/2, and learning from a WIN

### What happened (user's fills)
CP.TO long 128.45 → 129.34 (+0.69%%) and ABX.TO short 50.98 → 50.81
(+0.33%%): **both legs correct**, ≈ +$256 on the ~$50k pair book. First
entry in the ledger's PAIR line: 2/2, avg capture +0.51%%.

### Why this win teaches something (wins get the same audit as losses)
1. **The density rule earned its keep on day one, for the stated reason.**
   CP was rank #7 of 8 longs by probability but the DENSEST estimate — and
   it produced the best capture on the entire board (+0.87%% from the 9:45
   print). The max-P pick the old rule would have traded (CNR, P=0.65,
   sparse) made +0.01%% — a hit worth nothing. Familiarity beat extremity
   in exactly the way the day-9 validation predicted. n=1 — logged as
   supporting evidence, not proof; NO parameters touched on the back of it.
2. **The untraded board vindicated pair-only sizing.** Board picks went 3/7
   with −0.22%% avg capture (T −0.60%%, BCE −0.62%%, SLF −0.52%%). The old
   whole-board book would have lost money today; the selective pair made
   +0.51%%/leg. Selectivity IS the edge — now visible live, not just in
   backtest.
3. **Slippage is real but symmetric today.** User entry at 9:46 market paid
   +0.17%% vs the 9:45 print on CP (0.87%% model → 0.69%% realized) and
   GAINED ~0.18%% on ABX (bounce sold into). Realized pair average matched
   the model exactly (+0.51%%). Track it in future post-mortems: if entry
   slippage trends one-way, ~0.15-0.2%% is a third of the average edge.
4. **Cumulative honesty check.** Ledger overall 20/37 (54%%) — still the
   validated number; density tags now dense 59%% / mid 38%% / sparse 57%%
   (capture-weighted the ordering is cleaner: +0.13 / −0.28 / −0.14).
   Density-as-gate decision stays PARKED until ~20 tagged DAYS (rows ≠
   days); THE PAIR line is the record that now matters most.

### Encoded
Nothing changed in code — deliberately. The discipline cuts both ways: a
single winning day must not loosen anything (no size-up, no cap-widening,
no new "insight"), exactly as a single losing day must not panic-tighten a
validated rule. The ledger's PAIR line accumulates; the rules stand until
the data, not the mood, moves them.

## Day-11: the late run — 10:35 is not 9:46

### What happened
"Run report" landed at 10:35, 49 minutes past the validated window. The
engine happily printed a 9:45-featured board (pair: CM long / ENB short) —
but CM's price was already +0.66%% past its 9:45 print, and a fresh
10:30-decision read (the variant validated at 64.5%% in validate_time.py)
qualified ZERO longs and NINE shorts: the broad morning ramp had flipped
every long into the fade-prone profile. The published pair was stale on
arrival. Advice given: skip the long leg entirely (fresher lens + crowded
financials warning + spent drift all agreed), trade the densest 10:30
short only (CP.TO, sided-P 0.64, nd 0.25).

### Encoded
1. **LATE RUN banner** (`r945.late_minutes` + `leg_drift`, config
   `pair.stale_after_min` / `pair.spent_drift_pct`): a run >20 min past
   9:46 prints per-leg drift since the 9:45 print with a verdict —
   LONG above print / SHORT below print = "edge partly SPENT — do not
   chase"; the mirrored direction = "entry better than the print".
   The exact CM numbers are the regression test.
2. **Ledger caveat (process, not code):** the publish-time rows for
   2026-07-14 record the engine's stale pair (CM/ENB) — kept untouched per
   the no-hindsight rule; the user's actual executed trade diverged (CP
   short only). One-off caused by the late run; the banner prevents silent
   recurrence, and scoring will note the divergence.
3. NOT built: an automatic multi-time re-decision engine. The 10:30 lens
   exists in validate_time.py and can be run manually on a late day; making
   lateness convenient would encourage it, and every minute after 9:46
   trades away validated capture (0.70%% → 0.53%% median by 11:00).

### The close: what the late day actually cost (post-mortem)
User traded CM long 166.79→166.68 (−0.07%%) and CP short 128.54→128.54
(0.00%%) and called both "big misses". The tape says otherwise — the losses
were PROCESS, not prediction:
1. **CP short was a WINNING call that a chased fill destroyed.** Decision
   price 128.98 (10:30 lens) → close 128.54 = +0.34%% captured by the
   model. The fill at 128.54 was −0.34%% past the decision price — the
   entire edge consumed before entry — then a −0.9%% drawdown (CP hit
   129.65 at 15:20) round-tripped to breakeven on a final-10-minute plunge.
2. **CM long should not have existed.** The chat advice said skip it; the
   stale board itself printed "➤ BUY 148 sh @ market now" beside the
   warning. The order line is the instruction — it won. Tool defect, now
   fixed. (The 10:30 no-longs read was right: CM topped at 168.28 at 10:35,
   the minute the late board printed, and faded to 166.68.)
3. **The model itself had a losing day, honestly logged.** Even punctual
   9:46 execution loses: CM −0.17%%, ENB short −0.86%% (ENB qualified on
   both lenses and still lost — that is the ~1/3 of legs that lose by
   design). PAIR line now 2/4. NO parameter touched: two legs losing the
   same day happens ~1 day in 10 at the validated rates.

### Encoded (the two process fixes)
1. **Stale boards print NO ORDER LINES** (`render`, day-11 regression
   test): past `pair.stale_after_min` every leg's order is replaced by
   "⛔ NO ORDER — stale board: the decision price has expired." A warning
   next to a live order line loses; the order line must not exist.
2. **Fill bound on every order** (`r945.fill_bound`, `pair.max_chase_pct`,
   default 0.15%%): each order prints its worst acceptable fill (LONG ≤,
   SHORT ≥). Past the bound: NO TRADE. CP's exact numbers (128.98 decision,
   128.54 fill = bound violated) are the regression test.

## Day-12: the window-roll test — walking back the 68%% selector claim

### What happened
Morning question: "did yesterday's misses teach us anything that improves
tomorrow's predictions?" Two hypotheses from the day-11 tape were tested
walk-forward (breadth: shorts against a rising tide; crowd-avoidance in leg
selection). BOTH flipped sign between splits — nothing encoded. But re-running
the committed validator on the current data exposed something bigger: with
the rolling 60d window moved by just THREE sessions, the densest selector
fell from 68.5%% (z=3.2, "p≈0.0007") to **52.7%% (z=0.21, p=0.42)**; the
2nd-densest "placebo" now beats it on two splits; max-P swings 50%%→68%%
between odd/even. No selector separates qualified picks reliably.

### Why the original p-value lied (methodology lesson, now a standing rule)
1. Pair legs are NOT independent Bernoulli draws: two per day, sharing the
   day's tide; hits cluster. Effective n was far below 89.
2. All four "splits" (chronological + odd/even) reused the SAME training
   window and the same trained neighbourhoods — they were never independent
   replications, just re-slicings of one fitted object.
3. **New standing rule: a selection/gating claim is not validated until it
   survives a WINDOW-ROLL re-run** (recompute everything on a shifted data
   window), not merely in-window splits. Splits catch overfit patterns;
   only a window roll catches overfit machinery.

### What stands after the walkback
- The 0.55 qualification bar and STAND DOWN behaviour (board base ~51-54%%).
- The first-15-min ramp-fade effect and the 9:45 decision-time comparison
  (relative ordering was stable, though its absolute numbers carry the same
  caveat and 9:40 vs 9:45 remains the sharpest, most mechanism-backed gap).
- The peer-contradiction gate (mechanism-driven, restrictive-only).
- Process rules: too-early guard, LATE-RUN no-orders, fill bounds, sizing.
- Crowding read (44%%/33%% day-9; 44%% on the rolled window) — the one
  stable observation; stays a warning.
- Densest stays as the pair's deterministic tie-break (a daily pair needs
  ONE reproducible rule; live PAIR ledger keeps score) — with stated
  expectation reset to the honest ~52-56%%, printed in the report itself.

### Encoded
r945 header + pair docstring + rendered footer walked back to ~52-56%%;
validate_pair.py header carries the walkback; config comment softened. No
selector change, no threshold change — the reset is in the CLAIMS, which is
where the error lived.

### The close: destination vs road (learning from a scratch and a win)
User's fills: CNQ long 60.12→60.11 (scratch; the model's print-to-close was
−0.17%%, a narrow miss) and CP short 127.28→127.09 (+0.15%%, a hit — and the
fill was BETTER than the print, inside the bound; the fill-bound rule paid
on day one). PAIR line: 3/6 live. The user's key observation: both legs
swung hard against the call mid-day before finishing — CNQ dipped to
−1.3%% at 11:40 then recovered ALL of it; CP popped +0.5%% against the
short before paying. **The engine predicts the destination, not the road.**
Pooled path stats confirm the road is always like this: after a 9:45 entry
the MEDIAN worst swing against a long is −0.68%% (worse-quartile −1.35%%);
against a short +0.78%% (+1.40%%). Today's swings were statistically
ordinary — and holding through them was exactly correct.

**Encoded:** `session_rows` now measures each session's max adverse
excursion after 9:45 (`mae_dn`/`mae_up`); the pair legs print "normal swing
AGAINST this leg: median X / worse-quartile Y — the ROAD, not the verdict;
hold to 3:55." Printed only when ≥100 sessions back it (never fabricated).
This changes no prediction — it arms the holder against the path, which is
where hold-to-close workflows actually break.

## Day-13: the losing day, the deep search, and the honest ceiling

### What happened
Board 3/12; PAIR 0/2 (CVE long −0.91%%, CM short +1.11%% against). Mechanism:
a 9-short board met a +0.42%% TSX rally that began at 9:46 exactly; the pair
was long-energy/short-financials and the sector rotation ran precisely
backwards. The crowding-warned CM leg lost again. User reported −$777 and
−$892 — but at the PRINTED sizes the day was ≈ −$201 and −$223: the
positions were run at ~$100k/leg, 4x the printed $25k risk model. In a
no-stop workflow the share count IS the entire risk control; multiplying it
multiplies every loss identically.

### The deep search: every candidate fix FAILED the discipline — that is the finding
1. **Crowding gate: rejected.** The 44%%/33%% crowd stat that held on two
   windows flipped to 61%% (11/18) when ONE session entered the window.
   The "stable" signal was small-n illusion. The warning line stays (cheap,
   possibly true) but it must not gate.
2. **Board-tilt gate: rejected.** Tilted-board pair legs 42%% vs balanced
   65%% on discovery — and dead even (60/61) on confirm. Split-flip.
3. Standing conclusion, now proven three times (68%% selector, breadth,
   crowding): at ~50 sessions of free 15-min-delayed data, NO selection or
   gating refinement can be validated. "Thousands of lines of code" cannot
   extract information the data does not contain — they can only overfit
   it, and overfit gains evaporate exactly when trusted.

### The honest big picture (what the partners should be told)
Live ledger: 66 scored picks, 33/66 = 50.0%%; PAIR 3/8; last 20 ≈ 10/20.
This is consistent with a thin (52-55%%) edge having a normal bad stretch
AND with zero edge — n is still too small to distinguish. It is NOT
consistent with a high-60s expectation; that number was withdrawn on day-12
and must not be quoted. The genuine ceiling-raisers are data, not code:
real-time quotes/L2 (TwelveData adapter is ready behind an env key), an
ex-dividend calendar, a news feed. Options going forward: (a) keep trading
at PRINTED size while the PAIR ledger accumulates to a decisive n(~100
legs), (b) add paid data and re-validate, (c) paper-trade until the ledger
proves the edge. Any of these is defensible; 4x size on an unproven edge is
not.

### Encoded
1. **Accountability header**: every morning report now prints the live
   record (all / PAIR / last-20) and, while the record sits below 54%%, an
   explicit "NOT yet demonstrated an edge — trade the printed size or do
   not trade" warning (`ledger.live_summary`, tested).
2. **Sizing contract in BOOK mode**: "THE SHARE COUNTS ARE THE RISK MODEL —
   trading larger multiplies every loss by the same factor" with day-13's
   actual numbers as the example.
3. No new gates, deliberately — documented above.

## Day-14: the TwelveData deep validation — one year, four quarters, one survivor

### The data
User provided a TwelveData key (env var only, never stored). Free tier
gates TSX symbols, but 20 universe names have NYSE twins with ~1 year of
5-minute history: 5,160 ticker-sessions across 258 sessions — 4x the Yahoo
window, split into FOUR independent calendar quarters with the verdict rule
pre-registered and committed before results (validate_deep.py).

### Verdicts (permanent — recorded in the script header)
- **REFUTED: ramp-fade.** "Ramps >+0.5%% fade 61%%" — the oldest headline
  claim in r945 — showed fade rates of 42.7-50.5%% across all four
  quarters. Ramps mildly CONTINUE. Removed from every claim surface.
- **NOT VALIDATED: the 0.55 qualification bar.** The qualified pool beat
  its naive-side base in only 3 of 4 quarters and lost to it in one
  (47.3%% vs 53.3%%). Consistent with the live 33/66. The bar stays as the
  candidate-generation mechanism, but no pool-level edge may be claimed.
- **VALIDATED (the only one): the densest pair leg.** Beat both the
  qualified pool and max-P in all four quarters (54.7/54.3/56.0/52.9%%),
  capture positive in every quarter. Pooled: 239/439 = 54.4%%, z=1.86
  (p≈0.03), weighted capture +0.094%%/leg PRE-COST ≈ $23/leg/day at the
  printed $25k size. Day-9's direction was right; its magnitude (68%%) was
  winner's curse — the honest number is ~54%%.

### What this means (told to the user straight)
The system's ceiling on this data is a real, thin, barely-significant edge
worth ~$20-45/day pre-cost at printed size — commissions and slippage can
plausibly halve it. No amount of code changes that; only better data
(real-time TSX feed, order flow, calendars) could, and even that is
unproven. The tool's job from here: keep the pair workflow, keep printed
sizes, keep scoring the ledger, and never again claim more than the deep
validation supports. US-twin caveat: validation sample, not live levels —
FX separates the lines intraday.

### Addendum: universe expansion (21 → 61) tested and REJECTED
User's proposal: scan far more names so better opportunities aren't missed.
Tested properly (validate_universe.py): built a 61-name TSX-60-style list,
ALL passing a $10M/day median dollar-volume screen, and re-ran the
walk-forward pair machinery. Result: densest legs COLLAPSED to 40-50%% hit
with negative capture in 3 of 4 blocks (vs 51-60%% for the 21-name list on
identical data). Mechanism, verified by inspecting the picked legs: the
density selector's "familiarity" measure is hijacked by low-volatility
utilities/telecoms/staples (EMA, BCE, T, L, H) that sit at the centre of
the pooled feature space every single day — permanently "familiar," no
signal, tiny moves. Per-name volatility normalization did not rescue the
wide universe (26.9-46.4%%) AND broke the year-long validated result on 20
names (fails the all-quarters rule). Both changes rejected. **The
familiarity edge lives in a compact, homogeneous, liquid universe —
breadth dilutes it.** "Opportunities outside the radar" were looked for,
measured, and do not exist for this machine. The 21-name list and global
feature scaling stand; any future expansion must pass the deep
four-quarter protocol first.

## Day-15: a clean 2/2 — and the top of the board blew up without us

Pair: CNR long +0.25%% (the user's "end spike" was the ROAD pattern — faded
to −0.45%% by 14:55, within the printed median swing, then the last hour
paid; second identical V this week) and NTR short −0.45%% captured. Fills
inside bounds both legs; realized ≈ +$193 at printed size. Board 4/8.

The live lesson worth recording: the two HIGHEST-P picks on the board were
the day's disasters — BCE (P=0.65, top of board) −2.05%% and T (0.62)
−2.74%%, a telecom sector collapse. Max-P would have handed the user BCE
as the headline long; density selection took CNR (rank #5 by P) and won.
Recurring live confirmation of the day-14 deep finding: no P gradient,
extremity is often the trap. Both telecoms escaped peer machinery (group
of 2 — below all thresholds): observation only, NOT a rule; "avoid
telecoms" and "last-hour reversion" are exactly the kind of n=1 patterns
the discipline exists to refuse.

Cumulative: 37/74 (50%%); PAIR 5/10; dense tag 54%% / +0.12%% capture —
still the only cohort with positive capture, still tracking the
deep-validation number. Nothing encoded; nothing loosened.

## Day-16: the market-dump day — the pair structure was the protection

### What happened
TSX fell −1.06%% from 9:45; ALL financials collapsed together (RY −2.17%%,
BMO −2.04%%, MFC −1.82%%, TD −2.44%%). Pair: TD long (crowd-warned) −2.44%%
— a genuine tail day, beyond the printed worse-quartile road within 25
minutes — and TRP short +1.79%% captured. Net at printed size ≈ −$75 on a
−1%% tape day: the ~market-neutral pair did exactly what it exists to do.
Board 4/13. Crowd-warned pair legs are now 0/3 live (CM long d-11, CM
short d-13, TD long d-16) — still n=3 on an unstable stat; warning, not
gate.

### The one adjustment today motivates: a DISASTER STOP — year-tested
Pre-registered criteria, tested on the year-long data across all four
quarters (scratchpad stop_test, results permanent here):
- Stops at −2.0%%/−1.5%%/−1.0%% FAIL — they stop out the V-day winners
  (Q4 capture collapses +0.135%%→+0.044%% at −2.0%%).
- −2.5%% is EV-NEUTRAL in all four quarters (max diff 1.4bp = noise) and
  cuts the worst leg −3.88%% → −2.55%%.
- Strict pre-registered adoption bar (capture ≥ in ≥3/4 quarters) failed
  by 0.2bp, so the validated hold-to-close contract is UNCHANGED.
**Encoded as an OPTIONAL printed circuit-breaker** (`r945.disaster_level`,
`pair.disaster_stop_pct: 2.5`): each leg prints its disaster price with
the measured trade-off stated. Honesty note: −2.5%% would NOT have saved
today's TD (bottomed −2.44%% — inside the line); its value is the −3%%+
true disasters. Today's protection was the pair structure, and it worked.

## Day-17: rebound day — the pitfall-avoidance rules that FAILED their test

### What happened
Day after the dump: broad rebound. Board 6/8 — ALL six longs hit; both
shorts (SHOP pair leg −1.44%% against, T.TO board −2.42%% against) were
sparse gap-down continuation calls that the bounce ran over. User's pair:
MFC long +0.47%% realized (WIN, the dense #1-by-P leg), SHOP short −1.42%%
realized (LOSS — flagged "sparse, thinner evidence" in the morning report
itself). Net ≈ −$238 at printed size. PAIR line 7/14.

### Two pre-registered hypotheses from today's shape — BOTH REJECTED
Tested on the year data with live-faithful density labels, all-quarters rule:
1. **"Sparse leg → no leg": REJECTED.** Sparse pair legs hit 57/54/71/43%%
   by quarter (above 50%% in 3 of 4, positive capture in 3 of 4); dropping
   them worsens Q1 and Q4. Today's SHOP loss and day-13's CP WIN are the
   same cohort — one bad draw does not condemn it.
2. **"Minority-side leg on a ≥75%%-tilted board → no leg": REJECTED.**
   Against-the-tilt legs hit 53-61%% with the BEST capture of any cohort
   in Q3/Q4 (+0.488%%/+0.274%%); dropping them guts Q3 (+0.192→+0.069%%).
   The lone qualifier against a trending board is historically a strong
   trade that happened to lose today (and day-13).

### The standing lesson
The discipline's value is REFUSING adjustments as much as making them —
five candidate "fixes" have now failed the four-quarter protocol
(normalization, universe expansion, crowding gate, sparse-drop,
minority-drop) while exactly one rule ever passed it (densest leg). A
losing leg is the tuition of a ~54%% system; the hedge (MFC's win
offsetting most of SHOP's loss) and the printed size remain the actual
protections. Nothing changed; the reasons are recorded here so tomorrow's
bad day doesn't re-litigate them.

## Day-18: the first one-legged day — two structural bugs caught before entry

Board: nine qualified longs, ZERO shorts — the contract's "no forced leg"
case arrived. Two defects surfaced and were fixed BEFORE the user entered:
1. **One-legged sizing inverted risk.** The allocator gave the lone MFC leg
   the WHOLE $50k book — double single-name risk on a day with no hedge.
   Fixed: the book divides by at least two legs (`allocate_book min_legs`);
   a missing leg now reduces exposure (lone leg ≈ $25k, rest stays cash).
2. **Bar revision + re-publication.** A verification re-render 5 minutes
   later saw REVISED Yahoo bars (SHOP's first-15m print changed), produced
   a different board (CM/SHOP "pair"), and silently appended them to the
   ledger as pair rows. Accidental rows removed (documented here — the only
   ledger edit ever made, correcting a tool artifact, not an outcome);
   encoded **PUBLISH-ONCE**: the first --book run of a date is THE
   publication; any later run prints "informational ONLY" and cannot touch
   the ledger. The (date,ticker) dedupe alone was insufficient because
   revised bars qualify NEW tickers.
Lesson class: the 9:46 board is built on bars that the source may still
revise for minutes afterward. The publication is the decision; everything
after is commentary.

## Side-quest research: hold the pair legs for a week? (NO — measured)

Question: is holding the daily pair legs 1-5 sessions better than intraday?
Year-data answer (439 legs, walk-forward, per-quarter):

| horizon | mean capture | hit | std | worst leg | mean/std |
|---|---|---|---|---|---|
| 0d (current) | +0.094%% | 54.4%% | 1.09%% | −3.9%% | 0.086 |
| 1d | +0.143%% | 53.4%% | 2.07%% | −8.8%% | 0.069 |
| 3d | +0.183%% | 49.9%% | 3.37%% | −15.3%% | 0.054 |
| 5d | +0.177%% | 51.3%% | 3.95%% | −17.6%% | 0.045 |

Mean capture creeps up with horizon but risk explodes (3.6x std, 4.5x
tail) and hit decays to a coin flip; quarters flip sign at every horizon
past 0d (fails the all-quarters rule). The decomposition is decisive:
LONG legs 5d = +0.62%% while SHORT legs 5d = −0.39%% — the multi-day
"return" is just market drift (beta), not signal; the engine's edge has a
shelf life of ONE session. A week-held short additionally pays borrow and
carries open-ended gap risk that no intraday line protects. VERDICT: the
intraday contract is the best risk-adjusted expression by a wide margin;
weekly holds trade beta with 4x the pain. Daily workflow unchanged.

## Day-19: the prediction hit; the fill lost — and the order gets a clock

### What happened
One-legged day (MFC long only). The model's call was CORRECT: 9:45 print
60.63 → close 60.67, +0.06%%, a scored HIT (PAIR line 8/15 = 53%%, on the
validated ~54%%). The user's fill was 60.92 — 0.21%% PAST the printed fill
bound (≤60.79), bought inside the 9:50-10:55 spike to 61.12 — and rode
−0.41%% down from there. Under the system's own printed rule the correct
action at 60.92 was NO TRADE. Same failure shape as day-11's CP short
(winning call, chased fill, captured nothing), now on the long side.

### "Accuracy is decreasing" — checked against the record
The traded PAIR line is 8/15 with 3 of the last 5 hitting — exactly on
the stated ~54%% expectation. What has cost money this week is not the
direction calls; it is the gap between the printed contract and the
executed trade (4x size day-13, bound violations day-19). The system
cannot out-predict its own execution.

### Encoded
**Entry window** (`pair.entry_window_min`, default 10): every order now
prints "order window: until HH:MM ET — unfilled by then (or bound
broken): NO TRADE today." Price was already bounded; TIME wasn't — and
MFC drifted back inside the price bound at 11:10, where an entry would
have been an 85-minute-late unvalidated bet (the day-11 principle). The
order now expires on whichever bound breaks first.

## Day-20: a PROFITABLE day read as a failure — and the 6th rejected "double down"

### The dollars (user's own fills, both inside bounds)
NTR long 258 sh: 96.97 -> 96.48 = -$126.  SHOP short 153 sh: 162.45 ->
157.86 = +$702.  **NET +$576** at printed size. The pair did EXACTLY what
it is built to do: both fills inside the bounds, the short winner (+2.83%%
captured) dwarfed the long loser (-0.51%%) — the documented short-capture
asymmetry (day-1) paying out. This was one of the best days of the run,
experienced as a disappointment because attention anchored on the one red
leg. PAIR line 9/17 = 53%%, on the ~54%% expectation.

### "Double down on the better prediction" — tested, REJECTED (6th time)
The intuition: SHOP had aligned down-momentum (gap -1.18%%, first-15m
-1.20%%); NTR was conflicted (gap +0.77%%, first-15m -0.08%%). Pre-registered
year test (align_test.py, all four quarters): aligned legs 54.4%% vs
conflicting legs 54.5%% (z=-0.02); conflicting legs had BETTER capture in
all four quarters; dropping them lowers returns every quarter. Momentum
alignment has ZERO predictive value. You cannot identify the better leg at
9:46 — that is not a tooling gap, it is the measured nature of a ~54%% edge.
Rejected fixes now number SIX (normalization, universe expansion, crowding,
sparse-drop, minority-drop, momentum-alignment) against ONE that ever
passed (densest selection).

### The standing truth to internalize
A ~54%% pair means ~46%% of legs lose, unpredictably, and the edge is
delivered by the short-side capture asymmetry over many days — NOT by
being right on any given morning. "Prevent the misses / double down on the
winners" is mathematically the request to predict which coin-flip-plus lands
heads; every attempt overfits and the year data kills it. The system's job
is to keep taking both legs at printed size and let the asymmetry compound.
Nothing encoded today; the discipline held and the day made money.

## Day-21: full review — run time re-tested on a year (9:35 refuted, 9:40 rejected)

### Today
Board 11/13 — the best board of the run (9 of 10 longs hit; both other
energy shorts, CNQ -1.42%% and CVE -1.67%%, were big winners). PAIR: BNS
long +0.18%% HIT, TRP short -0.09%% miss (TRP was down to 99.08 at lunch
and ground back). Net -$17 at printed size — a scratch. PAIR line 10/19.

### The live book, as instructed at printed size (21 legs, 11 sessions)
  long legs   45%% win, avg -0.181%%, -$498
  short legs  50%% win, avg +0.231%%, +$577
  ALL         48%% win, avg +0.015%%, **+$79**
Flat-to-positive, with the short-capture asymmetry carrying the book
exactly as the year validation described. **Execution is no longer a
leak**: measured against the 9:45 prints, fills now run +0.036%%/leg in
the trader's FAVOUR (+$163 over 18 legs); the only material negative was
the day-18 bound violation (-0.47%%). Fill bounds + entry windows worked.

### Run-time question re-opened properly (validate_time_deep.py)
The original time test used the 60-day Yahoo window; day-12 proved those
produce mirages, so the whole question was re-run on the year-long
US-twin data (5,160 ticker-sessions) with the adoption bar pre-registered.
- **9:35 REFUTED.** The "earlier = more opportunities + better entries"
  hypothesis fails on every axis: 49.2%% hit (below a coin flip), capture
  negative in 3 of 4 quarters, and FEWER legs/session (1.74 vs 1.78), not
  more. Two 5-minute bars do not resolve the opening rotation.
- **9:40 met the bar, then failed the decisive paired test.** It beat
  9:45 on capture in 4/4 quarters unpaired — so it earned the paired test
  (paired_time.py) isolating the two possible channels: same-pick earlier
  entry is worth -0.012%% (t=-0.60, better on 32/72 legs) and different-pick
  selection is identical (+0.077%% vs +0.078%%, 53%% vs 55%%). Neither
  channel carries an edge; the aggregate gap was composition noise, and
  the two datasets disagree (60-day run scored 9:40 at 48.9%%).
- **Decision: 9:46 stands.** Eighth candidate improvement rejected.

### Codebase review
149 tests green, 7,769 lines, 20 modules. Scanned for stale accuracy
claims: every walked-back number (68%% selector, 61%% ramp-fade, 67%%
gradient) now appears ONLY inside its own refutation — no unsupported
claim can reach a morning report. Legacy 9:31-era modules (report/scan/
midday/hold/confirm) remain tested but are no longer in the daily path.

### Standing scoreboard of candidate improvements
REJECTED (8): per-name normalization · universe expansion to 61 names ·
crowding gate · sparse-leg drop · minority-leg drop · momentum-alignment ·
multi-day holds · alternative run times (9:35/9:40/9:50/10:00/10:30).
ADOPTED (1): densest-leg selection. Plus process rules that all paid off:
too-early guard, late-run no-orders, fill bounds, entry windows, min-legs
sizing, publish-once.

## Day-22: the deep set rebuilt FREE and 2x bigger — 4 more rejections, 1 adoption

### The question asked
"Go deep, micro and macro, find why the picks miss and actually raise the
9:46 accuracy." Answered by measurement, not opinion. Every claim below is
re-runnable: `python validate_twins.py`.

### First: the deep data problem was fixed
`validate_deep.py` needs a TwelveData key AND a scratchpad of pre-downloaded
JSON that does not survive a session — so the repo's only deep protocol was
**unrunnable**, which is exactly how a 60-day artifact becomes permanent.
Measured the alternatives: Yahoo hard-caps 5m bars at 60 days (confirmed,
HTTP 422 beyond), but serves **hourly bars for 720 days**. TSX hourly bars
come back with volume zeroed (86%% of rows — kills the `vp` feature); the US
dual-listings do not. Result: `validate_twins.py`, **9,651 ticker-sessions /
490 sessions / 20 names, free, rebuildable any time — ~2x the paid study's
5,160.** Caveat carried everywhere: its entry is 10:30 (first hourly bar),
so it is a MECHANISM sample and can never certify live 9:45 levels.

### The diagnosis (why legs miss)
- A universe name moves with the cross-sectional median ("the tide") **65-67%%
  of the time** — far more reliably than the engine's own ~54%% edge. The tide
  explains 6.8%% (60d/5m) to 24.0%% (2yr/1h) of single-name variance.
- **But the pair already neutralises it.** The two-leg book's beta to the tide
  is **+0.12**, and hedged calm vs windy days differ by 0.02%%/day (P(NET>0)
  52%% vs 49%%). There is no market-exposure leak left to fix.
- Therefore **the misses are idiosyncratic** — which is the same as saying
  there is nothing left for a smarter selector to remove. This is the
  quantified version of what days 13/14/17/20 kept concluding.

### Four more candidates tested, ALL REJECTED (pre-registered, all-four-quarters)
1. **Beta-matched pairing** (pick the long/short combo with the closest betas):
   quarters +0.009/+0.046/-0.060/+0.016. Fails. Its premise was wrong anyway —
   see the +0.12 beta above.
2. **Tide-removed (cross-sectional) training target**: +0.020/-0.001/+0.004/
   -0.032. Fails.
3. **Both combined**: +0.036/-0.021/+0.052/+0.044 — and *smaller than the
   2nd-densest placebo* (+0.030). Fails.
4. **"One-legged days are structurally worse"**: unhedged days +0.029%%/day vs
   hedged -0.012%%, quarters flip sign. Fails.

### The sixth confirmation that 60 days manufactures edges
Cross-sectional reversal (hardest first-15m riser underperforms after) measured
**corr -0.11, Q5-Q1 spread -0.43%%, same sign in all four blocks on 60 days** —
a textbook "discovery". On 486 sessions it is **corr -0.016, spread -0.005%%,
quarters flipping sign**, portfolio win rate 48-51%%. A brand-new hypothesis
class, same mirage. Also on the deep set: **no selector separates from
placebo** (densest 50.1%%, max-P 48.3%%, 2nd-densest 50.7%%, random 50.2%% — the
whole spread inside one standard error of 1.7pp).

### A shipped claim was overturned
**"Shorts capture ~2.7x more per win" is REFUTED at scale**: on 809 walk-forward
legs the avg-win/avg-loss ratio is **1.00x for shorts, 0.98x for longs**, with
per-quarter capture flipping sign on both sides. That number had been printed in
the r945 header since day-1 and used to justify the short side. Corrected in
place. (The live book's short-side outperformance stands as a live observation;
what died is the claim that a structural 2.7x magnitude asymmetry drives it.)

### ADOPTED (the 2nd rule ever to pass): equal-RISK leg weighting
On a two-leg day the legs are now weighted **inversely to each name's trailing
entry->close volatility** instead of equal-dollar, capped 35/65 so it can never
become a single-name bet (median split is only 58/42).

| metric | equal-DOLLAR | equal-RISK |
|---|---|---|
| NET std | 0.587 | **0.518 (-11.8%%)** |
| worst day | -2.22%% | **-1.52%%** |
| mean NET | -0.012%% | -0.005%% (unchanged) |
| quarters with lower vol | — | **4 of 4** |

**Why this one survived where nine alpha claims died: it predicts nothing.** It
is a variance identity — stop letting the jumpier leg dominate the book — so
there is no signal to overfit. State it honestly: it shrinks the **size** of bad
days, **not their frequency**. The hit rate is untouched (same picks, same
direction calls). Anyone who reads it as "more accuracy" has misread it.

### Also fixed: a real bug in the density labels
The dense/mid/sparse cutoffs were computed by measuring sampled training rows
against a pool **containing themselves** — each matched itself at distance 0,
biasing mean neighbour distance **-2.4%%** and both cutoffs ~2.3%% low, so live
picks (which never self-match) were tagged "sparse" more often than earned.
Selection is unaffected (it compares nd between live picks), but the dense tag
is the pre-registered candidate for a future gate — a biased label would have
corrupted the very evidence meant to decide it.

### The honest answer to "raise the accuracy"
Per-leg hit rate at 9:46 could not be raised, and the reason is now measured
rather than asserted: the tide is already hedged out, the residual is
idiosyncratic, and on 486 sessions the selection layer is statistically inert.
Ten candidate improvements have now been rejected against two adopted. What
improved today is **risk per unit of return** — a smaller worst day and 12%%
less volatility for the same picks — plus a deep-validation protocol that
anyone can re-run for free instead of trusting a number in a docstring.

### Standing scoreboard
REJECTED (12): per-name normalization · universe expansion · crowding gate ·
sparse-leg drop · minority-leg drop · momentum-alignment · multi-day holds ·
alternative run times · beta-matched pairing · cross-sectional target ·
beta+cross-sectional · one-legged-day penalty.
ADOPTED (2): densest-leg selection · equal-risk leg weighting.
REFUTED CLAIMS: ramp-fade 61%% · 68%% selector · 67%% gradient · short 2.7x
capture asymmetry.

### The close: the morning's diagnosis confirmed itself the same afternoon
PAIR: **BMO long -0.166%% MISS, BCE short +0.464%% HIT — pair NET +0.149%%.**
Neither leg came near its 2.5%% disaster line (BMO worst -1.09%% at 13:10, BCE
worst +0.66%% at 10:40 — both inside the printed road). PAIR line 11/21 (52%%).

**Board 4/11 — and the pair still made money. That is the whole thesis in one
day.** The tide ran **-0.345%%** (15 of 21 names down, breadth 29%%) against a
board that was **9 longs vs 2 shorts**. The long side was duly run over (2/9);
the short side went 2/2; the hedge carried the day. A directional book on that
board loses; the pair nets positive.

**The 65-67%% tide-following base rate measured this morning printed 71%% this
afternoon** — on the very session it was derived for. The diagnosis is not a
backtest artifact.

Two honest debits, neither of which may trigger a reversal:
- **Equal-risk sizing COST ~$23 today** (+$50.54 vs +$73.78 equal-dollar),
  because the winning leg (BCE, 1.05%%/day) was the jumpier one it down-weights.
  This is the *expected* cost of a variance trade, not evidence against it: the
  rule was adopted on 4-of-4 quarters of volatility reduction, and a single
  favourable draw for the volatile leg is exactly the day it gives back. Day-17's
  standing rule applies — one bad draw does not condemn a cohort.
- **Max-P would have beaten density on BOTH legs today** (MFC +0.355%% vs BMO
  -0.166%%; CVE +1.468%% vs BCE +0.464%%). n=1, and max-P measures *worse* over
  809 legs (48.3%% vs 50.1%%) and lost to densest in all four quarters of the
  day-14 study. Logged, not acted on. Recording it here is the point: the
  temptation arrives on the days the shipped rule underperforms.

One process note: the `--book` publication happened at 10:46, not 9:46, so the
board was stale and the tool correctly printed **NO ORDER** on both legs rather
than a live order line at expired prices. The day-11/day-19 machinery did its
job — but for sized orders the `--book` run must happen AT 9:46.

## Day-23: the day the sizing rule paid for itself — and a miss that wasn't one

### What happened
Board **8/10** — a broad rally (tide **+1.190%**, breadth 76%). PAIR: **SLF long
+0.987%% HIT** (worst against just -0.07%%, a clean one-way trade) and **AEM short
-1.298%% MISS**. Neither leg approached its disaster line (AEM worst +2.26%% at
12:00 vs the +2.5%% line at 205.32 — the printed road held again).

### The headline: equal-risk sizing turned a losing day into a winning one
| | shares | P&L |
|---|---|---|
| equal-RISK (shipped day-22) | SLF 276 / AEM 87 | **+$93.96** |
| equal-DOLLAR (the old rule) | SLF 212 / AEM 124 | **-$76.48** |

**Worth +$170.44 today.** AEM's trailing vol was 1.83%%/day vs SLF's 0.87%%, so
the rule put 65%% of the book on the calm leg and 35%% on the jumpy one — and the
jumpy one was the loser. Day-22 the same rule COST $23 when the volatile leg
won. Two sessions, +$147 net: that is precisely the shape of a variance trade,
and precisely why it was adopted on volatility reduction rather than on returns.

### The "big miss" was the market, not the pick
Decomposed against the tide: **AEM +1.30%% actually BEAT the +1.19%% tide** — in
market-neutral terms the short was **-0.11%%**, essentially median (rank 10 of
21). Meanwhile the "correct long" SLF (+0.99%%) **UNDERperformed** the tide by
-0.20%% (rank 12 of 21). The leg that felt like a disaster was the better
relative call, and the leg that felt like a win was the worse one. A short
against a +1.19%% tape loses in dollars no matter how good the name selection is
— which is the entire reason the book carries a long leg at the same time.

### "How do we avoid the bad short?" — every candidate is already dead
Today's short hit four cohorts that have EACH been separately tested and
rejected: sparse-tagged (day-17), minority side of a 9-long board (day-17),
momentum-aligned gap-down continuation (day-20), small peer group (day-15). Two
NEW hypotheses were pre-registered and tested on the deep set today:
1. **"Don't short a big gap-down": REJECTED.** Pooled it looks real (bottom-gap
   shorts hit 41.2%% vs 48.7%%), but it holds in only **3 of 4** quarters — and
   the LONG side shows the identical pattern in 3 of 4, so it is a gap-bucket
   artifact, not a short-specific edge. Pre-registration required it to exceed
   the opposite side; it did not.
2. **"Don't take legs already stretched from the prior close" (gap+r0 in the leg
   direction): REJECTED.** 2 of 4 quarters. The 60-day set said the opposite of
   the deep set (sparse-stretch shorts 80%% vs 48.7%%) — another window mirage.

Rejections now number **14** against **2** adoptions. The honest answer to
"avoid the bad short" is that this loss is not identifiable at 9:46 by any rule
that survives its own out-of-sample test — it is the 46%% of legs that lose.

### What the WINNING long teaches (wins get the same audit)
SLF was **dense**, rank #2 by P, and never traded more than 0.07%% against the
entry — it was correct within five minutes and stayed correct. There is no
action in that: the live dense cohort is now **28/51 (55%%) with +0.01%% capture**,
still the only tag beating its peers (mid 45%%, sparse 53%%), still tracking the
day-14 deep number, still short of the ~20-tagged-day gate. Nothing to change.

### Encoded: the ledger was silently misreporting the book (day-23 fix)
`avg move captured` averages the two legs EQUALLY — correct until day-22 made
them deliberately different sizes. Today it printed **-0.156%%** for a pair whose
book made **+$94**. A metric that reports a profitable day as negative would
have corrupted every future judgement of the strategy. Fixed: publish time now
persists each pair leg's share of book capacity (`weight` column), and the
report prints a **book-weighted return** beside the equal-weighted one — the
former judges the executed strategy, the latter stays the clean measure of the
DIRECTION calls. Existing rows keep a blank weight and are never back-edited
(day-18 rule); the metric starts accruing from day-23.

## Day-24: both legs wrong, and this time it was the PICKS — plus the worst bug yet

### What happened (FINAL, from official daily closes)
PAIR: **ENB long -1.021%%** and **BCE short -1.650%%** — a "none" day, both legs
wrong (~14-16%% of sessions). NET at printed size **≈-$654** (equal-risk sizing
saved ~$19 over equal-dollar; the only thing that worked).

**Unlike day-23, the market is no excuse.** The tide was ≈-0.1%% on 48%% breadth
— a flat tape — and both legs lost on RELATIVE terms too, so this was stock
selection, not the tape. Day-23's honest finding was "the miss was the market,
not the pick"; today's is the opposite and is recorded as plainly.

**CORRECTION (written day-25):** this section originally reported the 14:34
intraday state — "ENB -0.906%%, BCE -1.844%%, NET -$668, BCE rank 2 of 21, the
worst relative leg of the run" — as if it were the outcome. Those were live
mid-session numbers, and BCE in particular was quoted mid-swing. The direction
of the day is unchanged, but writing intraday figures into the permanent record
as results is the SAME error class as the ledger bug documented below, made in
prose instead of CSV on the very day it was diagnosed. Numbers above now come
from official daily closes only.

### Three causes, one of them a judgement error
1. **The other engine was right and was overruled.** The morning summary noted
   that `report.py` had BCE as a LONG and T.TO as THE CALL long, contradicting
   r945's shorts — and then advised following r945 as "the validated
   workflow". BCE closed +1.83%% and T.TO +2.83%%, the two strongest names on
   the board. The reasoning was defensible (r945 owns the 9:45 horizon,
   report.py is the legacy 9:31 lens) but the call cost money. Logged, NOT
   turned into a rule: two names on one day is exactly the sample size this
   discipline exists to refuse.
2. **A structural blind spot, now fixed.** BCE and T.TO are the whole telecom
   group. The peer gate needs >=3 OPPOSING picks and the crowding warning >=3
   AGREEING picks — a 2-name group can reach neither, so **6 of 21 names
   (gold, telecom, rail) were invisible to all peer machinery**. This is the
   SECOND time a 2-name telecom move took out picks unflagged (day-15: BCE and
   T both long, both collapsed; today: both short, both ripped).
3. **The crude warning was right about the risk, wrong about the mechanism.**
   ENB was flagged as "substantially a crude bet". Crude rose (+7.09%%, above
   the +6.50%% at print) and ENB fell anyway — it decoupled. The concentration
   warning was reasonable; it is not what killed the leg.

### Tested and REJECTED as a gate (#15) — but shipped as a warning
PRE-REGISTERED: "a pair leg whose PEER GROUP IS FULLY ALIGNED with it
underperforms." Fraction-of-group, not count, so a 2-name group can register.
- Fully-aligned legs: **38.7%% hit / -0.076%% capture (n=62)** vs 50.7%% /
  +0.017%% for the rest — the largest gap any candidate has produced.
- But **only 3 of 4 quarters** (Q2 flips: +0.184 vs +0.003). **FAILS** the
  all-four bar, exactly as the day-13 crowding stat did before it flipped.
- A PLACEBO grouping did NOT reproduce it (fully-aligned 56.6%%, 2/4) — so the
  signal is plausibly real. Plausible is not proven.
**Decision: no gate.** `r945.sector_warning` is now FRACTION-based, so a fully
aligned group of ANY size warns. Replayed on today's board it flags BOTH legs
(BCE "ENTIRE telecom 2/2", ENB "ENTIRE energy 5/5"); the old count rule was
SILENT on BCE. Re-test when n grows — if it holds 4/4 it becomes the third
adopted rule.

### THE WORST BUG FOUND SO FAR: the ledger scored a live session
`python ledger.py --score` run at **15:05** — 55 minutes before the close —
cheerfully wrote LIVE mid-session prices into the permanent record as
outcomes. ENB was stamped -1.136%% while the session still had an hour to run.
Nothing in the tool objected.

This is worse than any losing trade. The ledger is the arbiter of every claim
this repo makes — the PAIR line, the density hypothesis, the book-weighted
return, the "not yet an edge" warning. Non-final rows corrupt all of it, and
afterwards there is **no way to tell which rows were affected**.
- **Fixed**: `ledger.session_is_final` + a hard refusal in `score_rows`; held
  back rows stay blank and print an explicit warning naming the close time.
- **Repaired**: the 10 contaminated rows were blanked and re-scored from
  official daily closes. (Second ledger edit ever made, and like day-18's it
  corrects a TOOL ARTIFACT, never an outcome.)

**AND A SECOND BUG IN THE SAME PLACE, found day-25 because the first fix was
incomplete.** `close_fn` took only a ticker and returned `get_quote().last` —
the LATEST price, whatever the row's date. So scoring yesterday's rows the next
morning recorded TODAY's live price as yesterday's close: BCE.TO went in at
+0.049%% when its actual 2026-07-29 close was **+1.650%%**, a 1.6pp error, and
three of the ten hits flipped. The day-24 guard ("is the session final?") did
not catch it because the session WAS final — the wrong day's price was.
- **Fixed**: `close_fn(ticker, DATE)` is now the contract, served from cached
  daily bars; a date with no close is left blank, never approximated.
- **Audited**: all 157 scored rows re-checked against official daily closes.
  Exactly the 10 rows from that one mis-scored run were wrong; the other 147
  match. The track record before day-24 is sound.
- **Standing rule**: after any change to scoring, re-run the full audit. Two
  bugs in one function in two days, both silent, both in the component that
  grades everything else.
- Lesson class: the guards were all built around *entry* (too-early, stale
  board, fill bounds, entry window). Nothing guarded the *measurement*. A
  system that grades its own homework needs a clock on the grader too.

### Also shipped: the overnight-hold numbers now print next to the order
Prompted by a live "should I hold these overnight?" while both legs were red.
The measurement existed (day-18 side quest) but sat in a document nobody opens
at 3:50pm, which is precisely when the temptation arrives. BOOK mode now
prints: hold-to-close +0.094%%/54.4%%/std 1.09%%/worst -3.9%% versus one night
+0.143%%/53.4%%/std **2.07%%**/worst **-8.8%%** — one night nearly doubles
volatility and worsens the tail 2.3x, the 5-day "gain" is drift not signal
(longs +0.62%% vs shorts -0.39%%), and a held short pays borrow into gap risk
this tool has no calendar or news feed to price.

### Standing scoreboard
REJECTED (15): + fully-aligned peer group (3/4 quarters, warning only).
ADOPTED (2): densest-leg selection · equal-risk leg weighting.

## Day-25: external audit — 9 of 10 P0 findings confirmed and fixed

An independent software/model audit was received. Every finding was
**re-verified against current code before acting**; the results are recorded
here with the same standard applied to our own claims.

### Verification: 9 confirmed, 1 already fixed, several figures stale
| # | Finding | Verdict |
|---|---|---|
| 1 | adapter hard-coded, config ignored | **CONFIRMED** `r945.py:381` |
| 2 | signal bars taken by position, unvalidated | **CONFIRMED** `r945.py:402-405` |
| 3 | fill bound anchored to live price | **CONFIRMED** `r945.py:545`, locked by `test_dayeleven.py:117` |
| 4 | entry window measured from run time | **CONFIRMED** `r945.py:561-562` |
| 5 | re-run prints fresh order lines | **CONFIRMED** `r945.py:662` |
| 6 | ledger scores against the wrong date | **ALREADY FIXED** earlier the same day |
| 7 | research path scores a partial session | **CONFIRMED** `validate_pair.py:71` + `r945.py:105` |
| 8 | fetch failures silently shrink the universe | **CONFIRMED** `r945.py:386-387` |
| 9 | crashes on a cp1252 Windows console | **CONFIRMED** (14 non-ASCII glyphs) |
| 10 | README advertises the legacy command | **CONFIRMED** `README.md:52,59` |

The audit's *performance* figures come from a pre-day-22 snapshot (126 scored
rows, 19 pair legs, equal-DOLLAR sizing, 148 tests with one failure, no git
history). Current: 157 scored rows, 25 pair legs, equal-RISK sizing, 177 tests
green, full history. **This does not weaken the P0 findings** — those were
verified line by line against today's code — and its central conclusion is one
this journal already reached independently: no material executable edge is
demonstrated, and 52-56% accuracy *means* missing 44-48% of legs.

### The three that were costing money
1. **The no-chase bound enforced nothing.** `render()` passed `r["last"]`, so
   the "bound" moved with the market: on a leg running away from the print it
   silently authorised an unbounded chase — the exact failure it exists to
   prevent, and the day-11/day-19 losses it was written for. Now anchored to
   `p945`, and the test that locked the bug now locks the fix.
2. **The tolerance exceeded the edge.** 0.15% chase against a measured
   +0.094%/leg pre-cost edge: a fill at the bound could pay away more than the
   entire edge before costs. Tightened to **0.04%** — a fraction of the edge,
   not a round number. Deliberately fail-closed; it produces more no-trades.
   (Honest corollary: on a ~$30 name one tick is 0.032%, so the tolerance is
   about one tick. That is a real signal the edge may not be capturable in
   low-priced names, not a threshold to loosen.)
3. **The order window grew when you were late.** It ran from RUN time, so a
   first run at 09:55 minted an order valid to 10:05 — 20 minutes past the
   validated print. Now anchored to the signal bar: running late SHORTENS the
   window, and past it the tool prints ORDER WINDOW CLOSED.

### The three that were silent-failure risks
4. **Signal bars are now proven, not assumed** (`validate_signal_bars`): first
   bar exactly at the open, exact 5-minute grid, no duplicates, third bar
   COMPLETE, OHLC/volume sanity. A halt or missing opening bar used to shift
   `iloc[2]` to a different time with no visible failure — and every downstream
   guard is denominated in that price.
5. **Coverage gate** (`coverage_ok`, default 80%): the pair is chosen by
   comparing names against each other, so a silently missing name changes the
   bet. Below the floor: **no board, no orders**, with every excluded name and
   reason printed.
6. **A re-run can no longer print an order.** It rendered with `book=True`,
   producing fresh share counts for a REVISED board under an "informational
   only" disclaimer. A printed order line IS the instruction; the disclaimer
   loses. Re-runs now render non-actionable.

### Also fixed
7. `session_rows(drop_date=...)` — research scripts no longer score the
   current, still-open session as a completed outcome.
8. Configured `data_sources.primary` now reaches the 9:46 path, with the source
   and any fallback printed on every board.
9. UTF-8/replacing output so the daily entry point cannot die mid-order on a
   Windows console.
10. README now opens with ONE canonical command and labels every other module
    LEGACY. Two documents naming different daily commands is how the wrong
    strategy gets run.

### Deliberately NOT done
The audit's Phases B-F (native point-in-time TSX data, executable bid/ask fills,
nested cost-aware model search) are **blocked on data we do not have**, and it
explicitly says not to substitute a weaker dataset and call it equivalent. We
have no TSX Level 1 subscription and no paid intraday feed; Yahoo caps 5-minute
bars at 60 days and zeroes TSX hourly volume. Every P1 criticism of the
historical claim — training-window mismatch, US-twin domain mismatch,
non-executable bar-close fills, per-leg objective, no outer-fold calibration,
multiple-testing across 15 rejected candidates, day/ticker dependence — is
**accepted as valid and unresolved**. Nothing here should be read as evidence of
an edge. 177 tests green.

## Day-26 (TSX holiday, no trading): two safety fixes and a 16th rejection

Market closed for the Civic Holiday. No board, no orders, nothing traded. Used
the day for the work a trading morning has no time for.

### The holiday check was broken — and the day-25 gate is what saved it
`is_trading_day(2026-08-03)` returned **True** on a day the TSX was shut. Cause:
it depends on the OPTIONAL `pandas_market_calendars`, and where that is not
installed the `except` branch returns True for **every weekday**. A safety
check must never be one `pip install` away from silently returning the unsafe
answer.

What actually protected us was the day-25 coverage gate, on its first real
test: `0/21 names passed data validation, below the 80%% floor -> NO BOARD, NO
ORDERS`. Fail-closed worked. But that made the holiday check a single point of
failure, so it is now backed by `dashboard.tsx_holidays()` — computed, not
tabulated (so it never expires), covering all ten TSX statutory closures with
weekend-observance shifts. **Verified against pandas_market_calendars across
1,045 weekdays of 2024-2027: zero mismatches.**

### Tomorrow's real hazard, found by watching the US lines
The TSX was shut but the US dual-listings traded. **Telus's US line (TU) closed
-12.58%%**, so T.TO gaps enormously at tomorrow's open. Also crude **-6.34%%**
(ENB -2.3%%, CVE -2.6%%, TRP -1.9%%), NTR -4.9%%, AEM -3.4%%, SHOP -3.2%%, while
financials rose (TD/BMO/CM ~+1%%) and the S&P gained +1.65%% — a sharply split
tape.

The live 60-day pool's largest |gap| is **6.85%%** and it contains **zero** rows
beyond 8%%. A -12.6%% gap has no neighbours at all — yet k-NN takes the 60
nearest regardless of distance, so it returns a confident-looking P for a setup
it has never observed. The `sparse` tag hints at this and gates nothing.

**ADOPTED: an extrapolation guard** (`r945.extrapolation_check`). A name whose
features fall outside the training pool's own observed range is REFUSED, with
the reason printed alongside peer-gate exclusions. Measured before shipping:
fires on **0.82%%** of rows (deep set; 1.75%% true set) and those rows move
**1.89x** further by the close — rare and violent, exactly where an
unsupported extrapolation does most damage. Parameter-free: the bound is the
pool's own range, so there is nothing to tune or overfit.

**HONEST SCOPE — this is not an accuracy claim.** It has not been shown to
raise the hit rate. It refuses to predict where the model has no basis, which
is a data-validity guarantee like the day-25 bar checks, not alpha. It is the
first fix that directly addresses the earnings/news blind spot this journal has
listed as unresolved since day-13, and it does so without pretending to have a
news feed.

### REJECTED (#16): "the short side is structurally broken"
The week's most tempting conclusion — shorts 3/9 with -1.111%% capture, and
20/44 (45%%) cumulative. Tested properly by comparing each side against **its
own naive base rate**, because if the tape simply drifts up then longs win and
shorts lose with no skill involved, and dropping shorts would be a beta bet
rather than an improvement.

| | deep set | true 5m set |
|---|---|---|
| long skill vs P(up) | +1.1pp | **-6.2pp** |
| short skill vs P(down) | -1.8pp | **+5.3pp** |
| short skill negative in | 2 of 4 quarters | 1 of 4 quarters |

**The two datasets say opposite things about which side is better.** Fails the
all-four-quarters bar, and the true-horizon data would have had us cut the
LONGS. The live 45%% short record is a bad run, not a structural defect —
acting on it would have been backwards. Rejections now 16 against 2 adoptions.

### Ready for tomorrow
Shadow mode (`--shadow`) is available if the decision is to stop risking
capital while the ledger accrues. The recommendation from day-26 stands: after
29 executed pair legs at 14/29, no interval excludes a coin flip.

## Day-27: execution is now an ASSET — and two more tempting patterns rejected

### The trade (user's own fills)
BNS.TO long 123.67 -> 122.68 (-0.80%%) and BMO.TO short 254.25 -> 253.05
(+0.47%%). **NET -$87.75** at printed size (205 / 96 shares). Long MISS, short
HIT. Exits were 122.68 / 253.05 — the exact closing prints, so the hold-to-3:55
contract was honoured in full.

### What went RIGHT — and it is the thing that was broken for weeks
**Both fills beat the printed decision price.** BNS bought 0.024%% BELOW the
9:45 print; BMO sold 0.035%% ABOVE it. Execution ADDED **+$14.79** versus
trading at the print (+$6.15 on BNS, +$8.64 on BMO).

That closes the loop opened on day-11 (chased CP short captured zero), day-19
(fill 0.21%% past the bound), day-13 (4x size) and day-25 (the bound was
anchored to the LIVE price and enforced nothing). Execution used to be the
single largest drain in this system. It is now a small positive contributor,
two sessions running. **This is the one part of the machine that has verifiably
improved.**

### What went WRONG — the relative call, and only that
Tide **+0.069%%** (flat, 57%% breadth). Financials fell **-0.710%%** as a sector.
Because BOTH legs were financials, the sector move cancelled almost exactly and
**100%% of the outcome was the internal ranking**:

| financial | 9:45->close | |
|---|---|---|
| MFC | +0.962%% | |
| SLF | +0.069%% | |
| BMO | **-0.437%%** | our SHORT |
| RY | -0.710%% | |
| BNS | **-0.825%%** | our LONG |
| CM | -1.114%% | |
| TD | -1.380%% | |

The bet was "BNS outperforms BMO"; BNS underperformed by **-0.388%%**. We were
long the weaker of the two. BNS ranked 18/21 in the universe, BMO 16/21 — the
engine picked two weak names and went long the weaker one. No market move, no
execution error, no data fault: the relative call was simply wrong.

### REJECTED (#17): "a same-sector pair is a worse structure"
Today's pair was intra-sector, which makes the book ONE relative-value call
rather than two hedged bets. Tested on 333 two-legged deep sessions:
same-sector NET -0.0109%%/day vs cross-sector -0.0122%%, legs hit 50%% vs 51%%,
worse in only **2 of 4** quarters. Statistically indistinguishable. The one
real difference favours it: **lower volatility (std 0.447 vs 0.605)**, exactly
as the cancelling sector move predicts. Today's structure was not the problem.

### REJECTED (#18): "drop the MID density tag"
The live density record has stopped being the pre-registered monotonic
dense>mid>sparse and become a U-shape: dense 54%%, sparse 53%%, **mid 39%%**
(capture -0.304%%). Both of today's losing-pair legs were MID. Day-7 flagged
non-monotonicity as the reason to tag rather than gate, and picking the worst
of three buckets post-hoc is a multiple comparison — so it went to the full bar.

**The deep set says the OPPOSITE.** Mid is the BEST bucket: 53.0%% hit /
+0.0695%% capture, against dense 48.5%% / -0.0098%% and sparse 52.0%% / -0.1842%%.
Mid was worse in only **1 of 4** quarters. Cutting mid would have cut the
strongest cohort in the larger sample.

### The pattern that keeps repeating — now three for three
This week every live pattern that looked worth acting on pointed the OPPOSITE
way in the larger sample:
1. "shorts are broken" (45%% live) -> true-horizon data says shorts +5.3pp and
   LONGS -6.2pp (#16);
2. "same-sector pairs are worse" -> indistinguishable, and lower variance (#17);
3. "mid tags are bad" (39%% live) -> mid is the best bucket on 809 legs (#18).
Rejections now **18** against 2 adoptions. At ~30 executed legs the live record
cannot distinguish cohorts; it can only generate plausible stories, and acting
on any of them this week would have made things worse.

## Day-28: a WINNING day, audited the same as a loss — and the metric that was missing

### The trade
PAIR **2/2**: CP.TO long +0.369%% HIT, RY.TO short +0.404%% HIT. **NET +$193.90**
at printed size. Board 6/7. First positive book session in five. Neither leg
went materially against (worst -0.27%% / +0.28%%) — right early, right all day.

### The decomposition that matters (wins get the same audit — day-4, day-10)
Tide **-0.352%%** (down day, breadth 43%%):

| leg | absolute capture | RELATIVE to tide | universe rank |
|---|---|---|---|
| CP.TO long | +0.369%% | **+0.721%%** | 5/21 |
| RY.TO short | +0.404%% | **+0.052%%** | 12/21 |

**The long supplied 93%% of the pair's gain; the short supplied 7%%.** RY reads as
a clean HIT in the ledger, but market-neutral it was a MEDIAN name that fell
because the whole tape fell — on a -0.35%% day almost any short "wins". CP was
the real pick: it beat a falling tide by +0.72%%.

This is the exact mirror of day-23, where AEM "MISSED" while being relatively
fine. **The `hit` column measures the TAPE as much as the SELECTION.**

### ENCODED: relative (tide-removed) capture
The pair is market-neutral by construction, so the tide cancels between the
legs and a leg's real contribution is its move RELATIVE to the universe. Until
today the ledger had no way to express that — it credited a short for a falling
tape and penalised a long for the same.

Reconstructing the tide afterwards needs **every** name's 9:45 print, and the
qualified picks alone are a SELECTED sample that would give a biased tide. So
publish time now persists the 9:45 print for all evaluated names
(`universe_prints.csv`, publish-once), and the report prints relative capture
beside the absolute figures. Backfilled 252 prints across the 12 sessions still
inside Yahoo's 5-minute window.

**The first honest read of selection skill:**
```
  PAIR legs        17/33 (52%)   avg move captured -0.14%
  book-weighted    -0.315%/session over 5 sessions (1/5 positive)
  relative capture -0.129%/leg vs the tide over 23 legs (11/23 beat it)
```
With the tape removed the picks beat the universe **11 of 23 times (48%%)** with
slightly negative capture. That is the cleanest statement yet: the selection
layer has not demonstrated skill, and the absolute hit rate was partly
measuring the market all along.

### What today does NOT license
The all-SPARSE short board flagged as thin evidence this morning went **5/6**,
and in relative terms averaged +0.42%%. That contradicts my own morning caution
and reinforces day-17's rejection of "drop sparse legs" — it stays un-gated.
One good day is not evidence, in either direction: no rule was changed.

### The extrapolation guard's first live firing
SHOP.TO excluded on a **+20.83%%** gap (pool range [-7.28, +6.85]); verified
genuine — 173.41 close to a 209.08 open. It then moved -1.358%% post-gap. The
guard's job was to refuse a prediction it had no basis for, NOT to call the
direction, so this is a neutral outcome and must not be scored as a save.
Notable because day-27 walked back the anecdote that motivated the guard (the
"-12.58%% Telus" figure was a misread meta field); the measured justification —
fires on 0.82%% of rows, those rows move 1.89x further — was always the real
one, and today is the first live confirmation that the mechanism exists.

## Day-29: both legs missed on a FLAT tape — a clean selection failure, and a 19th rejection

### The trade
PAIR **0/2**: RY.TO long -0.148%%, ABX.TO short -0.728%%. **NET -$175.22**,
book-weighted capture -0.351%%. Board **2/9**.

### No tape excuse — this one is entirely the picks
Tide **-0.070%%**, breadth 48%%. Dead flat. Relative decomposition:

| leg | absolute | RELATIVE | rank |
|---|---|---|---|
| RY.TO long | -0.148%% | -0.078%% | 14/21 |
| ABX.TO short | +0.728%% | **-0.798%%** | **6/21** |

We shorted the **6th strongest name in the universe** on a flat tape. And the
whole board failed the same way: **board relative capture -0.289%%, only 2 of 9
picks beat the tide** — identical to the 2/9 absolute hit rate, because with a
flat tide absolute and relative coincide. This was not a market day that ran
over good picks; the picks were bad.

### REJECTED (#19): "do not oppose your own sector's opening move"
ABX (gold) closed +0.73%% while its ONLY peer AEM closed +1.47%% — the gold
sector rallied and we were short a member. The sector's first-15-minute move IS
known at 9:46, and this is a DIFFERENT variable from the day-20 rejection,
which tested the NAME's own momentum.

Tested on 754 deep legs with the all-four-quarters bar:
- opposing legs **52.8%% hit / +0.0360%% capture**; with-sector legs 47.3%% /
  -0.0123%% — **the opposite direction to the hypothesis**;
- worse in only **2 of 4** quarters;
- the **PLACEBO grouping reproduces the same 2/4 pattern**, so even the quarter
  split is not group-specific.
Opposing your sector is, if anything, mildly better. Today's ABX loss was not
an identifiable pitfall. Rejections now **19** against 2 adoptions.

### The number that now matters, and it is not the hit rate
With the day-28 relative metric accruing:

```
  PAIR absolute    17/35 (49%)   95% CI 33-64%
  relative capture -0.153%/leg over 25 legs   11/25 (44%) beat the tide
                   95% CI 27-63%
```

**The two disagree informatively.** The absolute pair record reads as a coin
flip; measured against the universe the picks are *slightly below* the median.
Whatever the absolute number flatters comes from the tape, not the selection.
Neither interval excludes 50%% at these sample sizes — but the direction of the
gap is the honest read, and it points the same way as the deep validation:
**the selection layer has not demonstrated skill.**

### The density tags reshuffled AGAIN — which is itself the finding
Live cohorts today: sparse 36/66 (55%%, +0.21%% capture), dense 32/62 (52%%),
mid 26/65 (40%%). A week ago dense led and sparse trailed; day-28 rejected
cutting mid because the deep set called mid the BEST bucket. Three orderings in
ten sessions. The tag ranking is noise at this n, and every attempt to gate on
it (#16 shorts, #18 mid) has pointed the wrong way. Do not gate on the tags.

### Day-29 addendum: "why no adjustment?" — the last untested lever, tested

Challenged on making no adjustment after an 0/2 day. Two honest answers.

**1. Magnitude.** RY -0.148%% is essentially flat against a printed normal
adverse swing of -0.7%% median / -1.3%% worse-quartile; ABX -0.728%% sits inside
the +1.2%% worse-quartile for a short. Book -0.351%% of capacity, disaster lines
(2.5%%) never approached. This was an ORDINARY losing session — the run's worst
is -1.310%% — and loss size is the evidence about whether something BROKE.
Nothing broke.

**2. Adjustments HAVE been made — just not to the selector.** Equal-risk
weighting (worth +$170 on day-23, +$187 on day-25, -$23 on day-22) and the
extrapolation guard are the two adoptions; execution went from the largest
drain in the system to a small positive (+$14.79 on day-27). What is refused is
re-tuning the SELECTION on one session — and three times in this window the
live pattern pointed the OPPOSITE way to the larger sample (#16 shorts, #18
mid, #19 sector-momentum). Acting on any would have made it worse.

**REJECTED (#20) — and this is the decisive one.** The single structural lever
never varied: the system trades EVERY session, publishing whenever two names
clear 0.55. The header claimed "selectivity IS the edge" — a claim that had
never been measured, because the bar had never been moved.

| bar | sessions | legs | hit | capture | pair NET/day |
|---|---|---|---|---|---|
| 0.55 | 476 | 809 | 50.1%% | -0.0047%% | +0.0004%% |
| 0.58 | 452 | 611 | 47.6%% | -0.0024%% | +0.0080%% |
| 0.60 | 376 | 437 | 48.7%% | -0.0196%% | -0.0111%% |
| 0.62 | 245 | 258 | 51.2%% | -0.0294%% | -0.0402%% |
| 0.65 | 91 | 91 | 52.7%% | -0.0762%% | -0.0762%% |

Capture **degrades monotonically** as the bar rises, and NO bar gives positive
capture in all four quarters. Hit rate creeps up (50.1 -> 52.7%%) while capture
falls: stricter picks are right slightly more often on SMALLER moves — worse
after costs, not better. **There is no bar at which this machine earns.**
The refuted sentence has been deleted from the r945 header.

### What this means
Twenty adjustments have now been tested against two adoptions, and the
adjustment space is close to exhausted: selector, side, sector, density tag,
pairing structure, target variable, universe, run time, horizon, and now the
qualification bar. The one metric that isolates skill from tape — relative
capture — reads **-0.153%%/leg, 11/25 (44%%) beating the universe**.

The evidence-supported adjustment is no longer a parameter. It is to STOP
RISKING CAPITAL on the selection layer while the ledger accrues (`--shadow`,
shipped day-26). Continuing to trade live is a defensible choice about the
owner's own capital; it is not a choice this evidence supports.

## Day-30: the pair, the week — and a narrative I nearly shipped

### Friday's pair
CP.TO long **+0.893%% HIT**, CNQ.TO short **-1.212%% MISS**. NET **-$34.82** —
almost flat, because the hedge did its job: a 1.2%% short miss was nearly
cancelled by a 0.89%% long win. Board 1/3 (the narrowest board of the run).

Tide **-0.020%%** (flat). Relative: CP **+0.913%%, rank 6/21** — a genuinely good
long. CNQ **-1.232%%, rank 4/21** — we shorted the 4th strongest name.

### The narrative I nearly shipped — and the data that killed it
Four consecutive short legs landed near the TOP of the universe:
BCE 2/21 (d-24), AC 2/21 (d-25), ABX 6/21 (d-29), CNQ 4/21 (d-30). Random
shorts would average rank ~11/21. That is a compelling story, it was forming in
my own write-ups, and it points at an obvious "fix" to the short side.

**It is false.** Measured over every pair leg with the tide removed:

| side | n | mean relative | beat the tide | 95%% CI |
|---|---|---|---|---|
| LONG | 14 | **-0.183%%** | 5/14 (36%%) | 16-61%% |
| SHORT | 13 | **-0.122%%** | 7/13 (54%%) | 29-77%% |

**Shorts are the BETTER side in relative terms; the LONGS are the weaker one.**
The four bad shorts were a salient recent streak, not the pattern — exactly the
recency trap this journal has documented nineteen times, and I was one step
from proposing a short-side gate on the strength of it.

Worth noting it agrees with rejection #16, where the true-horizon data said
longs -6.2pp and shorts +5.3pp. Two independent measurements now point at the
LONG side as the weaker one. Still not actionable: the CIs overlap almost
completely (16-61%% vs 29-77%%) and the deep set said the opposite (long +1.1pp,
short -1.8pp). Recorded, not acted on.

### The week
| date | long | short | book |
|---|---|---|---|
| 08-04 | BNS -0.825%% MISS | BMO +0.437%% HIT | -$102.45 |
| 08-05 | CP +0.369%% HIT | RY +0.404%% HIT | +$193.80 |
| 08-06 | RY -0.148%% MISS | ABX -0.728%% MISS | -$175.18 |
| 08-07 | CP +0.893%% HIT | CNQ -1.212%% MISS | -$34.80 |

**WEEK -$118.64**, pair legs 4/8, all picks 11/26. Against week 1's -$883, the
two-week total is **-$1,001**. The improvement is almost entirely variance
reduction, not better prediction: no leg came near a disaster line, the worst
book day was -0.350%% (vs -1.310%% in week 1), and the equal-risk weighting plus
the hedge repeatedly turned bad legs into small days.

### Standing position after 37 executed legs
```
  PAIR absolute    18/37 (49%)
  book-weighted    -0.285%/session over 7 sessions (1/7 positive)
  relative capture -0.154%/leg over 27 legs, 12/27 (44%) beat the tide
```
Twenty adjustments tested, two adopted. Execution is fixed and is now a small
positive. The selection layer still has not demonstrated skill, and the metric
that isolates it from the tape remains negative.

## Day-31: "why only one long and one short?" — never measured, now measured

### Why the CNQ short failed (2026-08-07)
Setup at 9:46: gap -1.21%%, first-15m -0.49%% — a falling name shorted for
CONTINUATION. It reversed **within 15 minutes of the print** (+0.19%% by 10:00)
and never came back, closing +1.21%%.

Mechanism: **crude rallied +1.15%% that day, and we shorted a producer into it.**
The producers followed crude (CNQ +1.21%%, CVE +1.36%%) while the pipelines did
not (ENB +0.04%%, TRP -0.11%%, SU -0.32%%) — so the energy sector median was a
flat +0.04%% and the split was producer-vs-pipeline, not sector-wide. Crude's
intraday direction was not knowable at 9:46, and the closest available proxy —
opposing your own sector's opening move — was tested and REJECTED as #19.

### ADOPTED (#3 ever): TWO legs per side, not one
The 1+1 structure was chosen on day-9 by workflow preference and **never
measured**. Tested with book CAPACITY HELD CONSTANT — more legs split the same
money, they do not add exposure — equal-risk within each side, half the book per
side:

| legs/side | NET/day | std | mean/std | worst |
|---|---|---|---|---|
| 1 (shipped) | +0.0004%% | 0.625 | +0.0007 | -2.22%% |
| **2** | **+0.0115%%** | **0.517** | **+0.0222** | -2.18%% |
| 3 | +0.0042%% | 0.499 | +0.0083 | -2.19%% |
| ALL | +0.0023%% | 0.509 | +0.0046 | -2.18%% |

Judged on the criterion that estimates fast — variance, exactly as the day-22
equal-risk adoption was — **2 legs/side lowers NET std in ALL FOUR quarters**
(0.573->0.442, 0.660->0.638, 0.563->0.495, 0.688->0.476), -17.1%% overall, with
the mean improving and the worst day slightly better. True-set: -24.4%%, 3/4.
Identical evidence profile to the one rule that has demonstrably helped.

**HONEST SCOPE — this is not "better opportunities".** It is the diversification
identity: spreading the same ~coin-flip across more names cuts idiosyncratic
variance. Nothing here says the picks improved; mean/std improves because the
denominator falls. 3 legs/side cuts variance slightly more but with a lower
mean, so 2 is the adoption.

### The honest counter-example, stated up front
Replayed on the very day that prompted the question, the new rule would have
been **WORSE**: Friday's second short (CVE -1.364%%) also missed, taking the book
from -$79.75 to -$96.31. That is expected. The rule was adopted on variance
across 479 sessions, not on any single session, and a day where the extra leg
also loses is exactly what a variance argument predicts will sometimes happen.

### Implementation notes
`pair.legs_per_side: 2`. The primary leg per side is unchanged (densest); extras
are the next-densest. Sizing is now SIDE-AWARE and the side must be **explicit**
— an earlier draft inferred it from `p_up`, which silently mis-sized any caller
that did not carry one, so a book with no side information now falls back to the
pre-day-31 flat split rather than guessing. The day-18 contract still holds: a
missing side leaves its half in cash. 200 tests green.

## Day-32: SLN, event swing trades, and longer holds — measured, NO EDGE FOUND

### What happened to SLN
**Silence Therapeutics (SLN, NasdaqGM)** — not a TSX name and not in the pair
universe. Friday close 11.95 -> Monday open **16.02, a +34.1%% gap**, on
**7.85M shares versus ~400k typical (~20x)**. Session high 17.00, low 15.245.
That volume-and-gap signature is a binary corporate/clinical event.

Its own history offers nothing to trade on: **3 gaps >= 15%% in 1,255 sessions
(0.2%% of days)**, and only TWO with five sessions of follow-through
(+8.3%%, -3.2%%). A single name's event history cannot support a strategy — which
is why this went to a cross-sectional study.

### The study (validate_events*.py, committed and re-runnable)
10 years of DAILY bars, 166 liquid US names, **400,703 ticker-days**. Entry at
the CLOSE of the gap day (observable, executable); horizons 1/3/5/10 sessions;
returns reported RAW and MARKET-RELATIVE, because day-18 already established
that multi-day "returns" from this project's engine were pure drift.

Exactly one bucket passed the pre-registered five-block consistency test:
**gap -5%%..-10%%, market-relative, +0.60%% (5d) / +0.98%% (10d), consistent in all
five two-year blocks, n=1,791.** Everything else flipped sign across blocks.

### Three tests dissolved it
1. **TAIL-CARRIED.** mean rel-10d +0.980%% but **MEDIAN +0.010%%**, win rate
   **49.9%%**. The typical event does nothing; a few huge rebounds carry the mean.
2. **BETA, NOT SELECTION.** The bounce exists only on market-DOWN days
   (+1.105%%) and is **NEGATIVE on market-up days (-0.624%%)**. A high-beta name
   that gapped down mechanically out-bounces the cross-sectional median when the
   tape recovers. Not a stock-specific edge.
3. **NOT SIZE-ROBUST.** Flips in 3 of 4 liquidity quartiles; the smallest
   quartile is outright **negative (-0.965%%)**.

**VERDICT: no tradeable gap-event edge found.** Rejection #21.

### The SLN-sized trade is unstudiable with this data
|gap| >= 20%% occurs **141 times in 10 years across 166 names**. At that
frequency no bucket reaches the sample size needed to distinguish a real effect
from noise — which is the same answer SLN's own n=2 history gave.

### SURVIVORSHIP BIAS — the caveat that matters most
The universe is TODAY's ticker list, so companies that gapped down and delisted
are ABSENT. That biases gap-DOWN results optimistically — the exact direction of
the one apparent finding. Removing it requires a point-in-time universe
including dead tickers, which is a paid data product. Any future revisit of this
question should start there, not with another free-data study.

### On "higher accuracy and returns with longer holds"
Two independent measurements now say no:
- **day-18** (this engine's own legs): 0d +0.094%%/54.4%%/std 1.09%% vs 5d
  +0.177%%/51.3%%/std **3.95%%**, worst leg -3.9%% -> **-17.6%%**, and the multi-day
  gain decomposed as market beta (longs +0.62%% vs shorts -0.39%% at 5d);
- **day-32** (event-driven, a genuinely different hypothesis on 400k
  ticker-days): the single surviving candidate is tail-carried beta.

Longer holds raise VARIANCE far faster than return in everything measured here.
That does not prove event trading cannot work — it says it cannot be validated
with free, survivorship-biased data, and this project's standing rule is not to
trade what it cannot validate.

## Day-33: the best-selected day of the run — and the ROI lever, measured and rejected

### The book (first live 2-legs-per-side board, and it was one-sided)
No qualified long; two shorts taken. **MFC.TO +0.790%% HIT, CP.TO +1.506%% HIT.
NET +$281.44** on ~$24.9k deployed — HALF the book, with the long side in cash.
Board 3/5.

**These were genuinely good picks, not tape.** The tide was **+0.117%%** — slightly
UP — and the shorts still won:

| leg | absolute | RELATIVE | universe rank |
|---|---|---|---|
| MFC short | +0.790%% | **+0.907%%** | **19/21** |
| CP short | +1.506%% | **+1.622%%** | **20/21** |

We shorted the 19th and 20th weakest names out of 21, against a rising tide.
That is the clearest instance of real selection skill in the run, and it is the
mirror of day-28's win (where the short "hit" while contributing 7%%).

### The day-31 change earned its keep — and gave some back Friday
Under the old one-leg rule only MFC would have been taken (403 sh, half book):
**+$197.47**. The two-leg book made **+$281.44** — the change was worth
**+$83.97 today**, against **-$16.56 on Friday**. Helped once, hurt once, exactly
as a variance argument predicts. Neither day is evidence; the 479-session
four-quarter variance result is.

### REJECTED (#22): "deploy more capital on one-sided days" — the ROI lever
Today's obvious ROI complaint: a +0.563%% book capture earned +$281 instead of
+$563 because half the capital sat idle. So: should one-sided days be sized up?

**First, the part that is arithmetic and not a discovery.** Doubling every
position doubles mean AND std; mean/std is unchanged. Scaling is a RISK-BUDGET
decision, never an edge. The only real question is whether one-sided sessions
are systematically better.

They look it — until the tide is removed:

| cohort | ABSOLUTE | blocks | RELATIVE (tide removed) | blocks |
|---|---|---|---|---|
| two-sided | -0.0065%% | FLIP | -0.0065%% | FLIP |
| **one-sided** | **+0.0267%%** | **CONSISTENT 4/4** | **-0.0076%%** | **FLIP** |

**The tide supplies 128%% of the one-sided gain** — the selection actually
detracts slightly. A one-sided book is NAKED directional, so it earns when the
tape happens to move its way; sizing it up would lever a beta bet, not harvest
an edge. The half-book rule (day-18) stands.

### The honest answer to "bigger ROI"
There are exactly two sources: a better edge, or more risk. Twenty-two tested
adjustments say the edge is not available in this data — and the one lever that
looked like free ROI is beta. More risk is always available and needs no
research; it is a decision about capital, and this project will not dress it up
as a discovery.

What HAS moved is the measurement: relative capture improved from -0.154%% to
**-0.056%%/leg (14/29 beat the tide)** and book-weighted from -0.285%% to
**-0.179%%/session (2/8 positive)**. Still negative, still no edge demonstrated —
but the metric that isolates skill is the one to watch, and today it moved for
the right reason.

## Day-34: a bad day the new structure made materially less bad

### The book (first full 2+2)
**1 of 4 legs hit. NET -$205.74**, book-weighted capture -0.411%%.

| leg | absolute | RELATIVE | rank |
|---|---|---|---|
| RY.TO long | -1.067%% MISS | -0.520%% | 17/21 |
| BMO.TO long | -1.264%% MISS | -0.718%% | 19/21 |
| CP.TO short | -0.416%% MISS | -0.962%% | 6/21 |
| ABX.TO short | **+1.552%% HIT** | **+1.006%%** | 20/21 |

Tide **-0.546%%** (breadth 33%%) and **financials -1.067%%** as a sector. Some of
this is tape — but only some: **three of four legs were also bad RELATIVE**, so
this was a genuine selection failure with a down tape on top, not one or the
other.

### The day-31 change was worth **+$163.58 today**
Under the old one-leg rule the book would have been RY long 84 sh + CP short
196 sh = **-$369.32**. The four-leg book lost **-$205.74**. The two losing legs
were half-sized and ABX — the extra short, which would never have been taken —
was the day's best leg at +1.552%%.

Running tally for the change: **-$16.56** (Fri), **+$83.97** (Mon), **+$163.58**
(today) = **+$231 over three sessions**. Still not evidence — three days never
are — but it is behaving as the 479-session variance result predicted: it makes
good days slightly better and bad days materially less bad.

### REJECTED (#23): "diversify the two legs on a side across sectors"
Today's obvious complaint: BOTH long legs were banks (RY + BMO), so when
financials fell they lost together. The extra leg is chosen by DENSITY alone
with no diversification constraint — a side can be two names from one sector,
and this happens on **43%% of sessions**.

Tested with the same bar as day-22/day-31:

| rule | NET/day | std | worst | P(>0) |
|---|---|---|---|---|
| density only (shipped) | **+0.0115%%** | 0.517 | -2.18%% | 51.9%% |
| + diversify across sectors | -0.0051%% | 0.517 | -2.21%% | 48.3%% |

**std is unchanged (0.517 -> 0.517), the mean gets WORSE, the worst day gets
slightly worse, and only 2 of 4 quarters improve.** Forcing sector spread buys
nothing. The reason is visible once stated: the book is long AND short, so a
same-sector long pair is still hedged by the short side — and the -17.1%%
variance reduction measured on day-31 already INCLUDED same-sector sides in 43%%
of its sessions. Today's intuition was reasonable and is measurably wrong.

### On "better and bigger ROI" — the same answer, now with a number
Twenty-three tested adjustments, three adopted, and every adopted one is a
VARIANCE result rather than a prediction improvement. That is not evasion, it is
what the data supports — and it is worth noting what it has actually bought:
today the book lost **-0.41%%** of capacity where the pre-day-22/31 structure
would have lost **-0.74%%**. The prediction layer has not improved; the damage
per unit of being wrong has roughly halved.

Standing: pair 21/43 (49%%), book-weighted -0.205%%/session (2/9 positive),
relative capture -0.085%%/leg with 15/33 beating the tide.

## Day-35: a green day — and the metric that says it was less green than it looks

First session of the run where **all four legs came in DENSE**, and the first
where the intraday path never went negative (+0.11%% by mid-morning, +0.21%% by
early afternoon, close in between).

| leg | side | capture | tide-relative | rank | verdict |
|---|---|---|---|---|---|
| MFC.TO | LONG | **-0.261%%** | -0.891%% | 18/21 | MISS |
| TD.TO | LONG | **+0.815%%** | +0.186%% | 8/21 | HIT |
| CNR.TO | SHORT | **+0.040%%** | +0.669%% | 15/21 | hit (scratch) |
| CNQ.TO | SHORT | **+0.015%%** | +0.644%% | 13/21 | hit (scratch) |

**NET +$87.23**, book-weighted capture **+0.175%%**. Tide **+0.629%%** — a
broadly rising tape, which makes the short side the honest story of the day:
both shorts finished essentially flat while the market rose two-thirds of a
percent, so **both beat the tide by ~0.65%%** even though neither made money.
That is exactly what a short leg is supposed to do on a green day, and it is
invisible in the raw hit column.

### The learning, and it is not a flattering one
Two of the three "hits" were **+0.040%%** and **+0.015%%**. Those are not
outcomes, they are noise that happened to land on the correct side of zero. The
`hit` column is a pure sign test, so a leg finishing +0.015%% counts exactly as
much as one finishing +1.5%%.

Measured across all 47 pair legs: **11%% finish inside ±0.10%%, and 4 of those 5
scored as HITS.** The headline hit rate is therefore inflated by ~3pp.

Implemented `decisive_line()` in `ledger.py` (+2 tests, 203 passing). The report
now prints both numbers side by side:

```
PAIR legs           : n=47   hit 24/47 (51%%)
decisive legs       : 20/42 (48%%) with |capture| >= 0.10%%  (5 scratches excluded)
```

This is a deliberately **less** favourable metric than the one it sits beside.
It was added on a winning day precisely so it can't be read as excuse-making
later, and it is the number to watch from here: a sign test on a distribution
centred near zero will always flatter itself.

### The excluded name that moved: AC.TO
The extrapolation guard refused AC.TO on `r0 = +5.67%%` — outside the training
pool's observed feature range — and it then moved **+2.580%%** from its 9:45
print. This is not an argument against the guard. The guard does not claim AC
would have fallen; it says the k-NN has **no neighbours** at that r0 and cannot
assign a direction, so the honest output is abstention. Day-25 measured the
alternative: rows outside the range move **1.89x further** than in-range rows,
i.e. the guard is refusing exactly the rows where a wrong call is most
expensive. Taking the trade would have been luck, not skill.

### No adjustment adopted today
Nothing in this session pointed at a testable rule change. The one miss (MFC)
was idiosyncratic — worst-decile relative on a day its sector twin TD was
mid-pack — which is the same idiosyncratic-residual pattern established on
day-29, not a new pattern. Twenty-three rejections, three adoptions, unchanged.

Standing: pair 24/47 (51%%), **decisive 20/42 (48%%)**, book-weighted
-0.167%%/session (3/10 positive), relative capture -0.057%%/leg with 18/37
beating the tide.

## Day-36: "is there a better exit than 15:59?" — the biggest untested parameter

Fair question, and an embarrassing one: **the exit time was never chosen.** It
was inherited from the first script and then baked into the ledger, every
backtest, the twins study and the adoption bar. Every number this system has
ever produced assumes a 9:45 -> close hold. Unlike most levers, changing it is
free — no new data, no new model, just a different clock.

Built `validate_exit.py`. Four independent samples, pre-registered bar written
before looking (75 candidate exits guarantees a winner by chance, so the bar is
built to make a lucky spike fail): beat the close on mean capture, in **all
four quarters**, with **+/-15 minutes also beating it** (no isolated spikes), by
**more than one standard error**, and agreeing on an independent sample.

### VERDICT — REJECTED (#24). No exit beats the close.

The 2-year twins are decisive: **944 pair legs over 288 test sessions**, and
the whole capture curve is flat inside +/-0.02%%.

| exit | 11:30 | 12:30 | 13:30 | 14:30 | 15:30 | close |
|---|---|---|---|---|---|---|
| mean | -0.020%% | -0.008%% | **+0.007%%** | +0.004%% | -0.004%% | -0.004%% |
| std | 0.51 | 0.70 | 0.78 | 0.86 | 0.91 | 0.96 |

Best-vs-close is **+0.011%% against a 1-se bar of 0.025%%**; fails smoothness,
fails the se bar, 3/4 quarters. Same story on the native 5m walk-forward (124
pair legs): best raw exit 15:45, **+0.007%%** better, 2/4 quarters.

### WHY there is nothing to find — the mechanism, and it is sample-independent
Correlation between the move so far and the rest of the day, across all 1,260
ticker-sessions: **+0.07 at 10:00, -0.00 at 11:30, -0.04 at 13:00, -0.02 at
15:45.** The path from 9:45 is essentially a martingale. It does not
systematically hand back what it gave, **so there is no peak to exit at.** An
exit rule can only help if the tape reverts; this one doesn't.

### The mirage I nearly shipped
On **three of four samples** the best raw exit was 09:50 or 10:00, and on the 47
real ledger legs a 10:00 exit "would have" returned **+0.056%%** against the
close's **-0.086%%**. That is a 0.14%% swing on the live record — exactly the
kind of number that gets adopted. It is not real:

1. it is the best of 75 candidates on 47 legs;
2. it does not reproduce on the same rule with 124 legs, nor with 944;
3. **differencing the curve into windows kills it.** The live legs' entire
   "early-exit edge" is ONE window — 10:00->10:30, **-0.202%%, t=-3.59.** One bad
   half-hour in a small sample, not a decay curve. On the 124-leg walk-forward
   no window carries the edge at all: every t-stat lands in **[-0.83, +1.35]**.
   Capture accrues roughly uniformly through the day.

A 0.03-0.06%% "edge" is also under a realistic round-trip cost, so even taking
the mirage at face value it does not pay for itself.

### What IS true, and is not actionable yet
**Variance keeps growing after the mean stops.** On the twins std runs 0.51 ->
0.96 from 11:30 to the close while the mean sits at zero; on the 5m pair sample
the mean is flat from 11:20 (+0.055 -> +0.062) while std goes 0.85 -> 1.32. If
that flatness is real, the last 4.5 hours buy **~55%% more risk for nothing** —
which would be the fourth variance result in a row, and this system's only
adoptions have all been variance results.

It fails the bar (2/4 quarters; the gain is a fraction of one se) and **124 legs
cannot separate +0.055 from +0.062.** So it is logged, not shipped.
`validate_exit.py` re-runs from scratch with no key and no cached artifact, so
this gets re-asked as the ledger grows rather than re-mined from memory.

Twenty-four rejections, three adoptions.

## Day-37: the holistic sweep — 800 configurations, and the honest verdict

Today all four legs missed. Both longs fell AND both shorts rose, so the tide
cannot explain it: **a pure selection failure in both directions.**

| leg | side | capture |
|---|---|---|
| RY.TO | LONG | -0.063%% |
| ENB.TO | LONG | -0.557%% |
| NTR.TO | SHORT | -0.374%% |
| T.TO | SHORT | -0.824%% |

Book **-0.423%%** of capacity. The right response was not another one-lever
test, so this is the sweep: **every knob at once, plus the null that says
whether any winner is real.**

### THE LIVE RECORD, stated plainly
* **PAIR legs 24/51 (47.1%%)** — two-sided binomial **p = 0.78**. That is not
  "underperforming", it is *indistinguishable from a coin flip.*
* mean capture **-0.113%%/leg**, t = **-0.80**. All 233 picks: 48.9%%, t = -0.56.
* Book: **23 sessions, mean -0.097%%/session, 9/23 positive, cumulative
  -2.24%% of capacity.**
* decisive legs (excluding scratches) **20/45 (44%%)**; relative capture
  **-0.098%%/leg** vs the tide.

### THE SWEEP — 800 configurations on 290 sessions
Legs per side 1-4 x long-only/short-only/both x bar 0.50-0.65 x four selectors
x every weekday, all re-slicing ONE walk-forward pass so no config gets a
different model.

**The shipped config — 2 legs / both sides / 0.55 / densest / all days — scores
mean +0.0004%%/session, t +0.01, 48%% positive: RANK 449 OF 800.** It is not
unlucky. It is average, and average here is zero.

### The one thing that nearly survived — and why it didn't
Best config: **long-only / bar 0.60 / Thursday / 1 leg, +0.512%%/session,
t +2.09**, and against 100 placebo sweeps (same names, days and sizes, sides
assigned at random) **p = 0.040**. First result in 25 tests to clear a placebo
band. It dies on autopsy, four ways:

1. **Quarters: +0.573 / -0.564 / +0.538 / +1.067.** Q2 strongly negative —
   fails the all-four-quarters bar outright.
2. **n = 37 Thursdays**, 6-11 per quarter.
3. **The selector is BACKWARDS.** random **+0.512** beats densest **+0.361**,
   max_p +0.371, sparsest +0.333. If the k-NN ranking were doing the work,
   densest would lead. Random leading is the signature of *no skill* — whatever
   this is, the model's ordering is not producing it.
4. It is not a Thursday tape effect either: buying the **whole universe** on
   Thursdays pays **+0.009%%/session**.

The null's own **median** best config was **+0.368%%/session**. A grid this size
manufactures half-percent "winners" from noise routinely. That is what the null
is for, and why a bare p-value would have been a trap.

### The structural fact that settles it: THIS CANNOT BE MEASURED IN TIME
Detecting a true **55%% hit rate at 80%% power needs ~781 legs.** The live
ledger has **51**. At 4 legs/session that is **roughly four years of trading**
before the record could distinguish a real edge from a coin flip — while paying
spread, commission and single-name risk the whole way.

### VERDICT — REJECTED (#25), and a recommendation, not another lever
Twenty-five tested changes, three adopted, and all three adopted ones were
**variance** results — none ever improved accuracy. The deep validation said
the selection layer is inert (densest 50.1%% vs random 50.2%%, 944 legs). The
exit time is flat. The entry time was refuted. Overnight doubles volatility.
Multi-day found no edge. Now the joint sweep finds nothing either.

**The honest conclusion is that this signal — pooled k-NN on r0/gap/vp over 21
TSX large caps — has no edge, and the surrounding strategy space does not
contain one.** The recommendation is to stop risking capital on it and run
`r945.py --shadow`, which prints the same book with no share counts, so the
ledger keeps accruing legs at zero cost. If the record ever separates from a
coin flip, that is when it earns money back.

## Day-38: one pick a day? no-trade days? 3-day and 1-week holds? — all measured

Three fair questions day-37's sweep did NOT answer: it always took a two-sided
book, always traded every session, always held to that day's close.
`validate_shape.py` sweeps 60 configurations — 4 shapes x 3 hold lengths x 5
abstention rules — with the same placebo calibration.

**Result: p = 0.920. The best real config (+0.1249%%/day of risk) is BELOW the
placebo MEDIAN (+0.1643%%).** A randomly-sided book routinely beats the best
real one on this grid. The shipped config ranks 42 of 60.

### 1. ONE PICK PER DAY — rejected (#26)
`one-best` at 1 day returns **-0.0196%%/trade, worse than the two-sided pair
(+0.0004%%)**. And the decisive detail: the single pick is **83%% LONG (239 long
/ 49 short)**. "One pick" is not a concentrated bet on the model's best idea —
it is a directional bet on the market wearing a pick's clothing. Concentration
also **triples volatility** (std 1.149 vs 0.451) and takes the worst trade from
-1.71%% to **-4.32%%**.

### 2. NO-TRADE DAYS — rejected (#27)
Five rules: minimum conviction, top pick must be dense, conviction margin over
the runner-up, deep board, none. **No rule helps consistently** — `top-dense`
improves one-best and hurts pair1/pair2/one-dense, and every sign flips across
shapes. Sign-flipping across neighbouring configurations is the signature of
noise, not a filter.

### 3. THREE-DAY AND ONE-WEEK HOLDS — rejected (#28), and this is the one that
### looks best until it's decomposed

| | per trade |
|---|---|
| one-best / **5 days** | **+0.5393%%** |
| whole universe over 5 days | **+0.5298%%** |
| one-best / **3 days** | +0.2507%% |
| whole universe over 3 days | +0.2805%% |

**The entire multi-day gain is market drift** collected by an 83%%-long book
over a rising two-year sample. At 3 days it is BELOW the market. Selection
contributes ~0.01%%. Hedge it properly and the drift vanishes: pair2/5d gives
+0.1123%%/trade, t +0.94.

The risk side is worse than the return side is good:

| config | std | worst trade |
|---|---|---|
| pair2 / 1 day | 0.451 | -1.71%% |
| one-best / 5 days | **4.584** | **-19.84%%** |

Ten times the volatility and a worst trade that would erase a year of the
printed edge — in exchange for the market return you could get from an index
fund without the single-name risk.

This is now the **third independent** measurement saying the same thing, after
day-24 (one night doubles volatility, 2.3x worse tail) and day-32 (event
swings: no edge): **this engine's signal does not survive past one session, and
what looks like a multi-day edge is beta.**

Twenty-eight rejections, three adoptions.

## Day-39: is 9:46 the right time to run? — re-raced on rebuildable data

Day-21 already raced six decision times and kept 9:45. Re-running it was still
worth doing for two reasons: **its dataset can no longer be fetched** (a 1-year
5m twins set; Yahoo caps 5m at 60 days), so the verdict rested on data nobody
can regenerate — and it **predates the placebo calibration**, which day-37
showed this grid badly needs.

Entry time is not the same question as day-36's exit time: moving the entry
moves **both** ends. A later entry gives a longer momentum window in `r0` and
more volume to judge `vp` against, but leaves less session to capture. Those
push opposite ways, so it has to be measured.

| TSX 5m (35 sessions) | mean | t | | twins 1h (288 sessions, 2yr) | mean | t |
|---|---|---|---|---|---|---|
| 09:35 | -0.0285%% | -0.25 | | **10:30\*** | -0.0212%% | -0.82 |
| 09:40 | +0.0802%% | +1.00 | | 11:30 | -0.0316%% | -1.39 |
| **09:45\*** | +0.0730%% | +0.56 | | 12:30 | -0.0064%% | -0.35 |
| 09:50 | **+0.1034%%** | +1.00 | | 13:30 | -0.0082%% | -0.52 |
| 10:00 | +0.0220%% | +0.23 | | | | |
| 10:15 | -0.0754%% | -0.87 | | | | |
| 10:30 | +0.0510%% | +0.66 | | | | |
| 11:00 | +0.0690%% | +1.04 | | | | |

**TSX: p = 0.640. Twins: p = 0.940. REJECTED (#29).** On the TSX sample the
placebo's *median* winner (+0.1212%%) beats the real winner (+0.1034%%). On two
years **every entry time is negative.** And the two samples disagree about
which time wins — 09:50 vs 12:30 — the instability signature day-21 named when
it refused 09:40.

### Two things that ARE real, and neither is an edge
* **Variance falls monotonically with a later entry** — TSX std 0.667 -> 0.393,
  twins 0.440 -> 0.268 — simply because less session remains, and the mean does
  not rise with it. Structurally identical to day-36: this strategy can always
  buy less risk by shortening exposure, never more return.
* **"Positive sessions" climbs to 66%% at 10:30/11:00 while the mean stays
  flat.** That is exactly the scratch artifact `decisive_line` was built for on
  day-35: shorter horizons make smaller moves, so more of them land barely on
  the right side of zero. A win rate that improves while the mean doesn't is a
  measurement artifact, not a better entry.

Twenty-nine rejections, three adoptions.

## Day-40: hundreds of names instead of 21 — the last untested lever

This was the one dimension I had been unable to rule out, and it needed new
data. Two things made it possible:

* **The S&P/TSX Composite list** (220 names) instead of the hand-picked 21.
* **TSX hourly volume is usable again.** Day-22 measured 86%% of TSX 1h bars
  with zeroed volume, which killed the `vp` feature and forced every deep study
  onto 20 US dual-listings as a proxy. Re-measured today: **~13%% on 1h, ~1%% on
  5m.** So for the first time this repo has a **native** deep sample:
  **153,112 rows / 218 names / 715 sessions.**

Day-14 rejected 21 -> 61 names, but on 60 days, without a placebo, and it
conflated two channels. It did find a real mechanism — low-volatility utilities
sit at the centre of the feature cloud *every* day, so they are permanently
"familiar" and hijack density selection — which implies a fix nobody tried:
rank a name's density against **its own** history, not the cross-section.
Growing the universe also gives more TRAINING data, so this run trains every
arm on the full wide universe and varies **only the eligible candidate set**:
same model, different menu.

### VERDICT — REJECTED (#30). 654 test sessions, ~3 years.

| pool | densest | max_p | random | self-relative |
|---|---|---|---|---|
| 21 shipped | -0.0163%% | +0.0021%% | -0.0074%% | -0.0081%% |
| 21 random | -0.0146%% | -0.0021%% | -0.0041%% | -0.0057%% |
| 50 random | +0.0018%% | -0.0078%% | -0.0024%% | +0.0056%% |
| 100 random | -0.0014%% | -0.0079%% | -0.0017%% | -0.0063%% |
| **all (218)** | +0.0122%% | -0.0217%% | **+0.0206%%** | -0.0020%% |

**Every arm sits inside ±0.022%%. Every t between -1.03 and +0.82. No trend
with pool size in any column.** The best arm (+0.0206%%) is *below* the placebo
median (+0.0314%%). **p = 0.867.**

### The finding is not what day-14 said
Day-14 concluded "the familiarity edge lives in a compact, homogeneous
universe." With 30x the sessions that reads as wrong in an instructive way:
**there is no edge to dilute at any breadth.** The 21-name universe is not
where the edge lives — it is where 60 days of data were too thin to see its
absence.

### The day-14 fix was well-motivated and changes nothing
Self-relative density scores **-0.0020%%** at full breadth. A better ordering of
a signal-free ranking is still signal-free.

### The thin sample would have lied — again
On 29 native 5m sessions, `all-220 / densest` scored **-0.2512%% (t -1.89)** and
looked like strong evidence that breadth actively HURTS. On 654 sessions the
same arm is **+0.0122%% (t +0.65)**. Had only the 5m run existed I would have
confidently written up a mechanism that does not exist — which is precisely
what day-14 did, and why it needed redoing.

Thirty rejections, three adoptions.

## Day-42: a green day, and the bug that was in MY report, not the market

| leg | side | capture | tide-rel | rank | verdict |
|---|---|---|---|---|---|
| BCE.TO | LONG | -0.276%% | -0.475%% | 14/21 | MISS |
| TRP.TO | LONG | **+0.726%%** | +0.526%% | 2/21 | HIT |
| BNS.TO | SHORT | -0.530%% | -0.331%% | 6/21 | MISS |
| CNR.TO | SHORT | **+1.080%%** | +1.280%% | 19/21 | HIT |

**NET +$119.90**, book-weighted **+0.240%%**, tide **+0.200%%** (breadth 13/21).
Relative capture **+0.250%%/leg** — 2 of 4 beat the tide, and the two that hit
did so on genuine selection: CNR was the 19th-best mover of 21 on a short, TRP
the 2nd-best of 21 on a long. Second consecutive green session.

**This changes nothing.** Two good days is what a coin flip looks like twice.
The day-37 verdict — 25+ tested changes, 3 adopted, all variance results, the
selection layer inert at 50.1%% vs 50.2%% random over 944 legs — is not touched
by a +$119 Friday, and it would be exactly the failure mode this file exists to
prevent to write it up as though it were.

### The real defect today was in the REPORT, not the strategy
Two sessions were working this repository in parallel. This clone was **eight
commits stale**, so `ledger.csv` was missing the entire 2026-08-13 session —
which went **0/4 on the pair**. Consequences, both in the 9:46 report handed to
the user:

1. The record printed **PAIR 24/47 (51%%)**. The truth was **24/51 (47%%)** —
   overstated by 4pp, in the flattering direction.
2. The report stated *"no run yesterday, so there's no unscored backlog."*
   There had been a run. It was the worst session of the month.

Absence of rows was read as absence of events. The board itself was never at
risk — it is computed from market data and never reads the ledger, and the
parallel session's `r945.py` changes were print-text plus an optional `--html`
flag, so the picks were byte-identical either way. But the *record* underneath
the board is the only thing that tells the user whether to trust it, and it was
wrong in the direction that makes the system look better than it is.

### IMPLEMENTED: `missing_sessions()` / `gap_line()` (+6 tests, 228 passing)
Between the ledger's last entry and today, any TSX trading day with no rows is
now named in both `ledger.py`'s report and the 9:46 board header:

```
  ⚠ RECORD MAY BE INCOMPLETE: no rows for trading day(s) 2026-08-13. Either no
    board was published then, or this copy of the ledger is stale (day-42).
```

Verified by replaying commit `061ca63`'s `ledger.csv` — this morning's exact
stale state — through the guard: it names 2026-08-13. On the current complete
ledger it is silent.

**Deliberately a warning, not a fail-closed refusal**, which breaks from
`coverage_ok` and `extrapolation_check`. Those protect the BET, and a partial
universe silently changes it, so refusing is right. This protects the RECORD,
and withholding a board that does not depend on the ledger would be theatre. A
legitimate no-run day trips it too — correctly, since from the ledger's side a
day nobody ran and a day that failed to sync are indistinguishable, and only the
reader can tell them apart.

### No strategy change adopted
Nothing in the session's four legs was a new pattern. The [mid] tag stayed bad
(both board mid names missed; the bucket is now 30/73, 41%%) but the pair only
ever selects DENSE legs, so mid never enters the book — dropping it changes no
trade, which is why it was rejected before and is still not a lever.

Standing: pair 26/55 (47%%), decisive 22/49 (45%%), book-weighted
-0.154%%/session (4/12 positive), relative capture -0.068%%/leg with 20/45
beating the tide.

## Day-43: the question thirty rejections never asked — model, or information?

Every one of the thirty rejected changes varied the **wrapper**: which leg to
pick, when to enter, when to exit, how long to hold, how many names to scan,
how many picks to take, what bar to qualify at, how to size. Not one varied the
**information** the prediction is computed from. The engine has used exactly
three features since day one — `r0`, `gap`, `vp` — and nobody ever asked whether
those three carry signal at all.

`validate_ceiling.py` asks it. If the features are informative and the k-NN is
too weak to extract them, a stronger learner wins and there is an accuracy lever.
If they carry nothing, then no selector, bar, or sizing rule built on them can
ever add accuracy — and thirty rejections stop looking like thirty unlucky draws
and start looking like **one fact observed thirty times**.

### The result, on 122,234 out-of-sample rows / 715 sessions (native TSX 1h)

| model | AUC | z | acc | Brier |
|---|---|---|---|---|
| baseline | 0.4895 | -6.34 | 49.5%% | 0.2501 |
| **knn (shipped)** | 0.4994 | **-0.39** | 50.0%% | 0.2525 |
| logistic | 0.4925 | -4.54 | 49.8%% | 0.2501 |
| **grad boost** | 0.5022 | **+1.32** | 50.3%% | 0.2508 |

Walk-forward by SESSION, never by row — two legs of one day share market
direction, so a row-wise split leaks. Gradient boosting has ~100x the capacity
of the shipped k-NN and finds **nothing**: z=1.32 on 122k rows.

Repeated on the native 9:45 5m pool where all three features ARE computable
(13,090 rows / 60 sessions): best real AUC **0.5106, z=1.04**. Same verdict.

### The positive control — why this null is trustworthy
This project's history is a history of false POSITIVES: a 60-day window
manufactures an effect, it ships, a wider sample kills it. A ceiling test has
the **opposite** failure mode — reporting "no signal" when the harness is simply
broken, which looks identical from the outside. So every run also fits the same
pipeline to a synthetic feature carrying a deliberately weak **52%%** edge:

| | real features | planted 52%% coin |
|---|---|---|
| knn (shipped) | z = **-0.39** | z = **+6.44** |
| logistic | z = -4.54 | z = **+15.47** |
| grad boost | z = +1.32 | z = **+13.39** |

The harness detects a 52%% coin at z=15. It sees nothing in `r0`/`gap`. Even the
shipped k-NN — the weakest extractor of the three — would have lit up at z=6.4
had a 52%% edge been present. **The features are the ceiling, not the model.**

### A data defect found on the way, and it invalidates a claim in shipped code
`build_pool.py` said TSX hourly volume was re-measured at "~13%% zeroed, so `vp`
is now computable and a NATIVE 2-year panel is possible". Day-22 had said 86%%.
**Both are right, and the conclusion drawn from the 13%% was wrong.** Measured
over 720 days on 5 large caps:

    all 1h bars       12.4-12.6%% zeroed     <- the reassuring number
    FIRST bar of day  86.1-86.8%% zeroed     <- the one that matters
    later bars         0.0- 0.3%% zeroed

The zeros are almost entirely the first bar of each session — and the 1h pool's
entry IS the first bar. So 85.9%% of its `v15` is zero and `vp` is not computable
on that panel at all.

It fails **silently**, twice over. First run of the ceiling test, `vp` NaN'd out
**145,201 of 145,228 rows** and left 27. And the idiom used across the existing
validators, `v15 / (median or 1)`, is worse than that: **100%% of tickers have a
zero median v15**, so it divides by 1 and yields RAW SHARE VOLUME — a big name's
raw count standardised against a small name's, exactly zero on 86%% of rows.
Every 1h-pool study that included `vp` was run on that column.

**This does not overturn day-37 through day-40.** Those compare arms drawn from
the same rows, and both arms carried the identical broken column, so the
comparisons stand. What changes is the description: no 1h result may be called a
test of the shipped THREE-feature engine. `usable_feats()` now measures the zero
rate and drops the column loudly instead of either failure mode.

### What this means for "how do we improve accuracy"
The honest answer is now specific rather than discouraging. Accuracy cannot be
improved by rearranging these three features — that is measured, not opined, and
the thirty rejections are its downstream consequence. It can only be improved by
**new information**. The candidates, in order of plausibility and none of them
free: order-book imbalance and true 9:45 volume pace (needs L1/L2 — TMX or IBKR,
not Yahoo); overnight news and earnings/guidance events (needs a dated feed with
point-in-time timestamps); sector/index futures state at 9:45; and short
interest or borrow cost. All of them are DATA acquisitions, not code changes,
and each one has to clear the same all-four-quarters bar as everything else.

Until such a feed exists, `--shadow` remains the correct mode — the day-37
recommendation, now with a mechanism behind it rather than an accumulation of
disappointments.

Standing: pair 26/55 (47%%), decisive 22/49 (45%%), book-weighted
-0.154%%/session (4/12 positive), relative capture -0.068%%/leg with 20/45
beating the tide.

## Day-44 addendum: "are you sure no longs? increase the coverage then" — re-verified live, and re-declined

A one-legged day (SHORT only, NTR.TO + T.TO) drew the obvious question: is
"no qualified long" really true, and would widening the universe fix it?

### Verified directly, not re-asserted
Reran the pipeline live and printed every one of the 21 names' `p_up`, not
just the qualified ones. Highest was **SU.TO at 0.535** — 15bp short of the
0.55 bar. No long today is correct, not a bug or a stale read.

### Widened it live, to answer the question with a number instead of a citation
Pulled the full 220-name S&P/TSX Composite and ran today's exact pipeline
against it (187/220 fetched). **18 qualified longs appeared** — densest pick
ABRA.TO, p_up 0.551. So yes: mechanically, more candidates means more names
cross an arbitrary threshold on any given day.

**This is day-40, re-litigated.** That was already the question, tested on
654 sessions: every pool size from 21 to 218 scored inside +/-0.022%%, p=0.867,
and the full-universe densest arm sat BELOW the placebo median. A wider net
catches more fish and more driftwood at the same ratio — today's ABRA.TO is
one draw from a pool that adds candidates without adding accuracy.

### Decision, put to the user rather than assumed
Three options were laid out plainly — keep 21 (matches the evidence), widen
permanently (accept day-40's null in exchange for fewer no-trade days), or log
the wide board as unstraded instrumentation. **Chosen: keep 21.** No config
change. Today's one-legged book (SHORT NTR.TO + T.TO, LONG side in cash)
stands as published.

The instructive part isn't the answer, which was already known — it's that
"are you sure" got a direct re-measurement instead of a restated prior, and
"increase the coverage" got an actual live run of the alternative instead of a
citation of day-40 alone. Both are now on the record with today's numbers, not
just the 3-year backtest's.

## Day-44: both legs hit, and the intraday path confirms existing rules rather than adding one

| leg | move | tide-rel | rank | verdict |
|---|---|---|---|---|
| NTR.TO | -0.274%% | -0.089%% | 12/21 | HIT |
| T.TO | **-0.958%%** | **-0.773%%** | **21/21** | HIT |

**NET +$136.63.** Tide -0.185%% (breadth 8/21 up). The two hits were earned
very differently: NTR's own move barely exceeded the tape's own decline (rank
12/21, near-zero relative capture), while T.TO was the single worst-performing
name in the entire 21-name universe (rank 21/21) — real selection, not drift.

### Intraday path
T.TO fell fast right after entry (-0.59%% by 9:50), partially round-tripped back
toward flat by 10:00-10:15 (-0.07%%), then built its real move from 11:30 on,
bottoming near -1.25%% at 15:00 before closing -0.96%%. NTR chopped between
+0.28%% and -0.47%% all session with no trend, finding its closing print only in
the final 45 minutes. Book P&L dipped negative twice early (-$16 at 9:30, -$35
at 10:00) before the afternoon move took over. Neither leg approached the 2.5%%
disaster line.

Of the six qualified shorts, the DENSE ones (NTR, T, TD) all hit; CVE (mid) missed
badly at +1.898%%, TRP (sparse) scratched at +0.011%%. Directionally consistent
with the standing density hypothesis (dense 53%% vs mid 41%% cumulative) — one
more data point in an existing column, not new evidence.

### No new lever — this session corroborates three shipped findings
1. **T.TO's early round-trip is why hold-to-close exists.** Watching the 10:00
   print would have shown the short near breakeven; bailing there would have
   missed the entire afternoon move. Day-19/20, reconfirmed.
2. **NTR's signal materialised only in the final 45 minutes.** Consistent with
   day-36's exit-timing study (944 legs, flat curve, no peak to exit at). One
   session does not move that result.
3. **NTR vs T is a clean live case of why `relative_line()` exists.** Both
   scored as ledger HITs; only the tide-relative number shows T did the real
   work while NTR mostly matched the market. The machinery already answers the
   question this contrast raises — nothing to add.

No code change. Also directly answered live and re-logged as a day-44 addendum:
"are you sure no longs?" (verified — closest miss SU.TO at 0.535) and "increase
the coverage then" (tested live against all 220 TSX Composite names, 18 longs
would have qualified — but this is day-40 re-litigated, 654 sessions already
inside +/-0.022%%, p=0.867; user chose to keep the 21-name universe).

Standing: pair 28/57 (49%%), decisive 24/51 (47%%), book-weighted
-0.122%%/session (5/13 positive), relative capture -0.046%%/leg with 22/47
beating the tide.

## Day-45: 1/4 legs — and the decomposition that says it was ALL selection

| leg | side | move | capture | tide-rel | rank | verdict |
|---|---|---|---|---|---|---|
| CNR.TO | LONG | -0.492%% | -0.492%% | **-0.026%%** | 12/21 | MISS |
| RY.TO | LONG | -0.537%% | -0.537%% | **-0.071%%** | 13/21 | MISS |
| SLF.TO | SHORT | +0.134%% | -0.134%% | **-0.600%%** | 7/21 | MISS |
| BNS.TO | SHORT | -0.350%% | +0.350%% | -0.116%% | 10/21 | HIT |

Hypothetical **-$97.53**, book-weighted **-0.195%%**. Tide **-0.466%%**, breadth
7/21. (No capital was at risk — the order window had closed before the run
finished, see day-45 publish note.)

### The two longs were NOT the mistake, and the relative column proves it
CNR at -0.026%% and RY at -0.071%% relative are, to two decimals, *the tide*.
They fell because the whole tape fell half a percent. As direction calls they
were near-perfectly average; as P&L they were the biggest dollar losers. Those
are different statements and the ledger has, until now, only reported the
second one clearly.

**The actual error was SLF.TO**: -0.600%% relative, the only leg meaningfully
worse than the tape, and 72%% of the day's entire loss. It was shorted and it
ROSE on a day when 14 of 21 names fell.

### IMPLEMENTED: `attribution()` / `attribution_line()` (+5 tests, 238 passing)
Every post-mortem here has argued verbally about "the market" vs "the picks",
and the two existing lines each answer half: `book_return_line` gives the
total, `relative_line` gives per-leg skill but is equal-weighted and does not
reconcile to the book. This splits it exactly, with no residual:

    sum(w*cap) = tide * sum(w*sign)     <- TIDE component (residual exposure)
               + sum(w*sign*rel)         <- SELECTION component (the picks)

Live over 14 sessions:

```
attribution : TIDE +0.018%%/session (market exposure, target ~0)
            · SELECTION -0.145%%/session (the picks)
```

They sum to the -0.127%%/session book return. **The hedge works — residual
market exposure is +0.009%% with t=+0.78, indistinguishable from the zero it is
designed to be. Every bit of the loss is selection.** That is the first direct
measurement of the long/short construction actually doing its job, rather than
it being assumed.

Honest caveat on the other half: SELECTION is -0.136%%/session with **t=-1.10,
95%% CI [-0.379, +0.106]** — it contains zero. Fourteen sessions cannot
distinguish a bad selector from an unlucky coin flip, and day-43 already
established which one it is (AUC 0.5022, z=1.32 on 122k rows). This is what a
signal-free selector looks like when you watch it for three weeks.

### The tempting pattern, measured and NOT adopted
The two best shorts in the universe today were T.TO (-1.031%%) and SHOP.TO
(-1.321%%) — **both were qualified, and both were rejected by the density
selector because they were tagged [mid]**. It took SLF (dense) instead, which
had the LOWEST sided-P of the five qualified shorts and was the worst outcome
of them. The obvious inference is "density is picking the wrong leg."

Tested it on the live ledger, tide-removed, comparing each day-side's PAIR legs
against the untraded BOARD legs on the same side — the direct question of
whether the selector adds value over the names it passed over:

    pair beat board on 17 of 34 day-sides
    mean advantage +0.047%%/leg, t = +0.26

**Exactly a coin flip.** Today is an anecdote in a sample that says the selector
neither adds nor destroys value, which matches day-9/12/14/22 (densest 50.1%%
vs max-P 48.3%% vs random 50.2%%). No change adopted. Rejection count stands at
thirty.

Standing: pair 29/61 (48%%), decisive 25/55 (45%%), book-weighted
-0.127%%/session (5/14 positive), relative capture -0.057%%/leg with 22/51
beating the tide.

## Day-47: a WINNING day whose profit was luck, and rejection #31

The book closed **+$73.39**. The attribution says do not celebrate it:

```
net directional exposure  -0.4989   (a hedged book is ~0)
TIDE component            +0.6655%
SELECTION component       -0.5183%
book-weighted total       +0.1472%
```

Tide **-1.334%**, breadth 4/21. No long qualified, so the book was short-only
and carried ~50%% net short exposure into a falling tape. **Every cent came from
being unhedged. The picks lost half a percent — the worst selection day of the
run.** Had the tape risen the same amount, the identical book loses the same
$73 with the identical picks. Without the day-45 attribution this reads as a
green day.

### The selector drew from the bottom of the day's distribution
13 of 15 qualified shorts hit. Ranked by capture, the top eight were all
`sparse` or `mid`; the two `dense` names — the only two the selector sizes —
came **9th and 14th of 15**, and the day's highest-conviction pick (BCE,
sided-P 0.617) closed UP while the tape fell 1.3%%.

| rank | ticker | tag | capture |
|---|---|---|---|
| 1 | BMO.TO | sparse | +3.296%% |
| 2 | CM.TO | sparse | +3.076%% |
| 3 | TD.TO | mid | +2.884%% |
| **9** | **CNQ.TO** | **dense** | **+1.140%%** <- sized |
| **14** | **BCE.TO** | **dense** | **-0.430%%** <- sized |

### REJECTED (#31), but the mechanism is REAL — `validate_density.py`, 719 sessions
The obvious inference is that density picks losers. Tested on 40,801 qualified
picks, walk-forward, with the standing four-quarter rule:

| tag | n | hit | capture | \|move\| | vol20 |
|---|---|---|---|---|---|
| dense | 13,601 | 49.5%% | -0.0062 | **0.732%%** | 1.565 |
| mid | 13,600 | 49.7%% | +0.0082 | 0.851%% | 1.821 |
| sparse | 13,600 | 49.6%% | +0.0012 | **1.287%%** | 2.657 |

**Q1 and Q2 confirmed, Q3 refuted.** `corr(nd, vol20) = +0.174` — dense really
is a proxy for CALM, and dense names really do move 43%% less than sparse ones.
But hit rate is flat to a tenth of a point across all three tags, and sparse
beat dense on capture in only **2 of 4 quarters** against a 4-of-4 bar. The tag
sorts by VOLATILITY, not by edge. Picking the calm name for the same expected
return is exactly what a tie-break should do — and all three adopted changes in
this project have been variance results.

Today felt like proof because big movers pay on a big-tide day. They punish
symmetrically on the days the tape runs the other way; that is variance, not
edge, and the whole point of the four-quarter rule is to stop one vivid session
from being mistaken for the second kind.

### The pre-registered density gate is now CLOSED — verdict: NO GATE
The live ledger currently shows sparse 56%% vs dense 52%%, which is what tempted
this in the first place. That is n=90 against n=13,601 per bucket in the deep
test. `ledger.py` no longer says "gate decision at ~20 tagged days"; it states
the verdict and why the live spread is noise, so the next reader is not tempted
by the same table.

### IMPLEMENTED: `one_sided_warning()` (+4 tests, 242 passing)
The board already printed "one leg is missing", which reads as a note about
lost opportunity. It never said the surviving leg converts a market-neutral
strategy into a directional bet. Now it does, at 9:46, while it can still
inform the decision:

```
⚠ THIS BOOK IS NOT MARKET-NEUTRAL TODAY. With the long half in cash it runs
  ~50%% net SHORT exposure, so today's P&L will be dominated by the TAPE, not
  by the picks: it profits if the market falls and loses by the same amount if
  it rises, whether or not the 2 legs are well chosen.
  Day-45 measured residual exposure at ~0 on two-sided days; that protection
  is absent here.
```

One of its tests asserts the warning agrees with the attribution arithmetic on
today's actual rows, so the claim and the measurement cannot drift apart.

Standing: pair 30/63 (48%%), decisive 26/57 (46%%), book-weighted
-0.109%%/session (6/15 positive), relative capture -0.080%%/leg with 20/48
beating the tide. Thirty-one rejections, three adoptions.

## Day-49: 0/3, no tape to blame — and four refuted claims still shipping

| leg | side | move | capture | rank | verdict |
|---|---|---|---|---|---|
| SU.TO | LONG | -1.023%% | -1.023%% | **18/21** | MISS |
| CNR.TO | SHORT | +0.718%% | -0.718%% | **4/21** | MISS |
| CP.TO | SHORT | +0.445%% | -0.445%% | **5/21** | MISS |

**NET -$401.33.** Tide only -0.237%%, and the book was properly hedged:

```
net directional exposure  +0.0044   (hedged, as designed)
TIDE component            -0.0010%%
SELECTION component       -0.8016%%   <- all of it
```

Yesterday's excuse does not apply. The hedge did its job and the selection
still lost 0.80%% — **the worst selection day of the run**. Nor were these near
misses: the engine longed the 4th-WORST name and shorted the 4th- and 5th-BEST.
Maximally anti-correlated on all three legs. That is a bad draw from a coin
(day-43: AUC 0.5022 on 122k rows), not a malfunction — but it is the shape of
day this record will keep producing until the information changes.

### THE REAL DEFECT FOUND TODAY: a decided verdict that never propagated
Day-47 closed the density gate. The verdict reached ONE line of `ledger.py` and
stopped. Four places still asserted the refuted position, and one of them
printed on **every board, every morning**:

1. `r945.py` docstring citing a **"63%% vs ~46%%"** holdout — refuted by
   49.5/49.7/49.6 on 40,801 picks.
2. Same docstring leaving the gate pending **"~20 live days"** — decided.
3. `ledger.py` module docstring repeating the pending framing.
4. The board tagline **"selected by DENSITY — familiarity beats extremity"** —
   an explicit edge claim, when day-47 showed density sorts by VOLATILITY.

This is the same failure class as day-42's stale ledger: a measurement is only
half-applied while the shipped text still says the old thing. A user reading
the board this morning was told density beats extremity, three days after that
was disproved. Now reads:

```
(tie-broken by DENSITY — a CALMNESS sort, not an edge: day-47)
```

Four regression tests assert none of the four can creep back (246 passing).

### Rest of the audit, clean
Every module byte-compiles; no bare excepts survive the day-29 rule; the two
`except Exception: pass` sites are correctly-scoped optional paths (a Windows
encoding fallback and the optional HTML record line), each with a working outer
report. **There is no bug in this repo that caused today**, and saying so is not
a deflection — it is the reason the only remaining lever is new information,
not new code.

### The out-of-sample replication is finally running
Day-46's `scaled` family (r0 and gap in units of each name's own volatility)
was the one arm positive in all four cells of that sweep, but it was generated
from a 12-arm search over the TSX panel and re-testing it there would be the
same draw read twice. `build_rich.py --us` now builds the identical feature
panel on **503 S&P 500 names** — different names, different market. 5m panel
built (29,968 rows / 501 names); the 3-year hourly panel is in flight. The
scrape fails loudly below 400 symbols rather than silently testing a truncated
universe.

Standing: pair 30/66 (45%%), decisive 26/60 (43%%), book-weighted
-0.152%%/session (6/16 positive), relative capture -0.123%%/leg with 20/51
beating the tide. Thirty-one rejections, three adoptions.

## Day-50: 4/4, and for once the reason is the good one

| leg | side | move | capture | tide-rel | rank | verdict |
|---|---|---|---|---|---|---|
| SU.TO | LONG | +0.159%% | +0.159%% | **+0.677%%** | 8/21 | HIT |
| AEM.TO | LONG | +0.013%% | +0.013%% | +0.531%% | 9/21 | hit (SCRATCH) |
| TD.TO | SHORT | -1.219%% | **+1.219%%** | **+0.701%%** | 18/21 | HIT |
| MFC.TO | SHORT | -0.728%% | **+0.728%%** | +0.210%% | 14/21 | HIT |

**NET +$267.99.** Tide -0.518%%, and the attribution is the point:

```
net exposure  -0.0007   (hedged, as designed)
TIDE          +0.0004%%  (essentially nothing)
SELECTION     +0.5356%%  <- all of it
```

**All four legs beat the tide**, three by more than half a percent. This is the
best SELECTION day recorded, and it completes a three-day set that shows why the
day-45 attribution was worth building:

| day | NET | hedge | TIDE | SELECTION | the honest reading |
|---|---|---|---|---|---|
| 47 | +$73 | one-legged | **+0.666%%** | -0.518%% | profit was unhedged luck |
| 49 | -$401 | working | -0.001%% | **-0.802%%** | picks were simply wrong |
| 50 | +$268 | working | +0.000%% | **+0.536%%** | picks were simply right |

Three consecutive sessions where the sign of the P&L and the sign of the SKILL
disagreed, agreed, and agreed again — and only the decomposition can tell them
apart. The headline number could not.

### Two things not to over-read
**TD short was the day's best call and had no evidence behind it.** It was
shorted after a +0.83%% first fifteen minutes, and the header records that the
"ramps fade" claim was REFUTED on 5,160 ticker-sessions (fade rate 42.7-50.5%%
across all four quarters; ramps mildly CONTINUE). It worked. One session does
not revive a claim that died on a year of data, and writing it up as though it
did is the exact failure mode this file exists to prevent.

**AEM is an economic scratch** (+0.013%%, $1.32). It scores as a hit in the sign
column. The honest count is three real hits, not four — which is what
`decisive_line` was added on day-35 to say out loud.

### NOTHING ADOPTED
A 4/4 day is when the pull to "lock in what worked" is strongest, and this
project's false positives were all born exactly there: day-9's 68%% selector,
day-22's 2.7x short asymmetry, day-29's selectivity claim. Each was vivid,
small, and killed by a wider sample.

One great day moved the pair line from 45%% to 49%%. It is still a coin flip.

Standing: pair 34/70 (49%%), decisive 29/63 (46%%), book-weighted
-0.111%%/session (7/17 positive), relative capture -0.087%%/leg with 26/60
beating the tide. Thirty-one rejections, three adoptions.

## Day-51: should each pick carry its own suggested HOLD DURATION? — REJECTED (#32)

Asked directly: add a suggested duration so the book can capture event/swing
moves instead of being capped at intraday. Four prior measurements bear on it
(day-24 overnight, day-32 event swings, day-36 exit time, day-38 fixed 3d/5d
holds) but **all four applied the SAME horizon to every trade**. Whether the
right horizon is PREDICTABLE PER PICK had never been asked, and that is the
only version of the idea that justifies a duration field.
`validate_horizon.py`, 38,402 qualified picks over 719 walk-forward sessions.

### A — does holding longer make the DIRECTION more often right?

| hold | hit (raw) | **hit (tide-relative)** | raw cap | **REL cap** | std | worst |
|---|---|---|---|---|---|---|
| to close | 49.6%% | **49.6%%** | +0.0006 | -0.0025 | 1.314 | -16.23%% |
| +1 day | 50.0%% | **50.0%%** | +0.0231 | +0.0012 | 2.667 | -80.43%% |
| +2 days | 50.2%% | **49.8%%** | +0.0224 | -0.0035 | 3.489 | -80.02%% |
| +3 days | 50.2%% | **49.9%%** | +0.0313 | -0.0114 | 4.204 | -80.33%% |
| +5 days | 50.4%% | **49.7%%** | +0.0592 | +0.0084 | 5.385 | -79.52%% |

**No.** Raw hit rate creeps 49.6%% -> 50.4%%, and every point of that is drift:
tide-relative accuracy is FLAT at 49.6-50.0%% across all five horizons. The raw
column is measuring the market, not the prediction — day-38's finding, now
visible in the accuracy column rather than just the return column.

Meanwhile the risk is not flat at all. Volatility **4x** (1.314 -> 5.385) and
the worst trade goes from **-16%% to -80%%**. Zero return improvement, five times
the tail.

### C — is the right horizon predictable?
Correlation between every 9:45 feature and the advantage of holding three extra
days: **max |corr| = 0.026** (`ret5`). Everything else is under 0.02. Nothing
knows which picks deserve a longer hold.

### D — the oracle bound, and the mistake I nearly shipped
Perfect per-pick horizon selection would earn **+2.3453%%/trade** against
+0.0084%% for the best fixed horizon — a gap of **+2.34%%**. The first version of
this script printed *"the gap is large; a predictor could matter"*, which is
wrong, and would have justified building the feature.

**Taking the maximum of five noisy, positively-correlated draws exceeds their
mean BY CONSTRUCTION**, signal or no signal. Recomputing the oracle on
multivariate noise with the same means and covariance:

```
REAL    oracle gap  +2.3369%%/trade
PLACEBO oracle gap  +2.8510%%/trade   (20 draws, sd 0.0117)
real / placebo = 0.82x
```

**The real gap is SMALLER than pure noise produces.** The entire "prize" is the
expected maximum of five noisy draws. There is nothing for any predictor to
find, at any skill level — the question is closed without needing a model.

The placebo is now built into the script and the verdict logic keys off the
EXCESS over it, so the naive reading cannot recur.

### On "event trade capture" specifically
Real event capture requires knowing WHEN events occur — earnings, guidance,
news. This engine has no such feed (day-43's binding gap). Without one, a longer
hold is not event capture; it is a longer random exposure to whatever happens.
A duration field cannot manufacture event awareness out of OHLCV bars.

Thirty-two rejections, three adoptions.

## Day-52: the US replication — `scaled` survives one market, dies in the other (#33)

Day-46's sweep found `scaled` (r0/gap in units of each name's OWN trailing
volatility) positive in all four cells on TSX, below the |z|>=3 bar. Day-51
re-ran the identical sweep on **500 S&P 500 names, 719 sessions, 294,949
out-of-sample rows** — a different market, so a TSX-generated hypothesis could
be confirmed rather than re-read on the draw that produced it.

### The pooled numbers looked like the first real find in fifty-one days

| | TSX (generated) | S&P 500 (replication) |
|---|---|---|
| `scaled` on y_rel | AUC 0.5045, z=+2.72 | AUC 0.5064, **z=+6.03** |

Same sign, near-identical effect size, comfortably past the bar out-of-sample.

### The four-quarter rule killed it, and the TSX column is the reason

| quarter | TSX shipped | TSX scaled | diff | US shipped | US scaled | diff |
|---|---|---|---|---|---|---|
| Q1 | 0.4967 | 0.5054 | **+0.0087** | 0.5007 | 0.5029 | +0.0022 |
| Q2 | 0.5085 | 0.5044 | -0.0040 | 0.5074 | 0.5144 | +0.0069 |
| Q3 | 0.5082 | 0.5036 | -0.0047 | 0.4991 | 0.4996 | +0.0006 |
| Q4 | 0.5057 | 0.5046 | -0.0011 | 0.5041 | 0.5076 | +0.0036 |
| **POOLED** | 0.5045 | 0.5045 | **-0.0001** | 0.5030 | 0.5064 | +0.0034 |

**US: 4 of 4 quarters. TSX: 1 of 4, and pooled dead level at -0.0001.**
`scaled` is genuinely better than `shipped` on US large caps and genuinely
IDENTICAL to it on the TSX names actually traded. Adopting on the strength of
the US column would be shipping a feature that measurably does nothing in the
only market the book touches. **REJECTED (#33).**

### The mistake in how day-46 was READ, which this exposes
Day-46 called `scaled` "the only family positive in all four cells". True, and
misleading: `shipped` was ALSO positive on y_rel (z=+2.75 TSX, +2.81 US). Each
family was compared against ZERO, never head-to-head against the incumbent.
Against the incumbent, on TSX, the difference is -0.0001 AUC.

**The real finding of day-46 was never `scaled`. It was the TARGET.** `y_rel`
("does this name beat the day's median") beat `y_abs` ("does it go up") for
almost every family on both markets — which is what day-45's attribution
implied, since residual market exposure is ~0 and 100%% of the book's P&L is
cross-sectional. Predicting absolute direction to place a relative bet has been
a mismatch since day one. That remains untested AS A CHANGE and is the one
thread left worth pulling.

### A flaw in my own pre-registered bar, stated plainly
The day-46 bar required sign agreement on the NATIVE 5-minute panel. That leg
is uninformative: 60 sessions is all Yahoo serves at 5m, and the native
positive control came back **z=-1.71 and z=+2.32** — it cannot detect a PLANTED
52%% coin and got one sign wrong. The bar was unsatisfiable with free data. This
was flagged on day-46 and not fixed, so day-51 re-ran into the same wall.
Replaced by the two-market four-quarter test above, which is stricter and
actually executable.

### And the caution that outlives all of it
AUC 0.5064 on 295k rows is overwhelmingly significant and nearly worthless.
z=6 certifies the effect is real; it says nothing about whether it is large
enough to survive spread and slippage. A +0.0034 AUC lift is a rounding error
against costs. Significance and usefulness are different questions and only the
second one pays — worth remembering the next time a big z appears.

Thirty-three rejections, three adoptions.

## Day-53: train on cross-sectional rank instead of direction? — REJECTED (#34)

The oldest mismatch in the engine, finally tested as a CHANGE. The k-NN learns
`r1 > 0` — "will this go up?" — but the book is long AND short, so the tape
cancels between the legs and only relative performance pays. Day-45 made it
concrete: residual market exposure is +0.009%%/session (t=+0.78) while 100%% of
P&L is the cross-sectional term. The engine predicts one quantity to bet on
another.

`validate_target.py` runs the WHOLE shipped pipeline twice on identical rows —
same k-NN, same 0.55 bar, same densest tie-break, same 2-per-side — differing
in one line:

    shipped   y = (r1 > 0)
    xs        y = (r1 > that session's median r1)

scored on **tide-relative capture per leg**, not AUC on the target. Day-46's
hint was AUC-on-target, which is near-circular: a model trained on y_rel will
of course predict y_rel better, and that says nothing about what the book earns.

### Result: 2 of 4 quarters on BOTH markets

| quarter | TSX shipped | TSX xs | diff | US shipped | US xs | diff |
|---|---|---|---|---|---|---|
| Q1 | +0.0005 | -0.0382 | **-0.0388** | -0.0528 | -0.0246 | +0.0282 |
| Q2 | -0.0266 | -0.0398 | -0.0132 | +0.0225 | +0.0736 | +0.0511 |
| Q3 | -0.0331 | -0.0330 | +0.0001 | +0.0167 | +0.0090 | -0.0077 |
| Q4 | +0.0010 | +0.0432 | **+0.0421** | -0.0337 | -0.0627 | -0.0290 |
| **POOLED** | -0.0146 | -0.0169 | **-0.0024** | -0.0118 | -0.0012 | **+0.0106** |

**TSX 2/4 (pooled WORSE), US 2/4 (pooled better).** Not a near miss — the
quarters that win on one market are the quarters that lose on the other. TSX's
best quarter for `xs` is Q4 (+0.0421); US's Q4 is its worst (-0.0290). Sign
disagreement across neighbouring windows is the signature of noise, which is the
same verdict day-38 reached about its no-trade rules.

The theoretical argument for this change was, and remains, correct: predicting
absolute direction to place a relative bet IS a mismatch. It simply does not
matter, because neither label carries signal (day-43: AUC 0.5022 with gradient
boosting on 122k rows). **Relabelling noise produces different noise.** A
well-motivated fix to a component that has no signal to fix changes nothing —
the same lesson day-40 recorded when self-relative density scored -0.0020%%
("a better ordering of a signal-free ranking is still signal-free").

### MY OWN STATED HYPOTHESIS, REFUTED
I predicted `xs` would remove one-legged days, since ~half the universe beats
the median by construction, and day-47 showed a one-legged book runs ~50%% net
exposure with its P&L dominated by the tape. Measured:

    shipped  one-legged sessions: 0/599 (0.0%%)
    xs       one-legged sessions: 0/599 (0.0%%)

**Zero for both arms.** The one-legged day is a SMALL-UNIVERSE artifact — with
218 names there is always a candidate on each side; with the shipped 21 there
is not. The cross-sectional label cannot fix it because the label was never the
cause. Worth recording that I asserted a mechanism and the data refused it.

Thirty-four rejections, three adoptions.

## Day-54: a catalyst-thesis checker — `catalyst.py` (+11 tests, 257 passing)

A biotech PDUFA thesis was proposed as a new strategy class: upside $36.00,
downside $20.50, price $25.00, claimed P(approval) 85%%, "expected value +34.7%%".
Binary catalysts differ from everything else here in one important way — they
have a MECHANISM. A scheduled FDA decision reveals real information on a known
date. `r0`/`gap`/`vp` never had that.

### The arithmetic kills this particular thesis before any biology is discussed

```
market-implied p = (25.00 - 20.50) / (36.00 - 20.50) = 29.0%%
```

**The claim is 85%%. The tape says 29%%.** That 56-point gap IS the trade, and
nothing in the matrix defends it. Worse, the triple is impossible: for p=85%%
with a $36 upside to produce a $25 price, the downside would have to be
**-$37.33/share**. At least one input is wrong.

The stress table matters more than the EV headline, because the downside is an
ASSUMPTION — a "$322.5M cash floor" is not a bound, and small/mid-cap biotech
routinely trades BELOW cash after a CRL:

| CRL price | drop | breakeven p |
|---|---|---|
| $20.50 | -18%% | 29.0%% |
| $15.00 | -40%% | 47.6%% |
| $12.00 | -52%% | 54.2%% |
| $9.00 | -64%% | 59.3%% |

### Base rate: 85%% is above it, not at it
FDA's own first-cycle review data puts recent first-cycle complete-response
rates near 30%%, i.e. a first-cycle approval base rate around **70%%**. A PDUFA
date IS a first-cycle decision. The ~75-80%% figure most theses quote is
EVENTUAL approval across multiple cycles — a different and much friendlier
number that does not apply to a single date.

### The design lesson: a checker that always objects carries no information
The first FRAGILE rule fired whenever a -64%% stress demanded a high breakeven —
which is true of nearly every binary trade, so the warning was noise. Rebuilt
on a CUSHION: `implied_downside` IS the floor at which the claimed probability
breaks even, so the distance from the assumed floor is the room the thesis has
to be wrong. Fires below 15%% of share price.

Then the tool rejected the "sound thesis" written for its own passing test —
price 25, up 30, down 22, p=45%% — because that edge breaks even at $20.91, only
**4%% of price** below the assumed $22 floor. **The tool was right and the test
was wrong.** The test now records this, and a separate case locks the silence on
a genuinely sound thesis (wide bracket, price near the low end, claim only
modestly above the market's).

### What it deliberately cannot do
It cannot tell you whether 85%% is right. That is a research question about the
drug and it is the ONLY question that matters — so the job is to make the size
of the claim explicit rather than launder it into an "expected value" that reads
like a measurement. Read-only and order-free, like everything else here.

### Why this class is worth pursuing where the 9:45 engine was not
Unlike the intraday features (day-43: AUC 0.5022 on 122k rows), catalysts have a
real mechanism AND the historical data is obtainable — BiopharmaWatch's Elite
tier carries historical PDUFA outcomes with run-up/run-down analytics, OZMOSI
covers ~3,000 events over ~700 tickers. That is a purchasable dataset, not the
$1,109/month TMX wall.

**The bias that would destroy a naive backtest**: failed biotechs delist or get
acquired, so any catalyst study built on TODAY's tickers is survivorship-poisoned
in the most dangerous direction — the wipeouts are literally absent. Day-40
caught a milder version of this in the TSX universe. The dataset must be
point-in-time or it is worthless.

Three questions, in order, before any capital: (1) do PDUFA outcomes beat their
market-implied probabilities, or is the market calibrated — the same ceiling
question day-43 asked; (2) what is the ACTUAL CRL drawdown distribution, versus
what cash-floor arguments assume; (3) how much of the documented run-up is
already arbitraged away.

## Day-70: the intraday side finally gets NEW information — rejection #36, and one adopted risk flag

**The habit worth breaking.** Thirty-five rejections on the intraday side share
one property: every one was a new function of the SAME three numbers — morning
return, overnight gap, volume. Gradient boosting reached AUC 0.5022 on 122,234
rows where the same harness detects a planted 52% coin at z=15. That stopped
being a modelling problem a long time ago. Another model on those features is
not a plan, it is a habit.

The catalyst side broke out of exactly this by using an EVENT rather than a
price feature, and the break was decisive (CRL vs random: -15.0pp, t=-3.41). So
day-70 applies the lesson to the intraday universe.

**The source nobody had looked for.** `earnings.py` has carried the admission
since day-64 that there is "no free source of historical announcement dates for
TSX names". That was true of Yahoo and false of EDGAR: a Canadian issuer
cross-listed in the US furnishes a **6-K** for material news, and the SEC
submissions API serves every filing date, historically, free.

**The join is where this nearly died.** Matching TSX tickers to CIKs by root
symbol is a trap — AC.TO is Air Canada, but AC in the US is Associated Capital
Group. ARE.TO matched Alexandria Real Estate. CCO.TO (Cameco) matched Clear
Channel Outdoor. ABX.TO matched Abacus Global Management. **Forty-one names
matched a real CIK belonging to a different company**, and joining those filing
dates onto TSX prices would have produced a clean-looking dataset made of pure
noise.

The guard is one form code: Canadian issuers report under MJDS on 40-F, and a
US domestic filer never does. All forty-one were caught by it.

**A second bug the guard exposed.** `build_catalyst.ticker_map` builds
CIK → ticker, but the SEC's file has one row per SECURITY — Royal Bank lists
common and several preferred series under one CIK, so the dict collapsed them
and the last row won. 7,998 tickers survived out of 10,403, and the casualties
included **RY, TD, ENB and ABX**. Inverting a lossy map does not recover what it
lost; `sixk.us_ticker_map()` reads the source file and keys by ticker. Coverage
went 56 names → **78 names**, 3,178 filings → **4,537**.

**Same-day is not the test, for a causal reason rather than a statistical one.**
The API gives a filing DATE and no timestamp, so a 6-K furnished at 16:30 tags a
session whose leg closed at 16:00 — and worse, a company may file BECAUSE the
stock moved, letting the outcome cause the label. The primary definition is the
first session STRICTLY AFTER the filing date. (Same-day duly came in at +1.88pp,
z=+2.22 — the reverse-causality direction, and still under the bar.)

**Pre-registered:** adopt only at |z| ≥ 3 under a SESSION-CLUSTERED bootstrap
(Canadian banks report on the same mornings and share that day's market
direction; treating those rows as independent would inflate any z by √cluster),
with a passing placebo and a passing positive control.

| | event sessions | other sessions | difference | z |
|---|---|---|---|---|
| continuation of the morning move | 48.43% | 48.66% | **-0.23pp** | **-0.28** |
| size of the move, either way | 1.11% | 0.97% | **+0.140pp** | **+6.35** |

*positive control detected; placebo (random sessions, same names, same counts)
+0.64pp at z=+0.72; 52,919 rows across 78 names.*

**REJECTION #36 — direction.** A 6-K filing is real, dated, and free, and the
session after one is not one basis point more predictable in direction than any
other session of the same name.

**ADOPTED — magnitude, as a RISK FLAG and never as a signal.** The same rows
move measurably further either way. More risk at no more edge is not a neutral
change; at a coin-flip direction, added variance is pure cost.

**Labelled honestly:** the magnitude test was written AFTER seeing the |r1|
column in the first run. It was not pre-registered and does not get called a
discovery. Two things earn it a place anyway — the mechanism is the least exotic
one in finance (news arrives, the stock moves more), and z=+6.35 survives any
sane correction for having asked two questions instead of one.

Shipped as `sixk.py`, printed under the intraday pair, warning and never
blocking — for the same reason `earnings.py` warns: no flag rescues a coin flip,
but a reader is entitled to know they are in the wider half of the distribution
before they size it.

## Day-70: the catalyst screen stops printing inputs and starts giving a verdict

The screen had been printing implied move, skew, cash per share and runway as
four separate lines and leaving the reader to combine them. That is a data dump
with good manners — it pushes the hardest step, the one where mistakes cost
money, onto the person with the least context about how each number was derived.

**The hinge is one number.**

    breakeven P(CRL) = put cost / |measured median rejection|

A put at 9% of spot against the measured -15.2% median needs a rejection to be
~59% likely just to break even. Asked that way, most catalyst "lottery tickets"
die on the spot. It is an UPPER bound — it uses the median while the left tail
is much fatter (p10 -57.5%) — and erring toward "this is expensive" is the safe
direction for a screen that must not talk anyone into a position.

**The spine of every verdict is the day-68 asymmetry, measured here:** a
rejection is violent and unpriced (-15.2% median, -15.0pp vs random, t=-3.41,
n=64) while an approval FAILS the same placebo gate (t=+0.98, median -2.52% vs
random -0.54%). Read together there is **no probability of approval at which
holding a long through the print is positive on this evidence** — the winning
outcome pays nothing distinguishable from a random three-day window while the
losing one takes 15%. A long into a PDUFA is selling insurance, not buying a
lottery ticket, and the screen now says so on every name.

**What it still refuses to do is supply P(CRL).** 8-K filings give the numerator
(64 rejections) and not the denominator, so a base rate computed here would be
fabricated. The verdict states the probability you would have to hold; the
conviction stays with the reader.

**The quote is checked before it is trusted**, because the verdict turns on one
put price and a stale quote does not produce a slightly-off call, it produces a
confident wrong one. Prices now come from the MID of a two-sided quote, with
`lastPrice` as a labelled fallback. Not theoretical: ZYME's ATM put was **24.6%
of spot on last trades and 13.6% on mids**, moving the breakeven from "no
probability makes the median case pay" to ~89%. Three checks gate the verdict —
put-call parity (an arbitrage identity, not a model: it holds whatever anyone
thinks the FDA will do, so a gap above 3% of spot is a statement about the
DATA), no two-sided quote, and zero open interest — and where any fails the call
becomes PRICING UNRELIABLE rather than a rung on the ladder.

**And two thresholds that were round numbers became measured ones.** The
materiality cutoffs were 0.20 and 0.45, with nothing behind them, and one
printed a false sentence live: IONS at ±16% was told it was "smaller than the
15.2% median rejection", which it is not. Both are now multiples of the measured
median rejection — half it, and three times it. A threshold that cannot be
stated truthfully in the line it triggers is the wrong threshold.

## Day-71: P(CRL) — the number every breakeven was missing

`screen.py` could compute the honest half of the question and had to stop:
*"the put costs 13.6% of spot, so it breaks even if a rejection is ~89% likely."*
That sentence has no ending. A reader with no base rate cannot tell whether 89%
is absurd or routine.

**Why no free base rate existed.** The FDA does not publish rejections.
Drugs@FDA — the agency's own complete record, free, no key — was checked
directly: **192,337 approvals, 1,205 tentative approvals, zero rejections of any
kind**. A complete response letter is a private communication to the sponsor.
The only public trace is the sponsor disclosing it, which forces the numerator
to EDGAR — and forces the denominator there too, because a ratio whose top and
bottom come from different populations is not a rate.

### The measurement

Both legs from one harvest, one classifier, one window (2015–2026):

| | count |
|---|---|
| rejections announced | 101 |
| approvals announced | 330 |
| **decisions** | **431** |
| **RAW P(CRL)** | **23.4%**, 95% Wilson [19.7%, 27.7%] |

### The audit, and the wrong turn it caused

The approval leg was audited against Drugs@FDA: of 1,556 original NDA/BLA
approvals, 499 went to SEC registrants, and the harvest found **29 — 6%
capture.** That looked like a broken approval harvest, so the phrase lists were
tested for recall. The result inverted the diagnosis:

    2023, approvals   5 shipped phrases -> 337 filings
                      3 alternatives    -> 0 NEW between them
                      1 alternative     -> 5 NEW          (saturated)
    2023, rejections  4 shipped phrases -> 35 filings
                      the BARE phrase   -> 128, of which 93 NEW

So the CRL search looked badly narrow, and it was re-run across all twelve
years with the bare phrase. **It produced exactly the same verified events** —
2019:12, 2020:16, 2021:16, 2022:4, 2023:9, 2024:6, 2025:3, 2026:5, identical in
every year, 102 CRLs and 436 events either way.

Tripling search recall added nothing, because every filing that ANNOUNCES a
rejection uses one of those four constructions; the other 93 were risk factors,
historical references and MD&A discussion — exactly what `classify.py` exists to
reject. **The agreement between an independent narrow search and a strict
classifier over a threefold wider net is the best evidence yet that the
classifier does what it claims.**

Which resolves the audit: the missing approvals are not a search failure. They
are **materiality**. A large sponsor does not file an 8-K when one of fifty
products gets a routine approval — those decisions are absent from the
population by construction, not missing from the harvest.

### Two numbers that answer two different questions

| | |
|---|---|
| **23.4%** | P(rejection \| the decision was ANNOUNCED in an 8-K). Both legs complete. |
| **~1.7%** | approaches P(rejection \| ANY original FDA decision), including every routine approval nobody announced. A different, larger population. |

The second was called "CORRECTED", and the word was doing the arguing. It is the
**floor**; the raw ratio is the **ceiling**.

### What the screen uses

**21% [16%, 27%]** — the single-asset stratum, 42/202 decisions across 163
sponsors. A name with a PDUFA date worth screening is a name for which the
decision is material, so **both** its outcomes would be announced. That is the
only population whose two legs are captured symmetrically, which is the sole
property that makes a ratio mean anything.

Biased **upward** by one mechanism, stated in the output: a developer whose only
drug was rejected may never file again, so rejections are over-represented among
infrequent filers by construction.

### The payoff

The breakeven becomes a comparison, live on the open ZYME position:

> HEDGE — the put covering the date costs 13.6% of spot, so it pays for itself
> if a rejection is more than ~89% likely at the measured median.
> **Against the measured base rate of 16%–27% for single-asset sponsors
> (n=202), the premium only pays if this name is 3.3–5.7x more likely to be
> rejected than the average decision** — that is a claim about the DRUG, and it
> is the claim to argue.

Across the current screen: JAZZ 1.0–1.7x (at the base rate), CYTK 2.1–3.6x,
ZYME 3.3–5.7x, PRAX 3.6–6.2x.

**One bias caught in the audit itself.** The first version asked only "is this
sponsor an SEC registrant", and the approvals it reported as missed were Takeda,
Novartis, AstraZeneca and Sanofi — all registrants, none of which has ever filed
an 8-K, because a foreign private issuer reports on 20-F and 6-K. Counting them
would have understated capture, inflated the correction, and pushed P(CRL) down
for a reason having nothing to do with the FDA. A form code told them apart, the
same way it separated Canadian issuers on day-70.

## Day-72: a data bug that survived four days, and the control that caught it

`fetch_prices` asked Yahoo for `interval="1d"` over `range="max"`. **Yahoo does
not refuse that.** It silently returns weekly, monthly or even quarterly bars
depending on how long the ticker has existed:

    SRPT   median gap 31d      HRTX   median gap 92d      ZYME   median gap 7d

Every window in `validate_catalyst.py` counts BARS. So the "close t-2 → close
t+1" event window was **three months** on those names, and day-68's entire CRL
distribution was computed on them. Those numbers were in the morning report for
four days.

**What caught it was a positive control.** `validate_runup.py` could not detect
a planted +1% drift, which is only possible if the sample is far noisier than a
daily window can be. Every aggregate looked plausible throughout — the medians
were sane, the t-statistics were significant, nothing errored. Without the
control the run-up study would have shipped on twenty-month windows.

`fetch_prices` now caps the lookback at 3,600 days (the largest range that still
returns daily bars) and **asserts the interval that came back** rather than the
one requested: a series whose median gap exceeds 4 days is rejected and counted.
Six of 117 tickers were rejected on the re-run.

### Re-measured — same events, same classifier, verified daily bars

| | was (contaminated) | now (daily) |
|---|---|---|
| CRL median | −15.20% | **−8.97%** (mean −18.48%) |
| CRL p10 / worst | −57.53% / −83.61% | −60.38% / −74.95% |
| CRL vs random | −15.00pp, t=−3.41 | **−18.31pp, t=−5.64** |
| APPROVAL vs random | −0.54%, t=+0.98 | **+5.38pp, t=+2.42** |

**The rejection finding got stronger.** It was never in doubt and now separates
from random at t=−5.64 on 57 events.

**The approval claim did not survive.** This repo had been repeating that an
approval is "indistinguishable from a random window" and therefore already
priced. On daily bars the approval reaction is *positive*. It still does not
clear the pre-registered |t| ≥ 3, so nothing is adopted and no long is
recommended — but **"positive and below the bar" is a different sentence from
"no edge exists"**, and the report now says the true one in every place the old
one appeared.

The bar did not move because a number came close to it.

### Breakevens now run against the mean as well as the median

An option pays an **expectation**, so the breakeven that decides whether a
premium is worth paying belongs against the mean drawdown (−18.5%). Quoting only
the median (−9.0%) made every put look roughly twice as dear as its expectation
justifies. Both are printed, because the gap between them **is** the fat left
tail — 19% of rejections finish worse than −40%.

## Day-72: the pre-decision window — UNDERPOWERED, which is not a rejection

The tradeable week-to-month question is: take a position N days before a
scheduled decision, exit *before* the print. It never carries the binary, so
unlike everything else in this domain it can be sized.

Measured pooled (ex ante you do not know the outcome), XBI-relative so sector
beta is not mistaken for an edge, window ending two sessions early so the print
can never fall inside it:

| horizon | n | mean | median | win% | z | placebo z |
|---|---|---|---|---|---|---|
| 5d | 231 | +0.53% | −0.61% | 45% | 0.85 | −0.53 |
| 10d | 231 | +0.18% | −0.57% | 47% | 0.18 | 2.05 |
| 20d | 231 | +2.51% | −0.94% | 45% | 1.40 | 1.91 |
| 40d | 230 | +3.23% | +0.13% | 50% | 1.51 | 1.30 |

Positive at every horizon, clearing nothing. **The reason is power, not
absence:**

    standard error at 20d       1.76pp
    minimum detectable effect   6.16pp    (bar |z| >= 3.5)

This sample can only resolve a drift larger than 6.2pp over 20 sessions. Any
run-up worth trading is smaller than that and therefore invisible to it, so "no
effect found" would be a claim the data cannot support. Rule 4 exists for this
case — day-46's bar was unsatisfiable and the honest output was to say so.

**The control had to be fixed before it could say this.** The first version
added the planted edge to every observation and reported the z of the *shifted*
sample — (base mean + edge)/sd rather than edge/sd — so with a base drift of
+2.5% it printed z=1.92 for a 1% plant. That is a number about the sample's own
drift, not about detectability. Power now derives from dispersion alone.

What fixes it is events, not modelling: the harvest grows by roughly 35
decisions a year.

## Day-72: what the intraday pair costs to express

`adapters.py` says in its own header that bid/ask is not exposed by any adapter
here, so the one term that actually determines the intraday book's result had
never appeared in the report. That matters because a coin flip is not a
zero-expectation trade:

    E[net] = (hit rate - 1/2) x 2 x E|move| - spread - fees
             \_______________________/
                    measured at ~0

With the directional term at zero across 36 rejections and a 34/70 record, the
spread is not a cost on top of the edge — **it is the outcome**. Live on liquid
TSX names the answer is smaller than expected and worth knowing either way:
ABX.TO 8bps, RY.TO 2bps, ENB.TO 1bp against a typical 0.97% move. Directional
term −3bps per leg, spread term −4bps, both certain, both previously invisible.

An unknown spread reports as UNKNOWN, never zero — zero is the most expensive
wrong answer available, because it says the trade is free. And this does **not**
re-rank the picks: the engine's selection rule produced the 70-leg record, and
silently changing it would break the only track record this repo has while
pretending to improve it.

## Day-77: REJECTION #37 — the approval leg, pre-registered and refused

The day-74 base-rate correction flipped the sign of the only tradeable
proposition in this repo, and the whole sign rested on one number that had never
passed: the approval reaction at **t = +2.42 on n = 173**, out of 977 approvals
in the harvest. The bar was **pre-registered and committed before the sample was
built** (`PREREGISTER_day77.md`).

**What was fixed to expand the sample.** The price fetch took a DURATION, which
Yahoo answers by choosing an interval to suit — and "10 years back from today"
silently dropped every 2015 and most 2016 event. An explicit `period1/period2`
pair returns true daily bars for any bounded window, verified back to
2015-01-02. Usable event windows went **230 → 605**.

| | before (n=173) | after (n=534) |
|---|---|---|
| approval vs random | +5.38pp, t=+2.42 | **+2.63pp, t=+2.61** |
| CRL vs random | −18.31pp, t=−5.64 | **−20.60pp, t=−6.83** (n=71) |

**This is a rejection, not an underpowered result.** Tripling n would have
carried a real +5.38pp effect to t ≈ 4.3. Instead **the effect halved and t
barely moved** — the signature of a small-sample overestimate regressing toward
a smaller truth. And the sample was powered to find it: SE 1.01pp, minimum
detectable effect 3.02pp, against a claimed 5.38pp. The pre-registration stated
in advance that a t between 2 and 3 on a larger sample counts as a rejection.

**What it costs.** There is no systematic long-into-decision trade:

    E[hold a long through the print]
      approval leg unestablished (=0)   -1.72% .. -3.22% per event
      crediting the unconfirmed +2.92%  -0.77% .. +0.95%

The reverse trade is the mirror and straddles zero the same way. **Neither
direction has an edge.**

**What survives, and it got stronger.** The rejection leg: a CRL is violent and
unpriced, now **t = −6.83** on 71 events, median −11.79%, mean −20.30%, 45%
worse than −18%, 24% worse than −40%. That is the only durable measurement in
this repo. At a base rate of 8.5–15.9% it does not produce a directional equity
edge on its own — it prices insurance, and the market charges 2.7–5.7× the
measured fair value for that insurance.

**The decision this forces**, taken from the pre-registered action table: stop
trading this system. It becomes research and monitoring. The intraday engine is
36 rejections and 311 live picks at 49%; the catalyst engine now has its own
rejection on the only leg that could have made a long pay.

## Day-78: two tests of a different kind — one rejected by a hair, one unanswerable

Both **pre-registered and committed before any result was computed**
(`PREREGISTER_day78.md`). Neither tests price predicting price, which is what
all 37 previous rejections were.

### TEST B — is P(CRL) conditional on the sponsor's own prior rejections?

| stratum | P(CRL) | 95% Wilson | n |
|---|---|---|---|
| no prior CRL for this sponsor | 9.9% | [8.0%, 12.2%] | 817 |
| **has a prior CRL** | **16.0%** | [11.9%, 21.2%] | 238 |
| has two or more | 17.1% | [10.3%, 27.1%] | 76 |

**REJECTED — the intervals overlap by 0.3pp.** The pre-registered bar was
non-overlapping Wilson intervals and it is not being moved after the fact.

For transparency: the standard two-proportion test gives **z = +2.60,
p = 0.0094**, which conventional practice would call significant. I chose a
stricter bar than convention and I am holding it. Recorded as a **re-test
candidate**, not an adoption — and the bias runs *against* the finding, since a
sponsor rejected once may never file again, so "has a prior CRL" over-selects
survivors and pushes the conditional rate DOWN.

The report now states this was tested and did not clear, so the question is
closed rather than quietly re-asked.

### TEST A — does insider open-market buying precede FDA outcomes?

Built `build_insider.py` on the SEC's bulk Insider Transactions datasets:
**373,229 code-P open-market purchases across 8,572 issuers, 2014–2026Q2**,
forty-seven quarterly ZIPs instead of ten thousand XML round trips. Code A
(awards at $0), M (option exercises), F (tax withholding) and S (sales) are all
discarded.

**The look-ahead trap is closed by construction.** A Form 4 is filed up to two
business days after the trade, so `TRANS_DATE` is not public when it happens.
Every purchase is keyed on **FILING_DATE**. Using the transaction date would
credit a trader with information nobody had, and is why much published insider
research fails to replicate.

    605 events with a usable price window
      115 (19%) had code-P buying FILED in the prior 90 days

    A1 outcome  AUC 0.5238   z=+0.66     (bar |z| >= 3.3)
    A2 return   +2.63pp      z=+1.12     (bar |z| >= 3.3)

**UNDERPOWERED — and that is not a rejection.** SE 2.36pp, minimum detectable
effect **7.78pp**. The observed +2.63pp is well inside the noise, so "no effect"
would be a claim the data cannot support.

**But the placebo is the more useful result.** The same 90-day lookback ending
at a *random* date produced **+2.01pp (z=+1.03)** — 76% of the apparent effect.
Whatever is there is a company-TYPE effect (the kind of company whose insiders
buy at all) rather than a TIMING effect (buying because a decision is coming).
That is worth more than the headline: it says raising n would likely be chasing
a confound.

**The confound named in advance did not appear.** Insiders bought into strength,
not weakness — prior 20d return +3.07% with buying versus +1.50% without. So
this is not a reversal signal wearing an insider costume; it simply is not a
signal at this sample size.

### What shipped

Nothing to the trading logic. `data/insider_buys.csv.gz` (6MB compressed) and
the harness are committed so the test is re-runnable when the harvest grows,
and `screen.py` now records that the prior-CRL conditioning was tested and did
not clear.

## Day-81: a diagnostic that could not see its own case, and the constant it exposed

Two robustness items were requested — a second fair-value estimator and a
plausibility gate. Both were built. Both immediately found that something
already shipping was wrong, which is the only real evidence that a check works.

### The second estimator caught nothing, because it was aimed wrong

Day-80 added a lognormal cross-check to `fairvalue.py` whose warning read *"the
empirical figure resamples this name's own history, so a single past crash
inflates it"*. It fired on no live name, and that silence was reported as
reassurance.

Planted controls (900 days, σ=0.8%/day, each defect isolated) say otherwise:

| control                      | gap | mean window return | σ drop when trimmed |
|------------------------------|-----|--------------------|---------------------|
| clean                        |  4% | +0.05%             |  3%                 |
| drift only (−40% over path)  | 43% | −1.13%             |  3%                 |
| one −55% day, drift removed  | 44% | +0.04%             | 71%                 |
| that crash **with** its level shift | **14%** | −2.84%   | 71%                 |

Three findings, none of them the one claimed:

1. **The direction was backwards.** A single crash inflates the LOGNORMAL, not
   the empirical estimate. σ is a second moment and one day dominates it;
   `E[max(0,-r)]` is a first moment where one day in 900 carries ~1/900 weight.
2. **The gap measures drift, not tails** — and not only drift. *Both*
   mechanisms open a gap, and **they subtract**. A name carrying both defects
   reads at 14%, under the 0.40 bar, while either alone reads at ~43%. **The
   worst case looked like the cleanest.** Gap magnitude is not a diagnostic.
3. **`trimmed_fv` tested the robust leg.** It winsorised the empirical
   estimator's window returns — 1% movement on the clean control and 1% on the
   crash control. That is why no live name tripped it.

Rebuilt: `window_drift` and `vol_outlier` measure the two mechanisms
separately, each with a planted positive control that must fire on its own
defect and stay quiet on the others (rule 4). Where both fire, both are named —
reporting only the first match would narrow the finding silently, the same
fault one layer down. On the live board **four of five names now carry a flag
where day-80 flagged none**, and PRAX's 0.55x "cheap" reading is explained by
its *lognormal* leg, not by the outlier story I gave in the report.

### The plausibility gate found a shipping arithmetic defect on its first run

`sanity.py` asserts bounds that no correct number can violate — a put cannot
exceed spot, a probability cannot leave [0,1], a rejection drawdown cannot be
positive, daily bars cannot be a week apart. Bounds are calibrated, not
guessed: the largest gap in real daily bars is 4 days (July 4 weekend, across
seven 3,080-bar series) and weekly bars are 7, so the bar sits at 6.

**Honest score against the five defects that actually shipped: one of five.**
Only day-72's monthly bars trip it. day-74 (334 approvals where the truth was
977), day-75 (a settled binary priced), day-79 (a 2.5x undercount) are all
perfectly possible numbers, and day-81's mislabelled warning is not a number.
It is a floor, not a net, and `tests/test_sanity.py` asserts the four misses
stay misses so the file can never be quietly read as more.

On its first run it raised on live output: **`fairvalue.fair_put` took its point
estimate from the volatility TERCILE (1.54/2.29/2.91) and its interval from the
OVERALL sample [2.07, 2.86]**, so for every low-vol name the printed fair value
fell outside its own printed range. Two populations in one line — rule 7, in
arithmetic. Shipping since day-79.

### Re-measuring it removed the tercile ladder entirely — REJECTION #38

The day-79 constants had no committed script, so they could not be re-derived.
`validate_eventmult.py` now reproduces them, resampling **names** rather than
events (605 decisions come from 184 names; one biotech contributes many
decisions from one volatility regime).

The headline replicates: **2.45x, 95% [1.95x, 3.00x]** against day-79's 2.46x.
The structure does not:

| tercile | day-79 | re-measured | 95% |
|---------|--------|-------------|-----|
| low     | 1.54x  | **2.09x**   | [1.49, 2.93] |
| mid     | 2.29x  | **2.09x**   | [1.28, 3.18] |
| high    | 2.91x  | **2.82x**   | [2.12, 3.68] |

Low and mid are identical. Tested directly rather than by eye — overlapping
marginal intervals prove nothing, so the *difference* was bootstrapped:

    high - low   +0.76x   95% [-0.34, +1.84]
    mid  - low   -0.01x   95% [-1.19, +1.25]

Both intervals are **wider than the effect**: the sample cannot resolve a
tercile gap below ~1.09x. By rule 10 that is **UNDERPOWERED, not refuted** —
the volatility effect day-79 claimed may well be real. But pricing off a
three-rung ladder this data cannot distinguish is not defensible, and it never
faced a direct test before being adopted.

**Shipped:** one multiplier, 2.45x, with its own matching interval. The name's
tercile is still printed beside it as an open question, explicitly not priced
in. That fixes the point-outside-interval defect at its root.

### What shipped

`sanity.py` + `validate_eventmult.py` + `fairvalue.py` rebuilt diagnostics,
`PREREGISTER_day81.md` (bars fixed from controls before any live name was run;
one rationale amendment recorded in place, no bar moved), `data/eventmult.json`,
34 new tests (553 → 587). The gate runs on every `brief.py` — constants checked
before rendering, prices checked before any horizon counts bars, and a name
that fails it now says so and withholds its fair value instead of printing one.

## Day-81 (cont.): provenance for every number, and the contradiction it found

Five shipping constants were retracted in eleven days and in every case a human
re-deriving them by hand was what caught it. `constants.py` registers all 38
published numbers — **1 cited, 14 design, 23 measured** — and makes three things
checkable that were previously only visible in a diff.

**Provenance.** Each number is MEASURED (a named script re-derives it), CITED
(from outside this repo, with no control here), or DESIGN (a chosen threshold).
One measured number, `fairvalue.N_RANDOM`, still has no script and is named as
such on every run. The distinction matters because day-79's constants sat
unprovenanced for two days and could not be checked until a script was written.

**Drift.** Values are snapshotted to `data/constants.json` and any change prints
with old → new, plus the command that re-derives it.

**Tension — and this is what it found.** Two constants in this report describe
P(rejection) and they disagree:

    catalyst.BASE_RATE_FIRST_CYCLE = 0.70   CITED, implies P(CRL) = 30%
    baserate (day-71)                       MEASURED 11.7%, 95% [8.5%, 15.9%]

The measured interval **excludes** the cited value. Both ship: `catalyst.assess`
anchors its guardrails on the first, every breakeven in the screen divides by
the second. So the report has been telling the reader a rejection is 30% likely
in one paragraph and 8–16% likely in the next, since day-54.

**Neither is declared wrong**, because they are not the same population and the
registry's job is to surface the conflict rather than settle it. The measured
leg counts only decisions announced in an 8-K, and companies publicise
approvals far more readily than rejections — so its CRL numerator is the leg
more likely to be undercounted, biasing it **down**, toward the cited figure
being the more honest one for a PDUFA date. The harvest also includes
supplements, which approve at higher rates, biasing it down a second time.
Against that, the measured leg has a positive control and a published interval
and the cited one has neither, here. What is not defensible is using both in
one argument (rule 8).

### A cache collision worth recording

Testing drift end-to-end, the registry reported a value the source file did not
contain. CPython invalidates bytecode on the source's mtime **truncated to the
second** plus its size, and rewriting `2.45` → `1.54` is the same number of
characters inside the same second — so `import` served a stale `.pyc`. Harmless
in a morning run where nothing has been edited for hours, but a false "nothing
moved" is the exact failure this file exists to prevent, so `live()` now reads
each constant a second time from the source text via `ast` and reports any
disagreement. Computed constants parse to None and are simply not double-read;
a check that always fires is one nobody reads.

**Shipped:** `constants.py`, `data/constants.json`, 18 tests (587 → 605), wired
into `brief.py` after the report so a changed basis is read next to the
conclusions it changed.

## Day-81 (cont.): the report gets a front page — 461 lines to 44

The full brief had grown to 461 lines with **77% of them in one section**. A
page that long is not read every morning; it is skimmed once and then trusted,
which is the worst of both — every caveat present, none of them seen. That is
how the day-79 fair-value defect survived two weeks of daily reading.

`view.py` draws the same run in ~44 lines, ordered by decision rather than by
topic: BOOK / DO TODAY / COMING UP / WATCH / RECORD. It is now the default;
`--full` prints the long page.

**It recomputes nothing.** `brief.build()` fills a digest as it goes and the
view draws from it. A summary built from a second pass is a second opinion, and
a top line that contradicts the detail below it is worse than no top line. The
full page is still BUILT either way, because it is what publishes the day's
permanent record via `r945.publish()` — a short view that skipped the
computation would silently stop the ledger accruing.

**The rule the tests enforce: concision may drop DETAIL, never DOUBT.** A fair
value flagged unreliable in the long page is marked `~` here, an unmarkable
position is still EXCLUDED and says why, and the live 45% record prints beside
the advice as always. What concision *is* allowed to do is collapse five
identical warnings into one line — five copies of the same caveat push the
things that differ off the screen, which is the failure being fixed.

**Two data gaps the short page immediately made visible**, both invisible in
the long one:

- **Bristol Myers Squibb's 2027-05-13 PDUFA resolves to no ticker at all**, so
  it cannot be priced by anything. The long page rendered it as a blank column,
  which reads like a name whose quote failed — a different and much smaller
  problem. Now reported as unpriceable, by filer name.
- 4 of 13 calendar names have no usable option quote, named rather than counted.

**Timing.** The only 9:46-dependent section is the intraday pair — the engine
with no measured edge. Positions, catalysts, calendar, fair value and the record
are all time-independent, so the report can be run at any hour and only the pair
block will say "too early".

**Shipped:** `view.py`, `brief.py --full`, a digest hook through `build()`,
16 tests (605 -> 622).

## Day-81 (cont.): the research output reaches the front page

The short view shipped with the catalyst list in DATE order — the five nearest
FDA decisions. That is the order the FDA's diary has, not the order a decision
has, and it hid the screen's entire output: **PRAX, the cheapest name on the
board at 0.44x quoted-to-fair, sits 118 days out and was the sixth row.** It
never appeared at all. The ranking existed and was correct; it was reachable
only via `--full`.

`OPPORTUNITIES` now leads with the ranking, cheapest first across all horizons,
each row carrying the ratio, the quote, the measured fair value and a verdict
tag. The date-ordered calendar is kept only as a fallback when nothing ranks.

**Two presentation defects fixed at the same time.** Verdicts truncated
mid-word ("DOWNSIDE IS THE CHEAPER SI") because the screen's sentences were
written to be read in a paragraph — each now has a short tag and keeps its full
sentence in `--full`, with unmapped verdicts falling through rather than
blanking. And the "why is this marked ~" hint pointed at COGT, a name EXCLUDED
from the ranking and therefore never marked; it now names a name the reader can
actually see.

**A duplicated 12-second download.** `_watch`/`_record` called
`ledger._tides_for_report()` — 120 days of daily bars for every ticker in
`universe_prints` — which `render_record` had already computed in the same run.
Two renderings, one computation was the stated rule and this broke it. The
tides now travel in the digest: the view test suite went 91s → 4.2s and every
morning run saves the same duplicate fetch.

**Width and length are now asserted, not eyeballed.** Overflow crept back three
times, so `test_no_line_overflows_the_column` and `test_a_busy_morning_still_
fits_on_one_screen` run against a deliberately busy digest — a position, an
exit, a pair, and a full ranking. Live output: 50 lines, zero over-width.

**Shipped:** `_opportunities` in `view.py`, verdict tags, tides through the
digest, 13 tests (629 -> 642).

## Day-81 (cont.): the record was a session stale, and said nothing about it

Running the report on a NEW trading day exposed two defects, both mine from the
day before.

**1. The `shares` column was declared but never written.** Day-81 added it to
`ledger.FIELDS` and set it in `r945`'s `lrows`, but `append_picks` builds its
row dict key by key and silently dropped it — the CSV header gained a column
that was never once populated, so the very next board published without it and
still restores at ±1 share. The test that was meant to cover this asserted
`"shares" in ledger.FIELDS`, which is the SCHEMA, not the behaviour. It now
round-trips a real value through a write and a read.

**2. The hit rate printed beside the advice was a session out of date.** The
page said "score after close: `python ledger.py --score`" and nobody ran it, so
on 2026-09-01 it printed 38/85 next to the day's picks while four legs from
08-31 sat unscored — and nothing on the page indicated the number was stale.
This is exactly the day-80 finding about the catalyst ledger, which carried the
identical instruction and reached 9 events logged and 0 scored: **a record that
requires a human to remember is not a record.**

`ledger.autoscore` is extracted from `main` and now runs every morning before
the record prints. Both day-24 guards still apply inside `score_rows` — an open
session is HELD BACK rather than stamped with a live mid-session price, and
closes are looked up by the row's own date. First run: **11 legs scored, 14
held back** (today's, correctly), and the record moved 38/85 → 40/89. A scoring
failure now says the record is STALE rather than printing an old number quietly.

**Shipped:** `ledger.autoscore`, the `shares` write, 5 tests (642 -> 646).

## Day-81 (cont.): the board drifted between re-reads, names and all

Yesterday's fix restored published SHARE COUNTS onto a re-read. It fixed the
sizes and left the names wrong.

Run at 10:40 on 2026-09-02 the engine published **SHORT CP.TO**. Run again at
10:43 it picked **SHORT RY.TO**, and the page printed RY.TO — a name the ledger
will never score, because the board is written once and RY.TO is not on it. The
restore noticed only that it could not size RY.TO; it never asked why RY.TO was
there at all.

**The 9:46 board IS the instruction.** Names, sides and sizes are all fixed at
publish. A later run reads it back; it does not get a vote. `_restore_published`
now rebuilds the whole pair structure from the ledger rows and discards the
fresh computation for display. A side absent from the board no longer acquires
one on a re-read.

**A new `leg` column** distinguishes the primary pick from the second leg that
splits the same half — without it a re-read can tell that both names were on
the board but not which one it instructed. Boards published before today infer
it from ledger order (which was publish order, top-ranked first) and say so.

**The `--book` renderer degrades honestly.** It read `last`, `r0` and `gap` —
live intraday measurements the ledger does not store. Filling them from the
fresh run would print today's tape beside yesterday's instruction, which is the
two-sources mixing this restore exists to stop, so a restored board prints
"intraday diagnostics not stored — re-read, not a fresh computation".

### Two smaller live findings the same run produced

**A book with no markable leg read as +0.00% on $0.** `mark_book` totals only
what it could price, so a fully-unmarked book returns zero — which at a glance
is a flat, fully-priced book rather than one where nothing is known. It now
reads UNPRICED and says "the total is unknown, not zero". The first attempt at
this split the header into two branches and left the position rows inside only
one, so an unpriced book listed no positions at all; the failure hid the thing
it was reporting. Tested both ways.

**One transient quote error blanked the whole book.** ZYME failed with a
RuntimeError and quoted fine seconds later. Failing closed is right; failing
closed on a blip a one-second retry survives is noise, and noise is what
teaches a reader to ignore the warning. One retry, then it still fails and
still says so.

**Shipped:** the pair rebuild, `ledger.leg`, the UNPRICED headline, a quote
retry, 10 tests (646 -> 651).

## Day-82: does the SELECTION rule earn its place? — UNDERPOWERED (not a rejection)

Pre-registered in `PREREGISTER_day82.md` **before any result was computed**,
including the expectation that it would come back underpowered.

### The experiment was already in the ledger

`r945.publish` has been recording every candidate that qualified at the bar,
not only the two it traded:

    role="pair"    the legs the density rule SELECTED, and traded
    role="board"   qualified the same day, same universe, same bar, NOT selected

Both are scored against the same 15:59 close, which makes the board rows a
ready-made counterfactual — *a qualifying name we did not pick* — and turns
38 sessions of accrued record into an out-of-sample test of the SELECTION RULE
rather than of the model. No new data was needed.

**Sample: 93 selected legs vs 215 qualified-but-not-selected, 38 sessions,
21 names, 2026-07-08 to 2026-09-01.**

### Result

| | selected (density) | not selected |
|---|---:|---:|
| decisive hit rate | **44.7%** | **53.1%** |
| mean capture/leg | **−0.108%** | **+0.088%** |

    hit rate      −8.28pp   95% [−21.95, +5.88]   placebo [−14.77, +7.08]
    mean capture  −0.20%    95% [−0.52, +0.11]    placebo [−0.35, +0.13]

**VERDICT: UNDERPOWERED.** Both point estimates run against density selection
— the legs the rule chose did worse than the ones it passed over — but both
intervals cover zero and **both observed values sit inside the placebo
distribution**, so a random split of the same legs reproduces the effect. The
positive control settles it: a planted 10pp lift registers at only **z=1.4**,
so this harness cannot see an effect two and a half times larger than the one
observed.

Reporting this as a refutation of density selection would violate rule 10, and
it is not one. It is a bound.

**When it stops being a bound: ~182 sessions.** z grows as √n, so reaching
|t| ≥ 3 at this effect size needs about 4.8× the current sample. At one session
a day that is roughly seven more months, and the question answers itself
without anyone doing anything except letting the ledger accrue.

### Context that makes the bound worth having

Density selection was adopted on day-9 from a walk-forward replay scoring
**68.0% discovery / 69.2% confirm** (n=89, p≈0.0007). The live record on the
same rule is **47%**. This study cannot say the day-9 result was wrong; it can
say that after 38 sessions there is no visible trace of a 20-point advantage,
and it can say exactly how long until that is answerable.

### Two methodological corrections made during the study

**The placebo was shuffling the wrong thing.** It permuted the pair/board label
across the pooled sample, but `r945` assigns it *within* each session — exactly
k legs out of that day's qualifiers. Pooling mixes sessions, destroys the
within-day structure and returns an interval that is too narrow, which would
make the observed difference look more surprising than it is. Shuffling within
session widened it from [−10.98, +10.90] to [−14.77, +7.08].

**A test asserted a null interval must cover zero, and failed on seed 4.** That
is not a harness bug — a 95% interval is *supposed* to miss 5% of the time — so
the test was flaky by construction and the obvious "fix" of changing the seed
would have buried the fact that nobody had measured the rate. Replaced with a
calibration check across 40 independent nulls: **5% false positives, exactly
nominal**, difference centred at +0.003.

### What shipped

`validate_selection.py` and 15 tests. **No change to the selection rule.** H2 —
what selection costs in spread — is not measurable on this sample at all,
because spreads were never stored before day-82; it is now accruing
prospectively via `ledger.spread_bps` and will be answerable later.

## Day-82: "half the calendar is unpriceable" was the market being shut

§5b said fix coverage first — roughly half the scheduled decisions were coming
back unpriceable. Diagnosing it per name reversed the conclusion.

**Every chain fetch succeeded.** Every in-horizon name returned a spot, a set
of expiries and a put chain. Nothing failed to fetch. What failed was the
quality checks, and the failure was universal:

    IONS  19d  OK spot=61.33  put=5.2   | FAILS: px_source=last, oi=0
    CYTK  72d  OK spot=71.93  put=5.4   | FAILS: px_source=last, oi=0
    PRAX 115d  OK spot=357.50 put=52.5  | FAILS: px_source=last, parity, oi=0

Seven of seven with no two-sided quote and zero open interest, including large
liquid biotechs. That is not a market fact, so the obvious next step was a
control — price something whose liquidity is not in question:

    SPY   ATM put  bid=0.0  ask=0.0  openInterest=0  volume=7488
    AAPL  ATM put  bid=0.0  ask=0.0  openInterest=0  volume=2139

**SPY options are the most liquid contracts in existence.** A zero two-sided
quote on SPY is a fact about the FEED, not about SPY: Yahoo's free chain zeroes
bid/ask and open interest outside market hours, and the run was at 06:47 ET.
Volume comes through, which is why the outage is invisible without a control.

So the report had been telling the portfolio manager that half the calendar was
unpriceable — a sentence that reads as *these companies are illiquid* — when
what had happened was that the options market was closed. During market hours
the same names price normally, which the 10:40 and 10:49 runs on 2026-09-02
confirm.

### What shipped

`quotes.py`: one option path with **typed** failure reasons (NO_TICKER,
CHAIN_ERROR, NO_SPOT, NO_EXPIRIES, NO_EXPIRY_AFTER_EVENT, NO_PUTS,
NO_TWO_SIDED, ZERO_OI, PARITY_BREAK, FEED_CLOSED) replacing a single
`except Exception` that recorded the exception CLASS, plus silent paths that
recorded nothing at all.

The design idea is the one this repo already applies to statistics: **a
positive control.** `feed_is_live()` prices SPY first, and reasons are split
into those that are properties of the NAME and those that are properties of the
FEED. `NO_TWO_SIDED` and `ZERO_OI` are deliberately ambiguous in isolation —
they mean opposite things depending on the control, which is exactly why the
control exists.

The report now prints **one line** for an outage instead of a roster of
companies, and groups genuine failures by their typed cause so the reader can
act on them. No fallback pricing, no synthetic bid/ask, no stale quote carried
forward: when the feed is shut the answer is that it is shut.

**Coverage during market hours was never the problem it appeared to be.** The
remaining genuine gaps are one decision with no resolvable ticker (Bristol
Myers Squibb, 2027-05-13) and names outside the pricing horizon.

## Day-82: the cost line has been dividing by the wrong number

§7 requires `python constants.py` to report no unprovenanced measured values.
Two remained. Writing the missing re-derivation script for one of them found a
number that had been wrong in the report for twelve days.

`cost.TYPICAL_MOVE_PCT = 0.97` is MEASURED — day-70 put |r1| on this universe
at 0.97% (non-event) and 1.11% (after a filing), taking the lower so the drag
is never flattered — but **no script re-derived it**, so it sat in the registry
as a claim wearing a measurement's clothes. It is the denominator of every
"spread is N% of the typical move" line the report prints.

`validate_typicalmove.py` re-derives it from the ledger over the same window
and universe: **median |capture| 0.69%, 95% [0.58%, 0.79%], 343 legs across 39
sessions, session-clustered.** The interval **excludes** the shipped 0.97%.

**The direction is not self-flattering, which is why it survived.** Too large a
denominator makes the spread look like a *smaller* share of a normal day's move
than it is, so the report has been **understating** what trading costs. A
spread quoted as "5% of the typical move" is nearer 7%.

**It was not corrected.** Day-70's sample cannot be reconstructed and the two
figures may describe different populations — the same rule-7 trap as
P(rejection). Changing a measured constant on the strength of an unregistered
study is what this machinery exists to prevent, so it is registered as a second
standing TENSION and prints on every run until someone decides it deliberately.

The re-derivation script is also forbidden from assigning the constant it
checks, asserted by a test: a checker that edits its own subject is not a check.

### Also cleaned up under §2

**A measured value existed in two places.** `screen._CRL = 11.79` was a literal
copy of `catalyst.CRL_MEDIAN = -11.79`, and that median has already been
re-measured twice (-15.20 → -8.97 → -11.79). Each time, the copy would have
kept a retired number while the file's own docstring claimed the thresholds
were anchored to the measurement precisely so that correcting it corrects them.
Now derived, with a positive control asserting the thresholds move when the
median moves.

**The advisory-committee base rates were unregistered.** `EXT_POSITIVE_APPROVED
= 0.97` and `EXT_NEGATIVE_REJECTED = 0.67` are printed beside FDA outcomes and
had no provenance entry, so a reader could take them as measured here. Both are
now CITED, with the source named.

**A mechanical literal scan does not work and is not kept.** Matching
constants by VALUE flagged every `2`, `6` and `0.1` in the repo — the same
false-positive failure as the earlier `get` matcher, and a check that fires on
correct code is one that gets deleted rather than obeyed. Only distinctive
values were pursued, by hand.

## Day-82: the P(rejection) contradiction — BLOCKED, and the blocker is named

§5b asked for the announcement bias to be measured directly: do companies
announce CRLs less readily than approvals? If they do, the measured 11.7%
understates the truth and the cited 30% is the better number for a PDUFA date.

**It cannot be measured with the data here, and the reason is rule 7 sitting
inside the capture audit rather than in the headline ratio.**

`baserate.capture_rate` reports that the harvest finds 50 of 499 FDA approvals
granted to public domestic filers — a 10% capture rate, from which
`corrected()` derives a FLOOR of P(CRL) = 1.26%. That 10% is not an
announcement rate, because the two sides count different events:

| | counts |
|---|---|
| numerator (harvest) | every 8-K announcing an FDA approval — label expansions, supplemental indications, device clearances, and approvals of a **partner's** application |
| denominator (Drugs@FDA) | **original** approvals only (AP/TA on ORIG submissions) |

A company announcing a label expansion produces a numerator event with no
denominator counterpart. The rate across that mismatch measures the difference
between two event classes, not how readily anyone announces anything, so **the
floor it produces is not a lower bound on anything.**

### I diagnosed this wrongly first, and the correction matters

The first pass tested sponsor names with raw string equality and found **11 of
334** matching, which looked like a broken join and would have been reported as
one. That is not what the code does. Measured with `same_company`, the matcher
the audit actually uses, **156 of 334 (47%)** match — and it joins
`AADI BIOSCIENCE, INC.` to `AADI` and `60 DEGREES PHARMACEUTICALS, INC.` to
`60 DEGREES PHARMS` while correctly refusing `GENENTECH` / `GENELABS`.

A second suspicion — that Drugs@FDA's sponsor list is polluted by industrial
gas registrants like `A G L WELDING SUPPLY CO INC` — was measured rather than
asserted: **12 sponsors, 16 of 1,556 records, 1%.** Immaterial. Both wrong
guesses were cheap to check and expensive to publish.

### Where this leaves the contradiction

**Open, and honestly so.** The raw measured rate stands: 11.7% [8.5%, 15.9%]
over 291 single-asset decisions, both legs from one harvest, one classifier and
one window. `summary()` returns that stratum, so **the broken floor never
reached the morning report** — which was already correct, not luck.

What would unblock it is a ground-truth set of DECISIONS including rejections.
FDA did not publish complete response letters historically, which is the whole
reason this repo had to infer P(CRL) from announcements in the first place.
Until such a set exists, the two numbers describe different populations and the
report must keep saying so rather than reconciling them.

`corrected()` is retained — deleting it would delete the record of why the
correction was attempted — with a docstring that now states what it is worth.

## Day-83b: post-announcement drift in SHARES — UNDERPOWERED both arms

The portfolio manager trades shares only, long or short, on a morning
recommendation with a hold duration. That withdrew the option expression
(`PREREGISTER_day83.md`) **unrun**, and forced the question back onto ground
day-51 had already rejected (#32).

Day-51's closing sentence is what made a re-ask legitimate:

> *A duration field cannot manufacture event awareness out of OHLCV bars.*

The engine now has the event feed it lacked then. With 1,097 dated FDA
decisions carrying a known OUTCOME, **the duration is a fact** (it runs from
the announcement) and **the direction is known at entry** (the 8-K has already
said approved or rejected). This is not predicting a binary — the binary has
resolved and is public. It is the classic post-announcement drift question,
and it is expressible in shares.

**Disclosed before running:** `validate_catalyst` has computed an `after5`
column since day-68, so this is a re-analysis of an existing column, not a
virgin test. It had never been written up and no result from it had been
quoted, but any adoption would have been provisional pending prospective
confirmation.

### Result — 611 usable events, 195 names, 5 sessions from the first tradable close

| arm | n | raw | vs market | verdict |
|---|---:|---:|---:|---|
| **CRL** | 72 | −0.60% | **−0.84%** [−3.04, +1.46] | UNDERPOWERED, MDE 3.44% |
| **APPROVAL** | 539 | −0.09% | **−0.41%** [−1.32, +0.51] | UNDERPOWERED, MDE 1.40% |

**Both observed values sit INSIDE their placebo** (random dates, same names:
CRL [−2.69, +4.46]; approval [−0.94, +3.50]). The positive controls settle it:
a planted **1.00%** drift registers at only **z=0.8** on the CRL arm and
**z=2.1** on the approval arm — neither reaches the bar.

**How much data would settle it:** ~908 CRL events (have 72) and ~1,076
approval events (have 539). The repo holds 120 CRLs in total, so the rejection
arm needs roughly **12x more decisions than exist in the harvest**. That arm is
not going to become answerable by waiting.

Net of a 0.10% round-trip share spread both arms are negative (−0.94% and
−0.51%), and neither is distinguishable from zero.

**VERDICT: UNDERPOWERED, not refuted (rule 10).** There is no visible
post-announcement drift to trade in either direction, and the data cannot
resolve one below 1.4% (approvals) or 3.4% (rejections). **Nothing adopted; the
morning report continues to make no multi-day directional recommendation.**

### A defect found while proving the report never errors

The dead-network scenario test regressed. Under a total feed outage
`hist_rows` is empty, so `pd.DataFrame([])` has no columns and
`train.groupby("t")` raised **`KeyError: 't'`** — propagating straight out of
`r945.run` and out of `brief.build`, which is the one path the report is
guaranteed never to show the portfolio manager. A total fetch failure is a
**coverage failure**, a thing this engine already knows how to report, not an
exception. Now fails closed with a stated reason that distinguishes a data
outage from a judgement about the names.

## Day-84: short interest as a selection input — NOT ADOPTED, and one arm is a real bound

Pre-registered in `PREREGISTER_day84.md`, bar fixed before any outcome was
computed: **|t| >= 3 on tide-relative capture AND the same sign in all four
quarters**, session-clustered, outside a placebo band. Both, not either.

This came from the direct question "what else would raise the hit rate". The
answer day-43 had already established is that `r0`/`gap`/`vp` are exhausted —
gradient boosting reached AUC 0.5022 on 122,234 rows — so accuracy can only
come from **new information**, and day-43's own shortlist named short interest
as one of four candidates never acquired. This is that acquisition.

### The feed, and why the US line is the right line HERE

FINRA's consolidated bi-weekly short interest: free, unauthenticated, 22,482
symbols per file, history to 2017-12-29. **4,134 reports across the 20 twins.**

The live book trades `.TO` and for the live book this is a proxy — that is
disclosed in the pre-registration and does not go away. But the study panel is
`validate_twins`, which prices the **US dual-listing**, so within the study the
short position and the return come from the same listing line (rule 7). CIRO's
Canadian report — the correct line, which would remove the proxy gap entirely —
returned **HTTP 403** on both the index and a direct media URL. Two failed
requests, counted, not routed around.

### A ticker is not a company, and this nearly ruined the join

The issuer check was written expecting to catch one fault and caught three:

| symbol | issuer | settlement span |
|---|---|---|
| `B` | Barnes Group Inc. | 2017-12-29 .. 2025-01-15 |
| `B` | **Barrick Mining Corporation** | 2025-05-15 .. 2026-08-14 |
| `GOLD` | Randgold Resources | 2017-12-29 .. 2018-12-31 |
| `GOLD` | **Barrick Gold Corp.** | 2019-01-15 .. 2025-04-30 |
| `GOLD` | Gold.com, Inc. | 2025-12-15 .. 2026-08-14 |

`ABX.TO` maps to `B` in the twins table. A join on the ticker alone would have
paired **Barnes Group's** short interest with **Barrick's** returns across most
of the panel, and this repo's own feasibility probe did exactly that — it
reported Barrick at days-to-cover 8.00 when the true figure is 1.70, because it
reached for `GOLD` and got Gold.com.

The fix is that **the issuer name, not a rename date, is the point-in-time
authority**. Rows are kept or dropped on what FINRA says the company is. It
reconstructs Barrick automatically and cleanly — `GOLD` to 2025-04-30, `B` from
2025-05-15, no gap and no overlap — while excluding all three impostors.
**212 rows dropped for ABX.TO, counted and printed.**

The same check initially produced a FALSE rejection: TransCanada renamed to TC
Energy in 2019 and 33 legitimate reports were being thrown away. A rename must
be accepted and a reassignment refused; they are indistinguishable from the
ticker, which is the whole argument for reading the issuer name.

### Point-in-time, which is where a fake edge would have come from

Settlement date is not publication date. FINRA disseminates on the 8th business
day after settlement; the join uses a **9-business-day** lag so the rounding is
against us, uses `publish_date` and never `settlement_date`, and a shipping
test fails if any session sees a report published after it. **3,877 legs, 0
UNKNOWN, latest report used 2026-08-27.** Every verdict below was re-run at a
**15-day** lag and none of them moved.

### The feasibility gate, which looks only at the feature

Registered in advance: if days-to-cover ranks are >= 0.90 persistent across
consecutive reports, the sort is a permanent name label and only the
name-demeaned form may proceed. Measured **rho = 0.840** — below the gate, so
both forms were admissible and the level arm ran as registered.

This gate is also where a prior of mine was refuted before any outcome was
touched. I had argued this universe of large-cap Canadian names would show no
dispersion in short positioning and so offer no sort to make. Days-to-cover on
2026-08-14 spans **1.12 (SHOP) to 17.29 (CM)**, roughly fifteen-fold. That
refutation is the only reason the study was written rather than declined.

### Results — 3,877 legs, 491 sessions, 20 names

| arm | side | effect %/leg | quarters | placebo | verdict |
|---|---|---|---|---|---|
| H1 level | LONG | −0.027 | SIGN FLIPS | inside | UNDERPOWERED < 0.150 |
| H1 level | SHORT | −0.059 | SIGN FLIPS | inside | UNDERPOWERED < 0.193 |
| H3 flow | LONG | +0.064 | SIGN FLIPS | inside | UNDERPOWERED < 0.152 |
| H3 flow | SHORT | −0.071 | SIGN FLIPS | inside | UNDERPOWERED < 0.169 |
| H2 exclusion | SHORT | **+0.032** | **consistent** | **inside** | see below |

H1 and H3 are uninformative and say so: the harness cannot resolve below
~0.15–0.20%/leg and the observed effects are a third of that. A planted
0.10%/leg edge registers at only z≈1.6–2.0 on these arms; the bar would need
~690–1,050 sessions against 237–347 held. **That is UNDERPOWERED, not a null**
(rule 10), and H3 was the arm I had given the better odds to in advance.

### H2 is the one that says something, and what it says is a bound

Dropping the most-shorted name from the short side gives **+0.032%/leg, 95%
[−0.001, +0.067], positive in all four quarters** (+0.036/+0.058/+0.026/+0.009).
Four-quarter consistency is the thing this project normally requires, so it is
worth being explicit about why this is still not an adoption:

1. **It is INSIDE the placebo band.** Dropping a *random* short leg produces
   [−0.036, +0.038]. The observed +0.032 sits near the top of that but within
   it. Removing any leg from a small side moves the mean; that is arithmetic,
   not selection, and the four-quarter consistency is a property of the
   arithmetic rather than of short interest.
2. **The interval touches zero**, so it fails the bar on its own terms.
3. **It is smaller than the cost it would have to clear.** The measured
   round-trip is ~8bps; the whole effect is 3.2bps.

But unlike H1 and H3, this arm is **well powered**: a planted 0.10%/leg edge
registers at **z=5.43**, needing ~93 sessions against 304 held. So H2 is not a
shrug — it is a genuine bounded negative:

> **An improvement of 0.10%/leg or more from excluding the most-shorted short
> leg is EXCLUDED. Only an effect below 0.052%/leg remains unresolvable, and
> anything in that range is smaller than the spread it must pay.**

That is the difference between "we could not see it" and "it is not there at a
size that would matter", and this study produced one of each.

### REJECTION #38 — short interest as a selection input

Nothing is adopted. The morning report is unchanged: no short-interest field,
no exclusion rule, no new claim. `build_shortinterest.py` and
`validate_shortinterest.py` are committed and re-runnable, `data/short_interest.csv`
is kept, and the day-43 shortlist now has one of its four candidates measured
and closed rather than merely named. Three remain: L1/L2 depth and true volume
pace, point-in-time overnight news, and index futures state at 9:45.

**Expected outcome recorded in advance** (PREREGISTER_day84.md): "UNDERPOWERED
on H1 and H2, on the cadence argument. H3 is the only arm I would give better
than negligible odds, and I would not put those above one in five." H1 was
underpowered as predicted; H3 produced nothing and was the wrong horse; H2 was
better powered than expected and returned a usable bound. Recording the guess
first is what makes it possible to say that the guess was half wrong.

**Scope, not to be stripped:** this is the twins panel with entry at 10:30. It
is a MECHANISM sample. It can refute a rule and it certifies nothing about live
9:45 levels, and the ledger's PAIR line remains the arbiter.

## Day-85: five US strategies, 1.39M ticker-days — ALL FIVE UNDERPOWERED

Pre-registered in `PREREGISTER_day85.md`. Not rejections: rule 10, and day-82's
precedent. Nothing is adopted and the morning report is unchanged.

The portfolio manager lifted the Canadian restriction and asked for five new
strategies tested on enough data to name the most accurate one. Two things that
licenses, both real:

- **Rejection #33's objection retires.** Day-52 threw out `scaled` even though
  it cleared on 500 US names in 4 of 4 quarters, because it was dead on the TSX
  — "a feature that measurably does nothing in the only market the book
  touches." The book can touch US names now.
- **The earnings blocker is gone.** `earnings.py` has said since day-53 that
  Yahoo returns fiscal quarter-END dates, so there was "no way to measure
  whether excluding these rows would have helped." **8-K Item 2.02** is the
  announcement itself and `acceptanceDateTime` stamps it to the minute.

### The panel

**1,387,399 ticker-days, 578 names, 2016-08-30 to 2026-09-03** — 3.5x day-32's
400,703. Plus **15,627 earnings announcements** across 439 names, split
**BEFORE_OPEN 7,761 / AFTER_CLOSE 7,110 / IN_SESSION 756**. The in-session ones
are excluded: daily bars cannot place an announcement that landed at 11am, and
guessing is how an event study measures its own look-ahead.

### THE CORRECTION THAT DECIDED THIS STUDY

The first run produced two apparent winners: H4 at **|t|=3.79** and H5 at
**|t|=7.15**, both consistent across four blocks and outside placebo. Both were
artefacts of the estimator.

Every weekly arm computes a forward return **on every date**, so a 20-session
observation shares 19 sessions with its neighbour. Resampling single dates
treats those as independent draws. The interval shrinks, `|t|` inflates, and an
effect looks decisive because of how it was measured rather than what it is.

All forward-return arms now use a **block bootstrap with block = horizon**:

| arm | \|t\| naive | \|t\| block | verdict |
|---|---|---|---|
| H4 reversal 5d | 3.79 | **2.24** | UNDERPOWERED |
| H5 proximity 5d | 4.35 | **2.46** | UNDERPOWERED |
| H5 proximity 20d | 7.15 | **2.14** | UNDERPOWERED |

A test pins the failure rather than asserting it: on pure noise with
20-session overlap the single-date bootstrap rejects zero far more often than
nominal while the block bootstrap does not, and a planted effect is still
detected so the wider interval is not simply blindness.

**Every "finding" in this study existed only under the wrong estimator.**

### Two more corrections, both caught by tests before any number was quoted

**Cost was reversing effects instead of erasing them.** `m - cost * sign(m)`
overshoots: +0.016% gross printed as −0.034% net, which reads as a reversed
edge rather than an erased one. An effect smaller than its cost is worth zero.

**A data limit was printing as a finding.** When a liquidity quartile was too
thin for a decile sort the size test returned nan and reported NOT SIZE-ROBUST.
That is NOT COMPUTABLE. Missing evidence is not adverse evidence.

### The registered hurdle was printed but not enforced — and it moved arms

The pre-registration requires a loser-buying arm to clear day-32's three
dissolving tests ON TOP of the bar. The first draft printed them beside a
verdict that still read CLEARS, leaving the reader to apply the study's own
rule. The verdict now names any test the arm failed.

It was registered for H4 only, on my assumption that momentum would come out
POSITIVE. **It came out negative.** H5's profitable orientation is therefore
long the names FARTHEST from their 52-week high — the loser-buying direction
the rule exists for. The rule did not change; the arm it lands on was decided
by the sign, and the sign was not what was expected.

### Results — all five, none dropped, none promoted

| arm | horizon | effect | \|t\| | blocks | win | verdict |
|---|---|---|---|---|---|---|
| H1 overnight−intraday | 1d | +0.023% | 0.97 | FLIPS | 52.9% | UNDERPOWERED |
| H2 PEAD | 5d | −0.000% | 0.00 | FLIPS | 50.5% | UNDERPOWERED |
| H2 PEAD | 10d | +0.075% | 1.36 | FLIPS | 50.8% | UNDERPOWERED |
| H3 earnings gap | 1d | +0.016% | 0.43 | FLIPS | 50.0% | UNDERPOWERED |
| H4 weekly reversal | 5d | +0.241% | 2.24 | consistent | 51.8% | UNDERPOWERED, TAIL-CARRIED |
| H5 52w proximity | 5d | −0.371% | 2.46 | consistent | 47.0% | UNDERPOWERED |
| H5 52w proximity | 20d | −1.165% | 2.14 | consistent | 46.0% | UNDERPOWERED |

**H1 confirms the documented split but cannot trade it.** Overnight
**+0.0487%/session (~+12.3%/yr, 57.2% of sessions)** against intraday
**+0.0259%/session (~+6.5%/yr, 54.5%)**, with SPY itself at +9.4%/yr overnight
versus +4.8%/yr intraday. The direction matches the literature and the level
matters — **the 9:46->close window the engine trades is the flatter half of the
day** — but the DIFFERENCE flips sign across blocks and is underpowered, and an
overnight expression pays the spread twice and inherits day-24's measured 2x
volatility and 2.3x worse tail.

**H2 is the disappointment.** The strongest published prior in the anomaly
literature, a proper point-in-time feed, 13,743 announcements — and the 5-day
arm is dead level at −0.000% with signs flipping. I had recorded it in advance
as "the most likely genuine strategy to survive". It was not.

**H4 fails its own registered hurdle** independently of the estimator: mean
+0.241% against a **median of +0.094%**, which is day-32's TAIL-CARRIED
signature exactly. Registered in advance: "if H4 is the only survivor I will
treat that as evidence of survivorship rather than a finding."

**H5 is the one worth keeping open.** It is the only arm that passes every
qualitative check — consistent in all four blocks, outside placebo, NOT
tail-carried (median −0.187% against mean −0.371%), same sign on market-up and
market-down days, and size-robust across all four liquidity quartiles. It fails
on one thing only: `|t|` of 2.46 against a bar of 3. That is what UNDERPOWERED
is supposed to mean, and it says what it needs:

| arm | \|t\| | sessions for \|t\|=3 | have | ~years |
|---|---|---|---|---|
| H5 5d | 2.46 | 3,449 | 2,313 | 13.7 |
| H5 20d | 2.14 | 4,529 | 2,298 | 18.0 |
| H4 5d | 2.24 | 4,481 | 2,507 | 17.8 |

Ten years is not enough for any of them. The cheaper route is **more names per
date** rather than more dates — the statistic is date-clustered, so widening
578 names to several thousand tightens each date's estimate without waiting
another decade. That is the one concrete next step this study earns.

**And H5's honest caveat stays attached:** its profitable direction buys the
most beaten-down decile, which is exactly where the absent delisted names would
have been. A survivorship-driven effect would look like this.

### Nothing adopted

No arm cleared. The answer to "which is the highest-accuracy strategy" is
**none of these five at this sample size**, with each arm's MDE printed so the
reader knows what could still be hiding. `build_us.py`, `validate_us.py` and
`data/us_earnings.csv` are committed and re-runnable; the 188MB price panel
rebuilds in one command.

**Expected outcomes, recorded in advance and scored honestly:** H1 confirming
the split but dying on execution — correct. H2 the most likely survivor —
wrong, it was the deadest arm. H3 underpowered — correct. H4 looking good then
dissolving — correct, and it dissolved on the exact test predicted. H5 "weak
but honest" — wrong in an interesting way: it was the strongest arm and the
wrong sign, which flipped its survivorship exposure.

## Day-86: REJECTION #39 — H5 replicates its sign and fails on concentration

Pre-registered in `PREREGISTER_day86.md`, bar inherited from day-85 unchanged.
Day-85 left H5 (52-week-high proximity) as the only arm passing every
qualitative check and missing only on `|t| = 2.46` against a bar of 3. This
resolves it.

### The test had to be out-of-sample, and that is most of the work

The obvious move — fetch more names, re-run — would have been **wrong in a way
that looks like success**. The original 578 would sit inside the wider
universe, so the re-run would report a tighter interval around the same numbers
and read as confirmation while re-reading the draw that produced the
hypothesis. Day-52 handled this correctly by taking a TSX-generated hypothesis
to 500 S&P names, and that is the shape used here.

**The day-85 names are excluded and `load_split()` raises `SampleLeak` if even
one reaches the replication set.** A test plants a leaked name and asserts the
run stops. Held-out sample: **2,876,380 ticker-days, 1,279 names, zero
overlap** — roughly twice the sample that generated the hypothesis.

### The sign replicates. Everything else says why that does not matter.

| | day-85 (578 names) | held-out (1,279 names) |
|---|---|---|
| 5d effect | −0.371% | **−1.339%** |
| 20d effect | −1.165% | **−5.099%** |
| 5d tail test | not tail-carried | **TAIL-CARRIED** (median −0.271%) |
| 20d tail test | not tail-carried | **TAIL-CARRIED** (median −1.394%) |
| small-vs-large ratio, 5d | 2.4x | **13.1x** |
| small-vs-large ratio, 20d | 3.9x | **25.0x** |

The sign is day-85's, so the replication succeeds on the one thing that was
pre-committed. The effect also got **3.6x bigger**. Both facts are what a
survivorship artefact looks like, and the rule that says so was registered
before the data was fetched:

> *if the effect GROWS as the universe extends into smaller names, that is the
> survivorship signature and is to be read as evidence against H5, not for it.*

### H5b, the registered decider, and the liquid quartile that settles it

| quartile | 5d | \|t\| | 20d | \|t\| |
|---|---|---|---|---|
| smallest | −4.060% | 2.30 | −15.235% | 1.91 |
| 2nd | −0.481% | 2.87 | −2.118% | 2.61 |
| 3rd | −0.382% | 2.18 | −1.378% | 2.27 |
| **largest** | **−0.310%** | **1.52** | **−0.609%** | **0.86** |

The largest quartile is the only one a portfolio manager could trade at size,
and there the effect is **−0.310% at |t| = 1.52** and **−0.609% at |t| = 0.86**.
Nothing. Everything H5 has lives in the smallest quartile — which is exactly
where the delisted names that were removed from the universe used to be.

The block profile says the same thing from another direction: 5d blocks ran
−0.306 / **−3.493** / −0.669 / −0.888, and 20d ran −0.603 / **−14.308** /
−2.181 / −3.298. One block carries an order of magnitude more than its
neighbours. Consistent in sign, yes — and driven by one period and a few tails.

**REJECTED (#39).** Not underpowered: the registered gradient rule fails
decisively at 13x and 25x, both horizons are tail-carried, and in liquid names
there is no effect to be underpowered about.

### A methodological finding worth more than the hypothesis

**Day-32's size test passed all of this.** Its criterion is SIGN-based — all
four quartiles negative, so it printed `size-robust` on an effect **25x larger
in the smallest quartile than the largest**. The three dissolving tests have
been this repo's standard defence since day-32, and one of them was too weak to
catch the exact failure it exists for.

`dissolving_tests` now fails an arm whose smallest quartile exceeds the largest
by **2x or more**, whatever the signs do. Checked against the record: no day-85
verdict changes, because every arm there was already UNDERPOWERED — but H5's
own day-85 ratios (2.4x and 3.9x) would have failed it at the time, which is
the point.

### Scored against the prediction

`PREREGISTER_day86.md` recorded: *"The point estimate replicates in sign — that
much I expect… What I expect to decide it is H5b: I expect the effect to be
materially larger in the small-cap quartiles… I do not expect a clean pass."*
All three correct. The one thing not anticipated was that day-32's own size
test would wave it through.

### Where this leaves the five

Day-85's five arms are now: H1 underpowered (and its executable form pays the
spread twice), H2 dead at −0.000%, H3 underpowered, H4 tail-carried, **H5
rejected**. The honest answer to "which strategy gives the highest hit rate"
remains **none of them**, and it is now a firmer none than it was yesterday.

## Day-87: three items closed — a constant corrected, a blocker re-probed, a window rejected

### 1. TYPICAL_MOVE_PCT: 0.97% -> 0.69%, and the correction is against us

Decided on **population**, not on which study was better run — day-70's sample
cannot be reconstructed, so that question is unanswerable and had kept this open
for weeks. It does not need answering. The constant is a DENOMINATOR:

```
cost.share_of_move = spread(this pick) / TYPICAL_MOVE_PCT
cost.edge_bps      = (p - 1/2) x 2 x E|move|      # p is the PICKS' hit rate
```

Both numerators are drawn from picks. Day-70 measured the whole 21-name
universe, which includes names the engine never selects — and selection is not
neutral with respect to volatility, since day-47 established that the density
tag sorts by volatility. So universe prints are the wrong leg (rule 7). The
ledger's **363 scored legs over 41 sessions** give a median |capture| of
**0.69% [0.59, 0.80]**, and that is the population the report describes.

**Direction, stated plainly: this makes the book look worse, not better.**
Every cost line printed before today understated the drag. A 5bp spread was
reading as 5.2% of a typical move; it is really **7.2%**.

`validate_typicalmove.py` was NOT edited — changing a constant inside the
script that checks it defeats the check, and a test enforces that. The tension
check stays armed and now falls silent because 0.69 sits inside its own
interval. Silence earned by agreement, not by deleting the check.

A test held a literal `0.97` and broke on a legitimate change, which means it
was testing the number rather than the arithmetic. It now references the
constant, with a separate assertion pinning day-87's value against a live
re-derivation so it cannot drift back silently.

### 2. P(rejection): still open, and the blocker was re-probed rather than inherited

Day-82 named the unblocker — published complete response letters. FDA has moved
toward releasing them, so this was worth re-testing.

**It is not there.** `fda.gov/.../complete-response-letters` returns **HTTP
404**; openFDA's `drugsfda` responds but carries approvals only. One dead
endpoint, one live-but-wrong one, both recorded rather than routed around.

No change. **Cited 30%** (first-cycle NME) anchors `catalyst.assess`'s
guardrails; **measured 11.7%** [8.5, 15.9] (291 single-asset decisions, one
harvest, one classifier, one window) divides every breakeven in the screen.
Different populations, neither substitutable, and the measured leg is biased
DOWN for two named reasons. The report keeps printing both and keeps saying
they must never be mixed. Third direct probe of this blocker.

### 3. The overnight window: REJECTED on cost, at 4.87bps

Pre-registered in `PREREGISTER_day87.md` with the expected outcome recorded:
*"I expect H1c to FAIL on cost… I am running it because that arithmetic
deserves to be on the record with the tail numbers beside it."*

| | gross | net 5bps | net 10bps | net 20bps |
|---|---|---|---|---|
| overnight | **+0.0487%** \|t\|=3.12 | −0.0013% | **−0.0513%** \|t\|=3.28 | −0.1513% |
| intraday | +0.0259% \|t\|=1.53 | −0.0241% | −0.0741% \|t\|=4.39 | −0.1741% |

**The overnight window clears the bar GROSS** — +0.0487%/session, |t|=3.12,
consistent across all four blocks, 57.2% of sessions. It is a real effect.

**Its entire edge is 4.87 basis points.** That is the break-even round trip.
At 5bps it is already zero; at the registered deciding cost of 10bps it is
**negative with |t|=3.28**, which is to say reliably losing. Both windows carry
the identical cost model, because costing one and not the other would settle
the question by construction.

**REJECTED.** The answer to "is the engine trading the wrong half of the day"
is: yes, the flatter half — and no, moving to the better half does not help,
because the gap between them (2.3bps) is smaller than the cost of acting on it.

### The tail refines a day-24 claim, and half of it does not replicate

Day-24 concluded that one night "doubles volatility, 2.3x worse tail."

| | overnight | intraday | ratio |
|---|---|---|---|
| std dev | 0.777 | 0.829 | **0.94x** |
| 5th percentile | −0.990 | −1.307 | 0.76x |
| worst day | **−11.712** | −4.728 | **2.48x** |

On 2,517 US sessions the volatility half is **wrong** — overnight is slightly
*less* volatile (0.94x), and its 5th percentile is *better*. The tail half is
**right, and almost exactly**: day-24 said 2.3x, this says 2.48x.

So the overnight penalty is not general volatility. It is a pure extreme-tail
effect: nothing unusual on a normal night, and a −11.7% day when it goes wrong
against a −4.7% worst intraday day. That is a sharper and more useful statement
than the one it replaces, and it is the shape a gap-risk argument should have
had all along.

### Where the eleven arms now stand

Days 84-87 tested eleven arms across three markets and 4.3M ticker-days. Every
one is closed or bounded: short interest (bounded null), PEAD, earnings gap,
weekly reversal (tail-carried), 52-week proximity (**rejected #39**), overnight
(**rejected, on cost**). The one durable finding is negative and structural —
**the intraday window carries roughly half the drift of the overnight one, and
neither survives a realistic spread as a long-only basket.**

## Day-87 close: five of six right, and the book still lost money

**Tide 0.000%.** The universe median was flat, so nothing today can be blamed
on or credited to the tape. This was selection, cleanly measured.

| pick | role | r1 | rel capture | |
|---|---|---|---|---|
| CM.TO | pair (extra) | −0.489% | +0.489% | HIT |
| SLF.TO | **pair (primary)** | **+0.304%** | **−0.304%** | **MISS** |
| CP.TO | board | −0.330% | +0.330% | HIT |
| CNR.TO | board | −0.536% | +0.536% | HIT |
| SHOP.TO | board | −1.511% | +1.511% | HIT |
| TD.TO | board | −0.714% | +0.714% | HIT |

All six calls were shorts; five fell. **The direction read was right and the
book still lost.**

```
CM.TO    65sh @ 163.55 = $10,631   +$51.98 gross   spread −$15.52
SLF.TO  126sh @ 111.75 = $14,080   −$42.80 gross   spread − $8.87
                                    +$ 9.18 gross   cost   −$24.39
                                                    NET    −$15.21
```

**The spread was 2.7x the gross gain.** This is the day-82 sentence made
literal: *spread is not a cost on top of the edge — it IS the outcome.* The
morning report predicted SLF would start "~$9 behind"; it was $8.87.

Two structural facts, neither of them bad luck:

1. **The miss was the biggest position.** SLF was the primary leg at $14,080
   against CM's $10,631. Equal-risk weighting (day-22) sizes UP the calmer
   name, and the calmer name is the one that went wrong. That is the rule
   behaving exactly as designed — it shrinks bad days, it does not pick better.
2. **CM's spread was 14.6bps** against SLF's 6.3. The winning leg paid 2.3x the
   toll of the losing one.

### The obvious inference from today, tested and refused

Board 4/4 at +0.773%/leg while the traded pair went 1/2 at +0.092%/leg. Across
the whole record the same pattern appears in the aggregates:

| | hit | Wilson | rel capture |
|---|---|---|---|
| PAIR (traded) | 47/97 (48.5%) | [38.8, 58.3] | −0.077%/leg |
| BOARD (untraded) | 105/198 (53.0%) | [46.1, 59.9] | −0.010%/leg |

A 4.5pp gap, and it is tempting. **It is an artefact of comparing unpaired
aggregates.** Legs on one day share that day's move, so the comparison has to
be paired by session. Paired:

**board minus pair = −0.003%/leg, 95% [−0.266, +0.254], |t| = 0.02**, board
better in 19 of 34 sessions.

Dead zero. The densest-leg selection is neither better nor worse than the board
it draws from — which is exactly what day-21 found on 809 deep-panel legs
(densest 50.1%, random 50.2%) and what day-47 concluded when it refused the
density gate. MDE here is 0.399%/leg, so this is UNDERPOWERED for anything
smaller, but the point estimate has no sign to chase.

**Nothing to do.** The idea today's session suggests is the one the record
already refuses.

## Day-88: the earnings gate — CLOSED by arithmetic, not by a null

Pre-registered in `PREREGISTER_day88.md`. This answers a question `earnings.py`
has carried since day-53 and could never test:

> *"there is no free source of historical announcement dates for TSX names, and
> therefore no way to measure whether excluding these rows would have helped."*

Panel: **123,772 ticker-sessions, 258 US names, 490 sessions**, hourly bars,
engine walk-forward identical to `validate_twins`. **50,779 qualified legs**
joined against **60,922 Item 2.02 announcements** timestamped to the minute.

### The placebo is silent, so the study is valid

An announcement accepted after 16:00 cannot move a leg that is flat by 15:55.
Excluding those days moved the number by **+0.0003%/leg, |t| = 0.23** — nothing.
Dropping rows per se does not manufacture an effect here. That control is
exact rather than statistical, and it is what makes the rest readable.

### The direction is right and the statistics do not support it

| group | n | hit | Wilson | rel capture |
|---|---|---|---|---|
| in-window (before open / in session) | 396 | 46.5% | [41.6, 51.4] | **−0.1539%** |
| after-close (reports tonight) | 263 | 45.6% | [39.7, 51.7] | −0.0334% |
| clean (no announcement) | 50,120 | 49.7% | [49.3, 50.2] | −0.0155% |

Earnings-day legs look **ten times worse in capture** and 3.2pp worse in hit
rate. Session-clustered, that difference is **−0.1383%/leg, |t| = 1.59, blocks
−0.256 / −0.218 / **+0.076** / −0.136 — SIGN FLIPS**. Both Wilson intervals
contain 50%. **UNDERPOWERED** (rule 10), needing ~1,409 in-window legs against
396 held, which is 3.6x this panel.

### What actually closes it is arithmetic, and no amount of data changes it

In-window legs are **0.78% of all legs**. Taking their penalty entirely at face
value — the point estimate the statistics do not support — removing them moves
the book average by:

```
0.0078 x 0.1384%/leg  =  +0.00108%/leg  =  +0.108 bps/leg
```

**One round-trip spread on the live book is ~8bps.** The entire filter effect,
granted its most flattering reading, is **1.3% of a single spread crossing.**

That is the answer, and it does not depend on power. A gate on an event that
occurs on 0.78% of ticker-sessions cannot move a book-level average, however
bad those sessions are. Waiting for 3.6x the data would let us measure the
penalty precisely; it would not make the gate worth having.

### REJECTED as a gate — and `earnings.py` was right to warn rather than block

The module's day-53 instinct is vindicated: warn, never block. The warning is
worth keeping for the reason it was written — a name reporting inside the
window hands you the same coin flip with a bigger stake on it, and the reader
is entitled to know before sizing. What is now measured is that turning that
warning into a gate buys **0.1 bps/leg**, which is indistinguishable from
nothing next to an 8bp spread.

**This is a better outcome than a null.** A null would have said "we could not
find an effect". This says "the effect can be granted in full and still cannot
matter", which closes the question permanently rather than deferring it to a
larger sample.

### Scored against the prediction

`PREREGISTER_day88.md` recorded: *"I expect H1 to be POSITIVE but small, and
probably underpowered… I expect H2 to show the dropped rows are genuinely
worse… I expect H3 to show nothing."* H1 +0.0042%/leg, underpowered — correct.
H2 directionally worse but underpowered — half right, the direction held and
the significance did not. H3 silent — correct. What I did not anticipate was
that the frequency argument would settle it independently of all three.

## The checklist the tool now enforces before a name is "actionable"

1. **Data verified live** (integrity guard passes).
2. **Verdict is a lean** (not NO-EDGE — WAIT).
3. **Persisted** ≥ `min_persistence` consecutive scans (no snapshot-chasing).
4. **Lenses aligned** (not `conflicted`; ideally structure + base rate + macro agree).
5. **In-sample** (analog base rate not flagged off-sample).
6. **Entry only on the trigger** (5-min hold beyond the opening range), never
   inside the no-trade zone.
7. **Size from the stop**, honour the invalidation, and remember the cap — it's a
   lean, not a prediction.

If a setup fails any of these, the honest output is **WAIT / STAND DOWN**.
