# Morning News Desk operations

The 09:46 report uses one frozen News Desk edition. The edition reads the CNW
archive, the durable worker archive and verified issuer releases saved by the
FMP pre-open job. The production edition records its own prompt version,
candidate counts, coverage, evidence, request and answer times, and seal.
The separate CNW research arm retains its registered inputs and scoreboard.

| Time ET | Worker check | Receipt |
|---|---|---|
| Overnight, every 10 minutes | Capture permitted CNW channels on a persistent host | `$RB_STATE_DIR/news_wire` and `newswire_reads.jsonl` |
| 08:40 | Run Yahoo, FMP and DeepSeek capability probes. Check the designated mail path. | `news_editions/<session>.preflight.json` |
| 09:31 | Reconcile the final overnight cutoff and prepare verified material calls | `newswire.log` and `news_desk.log` |
| By 09:43 | Seal one edition with its explicit coverage status | `news_editions/<session>.morning.json` |
| 09:46 | Render and publish once from the frozen report | Report database and dated DDA export |
| 09:48 | Compare the frozen report, export and received Gmail HTML | `news_editions/<session>.delivery.json` and audit status |

Enable the three News Desk timers on the existing persistent RB host after
installing their unit files and confirming that the collector, report process,
and delivery verification use the same writable state directory. Add their
failed unit statuses to the host’s alerting. Use one designated primary sender.
The capture, preflight, and audit timers are read-only with respect to email.
The existing interactive morning runner can use the final capture and edition
without the timers. Persistent capture and timed alerts require the host.

For connector delivery, obtain the full received HTML MIME part and record it
with `python news_edition.py verify-delivery --received-html PATH --message-id ID`.
The verification command expects the actual received HTML, separate from the
locally rendered dispatch file. A `RECONCILE` delivery plan requires checking
Sent for the existing primary report. An uncertain send needs operator
reconciliation before any retry. Keep the existing morning, bridge, and rescue
Routine prompts aligned with that rule.

When a partial or unavailable edition gains new verified material calls, run
`python news_edition.py final-capture` and `python news_edition.py addendum` before
16:00 ET. The addendum keeps its actual answer times. Export it separately
with `python dda_desk.py --export news-addendum --publish`. The designated sender
can claim it once with `python news_edition.py claim-addendum` and reply in the
original Gmail thread using the provider ID in the claim. The morning report,
website edition and research ledger keep their original timestamps.

On every deployment, replay `python -m pytest -q tests/test_news_edition.py
tests/test_dda_news_publication.py` and verify the actual host probes. A successful
public feed response covers its measured source window. Independent newswire
and issuer entitlements still determine the total universe the worker can see.
