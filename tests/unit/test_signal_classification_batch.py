from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from market_platform.signals import (
    SignalClassificationLevel,
    SignalClassificationSnapshot,
    SignalClassificationThresholds,
    classify_composite_signals,
)
from market_platform.signals.models import MarketSignal

_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _composite_signal(
    value: float | None,
    *,
    symbol: str = "MSFT",
    timestamp: datetime = _TIMESTAMP,
    name: str = "composite_score",
    parameters: dict[str, object] | None = None,
) -> MarketSignal:
    return MarketSignal(
        symbol=symbol,
        name=name,
        value=value,
        timestamp=timestamp,
        parameters=parameters or {"source": "test"},
    )


def _signal_generator(signals: list[MarketSignal]):
    yield from signals


def test_classify_composite_signals_handles_multiple_signals_in_order() -> None:
    signals = [_composite_signal(-0.9), _composite_signal(0.0), _composite_signal(0.8)]

    result = classify_composite_signals(signals)

    assert isinstance(result, SignalClassificationSnapshot)
    assert [classification.score for classification in result.classifications] == [
        pytest.approx(-0.9),
        pytest.approx(0.0),
        pytest.approx(0.8),
    ]
    assert [classification.level for classification in result.classifications] == [
        SignalClassificationLevel.STRONG_BEARISH,
        SignalClassificationLevel.NEUTRAL,
        SignalClassificationLevel.STRONG_BULLISH,
    ]


def test_classify_composite_signals_preserves_input_order() -> None:
    signals = [_composite_signal(0.8), _composite_signal(-0.9), _composite_signal(0.0)]

    result = classify_composite_signals(signals)

    assert [classification.score for classification in result.classifications] == [
        pytest.approx(0.8),
        pytest.approx(-0.9),
        pytest.approx(0.0),
    ]


def test_classify_composite_signals_accepts_list_input() -> None:
    signals = [_composite_signal(-0.2), _composite_signal(0.2)]

    result = classify_composite_signals(signals)

    assert len(result.classifications) == 2


def test_classify_composite_signals_accepts_tuple_input() -> None:
    signals = (_composite_signal(-0.2), _composite_signal(0.2))

    result = classify_composite_signals(signals)

    assert len(result.classifications) == 2


def test_classify_composite_signals_accepts_generator_input() -> None:
    signals = [_composite_signal(-0.2), _composite_signal(0.2)]

    result = classify_composite_signals(_signal_generator(signals))

    assert len(result.classifications) == 2


def test_classify_composite_signals_allows_empty_input() -> None:
    result = classify_composite_signals([])

    assert result == SignalClassificationSnapshot(
        classifications=(),
        thresholds=SignalClassificationThresholds(),
    )


def test_classify_composite_signals_uses_custom_thresholds() -> None:
    thresholds = SignalClassificationThresholds(
        strong_bearish=-0.75,
        bearish=-0.25,
        bullish=0.25,
        strong_bullish=0.75,
    )
    signals = [_composite_signal(-0.5), _composite_signal(0.5)]

    result = classify_composite_signals(signals, thresholds=thresholds)

    assert result.thresholds == thresholds
    assert [classification.level for classification in result.classifications] == [
        SignalClassificationLevel.BEARISH,
        SignalClassificationLevel.BULLISH,
    ]


def test_classify_composite_signals_propagates_invalid_signal_fail_fast() -> None:
    signals = [
        _composite_signal(-0.9),
        _composite_signal(0.0, name="momentum"),
        _composite_signal(0.8),
    ]

    with pytest.raises(ValueError, match="composite_score"):
        classify_composite_signals(signals)


def test_classify_composite_signals_does_not_mutate_inputs() -> None:
    parameters = {"source": "test", "nested": {"keep": True}}
    signals = [_composite_signal(-0.9, parameters=parameters), _composite_signal(0.8)]
    original = deepcopy(signals)

    classify_composite_signals(signals)

    assert signals == original
    assert signals[0].parameters == parameters


def test_classify_composite_signals_result_is_immutable() -> None:
    result = classify_composite_signals([_composite_signal(-0.9)])

    with pytest.raises(FrozenInstanceError):
        result.classifications = ()  # type: ignore[misc]


def test_package_level_public_import() -> None:
    result = classify_composite_signals([_composite_signal(0.8)])

    assert result.classifications[0].level == SignalClassificationLevel.STRONG_BULLISH
