"""Real provider smoke tests.

These tests touch external provider APIs and are skipped unless credentials
are explicitly enabled and credentials are configured.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import UTC, datetime

import pytest

from market_platform.config import get_settings
from market_platform.data.factory import create_default_market_data_service
from market_platform.data.models import PRICE_COLUMNS
from market_platform.research import (
    DailyTechnicalResearchRequest,
    DailyTechnicalResearchWorkflow,
    PriceAdjustmentPolicy,
    ResearchTimeframe,
    construct_daily_technical_analysis_profile,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

pytestmark = pytest.mark.skipif(
    os.environ.get("MARKET_PLATFORM_RUN_INTEGRATION_SMOKE") != "1",
    reason="integration smoke is opt-in; set MARKET_PLATFORM_RUN_INTEGRATION_SMOKE=1",
)


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


@pytest.mark.integration
def test_polygon_daily_technical_research_smoke() -> None:
    """Run the complete adjusted Polygon daily technical research path."""

    settings = get_settings()
    if not settings.polygon_api_key:
        pytest.skip("POLYGON_API_KEY is not configured")

    analysis_as_of = datetime.now(UTC)
    service = create_default_market_data_service(provider_order=["polygon"])
    request = DailyTechnicalResearchRequest(
        instrument=TradingInstrumentIdentity("AAPL", "NASDAQ"),
        timeframe=ResearchTimeframe.DAILY,
        provider="polygon",
        analysis_as_of=analysis_as_of,
        profile=construct_daily_technical_analysis_profile(),
    )
    result = asyncio.run(DailyTechnicalResearchWorkflow(service).run(request))
    projection = result.to_dict()

    assert result.snapshot.evidence.provider == "polygon"
    assert result.snapshot.evidence.adjustment_policy is PriceAdjustmentPolicy.ADJUSTED
    assert (
        result.snapshot.evidence.latest_completed_bar_session_date
        < result.snapshot.evidence.cutoff_session_date
    )
    assert result.snapshot.evidence.bar_count > 0
    assert projection == result.to_dict()
    assert json.loads(json.dumps(projection)) == projection
    for value in (
        result.snapshot.latest_close,
        result.snapshot.ema_8,
        result.snapshot.ema_20,
        result.snapshot.ema_144,
        result.snapshot.ema_169,
        result.snapshot.macd_line,
        result.snapshot.macd_signal,
        result.snapshot.macd_histogram,
        result.snapshot.rsi_14,
        result.snapshot.wilder_atr_14,
        result.snapshot.atr_percent_14,
        result.snapshot.realized_volatility,
        result.snapshot.current_drawdown,
    ):
        assert value is None or math.isfinite(value)
    assert result.snapshot.evidence.dataset_content_fingerprint.startswith("sha256:")
    assert result.snapshot.evidence.fingerprint.startswith("sha256:")
    assert result.snapshot.profile.fingerprint.startswith("sha256:")
    assert result.snapshot.fingerprint.startswith("sha256:")
