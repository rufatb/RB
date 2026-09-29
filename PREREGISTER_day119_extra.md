# PREREGISTER day-119 — Parts 3 and 4: two separate tests beside the desks

Registered 2026-09-29, before either section's first live signal. The owner
asked for additional sections, tested in parallel from the email, without
changing the existing system.

## Part 3 — Gap signal (`gap_signal.py`)

* **Rule:** day-113's, unchanged (rejection #42). A TSX-21 stock whose
  opening gap is at least one normal day's move is bet to continue in the
  gap's direction until the close. A normal day's move is the sd of its 20
  prior daily close-to-close returns. The gap is the engine's own 09:46
  measurement (open vs prior close).
* **Correction to how #42 was quoted.** The +0.139% it reported averages each
  SESSION's signals first. Per trade, over 3,642 signals across 10 years, the
  rule was right 48.7% and made +0.03% before costs. Over the last 12 months:
  311 signals, 44%, −0.07%. Per trade it is no better than a coin flip; the
  section prints this every day.
* **Recording:** `data/gap_calls.csv`, scored in the evening two ways — from
  the 09:30 open (the study's contract) and from the 09:45 bar close (what the
  09:50 email's reader can still get).

## Part 4 — Post-earnings drift (`pead.py`)

* **Event:** a results release on the Canadian wire (`data/newswire`) naming a
  pool or TSX-21 name. Date notices, AGM votes and conference-call notices are
  excluded by the title rule in `pead.py`.
* **Reaction:** the first session that could trade the release, measured close
  vs prior close.
* **Signal:** |reaction| ≥ one normal day's move (sd of the 20 prior daily
  returns). The bet is the reaction's direction, entered the next session at
  the 09:45 bar close and exited at the close of the fifth session (entry day =
  day 1).
* **Recording:** `data/pead_calls.csv`, appended when staged and scored in the
  evening once five sessions are done.
* **Prior:** the three months of archive held 24 such signals, right 50%. That
  is too few to say anything; this is a forward test.

## The bar, for both, at 40 live sessions (about 2026-11-24)

* the mean per trade is > 0 with t ≥ 2.0, clustered by session (Part 4: by
  entry session);
* the hit rate beats a side-flip placebo (2,000 draws) at p < 0.05;
* the mean still clears a 0.10% round-trip cost.

If fewer than 30 trades have completed by then, the verdict is UNDERPOWERED
and the test continues. Nothing is sized from either section until the bar
is met.
