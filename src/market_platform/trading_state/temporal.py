"""Pure explicit-time freshness and temporal-skew evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from market_platform.trading_state._canonical import (
    canonical_timestamp,
    require_exact_container,
)
from market_platform.trading_state.errors import TradingStateValidationError


class SnapshotFreshness(StrEnum):
    """Freshness outcome relative to one explicit evaluation time."""

    FRESH = "fresh"
    STALE = "stale"
    FUTURE_DATED = "future_dated"


class SnapshotSkew(StrEnum):
    """Temporal-coherence outcome for independently sourced facts."""

    COHERENT = "coherent"
    EXCESSIVE_SKEW = "excessive_skew"


def evaluate_snapshot_freshness(
    snapshot_as_of: datetime,
    evaluation_as_of: datetime,
    maximum_age: timedelta,
) -> SnapshotFreshness:
    """Evaluate age without consulting a wall clock."""

    snapshot_time = canonical_timestamp(snapshot_as_of, "snapshot_as_of")
    evaluation_time = canonical_timestamp(
        evaluation_as_of,
        "evaluation_as_of",
    )
    maximum = _nonnegative_duration(maximum_age, "maximum_age")
    if snapshot_time > evaluation_time:
        return SnapshotFreshness.FUTURE_DATED
    if evaluation_time - snapshot_time <= maximum:
        return SnapshotFreshness.FRESH
    return SnapshotFreshness.STALE


def evaluate_snapshot_skew(
    snapshot_times: list[datetime] | tuple[datetime, ...],
    maximum_skew: timedelta,
) -> SnapshotSkew:
    """Evaluate maximum time spread without freshness or atomicity claims."""

    raw_times = require_exact_container(
        snapshot_times,
        "snapshot_times",
        32,
        minimum_count=1,
    )
    maximum = _nonnegative_duration(maximum_skew, "maximum_skew")
    normalized: list[datetime] = []
    for value in raw_times:
        normalized.append(canonical_timestamp(value, "snapshot_times item"))
    observed = max(normalized) - min(normalized)
    if observed <= maximum:
        return SnapshotSkew.COHERENT
    return SnapshotSkew.EXCESSIVE_SKEW


def _nonnegative_duration(value: object, field_name: str) -> timedelta:
    if type(value) is not timedelta:
        raise TypeError(f"{field_name} must be a timedelta")
    if value < timedelta(0):
        raise TradingStateValidationError(f"{field_name} must be nonnegative")
    return value


__all__ = [
    "SnapshotFreshness",
    "SnapshotSkew",
    "evaluate_snapshot_freshness",
    "evaluate_snapshot_skew",
]
