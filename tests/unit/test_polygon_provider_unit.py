from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pandas as pd
import pytest

from market_platform.data.exceptions import ConfigurationError
from market_platform.data.http import HTTPClient
from market_platform.data.providers.polygon import POLYGON_BASE_URL, PolygonProvider


def test_polygon_provider_can_be_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    provider = PolygonProvider()

    assert provider.base_url == POLYGON_BASE_URL
    assert provider.api_key == ""


def test_polygon_provider_uses_injected_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={})
    )
    client = HTTPClient(client=httpx.Client(transport=transport))

    provider = PolygonProvider(http_client=client)

    assert provider.http_client is client


def test_polygon_provider_allows_missing_api_key_on_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = PolygonProvider()

    assert provider.api_key == ""


def test_polygon_provider_daily_prices_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apiKey"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "t": 1767312000000,
                        "o": 2.0,
                        "h": 3.0,
                        "l": 1.5,
                        "c": 2.5,
                        "v": 200,
                    },
                    {
                        "t": 1767225600000,
                        "o": 1.0,
                        "h": 2.0,
                        "l": 0.5,
                        "c": 1.5,
                        "v": 100,
                    },
                ]
            },
        )

    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(
        provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02")
    )

    assert "/v2/aggs/ticker/MSFT/range/1/day/2026-01-01/2026-01-02" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == [
        "symbol",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
    ]
    assert frame["timestamp"].dt.tz is not None
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    ]
    assert list(frame["symbol"]) == ["MSFT", "MSFT"]
    assert list(frame["provider"]) == ["polygon", "polygon"]


def test_polygon_provider_daily_prices_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    )
    provider = PolygonProvider(
        http_client=HTTPClient(client=httpx.Client(transport=transport))
    )

    with pytest.raises(ConfigurationError, match="POLYGON_API_KEY is not configured"):
        asyncio.run(provider.get_daily_prices("msft", date(2026, 1, 1), "2026-01-02"))


def test_polygon_provider_health_check_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apiKey"]
        return httpx.Response(200, json={"status": "OK", "message": "connected"})

    provider = PolygonProvider(
        http_client=HTTPClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    )

    frame = asyncio.run(provider.health_check())

    assert "/v1/marketstatus/now" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["provider", "status", "message"]
    assert frame.at[0, "provider"] == "polygon"
    assert frame.at[0, "status"] == "OK"
    assert frame.at[0, "message"] == "connected"
