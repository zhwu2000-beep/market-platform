"""Shared HTTP client for provider network access."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

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
type SleepFn = Callable[[float], None]

DEFAULT_USER_AGENT = "market-platform/0.1.0"
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


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
    ) -> None:
        self.config = config or HttpClientConfig()
        self._sleep = sleep
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

        merged_headers = self._headers(headers)
        attempts = self.config.max_retries + 1
        last_error: DataProviderError | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._logger.info(
                    "provider_http_request method=%s url=%s attempt=%s",
                    method,
                    url,
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
                return self._parse_json(response)
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


def create_http_client() -> HTTPClient:
    """Create a provider HTTP client from application settings."""

    settings = get_settings()
    return HTTPClient(
        HttpClientConfig(timeout_seconds=float(settings.request_timeout_seconds))
    )
