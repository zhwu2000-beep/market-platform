"""Composite signal scoring helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from numbers import Real

import numpy as np
import pandas as pd

from market_platform.signals.models import MarketSignal

_SIGNAL_NAME = "composite_score"
_ALLOWED_MISSING_POLICIES = {"exclude", "require_all"}


def calculate_composite_signal(
    signals: Iterable[MarketSignal],
    weights: Mapping[str, float],
    *,
    missing_policy: str = "exclude",
) -> MarketSignal:
    """Return a weighted composite score from a set of structured signals."""

    signal_list = list(signals)
    if not signal_list:
        raise ValueError("signals must not be empty")

    weight_items = list(weights.items())
    if not weight_items:
        raise ValueError("weights must not be empty")

    if missing_policy not in _ALLOWED_MISSING_POLICIES:
        raise ValueError("missing_policy must be one of: exclude, require_all")

    symbol, timestamp = _validate_signals(signal_list)
    signal_by_name = {signal.name.strip(): signal for signal in signal_list}
    configured_weights = _validate_weights(weight_items, signal_by_name)
    selected_names = list(configured_weights.keys())

    component_values: dict[str, float | None] = {}
    missing_signals: list[str] = []
    active_weights: dict[str, float] = {}
    for name in selected_names:
        signal = signal_by_name[name]
        component_value = _normalize_component_value(signal.value, signal.name)
        component_values[name] = component_value
        if component_value is None:
            missing_signals.append(name)
        else:
            active_weights[name] = configured_weights[name]

    if missing_policy == "require_all" and missing_signals:
        return _build_signal(
            symbol=symbol,
            timestamp=timestamp,
            value=None,
            missing_policy=missing_policy,
            configured_weights=configured_weights,
            normalized_weights={},
            component_values=component_values,
            component_contributions={},
            included_signals=[],
            missing_signals=missing_signals,
        )

    normalized_weights: dict[str, float] = {}
    component_contributions: dict[str, float] = {}
    included_signals: list[str] = []

    if not active_weights:
        score: float | None = None
    else:
        active_total_weight = float(sum(active_weights.values()))
        if not np.isfinite(active_total_weight) or active_total_weight <= 0:
            raise ValueError("Active weights must sum to a positive finite value")

        for name in selected_names:
            if name not in active_weights:
                continue
            normalized_weight = active_weights[name] / active_total_weight
            normalized_weights[name] = normalized_weight
            included_signals.append(name)
            component_value = component_values[name]
            assert component_value is not None
            component_contributions[name] = component_value * normalized_weight

        score = float(sum(component_contributions.values()))
        if not np.isfinite(score):
            raise ValueError("Composite signal result must be finite")

    return _build_signal(
        symbol=symbol,
        timestamp=timestamp,
        value=score,
        missing_policy=missing_policy,
        configured_weights=configured_weights,
        normalized_weights=normalized_weights,
        component_values=component_values,
        component_contributions=component_contributions,
        included_signals=included_signals,
        missing_signals=missing_signals,
    )


def _validate_signals(signals: list[MarketSignal]) -> tuple[str, datetime]:
    signal_names: set[str] = set()
    normalized_symbol: str | None = None
    normalized_timestamp: datetime | None = None

    for signal in signals:
        signal_name = _normalize_signal_name(signal.name)
        if signal_name in signal_names:
            raise ValueError("Signal names must be unique")
        signal_names.add(signal_name)

        signal_symbol = _normalize_symbol(signal.symbol)
        signal_timestamp = _normalize_timestamp(signal.timestamp)
        if normalized_symbol is None:
            normalized_symbol = signal_symbol
            normalized_timestamp = signal_timestamp
            continue

        if signal_symbol.casefold() != normalized_symbol.casefold():
            raise ValueError("All component signals must have the same symbol")
        if signal_timestamp != normalized_timestamp:
            raise ValueError("All component signals must have the same timestamp")

    assert normalized_symbol is not None
    assert normalized_timestamp is not None
    return normalized_symbol, normalized_timestamp


def _validate_weights(
    weight_items: list[tuple[str, float]],
    signal_by_name: Mapping[str, MarketSignal],
) -> dict[str, float]:
    validated: dict[str, float] = {}
    seen_names: set[str] = set()

    for raw_name, raw_weight in weight_items:
        name = _normalize_signal_name(raw_name)
        if name in seen_names:
            raise ValueError("Weight names must be unique")
        seen_names.add(name)

        if name not in signal_by_name:
            raise ValueError(f"Unknown weight name: {name}")

        weight = _normalize_weight_value(raw_weight, name)
        validated[name] = weight

    return validated


def _build_signal(
    *,
    symbol: str,
    timestamp: datetime,
    value: float | None,
    missing_policy: str,
    configured_weights: dict[str, float],
    normalized_weights: dict[str, float],
    component_values: dict[str, float | None],
    component_contributions: dict[str, float],
    included_signals: list[str],
    missing_signals: list[str],
) -> MarketSignal:
    return MarketSignal(
        symbol=symbol,
        name=_SIGNAL_NAME,
        value=value,
        timestamp=timestamp,
        parameters={
            "missing_policy": missing_policy,
            "configured_weights": configured_weights,
            "normalized_weights": normalized_weights,
            "component_values": component_values,
            "component_contributions": component_contributions,
            "included_signals": included_signals,
            "missing_signals": missing_signals,
        },
    )


def _normalize_signal_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Signal name cannot be empty")
    return name


def _normalize_symbol(value: str) -> str:
    symbol = value.strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    return symbol


def _normalize_timestamp(value: datetime) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("Signal timestamp must be timezone-aware")
    return timestamp.tz_convert(UTC).to_pydatetime()


def _normalize_weight_value(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"Weight for {name} must be a numeric value")

    weight = float(value)
    if not np.isfinite(weight):
        raise ValueError(f"Weight for {name} must be finite")
    if weight <= 0:
        raise ValueError(f"Weight for {name} must be strictly positive")
    return weight


def _normalize_component_value(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"Signal value for {name} must be numeric or None")

    numeric_value = float(value)
    if not np.isfinite(numeric_value):
        raise ValueError(f"Signal value for {name} must be finite")
    return numeric_value
