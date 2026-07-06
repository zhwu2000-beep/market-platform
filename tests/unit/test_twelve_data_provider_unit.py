from __future__ import annotations

import asyncio
from datetime import date, datetime

import httpx
import pytest

from market_platform.data.exceptions import ConfigurationError, DataProviderError
from market_platform.data.http import HTTPClient
from market_platform.data.providers.twelvedata import (
    TWELVE_DATA_BASE_URL,
    TwelveDataProvider,
)


def test_twelve_data_provider_name() -> None:
    assert TwelveDataProvider.name == "twelvedata"


def test_twelve_data_provider_can_be_constructed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    provider = TwelveDataProvider()

    assert provider.base_url == TWELVE_DATA_BASE_URL
    assert provider.api_key == ""


def test_twelve_data_provider_uses_injected_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = HTTPClient(client=httpx.Client(transport=transport))

    provider = TwelveDataProvider(http_client=client)

    assert provider.http_client is client


def test_twelve_data_provider_health_check_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json={"status": "ok"})
                )
            )
        )
    )

    with pytest.raises(
        ConfigurationError,
        match="TWELVE_DATA_API_KEY is not configured",
    ):
        asyncio.run(provider.health_check())


def test_twelve_data_provider_health_check_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["apiKey"] = request.url.params["apikey"]
        return httpx.Response(200, json={"status": "ok", "message": "connected"})

    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(transport=httpx.MockTransport(handler))
        )
    )

    frame = asyncio.run(provider.health_check())

    assert "/quote" in captured["url"]
    assert captured["apiKey"] == "test-key"
    assert list(frame.columns) == ["provider", "status", "message"]
    assert frame.at[0, "provider"] == "twelvedata"
    assert frame.at[0, "status"] == "ok"
    assert frame.at[0, "message"] == "connected"


def test_twelve_data_provider_health_check_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    provider = TwelveDataProvider(
        http_client=HTTPClient(
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=[])
                )
            )
        )
    )

    with pytest.raises(DataProviderError, match="must be an object"):
        asyncio.run(provider.health_check())


def test_twelve_data_provider_methods_raise_not_implemented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    provider = TwelveDataProvider()

    with pytest.raises(NotImplementedError):
        asyncio.run(
            provider.get_daily_prices(
                "MSFT",
                date(2026, 1, 1),
                date(2026, 1, 2),
            )
        )

    with pytest.raises(NotImplementedError):
        asyncio.run(
            provider.get_intraday_prices(
                "MSFT",
                datetime(2026, 1, 1, 0, 0),
                datetime(2026, 1, 2, 0, 0),
            )
        )

    with pytest.raises(NotImplementedError):
        asyncio.run(provider.get_latest_price("MSFT"))
