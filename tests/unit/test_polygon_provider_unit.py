from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import httpx
import pandas as pd
import pytest

from market_platform.data.exceptions import ConfigurationError, DataProviderError
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
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
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
        http_client=HTTPClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
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


def test_polygon_provider_latest_price_is_normalized(
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
                        "c": 123.45,
                    }
                ]
            },
        )

    provider = PolygonProvider(
        http_client=HTTPClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    )

    frame = asyncio.run(provider.get_latest_price("msft"))

    assert "/v2/aggs/ticker/MSFT/prev" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["symbol", "timestamp", "price", "provider"]
    assert frame.at[0, "symbol"] == "MSFT"
    assert frame.at[0, "provider"] == "polygon"
    assert frame.at[0, "price"] == 123.45
    assert frame["timestamp"].dt.tz is not None


def test_polygon_provider_latest_price_requires_api_key(
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
        asyncio.run(provider.get_latest_price("msft"))


def test_polygon_provider_latest_price_rejects_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="no results"):
        asyncio.run(provider.get_latest_price("msft"))


def test_polygon_provider_latest_price_rejects_missing_price_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={"results": [{"t": 1767312000000}]},
                    )
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="missing field"):
        asyncio.run(provider.get_latest_price("msft"))


@pytest.mark.parametrize(
    ("interval", "expected_path"),
    [
        ("1min", "/v2/aggs/ticker/MSFT/range/1/minute/"),
        ("1hour", "/v2/aggs/ticker/MSFT/range/1/hour/"),
    ],
)
def test_polygon_provider_intraday_prices_are_normalized(
    monkeypatch: pytest.MonkeyPatch,
    interval: str,
    expected_path: str,
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
                        "t": 1767225600000,
                        "o": 1.0,
                        "h": 2.0,
                        "l": 0.5,
                        "c": 1.5,
                        "v": 100,
                    },
                    {
                        "t": 1767312000000,
                        "o": 2.0,
                        "h": 3.0,
                        "l": 1.5,
                        "c": 2.5,
                        "v": 200,
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
        provider.get_intraday_prices(
            "msft",
            datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            interval=interval,
        )
    )

    assert expected_path in captured["url"]
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
    assert list(frame["timestamp"]) == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-02T00:00:00Z"),
    ]
    assert list(frame["symbol"]) == ["MSFT", "MSFT"]
    assert list(frame["provider"]) == ["polygon", "polygon"]
    assert frame["timestamp"].dt.tz is not None


def test_polygon_provider_intraday_prices_unsupported_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={})
                )
            )
        )
    )

    with pytest.raises(ValueError, match="Unsupported interval"):
        asyncio.run(
            provider.get_intraday_prices(
                "msft",
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
                interval="2min",
            )
        )


def test_polygon_provider_intraday_prices_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                )
            )
        )
    )

    with pytest.raises(ConfigurationError, match="POLYGON_API_KEY is not configured"):
        asyncio.run(
            provider.get_intraday_prices(
                "msft",
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            )
        )


def test_polygon_provider_intraday_prices_returns_empty_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": []})
                )
            )
        )
    )

    frame = asyncio.run(
        provider.get_intraday_prices(
            "msft",
            datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
        )
    )

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
    assert frame.empty


def test_polygon_provider_intraday_prices_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    provider = PolygonProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"results": "bad"})
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="must be a list"):
        asyncio.run(
            provider.get_intraday_prices(
                "msft",
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
            )
        )
