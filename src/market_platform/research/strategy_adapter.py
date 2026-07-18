"""Research-owned projections of strategy evaluation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from market_platform.research.models import ResearchSerializable
from market_platform.strategy.models import StrategyRunResult


@dataclass(frozen=True, slots=True)
class ResearchStrategyAssessment(ResearchSerializable):
    """Display-oriented research projection of one strategy evaluation."""

    strategy_id: str
    strategy_version: str
    status: str
    rationale: str
    evidence_count: int
    as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strategy_id",
            _normalize_required_text(self.strategy_id, "strategy_id"),
        )
        object.__setattr__(
            self,
            "strategy_version",
            _normalize_required_text(
                self.strategy_version,
                "strategy_version",
            ),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_required_text(self.status, "status"),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_required_text(self.rationale, "rationale"),
        )
        if isinstance(self.evidence_count, bool) or not isinstance(
            self.evidence_count,
            int,
        ):
            raise TypeError("evidence_count must be an integer")
        if self.evidence_count < 0:
            raise ValueError("evidence_count must not be negative")
        if not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a datetime")
        if self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        object.__setattr__(self, "as_of", self.as_of.astimezone(UTC))


def adapt_strategy_run_result(
    result: StrategyRunResult,
) -> tuple[ResearchStrategyAssessment, ...]:
    """Project strategy evaluations into research-owned assessments."""

    if not isinstance(result, StrategyRunResult):
        raise TypeError("result must be a StrategyRunResult")
    return tuple(
        ResearchStrategyAssessment(
            strategy_id=evaluation.provenance.strategy_id,
            strategy_version=evaluation.provenance.strategy_version,
            status=evaluation.status.value,
            rationale=evaluation.rationale,
            evidence_count=len(evaluation.evidence),
            as_of=evaluation.as_of,
        )
        for evaluation in result.evaluations
    )


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


__all__ = ["ResearchStrategyAssessment", "adapt_strategy_run_result"]
