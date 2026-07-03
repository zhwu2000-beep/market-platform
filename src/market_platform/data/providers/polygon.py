"""Polygon provider skeleton."""

from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd

from market_platform.data.http import HTTPClient
from market_platform.data.provider import DataProvider

POLYGON_BASE_URL = "https://api.polygon.io"


class PolygonProvider(DataProvider):
    """Skeleton Polygon provider with dependency injection hooks."""

    name = "polygon"

    def __init__(
        self,
        *,
        http_client: HTTPClient | None = None,
        api_key: str | None = None,
        base_url: str = POLYGON_BASE_URL,
    ) -> None:
        """Create a Polygon provider skeleton.

        The API key is loaded from ``POLYGON_API_KEY`` when not provided
        explicitly. This class does not perform any network requests yet.
        """

        resolved_api_key: str | None = (
            api_key if api_key is not None else os.getenv("POLYGON_API_KEY")
        )
        if not resolved_api_key:
            raise ValueError("POLYGON_API_KEY is not configured")

        self._api_key = resolved_api_key
        self._http_client = http_client or HTTPClient()
        self._base_url = base_url.rstrip("/")

    @property
    def api_key(self) -> str:
        """Return the resolved Polygon API key."""

        return self._api_key

    @property
    def http_client(self) -> HTTPClient:
        """Return the shared HTTP client instance."""

        return self._http_client

    @property
    def base_url(self) -> str:
        """Return the Polygon base URL."""

        return self._base_url

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Placeholder for future daily price support."""

        raise NotImplementedError

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """Placeholder for future intraday price support."""

        raise NotImplementedError

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        """Placeholder for future latest price support."""

        raise NotImplementedError

    async def health_check(self) -> pd.DataFrame:
        """Placeholder for future health check support."""

        raise NotImplementedError
