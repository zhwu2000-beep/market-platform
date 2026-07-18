"""Deterministic summaries for historical replay results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from market_platform.replay.models import HistoricalReplayResult, ReplayStrategyIdentity
from market_platform.strategy.models import StrategyEvaluationStatus


@dataclass(frozen=True, slots=True)
class StrategyReplaySummary:
    """Read-only status summary for one replayed strategy."""

    strategy: ReplayStrategyIdentity
    step_count: int
    applicable_count: int
    not_applicable_count: int
    insufficient_data_count: int
    first_applicable_as_of: datetime | None
    last_applicable_as_of: datetime | None
    status_transition_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, ReplayStrategyIdentity):
            raise TypeError("strategy must be a ReplayStrategyIdentity")
        for field_name in (
            "step_count",
            "applicable_count",
            "not_applicable_count",
            "insufficient_data_count",
            "status_transition_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")
        total = (
            self.applicable_count
            + self.not_applicable_count
            + self.insufficient_data_count
        )
        if total != self.step_count:
            raise ValueError("status counts must sum to step_count")
        first = _normalize_optional_timestamp(
            self.first_applicable_as_of, "first_applicable_as_of"
        )
        last = _normalize_optional_timestamp(
            self.last_applicable_as_of, "last_applicable_as_of"
        )
        if (first is None) != (last is None):
            raise ValueError("first and last applicable timestamps must both be set")
        if first is not None and last is not None and first > last:
            raise ValueError("first_applicable_as_of must not be later than last")
        object.__setattr__(self, "first_applicable_as_of", first)
        object.__setattr__(self, "last_applicable_as_of", last)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible strategy replay summary."""

        return {
            "strategy": self.strategy.to_dict(),
            "step_count": self.step_count,
            "applicable_count": self.applicable_count,
            "not_applicable_count": self.not_applicable_count,
            "insufficient_data_count": self.insufficient_data_count,
            "first_applicable_as_of": self.first_applicable_as_of.isoformat()
            if self.first_applicable_as_of is not None
            else None,
            "last_applicable_as_of": self.last_applicable_as_of.isoformat()
            if self.last_applicable_as_of is not None
            else None,
            "status_transition_count": self.status_transition_count,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplaySummary:
    """Read-only deterministic summary of a historical replay result."""

    symbol: str
    interval: str
    start_as_of: datetime | None
    end_as_of: datetime | None
    step_count: int
    strategies: tuple[StrategyReplaySummary, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(
            self, "interval", _normalize_required_text(self.interval, "interval")
        )
        object.__setattr__(
            self,
            "start_as_of",
            _normalize_optional_timestamp(self.start_as_of, "start_as_of"),
        )
        object.__setattr__(
            self,
            "end_as_of",
            _normalize_optional_timestamp(self.end_as_of, "end_as_of"),
        )
        if (
            self.start_as_of is not None
            and self.end_as_of is not None
            and self.start_as_of > self.end_as_of
        ):
            raise ValueError("start_as_of must be earlier than or equal to end_as_of")
        if isinstance(self.step_count, bool) or not isinstance(self.step_count, int):
            raise TypeError("step_count must be an integer")
        if self.step_count < 0:
            raise ValueError("step_count must not be negative")
        strategies = _normalize_strategy_summaries(self.strategies)
        for strategy in strategies:
            if strategy.step_count != self.step_count:
                raise ValueError("strategy summary step_count must match summary")
        object.__setattr__(self, "strategies", strategies)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible replay summary."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "start_as_of": self.start_as_of.isoformat()
            if self.start_as_of is not None
            else None,
            "end_as_of": self.end_as_of.isoformat()
            if self.end_as_of is not None
            else None,
            "step_count": self.step_count,
            "strategies": [strategy.to_dict() for strategy in self.strategies],
        }


def summarize_historical_replay(
    result: HistoricalReplayResult,
) -> HistoricalReplaySummary:
    """Summarize strategy evaluation statuses without rerunning replay."""

    if not isinstance(result, HistoricalReplayResult):
        raise TypeError("result must be a HistoricalReplayResult")

    strategy_summaries = tuple(
        _summarize_strategy(result, strategy_index, strategy)
        for strategy_index, strategy in enumerate(result.strategies)
    )
    return HistoricalReplaySummary(
        symbol=result.symbol,
        interval=result.interval,
        start_as_of=result.start_as_of,
        end_as_of=result.end_as_of,
        step_count=result.step_count,
        strategies=strategy_summaries,
    )


def _summarize_strategy(
    result: HistoricalReplayResult,
    strategy_index: int,
    strategy: ReplayStrategyIdentity,
) -> StrategyReplaySummary:
    statuses: list[StrategyEvaluationStatus] = []
    first_applicable_as_of: datetime | None = None
    last_applicable_as_of: datetime | None = None
    applicable_count = 0
    not_applicable_count = 0
    insufficient_data_count = 0
    status_transition_count = 0
    previous_status: StrategyEvaluationStatus | None = None

    for step in result.steps:
        evaluations = step.strategy_result.evaluations
        if len(evaluations) != len(result.strategies):
            raise ValueError("step evaluation count must match replay strategies")
        evaluation = evaluations[strategy_index]
        _validate_evaluation_identity(evaluation.provenance, strategy)
        status = evaluation.status
        statuses.append(status)
        if previous_status is not None and status is not previous_status:
            status_transition_count += 1
        previous_status = status
        if status is StrategyEvaluationStatus.APPLICABLE:
            applicable_count += 1
            if first_applicable_as_of is None:
                first_applicable_as_of = step.as_of
            last_applicable_as_of = step.as_of
        elif status is StrategyEvaluationStatus.NOT_APPLICABLE:
            not_applicable_count += 1
        elif status is StrategyEvaluationStatus.INSUFFICIENT_DATA:
            insufficient_data_count += 1
        else:  # pragma: no cover - defensive for future enum extension
            raise ValueError(f"unsupported strategy evaluation status: {status}")

    return StrategyReplaySummary(
        strategy=strategy,
        step_count=len(statuses),
        applicable_count=applicable_count,
        not_applicable_count=not_applicable_count,
        insufficient_data_count=insufficient_data_count,
        first_applicable_as_of=first_applicable_as_of,
        last_applicable_as_of=last_applicable_as_of,
        status_transition_count=status_transition_count,
    )


def _validate_evaluation_identity(
    provenance: object,
    strategy: ReplayStrategyIdentity,
) -> None:
    strategy_id = getattr(provenance, "strategy_id", None)
    strategy_version = getattr(provenance, "strategy_version", None)
    configuration_fingerprint = getattr(provenance, "configuration_fingerprint", None)
    if strategy_id != strategy.strategy_id:
        raise ValueError("evaluation strategy_id must match replay strategy identity")
    if strategy_version != strategy.strategy_version:
        raise ValueError(
            "evaluation strategy_version must match replay strategy identity"
        )
    if configuration_fingerprint != strategy.configuration_fingerprint:
        raise ValueError(
            "evaluation configuration_fingerprint must match replay strategy identity"
        )


def _normalize_strategy_summaries(
    value: object,
) -> tuple[StrategyReplaySummary, ...]:
    if isinstance(value, tuple):
        summaries = value
    elif isinstance(value, list):
        summaries = tuple(value)
    else:
        raise TypeError("strategies must be a tuple or list")
    for summary in summaries:
        if not isinstance(summary, StrategyReplaySummary):
            raise TypeError("strategies elements must be StrategyReplaySummary")
    return summaries


def _normalize_symbol(value: object) -> str:
    return _normalize_required_text(value, "symbol").upper()


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_optional_timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _normalize_timestamp(value, field_name)


__all__ = [
    "HistoricalReplaySummary",
    "StrategyReplaySummary",
    "summarize_historical_replay",
]
