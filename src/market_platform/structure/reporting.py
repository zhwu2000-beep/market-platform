"""Deterministic serialization of price structure snapshots."""

from __future__ import annotations

from datetime import datetime

from market_platform.structure.models import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceStructureSnapshot,
)


def snapshot_to_dict(snapshot: PriceStructureSnapshot) -> dict[str, object]:
    """Return the snapshot facts as deterministic, JSON-serializable data."""

    if not isinstance(snapshot, PriceStructureSnapshot):
        raise TypeError("snapshot must be a PriceStructureSnapshot")

    def timestamp(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def candidate_key(
        candidate: PriceLevelCandidate,
    ) -> tuple[str, str, float, str]:
        return (
            candidate.observed_at.isoformat(),
            candidate.kind.value,
            candidate.price,
            candidate.source_method,
        )

    def candidate_data(candidate: PriceLevelCandidate) -> dict[str, object]:
        return {
            "price": candidate.price,
            "kind": candidate.kind.value,
            "observed_at": candidate.observed_at.isoformat(),
            "source_method": candidate.source_method,
        }

    def observed_zone_key(
        observed: ObservedPriceZone,
    ) -> tuple[float, float, float, tuple[tuple[str, str, float, str], ...]]:
        zone = observed.zone
        return (
            zone.midpoint,
            zone.lower_bound,
            zone.upper_bound,
            tuple(sorted(candidate_key(item) for item in zone.candidates)),
        )

    candidates = sorted(snapshot.candidates, key=candidate_key)
    observed_zones = sorted(snapshot.observed_zones, key=observed_zone_key)

    return {
        "status": snapshot.status.value,
        "as_of": timestamp(snapshot.as_of),
        "current_price": snapshot.current_price,
        "atr": snapshot.atr,
        "candidates": [candidate_data(candidate) for candidate in candidates],
        "observed_zones": [
            {
                "zone": {
                    "lower_bound": observed.zone.lower_bound,
                    "upper_bound": observed.zone.upper_bound,
                    "midpoint": observed.zone.midpoint,
                    "candidates": [
                        candidate_data(candidate)
                        for candidate in sorted(
                            observed.zone.candidates,
                            key=candidate_key,
                        )
                    ],
                    "source_methods": sorted(observed.zone.source_methods),
                },
                "observation": {
                    "touch_count": observed.observation.touch_count,
                    "first_observed_at": timestamp(
                        observed.observation.first_observed_at
                    ),
                    "last_observed_at": timestamp(
                        observed.observation.last_observed_at
                    ),
                },
            }
            for observed in observed_zones
        ],
    }
