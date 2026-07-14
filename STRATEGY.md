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
