"""Real provider smoke tests.

These tests touch external provider APIs and are skipped unless credentials
are configured.
"""

from __future__ import annotations

import asyncio

import pytest

from market_platform.config import get_settings
from market_platform.data.factory import create_default_market_data_service
from market_platform.data.models import PRICE_COLUMNS


@pytest.mark.integration
def test_twelve_data_daily_prices_smoke() -> None:
    """Fetch a small real Twelve Data daily price sample."""

    settings = get_settings()
    if not settings.twelve_data_api_key:
        pytest.skip("TWELVE_DATA_API_KEY is not configured")

    service = create_default_market_data_service(provider_order=["twelvedata"])

    frame = asyncio.run(
        service.get_daily_prices(
            symbol="MSFT",
            start="2024-01-01",
            end="2024-01-10",
            provider="twelvedata",
        )
    )

    assert not frame.empty
    assert list(frame.columns) == PRICE_COLUMNS
    assert set(frame["symbol"]) == {"MSFT"}
    assert set(frame["provider"]) == {"twelvedata"}
    assert frame["timestamp"].dt.tz is not None