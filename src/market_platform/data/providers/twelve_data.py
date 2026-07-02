"""Twelve Data provider skeleton."""

from datetime import date, datetime
from typing import NoReturn

import pandas as pd

from market_platform.data.exceptions import DataProviderError
from market_platform.data.provider import DataProvider


class TwelveDataProvider(DataProvider):
    """Twelve Data implementation of the unified data provider interface."""

    name = "twelve_data"

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return normalized daily OHLCV prices."""

        self._not_implemented("get_daily_prices")

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """Return normalized intraday OHLCV prices."""

        self._not_implemented("get_intraday_prices")

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        """Return the latest normalized OHLCV price."""

        self._not_implemented("get_latest_price")

    async def health_check(self) -> pd.DataFrame:
        """Return Twelve Data health status."""

        self._not_implemented("health_check")

    def _not_implemented(self, method_name: str) -> NoReturn:
        raise DataProviderError(
            f"{self.name}.{method_name} is not implemented yet. "
            "Provider API calls are intentionally not wired in this layer."
        )
