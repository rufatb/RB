# September 10 delivery recovery

The morning publication was preserved. Its intraday worker timed out after
22 seconds; the independent equity section failed with URLError. This is an
unevaluated scan, not evidence that the market offered no opportunities.
The original diagnostics cannot establish which internal intraday stage
consumed that deadline.

Inspection found that Yahoo's two-host fallback allowed twenty seconds per
host inside that 22-second process budget. With 21 symbols and eight threads,
multiple request waves could exceed the budget before calibration returned.
Prepared-cache requests now use two seconds per host. Fixed stage and ticker
observations survive worker termination; successful sibling sections remain
independent. Training data order, scoring, selection and sizing are unchanged.
This repairs a budget mismatch; it does not prove it was the only cause of the
observed timeout or establish that a live request can complete.

The default brief configuration now resolves from its source directory.
`runtime_check.py` verifies the exact interpreter, imports and revision before
the report window. Both changes address observed startup failures; passing
the check certifies neither feed entitlements nor a minute-level delivery SLA.

A bounded Yahoo connectivity probe in the recovery environment was cancelled
before network approval. It received no provider HTTP response. No bypass or
repeat acquisition was used. EODHD's previously saved transport gap remains
distinct from provider denial and from improved predictions.

An explicit recipient request can authorize one informational replacement.
The replacement has its own immutable body, digest and unique delivery claim;
the original publication and sent record remain untouched. A durable claim
must precede Gmail transmission. A successful send records the actual Gmail
ID; ambiguous outcomes require Sent reconciliation, never blind retry.

This work adds no strategy, research adoption, new inferred holding or
backdated morning signal. Latest main research rejections and operational
updates are retained. The recorded ZYME close on September 10 is a ledger fact,
not independent brokerage verification.
