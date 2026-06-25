"""
analyst.py — optional Claude-powered analysis layer.

WHAT IT IS: a second pair of eyes that reads the SAME computed, real metrics the
deterministic engine produced and writes an honest narrative — pattern
observations a human might miss, which levels matter and why, and risk
considerations. It can reason over the deep history summary from patterns.py.

WHAT IT IS NOT (hard guardrails, do not strip):
    * It does NOT own the verdict or the probability. Those are computed
      deterministically in dashboard.py and CLAMPED to [0.35, 0.65]. The analyst
      is explicitly instructed it may not emit its own probability, may not tell
      the user to override the capped read, and may not manufacture confidence.
      Its output is labelled "advisory context" and is additive only — the
      calling code never lets it mutate `decision`.
    * It does NOT invent data. It is given only what was measured; it is told to
      say "unavailable" rather than guess, and that momentum/relative-strength
      are context, not signals.
    * It degrades gracefully: no API key -> a clear "analyst disabled" stub, the
      rest of the brief is unaffected.

Model: claude-opus-4-8 with adaptive thinking (see Anthropic docs / claude-api).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional


# This system prompt is load-bearing: it transmits the tool's honesty contract to
# the model. Edit with the same care as the in-code guardrails.
SYSTEM_PROMPT = """You are the advisory layer of an intraday decision-support tool \
for a single stock (default: Air Canada, AC.TO on the TSX). You were built by a \
trader who has watched AI models manufacture confident intraday calls that flip \
with the price. Your job is the opposite of that.

NON-NEGOTIABLE RULES:
1. You do NOT produce a directional verdict or a probability. A separate \
deterministic engine already computed an honest, CAPPED probability (clamped to \
[0.35, 0.65], default 0.50) and a verdict (BULL LEAN / BEAR LEAN / NO EDGE — \
WAIT). You must NOT output your own probability number, must NOT tell the user to \
override or ignore the capped read, and must NOT imply higher confidence than the \
engine. Open-to-close direction on a single name is near a coin flip; respect that.
2. Never invent data. If a metric is 'unavailable', say so. Treat momentum, \
relative strength, and correlated tickers as CONTEXT, not signals. Historical \
base rates are base rates, not forecasts — always note the sample size when you \
lean on one.
3. Be useful where it matters: invalidation levels and confirmation triggers \
("wait for X to break/hold"), risk considerations, and pattern observations a \
casual reader would miss. Levels beat predictions.
4. Be concise and honest. If the data says 'no edge', say 'no edge' — do not \
invent a narrative to fill space. Flag spike-fade / failed-breakout structure \
prominently when present; those precede chop.

Output PLAIN TEXT with these sections, each 1-4 tight sentences (omit a section \
if there is genuinely nothing honest to say):
PATTERN READ: — what the structure + history actually suggest (with sample sizes)
LEVELS TO WATCH: — the specific triggers/invalidations that matter today
RISK NOTES: — what would hurt, gap risk, what you're NOT seeing
WHAT I'D IGNORE: — noise the user might over-weight (momentum flips, thin samples)
You are advisory context, not the verdict."""


@dataclass
class AnalystResult:
    enabled: bool
    text: str
    model: Optional[str] = None
    error: Optional[str] = None


def _compact_brief(brief: dict) -> dict:
    """Extract only the real, computed numbers the analyst should reason over.

    We deliberately pass the engine's verdict/probability as READ-ONLY context so
    the model can explain them — not so it can change them."""
    d = brief.get("decision", {})
    s = brief.get("struct", {})
    orb = brief.get("orb", {})
    vw = brief.get("vwap", {})
    sf = brief.get("spike_fade", {})
    lv = brief.get("levels_actionable", {})
    ctx = brief.get("context", {})
    pat = brief.get("patterns", {})

    def thin_pattern(p):
        if not isinstance(p, dict):
            return p
        return {k: v for k, v in p.items() if k != "_label"}

    return {
        "ticker": brief.get("ticker"),
        "as_of": brief.get("generated_at"),
        "ENGINE_VERDICT_readonly": d.get("verdict"),
        "ENGINE_PROBABILITY_readonly": d.get("probability"),
        "ENGINE_CONVICTION_readonly": d.get("conviction"),
        "ENGINE_NAMED_FACTORS": d.get("factors"),
        "structure": s,
        "opening_range": {k: orb.get(k) for k in
                          ("orbN_low", "orbN_high", "pos_in_orb_pct", "available")},
        "vwap": {k: vw.get(k) for k in ("vwap", "price_vs_vwap_pct")},
        "spike_fade_flags": sf.get("flags"),
        "actionable_levels": lv,
        "context_only": ctx,
        "relative_strength": brief.get("rel_strength"),
        "history_patterns": {
            "history_days": pat.get("history_days"),
            "gap_statistics": thin_pattern(pat.get("gap_statistics", {})),
            "analog_days": thin_pattern(pat.get("analog_days", {})),
            "crude_regime": thin_pattern(pat.get("crude_regime", {})),
            "gap_continuation": thin_pattern(pat.get("gap_continuation", {})),
        },
        "net_buy_proxy": {k: v for k, v in (brief.get("proxy") or {}).items() if k != "_label"},
    }


def analyze(brief: dict, *, model: str = "claude-opus-4-8",
            max_tokens: int = 1500, enabled: bool = True) -> AnalystResult:
    """Run the Claude analyst. Returns a clearly-labelled stub if disabled/no key."""
    if not enabled:
        return AnalystResult(False, "(Claude analyst disabled by config/flag.)")

    # Guard FAILED upstream -> no directional context should be produced at all.
    if not brief.get("guard") or not getattr(brief["guard"], "passed", False):
        return AnalystResult(
            False,
            "(Claude analyst skipped: data integrity guard did not pass — no "
            "directional analysis is produced on unverified data.)",
        )

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return AnalystResult(
            False,
            "(Claude analyst unavailable: set ANTHROPIC_API_KEY to enable the "
            "Claude analysis layer. The deterministic brief above is unaffected.)",
        )

    try:
        import anthropic
    except Exception as e:
        return AnalystResult(False, f"(Claude analyst unavailable: {e})")

    payload = _compact_brief(brief)
    user_msg = (
        "Here is today's fully-computed brief for "
        f"{payload['ticker']} (every number is real and timestamped; the ENGINE_* "
        "fields are READ-ONLY — explain them, never override them):\n\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n\nWrite the advisory sections per your instructions. Remember: no "
        "probability of your own, levels over predictions, honesty over narrative."
    )

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},   # let Claude decide reasoning depth
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        if not text:
            return AnalystResult(False, "(Claude analyst returned no text.)", model=resp.model)
        return AnalystResult(True, text, model=resp.model)
    except Exception as e:  # network, auth, rate limit — never crash the brief
        return AnalystResult(False, f"(Claude analyst error: {e})", error=str(e))
