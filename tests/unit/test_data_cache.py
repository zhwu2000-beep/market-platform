from __future__ import annotations

from pathlib import Path

import pandas as pd

from market_platform.data.cache import MarketDataCache, MarketDataCacheKey


def _price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "MSFT",
                "timestamp": pd.Timestamp("2026-01-01T09:30:00Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
                "provider": "twelvedata",
            }
        ]
    )


def _latest_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "MSFT",
                "timestamp": pd.Timestamp("2026-01-01T09:30:00Z"),
                "price": 100.5,
                "provider": "twelvedata",
            }
        ]
    )


def test_cache_key_paths_are_normalized(tmp_path: Path) -> None:
    cache_key = MarketDataCacheKey.for_daily(
        symbol=" msft ",
        provider=" twelve_data ",
        start="2026-01-01",
        end="2026-01-02",
    )

    assert cache_key.path(tmp_path) == (
        tmp_path
        / "daily"
        / "twelvedata"
        / "MSFT"
        / "2026-01-01__2026-01-02.csv"
    )


def test_latest_and_intraday_cache_keys_include_auto_and_interval(
    tmp_path: Path,
) -> None:
    latest_key = MarketDataCacheKey.for_latest(symbol="msft", provider=None)
    intraday_key = MarketDataCacheKey.for_intraday(
        symbol="aapl",
        provider="twelve_data",
        interval="5min",
    )

    assert latest_key.path(tmp_path) == (
        tmp_path / "latest" / "auto" / "MSFT" / "latest.csv"
    )
    assert intraday_key.path(tmp_path) == (
        tmp_path
        / "intraday"
        / "twelvedata"
        / "AAPL"
        / "recent-1d__5min.csv"
    )


def test_cache_roundtrip_preserves_price_frame_timestamps(tmp_path: Path) -> None:
    cache = MarketDataCache(tmp_path)
    key = MarketDataCacheKey.for_daily(
        symbol="MSFT",
        provider="twelvedata",
        start="2026-01-01",
        end="2026-01-02",
    )

    cache.save(key, _price_frame())
    loaded = cache.load(key)

    assert list(loaded["timestamp"]) == [pd.Timestamp("2026-01-01T09:30:00Z")]
    assert str(loaded["timestamp"].dt.tz) == "UTC"
    assert list(loaded["provider"]) == ["twelvedata"]


def test_cache_roundtrip_preserves_latest_frame_timestamps(tmp_path: Path) -> None:
    cache = MarketDataCache(tmp_path)
    key = MarketDataCacheKey.for_latest(symbol="MSFT", provider=None)

    cache.save(key, _latest_frame())
    loaded = cache.load(key)

    assert list(loaded["timestamp"]) == [pd.Timestamp("2026-01-01T09:30:00Z")]
    assert str(loaded["timestamp"].dt.tz) == "UTC"
    assert list(loaded["price"]) == [100.5]
