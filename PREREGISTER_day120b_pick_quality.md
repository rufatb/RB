# PREREGISTER day-120b — why the Top 2 went 0/2 on 2026-09-30, tested before acted on

Registered 2026-10-01, BEFORE any of the numbers below were computed. The owner
said: "change and make it better, I don't want things like this to happen again."

## What happened on 2026-09-30

* **TD long (3 of 3 agreed), −0.75%.** All the banks fell 0.63–1.80% from 09:45
  while XIU fell 0.83%. TD's whole day (−0.96%) was better than every other
  bank. The pick lost to the market, not to the other banks.
* **WSP short (2 of 3 agreed), −1.01%.** The reason was the prior session's
  −5.9% relative drop. WSP bounced +1.57% on the day.

## Three questions, all on the day-117 replay

The data is the same 59 sessions, the same production pools and the same
answers. The yardstick is 09:45 → close. No prompt is re-asked.

**H1 — Hedged expression (variance).** Each pick's return is measured relative
to the median 09:45 → close return of its sector peers in that session's pool:
* the sector comes from `data/tsx_sectors.json`, applied retroactively
  (labels, not prices);
* with fewer than 2 peers, the pool's median is used instead.

Reported for both raw and hedged returns:
* hit rate;
* mean;
* per-pick sd;
* correlation with the pool median.

H1 claims NO accuracy. It is adopted as an ADDITIONAL scored expression of
every Top 2 pick (raw stays the headline record) if it cuts per-pick sd by at
least 15%. If not, it is printed as a measurement only.

**H2 — Chasing yesterday.** A pick is CHASING when two things hold:
* its side agrees with the sign of the prior session's `move_atr`;
* |`move_atr`| ≥ 1.0 (a move of at least one normal day, carried on).

The test compares CHASING picks with the rest, using the session-clustered
difference in mean return. The bar is t ≤ −3.0 (chasing worse).

Required alongside it:
* a placebo (labels shuffled within a session);
* a planted control (−0.5% added to the chasing picks, which must be detected).

The rule is also run on the whole 4,601-row panel, to check whether
continuation after a big move is any different from reversal.

* **If it passes:** E3 joins E1 and E2 on the Top 2 and the debate (sort last /
  drop).
* **If not:** it is a flag printed beside the pick and nothing else.

**H3 — Single-source agreement.** "3 of 3" built on one press release is not
three opinions. This cannot be replayed: Claude cannot be replayed, and the
replay has no wire for most sessions. It is DISPLAYED only: when every backer's
reason cites the same issuer release, the agreement column says so.

## The bar does not move

A null is reported as a null and the rules are not tuned against it. The
forward record decides at 40 live sessions, as day-118 registered.
