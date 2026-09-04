"""Polygon provider skeleton."""

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import pandas as pd

from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import ExactJsonResult, HTTPClient, JsonValue
from market_platform.data.models import (
    LATEST_PRICE_COLUMNS,
    PRICE_COLUMNS,
    normalize_latest_price_frame,
    normalize_price_frame,
)
from market_platform.data.provider import DataProvider, normalize_date_like

POLYGON_BASE_URL = "https://api.polygon.io"
POLYGON_PROVIDER_NAME = "polygon"
_COMPLETED_DAILY_BASE_URL = "https://api.polygon.io"
_COMPLETED_DAILY_MULTIPLIER = 1
_COMPLETED_DAILY_TIMESPAN = "day"
_COMPLETED_DAILY_ADJUSTED = True
_COMPLETED_DAILY_SORT = "asc"
_COMPLETED_DAILY_LIMIT = 50000
_COMPLETED_DAILY_TICKER_MAX_LENGTH = 32
_COMPLETED_DAILY_TICKER_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*\Z",
    re.ASCII,
)
_CANONICAL_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_CREDENTIAL_QUERY_PARAM_CONCEPTS = frozenset(
    {
        "apikey",
        "xapikey",
        "apitoken",
        "authorization",
        "accesstoken",
        "clientsecret",
        "key",
        "token",
    }
)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyAggregate:
    """One immutable exact-number aggregate from Polygon."""

    timestamp: int | Decimal
    open: int | Decimal
    high: int | Decimal
    low: int | Decimal
    close: int | Decimal
    volume: int | Decimal

    def __post_init__(self) -> None:
        for name in ("timestamp", "open", "high", "low", "close", "volume"):
            _exact_number(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyAcquisition:
    """One immutable Polygon completed-daily transport acquisition.

    The next_page_reference field is a sanitized provider-observed pagination
    reference, never the raw next_url response value.
    """

    requested_ticker: str
    requested_from: str
    requested_to: str
    response_ticker_is_present: bool
    response_ticker: str | None
    response_adjusted_is_present: bool
    response_adjusted: bool | None
    request_id_is_present: bool
    request_id: str | None
    query_count_is_present: bool
    query_count: int | None
    results_count_is_present: bool
    results_count: int | None
    count_is_present: bool
    count: int | None
    next_url_is_present: bool
    next_page_reference: str | None
    results_is_present: bool
    rows: tuple[PolygonCompletedDailyAggregate, ...]
    response_received_at: datetime
    request_base_url: str = field(init=False, default=_COMPLETED_DAILY_BASE_URL)
    resolved_route: str = field(init=False)
    multiplier: int = field(init=False, default=_COMPLETED_DAILY_MULTIPLIER)
    timespan: str = field(init=False, default=_COMPLETED_DAILY_TIMESPAN)
    adjusted: bool = field(init=False, default=_COMPLETED_DAILY_ADJUSTED)
    sort: str = field(init=False, default=_COMPLETED_DAILY_SORT)
    limit: int = field(init=False, default=_COMPLETED_DAILY_LIMIT)

    def __post_init__(self) -> None:
        ticker = _validate_completed_daily_ticker(self.requested_ticker)
        requested_from = _validate_canonical_date_string(
            self.requested_from,
            "requested_from",
        )
        requested_to = _validate_canonical_date_string(
            self.requested_to,
            "requested_to",
        )
        _validate_completed_daily_interval(requested_from, requested_to)
        _validate_optional_presence(
            self.response_ticker_is_present,
            self.response_ticker,
            str,
            "response_ticker",
        )
        _validate_optional_presence(
            self.response_adjusted_is_present,
            self.response_adjusted,
            bool,
            "response_adjusted",
        )
        _validate_optional_presence(
            self.request_id_is_present,
            self.request_id,
            str,
            "request_id",
        )
        _validate_optional_presence(
            self.query_count_is_present,
            self.query_count,
            int,
            "query_count",
        )
        _validate_optional_presence(
            self.results_count_is_present,
            self.results_count,
            int,
            "results_count",
        )
        _validate_optional_presence(
            self.count_is_present,
            self.count,
            int,
            "count",
        )
        _validate_optional_presence(
            self.next_url_is_present,
            self.next_page_reference,
            str,
            "next_page_reference",
        )
        if self.next_page_reference is not None:
            sanitized = _sanitize_next_page_reference(self.next_page_reference)
            if sanitized != self.next_page_reference:
                raise DataProviderError(
                    "Polygon completed-daily next_page_reference must be sanitized"
                )
        if type(self.results_is_present) is not bool:
            raise DataProviderError(
                "Polygon completed-daily results_is_present must be a boolean"
            )
        if type(self.rows) is not tuple:
            raise DataProviderError("Polygon completed-daily rows must be a tuple")
        if any(type(row) is not PolygonCompletedDailyAggregate for row in self.rows):
            raise DataProviderError(
                "Polygon completed-daily rows must contain exact aggregate values"
            )
        if not self.results_is_present and self.rows:
            raise DataProviderError(
                "Polygon completed-daily absent results cannot contain rows"
            )
        received_at = _validate_response_received_at(self.response_received_at)
        object.__setattr__(self, "requested_ticker", ticker)
        object.__setattr__(self, "requested_from", requested_from)
        object.__setattr__(self, "requested_to", requested_to)
        object.__setattr__(self, "response_received_at", received_at)
        object.__setattr__(
            self,
            "resolved_route",
            _completed_daily_route(ticker, requested_from, requested_to),
        )

    @property
    def additional_page_indicated(self) -> bool:
        """Return whether the provider supplied a non-null next-page reference."""

        return self.next_url_is_present and self.next_page_reference is not None


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
            params={
                "adjusted": "true",
                "sort": "asc",
                "limit": "50000",
                "apiKey": api_key,
            },
        )
        return self._daily_payload_to_frame(symbol=symbol, payload=payload)

    async def get_completed_daily_acquisition(
        self,
        ticker: str,
        start: date | str,
        end: date | str,
    ) -> PolygonCompletedDailyAcquisition:
        """Acquire and preserve the fixed Polygon completed-daily source response."""

        api_key = self._require_api_key()
        requested_ticker = _validate_completed_daily_ticker(ticker)
        requested_from = _canonical_completed_daily_date(start, "start")
        requested_to = _canonical_completed_daily_date(end, "end")
        _validate_completed_daily_interval(requested_from, requested_to)
        route = _completed_daily_route(
            requested_ticker,
            requested_from,
            requested_to,
        )
        exact_result = self._http_client.get_exact_json(
            f"{_COMPLETED_DAILY_BASE_URL}{route}",
            params={
                "adjusted": "true",
                "sort": _COMPLETED_DAILY_SORT,
                "limit": str(_COMPLETED_DAILY_LIMIT),
                "apiKey": api_key,
            },
        )
        return _parse_completed_daily_acquisition(
            exact_result,
            requested_ticker=requested_ticker,
            requested_from=requested_from,
            requested_to=requested_to,
        )

    async def get_intraday_prices(
        self,
        symbol: str,
        start: datetime | date | str,
        end: datetime | date | str,
        interval: str = "1min",
    ) -> pd.DataFrame:
        """Return Polygon intraday aggregates as a standardized DataFrame."""

        api_key = self._require_api_key()
        multiplier, timespan = self._interval_to_polygon_params(interval)
        start_str = normalize_date_like(start)
        end_str = normalize_date_like(end)
        payload = self._request(
            (
                f"/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/"
                f"{timespan}/{start_str}/{end_str}"
            ),
            params={"apiKey": api_key},
        )
        return self._historical_payload_to_frame(
            symbol=symbol,
            payload=payload,
            missing_field_message=(
                "Polygon intraday price result missing field: {field}"
            ),
        )

    async def get_latest_price(self, symbol: str) -> pd.DataFrame:
        """Return the latest Polygon price as a standardized DataFrame."""

        api_key = self._require_api_key()
        payload = self._request(
            f"/v2/aggs/ticker/{symbol.upper()}/prev",
            params={"adjusted": "true", "apiKey": api_key},
        )
        return self._latest_payload_to_frame(symbol=symbol, payload=payload)

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
            raise DataProviderError("Polygon historical response must be an object")
        if payload.get("adjusted") is not True:
            raise DataProviderError(
                "Polygon daily response must prove adjusted is exact boolean true"
            )
        return self._historical_payload_to_frame(
            symbol=symbol,
            payload=payload,
            missing_field_message="Polygon daily price result missing field: {field}",
            normalize_daily_timestamp=True,
        )

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

    def _historical_payload_to_frame(
        self,
        *,
        symbol: str,
        payload: JsonValue,
        missing_field_message: str,
        normalize_daily_timestamp: bool = False,
    ) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Polygon historical response must be an object")

        results = payload.get("results", [])
        if results is None:
            results = []
        if not isinstance(results, list):
            raise DataProviderError("Polygon historical results must be a list")
        if not results:
            empty_frame = pd.DataFrame(columns=PRICE_COLUMNS)
            empty_frame = normalize_price_frame(empty_frame)
            return empty_frame.sort_values("timestamp", ascending=True, kind="stable")

        rows: list[dict[str, object]] = []
        for item in results:
            if not isinstance(item, dict):
                raise DataProviderError("Polygon historical result must be an object")
            try:
                timestamp_value = (
                    _daily_timestamp_value(item["t"])
                    if normalize_daily_timestamp
                    else cast(float | str | datetime | date, item["t"])
                )
                timestamp = pd.to_datetime(timestamp_value, unit="ms", utc=True)
                if normalize_daily_timestamp:
                    session_date = timestamp.tz_convert(
                        ZoneInfo("America/New_York")
                    ).date()
                    timestamp = pd.Timestamp(
                        datetime.combine(session_date, datetime.min.time(), tzinfo=UTC)
                    )
                rows.append(
                    {
                        "symbol": symbol.upper(),
                        "timestamp": timestamp,
                        "open": _daily_numeric_value(item["o"], "open")
                        if normalize_daily_timestamp
                        else item["o"],
                        "high": _daily_numeric_value(item["h"], "high")
                        if normalize_daily_timestamp
                        else item["h"],
                        "low": _daily_numeric_value(item["l"], "low")
                        if normalize_daily_timestamp
                        else item["l"],
                        "close": _daily_numeric_value(item["c"], "close")
                        if normalize_daily_timestamp
                        else item["c"],
                        "volume": _daily_numeric_value(item["v"], "volume")
                        if normalize_daily_timestamp
                        else item["v"],
                        "provider": self.name,
                    }
                )
            except KeyError as exc:
                raise DataProviderError(
                    missing_field_message.format(field=exc.args[0])
                ) from exc
            except (TypeError, ValueError, OverflowError) as exc:
                if not normalize_daily_timestamp:
                    raise
                raise DataProviderError(
                    "Polygon daily price result is malformed"
                ) from exc

        frame = pd.DataFrame(rows, columns=PRICE_COLUMNS)
        frame = normalize_price_frame(frame)
        frame = frame.sort_values("timestamp", ascending=True, kind="stable")
        return frame.reset_index(drop=True)

    def _interval_to_polygon_params(self, interval: str) -> tuple[int, str]:
        mapping: dict[str, tuple[int, str]] = {
            "1min": (1, "minute"),
            "5min": (5, "minute"),
            "15min": (15, "minute"),
            "30min": (30, "minute"),
            "1hour": (1, "hour"),
        }
        try:
            return mapping[interval]
        except KeyError as exc:
            raise ValueError(
                "Unsupported interval. Use one of: 1min, 5min, 15min, 30min, 1hour"
            ) from exc

    def _latest_payload_to_frame(self, symbol: str, payload: JsonValue) -> pd.DataFrame:
        if not isinstance(payload, dict):
            raise DataProviderError("Polygon latest price response must be an object")

        results = payload.get("results", [])
        if results is None:
            results = []
        if not isinstance(results, list):
            raise DataProviderError("Polygon latest price results must be a list")
        if not results:
            raise DataProviderError("Polygon latest price response has no results")

        item = results[0]
        if not isinstance(item, dict):
            raise DataProviderError("Polygon latest price result must be an object")

        try:
            price_value = item["c"] if "c" in item else item["price"]
            latest_frame = pd.DataFrame(
                [
                    {
                        "symbol": symbol.upper(),
                        "timestamp": pd.to_datetime(
                            cast(float | str | datetime | date, item["t"]),
                            unit="ms",
                            utc=True,
                        ),
                        "price": price_value,
                        "provider": self.name,
                    }
                ],
                columns=LATEST_PRICE_COLUMNS,
            )
        except KeyError as exc:
            raise DataProviderError(
                f"Polygon latest price result missing field: {exc.args[0]}"
            ) from exc

        latest_frame = normalize_latest_price_frame(latest_frame)
        return latest_frame.reset_index(drop=True)


def _daily_timestamp_value(value: object) -> int | float:
    if type(value) not in (int, float):
        raise ValueError("daily timestamp must be a finite number")
    numeric = cast(int | float, value)
    if not math.isfinite(numeric):
        raise ValueError("daily timestamp must be a finite number")
    return numeric


def _daily_numeric_value(value: object, field: str) -> int | float | Decimal:
    if type(value) not in (int, float, Decimal):
        raise ValueError(f"daily {field} must be a finite number")
    numeric = cast(int | float | Decimal, value)
    if not math.isfinite(numeric):
        raise ValueError(f"daily {field} must be a finite number")
    return numeric


def _parse_completed_daily_acquisition(
    exact_result: ExactJsonResult,
    *,
    requested_ticker: str,
    requested_from: str,
    requested_to: str,
) -> PolygonCompletedDailyAcquisition:
    payload = exact_result.value
    if not isinstance(payload, Mapping):
        raise DataProviderError("Polygon completed-daily response must be an object")

    response_ticker_is_present, response_ticker = _optional_string(payload, "ticker")
    response_adjusted_is_present, response_adjusted = _optional_bool(
        payload, "adjusted"
    )
    request_id_is_present, request_id = _optional_string(payload, "request_id")
    query_count_is_present, query_count = _optional_int(payload, "queryCount")
    results_count_is_present, results_count = _optional_int(payload, "resultsCount")
    count_is_present, count = _optional_int(payload, "count")
    next_url_is_present, observed_next_url = _optional_string(payload, "next_url")
    next_page_reference = (
        None
        if observed_next_url is None
        else _sanitize_next_page_reference(observed_next_url)
    )

    results_is_present = "results" in payload
    rows_value = payload.get("results", ())
    if results_is_present and type(rows_value) is not tuple:
        raise DataProviderError("Polygon completed-daily results must be an array")
    rows = tuple(
        _parse_completed_daily_row(item)
        for item in cast(tuple[object, ...], rows_value)
    )

    return PolygonCompletedDailyAcquisition(
        requested_ticker=requested_ticker,
        requested_from=requested_from,
        requested_to=requested_to,
        response_ticker_is_present=response_ticker_is_present,
        response_ticker=response_ticker,
        response_adjusted_is_present=response_adjusted_is_present,
        response_adjusted=response_adjusted,
        request_id_is_present=request_id_is_present,
        request_id=request_id,
        query_count_is_present=query_count_is_present,
        query_count=query_count,
        results_count_is_present=results_count_is_present,
        results_count=results_count,
        count_is_present=count_is_present,
        count=count,
        next_url_is_present=next_url_is_present,
        next_page_reference=next_page_reference,
        results_is_present=results_is_present,
        rows=rows,
        response_received_at=exact_result.response_received_at,
    )


def _parse_completed_daily_row(value: object) -> PolygonCompletedDailyAggregate:
    if not isinstance(value, Mapping):
        raise DataProviderError("Polygon completed-daily aggregate must be an object")
    try:
        return PolygonCompletedDailyAggregate(
            timestamp=_exact_number(value["t"], "timestamp"),
            open=_exact_number(value["o"], "open"),
            high=_exact_number(value["h"], "high"),
            low=_exact_number(value["l"], "low"),
            close=_exact_number(value["c"], "close"),
            volume=_exact_number(value["v"], "volume"),
        )
    except KeyError as exc:
        raise DataProviderError(
            f"Polygon completed-daily aggregate missing field: {exc.args[0]}"
        ) from exc


def _exact_number(value: object, field: str) -> int | Decimal:
    if type(value) not in (int, Decimal):
        raise DataProviderError(
            f"Polygon completed-daily {field} must be an exact JSON number"
        )
    if type(value) is Decimal and not value.is_finite():
        raise DataProviderError(
            f"Polygon completed-daily {field} must be a finite JSON number"
        )
    return cast(int | Decimal, value)


def _optional_string(
    payload: Mapping[str, object], field: str
) -> tuple[bool, str | None]:
    if field not in payload:
        return False, None
    value = payload[field]
    if value is not None and type(value) is not str:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be a string or null"
        )
    return True, value


def _optional_bool(
    payload: Mapping[str, object], field: str
) -> tuple[bool, bool | None]:
    if field not in payload:
        return False, None
    value = payload[field]
    if value is not None and type(value) is not bool:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be a boolean or null"
        )
    return True, value


def _optional_int(payload: Mapping[str, object], field: str) -> tuple[bool, int | None]:
    if field not in payload:
        return False, None
    value = payload[field]
    if value is not None and type(value) is not int:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be an integer or null"
        )
    return True, value


def _validate_completed_daily_ticker(value: object) -> str:
    if type(value) is not str:
        raise DataProviderError("Polygon completed-daily ticker must be a string")
    ticker = value
    if (
        len(ticker) > _COMPLETED_DAILY_TICKER_MAX_LENGTH
        or _COMPLETED_DAILY_TICKER_PATTERN.fullmatch(ticker) is None
    ):
        raise DataProviderError(
            "Polygon completed-daily ticker must be a valid U.S. stock ticker"
        )
    return ticker


def _canonical_completed_daily_date(value: object, field: str) -> str:
    if type(value) is date:
        return value.isoformat()
    if type(value) is not str:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be a date or exact YYYY-MM-DD string"
        )
    return _validate_canonical_date_string(value, field)


def _validate_canonical_date_string(value: object, field: str) -> str:
    if type(value) is not str or _CANONICAL_DATE_PATTERN.fullmatch(value) is None:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be an exact YYYY-MM-DD date"
        )
    text = value
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be an exact YYYY-MM-DD date"
        ) from exc
    if parsed.isoformat() != text:
        raise DataProviderError(
            f"Polygon completed-daily {field} must be an exact YYYY-MM-DD date"
        )
    return text


def _validate_completed_daily_interval(
    requested_from: str,
    requested_to: str,
) -> None:
    if requested_from > requested_to:
        raise DataProviderError(
            "Polygon completed-daily start date must not be after end date"
        )


def _completed_daily_route(ticker: str, requested_from: str, requested_to: str) -> str:
    ticker_segment = quote(ticker, safe="")
    return (
        f"/v2/aggs/ticker/{ticker_segment}/range/{_COMPLETED_DAILY_MULTIPLIER}/"
        f"{_COMPLETED_DAILY_TIMESPAN}/{requested_from}/{requested_to}"
    )


def _validate_optional_presence(
    is_present: object,
    value: object,
    expected_type: type[object],
    field: str,
) -> None:
    if type(is_present) is not bool:
        raise DataProviderError(
            f"Polygon completed-daily {field}_is_present must be a boolean"
        )
    if not is_present and value is not None:
        raise DataProviderError(f"Polygon completed-daily absent {field} must be null")
    if value is not None and type(value) is not expected_type:
        raise DataProviderError(f"Polygon completed-daily {field} has an invalid type")


def _validate_response_received_at(value: object) -> datetime:
    if type(value) is not datetime:
        raise DataProviderError(
            "Polygon completed-daily response_received_at must be a datetime"
        )
    received_at = value
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise DataProviderError(
            "Polygon completed-daily response_received_at must be timezone-aware"
        )
    if received_at.utcoffset() != timedelta(0):
        raise DataProviderError(
            "Polygon completed-daily response_received_at must be UTC"
        )
    return received_at.astimezone(UTC)


def _is_credential_query_parameter(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", name.strip().lower())
    return normalized in _CREDENTIAL_QUERY_PARAM_CONCEPTS


def _sanitize_next_page_reference(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.username is not None or parts.password is not None:
            raise DataProviderError(
                "Polygon completed-daily next_url must not contain user information"
            )
    except ValueError as exc:
        raise DataProviderError(
            "Polygon completed-daily next_url must be a valid URL"
        ) from exc
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_credential_query_parameter(key)
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
