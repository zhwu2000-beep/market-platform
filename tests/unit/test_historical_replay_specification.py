from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from market_platform.replay import HistoricalReplaySpecification

_START = datetime(2026, 1, 10, tzinfo=UTC)


def _specification(**overrides: object) -> HistoricalReplaySpecification:
    values: dict[str, object] = {
        "symbol": " msft ",
        "interval": " 1day ",
        "context_start": _START,
        "evaluation_start": _START,
        "evaluation_end": _START + timedelta(days=2),
    }
    values.update(overrides)
    return HistoricalReplaySpecification(**values)  # type: ignore[arg-type]


def test_specification_is_immutable_normalized_and_deterministic() -> None:
    offset = timezone(timedelta(hours=5, minutes=30))
    specification = _specification(
        context_start=datetime(2026, 1, 10, 5, 30, tzinfo=offset),
        evaluation_start=datetime(2026, 1, 11, 5, 30, tzinfo=offset),
        evaluation_end=datetime(2026, 1, 12, 5, 30, tzinfo=offset),
    )

    assert specification.symbol == "MSFT"
    assert specification.interval == "1day"
    assert specification.context_start == _START
    assert specification.evaluation_start == _START + timedelta(days=1)
    assert specification.evaluation_end == _START + timedelta(days=2)
    assert specification == HistoricalReplaySpecification(
        symbol="MSFT",
        interval="1day",
        context_start=_START,
        evaluation_start=_START + timedelta(days=1),
        evaluation_end=_START + timedelta(days=2),
    )
    assert specification.to_dict() == {
        "symbol": "MSFT",
        "interval": "1day",
        "context_start": "2026-01-10T00:00:00+00:00",
        "evaluation_start": "2026-01-11T00:00:00+00:00",
        "evaluation_end": "2026-01-12T00:00:00+00:00",
    }
    with pytest.raises(FrozenInstanceError):
        specification.symbol = "AAPL"  # type: ignore[misc]


def test_context_may_equal_or_precede_evaluation_start() -> None:
    assert _specification().context_start == _specification().evaluation_start
    earlier = _specification(
        context_start=_START - timedelta(days=20),
        evaluation_start=_START,
    )
    assert earlier.context_start < earlier.evaluation_start


@pytest.mark.parametrize(
    "field",
    ["context_start", "evaluation_start", "evaluation_end"],
)
def test_specification_rejects_naive_timestamps(field: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must be timezone-aware"):
        _specification(**{field: datetime(2026, 1, 10)})


@pytest.mark.parametrize("field", ["symbol", "interval"])
def test_specification_rejects_empty_text(field: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must not be empty"):
        _specification(**{field: "  "})


def test_specification_rejects_invalid_temporal_ordering() -> None:
    with pytest.raises(ValueError, match="context_start"):
        _specification(
            context_start=_START + timedelta(days=1),
            evaluation_start=_START,
        )
    with pytest.raises(ValueError, match="evaluation_start"):
        _specification(evaluation_end=_START - timedelta(days=1))