"""Polygon data provider."""

from datetime import date, datetime
from typing import Any, NoReturn, cast

import pandas as pd

from market_platform.config import Settings, get_settings
from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    RateLimitError,
)
from market_platform.data.http import HTTPClient, HttpClientConfig, JsonValue
from market_platform.data.models import (
    PRICE_COLUMNS,
    normalize_health_check_frame,
    normalize_price_frame,
)
from market_platform.data.provider import DataProvider

POLYGON_BASE_URL = "https://api.polygon.io"


class PolygonProvider(DataProvider):
    """Polygon implementation of the unified data provider interface."""

    name = "polygon"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: HTTPClient | None = None,
        base_url: str = POLYGON_BASE_URL,
    ) -> None:
        self._settings = settings or get_settings()
        self._http_client = http_client or HTTPClient(
            HttpClientConfig(
                timeout_seconds=float(self._settings.request_timeout_seconds)
            )
        )
        self._base_url = base_url.rstrip("/")

    async def get_daily_prices(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Return normalized daily OHLCV prices."""

        self._ensure_api_key()
        try:
            url = (
                f"{self._base_url}/v2/aggs/ticker/{symbol.upper()}"
                f"/range/1/day/{start.isoformat()}/{end.isoformat()}"
            )
            payload = self._get_json(
                url,
                params={
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 50000,
                    "apiKey": self._settings.polygon_api_key,
                },
            )
            return self._daily_prices_to_frame(symbol=symbol, payload=payload)
        except DataProviderError:
            raise
        except Exception as exc:
            raise DataProviderError("Polygon daily price normalization failed") from exc

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
        """Return Polygon health status."""

        self._ensure_api_key()
        try:
            payload = self._get_json(
                f"{self._base_url}/v1/marketstatus/now",
                params={"apiKey": self._settings.polygon_api_key},
            )
            return self._health_to_frame(payload)
        except DataProviderError:
            raise
        except Exception as exc:
            raise DataProviderError(
                "Polygon health check normalization failed"
            ) from exc

    def _not_implemented(self, method_name: str) -> NoReturn:
        raise DataProviderError(
            f"{self.name}.{method_name} is not implemented yet. "
            "This provider method is intentionally out of scope for now."
        )

    def _ensure_api_key(self) -> None:
        if not self._settings.polygon_api_key:
            raise AuthenticationError("Polygon API key is not configured")

    def _get_json(self, url: str, *, params: dict[str, Any]) -> JsonValue:
        try:
            payload = self._http_client.get(url, params=params)
            self._raise_for_polygon_status(payload)
            return payload
        except DataProviderError:
            raise
        except Exception as exc:
            raise DataProviderError("Polygon provider request failed") from exc

    def _raise_for_polygon_status(self, payload: JsonValue) -> None:
        if not isinstance(payload, dict):
            raise DataProviderError("Polygon response must be a JSON object")

        status = payload.get("status")
        if not isinstance(status, str):
            return

        normalized_status = status.upper()
        if normalized_status == "NOT_AUTHORIZED":
            raise AuthenticationError("Polygon API request was not authorized")
        if normalized_status == "ERROR":
            message = str(payload.get("error") or payload.get("message") or status)
            if "rate" in message.lower() or "limit" in message.lower():
                raise RateLimitError(f"Polygon API rate limit error: {message}")
            raise DataProviderError(f"Polygon API error: {message}")

    def _daily_prices_to_frame(self, symbol: str, payload: JsonValue) -> pd.DataFrame:
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
            row = cast(dict[str, Any], item)
            try:
                rows.append(
                    {
                        "symbol": symbol.upper(),
                        "timestamp": pd.to_datetime(row["t"], unit="ms", utc=True),
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
        return normalize_price_frame(frame)

    def _health_to_frame(self, payload: JsonValue) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Polygon health response must be an object")

        server_time = payload.get("serverTime")
        checked_at = pd.Timestamp.now(tz="UTC") if server_time is None else server_time
        market = payload.get("market", "unknown")
        status = "ok" if isinstance(market, str) and market else "unknown"

        frame = pd.DataFrame(
            [
                {
                    "provider": self.name,
                    "status": status,
                    "checked_at": checked_at,
                    "latency_ms": None,
                    "message": f"market={market}",
                }
            ]
        )
        return normalize_health_check_frame(frame)
