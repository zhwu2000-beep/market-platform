"""Polygon provider skeleton."""

import os
from datetime import date, datetime
from typing import cast

import pandas as pd

from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import HTTPClient, JsonValue
from market_platform.data.models import PRICE_COLUMNS, normalize_price_frame
from market_platform.data.provider import DataProvider, normalize_date_like

POLYGON_BASE_URL = "https://api.polygon.io"
POLYGON_PROVIDER_NAME = "polygon"


class PolygonProvider(DataProvider):
    """Skeleton Polygon provider with dependency injection hooks."""

    name = POLYGON_PROVIDER_NAME

    def __init__(
        self,
        *,
        http_client: HTTPClient | None = None,
        api_key: str | None = None,
        base_url: str = POLYGON_BASE_URL,
    ) -> None:
        """Create a Polygon provider skeleton.

        The API key is loaded from ``POLYGON_API_KEY`` when not provided
        explicitly. Construction never fails if the key is missing.
        """

        self._api_key = api_key if api_key is not None else os.getenv("POLYGON_API_KEY")
        self._http_client = http_client or HTTPClient()
        self._base_url = base_url.rstrip("/")

    @property
    def api_key(self) -> str:
        """Return the resolved Polygon API key."""

        return self._api_key or ""

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
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        """Return Polygon daily aggregates as a standardized DataFrame."""

        api_key = self._require_api_key()
        start_str = normalize_date_like(start)
        end_str = normalize_date_like(end)
        payload = self._request(
            f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start_str}/{end_str}",
            params={"apiKey": api_key},
        )
        return self._daily_payload_to_frame(symbol=symbol, payload=payload)

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
        """Return a lightweight health check result for Polygon."""

        api_key = self._require_api_key()
        payload = self._request(
            "/v1/marketstatus/now",
            params={"apiKey": api_key},
        )
        return self._health_payload_to_frame(payload)

    def _require_api_key(self) -> str:
        if not self._api_key:
            raise ConfigurationError("POLYGON_API_KEY is not configured")
        return self._api_key

    def _request(self, path: str, *, params: dict[str, str]) -> JsonValue:
        return self._http_client.get(f"{self._base_url}{path}", params=params)

    def _daily_payload_to_frame(self, symbol: str, payload: JsonValue) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Polygon daily prices response must be an object")

        results = payload.get("results", [])
        if results is None:
            results = []
        if not isinstance(results, list):
            raise DataProviderError("Polygon daily prices results must be a list")

        rows: list[dict[str, object]] = []
        for item in results:
            if not isinstance(item, dict):
                raise DataProviderError("Polygon daily price result must be an object")
            row = item
            try:
                timestamp_value = cast(float | str | datetime | date, row["t"])
                rows.append(
                    {
                        "symbol": symbol.upper(),
                        "timestamp": pd.to_datetime(
                            timestamp_value, unit="ms", utc=True
                        ),
                        "open": row["o"],
                        "high": row["h"],
                        "low": row["l"],
                        "close": row["c"],
                        "volume": row["v"],
                        "provider": self.name,
                    }
                )
            except KeyError as exc:
                raise DataProviderError(
                    f"Polygon daily price result missing field: {exc.args[0]}"
                ) from exc

        frame = pd.DataFrame(rows, columns=PRICE_COLUMNS)
        frame = normalize_price_frame(frame)
        frame = frame.sort_values("timestamp", ascending=True, kind="stable")
        return frame.reset_index(drop=True)

    def _health_payload_to_frame(self, payload: JsonValue) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Polygon health response must be an object")

        status = payload.get("status", "ok")
        message = payload.get("message")
        if message is None:
            message = payload.get("market", "connected")

        frame = pd.DataFrame(
            [
                {
                    "provider": self.name,
                    "status": status,
                    "message": message,
                }
            ]
        )
        return frame.loc[:, ["provider", "status", "message"]]
