# PREREGISTER day-121b — does agreement beat one model, and do the picks work from the open?

Registered 2026-10-01 (evening), BEFORE either number below was computed. The
owner asked: "what other ways can we test to make it a little more accurate?"

The data is the day-117 replay:
* 59 sessions;
* the production pools;
* DeepSeek's and Jev's answers to the live prompt, cached in
  `.rb-state/replay/answers/`;
* the 4,601-row panel in `.rb-state/replay/panel.json`.

For each panel row:
* `r` is the 09:45 bar close → 15:55 bar close;
* `r0_today` is today's 09:30 open → the 09:45 price;
* open → close is (1 + r0_today)(1 + r) − 1.

Picks are signed by side. Claude cannot be replayed (it has seen outcomes), so
"agreement" here is between DeepSeek and Jev, exactly as `top_picks.select`
counts it with Claude absent.

## T1 — Does agreement add anything? (the rule adopted on 2026-10-01)

Two comparisons:
* **Rule against rule.** For each session, run `top_picks.select` twice: under
  AGREEMENT ONLY (as shipped), and under the old filled rule (top two
  candidates, split last). Report each rule's picks, hit rate and mean.
* **Agreed against single.** Compare names both models back on the same side
  with DeepSeek selections that Jev did not back. Statistic: the
  session-clustered mean difference (agreed − single), on sessions holding
  both kinds.

Controls:
* **Placebo:** shuffle the agreed/single labels within each session, 2,000
  times. p = the share of shuffles with a difference at least as large.
* **Planted control:** +0.5% added to every agreed pick must show at t ≥ 3.
  Otherwise the comparison is UNDERPOWERED, not null.

**Bar:**
* agreed better at t ≥ 3 and placebo p < 0.01 → agreement adds accuracy;
* t ≤ −3 → agreement hurts;
* anything else → no measured difference, and agreement-only stays a
  presentation rule, as already stated.

## T2 — Are the picks priced in the first 15 minutes? (entry at the open)

Population: the day-117 registered picks, DeepSeek selected plus Jev forced.
For each pick, three signed returns: open → 09:45, 09:45 → close, and open →
close.

Statistics:
* the clustered mean of each, by session;
* against random same-side picks from the same session's pool (2,000 draws,
  same count per session): p = the share of random means at least as large as
  the real one.

Planted control: +0.5% added to open → close must show at t ≥ 3.

**Bar:**
* open → close mean > 0 at clustered t ≥ 3 AND random-pool p < 0.01 → the
  picks carry information the first 15 minutes absorbs. Delivering them before
  the open (an at-the-open entry) becomes a registered forward test. This is
  possible: the picks are sealed by ~09:00.
* Anything else → entering earlier is not a lever for these picks.

## Expected

Day-117 found no field with signal and both models at chance from 09:45. I
expect both tests to show no measured difference. They are run because each
decides a concrete question (keep agreement-only as more than a label? deliver
before the open?) for minutes of compute, and the answer goes on the record
either way. Nothing is tuned against the result.
