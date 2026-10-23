# Audit, day-138: before the news, held a few days

Registered in `PREREGISTER_day138_events.md` (4fb0885, amendment 1 f5f8a9d)
before any return was computed. Script `replay_events.py`; summary
`data/replay_day138_events.json`; tests `tests/test_replay_events.py`.

## The question

After the Top 2's losing run, the owner asked for new ways for the council
under three conditions:
* no retrospective bias;
* a hold of a few days;
* nothing the price has already moved on.

Every design below follows all three:
* No input is the stock's own past move.
* Three of them enter before a scheduled report is out, so nothing in it can
  be in the price.
* The fourth acts only where the open had not moved the model's way.

## What was run

* **E1–E3: the 150 names, 2012-01 → 2026-10.**
  * **Data:** FMP dividend-adjusted daily bars and FMP's report dates, from the
    day-135b cache.
  * **Window:** enter at the close before the report date and exit at the close
    of D1 + 2, three to four sessions. That holds a report whether it comes
    before the open or after the close, and most of those FMP dates a day
    early.
  * **Measure:** the return against XIU, minus the same name's return in random
    windows away from its reports (2,000 draws).
  * **t:** the smaller of the clusterings by name and by week.
* **E4:** day-122's cached DeepSeek answers on 420 overnight releases, from
  open to the close two sessions later.
* **E1-US (amendment 1):** E1's rule on the S&P 500 as it stood on each date.
  * Membership is rebuilt from FMP's change history, delisted names included
    where FMP serves them.
  * SPY is the market.
  * This was added after E1 passed and registered before it ran.

## Results

| Test | Reports | Excess a report | t | Verdict |
|---|---:|---:|---:|---|
| E1, long every report (TSX list) | 8,203 | +0.37% | +3.78 | PASS as registered |
| E2, the previous surprise's side | 6,926 | +0.11% | +1.27 | NULL |
| E3, the peers' surprises' side | 2,208 | +0.33% | +1.68 | UNDERPOWERED |
| E4, the model's read the open had not priced | 133 | +0.24% | +0.63 | UNDERPOWERED |
| E1-US, long every report (S&P 500 as it stood) | 27,701 | +0.01% | +0.20 | NULL (planted 0.50% at t = 8.07) |

## Why E1 is not adopted

The TSX list is today's 150 most-traded names. Testing history on it tests
survivors, and the premium came from survival.

* **On the S&P 500 as it stood,** the rule earns nothing (+0.01%, t = 0.20).
  It had the power to see 0.24%.
* **Split by survival:**
  * names still in the index today: +0.15% a report (t = 2.42);
  * names since removed: −0.65% (t = −4.76).
* **On the TSX list,** the premium is largest in 2024–2026 (+0.47%, +0.90%,
  +1.07% a report). A list ranked on the last 20 sessions' trading leans
  hardest toward recent winners in those years.
* **The checks made after E1's verdict all held:**
  * against the names not reporting in the same window: +0.40%, t = 4.05;
  * on a market model: +0.34%, t = 3.50;
  * trimmed at 1% and 99%: +0.36%;
  * when the report's volume spike fell inside the window: +0.48%, against
    −0.00% when FMP's date put it after the exit.

  Each of these is also what survivors would show: a name that grew onto
  today's list did so partly on its report days.
* **The sized portfolio is not evidence.** 5% a window, at most 100% open,
  hedged: +8.7% a year net, max drawdown 14%, and 2024–2026 alone +17%. It
  reads the same survivor premium.

## What it means

* **The owner's three conditions are the right ones,** and they still find
  nothing here.
  * Before the news, the only systematic payment is a risk premium.
  * In a universe that includes the losers, that premium was zero over
    2012–2026.
* **The models' judgment adds nothing measurable** on top: E2–E4, and every
  earlier test since day-117.
* **A rule for every future test:** a long-only or event rule is never judged
  on today's list.
  * Its history is survivor history; the check is a point-in-time universe
    (`replay_events.sp500_membership`).
  * Earlier nulls on the list stand. A PASS on it needs this check.

## Not claimed

* That no premium exists on the TSX. Without a point-in-time TSX list it
  cannot be measured here, and the US result says not to expect one.
* That any pick, council or rule is more accurate.
