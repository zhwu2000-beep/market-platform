from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_platform.observation import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    PriceFacts,
    SignalFacts,
    StructureFacts,
    build_market_observation,
)
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot
from market_platform.structure.models import (
    ObservedPriceZone,
    PriceLevelCandidate,
    PriceLevelKind,
    PriceStructureSnapshot,
    PriceStructureStatus,
    PriceZone,
    PriceZoneObservation,
)
from market_platform.structure.reporting import snapshot_to_dict

_OCCURRED_AT = datetime(2026, 1, 10, tzinfo=UTC)
_CONFIRMED_AT = datetime(2026, 1, 12, tzinfo=UTC)
_AS_OF = datetime(2026, 1, 15, tzinfo=UTC)


def _identity() -> ObservationIdentity:
    return ObservationIdentity(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        window_start=datetime(2025, 10, 1, tzinfo=UTC),
        window_end=_AS_OF,
    )


def _provenance() -> ObservationProvenance:
    return ObservationProvenance(
        provider="polygon",
        methodology="market_observation_adapter",
        methodology_version="v1",
        parameters={"signal_method": "existing", "structure_method": "existing"},
        input_fingerprint="sha256:observation-input",
    )


def _signal_snapshot() -> MarketSignalSnapshot:
    return MarketSignalSnapshot(
        symbol="MSFT",
        timestamp=_AS_OF,
        signals=(
            MarketSignal(
                symbol="MSFT",
                name="trend",
                value=0.025,
                timestamp=_AS_OF,
                parameters={"short_window": 20, "long_window": 50},
            ),
        ),
    )


def _structure_snapshot() -> PriceStructureSnapshot:
    pivot = PriceLevelCandidate(
        price=100.0,
        kind=PriceLevelKind.SWING_HIGH,
        occurred_at=_OCCURRED_AT,
        confirmed_at=_CONFIRMED_AT,
    )
    observed_zone = ObservedPriceZone(
        zone=PriceZone(
            lower_bound=100.0,
            upper_bound=100.0,
            midpoint=100.0,
            candidates=(pivot,),
            source_methods=("swing_pivot",),
        ),
        observation=PriceZoneObservation(
            touch_count=1,
            first_observed_at=_CONFIRMED_AT,
            last_observed_at=_CONFIRMED_AT,
        ),
    )
    return PriceStructureSnapshot(
        status=PriceStructureStatus.OK,
        as_of=_AS_OF,
        current_price=101.0,
        atr=2.0,
        candidates=(pivot,),
        observed_zones=(observed_zone,),
    )


def _observation(
    signal_snapshot: MarketSignalSnapshot | None = None,
    structure_snapshot: PriceStructureSnapshot | None = None,
) -> MarketObservation:
    return build_market_observation(
        _identity(),
        _provenance(),
        price_facts=PriceFacts(latest_price=101.0, observed_at=_AS_OF),
        signal_snapshot=signal_snapshot or _signal_snapshot(),
        structure_snapshot=structure_snapshot or _structure_snapshot(),
    )


def test_integrated_observation_fact_groups_are_frozen() -> None:
    observation = _observation()

    assert isinstance(observation.price_facts, PriceFacts)
    assert isinstance(observation.signal_facts, SignalFacts)
    assert isinstance(observation.structure_facts, StructureFacts)

    with pytest.raises(FrozenInstanceError):
        observation.price_facts = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observation.price_facts.latest_price = 99.0  # type: ignore[union-attr,misc]
    with pytest.raises(FrozenInstanceError):
        observation.signal_facts.as_of = _OCCURRED_AT  # type: ignore[union-attr,misc]
    with pytest.raises(FrozenInstanceError):
        observation.structure_facts.as_of = _OCCURRED_AT  # type: ignore[union-attr,misc]


def test_structure_point_in_time_fields_survive_observation_adapter() -> None:
    observation = _observation()
    assert observation.structure_facts is not None

    pivot = observation.structure_facts.confirmed_pivots[0]
    zone = observation.structure_facts.available_zones[0].zone

    assert observation.structure_facts.as_of == _AS_OF
    assert pivot.occurred_at == _OCCURRED_AT
    assert pivot.confirmed_at == _CONFIRMED_AT
    assert zone.available_at == _CONFIRMED_AT

    payload = observation.to_dict()
    structure_payload = payload["structure_facts"]
    assert isinstance(structure_payload, dict)
    assert structure_payload["confirmed_pivots"][0]["occurred_at"] == (
        _OCCURRED_AT.isoformat()
    )
    assert structure_payload["confirmed_pivots"][0]["confirmed_at"] == (
        _CONFIRMED_AT.isoformat()
    )
    assert structure_payload["available_zones"][0]["zone"]["available_at"] == (
        _CONFIRMED_AT.isoformat()
    )
    json.dumps(payload)


def test_builder_does_not_modify_or_alias_mutable_input_facts() -> None:
    signal_snapshot = _signal_snapshot()
    structure_snapshot = _structure_snapshot()
    signal_parameters_before = dict(signal_snapshot.signals[0].parameters)
    structure_before = snapshot_to_dict(structure_snapshot)

    observation = _observation(signal_snapshot, structure_snapshot)

    assert signal_snapshot.signals[0].parameters == signal_parameters_before
    assert snapshot_to_dict(structure_snapshot) == structure_before
    assert observation.signal_facts is not None
    assert observation.signal_facts.signals[0] is not signal_snapshot.signals[0]

    signal_snapshot.signals[0].parameters["short_window"] = 5

    assert observation.signal_facts.signals[0].parameters["short_window"] == 20


def test_observation_contains_facts_without_state_or_strategy_fields() -> None:
    field_names = {field.name for field in fields(MarketObservation)}

    assert field_names == {
        "identity",
        "provenance",
        "price_facts",
        "signal_facts",
        "structure_facts",
    }
    assert not field_names.intersection(
        {
            "market_state",
            "trend_regime",
            "direction",
            "entry_point",
            "target_price",
            "probability",
        }
    )


def test_observation_package_does_not_depend_on_research_or_strategy() -> None:
    package = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "market_platform"
        / "observation"
    )
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )

    assert "market_platform.research" not in source
    assert "market_platform.strategy" not in source
