# PREREGISTER day-126 — the desks research before they pick; Claude answers stateless; a web scout for the council

Registered 2026-10-05 (≈ 20:45 ET), before any of it ran. The owner asked
for the models to use the data dynamically ("not a point-in-time hardcode"),
authorised replacing the current path from 2026-10-06, and asked whether the
OpenRouter key could add something unique. The constraints still hold:
* the email arrives every morning;
* nothing breaks or gets worse;
* the Top 2 consensus stays at the top.

## 1. The research round (replaces the single-shot desk call)

DeepSeek, Gemini and Claude each receive the same brief as today, plus
read-only FMP tools. Each decides what to look up before it answers:

| Tool | Returns |
|---|---|
| `analyst_history(ticker)` | broker actions with dates, including maintains |
| `earnings_history(ticker)` | EPS and revenue, actual vs estimate, by date |
| `key_metrics(ticker)` | TTM valuation, margins, leverage |
| `daily_prices(ticker, sessions)` | the last ≤ 20 daily closes and volumes |
| `reaction_history(ticker, event)` | for the name's last ≤ 3 analyst changes or reports: the opening gap and 09:45 → close against XIU, from FMP 5-minute bars |
| `news(ticker)` | FMP headlines with publisher and time, marked UNVERIFIED |
| `peers(ticker)` | the peer list and each peer's last-session move |
| `sector_performance()` | TSX sectors on the last session |

Rules:
* **Scope.** Only tickers in the brief. Only data published before today's
  session. A budget of 8 calls and 75 seconds per model; when it is spent,
  the model must answer.
* **Answer.** The same JSON, the same `_clean` / `check_levels` /
  `check_basis`, the same ceiling of two per side.
* **Logging.** Every call and its compact result are logged to
  `research_<model>.json` and frozen into the snapshot.
* **Fallback.** If the research round fails, the desk answers single-shot
  exactly as on 2026-10-05, and the gaps say so.
* **Versions.** Prompt `day126-research-v1`. The system prompt is
  `SYSTEM_PROMPT` plus one research paragraph.
* **Jev** cannot call tools (a decisions API) and is unchanged.

## 2. Claude answers stateless, through OpenRouter

The session-route asymmetry recorded on day-124 (Claude can recognise its own
proposals) is removed:
* **Desk:** `anthropic/claude-opus-5.5` via OpenRouter, using the research
  round above. The session's own answer is the fallback when OpenRouter
  fails. It seals as route `openrouter`.
* **Council ballot:** the same model, stateless, asked with the same council
  prompt and ROUND_2 note as the others, after Round 1. The session ballot is
  the fallback.

## 3. The web scout (Perplexity `sonar-pro`, live web search)

After the desks and before the council's Round 1, one call per position on
the table (at most 8, in parallel). Each returns up to three dated facts from
the last 72 hours with their citation URLs.
* They enter the council's evidence rows as `web_news`, labelled UNVERIFIED
  web text.
* The council payload carries one `evidence_legend` describing `research`
  (FMP facts the desks fetched, by ticker) and `web_news`.
* The council's frozen prompt and consensus rule are unchanged; this is
  amendment 2 to `PREREGISTER_day124_council.md`.
* On the probe, the scout missed the Cenovus–Athabasca deal announced that
  morning. Web text is evidence to weigh, never a fact.

## Test before shipping (paired, on the day-117 replay sessions)

DeepSeek single-shot against DeepSeek with research, on the same replay
pools and the same scorer.
* **Point-in-time tools only:**
  * `key_metrics` and the consensus counts are disabled in replay, because
    they are current values;
  * every other tool is cut at the session date;
  * `news` is dropped, because FMP's history is not complete.
* **Bar (non-inferiority, not skill):** the research arm's mean per pick is
  not below the single-shot arm's by more than 0.30% (one-sided, clustered
  by session).
* An underpowered "no worse" is all 59 sessions can show. **No accuracy gain
  is claimed**, and none is claimed in the email.

If the research arm fails the bar, the desks ship single-shot and only the
scout and the stateless Claude change.

## Records

The desks keep their scoreboard rows and split by `prompt_version`. The
council's Top 2 stays `day124-council`. The counted shadow continues.

## Clarification, before the replay runs (2026-10-05 ≈ 20:50 ET)

"Not below by more than 0.30%" is the POINT ESTIMATE:
* the research arm's mean signed return per pick minus the single-shot arm's;
* each arm scored 09:40-bar close → 15:55-bar close on FMP 5-minute bars, the
  scoreboard's yardstick, the same for both arms;
* the difference must be ≥ −0.30%.

Both arms use today's prompt (`day125-v4`) on the 59 cached day-117 pools,
asked as of 09:00 on each session. The research arm's tools are the replay
set (analyst_history, earnings_history, daily_prices, reaction_history,
sector_performance), all cut before the session.

Reported beside it, not used to decide:
* hit rates;
* the difference's session-clustered 95% interval;
* the research calls made.

Summary: `data/replay_day126_research.json`.

## Result and amendment 1 (2026-10-06 ≈ 00:55 UTC, before the first live morning)

**The paired replay PASSES the registered bar.** On 59 sessions, both arms
asked as of 09:00:
* single-shot: 73 picks, 52.1% right, +0.069%/pick;
* research: 122 picks, 49.2% right, −0.001%/pick (5.98 calls per session,
  no failed round);
* difference: −0.070% against a bar of −0.30%, with a 95% interval of
  [−0.60, +0.47].

That is "no worse", underpowered as registered; no gain is claimed. The
research arm picks about 70% more often.

**DeepSeek's research path then FAILED the planted-edge control** (house
rule 4), on the `day125-v4` prompt and the day-110 planted universe:
* with tools: 1 clean run of 8. Six abstained, and once the planted short
  was put LONG. It used 2–4 calls per run, and abstained whether the tools
  returned no history or a history consistent with the plant.
* single-shot, the same morning: 3 clean runs of 4, one abstention.

Gemini (2 of 2 clean) and Claude via OpenRouter (2 of 3 clean, one
abstention; single-shot 2 of 2) pass with the tools offered. Neither made a
call on the control.

So, from 2026-10-06:
* DeepSeek's desk ships SINGLE-SHOT (`deepseek_opportunities.RESEARCH_LIVE
  = False`);
* Gemini and Claude research as registered;
* the scout and the stateless Claude ballot ship as registered.

DeepSeek's research path is kept for the replay and a later re-test. That
re-test must pass the control before it goes live.
