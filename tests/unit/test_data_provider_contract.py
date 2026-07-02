from datetime import UTC, date, datetime
from typing import ClassVar

import pandas as pd
import pytest

from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.models import (
    HEALTH_CHECK_COLUMNS,
    PRICE_COLUMNS,
    normalize_health_check_frame,
    normalize_price_frame,
)
from market_platform.data.provider import DataProvider
from market_platform.data.providers.twelve_data import TwelveDataProvider


class IncompleteProvider(DataProvider):
    name = "incomplete"


class FakeProvider(DataProvider):
    name = "fake"
    called_methods: ClassVar[list[str]] = []

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        self.called_methods.append("get_daily_prices")
        return normalize_price_frame(_price_frame(symbol=symbol, provider=self.name))

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        self.called_methods.append("get_intraday_prices")
        return normalize_price_frame(_price_frame(symbol=symbol, provider=self.name))

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        self.called_methods.append("get_latest_price")
        return normalize_price_frame(_price_frame(symbol=symbol, provider=self.name))

    async def health_check(self) -> pd.DataFrame:
        self.called_methods.append("health_check")
        return normalize_health_check_frame(
            pd.DataFrame(
                [
                    {
                        "provider": self.name,
                        "status": "ok",
                        "checked_at": datetime(2026, 1, 1, tzinfo=UTC),
                        "latency_ms": 1.2,
                        "message": "",
                    }
                ]
            )
        )


def _price_frame(symbol: str, provider: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "timestamp": "2026-01-01T09:30:00-05:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1000,
                "provider": provider,
            }
        ]
    )


def test_data_provider_requires_full_contract() -> None:
    with pytest.raises(TypeError):
        IncompleteProvider()


@pytest.mark.parametrize(
    "method_name",
    [
        "get_daily_prices",
        "get_intraday_prices",
        "get_latest_price",
        "health_check",
    ],
)
def test_data_provider_declares_required_methods(method_name: str) -> None:
    assert hasattr(DataProvider, method_name)


def test_price_frame_schema_and_utc_normalization() -> None:
    normalized = normalize_price_frame(_price_frame(symbol="MSFT", provider="fake"))

    assert list(normalized.columns) == PRICE_COLUMNS
    assert str(normalized["timestamp"].dt.tz) == "UTC"
    assert normalized.at[0, "timestamp"] == pd.Timestamp(
        "2026-01-01T14:30:00Z"
    )


def test_health_check_frame_schema_and_utc_normalization() -> None:
    normalized = normalize_health_check_frame(
        pd.DataFrame(
            [
                {
                    "provider": "fake",
                    "status": "ok",
                    "checked_at": "2026-01-01T22:00:00+08:00",
                    "latency_ms": 2.5,
                    "message": "",
                }
            ]
        )
    )

    assert list(normalized.columns) == HEALTH_CHECK_COLUMNS
    assert str(normalized["checked_at"].dt.tz) == "UTC"
    assert normalized.at[0, "checked_at"] == pd.Timestamp("2026-01-01T14:00:00Z")


def test_normalizers_reject_missing_required_columns() -> None:
    with pytest.raises(ValueError, match="Price frame is missing required columns"):
        normalize_price_frame(pd.DataFrame([{"symbol": "MSFT"}]))

    with pytest.raises(ValueError, match="Health check frame is missing required"):
        normalize_health_check_frame(pd.DataFrame([{"provider": "fake"}]))


def test_provider_exceptions_share_base_type() -> None:
    assert issubclass(AuthenticationError, DataProviderError)
    assert issubclass(RateLimitError, DataProviderError)
    assert issubclass(NetworkError, DataProviderError)


def test_provider_skeleton_raises_unified_exception() -> None:
    provider = TwelveDataProvider()

    with pytest.raises(DataProviderError, match="not implemented yet"):
        import asyncio

        asyncio.run(
            provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 2))
        )
