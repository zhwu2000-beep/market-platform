import asyncio
from datetime import UTC, date

import httpx
import pandas as pd
import pytest

from market_platform.config import Settings
from market_platform.data.exceptions import (
    AuthenticationError,
    DataProviderError,
    RateLimitError,
)
from market_platform.data.http import HTTPClient, HttpClientConfig
from market_platform.data.models import HEALTH_CHECK_COLUMNS, PRICE_COLUMNS
from market_platform.data.providers.polygon import PolygonProvider


def _http_client(handler: httpx.MockTransport) -> HTTPClient:
    return HTTPClient(
        config=HttpClientConfig(max_retries=0),
        client=httpx.Client(transport=handler),
    )


def test_polygon_daily_prices_uses_http_client_and_normalizes_frame() -> None:
    captured_request: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["api_key"] = request.url.params["apiKey"]
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [
                    {
                        "t": 1767225600000,
                        "o": 100.0,
                        "h": 110.0,
                        "l": 95.0,
                        "c": 105.0,
                        "v": 123456,
                    }
                ],
            },
        )

    provider = PolygonProvider(
        settings=Settings(polygon_api_key="test-key"),
        http_client=_http_client(httpx.MockTransport(handler)),
        base_url="https://polygon.test",
    )

    frame = asyncio.run(
        provider.get_daily_prices("msft", date(2026, 1, 1), date(2026, 1, 2))
    )

    assert captured_request["api_key"] == "test-key"
    assert "/v2/aggs/ticker/MSFT/range/1/day/2026-01-01/2026-01-02" in (
        captured_request["url"]
    )
    assert list(frame.columns) == PRICE_COLUMNS
    assert frame.at[0, "symbol"] == "MSFT"
    assert frame.at[0, "timestamp"] == pd.Timestamp(
        "2026-01-01T00:00:00Z",
        tz=UTC,
    )
    assert frame.at[0, "open"] == 100.0
    assert frame.at[0, "provider"] == "polygon"


def test_polygon_daily_prices_returns_empty_canonical_frame() -> None:
    provider = PolygonProvider(
        settings=Settings(polygon_api_key="test-key"),
        http_client=_http_client(
            httpx.MockTransport(
                lambda request: httpx.Response(200, json={"status": "OK"})
            )
        ),
        base_url="https://polygon.test",
    )

    frame = asyncio.run(
        provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 2))
    )

    assert list(frame.columns) == PRICE_COLUMNS
    assert frame.empty


def test_polygon_health_check_normalizes_frame() -> None:
    provider = PolygonProvider(
        settings=Settings(polygon_api_key="test-key"),
        http_client=_http_client(
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "market": "open",
                        "serverTime": "2026-01-01T14:30:00Z",
                    },
                )
            )
        ),
        base_url="https://polygon.test",
    )

    frame = asyncio.run(provider.health_check())

    assert list(frame.columns) == HEALTH_CHECK_COLUMNS
    assert frame.at[0, "provider"] == "polygon"
    assert frame.at[0, "status"] == "ok"
    assert frame.at[0, "checked_at"] == pd.Timestamp("2026-01-01T14:30:00Z")
    assert frame.at[0, "message"] == "market=open"


def test_polygon_requires_api_key_before_network_access() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be called without an API key")

    provider = PolygonProvider(
        settings=Settings(polygon_api_key=""),
        http_client=_http_client(httpx.MockTransport(handler)),
        base_url="https://polygon.test",
    )

    with pytest.raises(AuthenticationError, match="API key"):
        asyncio.run(
            provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 2))
        )


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"status": "NOT_AUTHORIZED"}, AuthenticationError),
        ({"status": "ERROR", "error": "rate limit exceeded"}, RateLimitError),
        ({"status": "ERROR", "error": "bad request"}, DataProviderError),
    ],
)
def test_polygon_json_errors_are_converted_to_unified_exceptions(
    payload: dict[str, str],
    expected_error: type[DataProviderError],
) -> None:
    provider = PolygonProvider(
        settings=Settings(polygon_api_key="test-key"),
        http_client=_http_client(
            httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ),
        base_url="https://polygon.test",
    )

    with pytest.raises(expected_error):
        asyncio.run(
            provider.get_daily_prices("MSFT", date(2026, 1, 1), date(2026, 1, 2))
        )
