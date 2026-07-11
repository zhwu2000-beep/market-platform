"""Batch composite signal classification helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from market_platform.signals.classification import (
    SignalClassification,
    SignalClassificationThresholds,
    classify_composite_signal,
)
from market_platform.signals.models import MarketSignal


@dataclass(frozen=True, slots=True)
class SignalClassificationSnapshot:
    """Immutable batch classification result for composite signals."""

    classifications: tuple[SignalClassification, ...]
    thresholds: SignalClassificationThresholds


def classify_composite_signals(
    signals: Iterable[MarketSignal],
    thresholds: SignalClassificationThresholds | None = None,
) -> SignalClassificationSnapshot:
    """Classify composite signals in input order using a shared threshold set."""

    resolved_thresholds = (
        SignalClassificationThresholds() if thresholds is None else thresholds
    )
    classifications = tuple(
        classify_composite_signal(signal, thresholds=resolved_thresholds)
        for signal in signals
    )
    return SignalClassificationSnapshot(
        classifications=classifications,
        thresholds=resolved_thresholds,
    )
