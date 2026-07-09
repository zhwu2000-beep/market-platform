"""Twelve Data provider skeleton."""

import os
from datetime import UTC, date, datetime
from typing import cast

import pandas as pd

from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import HTTPClient, JsonValue
from market_platform.data.models import (
    LATEST_PRICE_COLUMNS,
    PRICE_COLUMNS,
    normalize_latest_price_frame,
    normalize_price_frame,
)
from market_platform.data.provider import DataProvider, normalize_date_like

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
TWELVE_DATA_PROVIDER_NAME = "twelvedata"
_INTRADAY_INTERVALS: dict[str, str] = {
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1h": "1h",
}


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
        start: date | str,
        end: date | str,
    ) -> pd.DataFrame:
        """Return Twelve Data daily prices as a standardized DataFrame."""

        api_key = self._require_api_key()
        payload = self._request(
            "/time_series",
            params={
                "symbol": symbol.upper(),
                "interval": "1day",
                "start_date": normalize_date_like(start),
                "end_date": normalize_date_like(end),
                "apikey": api_key,
            },
        )
        return self._daily_payload_to_frame(symbol=symbol, payload=payload)

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """Return Twelve Data intraday prices as a standardized DataFrame."""

        api_key = self._require_api_key()
        api_interval = self._normalize_intraday_interval(interval)
        payload = self._request(
            "/time_series",
            params={
                "symbol": symbol.upper(),
                "interval": api_interval,
                "start_date": self._datetime_to_query_value(start),
                "end_date": self._datetime_to_query_value(end),
                "apikey": api_key,
            },
        )
        return self._historical_payload_to_frame(
            symbol=symbol,
            payload=payload,
            missing_field_message=(
                "Twelve Data intraday value missing field: {field}"
            ),
        )

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        """Return Twelve Data latest price as a standardized DataFrame."""

        api_key = self._require_api_key()
        payload = self._request(
            "/price",
            params={
                "symbol": symbol.upper(),
                "apikey": api_key,
            },
        )
        return self._latest_payload_to_frame(symbol=symbol, payload=payload)

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

    def _daily_payload_to_frame(self, symbol: str, payload: JsonValue) -> pd.DataFrame:
        return self._historical_payload_to_frame(
            symbol=symbol,
            payload=payload,
            missing_field_message="Twelve Data daily value missing field: {field}",
        )

    def _latest_payload_to_frame(self, symbol: str, payload: JsonValue) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Twelve Data latest response must be an object")

        status = payload.get("status", "ok")
        if isinstance(status, str) and status.lower() in {"error", "fail"}:
            message = payload.get("message") or payload.get("code") or "request failed"
            raise DataProviderError(str(message))

        timestamp_value: object | None = (
            payload.get("datetime") or payload.get("timestamp")
        )
        if timestamp_value is None:
            date_value = payload.get("date")
            time_value = payload.get("time")
            if date_value is not None and time_value is not None:
                timestamp_value = f"{date_value}T{time_value}"
            else:
                timestamp_value = date_value
        if timestamp_value is None:
            timestamp_value = datetime.now(UTC)

        price_value = payload.get("price")
        if price_value in {"", None}:
            price_value = payload.get("close")
        if price_value in {"", None}:
            price_value = payload.get("value")
        if price_value in {"", None}:
            price_value = payload.get("last")
        if price_value in {"", None}:
            raise DataProviderError(
                "Twelve Data latest price response missing field: price"
            )

        latest_frame = pd.DataFrame(
            [
                {
                    "symbol": symbol.upper(),
                    "timestamp": pd.to_datetime(
                        cast(str | datetime | date | int | float, timestamp_value),
                        utc=True,
                    ),
                    "price": price_value,
                    "provider": self.name,
                }
            ],
            columns=LATEST_PRICE_COLUMNS,
        )
        latest_frame = normalize_latest_price_frame(latest_frame)
        return latest_frame.reset_index(drop=True)

    def _historical_payload_to_frame(
        self,
        *,
        symbol: str,
        payload: JsonValue,
        missing_field_message: str,
    ) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Twelve Data response must be an object")

        status = payload.get("status", "ok")
        if isinstance(status, str) and status.lower() in {"error", "fail"}:
            message = payload.get("message") or payload.get("code") or "request failed"
            raise DataProviderError(str(message))

        values = payload.get("values", [])
        if values is None:
            values = []
        if not isinstance(values, list):
            raise DataProviderError("Twelve Data values must be a list")
        if not values:
            empty_frame = pd.DataFrame(columns=PRICE_COLUMNS)
            empty_frame = normalize_price_frame(empty_frame)
            return empty_frame.sort_values("timestamp", ascending=True, kind="stable")

        rows: list[dict[str, object]] = []
        for item in values:
            if not isinstance(item, dict):
                raise DataProviderError("Twelve Data value must be an object")
            if "datetime" not in item:
                raise DataProviderError(missing_field_message.format(field="datetime"))

            volume_value: object | None = item.get("volume")
            if volume_value in {"", None}:
                volume_value = pd.NA

            try:
                timestamp_value = item["datetime"]
                if not isinstance(timestamp_value, (str, datetime, date, int, float)):
                    raise DataProviderError(
                        "Twelve Data daily value datetime must be a scalar value"
                    )
                rows.append(
                    {
                        "symbol": symbol.upper(),
                        "timestamp": pd.to_datetime(
                            cast(str | datetime | date | int | float, timestamp_value),
                            utc=True,
                        ),
                        "open": item["open"],
                        "high": item["high"],
                        "low": item["low"],
                        "close": item["close"],
                        "volume": volume_value,
                        "provider": self.name,
                    }
                )
            except KeyError as exc:
                raise DataProviderError(
                    missing_field_message.format(field=exc.args[0])
                ) from exc

        frame = pd.DataFrame(rows, columns=PRICE_COLUMNS)
        frame = normalize_price_frame(frame)
        frame = frame.sort_values("timestamp", ascending=True, kind="stable")
        return frame.reset_index(drop=True)

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

    def _normalize_intraday_interval(self, interval: str) -> str:
        normalized_interval = interval.strip().lower()
        try:
            return _INTRADAY_INTERVALS[normalized_interval]
        except KeyError as exc:
            raise ValueError(
                "Unsupported interval. Use one of: 1min, 5min, 15min, 30min, 1h"
            ) from exc

    def _datetime_to_query_value(self, value: datetime) -> str:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        return timestamp.isoformat()
