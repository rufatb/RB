# PREREGISTER day-119 — Top 2: the two names the models agree on most

Registered 2026-09-29, before the section's first live pick.

## What it is

The owner asked for two picks at the top of every email, long and/or short,
"that all language models agree are the opportunities of the day", never more
and never fewer than two. `top_picks.py` COUNTS agreement; it cannot create it.
* **Backing:** Claude's sealed selection, DeepSeek's selection (deepseek-v4-pro
  from 2026-09-29), and Jev's selection, forced pick or top-ranked name, all on
  the same side.
* **Ranking:** by the number of backing models; then by the strongest kind of
  backing (a selection, then a forced pick, then a ranked name); then by Jev's
  rank; then by the strongest single model's own number. Never an average.
* **Split names:** a name the models put on opposite sides goes last.

Each pick prints "k of n" and who backs it; "1 of 3" is printed as no agreement.

## What is recorded and how it is judged

Every Top 2 pick is recorded as `model_picks` model `top2`, kind `pick`, with
its `agreement`. It is scored on the desks' yardstick: the 09:45 bar close to
the 15:55 bar close, no costs. It is printed as the first scoreboard row.

At 40 live sessions (about 2026-11-24), the bar is the day-117 bar:
* the session-clustered mean per pick is > 0 with t ≥ 2.0;
* the hit rate beats random picks from the same session's pool (same
  long/short counts) at p < 0.05;
* the sign is the same in both halves of the sessions.

Split by agreement (3 of 3, 2 of 3, 1 of 3), the results are DESCRIPTIVE only:
at ~2 picks a session no split will be powered.

## Prior, stated up front

Day-117 found each model no better than random on these inputs, and day-118
found the open prices overnight releases. The three models read the same
brief, so their agreement is not independent evidence. The expected result is
a coin flip; the section is printed because the owner asked for it, and
nothing is sized from it.
