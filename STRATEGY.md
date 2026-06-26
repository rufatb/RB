# Strategy & Lessons Learned

A living record of what went wrong in live trading and the rules now **encoded in
the tool** so the same mistakes get caught automatically. The tool's job is to
enforce discipline the trader won't always enforce under pressure.

---

## Day 1 post-mortem (AC.TO / SHOP.TO / CVE.TO)

### What happened
- **SHOP.TO long @ 159.64** — entered *inside* the no-trade zone (158.52–161.00),
  **below** the stated trigger (5-min hold above 161.00), on a name that had a
  **FADE WARNING** and was below VWAP. It was the *snapshot* scan leader at 09:50
  and had decayed to WAIT within 5 minutes. Exited shortly after (≈ scratch).
- **CVE.TO short** — entered while CVE was a live **BULL LEAN** (+1.2% over open,
  above VWAP, at session highs). Justified by the day-long base rate (≈72%
  close-down) + crude headwind — but price was already **off-sample** (outside
  the analog range), so that base rate didn't apply. It spiked further against
  the short into the afternoon.

### Root causes
1. **No confirmation discipline** — both entries front-ran / fought the trigger.
2. **Snapshot-chasing** — the 5-min scan leader rotated 8× in 30 min; a single
   snapshot was treated as a signal.
3. **Horizon/lens mismatch** — trading 5-min opening structure while intending to
   hold to 4pm, and acting when the lenses (structure / base rate / macro)
   *conflicted*.
4. **Ignoring off-sample** — acted on a base rate when today was nothing like the
   sample it came from.

---

## Rules now encoded in the tool

| Lesson | Where it lives | What it does |
|--------|----------------|--------------|
| Don't chase the rotating snapshot | `scan.py` **persistence filter** | A name is "actionable" only after holding the same verdict for `scan.min_persistence` consecutive scans (default 2). Raw leaders that haven't persisted show as "forming", not recommended. |
| Don't trade conflicting lenses | `metrics.eod_alignment` + brief/scan **EOD alignment** line | Combines intraday structure, the day-long analog base rate, and (optional) macro. `conflicted` → stand down. This flagged the live CVE short as "⛔ CONFLICTED — SHOP/CVE failure mode". |
| Don't trust an off-sample base rate | `patterns.analog_days` **off_sample** flag | When today's setup is outside the historical neighbour range, the base rate is marked UNRELIABLE and surfaced in the brief/scan. |
| Confirmation over front-running | existing **triggers + no-trade zone** | The brief always states "wait for X to break & 5-min hold"; entries inside the no-trade zone are, by construction, not the setup. |
| Respect the cap | existing **[0.35, 0.65] clamp** + backtest | Open-to-close is ~coin-flip; the backtest showed the engine is mildly overconfident. ~0.59 = a lean, size small. |
| Overnight = gap risk | `risk.py` **gap-risk table + margin carry** | A short held overnight has open-ended up-gap risk; the tool quantifies 1/2/3% gap impact and borrow cost. Exit on thesis-break rather than holding-and-hoping. |

---

## The checklist the tool now enforces before a name is "actionable"

1. **Data verified live** (integrity guard passes).
2. **Verdict is a lean** (not NO-EDGE — WAIT).
3. **Persisted** ≥ `min_persistence` consecutive scans (no snapshot-chasing).
4. **Lenses aligned** (not `conflicted`; ideally structure + base rate + macro agree).
5. **In-sample** (analog base rate not flagged off-sample).
6. **Entry only on the trigger** (5-min hold beyond the opening range), never
   inside the no-trade zone.
7. **Size from the stop**, honour the invalidation, and remember the cap — it's a
   lean, not a prediction.

If a setup fails any of these, the honest output is **WAIT / STAND DOWN**.
