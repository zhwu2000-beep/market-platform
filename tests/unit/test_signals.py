from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from market_platform.signals.calculators import (
    calculate_current_drawdown,
    calculate_distance_from_moving_average,
    calculate_momentum,
    calculate_realized_volatility,
    calculate_trend,
)
from market_platform.signals.service import calculate_market_signals


def _price_frame(
    *,
    symbol: str = "MSFT",
    rows: int = 60,
    start: datetime | None = None,
    closes: list[float] | None = None,
) -> pd.DataFrame:
    base_timestamp = start or datetime(2026, 1, 1, tzinfo=UTC)
    values = (
        closes
        if closes is not None
        else [100.0 + float(index) for index in range(rows)]
    )
    timestamps = [
        base_timestamp + timedelta(days=index) for index in range(len(values))
    ]

    return pd.DataFrame(
        {
            "symbol": [symbol] * len(values),
            "timestamp": timestamps,
            "open": values,
            "high": [value + 1.0 for value in values],
            "low": [value - 1.0 for value in values],
            "close": values,
            "volume": [1_000_000 + index for index in range(len(values))],
            "provider": ["twelvedata"] * len(values),
        }
    )


def test_calculators_match_expected_formulas() -> None:
    frame = _price_frame(rows=60)
    closes = pd.Series(frame["close"].to_list(), dtype="float64")

    expected_trend = (
        closes.rolling(20).mean().iloc[-1] / closes.rolling(50).mean().iloc[-1]
        - 1.0
    )
    expected_momentum = closes.iloc[-1] / closes.iloc[-21] - 1.0
    log_returns = np.log(closes / closes.shift(1)).iloc[-20:]
    expected_volatility = float(log_returns.std(ddof=1)) * float(np.sqrt(252))
    expected_drawdown = closes.iloc[-1] / closes.max() - 1.0
    expected_distance = closes.iloc[-1] / closes.rolling(20).mean().iloc[-1] - 1.0

    assert calculate_trend(frame) == pytest.approx(expected_trend)
    assert calculate_momentum(frame) == pytest.approx(expected_momentum)
    assert calculate_realized_volatility(frame) == pytest.approx(expected_volatility)
    assert calculate_current_drawdown(frame) == pytest.approx(expected_drawdown)
    assert calculate_distance_from_moving_average(frame) == pytest.approx(
        expected_distance
    )


@pytest.mark.parametrize(
    ("short_window", "long_window"),
    [
        (20, 20),
        (21, 20),
    ],
)
def test_calculate_trend_rejects_invalid_window_relationships(
    short_window: int,
    long_window: int,
) -> None:
    frame = _price_frame(rows=60)

    with pytest.raises(ValueError, match="strictly less than long_window"):
        calculate_trend(frame, short_window=short_window, long_window=long_window)


def test_calculate_market_signals_sorts_unsorted_input_without_mutating_source(
) -> None:
    frame = _price_frame(rows=60)
    original = frame.copy(deep=True)
    unsorted = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)

    snapshot = calculate_market_signals(unsorted)

    reshuffled = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)
    pd.testing.assert_frame_equal(unsorted, reshuffled)
    pd.testing.assert_frame_equal(frame, original)
    assert snapshot.symbol == "MSFT"
    assert snapshot.timestamp == pd.Timestamp("2026-03-01T00:00:00Z").to_pydatetime()
    assert snapshot.timestamp.tzinfo is not None


def test_calculate_market_signals_returns_none_for_signals_with_insufficient_history(
) -> None:
    frame = _price_frame(rows=10)

    snapshot = calculate_market_signals(frame)

    values = {signal.name: signal.value for signal in snapshot.signals}
    assert values["trend"] is None
    assert values["momentum"] is None
    assert values["realized_volatility"] is None
    assert values["distance_from_moving_average"] is None
    assert values["current_drawdown"] == pytest.approx(0.0)


def test_calculate_market_signals_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_market_signals(pd.DataFrame())


def test_calculate_market_signals_rejects_missing_required_columns() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        calculate_market_signals(pd.DataFrame({"symbol": ["MSFT"]}))


@pytest.mark.parametrize(
    ("calculator", "kwargs"),
    [
        (calculate_trend, {"short_window": 0}),
        (calculate_trend, {"short_window": -1}),
        (calculate_momentum, {"window": 0}),
        (calculate_realized_volatility, {"window": 0}),
        (calculate_distance_from_moving_average, {"window": 0}),
    ],
)
def test_calculators_reject_invalid_windows(calculator, kwargs) -> None:
    frame = _price_frame(rows=60)

    with pytest.raises(ValueError, match="positive integer"):
        calculator(frame, **kwargs)


def test_calculate_market_signals_rejects_multiple_symbols() -> None:
    frame = _price_frame(rows=60)
    frame.loc[0, "symbol"] = "AAPL"

    with pytest.raises(ValueError, match="exactly one unique symbol"):
        calculate_market_signals(frame)


def test_calculate_market_signals_rejects_missing_symbol_values() -> None:
    frame = _price_frame(rows=60)
    frame.loc[0, "symbol"] = None

    with pytest.raises(ValueError, match="missing symbol values"):
        calculate_market_signals(frame)


def test_calculate_market_signals_rejects_missing_timestamp_values() -> None:
    frame = _price_frame(rows=60)
    frame.loc[0, "timestamp"] = None

    with pytest.raises(ValueError, match="missing timestamps"):
        calculate_market_signals(frame)


def test_calculate_market_signals_rejects_invalid_timestamp_strings() -> None:
    frame = _price_frame(rows=60)
    frame["timestamp"] = frame["timestamp"].astype(object)
    frame.loc[0, "timestamp"] = "not-a-timestamp"

    with pytest.raises(ValueError):
        calculate_market_signals(frame)


def test_calculate_market_signals_rejects_missing_close_values() -> None:
    frame = _price_frame(rows=60)
    frame.loc[0, "close"] = None

    with pytest.raises(ValueError, match="missing close values"):
        calculate_market_signals(frame)


def test_calculate_market_signals_rejects_non_finite_close_values() -> None:
    frame = _price_frame(rows=60)
    frame.loc[0, "close"] = float("inf")

    with pytest.raises(ValueError, match="non-finite close values"):
        calculate_market_signals(frame)


def test_calculate_realized_volatility_rejects_non_positive_close_values() -> None:
    frame = _price_frame(rows=60)
    frame.loc[10, "close"] = 0.0

    with pytest.raises(ValueError, match="must be positive"):
        calculate_realized_volatility(frame)


def test_market_signal_snapshot_contents_and_order_are_stable() -> None:
    frame = _price_frame(rows=60)

    snapshot = calculate_market_signals(frame)

    assert [signal.name for signal in snapshot.signals] == [
        "trend",
        "momentum",
        "realized_volatility",
        "current_drawdown",
        "distance_from_moving_average",
    ]
    assert all(signal.symbol == "MSFT" for signal in snapshot.signals)
    assert all(signal.timestamp == snapshot.timestamp for signal in snapshot.signals)
    assert snapshot.signals[0].parameters == {"short_window": 20, "long_window": 50}
    assert snapshot.signals[1].parameters == {"window": 20}
    assert snapshot.signals[2].parameters == {
        "window": 20,
        "annualization_factor": 252,
        "return_type": "log",
    }
    assert snapshot.signals[3].parameters == {
        "reference": "highest_close_to_latest_timestamp"
    }
    assert snapshot.signals[4].parameters == {"window": 20}
