"""Unit test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from market_platform.config import get_settings


@pytest.fixture(autouse=True)
def isolate_unit_test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep unit tests isolated from local .env provider credentials and order."""

    monkeypatch.setenv("MARKET_PLATFORM_DATA_PROVIDER_ORDER", "")
    monkeypatch.setenv("POLYGON_API_KEY", "")
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "")

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()