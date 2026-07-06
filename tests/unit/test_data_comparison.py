from __future__ import annotations

import asyncio
from datetime import UTC, date

import pandas as pd
import pytest

from market_platform.data.comparison import (
    compare_daily_prices,
    compare_provider_daily_prices,
)
from market_platform.data.provider import DataProvider


def _daily_frame(
    *,
    symbol: str,
    provider: str,
    timestamps: list[str],
    closes: list[float],
    volumes: list[object],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * len(timestamps),
            "timestamp": [pd.Timestamp(ts, tz=UTC) for ts in timestamps],
            "open": [1.0] * len(timestamps),
            "high": [2.0] * len(timestamps),
            "low": [0.5] * len(timestamps),
            "close": closes,
            "volume": volumes,
            "provider": [provider] * len(timestamps),
        }
    )


class _FakeProvider(DataProvider):
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[tuple[str, object, object]] = []
        self.name = "fake"

    async def get_daily_prices(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        self.calls.append((symbol, start, end))
        return self.frame

    async def get_intraday_prices(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1min",
    ) -> pd.DataFrame:
        raise NotImplementedError

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        raise NotImplementedError

    async def health_check(self) -> pd.DataFrame:
        raise NotImplementedError


def test_compare_daily_prices_produces_matched_rows() -> None:
    left = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-01", "2026-01-02"],
        closes=[10.0, 12.0],
        volumes=[100, 200],
    )
    right = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-01", "2026-01-02"],
        closes=[9.0, 11.0],
        volumes=[80, 150],
    )

    frame = compare_daily_prices(left, right)

    assert list(frame["match_status"]) == ["matched", "matched"]
    assert list(frame["left_provider"]) == ["polygon", "polygon"]
    assert list(frame["right_provider"]) == ["twelvedata", "twelvedata"]
    assert list(frame["close_diff"]) == [1.0, 1.0]
    assert list(frame["close_diff_pct"]) == [1.0 / 9.0, 1.0 / 11.0]
    assert list(frame["volume_diff"]) == [20, 50]


def test_compare_daily_prices_includes_left_only_and_right_only_rows() -> None:
    left = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-01", "2026-01-02"],
        closes=[10.0, 12.0],
        volumes=[100, 200],
    )
    right = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-02", "2026-01-03"],
        closes=[11.0, 13.0],
        volumes=[150, 250],
    )

    frame = compare_daily_prices(left, right)

    assert list(frame["match_status"]) == ["left_only", "matched", "right_only"]
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
        pd.Timestamp("2026-01-03T00:00:00Z"),
    ]
    assert pd.isna(frame.at[0, "right_close"])
    assert pd.isna(frame.at[2, "left_close"])


def test_compare_daily_prices_sorts_by_timestamp() -> None:
    left = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-02", "2026-01-01"],
        closes=[12.0, 10.0],
        volumes=[200, 100],
    )
    right = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-02", "2026-01-01"],
        closes=[11.0, 9.0],
        volumes=[150, 80],
    )

    frame = compare_daily_prices(left, right)

    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    ]


def test_compare_daily_prices_handles_missing_volume() -> None:
    left = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-01"],
        closes=[10.0],
        volumes=[pd.NA],
    )
    right = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-01"],
        closes=[9.0],
        volumes=[100],
    )

    frame = compare_daily_prices(left, right)

    assert pd.isna(frame.at[0, "volume_diff"])


def test_compare_daily_prices_handles_blank_volume() -> None:
    left = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-01"],
        closes=[10.0],
        volumes=[""],
    )
    right = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-01"],
        closes=[9.0],
        volumes=[100],
    )

    frame = compare_daily_prices(left, right)

    assert pd.isna(frame.at[0, "volume_diff"])


def test_compare_daily_prices_rejects_mismatched_symbols() -> None:
    left = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-01"],
        closes=[10.0],
        volumes=[100],
    )
    right = _daily_frame(
        symbol="AAPL",
        provider="twelvedata",
        timestamps=["2026-01-01"],
        closes=[9.0],
        volumes=[100],
    )

    with pytest.raises(ValueError, match="symbols must match"):
        compare_daily_prices(left, right)


def test_compare_daily_prices_rejects_missing_required_columns() -> None:
    left = pd.DataFrame(
        {
            "symbol": ["MSFT"],
            "timestamp": [pd.Timestamp("2026-01-01", tz=UTC)],
            "close": [10.0],
            "volume": [100],
            "provider": ["polygon"],
        }
    )
    right = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-01"],
        closes=[9.0],
        volumes=[100],
    )

    with pytest.raises(ValueError, match="missing required columns"):
        compare_daily_prices(left, right)


def test_compare_daily_prices_returns_empty_frame_for_empty_inputs() -> None:
    left = pd.DataFrame(
        columns=[
            "symbol",
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "provider",
        ]
    )
    right = pd.DataFrame(
        columns=[
            "symbol",
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "provider",
        ]
    )

    frame = compare_daily_prices(left, right)

    assert frame.empty
    assert list(frame.columns) == [
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


def test_compare_provider_daily_prices_calls_both_providers() -> None:
    left_frame = _daily_frame(
        symbol="MSFT",
        provider="polygon",
        timestamps=["2026-01-01"],
        closes=[10.0],
        volumes=[100],
    )
    right_frame = _daily_frame(
        symbol="MSFT",
        provider="twelvedata",
        timestamps=["2026-01-01"],
        closes=[9.0],
        volumes=[80],
    )
    left_provider = _FakeProvider(left_frame)
    right_provider = _FakeProvider(right_frame)

    frame = asyncio.run(
        compare_provider_daily_prices(
            left_provider,
            right_provider,
            "MSFT",
            "2026-01-01",
            "2026-01-02",
        )
    )

    assert left_provider.calls == [
        ("MSFT", date(2026, 1, 1), date(2026, 1, 2))
    ]
    assert right_provider.calls == [
        ("MSFT", date(2026, 1, 1), date(2026, 1, 2))
    ]
    assert list(frame["match_status"]) == ["matched"]


def test_compare_provider_daily_prices_propagates_provider_errors() -> None:
    class _FailingProvider(_FakeProvider):
        async def get_daily_prices(
            self,
            symbol: str,
            start: date | str,
            end: date | str,
        ) -> pd.DataFrame:
            raise RuntimeError("boom")

    left_provider = _FailingProvider(pd.DataFrame())
    right_provider = _FakeProvider(
        _daily_frame(
            symbol="MSFT",
            provider="twelvedata",
            timestamps=["2026-01-01"],
            closes=[9.0],
            volumes=[80],
        )
    )

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(
            compare_provider_daily_prices(
                left_provider,
                right_provider,
                "MSFT",
                "2026-01-01",
                "2026-01-02",
            )
        )
