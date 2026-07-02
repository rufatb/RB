"""
risk.py — risk-first sizing and cost math.

HONESTY CONSTRAINT (do not strip):
    Position size is derived from STOP DISTANCE and account risk %, never from
    conviction. A high-conviction feeling does not buy you a bigger position;
    a tighter, well-defined stop does. Overnight gap risk and margin carry cost
    are made explicit because they are the costs people forget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RiskPlan:
    entry: float
    stop: float
    side: str                     # 'long' or 'short'
    risk_dollars: float
    stop_distance: float
    shares: int
    position_value: float
    r_multiples: list = field(default_factory=list)   # [(target_name, level, R)]
    overnight_margin_cost: Optional[float] = None
    gap_risk: list = field(default_factory=list)       # [(gap_pct, $impact)]
    notes: list = field(default_factory=list)


def position_size(
    *,
    account_equity: float,
    risk_per_trade_pct: float,
    entry: float,
    stop: float,
    side: str = "long",
    max_position_pct: float = 100.0,
) -> RiskPlan:
    """
    Shares = (equity × risk%/100) / per-share stop distance.
    The position size FALLS OUT of the stop — that is the whole point.

    max_position_pct caps position VALUE as a % of equity. WHY: a very tight
    stop makes the risk formula balloon the share count (seen live: a $0.12
    stop implied a $102k position on $100k equity). Tight stop ≠ license to
    lever up; the cap binds first and is noted on the plan.
    """
    risk_dollars = account_equity * (risk_per_trade_pct / 100.0)
    stop_distance = abs(entry - stop)
    notes = []
    if stop_distance <= 0:
        return RiskPlan(
            entry=entry, stop=stop, side=side, risk_dollars=risk_dollars,
            stop_distance=0.0, shares=0, position_value=0.0,
            notes=["stop distance is zero — cannot size a position"],
        )
    shares = int(risk_dollars // stop_distance)
    max_value = account_equity * (max_position_pct / 100.0)
    if entry > 0 and shares * entry > max_value:
        shares = int(max_value // entry)
        actual_risk = shares * stop_distance
        notes.append(
            f"position capped at {max_position_pct:.0f}% of equity "
            f"(risk-formula size exceeded it; actual $ at stop ≈ {actual_risk:.0f})"
        )
    position_value = shares * entry
    return RiskPlan(
        entry=entry, stop=stop, side=side, risk_dollars=risk_dollars,
        stop_distance=stop_distance, shares=shares, position_value=position_value,
        notes=notes,
    )


def add_r_multiples(plan: RiskPlan, targets: list) -> RiskPlan:
    """targets: list of (name, level). R = reward/risk per share."""
    if plan.stop_distance <= 0:
        return plan
    for name, level in targets:
        if level is None:
            continue
        if plan.side == "long":
            reward = level - plan.entry
        else:
            reward = plan.entry - level
        r = reward / plan.stop_distance
        plan.r_multiples.append((name, level, r))
    return plan


def overnight_margin_cost(
    plan: RiskPlan,
    *,
    is_margin: bool,
    cad_prime: float,
    margin_spread: float,
    borrowed_fraction: float = 1.0,
) -> RiskPlan:
    """
    Overnight carry on borrowed funds:
        cost/day = borrowed × (prime + spread)/100 / 365

    borrowed_fraction lets you model partial margin use. If not on margin, the
    cost is zero — but we still attach the field so the brief is explicit.
    """
    if not is_margin:
        plan.overnight_margin_cost = 0.0
        plan.notes.append("cash account — no overnight margin cost")
        return plan
    annual_rate = (cad_prime + margin_spread) / 100.0
    borrowed = plan.position_value * borrowed_fraction
    plan.overnight_margin_cost = borrowed * annual_rate / 365.0
    return plan


def gap_risk_table(plan: RiskPlan, gaps_pct=(1.0, 2.0)) -> RiskPlan:
    """
    What an overnight gap AGAINST the position costs in dollars.
    A stop does not protect you across a gap — this is why it's surfaced.
    """
    for g in gaps_pct:
        impact = plan.position_value * (g / 100.0)
        plan.gap_risk.append((g, -abs(impact)))
    return plan


def build_full_plan(
    *,
    account_equity: float,
    risk_per_trade_pct: float,
    entry: float,
    stop: float,
    side: str,
    targets: list,
    is_margin: bool,
    cad_prime: float,
    margin_spread: float,
    max_position_pct: float = 100.0,
) -> RiskPlan:
    """Convenience: full risk picture for a hypothetical trigger->stop trade."""
    plan = position_size(
        account_equity=account_equity,
        risk_per_trade_pct=risk_per_trade_pct,
        entry=entry, stop=stop, side=side,
        max_position_pct=max_position_pct,
    )
    plan = add_r_multiples(plan, targets)
    plan = overnight_margin_cost(
        plan, is_margin=is_margin, cad_prime=cad_prime, margin_spread=margin_spread
    )
    plan = gap_risk_table(plan)
    return plan
