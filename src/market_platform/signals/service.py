"""Signal aggregation helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from market_platform.signals.calculators import (
    calculate_current_drawdown,
    calculate_distance_from_moving_average,
    calculate_momentum,
    calculate_realized_volatility,
    calculate_trend,
)
from market_platform.signals.models import MarketSignal, MarketSignalSnapshot

DEFAULT_TREND_SHORT_WINDOW = 20
DEFAULT_TREND_LONG_WINDOW = 50
DEFAULT_MOMENTUM_WINDOW = 20
DEFAULT_REALIZED_VOLATILITY_WINDOW = 20
DEFAULT_DISTANCE_FROM_MA_WINDOW = 20
DEFAULT_ANNUALIZATION_FACTOR = 252


def calculate_market_signals(prices: pd.DataFrame) -> MarketSignalSnapshot:
    """Return the default structured market signals for a single symbol."""

    prepared = _prepare_snapshot_frame(prices)
    return _build_snapshot_from_prepared_frame(prepared, position=len(prepared) - 1)


def precompute_market_signal_snapshots(
    prices: pd.DataFrame,
) -> tuple[MarketSignalSnapshot, ...]:
    """Precompute point-in-time market signal snapshots for every frame row."""

    prepared = _prepare_snapshot_frame(prices)
    symbol = str(prepared["symbol"].iloc[0])
    close = prepared["close"]
    timestamps = prepared["timestamp"]

    short_ma = close.rolling(DEFAULT_TREND_SHORT_WINDOW).mean()
    long_ma = close.rolling(DEFAULT_TREND_LONG_WINDOW).mean()
    trend = short_ma / long_ma - 1.0
    momentum = close / close.shift(DEFAULT_MOMENTUM_WINDOW) - 1.0
    if len(prepared) <= DEFAULT_REALIZED_VOLATILITY_WINDOW:
        realized_volatility = pd.Series(np.nan, index=close.index)
    else:
        if (close <= 0).any():
            raise ValueError("Close prices must be positive for realized volatility")
        log_returns = pd.Series(
            np.log(close.to_numpy() / close.shift(1).to_numpy()),
            index=close.index,
        )
        realized_volatility = (
            log_returns.rolling(DEFAULT_REALIZED_VOLATILITY_WINDOW).apply(
                lambda values: float(values.std(ddof=1)),
                raw=False,
            )
            * np.sqrt(DEFAULT_ANNUALIZATION_FACTOR)
        )
    current_drawdown = close / close.expanding().max() - 1.0
    distance_from_moving_average = (
        close / close.rolling(DEFAULT_DISTANCE_FROM_MA_WINDOW).mean() - 1.0
    )

    snapshots: list[MarketSignalSnapshot] = []
    for position in range(len(prepared)):
        timestamp = timestamps.iloc[position].to_pydatetime()
        signals = (
            _build_signal(
                symbol=symbol,
                name="trend",
                value=_optional_float(trend.iloc[position]),
                timestamp=timestamp,
                parameters={
                    "short_window": DEFAULT_TREND_SHORT_WINDOW,
                    "long_window": DEFAULT_TREND_LONG_WINDOW,
                },
            ),
            _build_signal(
                symbol=symbol,
                name="momentum",
                value=_optional_float(momentum.iloc[position]),
                timestamp=timestamp,
                parameters={"window": DEFAULT_MOMENTUM_WINDOW},
            ),
            _build_signal(
                symbol=symbol,
                name="realized_volatility",
                value=_optional_float(realized_volatility.iloc[position]),
                timestamp=timestamp,
                parameters={
                    "window": DEFAULT_REALIZED_VOLATILITY_WINDOW,
                    "annualization_factor": DEFAULT_ANNUALIZATION_FACTOR,
                    "return_type": "log",
                },
            ),
            _build_signal(
                symbol=symbol,
                name="current_drawdown",
                value=float(current_drawdown.iloc[position]),
                timestamp=timestamp,
                parameters={"reference": "highest_close_to_latest_timestamp"},
            ),
            _build_signal(
                symbol=symbol,
                name="distance_from_moving_average",
                value=_optional_float(distance_from_moving_average.iloc[position]),
                timestamp=timestamp,
                parameters={"window": DEFAULT_DISTANCE_FROM_MA_WINDOW},
            ),
        )
        snapshots.append(
            MarketSignalSnapshot(symbol=symbol, timestamp=timestamp, signals=signals)
        )
    return tuple(snapshots)


def _build_snapshot_from_prepared_frame(
    prepared: pd.DataFrame,
    *,
    position: int,
) -> MarketSignalSnapshot:
    symbol = str(prepared["symbol"].iloc[0])
    timestamp = prepared["timestamp"].iloc[position].to_pydatetime()
    prefix = prepared.iloc[: position + 1]

    signals = (
        _build_signal(
            symbol=symbol,
            name="trend",
            value=calculate_trend(
                prefix,
                short_window=DEFAULT_TREND_SHORT_WINDOW,
                long_window=DEFAULT_TREND_LONG_WINDOW,
            ),
            timestamp=timestamp,
            parameters={
                "short_window": DEFAULT_TREND_SHORT_WINDOW,
                "long_window": DEFAULT_TREND_LONG_WINDOW,
            },
        ),
        _build_signal(
            symbol=symbol,
            name="momentum",
            value=calculate_momentum(
                prefix,
                window=DEFAULT_MOMENTUM_WINDOW,
            ),
            timestamp=timestamp,
            parameters={"window": DEFAULT_MOMENTUM_WINDOW},
        ),
        _build_signal(
            symbol=symbol,
            name="realized_volatility",
            value=calculate_realized_volatility(
                prefix,
                window=DEFAULT_REALIZED_VOLATILITY_WINDOW,
            ),
            timestamp=timestamp,
            parameters={
                "window": DEFAULT_REALIZED_VOLATILITY_WINDOW,
                "annualization_factor": DEFAULT_ANNUALIZATION_FACTOR,
                "return_type": "log",
            },
        ),
        _build_signal(
            symbol=symbol,
            name="current_drawdown",
            value=calculate_current_drawdown(prefix),
            timestamp=timestamp,
            parameters={"reference": "highest_close_to_latest_timestamp"},
        ),
        _build_signal(
            symbol=symbol,
            name="distance_from_moving_average",
            value=calculate_distance_from_moving_average(
                prefix,
                window=DEFAULT_DISTANCE_FROM_MA_WINDOW,
            ),
            timestamp=timestamp,
            parameters={"window": DEFAULT_DISTANCE_FROM_MA_WINDOW},
        ),
    )
    return MarketSignalSnapshot(symbol=symbol, timestamp=timestamp, signals=signals)


def _prepare_snapshot_frame(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    if frame.empty:
        raise ValueError("Price frame must not be empty")
    required_columns = {"symbol", "timestamp", "close"}
    if not required_columns.issubset(frame.columns):
        missing = sorted(required_columns - set(frame.columns))
        raise ValueError(
            "Price frame is missing required columns: " + ", ".join(missing)
        )

    if frame["symbol"].isna().any():
        raise ValueError("Price frame must not contain missing symbol values")

    symbol_values = frame["symbol"].astype("string").str.strip()
    if symbol_values.eq("").any():
        raise ValueError("Price frame must not contain empty symbol values")
    unique_symbols = symbol_values.unique()
    if len(unique_symbols) != 1:
        raise ValueError("Price frame must contain exactly one unique symbol")

    symbol = str(unique_symbols[0]).strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    frame["symbol"] = symbol

    timestamp_values = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
        format="mixed",
    )
    if timestamp_values.isna().any():
        raise ValueError("Price frame must not contain missing timestamps")

    close_values = pd.to_numeric(frame["close"], errors="raise")
    if close_values.isna().any():
        raise ValueError("Price frame must not contain missing close values")
    if not np.isfinite(close_values.to_numpy()).all():
        raise ValueError("Price frame must not contain non-finite close values")

    frame["timestamp"] = timestamp_values
    frame["close"] = close_values
    frame = frame.sort_values("timestamp", ascending=True, kind="stable")
    return frame.reset_index(drop=True)


def _build_signal(
    *,
    symbol: str,
    name: str,
    value: float | None,
    timestamp: datetime,
    parameters: dict[str, object],
) -> MarketSignal:
    return MarketSignal(
        symbol=symbol,
        name=name,
        value=value,
        timestamp=timestamp,
        parameters=parameters,
    )


def _optional_float(value: Any) -> float | None:
    numeric = float(value)
    if not np.isfinite(numeric):
        return None
    return numeric
