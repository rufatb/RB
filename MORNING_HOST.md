# Morning execution without a chat session

The 2026-11-11 Claude worker stall queued the 08:50 trigger until 09:21.
Preparation began at 09:23, missed its staging budgets, and no Claude brief or
DDA research pass was created. An empty council is not a consensus decision.

`morning_service.py` is an **opt-in replacement**, not an installed service.
It starts `morning_full.sh` at 08:50 on a persistent Linux host and polls the
existing decision/open-check composition functions. Their HTML is sent over
the host's SMTP transport. `morning.sh` retains its existing immutable report
delivery and record publication. The model routes, ordering and cutoffs stay
the same. No strategy or trade is introduced.

If the 09:00 decision is not ready, the sender sends one explicit readiness
notice, while preparation continues. It does not claim a crash or that a future
09:46 publication failed. A ready decision can follow. Recovery research sent
before 09:46 uses `RB Recovery Research`, so it cannot satisfy the existing
daily-report duplicate search and suppress the later report.

The host needs the existing DeepSeek, OpenRouter, Gemini and FMP credentials in
environment variables or persistent `$RB_STATE_DIR/secrets/` files. It also
needs its own Gmail app password or another configured SMTP account, sender and
recipient (`smtp_credential.py`). **A Gmail connector in Claude does not supply
those server credentials.** Do not copy connector tokens or put keys in git.

Use the existing `/opt/RB` installation and `/etc/rb-report.env` instructions in
`RUNBOOK.md`. Add the explicit existing DeepSeek model to the environment; do
not silently change the account's configured model. Check without sending:

```bash
/opt/RB/.venv/bin/python /opt/RB/morning_service.py --state-dir /var/lib/rb-report --check
```

Before activation, run that check with the service's environment loaded, verify
SMTP connectivity/authentication on the host, and make one deliberate test send
with the owner's authorization. Review the first morning's logs and inbox.
This document does not claim that any of those live checks happened.

Cut over exactly one writer: disable the old `rb-report.timer` and the Claude
08:50/watchdog/bridge senders before enabling `rb-morning.timer`. The old
08:12 pre-open Routine can still collect research; the full morning also keeps
its existing second read. Do not run the two report orchestrators together.

```bash
sudo cp /opt/RB/deploy/rb-morning.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl disable --now rb-report.timer
# Disable the old Claude morning and fallback senders during the same cutover.
sudo systemctl enable --now rb-morning.timer
systemctl list-timers rb-morning.timer
journalctl -u rb-morning.service
```

These are operator cutover commands, not an installer invoked by this patch.
The timer uses Eastern time and does not replay a missed morning after boot.
Timing semantics: [systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html).
There is one durable daily run claim and per-message send claims. A send with
an uncertain outcome requires Sent reconciliation using its deterministic
Message-ID; it is never retried automatically. Credentials, claims, heartbeats
and raw logs remain private in the persistent state directory.
