from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.signals import calculate_composite_signal
from market_platform.signals.models import MarketSignal

_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _signal(name: str, value: float | None, *, symbol: str = "MSFT") -> MarketSignal:
    return MarketSignal(
        symbol=symbol,
        name=name,
        value=value,
        timestamp=_TIMESTAMP,
        parameters={"source": "test"},
    )


def test_weighted_two_components() -> None:
    signals = [_signal("trend", 1.0), _signal("momentum", 3.0)]
    weights = {"trend": 1.0, "momentum": 3.0}

    result = calculate_composite_signal(signals, weights)

    assert result.symbol == "MSFT"
    assert result.name == "composite_score"
    assert result.timestamp == _TIMESTAMP
    assert result.value == pytest.approx(2.5)
    assert result.parameters["missing_policy"] == "exclude"
    assert list(result.parameters["configured_weights"].keys()) == [
        "trend",
        "momentum",
    ]
    assert result.parameters["configured_weights"] == {
        "trend": 1.0,
        "momentum": 3.0,
    }
    assert result.parameters["normalized_weights"] == {
        "trend": pytest.approx(0.25),
        "momentum": pytest.approx(0.75),
    }
    assert result.parameters["component_values"] == {"trend": 1.0, "momentum": 3.0}
    assert result.parameters["component_contributions"] == {
        "trend": pytest.approx(0.25),
        "momentum": pytest.approx(2.25),
    }
    assert result.parameters["included_signals"] == ["trend", "momentum"]
    assert result.parameters["missing_signals"] == []


def test_equal_weights() -> None:
    signals = [_signal("trend", 2.0), _signal("momentum", 6.0)]
    weights = {"trend": 1.0, "momentum": 1.0}

    result = calculate_composite_signal(signals, weights)

    assert result.value == pytest.approx(4.0)
    assert result.parameters["normalized_weights"] == {
        "trend": pytest.approx(0.5),
        "momentum": pytest.approx(0.5),
    }


def test_weight_metadata_order_is_deterministic() -> None:
    signals = [_signal("trend", 2.0), _signal("momentum", 6.0)]
    weights = {"momentum": 3.0, "trend": 1.0}

    result = calculate_composite_signal(signals, weights)

    assert list(result.parameters["configured_weights"].keys()) == [
        "momentum",
        "trend",
    ]
    assert list(result.parameters["normalized_weights"].keys()) == [
        "momentum",
        "trend",
    ]
    assert list(result.parameters["component_values"].keys()) == [
        "momentum",
        "trend",
    ]
    assert list(result.parameters["component_contributions"].keys()) == [
        "momentum",
        "trend",
    ]
    assert result.parameters["included_signals"] == ["momentum", "trend"]


def test_exclude_policy_one_missing_component() -> None:
    signals = [_signal("trend", 2.0), _signal("momentum", None)]
    weights = {"trend": 2.0, "momentum": 6.0}

    result = calculate_composite_signal(signals, weights, missing_policy="exclude")

    assert result.value == pytest.approx(2.0)
    assert result.parameters["missing_policy"] == "exclude"
    assert result.parameters["normalized_weights"] == {"trend": pytest.approx(1.0)}
    assert result.parameters["component_values"] == {"trend": 2.0, "momentum": None}
    assert result.parameters["component_contributions"] == {"trend": pytest.approx(2.0)}
    assert result.parameters["included_signals"] == ["trend"]
    assert result.parameters["missing_signals"] == ["momentum"]


def test_exclude_policy_with_all_components_missing() -> None:
    signals = [_signal("trend", None), _signal("momentum", None)]
    weights = {"trend": 2.0, "momentum": 6.0}

    result = calculate_composite_signal(signals, weights, missing_policy="exclude")

    assert result.value is None
    assert result.parameters["missing_policy"] == "exclude"
    assert result.parameters["normalized_weights"] == {}
    assert result.parameters["component_contributions"] == {}
    assert result.parameters["included_signals"] == []
    assert result.parameters["missing_signals"] == ["trend", "momentum"]


def test_require_all_policy_with_missing_component() -> None:
    signals = [_signal("trend", 2.0), _signal("momentum", None)]
    weights = {"trend": 2.0, "momentum": 6.0}

    result = calculate_composite_signal(
        signals,
        weights,
        missing_policy="require_all",
    )

    assert result.value is None
    assert result.parameters["missing_policy"] == "require_all"
    assert result.parameters["normalized_weights"] == {}
    assert result.parameters["component_contributions"] == {}
    assert result.parameters["included_signals"] == []
    assert result.parameters["missing_signals"] == ["momentum"]


def test_rejects_unsupported_missing_policy() -> None:
    signals = [_signal("trend", 2.0)]
    weights = {"trend": 1.0}

    with pytest.raises(ValueError, match="missing_policy"):
        calculate_composite_signal(signals, weights, missing_policy="drop")


def test_rejects_empty_signals() -> None:
    with pytest.raises(ValueError, match="signals must not be empty"):
        calculate_composite_signal([], {"trend": 1.0})


def test_rejects_empty_weights() -> None:
    with pytest.raises(ValueError, match="weights must not be empty"):
        calculate_composite_signal([_signal("trend", 1.0)], {})


def test_rejects_mismatched_symbols() -> None:
    signals = [_signal("trend", 1.0), _signal("momentum", 2.0, symbol="SPY")]
    weights = {"trend": 1.0, "momentum": 1.0}

    with pytest.raises(ValueError, match="same symbol"):
        calculate_composite_signal(signals, weights)


def test_rejects_mismatched_timestamps() -> None:
    signals = [
        _signal("trend", 1.0),
        MarketSignal(
            symbol="MSFT",
            name="momentum",
            value=2.0,
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            parameters={"source": "test"},
        ),
    ]
    weights = {"trend": 1.0, "momentum": 1.0}

    with pytest.raises(ValueError, match="same timestamp"):
        calculate_composite_signal(signals, weights)


def test_rejects_duplicate_signal_names() -> None:
    signals = [_signal("trend", 1.0), _signal("trend", 2.0)]
    weights = {"trend": 1.0}

    with pytest.raises(ValueError, match="Signal names must be unique"):
        calculate_composite_signal(signals, weights)


def test_rejects_unknown_weight_names() -> None:
    signals = [_signal("trend", 1.0)]
    weights = {"trend": 1.0, "momentum": 1.0}

    with pytest.raises(ValueError, match="Unknown weight name"):
        calculate_composite_signal(signals, weights)


@pytest.mark.parametrize("weight", [0, -1])
def test_rejects_non_positive_weights(weight: object) -> None:
    signals = [_signal("trend", 1.0)]
    weights = {"trend": weight}  # type: ignore[dict-item]

    with pytest.raises(ValueError, match="strictly positive"):
        calculate_composite_signal(signals, weights)


@pytest.mark.parametrize("weight", ["1", True, False, float("inf"), float("nan")])
def test_rejects_invalid_weights(weight: object) -> None:
    signals = [_signal("trend", 1.0)]
    weights = {"trend": weight}  # type: ignore[dict-item]

    with pytest.raises(ValueError):
        calculate_composite_signal(signals, weights)


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_rejects_non_finite_component_values(value: float) -> None:
    signals = [_signal("trend", value)]
    weights = {"trend": 1.0}

    with pytest.raises(ValueError, match="must be finite"):
        calculate_composite_signal(signals, weights)


def test_rejects_boolean_component_values() -> None:
    signals = [_signal("trend", True)]
    weights = {"trend": 1.0}

    with pytest.raises(ValueError, match="numeric or None"):
        calculate_composite_signal(signals, weights)


def test_timezone_normalization_accepts_same_instant_across_timezones() -> None:
    signals = [
        MarketSignal(
            symbol="MSFT",
            name="trend",
            value=1.0,
            timestamp=datetime(2026, 1, 1, 9, tzinfo=UTC),
            parameters={"source": "test"},
        ),
        MarketSignal(
            symbol=" msft ",
            name="momentum",
            value=3.0,
            timestamp=datetime(2026, 1, 1, 4, tzinfo=timezone(timedelta(hours=-5))),
            parameters={"source": "test"},
        ),
    ]
    weights = {"trend": 1.0, "momentum": 3.0}

    result = calculate_composite_signal(signals, weights)

    assert result.timestamp.tzinfo is UTC
    assert result.timestamp == datetime(2026, 1, 1, 9, tzinfo=UTC)
    assert result.symbol == "MSFT"


def test_symbol_whitespace_and_case_normalization_is_accepted() -> None:
    signals = [
        _signal("trend", 1.0, symbol=" msft "),
        _signal("momentum", 3.0, symbol="MSFT"),
    ]
    weights = {"trend": 1.0, "momentum": 3.0}

    result = calculate_composite_signal(signals, weights)

    assert result.symbol == "msft"
    assert result.value == pytest.approx(2.5)


def test_does_not_mutate_inputs() -> None:
    signals = [_signal("trend", 1.0), _signal("momentum", 3.0)]
    weights = {"trend": 1.0, "momentum": 3.0}
    signals_before = deepcopy(signals)
    weights_before = deepcopy(weights)

    calculate_composite_signal(signals, weights)

    assert signals == signals_before
    assert weights == weights_before


def test_public_import() -> None:
    result = calculate_composite_signal([_signal("trend", 1.0)], {"trend": 1.0})

    assert result.name == "composite_score"
