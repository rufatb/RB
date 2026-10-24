# Review brief for Muse: rufatb/RB, day-138 to day-139

## Where

* **Repository:** https://github.com/rufatb/RB
* **Branch:** `claude/session-rw51c2`. It mirrors `main` exactly; every change
  goes to `main` and is then force-pushed to this branch. Reviewing either
  gives the same commits.
* **Range to review:** everything after `a21df62` (the day-137b notes) up to
  the branch tip:
  https://github.com/rufatb/RB/compare/a21df62...claude/session-rw51c2
* **Code and research commits:**

  | Commit | What |
  |---|---|
  | 4fb0885 | day-138 registration (E1–E4) |
  | f5f8a9d | day-138 amendment 1: E1's rule on the point-in-time S&P 500, registered before it ran |
  | d00c554 | day-138 results: `replay_events.py`, its tests, the summary JSON, audit, docs |
  | b77c699 | day-138b: the owner's spreadsheet read against the records (docs only) |
  | 42efb37 | day-139 registration: the news desk asked before the open |
  | the tip | day-139: `news_desk.py --preopen`, the 09:20 step in `morning_full.sh`, the evening review section, tests, docs, this brief |

* **Record commits** (`record: …`) are the scheduled runs' data. They should
  touch only these files and only fill empty cells:
  * `ledger.csv`, `universe_prints.csv`;
  * `data/model_picks.csv`, `data/newswire/`, `data/gap_calls.csv`,
    `data/pead_calls.csv`, `data/news_calls.csv`, `data/reviews/`.

## What the project is

Read-only research: a morning report of language-model stock picks on 150
TSX names, with a scoreboard. Nothing in it places, changes or cancels an
order.

Every change is registered before it is tested (`PREREGISTER_*.md`), and the
bar is never moved after. Read the top three sections of `CLAUDE.md` first.

## What to check, in order

1. **Registration before results.**
   * In `git log`, each `PREREGISTER_*` commit comes before the results it
     governs: 4fb0885, then f5f8a9d, then d00c554; and 42efb37 before any
     pre-open code or call.
   * `git log -p PREREGISTER_day138_events.md`: nothing above "Results"
     changed after the results were computed.
2. **`replay_events.py` does what `PREREGISTER_day138_events.md` says.**
   * **Window:** enter at the close of P0 (the last session before the
     report date), exit at the close of D1 + 2; y = the stock's return minus
     XIU's.
   * **No future data in a side.**
     * E2 uses only a report 30–200 days earlier.
     * E3 uses only peers whose reports are public at least 5 sessions
       before P0, within 30 days.
   * **Placebo:** the same name and side, random windows within ±250
     sessions, never within 10 sessions of the name's reports.
     * Excess is the events' mean minus the placebo mean.
     * t is the smaller |t| of name and week clustering.
     * The PASS conditions are exactly as registered.
   * **E1-US:** `sp500_membership` rebuilds the S&P 500 backwards from FMP's
     change history.
     * Intervals start inclusive and end exclusive; check replacement
       records.
     * An event is kept only when the name was a member at P0.
   * **E1 is "not adopted"** because E1-US is NULL (amendment 1); check the
     audit says so and nothing ships.
3. **`news_desk.py`, day-139.**
   * **Timing guards.** `stage_preopen` refuses at or after 09:30, and drops
     an answer received at or after 09:30.
   * **Window and prompt.** The window is cut at the moment of asking
     (`events(until=)`). The prompt is unchanged (`SYSTEM_PROMPT`, pinned by
     `test_the_prompt_is_the_registered_one_verbatim`).
   * **The new column.** `asked_at` is the LAST column of
     `data/news_calls.csv`. Existing values never change; confirm `_write`
     cannot drop or reorder a filled value.
   * **Scoring.** `score()` fills `preopen` rows on the same yardstick, and
     `record_line` (the day-122 test) still counts the FULL arm only.
4. **`morning_full.sh`.** The 09:20 step must never delay the 09:30 staging
   cutoff or the 09:46 publication.
   * Its timeout is at most 480 s, and it ends by 09:29.
   * It is never started with no budget: `timeout 0` would mean no timeout.
   * Its failure is not added to `stage_faults`.
5. **No secrets.** `git grep -nE 'sk-[A-Za-z0-9]{20,}|sk-or-v1-[0-9a-f]{20,}'`
   must find nothing. Credentials live only in `.rb-state/secrets/`, which is
   gitignored.
6. **Record commits** only fill blanks: compare filled cells before and after
   each one.
7. **Statistics.** The clustering is by session or name. The survivorship
   argument for E1 (names still in the index +0.15%, since removed −0.65%)
   follows from the committed `data/replay_day138_events.json`.

## How to run

* Python 3.11, then `pip install -r requirements.txt`.
* **The suite:** `python -m pytest -q tests/`. About 3,090 tests, around ten
  minutes, with no network: `tests/conftest.py` points every test at empty
  archives and state.
* **Just the changed parts:**
  `python -m pytest -q tests/test_replay_events.py tests/test_news_desk.py tests/test_morning_full.py tests/test_daily_review.py`
* **Do not rerun the studies.** They need an FMP key and cached data that are
  not in the repository. Review the code and the committed summary JSON.

## Rules for the review

* Read-only research: never add anything that submits, modifies or cancels an
  order.
* Do not change a registered bar, a prompt, a recorded value or a scheduled
  Routine. Propose changes; do not push them to `main`.
* Never commit or print a credential.
* **Report:**
  * findings ranked by severity, each with file:line, what is wrong, and a
    concrete case where it fails;
  * "no findings" if there are none.
* **Where to put it:** a GitHub issue on rufatb/RB titled "Muse review:
  day-138/139", or comments on the commits above.
