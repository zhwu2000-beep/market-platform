"""Pure market signal calculators for single-symbol daily price frames."""

from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd

_REQUIRED_COLUMNS = {"symbol", "timestamp", "close"}
_ANNUALIZATION_FACTOR = 252


def calculate_trend(
    prices: pd.DataFrame,
    short_window: int = 20,
    long_window: int = 50,
) -> float | None:
    """Return the short/long moving-average trend ratio minus one."""

    _validate_window(short_window, "short_window")
    _validate_window(long_window, "long_window")
    if short_window >= long_window:
        raise ValueError("short_window must be strictly less than long_window")
    frame = _prepare_price_frame(prices)
    if len(frame) < long_window:
        return None

    close = frame["close"]
    short_ma = close.rolling(short_window).mean().iloc[-1]
    long_ma = close.rolling(long_window).mean().iloc[-1]
    return _ratio_minus_one(short_ma, long_ma)


def calculate_momentum(
    prices: pd.DataFrame,
    window: int = 20,
) -> float | None:
    """Return the latest close divided by the close ``window`` periods earlier."""

    _validate_window(window, "window")
    frame = _prepare_price_frame(prices)
    if len(frame) <= window:
        return None

    close = frame["close"]
    latest_close = float(close.iloc[-1])
    prior_close = float(close.iloc[-(window + 1)])
    return _ratio_minus_one(latest_close, prior_close)


def calculate_realized_volatility(
    prices: pd.DataFrame,
    window: int = 20,
) -> float | None:
    """Return annualized realized volatility from log returns."""

    _validate_window(window, "window")
    frame = _prepare_price_frame(prices)
    if len(frame) <= window:
        return None

    close = frame["close"]
    if (close <= 0).any():
        raise ValueError("Close prices must be positive for realized volatility")

    log_returns = pd.Series(
        np.log(close.to_numpy() / close.shift(1).to_numpy()),
        index=close.index,
    ).iloc[-window:]
    realized_volatility = float(log_returns.std(ddof=1))
    if not np.isfinite(realized_volatility):
        return None
    return realized_volatility * sqrt(_ANNUALIZATION_FACTOR)


def calculate_current_drawdown(prices: pd.DataFrame) -> float:
    """Return the latest close divided by the highest historical close minus one."""

    frame = _prepare_price_frame(prices)
    close = frame["close"]
    latest_close = float(close.iloc[-1])
    highest_close = float(close.max())
    return _ratio_minus_one(latest_close, highest_close)


def calculate_distance_from_moving_average(
    prices: pd.DataFrame,
    window: int = 20,
) -> float | None:
    """Return the latest close divided by the moving average minus one."""

    _validate_window(window, "window")
    frame = _prepare_price_frame(prices)
    if len(frame) < window:
        return None

    close = frame["close"]
    moving_average = close.rolling(window).mean().iloc[-1]
    latest_close = float(close.iloc[-1])
    return _ratio_minus_one(latest_close, moving_average)


def _prepare_price_frame(prices: pd.DataFrame) -> pd.DataFrame:
    missing_columns = _REQUIRED_COLUMNS - set(prices.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Price frame is missing required columns: {missing}")

    frame = prices.loc[:, ["symbol", "timestamp", "close"]].copy()
    if frame["symbol"].isna().any():
        raise ValueError("Price frame must not contain missing symbol values")

    symbol_values = frame["symbol"].astype("string").str.strip()
    if symbol_values.eq("").any():
        raise ValueError("Price frame must not contain empty symbol values")
    unique_symbols = symbol_values.unique()
    if len(unique_symbols) != 1:
        raise ValueError("Price frame must contain exactly one unique symbol")

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

    symbol = str(unique_symbols[0]).strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    frame["symbol"] = symbol
    frame["timestamp"] = timestamp_values
    frame["close"] = close_values
    frame = frame.sort_values("timestamp", ascending=True, kind="stable")
    return frame.reset_index(drop=True)


def _validate_window(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _ratio_minus_one(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise ValueError("Denominator must be non-zero")
    return numerator / denominator - 1.0
