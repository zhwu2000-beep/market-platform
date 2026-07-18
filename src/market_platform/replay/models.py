"""Immutable historical replay result models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from market_platform.state.models import MarketState
from market_platform.strategy.models import StrategyRunResult


@dataclass(frozen=True, slots=True)
class ReplayStrategyIdentity:
    """Immutable identity projection for one replayed strategy."""

    strategy_id: str
    strategy_version: str
    configuration_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strategy_id",
            _normalize_required_text(self.strategy_id, "strategy_id"),
        )
        object.__setattr__(
            self,
            "strategy_version",
            _normalize_required_text(self.strategy_version, "strategy_version"),
        )
        if self.configuration_fingerprint is not None:
            object.__setattr__(
                self,
                "configuration_fingerprint",
                _normalize_required_text(
                    self.configuration_fingerprint, "configuration_fingerprint"
                ),
            )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible strategy identity representation."""

        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "configuration_fingerprint": self.configuration_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayStep:
    """One point-in-time replayed state and strategy result."""

    symbol: str
    interval: str
    as_of: datetime
    observation_fingerprint: str
    state: MarketState
    strategy_result: StrategyRunResult

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(
            self, "interval", _normalize_required_text(self.interval, "interval")
        )
        object.__setattr__(self, "as_of", _normalize_timestamp(self.as_of, "as_of"))
        object.__setattr__(
            self,
            "observation_fingerprint",
            _normalize_required_text(
                self.observation_fingerprint, "observation_fingerprint"
            ),
        )
        if not isinstance(self.state, MarketState):
            raise TypeError("state must be a MarketState")
        if not isinstance(self.strategy_result, StrategyRunResult):
            raise TypeError("strategy_result must be a StrategyRunResult")
        _validate_step_identity(self)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible replay step representation."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "as_of": self.as_of.isoformat(),
            "observation_fingerprint": self.observation_fingerprint,
            "state": self.state.to_dict(),
            "strategy_result": self.strategy_result.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayResult:
    """Immutable result of replaying strategies across historical bars."""

    symbol: str
    interval: str
    start_as_of: datetime | None
    end_as_of: datetime | None
    steps: tuple[HistoricalReplayStep, ...]
    state_model_id: str
    state_model_version: str
    strategies: tuple[ReplayStrategyIdentity, ...]

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
        object.__setattr__(
            self,
            "state_model_id",
            _normalize_required_text(self.state_model_id, "state_model_id"),
        )
        object.__setattr__(
            self,
            "state_model_version",
            _normalize_required_text(self.state_model_version, "state_model_version"),
        )
        steps = _normalize_steps(self.steps)
        strategies = _normalize_strategy_identities(self.strategies)
        _validate_result_steps(self, steps, strategies)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "strategies", strategies)

    @property
    def step_count(self) -> int:
        """Return the number of replayed steps."""

        return len(self.steps)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible replay result representation."""

        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "start_as_of": self.start_as_of.isoformat()
            if self.start_as_of is not None
            else None,
            "end_as_of": self.end_as_of.isoformat()
            if self.end_as_of is not None
            else None,
            "state_model_id": self.state_model_id,
            "state_model_version": self.state_model_version,
            "strategies": [strategy.to_dict() for strategy in self.strategies],
            "steps": [step.to_dict() for step in self.steps],
        }


def _validate_step_identity(step: HistoricalReplayStep) -> None:
    state = step.state
    result = step.strategy_result
    if state.symbol != step.symbol:
        raise ValueError("step state symbol must match step symbol")
    if state.interval != step.interval:
        raise ValueError("step state interval must match step interval")
    if state.as_of != step.as_of:
        raise ValueError("step state as_of must match step as_of")
    if state.provenance.observation_fingerprint != step.observation_fingerprint:
        raise ValueError("step state fingerprint must match step fingerprint")
    if result.symbol != step.symbol:
        raise ValueError("step strategy result symbol must match step symbol")
    if result.interval != step.interval:
        raise ValueError("step strategy result interval must match step interval")
    if result.as_of != step.as_of:
        raise ValueError("step strategy result as_of must match step as_of")
    if result.observation_fingerprint != step.observation_fingerprint:
        raise ValueError("step strategy result fingerprint must match step fingerprint")
    if result.state_model_id != state.provenance.model_id:
        raise ValueError("step strategy result state_model_id must match state")
    if result.state_model_version != state.provenance.model_version:
        raise ValueError("step strategy result state_model_version must match state")


def _validate_result_steps(
    result: HistoricalReplayResult,
    steps: tuple[HistoricalReplayStep, ...],
    strategies: tuple[ReplayStrategyIdentity, ...],
) -> None:
    previous_as_of: datetime | None = None
    expected_ids = tuple(strategy.strategy_id for strategy in strategies)
    expected_versions = tuple(strategy.strategy_version for strategy in strategies)
    for step in steps:
        if step.symbol != result.symbol:
            raise ValueError("replay step symbol must match result symbol")
        if step.interval != result.interval:
            raise ValueError("replay step interval must match result interval")
        if previous_as_of is not None and step.as_of <= previous_as_of:
            raise ValueError("replay steps must be strictly ordered by as_of")
        previous_as_of = step.as_of
        if step.state.provenance.model_id != result.state_model_id:
            raise ValueError("replay step state_model_id must match result")
        if step.state.provenance.model_version != result.state_model_version:
            raise ValueError("replay step state_model_version must match result")
        evaluations = step.strategy_result.evaluations
        if (
            tuple(evaluation.provenance.strategy_id for evaluation in evaluations)
            != expected_ids
        ):
            raise ValueError("replay step strategy ids must match result strategies")
        if (
            tuple(evaluation.provenance.strategy_version for evaluation in evaluations)
            != expected_versions
        ):
            raise ValueError(
                "replay step strategy versions must match result strategies"
            )


def _normalize_steps(value: object) -> tuple[HistoricalReplayStep, ...]:
    if isinstance(value, tuple):
        steps = value
    elif isinstance(value, list):
        steps = tuple(value)
    else:
        raise TypeError("steps must be a tuple or list")
    for step in steps:
        if not isinstance(step, HistoricalReplayStep):
            raise TypeError("steps elements must be HistoricalReplayStep instances")
    return steps


def _normalize_strategy_identities(value: object) -> tuple[ReplayStrategyIdentity, ...]:
    if isinstance(value, tuple):
        strategies = value
    elif isinstance(value, list):
        strategies = tuple(value)
    else:
        raise TypeError("strategies must be a tuple or list")
    for strategy in strategies:
        if not isinstance(strategy, ReplayStrategyIdentity):
            raise TypeError("strategies elements must be ReplayStrategyIdentity")
    return strategies


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


__all__ = ["HistoricalReplayResult", "HistoricalReplayStep", "ReplayStrategyIdentity"]
