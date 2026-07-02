import asyncio
import os
from datetime import date

import pytest

from market_platform.config import Settings
from market_platform.data.providers.polygon import PolygonProvider


@pytest.mark.integration
def test_polygon_provider_name() -> None:
    provider = PolygonProvider()

    assert provider.name == "polygon"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_POLYGON_INTEGRATION") != "1"
    or not Settings().polygon_api_key,
    reason="Set RUN_POLYGON_INTEGRATION=1 and POLYGON_API_KEY to run this test.",
)
def test_polygon_daily_prices_real_api() -> None:
    provider = PolygonProvider()

    frame = asyncio.run(
        provider.get_daily_prices("MSFT", date(2026, 1, 2), date(2026, 1, 2))
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
