from __future__ import annotations

from datetime import UTC, datetime

import pytest

from market_platform.observation import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
    build_observation,
)


def _identity() -> ObservationIdentity:
    return ObservationIdentity(
        symbol="MSFT",
        interval="1day",
        as_of=datetime(2026, 7, 15, tzinfo=UTC),
        window_start=datetime(2026, 4, 1, tzinfo=UTC),
        window_end=datetime(2026, 7, 14, tzinfo=UTC),
    )


def _provenance(parameters: dict[str, object]) -> ObservationProvenance:
    return ObservationProvenance(
        provider="polygon",
        methodology="market_observation",
        methodology_version="v1",
        parameters=parameters,
        input_fingerprint="sha256:abc123",
    )


def test_build_observation_returns_minimal_boundary_model() -> None:
    identity = _identity()
    provenance = _provenance({"lookback_days": 120})

    observation = build_observation(identity, provenance)

    assert observation == MarketObservation(
        identity=identity,
        provenance=provenance,
    )
    assert observation.identity is identity
    assert observation.provenance is provenance


def test_build_observation_does_not_modify_inputs() -> None:
    parameters: dict[str, object] = {"lookback_days": 120}
    identity = _identity()
    provenance = _provenance(parameters)
    identity_before = identity.to_dict()
    provenance_before = provenance.to_dict()
    parameters_before = dict(parameters)

    build_observation(identity, provenance)

    assert identity.to_dict() == identity_before
    assert provenance.to_dict() == provenance_before
    assert parameters == parameters_before


@pytest.mark.parametrize(
    ("identity", "provenance", "message"),
    [
        ("identity", _provenance({}), "identity must be an ObservationIdentity"),
        (_identity(), "provenance", "provenance must be an ObservationProvenance"),
    ],
)
def test_build_observation_rejects_invalid_boundary_models(
    identity: object,
    provenance: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        build_observation(
            identity,  # type: ignore[arg-type]
            provenance,  # type: ignore[arg-type]
        )
