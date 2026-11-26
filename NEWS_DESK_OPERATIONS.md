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
| 09:31 | Reconcile CNW and the FMP cross-listed issuer feed through the overnight cutoff | `newswire.log`, `news_desk.log`, and `news_editions/<session>.press.json` |
| By 09:43 | Seal one edition with its explicit coverage status | `news_editions/<session>.morning.json` |
| 09:46 | Render and publish once from the frozen report | Report database and dated DDA export |
| 09:48 | Compare the frozen report, export and received Gmail HTML | `news_editions/<session>.delivery.json` and audit status |

On a persistent morning worker running the full morning routine, include the
three News Desk timers with `sudo deploy/install.sh --news-desk` after confirming
that the collector, report process, and delivery verification use the same
writable state directory. Include `--check --news-desk` in the status check and
add the failed units to the host's alerting. Use one designated primary sender.
The News Desk timers read and record status without sending email.
The existing interactive morning runner can use the final capture and edition
without the timers. Persistent capture and timed alerts require the host.

A verified quiet morning requires complete receipts from both configured
source reads. The FMP receipt gives the checked and expected counts for the
same-ISIN cross-listed universe. If FMP times out, returns unreadable rows, or
hits a cap inside the window, a morning with verified calls is marked
`PARTIAL`. An empty result with an incomplete source check is `UNAVAILABLE`.

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
