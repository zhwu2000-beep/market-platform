"""Pure deterministic stage-gated structural risk evaluation."""

from __future__ import annotations

from market_platform.risk.context import RiskEvaluationContext
from market_platform.risk.decision import (
    RiskDecision,
    _canonical_structural_risk_result,
    _create_risk_decision_from_canonical_result,
)


def evaluate_structural_risk(context: RiskEvaluationContext) -> RiskDecision:
    """Evaluate structural eligibility without financial or external effects."""

    result = _canonical_structural_risk_result(context)
    return _create_risk_decision_from_canonical_result(context, result)


__all__ = ["evaluate_structural_risk"]
