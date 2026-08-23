# data/ — derived research artifacts, committed on purpose

Everything here is DERIVED, not raw: each file is the output of a harvester in
this repo, reproducible from public sources with the command named beside it.
None of it is licensed data and none of it is a price feed.

## Why these are committed rather than left in the scratch directory

The container this repo runs in is recycled between sessions. It happened four
times while day-70 and day-71 were being built, and each time it destroyed
`catalyst_events.csv` — forty minutes of EDGAR full-text search — along with
every number computed from it. The failure mode is worse than the lost time:
`brief.py` degrades quietly. The base rate goes missing, `screen.py` falls back
to "no base rate has been computed", and the morning report is thinner than it
was yesterday for a reason that has nothing to do with the market.

A file that takes forty minutes to rebuild, changes a few times a year, and is
depended on by the report every single morning belongs in the repository.

## What is here

| file | rebuilt by | what it is |
|---|---|---|
| `catalyst_events.csv` | `python build_catalyst.py --start 2015 --end 2026` | every 8-K that ANNOUNCES an FDA rejection or approval, 2015-2026, verified by `classify.py` |
| `baserate.json` | `python baserate.py` | P(CRL) with its coverage audit and sponsor strata |

## Refreshing

Both are append-mostly: new events arrive as companies file. Re-run the
harvester when the newest event is more than a month old, then re-run
`baserate.py` and commit both together — they must not drift apart, since the
second is computed entirely from the first.
