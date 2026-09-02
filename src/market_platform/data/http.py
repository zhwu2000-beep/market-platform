"""Shared HTTP client for provider network access."""

import json as json_module
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from market_platform.config import get_settings
from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.logging import get_logger

type JsonValue = (
    dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None
)
type ExactJsonValue = (
    Mapping[str, ExactJsonValue]
    | tuple[ExactJsonValue, ...]
    | str
    | int
    | Decimal
    | bool
    | None
)
type SleepFn = Callable[[float], None]
type ResponseClock = Callable[[], datetime]

DEFAULT_USER_AGENT = "market-platform/0.1.0"
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
SENSITIVE_QUERY_PARAM_NAMES = {
    "apikey",
    "authorization",
    "access_token",
    "key",
    "token",
}
_EXACT_JSON_RESULT_SEAL = object()


@dataclass(frozen=True, slots=True, init=False)
class ExactJsonResult:
    """One immutable exact-decimal JSON transport observation."""

    value: ExactJsonValue
    response_received_at: datetime

    def __init__(self) -> None:
        raise TypeError("ExactJsonResult must be created by HTTPClient")

    @classmethod
    def _create(
        cls,
        *,
        value: object,
        response_received_at: datetime,
        seal: object,
    ) -> ExactJsonResult:
        if seal is not _EXACT_JSON_RESULT_SEAL:
            raise TypeError("ExactJsonResult construction is private")
        result = object.__new__(cls)
        object.__setattr__(result, "value", _freeze_exact_json(value))
        object.__setattr__(
            result,
            "response_received_at",
            _canonical_response_received_at(response_received_at),
        )
        return result


@dataclass(frozen=True, slots=True)
class HttpClientConfig:
    """Configuration for the shared provider HTTP client."""

    timeout_seconds: float = 30.0
    max_retries: int = 2
    backoff_factor: float = 0.5
    user_agent: str = DEFAULT_USER_AGENT
    default_headers: Mapping[str, str] = field(default_factory=dict)


class HTTPClient:
    """Synchronous HTTP client used by all data providers."""

    def __init__(
        self,
        config: HttpClientConfig | None = None,
        client: httpx.Client | None = None,
        sleep: SleepFn = time.sleep,
        response_clock: ResponseClock | None = None,
    ) -> None:
        self.config = config or HttpClientConfig()
        self._sleep = sleep
        self._response_clock = _utc_now if response_clock is None else response_clock
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self.config.timeout_seconds),
            headers=self._headers(),
        )
        self._logger = get_logger(__name__)

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        """Send a GET request and return parsed JSON."""

        return self.request("GET", url, params=params, headers=headers)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: JsonValue | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        """Send an HTTP request with retry, logging, and normalized errors."""

        response = self._send_request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
        )
        return self._parse_json(response)

    def get_exact_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ExactJsonResult:
        """Send GET and return immutable JSON with exact decimal numbers."""

        response = self._send_request(
            "GET",
            url,
            params=params,
            json=None,
            headers=headers,
        )
        response_received_at = self._response_clock()
        return ExactJsonResult._create(
            value=self._parse_exact_json(response),
            response_received_at=response_received_at,
            seal=_EXACT_JSON_RESULT_SEAL,
        )

    def _send_request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None,
        json: JsonValue | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        """Return one successful response through the shared transport policy."""

        merged_headers = self._headers(headers)
        attempts = self.config.max_retries + 1
        last_error: DataProviderError | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._logger.info(
                    "provider_http_request method=%s url=%s params=%s attempt=%s",
                    method,
                    self._redact_url(url),
                    self._redact_params(params),
                    attempt,
                )
                response = self._client.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=merged_headers,
                    timeout=self.config.timeout_seconds,
                )
                if self._should_retry_status(response.status_code, attempt, attempts):
                    last_error = self._status_error(response)
                    self._sleep(self._backoff_seconds(attempt))
                    continue

                self._raise_for_status(response)
                return response
            except httpx.RequestError as exc:
                last_error = NetworkError(f"Network request failed: {exc}")
            except DataProviderError:
                raise

            if attempt < attempts:
                self._sleep(self._backoff_seconds(attempt))

        if last_error is not None:
            raise last_error
        raise DataProviderError("HTTP request failed without a captured error")

    def close(self) -> None:
        """Close the underlying HTTP client when owned by this wrapper."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HTTPClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self, headers: Mapping[str, str] | None = None) -> dict[str, str]:
        merged = {
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
            **self.config.default_headers,
        }
        if headers is not None:
            merged.update(headers)
        return merged

    def _backoff_seconds(self, attempt: int) -> float:
        return float(self.config.backoff_factor * (2 ** (attempt - 1)))

    def _raise_for_status(self, response: httpx.Response) -> None:
        error = self._status_error(response)
        if error is not None:
            raise error

    def _status_error(self, response: httpx.Response) -> DataProviderError | None:
        status_code = response.status_code
        if status_code < 400:
            return None

        message = f"HTTP request failed with status {status_code}"
        if status_code in {401, 403}:
            return AuthenticationError(message)
        if status_code == 429:
            return RateLimitError(message)
        return DataProviderError(message)

    def _should_retry_status(
        self,
        status_code: int,
        attempt: int,
        attempts: int,
    ) -> bool:
        return status_code in RETRYABLE_STATUS_CODES and attempt < attempts

    def _parse_json(self, response: httpx.Response) -> JsonValue:
        try:
            parsed: JsonValue = response.json()
        except ValueError as exc:
            raise DataProviderError("HTTP response did not contain valid JSON") from exc
        return parsed

    def _parse_exact_json(self, response: httpx.Response) -> object:
        try:
            parsed: object = json_module.loads(
                response.content,
                parse_float=Decimal,
                parse_constant=_reject_non_json_number,
            )
        except ValueError as exc:
            raise DataProviderError("HTTP response did not contain valid JSON") from exc
        return parsed

    def _redact_url(self, url: str) -> str:
        parts = urlsplit(url)
        if not parts.query:
            return url

        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        redacted_query = urlencode(
            [(key, self._redact_query_value(key, value)) for key, value in query_pairs]
        )
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, redacted_query, parts.fragment)
        )

    def _redact_params(self, params: Mapping[str, Any] | None) -> dict[str, Any] | None:
        if params is None:
            return None
        return {
            key: self._redact_query_value(key, value) for key, value in params.items()
        }

    def _redact_query_value(self, key: str, value: Any) -> Any:
        if key.strip().lower() in SENSITIVE_QUERY_PARAM_NAMES:
            return "[REDACTED]"
        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_response_received_at(value: object) -> datetime:
    if type(value) is not datetime:
        raise TypeError("response clock must return an exact datetime")
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("response clock must return a timezone-aware datetime")
    return timestamp.astimezone(UTC)


def _reject_non_json_number(value: str) -> object:
    raise ValueError(f"non-JSON numeric constant is not supported: {value}")


def _freeze_exact_json(value: object) -> ExactJsonValue:
    if value is None or type(value) in (str, int, bool, Decimal):
        return cast(str | int | bool | Decimal | None, value)
    if type(value) is list:
        return tuple(_freeze_exact_json(item) for item in cast(list[object], value))
    if type(value) is dict:
        items = cast(dict[object, object], value)
        if any(type(key) is not str for key in items):
            raise DataProviderError("HTTP response JSON object keys must be strings")
        frozen = {
            cast(str, key): _freeze_exact_json(item) for key, item in items.items()
        }
        return MappingProxyType(frozen)
    raise DataProviderError("HTTP response contained an unsupported JSON value")


def create_http_client() -> HTTPClient:
    """Create a provider HTTP client from application settings."""

    settings = get_settings()
    return HTTPClient(
        HttpClientConfig(timeout_seconds=float(settings.request_timeout_seconds))
    )
