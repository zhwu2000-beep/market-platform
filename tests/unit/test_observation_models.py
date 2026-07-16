from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.observation import (
    MarketObservation,
    ObservationIdentity,
    ObservationProvenance,
)

_AS_OF = datetime(2026, 7, 15, tzinfo=UTC)
_WINDOW_START = datetime(2026, 4, 1, tzinfo=UTC)
_WINDOW_END = datetime(2026, 7, 14, tzinfo=UTC)


def _identity() -> ObservationIdentity:
    return ObservationIdentity(
        symbol="MSFT",
        interval="1day",
        as_of=_AS_OF,
        window_start=_WINDOW_START,
        window_end=_WINDOW_END,
    )


def _provenance() -> ObservationProvenance:
    return ObservationProvenance(
        provider="polygon",
        methodology="market_observation",
        methodology_version="v1",
        parameters={"lookback_days": 120, "components": ("signals", "structure")},
        input_fingerprint="sha256:abc123",
    )


def test_observation_identity_normalizes_symbol_and_timestamps() -> None:
    identity = ObservationIdentity(
        symbol=" msft ",
        interval=" 1day ",
        as_of=datetime(
            2026,
            7,
            15,
            8,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        window_start=datetime(
            2026,
            4,
            1,
            8,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        window_end=datetime(
            2026,
            7,
            14,
            8,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    )

    assert identity.symbol == "MSFT"
    assert identity.interval == "1day"
    assert identity.as_of == datetime(2026, 7, 15, tzinfo=UTC)
    assert identity.window_start == datetime(2026, 4, 1, tzinfo=UTC)
    assert identity.window_end == datetime(2026, 7, 14, tzinfo=UTC)


def test_observation_models_are_frozen() -> None:
    identity = _identity()
    provenance = _provenance()
    observation = MarketObservation(identity=identity, provenance=provenance)

    with pytest.raises(FrozenInstanceError):
        identity.symbol = "AAPL"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        provenance.provider = "twelve_data"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observation.identity = identity  # type: ignore[misc]


def test_market_observation_serialization_is_nested_and_json_compatible() -> None:
    observation = MarketObservation(
        identity=_identity(),
        provenance=_provenance(),
    )

    payload = observation.to_dict()

    assert payload == {
        "identity": {
            "symbol": "MSFT",
            "interval": "1day",
            "as_of": _AS_OF.isoformat(),
            "window_start": _WINDOW_START.isoformat(),
            "window_end": _WINDOW_END.isoformat(),
        },
        "provenance": {
            "provider": "polygon",
            "methodology": "market_observation",
            "methodology_version": "v1",
            "parameters": {
                "lookback_days": 120,
                "components": ["signals", "structure"],
            },
            "input_fingerprint": "sha256:abc123",
        },
        "price_facts": None,
        "signal_facts": None,
        "structure_facts": None,
    }
    json.dumps(payload)


@pytest.mark.parametrize("field_name", ["symbol", "interval"])
def test_observation_identity_rejects_empty_text(field_name: str) -> None:
    kwargs = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "window_start": _WINDOW_START,
        "window_end": _WINDOW_END,
    }
    kwargs[field_name] = "  "

    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        ObservationIdentity(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field_name",
    ["as_of", "window_start", "window_end"],
)
def test_observation_identity_requires_aware_timestamps(field_name: str) -> None:
    kwargs = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": _AS_OF,
        "window_start": _WINDOW_START,
        "window_end": _WINDOW_END,
    }
    kwargs[field_name] = datetime(2026, 7, 1)

    with pytest.raises(ValueError, match=f"{field_name} must be timezone-aware"):
        ObservationIdentity(**kwargs)  # type: ignore[arg-type]


def test_observation_identity_rejects_invalid_window_order() -> None:
    with pytest.raises(ValueError, match="window_start must be earlier"):
        ObservationIdentity(
            symbol="MSFT",
            interval="1day",
            as_of=_AS_OF,
            window_start=_WINDOW_END,
            window_end=_WINDOW_START,
        )

    with pytest.raises(ValueError, match="window_end must be earlier"):
        ObservationIdentity(
            symbol="MSFT",
            interval="1day",
            as_of=_WINDOW_END,
            window_start=_WINDOW_START,
            window_end=_AS_OF,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "provider",
        "methodology",
        "methodology_version",
        "input_fingerprint",
    ],
)
def test_observation_provenance_rejects_empty_text(field_name: str) -> None:
    kwargs = {
        "provider": "polygon",
        "methodology": "market_observation",
        "methodology_version": "v1",
        "parameters": {},
        "input_fingerprint": "sha256:abc123",
    }
    kwargs[field_name] = " "

    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        ObservationProvenance(**kwargs)  # type: ignore[arg-type]


def test_observation_provenance_copies_parameters() -> None:
    parameters: dict[str, object] = {"lookback_days": 120}

    provenance = ObservationProvenance(
        provider="polygon",
        methodology="market_observation",
        methodology_version="v1",
        parameters=parameters,
        input_fingerprint="sha256:abc123",
    )
    parameters["lookback_days"] = 5
    parameters["new"] = True

    assert provenance.parameters == {"lookback_days": 120}


def test_observation_provenance_rejects_invalid_parameters() -> None:
    with pytest.raises(TypeError, match="parameters must be a mapping"):
        ObservationProvenance(
            provider="polygon",
            methodology="market_observation",
            methodology_version="v1",
            parameters=[("lookback_days", 120)],  # type: ignore[arg-type]
            input_fingerprint="sha256:abc123",
        )


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("identity", "identity", "identity must be an ObservationIdentity"),
        (
            "provenance",
            "provenance",
            "provenance must be an ObservationProvenance",
        ),
    ],
)
def test_market_observation_rejects_invalid_nested_models(
    field_name: str,
    value: object,
    message: str,
) -> None:
    kwargs = {"identity": _identity(), "provenance": _provenance()}
    kwargs[field_name] = value

    with pytest.raises(TypeError, match=message):
        MarketObservation(**kwargs)  # type: ignore[arg-type]
