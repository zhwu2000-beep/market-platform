import logging
from collections.abc import Callable, Mapping
from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from inspect import signature

import httpx
import pytest

from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    NetworkError,
    RateLimitError,
)
from market_platform.data.http import ExactJsonResult, HTTPClient, HttpClientConfig


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    config: HttpClientConfig | None = None,
    sleeps: list[float] | None = None,
    response_clock: Callable[[], datetime] | None = None,
) -> HTTPClient:
    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport)
    sleep_calls = sleeps if sleeps is not None else []
    return HTTPClient(
        config=config,
        client=httpx_client,
        sleep=sleep_calls.append,
        response_clock=response_clock,
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


def test_standard_json_path_retains_existing_float_semantics() -> None:
    client = _client(lambda request: httpx.Response(200, content=b'{"value":123.456}'))

    payload = client.get("https://example.test/prices")

    assert type(payload) is dict
    assert type(payload["value"]) is float
    assert payload == {"value": 123.456}


def test_exact_json_preserves_decimal_and_large_precision() -> None:
    client = _client(
        lambda request: httpx.Response(
            200,
            content=(
                b'{"ordinary":123.456,'
                b'"precise":12345678901234567890.12345678901234567890123456789}'
            ),
        )
    )

    result = client.get_exact_json("https://example.test/prices")

    assert isinstance(result.value, Mapping)
    assert result.value["ordinary"] == Decimal("123.456")
    assert type(result.value["ordinary"]) is Decimal
    assert result.value["precise"] == Decimal(
        "12345678901234567890.12345678901234567890123456789"
    )


def test_exact_json_preserves_integer_and_nested_json_semantics() -> None:
    client = _client(
        lambda request: httpx.Response(
            200,
            content=(
                b'{"integer":123456789012345678901234567890,'
                b'"nested":[{"decimal":1.25},[2.5]],'
                b'"text":"value","flag":true,"missing":null}'
            ),
        )
    )

    result = client.get_exact_json("https://example.test/prices")
    payload = result.value

    assert isinstance(payload, Mapping)
    assert type(payload["integer"]) is int
    assert payload["integer"] == 123456789012345678901234567890
    assert payload["nested"] == (
        {"decimal": Decimal("1.25")},
        (Decimal("2.5"),),
    )
    assert payload["text"] == "value"
    assert payload["flag"] is True
    assert payload["missing"] is None
    assert not _contains_float(payload)


def test_exact_json_result_recursively_owns_immutable_values() -> None:
    result = _client(
        lambda request: httpx.Response(
            200,
            content=b'{"rows":[{"value":1.25}]}',
        )
    ).get_exact_json("https://example.test/prices")

    assert isinstance(result.value, Mapping)
    rows = result.value["rows"]
    assert type(rows) is tuple
    assert isinstance(rows[0], Mapping)
    with pytest.raises(TypeError):
        rows[0]["value"] = Decimal("2.5")


def test_equivalent_decimal_spellings_are_numerically_equal() -> None:
    first = _client(
        lambda request: httpx.Response(200, content=b'{"value":1.2300}')
    ).get_exact_json("https://example.test/prices")
    second = _client(
        lambda request: httpx.Response(200, content=b'{"value":1.23}')
    ).get_exact_json("https://example.test/prices")

    assert first.value == second.value


def test_exact_json_invalid_body_uses_existing_provider_error() -> None:
    client = _client(lambda request: httpx.Response(200, text="not-json"))

    with pytest.raises(DataProviderError, match="valid JSON"):
        client.get_exact_json("https://example.test/prices")


@pytest.mark.parametrize("constant", (b"NaN", b"Infinity", b"-Infinity"))
def test_exact_json_rejects_non_standard_numeric_constants(constant: bytes) -> None:
    client = _client(
        lambda request: httpx.Response(
            200,
            content=b'{"value":' + constant + b"}",
        )
    )

    with pytest.raises(DataProviderError, match="valid JSON"):
        client.get_exact_json("https://example.test/prices")


@pytest.mark.parametrize("method_name", ("get", "get_exact_json"))
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    (
        (401, AuthenticationError),
        (403, AuthenticationError),
        (429, RateLimitError),
        (500, DataProviderError),
    ),
)
def test_standard_and_exact_paths_share_http_error_mapping(
    method_name: str,
    status_code: int,
    expected_error: type[DataProviderError],
) -> None:
    client = _client(
        lambda request: httpx.Response(status_code, json={"error": "failed"}),
        config=HttpClientConfig(max_retries=0),
    )

    with pytest.raises(expected_error):
        getattr(client, method_name)("https://example.test/prices")


def test_exact_json_uses_shared_retry_and_backoff() -> None:
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503, json={"error": "try again"})
        return httpx.Response(200, content=b'{"value":1.25}')

    result = _client(
        handler,
        config=HttpClientConfig(max_retries=2, backoff_factor=0.25),
        sleeps=sleeps,
    ).get_exact_json("https://example.test/prices")

    assert calls == 3
    assert sleeps == [0.25, 0.5]
    assert isinstance(result.value, Mapping)
    assert result.value["value"] == Decimal("1.25")


def test_exact_json_uses_shared_logging_and_redaction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(lambda request: httpx.Response(200, content=b'{"ok":true}'))

    with caplog.at_level(logging.INFO, logger="market_platform.data.http"):
        client.get_exact_json(
            "https://example.test/prices?apiKey=secret-key&symbol=MSFT",
            params={"token": "token-value", "authorization": "Bearer secret"},
        )

    assert "provider_http_request" in caplog.text
    assert "secret-key" not in caplog.text
    assert "token-value" not in caplog.text
    assert "Bearer secret" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_exact_json_captures_canonical_receipt_time_at_transport_boundary() -> None:
    events: list[str] = []
    supplied = datetime(
        2026,
        9,
        2,
        16,
        30,
        tzinfo=timezone(timedelta(hours=8)),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        events.append("response")
        return httpx.Response(200, content=b'{"ok":true}')

    def response_clock() -> datetime:
        events.append("clock")
        return supplied

    result = _client(handler, response_clock=response_clock).get_exact_json(
        "https://example.test/prices"
    )

    assert events == ["response", "clock"]
    assert result.response_received_at == datetime(2026, 9, 2, 8, 30, tzinfo=UTC)
    assert result.response_received_at.tzinfo is UTC


def test_exact_json_receipt_clock_is_transport_configuration_not_request_input() -> (
    None
):
    parameters = signature(HTTPClient.get_exact_json).parameters

    assert "response_received_at" not in parameters
    assert "response_clock" not in parameters
    assert set(parameters) == {"self", "url", "params", "headers"}


def test_exact_json_result_exposes_no_transport_or_credentials() -> None:
    result = _client(
        lambda request: httpx.Response(200, content=b'{"ok":true}'),
        response_clock=lambda: datetime(2026, 9, 2, tzinfo=UTC),
    ).get_exact_json(
        "https://example.test/prices",
        params={"apiKey": "secret"},
    )

    assert type(result) is ExactJsonResult
    assert tuple(field.name for field in fields(result)) == (
        "value",
        "response_received_at",
    )
    assert not hasattr(result, "response")
    assert not hasattr(result, "headers")
    assert not hasattr(result, "client")
    assert not hasattr(result, "credentials")


def test_exact_json_result_cannot_be_caller_constructed() -> None:
    with pytest.raises(TypeError, match="created by HTTPClient"):
        ExactJsonResult()


def _contains_float(value: object) -> bool:
    if type(value) is float:
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if type(value) is tuple:
        return any(_contains_float(item) for item in value)
    return False
