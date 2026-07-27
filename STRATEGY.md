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
