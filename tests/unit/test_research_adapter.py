from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_platform.research.adapter import adapt_market_state_to_view
from market_platform.research.models import MarketView
from market_platform.state import (
    DirectionalRegime,
    MarketState,
    MomentumRegime,
    StateModelProvenance,
    StateQuality,
    StructureState,
    TrendRegime,
    VolatilityRegime,
)


def _state(**overrides: object) -> MarketState:
    values: dict[str, object] = {
        "symbol": "MSFT",
        "interval": "1day",
        "as_of": datetime(2026, 7, 16, tzinfo=UTC),
        "provenance": StateModelProvenance(
            model_id="test-state-model",
            model_version="1.0.0",
            parameters={},
            observation_fingerprint="sha256:observation",
        ),
        "directional_regime": DirectionalRegime.UP,
        "trend_regime": TrendRegime.UP,
        "momentum_regime": MomentumRegime.POSITIVE,
        "volatility_regime": VolatilityRegime.NORMAL,
        "structure_state": StructureState.AVAILABLE,
        "quality": StateQuality.COMPLETE,
        "missing_inputs": (),
    }
    values.update(overrides)
    return MarketState(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("regime", "direction", "strength"),
    [
        (DirectionalRegime.STRONG_UP, "bullish", "strong"),
        (DirectionalRegime.UP, "bullish", "moderate"),
        (DirectionalRegime.NEUTRAL, "neutral", "neutral"),
        (DirectionalRegime.DOWN, "bearish", "moderate"),
        (DirectionalRegime.STRONG_DOWN, "bearish", "strong"),
        (DirectionalRegime.UNAVAILABLE, None, None),
        (DirectionalRegime.INDETERMINATE, None, None),
    ],
)
def test_directional_regime_mapping(
    regime: DirectionalRegime,
    direction: str | None,
    strength: str | None,
) -> None:
    view = adapt_market_state_to_view(_state(directional_regime=regime))

    assert view.direction == direction
    assert view.strength == strength


@pytest.mark.parametrize(
    ("regime", "expected"),
    [
        (TrendRegime.STRONG_UP, "strongly_positive"),
        (TrendRegime.UP, "positive"),
        (TrendRegime.NEUTRAL, "neutral"),
        (TrendRegime.DOWN, "negative"),
        (TrendRegime.STRONG_DOWN, "strongly_negative"),
        (TrendRegime.UNAVAILABLE, None),
        (TrendRegime.INDETERMINATE, "indeterminate"),
    ],
)
def test_trend_regime_mapping(
    regime: TrendRegime,
    expected: str | None,
) -> None:
    view = adapt_market_state_to_view(_state(trend_regime=regime))

    assert view.trend_state == expected


@pytest.mark.parametrize(
    ("regime", "expected"),
    [
        (MomentumRegime.STRONG_POSITIVE, "strongly_positive"),
        (MomentumRegime.POSITIVE, "positive"),
        (MomentumRegime.NEUTRAL, "neutral"),
        (MomentumRegime.NEGATIVE, "negative"),
        (MomentumRegime.STRONG_NEGATIVE, "strongly_negative"),
        (MomentumRegime.UNAVAILABLE, None),
        (MomentumRegime.INDETERMINATE, "indeterminate"),
    ],
)
def test_momentum_regime_mapping(
    regime: MomentumRegime,
    expected: str | None,
) -> None:
    view = adapt_market_state_to_view(_state(momentum_regime=regime))

    assert view.momentum_state == expected


@pytest.mark.parametrize(
    ("regime", "expected"),
    [
        (VolatilityRegime.LOW, "low"),
        (VolatilityRegime.NORMAL, "normal"),
        (VolatilityRegime.HIGH, "high"),
        (VolatilityRegime.UNAVAILABLE, "unavailable"),
        (VolatilityRegime.INDETERMINATE, "indeterminate"),
    ],
)
def test_volatility_regime_mapping(
    regime: VolatilityRegime,
    expected: str,
) -> None:
    view = adapt_market_state_to_view(_state(volatility_regime=regime))

    assert view.volatility_state == expected


@pytest.mark.parametrize(
    ("state_value", "expected"),
    [
        (StructureState.AVAILABLE, "available"),
        (StructureState.OBSERVED, "observed"),
        (StructureState.INSUFFICIENT, "insufficient"),
        (StructureState.UNAVAILABLE, None),
        (StructureState.INDETERMINATE, "indeterminate"),
    ],
)
def test_structure_state_mapping(
    state_value: StructureState,
    expected: str | None,
) -> None:
    view = adapt_market_state_to_view(_state(structure_state=state_value))

    assert view.price_structure == expected


def test_unavailable_state_is_represented_without_inventing_direction() -> None:
    state = _state(
        directional_regime=DirectionalRegime.UNAVAILABLE,
        trend_regime=TrendRegime.UNAVAILABLE,
        momentum_regime=MomentumRegime.UNAVAILABLE,
        volatility_regime=VolatilityRegime.UNAVAILABLE,
        structure_state=StructureState.UNAVAILABLE,
        quality=StateQuality.UNAVAILABLE,
        missing_inputs=("signal_facts", "structure_facts"),
    )

    view = adapt_market_state_to_view(state)

    assert view == MarketView(
        direction=None,
        strength=None,
        trend_state=None,
        momentum_state=None,
        volatility_state="unavailable",
        price_structure=None,
        confidence=None,
    )


@pytest.mark.parametrize(
    ("quality", "missing_inputs"),
    [
        (StateQuality.COMPLETE, ()),
        (StateQuality.DEGRADED, ("momentum",)),
        (StateQuality.UNAVAILABLE, ("signal_facts",)),
    ],
)
def test_quality_does_not_become_unvalidated_confidence(
    quality: StateQuality,
    missing_inputs: tuple[str, ...],
) -> None:
    view = adapt_market_state_to_view(
        _state(quality=quality, missing_inputs=missing_inputs)
    )

    assert view.confidence is None


def test_adapter_does_not_modify_input_state() -> None:
    state = _state()
    before = state.to_dict()

    adapt_market_state_to_view(state)

    assert state.to_dict() == before


def test_adapter_output_uses_existing_market_view_schema() -> None:
    view = adapt_market_state_to_view(_state())

    assert isinstance(view, MarketView)
    assert {field.name for field in fields(view)} == {
        "direction",
        "strength",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "price_structure",
        "confidence",
    }
    assert set(view.to_dict()) == {
        "direction",
        "strength",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "price_structure",
        "confidence",
    }


def test_adapter_has_no_computation_or_data_dependencies() -> None:
    adapter_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "market_platform"
        / "research"
        / "adapter.py"
    )
    source = adapter_path.read_text(encoding="utf-8")

    assert "market_platform.research.interpretation" not in source
    assert "market_platform.signals" not in source
    assert "market_platform.data" not in source
    assert "calculate_composite" not in source
    assert "classify_" not in source
    assert "interpret_" not in source


def test_adapter_rejects_non_state_input() -> None:
    with pytest.raises(TypeError, match="state must be a MarketState"):
        adapt_market_state_to_view("state")  # type: ignore[arg-type]
