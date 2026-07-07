import logging
from collections.abc import Callable

import httpx
import pytest

from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.http import HTTPClient, HttpClientConfig


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    config: HttpClientConfig | None = None,
    sleeps: list[float] | None = None,
) -> HTTPClient:
    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport)
    sleep_calls = sleeps if sleeps is not None else []
    return HTTPClient(
        config=config,
        client=httpx_client,
        sleep=sleep_calls.append,
    )


def test_get_parses_json_and_sends_default_headers() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    client = _client(
        handler,
        config=HttpClientConfig(
            user_agent="test-agent",
            default_headers={"X-Provider": "shared"},
        ),
    )

    assert client.get("https://example.test/prices") == {"ok": True}
    assert captured_headers["user-agent"] == "test-agent"
    assert captured_headers["accept"] == "application/json"
    assert captured_headers["x-provider"] == "shared"


def test_request_headers_override_defaults() -> None:
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(request.headers)
        return httpx.Response(200, json=[])

    client = _client(
        handler,
        config=HttpClientConfig(default_headers={"X-Provider": "default"}),
    )

    assert (
        client.get(
            "https://example.test/prices",
            headers={"X-Provider": "override"},
        )
        == []
    )
    assert captured_headers["x-provider"] == "override"


def test_timeout_is_applied_to_requests() -> None:
    captured_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_timeout.update(request.extensions["timeout"])
        return httpx.Response(200, json={"ok": True})

    client = _client(
        handler,
        config=HttpClientConfig(timeout_seconds=7.5),
    )

    client.get("https://example.test/prices")

    assert captured_timeout["connect"] == 7.5
    assert captured_timeout["read"] == 7.5
    assert captured_timeout["write"] == 7.5
    assert captured_timeout["pool"] == 7.5


def test_invalid_json_raises_provider_error() -> None:
    client = _client(lambda request: httpx.Response(200, text="not-json"))

    with pytest.raises(DataProviderError, match="valid JSON"):
        client.get("https://example.test/prices")


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (429, RateLimitError),
        (500, DataProviderError),
    ],
)
def test_http_errors_are_converted_to_unified_exceptions(
    status_code: int,
    expected_error: type[DataProviderError],
) -> None:
    client = _client(
        lambda request: httpx.Response(status_code, json={"error": "failed"}),
        config=HttpClientConfig(max_retries=0),
    )

    with pytest.raises(expected_error):
        client.get("https://example.test/prices")


def test_retry_uses_exponential_backoff_for_retryable_status() -> None:
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503, json={"error": "try again"})
        return httpx.Response(200, json={"ok": True})

    client = _client(
        handler,
        config=HttpClientConfig(max_retries=2, backoff_factor=0.25),
        sleeps=sleeps,
    )

    assert client.get("https://example.test/prices") == {"ok": True}
    assert calls == 3
    assert sleeps == [0.25, 0.5]


def test_network_errors_are_retried_then_converted() -> None:
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(
        handler,
        config=HttpClientConfig(max_retries=2, backoff_factor=1.0),
        sleeps=sleeps,
    )

    with pytest.raises(NetworkError, match="Network request failed"):
        client.get("https://example.test/prices")

    assert calls == 3
    assert sleeps == [1.0, 2.0]


def test_request_logging(caplog: pytest.LogCaptureFixture) -> None:
    client = _client(lambda request: httpx.Response(200, json={"ok": True}))

    with caplog.at_level(logging.INFO, logger="market_platform.data.http"):
        client.get(
            "https://example.test/prices?apiKey=secret-key&symbol=MSFT",
            params={
                "apikey": "secret-key-2",
                "token": "token-value",
                "access_token": "access-token-value",
                "authorization": "Bearer secret",
            },
        )

    assert "provider_http_request" in caplog.text
    assert "method=GET" in caplog.text
    assert "secret-key" not in caplog.text
    assert "secret-key-2" not in caplog.text
    assert "token-value" not in caplog.text
    assert "access-token-value" not in caplog.text
    assert "Bearer secret" not in caplog.text
    assert "[REDACTED]" in caplog.text
