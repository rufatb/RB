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
