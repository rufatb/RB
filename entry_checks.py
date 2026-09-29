"""ENTRY CHECKS — two consistency rules applied at 09:46 to the Top 2 and the
debate's final (PREREGISTER_day120_entry_checks.md).

  E1 void at entry  the 09:46 mark is already past the pick's own "wrong if"
  E2 conflict       the models put the name on opposite sides this morning

Pure functions; no fetch. A missing quote or level is NOT CHECKED, never a
pass or a fail. These are not signals and claim no accuracy.
"""
from __future__ import annotations

RULE_VERSION = 'day120-entry'
USABLE = ('OK', 'CORROBORATED')


def marks(quotes):
    """{ticker: 09:46 mid} from validated quotes; unusable quotes are left out."""
    out = {}
    for t, q in (quotes or {}).items():
        if isinstance(q, dict) and q.get('status') in USABLE and isinstance(q.get('mark'), (int, float)):
            out[t] = float(q['mark'])
    return out


def check(side, level, price):
    """'VOID' | 'OK' | 'NOT CHECKED' (no level, no price)."""
    if not isinstance(level, (int, float)) or not isinstance(price, (int, float)):
        return 'NOT CHECKED'
    crossed = price < level if side == 'LONG' else price > level
    return 'VOID' if crossed else 'OK'


def conflicted(pairs):
    """Tickers that appear on both sides among (ticker, side) pairs."""
    sides = {}
    for t, s in pairs:
        sides.setdefault(t, set()).add(s)
    return {t for t, s in sides.items() if len(s) > 1}
