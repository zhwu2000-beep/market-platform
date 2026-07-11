from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from market_platform.signals import (
    SignalClassification,
    SignalClassificationLevel,
    SignalClassificationSnapshot,
    SignalClassificationSort,
    SignalClassificationThresholds,
    sort_signal_classifications,
)

_TIMESTAMP = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)


def _classification(symbol: str, score: float) -> SignalClassification:
    return SignalClassification(
        symbol=symbol,
        timestamp=_TIMESTAMP,
        score=score,
        level=SignalClassificationLevel.NEUTRAL,
        thresholds=SignalClassificationThresholds(),
    )


def _snapshot(*classifications: SignalClassification) -> SignalClassificationSnapshot:
    return SignalClassificationSnapshot(
        classifications=classifications,
        thresholds=SignalClassificationThresholds(),
    )


def test_sort_signal_classifications_preserves_input_order() -> None:
    snapshot = _snapshot(_classification("MSFT", 0.10), _classification("AAPL", 0.72))

    result = sort_signal_classifications(snapshot)

    assert result is snapshot
    assert result.classifications == snapshot.classifications


def test_sort_signal_classifications_input_returns_original_snapshot() -> None:
    snapshot = _snapshot(_classification("MSFT", 0.10))

    result = sort_signal_classifications(snapshot, SignalClassificationSort.INPUT)

    assert result is snapshot


def test_sort_signal_classifications_orders_score_descending() -> None:
    snapshot = _snapshot(
        _classification("MSFT", 0.10),
        _classification("AAPL", 0.72),
        _classification("GOOG", 0.33),
    )

    result = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_DESC)

    assert [classification.symbol for classification in result.classifications] == [
        "AAPL",
        "GOOG",
        "MSFT",
    ]


def test_sort_signal_classifications_orders_score_ascending() -> None:
    snapshot = _snapshot(
        _classification("MSFT", 0.10),
        _classification("AAPL", 0.72),
        _classification("GOOG", 0.33),
    )

    result = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_ASC)

    assert [classification.symbol for classification in result.classifications] == [
        "MSFT",
        "GOOG",
        "AAPL",
    ]


def test_sort_signal_classifications_is_stable_for_equal_scores() -> None:
    snapshot = _snapshot(
        _classification("MSFT", 0.50),
        _classification("AAPL", 0.50),
        _classification("GOOG", 0.20),
    )

    desc = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_DESC)
    asc = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_ASC)

    assert [classification.symbol for classification in desc.classifications[:2]] == [
        "MSFT",
        "AAPL",
    ]
    assert [classification.symbol for classification in asc.classifications[-2:]] == [
        "MSFT",
        "AAPL",
    ]


def test_sort_signal_classifications_accepts_empty_snapshot() -> None:
    snapshot = _snapshot()

    result = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_DESC)

    assert result.classifications == ()
    assert result.thresholds is snapshot.thresholds


def test_sort_signal_classifications_preserves_thresholds_object() -> None:
    thresholds = SignalClassificationThresholds()
    snapshot = SignalClassificationSnapshot(
        classifications=(
            _classification("MSFT", 0.10),
            _classification("AAPL", 0.72),
        ),
        thresholds=thresholds,
    )

    result = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_ASC)

    assert result.thresholds is thresholds


def test_sort_signal_classifications_does_not_mutate_input_snapshot() -> None:
    snapshot = _snapshot(
        _classification("MSFT", 0.10),
        _classification("AAPL", 0.72),
    )
    original = deepcopy(snapshot)

    sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_DESC)

    assert snapshot == original


def test_sort_signal_classifications_returns_tuple_output() -> None:
    snapshot = _snapshot(
        _classification("MSFT", 0.10),
        _classification("AAPL", 0.72),
    )

    result = sort_signal_classifications(snapshot, SignalClassificationSort.SCORE_DESC)

    assert isinstance(result.classifications, tuple)


def test_package_level_public_import() -> None:
    snapshot = _snapshot(_classification("MSFT", 0.10))

    result = sort_signal_classifications(snapshot)

    assert result is snapshot
