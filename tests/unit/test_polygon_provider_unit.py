from __future__ import annotations

import httpx
import pytest

from market_platform.data.http import HTTPClient
from market_platform.data.providers.polygon import POLYGON_BASE_URL, PolygonProvider


def test_polygon_provider_can_be_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")

    provider = PolygonProvider()

    assert provider.api_key == "test-key"
    assert provider.base_url == POLYGON_BASE_URL


def test_polygon_provider_uses_injected_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={})
    )
    client = HTTPClient(client=httpx.Client(transport=transport))

    provider = PolygonProvider(http_client=client)

    assert provider.http_client is client


def test_polygon_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    with pytest.raises(ValueError, match="POLYGON_API_KEY is not configured"):
        PolygonProvider()
