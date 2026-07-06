"""Twelve Data provider skeleton."""

import os
from datetime import date, datetime

import pandas as pd

from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import HTTPClient, JsonValue
from market_platform.data.provider import DataProvider

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
TWELVE_DATA_PROVIDER_NAME = "twelvedata"


class TwelveDataProvider(DataProvider):
    """Skeleton Twelve Data provider with dependency injection hooks."""

    name = TWELVE_DATA_PROVIDER_NAME

    def __init__(
        self,
        *,
        http_client: HTTPClient | None = None,
        api_key: str | None = None,
        base_url: str = TWELVE_DATA_BASE_URL,
    ) -> None:
        """Create a Twelve Data provider skeleton.

        The API key is loaded from ``TWELVE_DATA_API_KEY`` when not provided
        explicitly. Construction never fails if the key is missing.
        """

        self._api_key = (
            api_key if api_key is not None else os.getenv("TWELVE_DATA_API_KEY")
        )
        self._http_client = http_client or HTTPClient()
        self._base_url = base_url.rstrip("/")

    @property
    def api_key(self) -> str:
        """Return the resolved Twelve Data API key."""

        return self._api_key or ""

    @property
    def http_client(self) -> HTTPClient:
        """Return the shared HTTP client instance."""

        return self._http_client

    @property
    def base_url(self) -> str:
        """Return the Twelve Data base URL."""

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
        """Return a lightweight health check result for Twelve Data."""

        api_key = self._require_api_key()
        payload = self._request(
            "/quote",
            params={
                "symbol": "AAPL",
                "apikey": api_key,
            },
        )
        return self._health_payload_to_frame(payload)

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise ConfigurationError("TWELVE_DATA_API_KEY is not configured")
        return self._api_key

    def _request(self, path: str, *, params: dict[str, str]) -> JsonValue:
        return self._http_client.get(f"{self._base_url}{path}", params=params)

    def _health_payload_to_frame(self, payload: JsonValue) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Twelve Data health response must be an object")

        status = payload.get("status", "ok")
        if isinstance(status, str) and status.lower() in {"error", "fail"}:
            message = payload.get("message") or "Twelve Data health check failed"
            raise DataProviderError(str(message))

        message_value = payload.get("message")
        if message_value is None:
            if payload.get("symbol") is not None:
                message_value = f"symbol={payload['symbol']}"
            elif payload.get("close") is not None:
                message_value = f"close={payload['close']}"
            else:
                message_value = "connected"

        frame = pd.DataFrame(
            [
                {
                    "provider": self.name,
                    "status": status,
                    "message": message_value,
                }
            ]
        )
        return frame.loc[:, ["provider", "status", "message"]]
