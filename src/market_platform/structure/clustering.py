"""ATR-based price-level clustering utilities."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from numbers import Real

from market_platform.structure.models import PriceLevelCandidate, PriceZone


def filter_available_zones(
    zones: Sequence[PriceZone],
    as_of: datetime,
) -> tuple[PriceZone, ...]:
    """Return zones that were available no later than the requested time."""

    if isinstance(zones, (str, bytes, bytearray, dict)):
        raise TypeError("zones must be a sequence of PriceZone")
    if not isinstance(zones, Sequence):
        raise TypeError("zones must be a sequence of PriceZone")
    normalized_as_of = _normalize_as_of(as_of)
    available: list[PriceZone] = []
    for zone in zones:
        if not isinstance(zone, PriceZone):
            raise TypeError("zones must contain PriceZone instances")
        if zone.available_at <= normalized_as_of:
            available.append(zone)
    return tuple(available)


def create_price_zone(candidates: Sequence[PriceLevelCandidate]) -> PriceZone:
    """Return a deterministic zone derived from candidate prices.

    Candidates are sorted by occurrence and confirmation times before zone
    boundaries are derived. Source methods are deduplicated in first-seen order
    from the sorted candidates.
    """

    normalized_candidates = _sort_candidates(_normalize_candidates(candidates))
    if not normalized_candidates:
        raise ValueError("candidates must not be empty")
    lower_bound = min(candidate.price for candidate in normalized_candidates)
    upper_bound = max(candidate.price for candidate in normalized_candidates)
    midpoint = (lower_bound + upper_bound) / 2.0
    source_methods = _dedupe_source_methods(normalized_candidates)
    return PriceZone(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        midpoint=midpoint,
        candidates=normalized_candidates,
        source_methods=source_methods,
    )


def cluster_price_levels(
    candidates: Sequence[PriceLevelCandidate],
    *,
    atr: float,
    atr_multiplier: float,
) -> tuple[PriceZone, ...]:
    """Cluster nearby candidates using single-linkage ATR tolerance.

    This implementation uses a simple one-dimensional single-linkage rule: once
    candidates are sorted by price, any adjacent gap at or below the tolerance
    keeps the sequence in the same cluster. That means chain-linked candidates
    can merge even when the first and last items in the chain are farther apart
    than the tolerance.
    """

    normalized_candidates = _normalize_candidates(candidates)
    if not normalized_candidates:
        return ()

    normalized_atr = _require_positive_number(atr, "atr")
    normalized_multiplier = _require_positive_number(atr_multiplier, "atr_multiplier")
    tolerance = normalized_atr * normalized_multiplier

    sorted_by_price = sorted(
        normalized_candidates,
        key=_candidate_sort_key_by_price,
    )

    zones: list[PriceZone] = []
    current_cluster: list[PriceLevelCandidate] = [sorted_by_price[0]]
    previous_price = sorted_by_price[0].price

    for candidate in sorted_by_price[1:]:
        if candidate.price - previous_price <= tolerance:
            current_cluster.append(candidate)
        else:
            zones.append(create_price_zone(tuple(current_cluster)))
            current_cluster = [candidate]
        previous_price = candidate.price

    zones.append(create_price_zone(tuple(current_cluster)))
    return tuple(sorted(zones, key=lambda zone: zone.midpoint))


def _normalize_candidates(
    candidates: Sequence[PriceLevelCandidate],
) -> tuple[PriceLevelCandidate, ...]:
    if isinstance(candidates, (str, bytes, bytearray, dict)):
        raise TypeError("candidates must be a sequence of PriceLevelCandidate")
    if not isinstance(candidates, Sequence):
        raise TypeError("candidates must be a sequence of PriceLevelCandidate")
    normalized = tuple(candidates)
    for candidate in normalized:
        if not isinstance(candidate, PriceLevelCandidate):
            raise TypeError("candidates must contain PriceLevelCandidate instances")
    return normalized


def _candidate_sort_key_by_price(
    candidate: PriceLevelCandidate,
) -> tuple[float, str, str, str, str]:
    return (
        candidate.price,
        candidate.occurred_at.isoformat(),
        candidate.confirmed_at.isoformat(),
        candidate.kind.value,
        candidate.source_method,
    )


def _candidate_sort_key(
    candidate: PriceLevelCandidate,
) -> tuple[str, str, str, float, str]:
    return (
        candidate.occurred_at.isoformat(),
        candidate.confirmed_at.isoformat(),
        candidate.kind.value,
        candidate.price,
        candidate.source_method,
    )


def _sort_candidates(
    candidates: Sequence[PriceLevelCandidate],
) -> tuple[PriceLevelCandidate, ...]:
    return tuple(sorted(candidates, key=_candidate_sort_key))


def _dedupe_source_methods(
    candidates: Sequence[PriceLevelCandidate],
) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in sorted(candidates, key=_candidate_sort_key):
        method = candidate.source_method.strip()
        if method in seen:
            continue
        seen.add(method)
        ordered.append(method)
    return tuple(ordered)


def _require_positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be numeric")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite")
    if numeric_value <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0")
    return numeric_value


def _normalize_as_of(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("as_of must be a datetime")
    if value.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)
