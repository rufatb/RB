# PREREGISTER day-127 — every input carries its date; the flash is re-checked at the open

Registered 2026-10-06 (≈ 15:20 ET), before any of it ran.

## What happened

On 2026-10-06 the council shorted CVE.TO, 4 of 4. Every reason it gave was
2026-10-05's:
* the Athabasca deal announced that morning;
* r0 −4.04%, rel_sector −3.69%, rvol 1.84;
* a WTI change of −2.31% observed PRE-MARKET at 08:44.

The arguments called these "today's". CVE then moved with its sector (+1.15%
vs XEG +1.13%, 09:45 → 15:00) while oil reversed upward. The owner asked that
the system never act on yesterday's reasoning, and that a pick be confirmed
alive on the day of the trade.

One day is an anecdote (day-98, day-120b). Nothing below is a signal, a
threshold or a rule fitted to that day. It is input labelling and delivery
hygiene, and it is registered so it is not mistaken for either.

## 1. Every input carries its date (prompt `day127-v5`, Jev `day127-v3`)

`deepseek_opportunities.build_request`, which feeds DeepSeek, Gemini, Claude's
brief and the council's evidence rows, adds:
* `data_dates` at the top of the payload:
  * today's date, and that none of today's trading is in the rows;
  * the PRIOR session's date, which every price, return, volume and
    indicator field describes;
  * how to read headline ages and macro clocks.
* `age_hours` on every headline: the hours from publication to the brief.
* `window` on every macro field: "PRE-MARKET today" when observed before
  09:30 ET today, or "PRIOR SESSION <date>" when observed earlier.

The system prompt gains ONE paragraph. It tells the model to:
* read `data_dates`;
* never call a supplied move "today's";
* give a reason that still holds for today's session, not one made only of
  the prior session's move and news, or abstain.

Jev's instructions gain the same sentence, and its state carries `data_dates`.

The council's frozen prompt is unchanged (amendment 3 to day-124). Its payload
carries the same `data_dates` beside `evidence_legend`.

**Controls (house rule 4) before it goes live.** The planted-edge control is
re-run on the new prompt for each of:
* DeepSeek;
* Gemini;
* Claude via OpenRouter;
* Jev.

A desk whose control is worse than on `day125-v4` is reported, not hidden.

The desks' records are split by `prompt_version`. No accuracy gain is claimed.

## 2. The flash names its exposure and is re-checked at the open

**In the flash.** Each position prints its sector and the sector ETF it moves
with, from `data/tsx_sectors.json` (for example, Energy → XEG.TO). This is
display only.

**`council_flash.py --open-check`.** At 09:31 ET it takes FMP quotes for each
flashed position, its sector ETF and XIU.TO. It fails closed:
* a quote not stamped today after 09:30 is NOT CHECKED;
* it never guesses.

It prints:
* the day-120 E1 verdict, unchanged: VOID when the price is already past the
  position's "wrong if", otherwise STILL VALID;
* the open against the prior close, signed to the pick;
* the sector ETF's move beside it.

No new threshold, no new verdict. It is sent as one short email; the 09:46
report still applies E1 to its own 09:46 quote. Nothing is recorded or scored.

## Not done

There is no rule against "acquirer the day after a deal", "fading a day-1
move" or "shorting into an oil reversal". Those would be fitted to one day.
They may be registered and tested on FMP history separately.

## Result and amendment 1 (2026-10-06 ≈ 16:00 ET, before the first live morning)

**The registered prompt paragraph FAILED the planted-edge control.** It told
the models to read `data_dates`, never call a supplied move today's, and
abstain on a thesis made only of the prior session. Every input the desks see
before the open IS the prior session, so in effect it said "abstain".

Controls on the same day (clean = both planted names, nothing else):

| Version | DeepSeek | Claude (OpenRouter) | Jev | Gemini |
|---|---|---|---|---|
| day125 prompts (yesterday's) | 5/10 (once sides swapped, once noise names) | 3/3 | 3/3 | — |
| + the registered paragraph | 0/4 | 0/3 | 0/2 | 3/3 |
| emphatic labels, abstain clause removed | 1/4 | 0/3 | 0/3 | 2/2 |
| plain labels + one neutral sentence | 3/4 | 0/3 | 3/3 | 2/2 |
| **plain labels in the payload, prompt text unchanged** | **5/10, no side error** | **5/5** | **3/3** | **2/2** |

What ships, as version `day127-dated` for both prompt families:
* the payload carries plain `data_dates` (`today`, `rows_describe`,
  `written_at`);
* every headline carries `age_hours`;
* every macro field carries `window` ("PRE-MARKET today (08:44 ET)",
  "PRIOR SESSION 2026-10-05").

The system prompt and Jev's instruction TEXT are byte-identical to day-125's.
A test pins that `data_dates` is not mentioned in `SYSTEM_PROMPT`.

With the plain labels, Claude's control reasons began "Prior session closed
42.8 above orb_high 41.9…": it named the session correctly without being told
to.

No instruction to abstain on prior-session reasoning ships. One was tried,
and the control shows it would have silenced the desks. Section 2 (exposure
line, open check) is unaffected and ships as registered.
