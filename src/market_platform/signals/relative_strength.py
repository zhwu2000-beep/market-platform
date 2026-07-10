"""Relative strength signal helpers for aligned asset and benchmark prices."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from market_platform.signals.models import MarketSignal

_REQUIRED_COLUMNS = {"symbol", "timestamp", "close"}
_ALIGNED_COLUMNS = ["symbol", "timestamp", "close"]
_SIGNAL_NAME = "relative_strength"
_ALIGNMENT_NAME = "timestamp_intersection"
_RETURN_TYPE = "total_return_ratio"
_DEFAULT_WINDOW = 20


def align_asset_and_benchmark_prices(
    asset_prices: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return asset and benchmark price frames aligned on UTC timestamp intersection."""

    asset_frame = _prepare_single_symbol_price_frame(asset_prices, role="Asset")
    benchmark_frame = _prepare_single_symbol_price_frame(
        benchmark_prices,
        role="Benchmark",
    )

    asset_symbol = _normalize_symbol(asset_frame["symbol"].iloc[0])
    benchmark_symbol = _normalize_symbol(benchmark_frame["symbol"].iloc[0])
    if asset_symbol.casefold() == benchmark_symbol.casefold():
        raise ValueError("Asset and benchmark frames must use different symbols")

    common_timestamps = pd.Index(asset_frame["timestamp"]).intersection(
        pd.Index(benchmark_frame["timestamp"])
    )
    if common_timestamps.empty:
        raise ValueError("Asset and benchmark frames do not share any timestamps")

    asset_aligned = asset_frame.loc[
        asset_frame["timestamp"].isin(common_timestamps)
    ].copy()
    benchmark_aligned = benchmark_frame.loc[
        benchmark_frame["timestamp"].isin(common_timestamps)
    ].copy()

    asset_aligned = asset_aligned.sort_values(
        "timestamp", ascending=True, kind="stable"
    ).reset_index(drop=True)
    benchmark_aligned = benchmark_aligned.sort_values(
        "timestamp", ascending=True, kind="stable"
    ).reset_index(drop=True)

    if len(asset_aligned) != len(benchmark_aligned):
        raise ValueError("Aligned asset and benchmark frames must have equal lengths")

    if not asset_aligned["timestamp"].reset_index(drop=True).equals(
        benchmark_aligned["timestamp"].reset_index(drop=True)
    ):
        raise ValueError("Aligned asset and benchmark timestamps must match exactly")

    return (
        asset_aligned.loc[:, _ALIGNED_COLUMNS],
        benchmark_aligned.loc[:, _ALIGNED_COLUMNS],
    )


def calculate_relative_strength(
    asset_prices: pd.DataFrame,
    benchmark_prices: pd.DataFrame,
    window: int = _DEFAULT_WINDOW,
) -> MarketSignal:
    """Return a structured relative-strength signal for an asset versus benchmark."""

    _validate_window(window, "window")
    asset_aligned, benchmark_aligned = align_asset_and_benchmark_prices(
        asset_prices,
        benchmark_prices,
    )
    if len(asset_aligned) <= window:
        return _build_signal(
            symbol=_normalize_symbol(asset_aligned["symbol"].iloc[0]),
            benchmark_symbol=_normalize_symbol(benchmark_aligned["symbol"].iloc[0]),
            timestamp=asset_aligned["timestamp"].iloc[-1].to_pydatetime(),
            window=window,
            value=None,
        )

    asset_window = asset_aligned.iloc[-(window + 1) :].reset_index(drop=True)
    benchmark_window = benchmark_aligned.iloc[-(window + 1) :].reset_index(drop=True)

    latest_asset_close = float(asset_window["close"].iloc[-1])
    starting_asset_close = float(asset_window["close"].iloc[0])
    latest_benchmark_close = float(benchmark_window["close"].iloc[-1])
    starting_benchmark_close = float(benchmark_window["close"].iloc[0])

    asset_total_return = _ratio_minus_one(
        latest_asset_close,
        starting_asset_close,
    )
    benchmark_total_return = _ratio_minus_one(
        latest_benchmark_close,
        starting_benchmark_close,
    )

    benchmark_growth = 1.0 + benchmark_total_return
    if benchmark_growth == 0:
        raise ValueError("Denominator must be non-zero")

    relative_strength = (1.0 + asset_total_return) / benchmark_growth - 1.0
    return _build_signal(
        symbol=_normalize_symbol(asset_aligned["symbol"].iloc[0]),
        benchmark_symbol=_normalize_symbol(benchmark_aligned["symbol"].iloc[0]),
        timestamp=asset_aligned["timestamp"].iloc[-1].to_pydatetime(),
        window=window,
        value=relative_strength,
    )


def _prepare_single_symbol_price_frame(
    prices: pd.DataFrame,
    *,
    role: str,
) -> pd.DataFrame:
    if prices.empty:
        raise ValueError(f"{role} price frame must not be empty")

    missing_columns = _REQUIRED_COLUMNS - set(prices.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"{role} price frame is missing required columns: {missing}")

    frame = prices.loc[:, _ALIGNED_COLUMNS].copy()
    if frame["symbol"].isna().any():
        raise ValueError(f"{role} price frame must not contain missing symbol values")

    symbol_values = frame["symbol"].astype("string").str.strip()
    if symbol_values.eq("").any():
        raise ValueError(f"{role} price frame must not contain empty symbol values")
    unique_symbols = symbol_values.unique()
    if len(unique_symbols) != 1:
        raise ValueError(f"{role} price frame must contain exactly one unique symbol")

    timestamp_values = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
        format="mixed",
    )
    if timestamp_values.isna().any():
        raise ValueError(
            f"{role} price frame must not contain missing timestamps"
        )
    if timestamp_values.duplicated().any():
        raise ValueError(
            f"{role} price frame must not contain duplicate timestamps"
        )

    close_values = pd.to_numeric(frame["close"], errors="raise")
    if close_values.isna().any():
        raise ValueError(f"{role} price frame must not contain missing close values")
    if not np.isfinite(close_values.to_numpy()).all():
        raise ValueError(
            f"{role} price frame must not contain non-finite close values"
        )

    symbol = str(unique_symbols[0]).strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty")

    frame["symbol"] = symbol
    frame["timestamp"] = timestamp_values
    frame["close"] = close_values
    frame = frame.sort_values("timestamp", ascending=True, kind="stable")
    return frame.reset_index(drop=True)


def _build_signal(
    *,
    symbol: str,
    benchmark_symbol: str,
    timestamp: datetime,
    window: int,
    value: float | None,
) -> MarketSignal:
    return MarketSignal(
        symbol=symbol,
        name=_SIGNAL_NAME,
        value=value,
        timestamp=timestamp,
        parameters={
            "window": window,
            "benchmark_symbol": benchmark_symbol,
            "alignment": _ALIGNMENT_NAME,
            "return_type": _RETURN_TYPE,
        },
    )


def _normalize_symbol(value: str) -> str:
    symbol = value.strip()
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    return symbol


def _validate_window(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _ratio_minus_one(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise ValueError("Denominator must be non-zero")
    return numerator / denominator - 1.0
