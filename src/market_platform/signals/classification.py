"""Composite signal classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from numbers import Real

import numpy as np

from market_platform.signals.models import MarketSignal

_COMPOSITE_SIGNAL_NAME = "composite_score"
_DEFAULT_STRONG_BEARISH = -0.60
_DEFAULT_BEARISH = -0.20
_DEFAULT_BULLISH = 0.20
_DEFAULT_STRONG_BULLISH = 0.60


class SignalClassificationLevel(StrEnum):
    """Discrete classification levels for a composite signal."""

    STRONG_BEARISH = "strong_bearish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    BULLISH = "bullish"
    STRONG_BULLISH = "strong_bullish"


@dataclass(frozen=True, slots=True)
class SignalClassificationThresholds:
    """Monotonic threshold boundaries used to classify composite scores."""

    strong_bearish: float = _DEFAULT_STRONG_BEARISH
    bearish: float = _DEFAULT_BEARISH
    bullish: float = _DEFAULT_BULLISH
    strong_bullish: float = _DEFAULT_STRONG_BULLISH

    def __post_init__(self) -> None:
        strong_bearish = _normalize_threshold(self.strong_bearish, "strong_bearish")
        bearish = _normalize_threshold(self.bearish, "bearish")
        bullish = _normalize_threshold(self.bullish, "bullish")
        strong_bullish = _normalize_threshold(
            self.strong_bullish,
            "strong_bullish",
        )

        if not strong_bearish < bearish < bullish < strong_bullish:
            raise ValueError(
                "Thresholds must satisfy strong_bearish < bearish < bullish < "
                "strong_bullish"
            )

        object.__setattr__(self, "strong_bearish", strong_bearish)
        object.__setattr__(self, "bearish", bearish)
        object.__setattr__(self, "bullish", bullish)
        object.__setattr__(self, "strong_bullish", strong_bullish)


@dataclass(frozen=True, slots=True)
class SignalClassification:
    """Immutable classification result for a composite score."""

    symbol: str
    timestamp: datetime
    score: float
    level: SignalClassificationLevel
    thresholds: SignalClassificationThresholds
    source_signal_name: str = _COMPOSITE_SIGNAL_NAME


def classify_composite_signal(
    signal: MarketSignal,
    thresholds: SignalClassificationThresholds | None = None,
) -> SignalClassification:
    """Classify a composite score into one of five ordered levels."""

    if signal.name != _COMPOSITE_SIGNAL_NAME:
        raise ValueError("Signal must be named composite_score")

    score = _normalize_score(signal.value)
    if thresholds is None:
        thresholds = SignalClassificationThresholds()

    level = _classify_score(score, thresholds)
    return SignalClassification(
        symbol=signal.symbol,
        timestamp=signal.timestamp,
        score=score,
        level=level,
        thresholds=thresholds,
    )


def _classify_score(
    score: float,
    thresholds: SignalClassificationThresholds,
) -> SignalClassificationLevel:
    if score <= thresholds.strong_bearish:
        return SignalClassificationLevel.STRONG_BEARISH
    if score <= thresholds.bearish:
        return SignalClassificationLevel.BEARISH
    if score < thresholds.bullish:
        return SignalClassificationLevel.NEUTRAL
    if score < thresholds.strong_bullish:
        return SignalClassificationLevel.BULLISH
    return SignalClassificationLevel.STRONG_BULLISH


def _normalize_score(value: object) -> float:
    if value is None:
        raise ValueError("Composite signal value must be numeric")
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Composite signal value must be numeric")

    score = float(value)
    if not np.isfinite(score):
        raise ValueError("Composite signal value must be finite")
    if score < -1.0 or score > 1.0:
        raise ValueError("Composite signal value must be within [-1.0, 1.0]")
    return score


def _normalize_threshold(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} threshold must be numeric")

    threshold = float(value)
    if not np.isfinite(threshold):
        raise ValueError(f"{name} threshold must be finite")
    if threshold < -1.0 or threshold > 1.0:
        raise ValueError(f"{name} threshold must be within [-1.0, 1.0]")
    return threshold