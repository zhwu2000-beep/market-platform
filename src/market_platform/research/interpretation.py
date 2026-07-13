"""Transparent research signal interpretation helpers.

These baseline scales are transparent and uncalibrated v1 interpretation scales,
not forecast parameters and not statistically estimated probabilities.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from numbers import Real

from market_platform.research.models import ResearchSerializable
from market_platform.signals.composite import calculate_composite_signal
from market_platform.signals.models import MarketSignal

DIRECTIONAL_TREND_SCALE = 0.10
DIRECTIONAL_MOMENTUM_SCALE = 0.20
DIRECTIONAL_CURRENT_DRAWDOWN_SCALE = 0.20
DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE = 0.10

_DEFAULT_DIRECTIONAL_RULES: tuple[SignalInterpretationRule, ...] = ()
_DIRECTIONAL_METHODOLOGY = "baseline_uncalibrated_directional_rescaling_v1"
_REALIZED_VOLATILITY_METHODOLOGY = "baseline_realized_volatility_thresholds_v1"
_COMPOSITE_SIGNAL_NAME = "composite_score"
_DIRECTIONAL_FORMULA = "clamp(raw_value / scale, -1.0, 1.0)"


class SignalRole(StrEnum):
    """Role assigned to an interpreted research signal."""

    DIRECTIONAL = "directional"
    VOLATILITY = "volatility"
    CONTEXTUAL = "contextual"


class InterpretedSignalState(StrEnum):
    """Directional interpretation state for a research signal."""

    STRONGLY_NEGATIVE = "strongly_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    STRONGLY_POSITIVE = "strongly_positive"
    UNAVAILABLE = "unavailable"


class VolatilityState(StrEnum):
    """Descriptive volatility state for realized volatility signals."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SignalInterpretationRule(ResearchSerializable):
    """Transparent mapping from a raw signal name to a normalized score."""

    signal_name: str
    role: SignalRole
    methodology: str
    scale: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "signal_name",
            _normalize_required_text(self.signal_name, "signal_name"),
        )
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        if not isinstance(self.role, SignalRole):
            raise TypeError("role must be a SignalRole")
        if self.role is SignalRole.DIRECTIONAL:
            if self.scale is None:
                raise ValueError("directional rules require a positive finite scale")
            object.__setattr__(
                self,
                "scale",
                _normalize_positive_number(self.scale, "scale"),
            )
            return
        if self.scale is not None:
            raise ValueError("non-directional rules must not define scale")


@dataclass(frozen=True, slots=True)
class InterpretedSignal(ResearchSerializable):
    """Normalized directional interpretation of a raw market signal."""

    symbol: str
    timestamp: datetime
    name: str
    raw_value: float | None
    score: float | None
    state: InterpretedSignalState
    role: SignalRole
    methodology: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(self, "timestamp", _normalize_timestamp(self.timestamp))
        object.__setattr__(self, "name", _normalize_required_text(self.name, "name"))
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        if self.role is not SignalRole.DIRECTIONAL:
            raise ValueError("InterpretedSignal requires role SignalRole.DIRECTIONAL")
        if not isinstance(self.state, InterpretedSignalState):
            raise TypeError("state must be an InterpretedSignalState")

        if self.raw_value is None:
            if self.score is not None:
                raise ValueError("score must be None when raw_value is None")
            if self.state is not InterpretedSignalState.UNAVAILABLE:
                raise ValueError(
                    "available states require both raw_value and score"
                )
        else:
            raw_numeric = _normalize_numeric_value(self.raw_value, "raw_value")
            score_numeric = _normalize_score_value(self.score)
            if self.state is InterpretedSignalState.UNAVAILABLE:
                raise ValueError(
                    "available states require a non-unavailable state"
                )
            object.__setattr__(self, "raw_value", raw_numeric)
            object.__setattr__(self, "score", score_numeric)

        object.__setattr__(self, "parameters", dict(self.parameters))


@dataclass(frozen=True, slots=True)
class VolatilityAssessment(ResearchSerializable):
    """Descriptive interpretation of realized volatility."""

    symbol: str
    timestamp: datetime
    raw_value: float | None
    state: VolatilityState
    methodology: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _normalize_symbol(self.symbol))
        object.__setattr__(self, "timestamp", _normalize_timestamp(self.timestamp))
        object.__setattr__(
            self,
            "methodology",
            _normalize_required_text(self.methodology, "methodology"),
        )
        if not isinstance(self.state, VolatilityState):
            raise TypeError("state must be a VolatilityState")
        if self.raw_value is None:
            if self.state is not VolatilityState.UNAVAILABLE:
                raise ValueError("available volatility states require a raw_value")
        else:
            raw_numeric = _normalize_non_negative_number(self.raw_value, "raw_value")
            if self.state is VolatilityState.UNAVAILABLE:
                raise ValueError(
                    "unavailable volatility assessments must have raw_value set to None"
                )
            object.__setattr__(self, "raw_value", raw_numeric)
        object.__setattr__(self, "parameters", dict(self.parameters))


def interpret_market_signal(
    signal: MarketSignal,
    rule: SignalInterpretationRule,
) -> InterpretedSignal:
    """Interpret a raw directional signal using a transparent baseline rule."""

    if rule.role is not SignalRole.DIRECTIONAL:
        raise ValueError("interpret_market_signal requires a directional rule")

    signal_name = _normalize_required_text(signal.name, "signal.name")
    if signal_name != rule.signal_name:
        raise ValueError("signal.name must match rule.signal_name")

    symbol = _normalize_symbol(signal.symbol)
    timestamp = _normalize_timestamp(signal.timestamp)
    source_parameters = dict(signal.parameters)
    parameters = _directional_parameters(rule, source_parameters)

    if signal.value is None:
        return InterpretedSignal(
            symbol=symbol,
            timestamp=timestamp,
            name=signal_name,
            raw_value=None,
            score=None,
            state=InterpretedSignalState.UNAVAILABLE,
            role=rule.role,
            methodology=rule.methodology,
            parameters=parameters,
        )

    raw_value = _normalize_numeric_value(signal.value, "signal.value")
    assert rule.scale is not None
    score = _clamp(raw_value / rule.scale)
    state = _classify_directional_score(score)
    return InterpretedSignal(
        symbol=symbol,
        timestamp=timestamp,
        name=signal_name,
        raw_value=raw_value,
        score=score,
        state=state,
        role=rule.role,
        methodology=rule.methodology,
        parameters=parameters,
    )


def interpret_realized_volatility(
    signal: MarketSignal,
    *,
    low_threshold: float = 0.15,
    high_threshold: float = 0.30,
) -> VolatilityAssessment:
    """Interpret realized volatility into a descriptive volatility state."""

    signal_name = _normalize_required_text(signal.name, "signal.name")
    if signal_name != "realized_volatility":
        raise ValueError("signal.name must be realized_volatility")

    low = _normalize_non_negative_number(low_threshold, "low_threshold")
    high = _normalize_non_negative_number(high_threshold, "high_threshold")
    if not low < high:
        raise ValueError("low_threshold must be less than high_threshold")

    symbol = _normalize_symbol(signal.symbol)
    timestamp = _normalize_timestamp(signal.timestamp)
    parameters = dict(signal.parameters)

    if signal.value is None:
        return VolatilityAssessment(
            symbol=symbol,
            timestamp=timestamp,
            raw_value=None,
            state=VolatilityState.UNAVAILABLE,
            methodology=_REALIZED_VOLATILITY_METHODOLOGY,
            parameters={
                "low_threshold": low,
                "high_threshold": high,
                "source_parameters": parameters,
            },
        )

    raw_value = _normalize_non_negative_number(signal.value, "signal.value")
    if raw_value < low:
        state = VolatilityState.LOW
    elif raw_value < high:
        state = VolatilityState.NORMAL
    else:
        state = VolatilityState.HIGH

    return VolatilityAssessment(
        symbol=symbol,
        timestamp=timestamp,
        raw_value=raw_value,
        state=state,
        methodology=_REALIZED_VOLATILITY_METHODOLOGY,
        parameters={
            "low_threshold": low,
            "high_threshold": high,
            "source_parameters": parameters,
        },
    )


def interpret_directional_signals(
    signals: Iterable[MarketSignal],
    rules: Mapping[str, SignalInterpretationRule] | None = None,
) -> tuple[InterpretedSignal, ...]:
    """Interpret the configured directional signals in input order."""

    signal_list = list(signals)
    if not signal_list:
        return ()

    rule_map = _copy_directional_rules(rules)
    seen_names: set[str] = set()
    interpreted: list[InterpretedSignal] = []
    reference_symbol: str | None = None
    reference_timestamp: datetime | None = None

    for signal in signal_list:
        signal_name = _normalize_required_text(signal.name, "signal.name")
        if signal_name in seen_names:
            raise ValueError("Signal names must be unique")
        seen_names.add(signal_name)

        rule = rule_map.get(signal_name)
        if rule is None:
            continue

        interpreted_signal = interpret_market_signal(signal, rule)
        if reference_symbol is None:
            reference_symbol = interpreted_signal.symbol
            reference_timestamp = interpreted_signal.timestamp
        else:
            if interpreted_signal.symbol != reference_symbol:
                raise ValueError("Directional signals must share the same symbol")
            if interpreted_signal.timestamp != reference_timestamp:
                raise ValueError("Directional signals must share the same timestamp")
        interpreted.append(interpreted_signal)

    return tuple(interpreted)


def calculate_research_composite_signal(
    interpreted_signals: Iterable[InterpretedSignal],
    weights: Mapping[str, float] | None = None,
) -> MarketSignal:
    """Build a composite score from interpreted directional signals."""

    signal_list = list(interpreted_signals)
    if not signal_list:
        raise ValueError("interpreted_signals must not be empty")

    directional_signals = [
        signal for signal in signal_list if signal.role is SignalRole.DIRECTIONAL
    ]
    reference = signal_list[0]

    if not directional_signals:
        return MarketSignal(
            symbol=reference.symbol,
            name=_COMPOSITE_SIGNAL_NAME,
            value=None,
            timestamp=reference.timestamp,
            parameters={
                "missing_policy": "exclude",
                "configured_weights": {},
                "normalized_weights": {},
                "component_values": {},
                "component_contributions": {},
                "included_signals": [],
                "missing_signals": [],
            },
        )

    component_signals = [
        MarketSignal(
            symbol=signal.symbol,
            name=signal.name,
            value=signal.score,
            timestamp=signal.timestamp,
            parameters=dict(signal.parameters),
        )
        for signal in directional_signals
    ]

    composite_weights = (
        {signal.name: 1.0 for signal in directional_signals}
        if weights is None
        else dict(weights)
    )

    return calculate_composite_signal(
        component_signals,
        composite_weights,
        missing_policy="exclude",
    )


def _copy_directional_rules(
    rules: Mapping[str, SignalInterpretationRule] | None,
) -> dict[str, SignalInterpretationRule]:
    if rules is None:
        return {rule.signal_name: rule for rule in _default_directional_rules()}
    if not isinstance(rules, Mapping):
        raise TypeError("rules must be a Mapping")

    normalized_rules: dict[str, SignalInterpretationRule] = {}
    for raw_name, rule in rules.items():
        name = _normalize_required_text(raw_name, "signal_name")
        if name in normalized_rules:
            raise ValueError("Directional rule names must be unique")
        if not isinstance(rule, SignalInterpretationRule):
            raise TypeError(
                "rules values must be SignalInterpretationRule instances"
            )
        if rule.role is not SignalRole.DIRECTIONAL:
            raise ValueError(
                "Directional rules must have role SignalRole.DIRECTIONAL"
            )
        if name != rule.signal_name:
            raise ValueError("Mapping key must match rule.signal_name")
        normalized_rules[name] = rule
    return normalized_rules


def _default_directional_rules() -> tuple[SignalInterpretationRule, ...]:
    global _DEFAULT_DIRECTIONAL_RULES
    if _DEFAULT_DIRECTIONAL_RULES:
        return _DEFAULT_DIRECTIONAL_RULES

    _DEFAULT_DIRECTIONAL_RULES = (
        SignalInterpretationRule(
            signal_name="trend",
            role=SignalRole.DIRECTIONAL,
            methodology=_DIRECTIONAL_METHODOLOGY,
            scale=DIRECTIONAL_TREND_SCALE,
        ),
        SignalInterpretationRule(
            signal_name="momentum",
            role=SignalRole.DIRECTIONAL,
            methodology=_DIRECTIONAL_METHODOLOGY,
            scale=DIRECTIONAL_MOMENTUM_SCALE,
        ),
        SignalInterpretationRule(
            signal_name="current_drawdown",
            role=SignalRole.DIRECTIONAL,
            methodology=_DIRECTIONAL_METHODOLOGY,
            scale=DIRECTIONAL_CURRENT_DRAWDOWN_SCALE,
        ),
        SignalInterpretationRule(
            signal_name="distance_from_moving_average",
            role=SignalRole.DIRECTIONAL,
            methodology=_DIRECTIONAL_METHODOLOGY,
            scale=DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE,
        ),
    )
    return _DEFAULT_DIRECTIONAL_RULES


def _directional_parameters(
    rule: SignalInterpretationRule,
    source_parameters: dict[str, object],
) -> dict[str, object]:
    assert rule.scale is not None
    return {
        "signal_name": rule.signal_name,
        "role": rule.role.value,
        "methodology": rule.methodology,
        "scale": rule.scale,
        "formula": _DIRECTIONAL_FORMULA,
        "source_parameters": dict(source_parameters),
    }


def _normalize_required_text(value: object, field_name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _normalize_symbol(value: object) -> str:
    return _normalize_required_text(value, "symbol").upper()


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_numeric_value(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    return numeric_value


def _normalize_positive_number(value: object, field_name: str) -> float:
    numeric_value = _normalize_numeric_value(value, field_name)
    if numeric_value <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return numeric_value


def _normalize_non_negative_number(value: object, field_name: str) -> float:
    numeric_value = _normalize_numeric_value(value, field_name)
    if numeric_value < 0.0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric_value


def _normalize_score_value(value: object | None) -> float:
    numeric_value = _normalize_numeric_value(value, "score")
    if numeric_value < -1.0 or numeric_value > 1.0:
        raise ValueError("score must be within [-1.0, 1.0]")
    return numeric_value


def _clamp(value: float) -> float:
    if value < -1.0:
        return -1.0
    if value > 1.0:
        return 1.0
    return value


def _classify_directional_score(score: float) -> InterpretedSignalState:
    if score <= -0.60:
        return InterpretedSignalState.STRONGLY_NEGATIVE
    if score <= -0.20:
        return InterpretedSignalState.NEGATIVE
    if score < 0.20:
        return InterpretedSignalState.NEUTRAL
    if score < 0.60:
        return InterpretedSignalState.POSITIVE
    return InterpretedSignalState.STRONGLY_POSITIVE


__all__ = [
    "DIRECTIONAL_CURRENT_DRAWDOWN_SCALE",
    "DIRECTIONAL_DISTANCE_FROM_MOVING_AVERAGE_SCALE",
    "DIRECTIONAL_MOMENTUM_SCALE",
    "DIRECTIONAL_TREND_SCALE",
    "InterpretedSignal",
    "InterpretedSignalState",
    "SignalInterpretationRule",
    "SignalRole",
    "VolatilityAssessment",
    "VolatilityState",
    "calculate_research_composite_signal",
    "interpret_directional_signals",
    "interpret_market_signal",
    "interpret_realized_volatility",
]
