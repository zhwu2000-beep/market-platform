"""Comparison helpers for normalized provider outputs."""

from __future__ import annotations

from typing import Any, cast

import pandas as pd

from market_platform.data.models import PRICE_COLUMNS

COMPARISON_COLUMNS = [
    "symbol",
    "timestamp",
    "left_provider",
    "right_provider",
    "left_close",
    "right_close",
    "close_diff",
    "close_diff_pct",
    "left_volume",
    "right_volume",
    "volume_diff",
    "match_status",
]


def compare_daily_prices(
    left: pd.DataFrame,
    right: pd.DataFrame,
) -> pd.DataFrame:
    """Compare two normalized daily OHLCV DataFrames."""

    left_frame = _prepare_daily_prices(left)
    right_frame = _prepare_daily_prices(right)

    left_symbol = _frame_symbol(left_frame)
    right_symbol = _frame_symbol(right_frame)
    if (
        left_symbol is not None
        and right_symbol is not None
        and left_symbol != right_symbol
    ):
        raise ValueError("Daily price symbols must match")

    if left_frame.empty and right_frame.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)

    merged = left_frame.merge(
        right_frame,
        on="timestamp",
        how="outer",
        suffixes=("_left", "_right"),
        indicator=True,
    )
    merged = merged.sort_values("timestamp", ascending=True, kind="stable")

    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        match_status = {
            "both": "matched",
            "left_only": "left_only",
            "right_only": "right_only",
        }[row["_merge"]]
        left_close = row.get("close_left")
        right_close = row.get("close_right")
        left_volume = row.get("volume_left")
        right_volume = row.get("volume_right")
        close_diff = _difference(left_close, right_close)
        close_diff_pct = _percentage_difference(close_diff, right_close)
        volume_diff = _difference(left_volume, right_volume, allow_missing=True)

        rows.append(
            {
                "symbol": _row_symbol(row),
                "timestamp": row["timestamp"],
                "left_provider": row.get("provider_left", pd.NA),
                "right_provider": row.get("provider_right", pd.NA),
                "left_close": left_close,
                "right_close": right_close,
                "close_diff": close_diff,
                "close_diff_pct": close_diff_pct,
                "left_volume": left_volume,
                "right_volume": right_volume,
                "volume_diff": volume_diff,
                "match_status": match_status,
            }
        )

    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def _prepare_daily_prices(frame: pd.DataFrame) -> pd.DataFrame:
    missing_columns = set(PRICE_COLUMNS) - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Daily price frame is missing required columns: {missing}")

    prepared = frame.loc[:, PRICE_COLUMNS].copy()
    prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], utc=True)
    return prepared


def _frame_symbol(frame: pd.DataFrame) -> str | None:
    symbols = frame["symbol"].dropna().astype(str).unique()
    if len(symbols) == 0:
        return None
    if len(symbols) > 1:
        raise ValueError("Daily price frame contains multiple symbols")
    return cast(str, symbols[0])


def _row_symbol(row: pd.Series) -> str:
    left_symbol = row.get("symbol_left")
    if pd.notna(left_symbol):
        return str(left_symbol.item() if hasattr(left_symbol, "item") else left_symbol)
    right_symbol = row.get("symbol_right")
    if pd.notna(right_symbol):
        return str(
            right_symbol.item() if hasattr(right_symbol, "item") else right_symbol
        )
    return ""


def _difference(
    left_value: Any,
    right_value: Any,
    *,
    allow_missing: bool = False,
) -> Any:
    left_numeric = pd.to_numeric(left_value, errors="coerce")
    right_numeric = pd.to_numeric(right_value, errors="coerce")
    if pd.isna(left_numeric) or pd.isna(right_numeric):
        return pd.NA if allow_missing else pd.NA
    return left_numeric - right_numeric


def _percentage_difference(close_diff: Any, right_close: Any) -> Any:
    right_numeric = pd.to_numeric(right_close, errors="coerce")
    if pd.isna(close_diff) or pd.isna(right_numeric) or right_numeric == 0:
        return pd.NA
    return close_diff / right_numeric
