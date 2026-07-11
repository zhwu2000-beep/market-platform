from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from market_platform.signals import (
    SignalClassification,
    SignalClassificationLevel,
    SignalClassificationThresholds,
    classify_composite_signal,
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


def test_classify_composite_signal_uses_default_thresholds() -> None:
    signal = _composite_signal(0.32)

    result = classify_composite_signal(signal)

    assert isinstance(result, SignalClassification)
    assert result.symbol == "MSFT"
    assert result.timestamp == _TIMESTAMP
    assert result.score == pytest.approx(0.32)
    assert result.level == SignalClassificationLevel.BULLISH
    assert result.thresholds == SignalClassificationThresholds()
    assert result.source_signal_name == "composite_score"


@pytest.mark.parametrize(
    ("score", "expected_level"),
    [
        (-1.0, SignalClassificationLevel.STRONG_BEARISH),
        (-0.60, SignalClassificationLevel.STRONG_BEARISH),
        (-0.599999, SignalClassificationLevel.BEARISH),
        (-0.20, SignalClassificationLevel.BEARISH),
        (-0.199999, SignalClassificationLevel.NEUTRAL),
        (0.0, SignalClassificationLevel.NEUTRAL),
        (0.199999, SignalClassificationLevel.NEUTRAL),
        (0.20, SignalClassificationLevel.BULLISH),
        (0.599999, SignalClassificationLevel.BULLISH),
        (0.60, SignalClassificationLevel.STRONG_BULLISH),
        (1.0, SignalClassificationLevel.STRONG_BULLISH),
    ],
)
def test_classify_composite_signal_boundary_behavior(
    score: float,
    expected_level: SignalClassificationLevel,
) -> None:
    result = classify_composite_signal(_composite_signal(score))

    assert result.level == expected_level
    assert result.score == pytest.approx(score)


def test_classify_composite_signal_rejects_non_composite_signal_name() -> None:
    signal = _composite_signal(0.1, name="momentum")

    with pytest.raises(ValueError, match="composite_score"):
        classify_composite_signal(signal)


@pytest.mark.parametrize("value", [None, "1", True, False])
def test_classify_composite_signal_rejects_non_numeric_signal_values(
    value: object,
) -> None:
    signal = _composite_signal(value)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="numeric"):
        classify_composite_signal(signal)


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_classify_composite_signal_rejects_non_finite_signal_values(
    value: float,
) -> None:
    signal = _composite_signal(value)

    with pytest.raises(ValueError, match="finite"):
        classify_composite_signal(signal)


@pytest.mark.parametrize("value", [-1.01, 1.01])
def test_classify_composite_signal_rejects_out_of_range_values(value: float) -> None:
    signal = _composite_signal(value)

    with pytest.raises(ValueError, match=r"\[-1\.0, 1\.0\]"):
        classify_composite_signal(signal)


def test_classify_composite_signal_accepts_custom_thresholds() -> None:
    thresholds = SignalClassificationThresholds(
        strong_bearish=-0.75,
        bearish=-0.25,
        bullish=0.25,
        strong_bullish=0.75,
    )
    signal = _composite_signal(0.5)

    result = classify_composite_signal(signal, thresholds=thresholds)

    assert result.level == SignalClassificationLevel.BULLISH
    assert result.thresholds == thresholds


def test_classify_composite_signal_rejects_invalid_threshold_ordering() -> None:
    with pytest.raises(
        ValueError,
        match=r"strong_bearish < bearish < bullish < strong_bullish",
    ):
        SignalClassificationThresholds(
            strong_bearish=-0.20,
            bearish=-0.60,
            bullish=0.20,
            strong_bullish=0.60,
        )


@pytest.mark.parametrize(
    ("threshold_kwargs", "expected_message"),
    [
        ({"strong_bearish": float("nan")}, "strong_bearish threshold must be finite"),
        ({"bearish": float("inf")}, "bearish threshold must be finite"),
        ({"bullish": -1.5}, r"bullish threshold must be within \[-1.0, 1.0\]"),
        ({"strong_bullish": True}, "strong_bullish threshold must be numeric"),
    ],
)
def test_classify_composite_signal_rejects_invalid_threshold_values(
    threshold_kwargs: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        SignalClassificationThresholds(**threshold_kwargs)  # type: ignore[arg-type]


def test_classify_composite_signal_preserves_input_signal_metadata() -> None:
    parameters = {"source": "test", "nested": {"keep": True}}
    signal = _composite_signal(0.1, parameters=parameters)
    original = deepcopy(signal)

    result = classify_composite_signal(signal)

    assert signal == original
    assert result.symbol == signal.symbol
    assert result.timestamp == signal.timestamp
    assert result.score == pytest.approx(0.1)


def test_classify_composite_signal_preserves_same_instant_timezone() -> None:
    signal = MarketSignal(
        symbol="MSFT",
        name="composite_score",
        value=0.1,
        timestamp=datetime(2026, 1, 1, 4, tzinfo=UTC),
        parameters={"source": "test"},
    )

    result = classify_composite_signal(signal)

    assert result.timestamp == datetime(2026, 1, 1, 4, tzinfo=UTC)
    assert result.timestamp.tzinfo is UTC


def test_classification_result_is_immutable() -> None:
    result = classify_composite_signal(_composite_signal(0.1))

    with pytest.raises(FrozenInstanceError):
        result.score = 0.2  # type: ignore[misc]


def test_package_level_public_import() -> None:
    result = classify_composite_signal(_composite_signal(-0.9))

    assert result.level == SignalClassificationLevel.STRONG_BEARISH
