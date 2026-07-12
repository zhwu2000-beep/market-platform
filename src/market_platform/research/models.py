"""Immutable research domain models."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum, StrEnum
from numbers import Real
from typing import Any, cast


class ResearchSerializable:
    """Mixin that renders nested models into JSON-compatible data."""

    def to_dict(self) -> dict[str, object]:
        return {
            field.name: _serialize_value(getattr(self, field.name))
            for field in fields(cast(Any, self))
        }


class ResearchStatus(StrEnum):
    """Overall status for a research result."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ResearchWarning(ResearchSerializable):
    """Structured warning attached to a research result."""

    code: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _normalize_required_text(self.code, "code"))
        object.__setattr__(
            self,
            "message",
            _normalize_required_text(self.message, "message"),
        )


@dataclass(frozen=True, slots=True)
class ResearchRequest(ResearchSerializable):
    """Request for a market research workflow."""

    symbol: str
    horizon_days: int
    provider: str | None = None
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        _require_positive_int(self.horizon_days, "horizon_days")
        if self.provider is not None:
            object.__setattr__(
                self,
                "provider",
                _normalize_required_text(self.provider, "provider"),
            )
        if self.as_of is not None and self.as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware when provided")


@dataclass(frozen=True, slots=True)
class MarketView(ResearchSerializable):
    """High-level market interpretation for a research request."""

    direction: str | None = None
    strength: str | None = None
    trend_state: str | None = None
    momentum_state: str | None = None
    volatility_state: str | None = None
    price_structure: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "direction",
            _normalize_optional_text(self.direction, "direction"),
        )
        object.__setattr__(
            self,
            "strength",
            _normalize_optional_text(self.strength, "strength"),
        )
        object.__setattr__(
            self,
            "trend_state",
            _normalize_optional_text(self.trend_state, "trend_state"),
        )
        object.__setattr__(
            self,
            "momentum_state",
            _normalize_optional_text(self.momentum_state, "momentum_state"),
        )
        object.__setattr__(
            self,
            "volatility_state",
            _normalize_optional_text(self.volatility_state, "volatility_state"),
        )
        object.__setattr__(
            self,
            "price_structure",
            _normalize_optional_text(self.price_structure, "price_structure"),
        )
        if self.confidence is not None:
            object.__setattr__(
                self,
                "confidence",
                _require_unit_interval(self.confidence, "confidence"),
            )


@dataclass(frozen=True, slots=True)
class PriceTarget(ResearchSerializable):
    """Projected price range for a given horizon."""

    horizon_days: int
    lower: float
    central: float
    upper: float
    methodology: tuple[str, ...]
    confidence: float | None = None

    def __post_init__(self) -> None:
        _require_positive_int(self.horizon_days, "horizon_days")
        lower = _require_non_negative_number(self.lower, "lower")
        central = _require_non_negative_number(self.central, "central")
        upper = _require_non_negative_number(self.upper, "upper")
        if not lower <= central <= upper:
            raise ValueError("PriceTarget must satisfy lower <= central <= upper")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "central", central)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text_tuple(self.methodology, "methodology"),
        )
        if self.confidence is not None:
            object.__setattr__(
                self,
                "confidence",
                _require_unit_interval(self.confidence, "confidence"),
            )


@dataclass(frozen=True, slots=True)
class ProbabilityEstimate(ResearchSerializable):
    """Estimated probability for a named event."""

    event: str
    horizon_days: int
    probability: float
    methodology: str
    sample_size: int | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event", _normalize_required_text(self.event, "event"))
        _require_positive_int(self.horizon_days, "horizon_days")
        object.__setattr__(
            self,
            "probability",
            _require_unit_interval(self.probability, "probability"),
        )
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        if self.sample_size is not None:
            _require_non_negative_int(self.sample_size, "sample_size")
        if self.model_version is not None:
            object.__setattr__(
                self,
                "model_version",
                _normalize_required_text(self.model_version, "model_version"),
            )


@dataclass(frozen=True, slots=True)
class PriceLevel(ResearchSerializable):
    """Important price level for support, resistance, or reference."""

    lower: float
    upper: float
    level_type: str
    strength: float | None = None
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        lower = _require_non_negative_number(self.lower, "lower")
        upper = _require_non_negative_number(self.upper, "upper")
        if lower > upper:
            raise ValueError("PriceLevel must satisfy lower <= upper")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        object.__setattr__(
            self,
            "level_type",
            _normalize_required_text(self.level_type, "level_type"),
        )
        if self.strength is not None:
            object.__setattr__(
                self,
                "strength",
                _require_unit_interval(self.strength, "strength"),
            )
        object.__setattr__(
            self,
            "sources",
            _normalize_string_tuple(self.sources, "sources"),
        )


@dataclass(frozen=True, slots=True)
class PositionContext(ResearchSerializable):
    """Position and capital context for a research workflow."""

    shares: int
    average_cost: float | None = None
    available_cash: float | None = None
    max_risk_amount: float | None = None
    willing_to_add: bool | None = None
    willing_to_be_assigned: bool | None = None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.shares, "shares")
        if self.average_cost is not None:
            object.__setattr__(
                self,
                "average_cost",
                _require_non_negative_number(self.average_cost, "average_cost"),
            )
        if self.available_cash is not None:
            object.__setattr__(
                self,
                "available_cash",
                _require_non_negative_number(self.available_cash, "available_cash"),
            )
        if self.max_risk_amount is not None:
            object.__setattr__(
                self,
                "max_risk_amount",
                _require_non_negative_number(self.max_risk_amount, "max_risk_amount"),
            )
        object.__setattr__(
            self,
            "willing_to_add",
            _normalize_optional_bool(self.willing_to_add, "willing_to_add"),
        )
        object.__setattr__(
            self,
            "willing_to_be_assigned",
            _normalize_optional_bool(
                self.willing_to_be_assigned,
                "willing_to_be_assigned",
            ),
        )


@dataclass(frozen=True, slots=True)
class PositionAction(ResearchSerializable):
    """Suggested position-management action."""

    action_type: str
    rationale: str
    trigger_price: float | None = None
    invalidation_price: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_type",
            _normalize_required_text(self.action_type, "action_type"),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_required_text(self.rationale, "rationale"),
        )
        if self.trigger_price is not None:
            object.__setattr__(
                self,
                "trigger_price",
                _require_non_negative_number(self.trigger_price, "trigger_price"),
            )
        if self.invalidation_price is not None:
            object.__setattr__(
                self,
                "invalidation_price",
                _require_non_negative_number(
                    self.invalidation_price,
                    "invalidation_price",
                ),
            )


@dataclass(frozen=True, slots=True)
class StrategyCandidate(ResearchSerializable):
    """Candidate strategy suitable for a research request."""

    strategy_type: str
    objective: str
    rationale: str
    suitability_score: float | None = None
    max_profit: float | None = None
    max_loss: float | None = None
    breakeven: tuple[float, ...] = ()
    entry_conditions: tuple[str, ...] = ()
    exit_conditions: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strategy_type",
            _normalize_required_text(self.strategy_type, "strategy_type"),
        )
        object.__setattr__(
            self,
            "objective",
            _normalize_required_text(self.objective, "objective"),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_required_text(self.rationale, "rationale"),
        )
        if self.suitability_score is not None:
            object.__setattr__(
                self,
                "suitability_score",
                _require_unit_interval(
                    self.suitability_score,
                    "suitability_score",
                ),
            )
        if self.max_profit is not None:
            object.__setattr__(
                self,
                "max_profit",
                _require_non_negative_number(self.max_profit, "max_profit"),
            )
        if self.max_loss is not None:
            object.__setattr__(
                self,
                "max_loss",
                _require_non_negative_number(self.max_loss, "max_loss"),
            )
        object.__setattr__(
            self,
            "breakeven",
            _normalize_number_tuple(self.breakeven, "breakeven"),
        )
        object.__setattr__(
            self,
            "entry_conditions",
            _normalize_string_tuple(self.entry_conditions, "entry_conditions"),
        )
        object.__setattr__(
            self,
            "exit_conditions",
            _normalize_string_tuple(self.exit_conditions, "exit_conditions"),
        )
        object.__setattr__(
            self,
            "rejection_reasons",
            _normalize_string_tuple(self.rejection_reasons, "rejection_reasons"),
        )


@dataclass(frozen=True, slots=True)
class ResearchResult(ResearchSerializable):
    """Structured outcome of a research workflow."""

    request: ResearchRequest
    status: ResearchStatus
    model_version: str
    market_view: MarketView | None = None
    price_targets: tuple[PriceTarget, ...] = ()
    probabilities: tuple[ProbabilityEstimate, ...] = ()
    price_levels: tuple[PriceLevel, ...] = ()
    position_actions: tuple[PositionAction, ...] = ()
    strategy_candidates: tuple[StrategyCandidate, ...] = ()
    warnings: tuple[ResearchWarning, ...] = ()
    summary: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ResearchRequest):
            raise TypeError("request must be a ResearchRequest")
        if not isinstance(self.status, ResearchStatus):
            raise TypeError("status must be a ResearchStatus")
        if self.market_view is not None and not isinstance(
            self.market_view, MarketView
        ):
            raise TypeError("market_view must be a MarketView or None")
        object.__setattr__(
            self,
            "model_version",
            _normalize_required_text(self.model_version, "model_version"),
        )
        if self.summary is not None:
            object.__setattr__(
                self,
                "summary",
                _normalize_required_text(self.summary, "summary"),
            )
        object.__setattr__(
            self,
            "price_targets",
            _normalize_model_tuple(self.price_targets, "price_targets", PriceTarget),
        )
        object.__setattr__(
            self,
            "probabilities",
            _normalize_model_tuple(
                self.probabilities,
                "probabilities",
                ProbabilityEstimate,
            ),
        )
        object.__setattr__(
            self,
            "price_levels",
            _normalize_model_tuple(self.price_levels, "price_levels", PriceLevel),
        )
        object.__setattr__(
            self,
            "position_actions",
            _normalize_model_tuple(
                self.position_actions,
                "position_actions",
                PositionAction,
            ),
        )
        object.__setattr__(
            self,
            "strategy_candidates",
            _normalize_model_tuple(
                self.strategy_candidates,
                "strategy_candidates",
                StrategyCandidate,
            ),
        )
        object.__setattr__(
            self,
            "warnings",
            _normalize_model_tuple(self.warnings, "warnings", ResearchWarning),
        )


def _normalize_symbol(value: object) -> str:
    symbol = _normalize_required_text(value, "symbol").upper()
    if not symbol:
        raise ValueError("symbol must not be empty")
    return symbol


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_required_text(value, field_name)


def _normalize_required_text_tuple(
    values: object,
    field_name: str,
) -> tuple[str, ...]:
    container = _normalize_tuple_container(values, field_name)
    normalized = tuple(
        _normalize_required_text(value, field_name) for value in container
    )
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalize_string_tuple(
    values: object,
    field_name: str,
) -> tuple[str, ...]:
    container = _normalize_tuple_container(values, field_name)
    return tuple(_normalize_required_text(value, field_name) for value in container)


def _normalize_number_tuple(
    values: object,
    field_name: str,
) -> tuple[float, ...]:
    container = _normalize_tuple_container(values, field_name)
    return tuple(
        _require_non_negative_number(value, field_name) for value in container
    )


def _normalize_model_tuple[ModelT](
    values: object,
    field_name: str,
    expected_type: type[ModelT],
) -> tuple[ModelT, ...]:
    container = _normalize_tuple_container(values, field_name)
    normalized: list[ModelT] = []
    for value in container:
        if not isinstance(value, expected_type):
            raise TypeError(
                f"{field_name} elements must be {expected_type.__name__} instances"
            )
        normalized.append(value)
    return tuple(normalized)


def _normalize_tuple_container(values: object, field_name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes, bytearray, dict)):
        raise TypeError(f"{field_name} must be a tuple or list")
    if isinstance(values, tuple):
        return values
    if isinstance(values, list):
        return tuple(values)
    raise TypeError(f"{field_name} must be a tuple or list")


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _require_unit_interval(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    if not 0.0 <= numeric_value <= 1.0:
        raise ValueError(f"{field_name} must be within [0.0, 1.0]")
    return numeric_value


def _require_non_negative_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    if numeric_value < 0.0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric_value


def _normalize_optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise TypeError(f"{field_name} must be a bool or None")


def _serialize_value(value: object) -> object:
    if isinstance(value, ResearchSerializable):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            field.name: _serialize_value(getattr(value, field.name))
            for field in fields(value)
        }
    return value
