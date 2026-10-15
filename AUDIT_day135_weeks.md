# Day-135b audit — multi-week holds after earnings and rating changes (owner, 2026-10-15)

Registered first: `PREREGISTER_day135_weeks.md` (3e0e8bc). Script:
`replay_weeks.py`. Summary: `data/replay_day135_weeks.json`.

## The question

The owner: the 09:45 → close trade is "too much of a gamble"; would a hold of
a couple of weeks after company events (earnings surprises, reports, rating
changes) carry an edge?

## The data

* **Coverage.** 150 names, 6,477 sessions (2001-01-02 → 2026-10-14), 12,633
  earnings reports with a known actual, and 1,862 rating-change days on 87
  names (FMP's ratings start in 2012).
* **Sources.** FMP Premium: earnings, grades, and dividend-adjusted plus raw
  daily bars.
* **Clean.** No series was rejected for granularity and no fetch failed.
  * 2,257 reports fall before the price history and were dropped;
  * 488 had a missing bar on a required date;
  * 16 rating days netted to zero.

## Registered results (decided at H = 10 sessions, market-adjusted, % per trade)

| Signal | n | mean | median | t (conservative) | placebo p | 4 blocks | net of cost | registered verdict |
|---|---:|---:|---:|---:|---:|---|---:|---|
| W1 EPS surprise | 6,549 | +0.329 | +0.426 | +3.54 | 0.000 | +0.68 +0.42 +0.17 +0.03 | +0.189 | DRIFT |
| W2 reaction | 7,546 | +0.058 | +0.140 | +0.42 | 0.541 | +0.26 +0.15 −0.15 −0.03 | −0.082 | NULL |
| W3 both agree | 3,031 | +0.389 | +0.470 | +2.51 | 0.001 | +0.89 +0.63 +0.11 −0.07 | +0.250 | NULL |
| W4 rating change | 1,862 | −0.011 | −0.077 | −0.05 | 0.941 | −0.03 +0.03 −0.27 +0.23 | −0.151 | UNDERPOWERED |

* **The planted 0.50% control** shows at t = 5.38 (W1), 3.62 (W2), 3.22 (W3)
  and 2.30 (W4).
* **The smallest detectable effect** at the bar is 0.36%, 0.53%, 0.60% and
  0.83%.
* **The secondary horizons agree in sign.**
  * W1: +0.32% at 5 sessions, +0.44% at 20.
  * W3: +0.35% at 5, +0.47% at 20.
  * Neither can rescue anything on its own.

## W1's pass is an artifact of FMP's report dates

**The registered premise fails.** The registration says everything is known at
the entry close: the close of the first session after FMP's report date. That
holds only if FMP's date is the day the report came out.

**What the first run showed.** Signed by the surprise and market-adjusted, the
daily returns run:

| day vs entry | −1 (report) | 0 (entry day) | +1 | +2 | +3 … +10, summed |
|---|---:|---:|---:|---:|---:|
| 2012 on | +0.93 | +1.12 | +0.14 | +0.07 | ≈ 0 |
| before 2012 | +0.97 | +0.71 | +0.32 | +0.15 | ≈ +0.2 |

The "10-day drift" is almost all the two sessions after entry. That is a
spill-over from the announcement window, not a drift over weeks.

**The check: where is each report's volume spike?** (`volume_peak`)
* On the report's own session or D1, the date is right and the entry follows
  the reaction.
* In the three sessions after the entry, FMP's date is early: the replay
  entered with the surprise in hand BEFORE the market reacted. That is
  look-ahead.

| Reports whose volume peak falls after the entry | share |
|---|---:|
| before 2012 (4,396) | 47.5% |
| 2012 on (8,165) | 36.0% |

**W1 at 10 sessions, by whether the volume confirms the date:**

| | 2012 on | before 2012 |
|---|---|---|
| date confirmed | **+0.019%, t = 0.13** (n = 2,911) | +0.580%, t = 3.29 (n = 1,229) |
| peak after entry (date early) | +0.492%, t = 2.14 (n = 1,493) | +0.711%, t = 3.23 (n = 916) |

**So:**
* **Since 2012**, on reports whose date is right, the drift is zero. The
  2012-on W1 figure (+0.18%, t = 1.48) is the real reaction on misdated
  reports, seen by the replay before the market saw it.
* **Before 2012**, correctly dated reports drifted +0.58%. That matches the
  Canadian literature for 1994–2009 (Chudek, Truong and Veeraraghavan 2011),
  and the drift has been arbitraged away since (Martineau 2022). Survivorship
  also leans this way: today's 150 names are the ones that kept rising, and
  the selection is strongest furthest back.
* **This check was added after the first run.** It is a check that the
  registered premise holds, not a new hypothesis, and never a trading rule:
  the volume after entry is not known at entry.

The registered W1 verdict is recorded as it fell, DRIFT, with the premise
shown to fail. It is **REJECTED as an edge (#50)**.

## Descriptive splits (W1, H = 10; no verdict)

* **Legs:** long +0.50% (t = 3.54), short +0.16% (t = 0.89). The long side
  carries it, which is survivorship's direction.
* **Liquidity:** the most liquid third +0.10% (t = 0.78); middle +0.56%; least
  +0.33%.
* **Sector:**
  * energy +0.56% (t = 1.79);
  * financials +0.27% (1.88);
  * mining −0.08%;
  * technology +0.43% (0.83);
  * the rest +0.52% (4.06).
* **Market at entry:** XIU above its 50-session average +0.31%; below +0.38%.
  The owner's macro split shows nothing.
* **Busy report days** (10+ names): +0.17% against +0.40% on quieter days.
* **Revenue surprise on the same side:** +0.29% against +0.35%. Agreement adds
  nothing.

## What it means for the owner's question

* **Holding for weeks does not rescue the edge on these names.** With the
  timing right, a TSX-150 earnings surprise is priced within about two
  sessions, and since 2012 nothing follows.
  * The reaction-signed version (W2) is flat, as day-85 found on US names.
  * Rating changes (W4) show nothing at 1–4 weeks, but cannot rule out an
    effect below 0.8%.
* **A data lesson that outlives this study.** Any earnings backtest on FMP's
  historical report dates will look profitable through look-ahead, because a
  third of the dates are early. A real test needs the issuer's own
  timestamps. The newswire archive (day-118) has them, but only from
  2026-07.
* **Nothing is proposed.** The registration attached a forward shadow desk to
  a DRIFT verdict. The pass is an artifact, and the measured clean effect
  (+0.02%) is far below anything a forward record could confirm. Building it
  anyway is the owner's call.
