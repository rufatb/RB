# PREREGISTER day-125 — FMP data in the morning brief, and one test before it is described

Registered 2026-10-06 (≈ 00:15 ET), before any FMP data reached a model and
before the test below ran. The owner bought FMP Premium (Canadian coverage)
and asked for every useful FMP field in front of the models each morning.

## What enters the brief (every model sees the same rows)

Staged before Claude's brief by `fmp_context.py --stage`, read by
`factor_inputs.build_from_state`, and rendered into each name's row by
`deepseek_opportunities._row` — the one row builder Claude, DeepSeek, Gemini,
Jev, the debate and the council all share.

Per name:
* `analyst_30d`: rating CHANGES (upgrade, downgrade) in the last 30 calendar
  days, at most 3, as "date firm action from→to". Maintains are left out.
* `analyst_consensus`: today's count of buy / hold / sell ratings.
* `last_report` and `eps_surprise_pct`: the last reported quarter's date and
  EPS against its consensus estimate.
* `next_report`: the next scheduled report date.

Once per morning, in `macro`:
* `events_today`: Canada and US economic releases scheduled 08:00–16:00 ET
  today, with impact High or Medium, as "HH:MM CC event (impact) est / prev".

A failed or partial fetch costs only these fields, and the gaps say so. FMP
quotes carry no bid/ask, so they are NOT used for sizing.

The prompt becomes `day125-v4`. It describes each new field and states its
tested status: analyst changes carry the result below; the other fields are
untested context. Positive controls are re-run for DeepSeek, Gemini and Jev
(house rule 4).

## The test: does an analyst rating change move the stock after 09:45?

* **Population.** The 117 TSX names in the morning pool. Every upgrade or
  downgrade FMP dates from 2024-01-02 to 2026-10-02 (216 counted before any
  return was looked at). Each event's sign is +1 for an upgrade, −1 for a
  downgrade.
* **Session.** The primary session is the rating's date when that is a TSX
  session, else the next session. D+1 is reported as secondary. FMP gives no
  time of day.
* **Primary outcome.** The signed return from the close of the 09:40 bar (=
  09:45) to the close of the 15:55 bar, MINUS XIU.TO's return over the same
  bars. These are the scoreboard's entry and exit, against the market.
* **Bar.** Mean > 0 with a session-clustered t ≥ 3.0, AND a placebo
  p < 0.05. The placebo applies each event's sign to a random NON-event
  session of the same name from the same fetched window, over 2,000 draws.
* **Positive control (house rules 4 and 10).** The t a planted +0.5% would
  show, computed as edge / se. Below t = 3 means UNDERPOWERED, not null.
* **Reported beside it, not tested:**
  * the signed gap (prior close → open) and open → 09:45, i.e. whether the
    open priced the change;
  * D+1 from 09:45 to the close;
  * upgrades and downgrades separately.

## Use of the result

* **Pass:** the prompt says so in one line with the numbers.
* **Fail:** the prompt says a registered test found no same-day drift after a
  rating change (with the numbers), and to treat the field as context.

The field is shown either way: the owner asked for the data. It is never
turned into a rule, a filter or a sizing input without a new registration.
The prompt is not re-worded against the replay beyond that one line.

Summary: `data/replay_day125_analyst.json`.
