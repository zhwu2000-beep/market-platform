"""Unified data provider interface."""

from abc import ABC, abstractmethod
from datetime import date, datetime

import pandas as pd


class DataProvider(ABC):
    """Base contract implemented by every market data provider.

    All methods return pandas DataFrames with canonical columns defined in
    ``market_platform.data.models``. Provider implementations must translate
    vendor-specific errors into ``market_platform.data.exceptions``.
    """

    name: str

    @abstractmethod
    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return daily OHLCV prices with UTC timestamps."""

    @abstractmethod
    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """Return intraday OHLCV prices with UTC timestamps."""

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        """Return the latest available OHLCV price row."""

    @abstractmethod
    async def health_check(self) -> pd.DataFrame:
        """Return provider health status using the canonical health schema."""
