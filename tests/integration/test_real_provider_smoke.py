"""Real provider smoke tests.

These tests touch external provider APIs and are skipped unless credentials
are explicitly enabled and credentials are configured.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import UTC, datetime, timedelta
from numbers import Real
from pathlib import Path

import pytest

from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
from market_platform.application.polygon_completed_daily_evidence_candidate import (
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    PolygonCompletedDailyEvidenceCandidateApplicationService,
)
from market_platform.config import get_settings
from market_platform.data.factory import (
    create_default_market_data_service,
    create_polygon_provider,
)
from market_platform.data.models import PRICE_COLUMNS
from market_platform.instruments import ExternalInstrumentIdentity
from market_platform.research import (
    DailyTechnicalResearchRequest,
    DailyTechnicalResearchWorkflow,
    IntegrityCheckedDailyTechnicalResearchWorkflow,
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
    assert str(frame["timestamp"].dt.tz) == "UTC"
    for field in ("open", "high", "low", "close"):
        present_values = frame[field].dropna().tolist()
        assert present_values
        assert all(
            isinstance(value, Real) and not isinstance(value, bool)
            for value in present_values
        )
        assert all(math.isfinite(float(value)) for value in present_values)
    present_volume = frame["volume"].dropna().tolist()
    assert all(
        isinstance(value, Real) and not isinstance(value, bool)
        for value in present_volume
    )
    assert all(math.isfinite(float(value)) for value in present_volume)


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


@pytest.mark.integration
def test_polygon_verified_daily_technical_research_smoke(tmp_path: Path) -> None:
    """Run verified AAPL research with temporary trusted local metadata."""

    settings = get_settings()
    if not settings.polygon_api_key:
        pytest.skip("POLYGON_API_KEY is not configured")

    mapping_path = tmp_path / "trusted_mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "schema_version": "trusted_instrument_mapping_document/v1",
                "source": {
                    "source_id": "real-smoke-fixture",
                    "source_version": "1",
                    "configuration_fingerprint": None,
                },
                "instruments": [
                    {
                        "instrument_id": "security.aapl",
                        "trading_identity": {
                            "symbol": "AAPL",
                            "venue": "NASDAQ",
                        },
                        "asset_class": "equity",
                        "trading_currency": "USD",
                    }
                ],
                "mappings": [
                    {
                        "external_identity": {
                            "namespace": "polygon",
                            "external_symbol": "AAPL",
                            "external_venue": "NASDAQ",
                        },
                        "canonical_instrument_id": "security.aapl",
                        "valid_from": "1980-12-12",
                        "expires_at": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    analysis_as_of = datetime.now(UTC)
    request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("AAPL", "NASDAQ"),
        ResearchTimeframe.DAILY,
        "polygon",
        analysis_as_of,
        construct_daily_technical_analysis_profile(),
    )
    registry = load_trusted_instrument_mapping_registry(mapping_path)
    service = create_default_market_data_service(provider_order=["polygon"])
    result = asyncio.run(
        IntegrityCheckedDailyTechnicalResearchWorkflow(service).run(request, registry)
    )

    assert result.integrity.admitted_bar_count > 0
    assert result.integrity.requested_trading_identity == request.instrument
    assert result.integrity.fingerprint == result.integrity.to_dict()["fingerprint"]
    assert result.research.snapshot.evidence.dataset_content_fingerprint == (
        result.integrity.admitted_dataset_fingerprint
    )


@pytest.mark.integration
def test_polygon_completed_daily_evidence_candidate_smoke() -> None:
    """Construct one real Candidate from external operator-owned mapping data."""

    settings = get_settings()
    if not settings.polygon_api_key:
        pytest.skip("POLYGON_API_KEY is not configured")
    mapping_path = os.environ.get("MARKET_PLATFORM_POLYGON_CANDIDATE_MAPPING_PATH")
    if not mapping_path:
        pytest.skip("MARKET_PLATFORM_POLYGON_CANDIDATE_MAPPING_PATH is not configured")

    registry = load_trusted_instrument_mapping_registry(mapping_path)
    query_as_of = datetime.now(UTC)
    requested_to = query_as_of.date() - timedelta(days=1)
    request = PolygonCompletedDailyEvidenceCandidateApplicationRequest(
        external_identity=ExternalInstrumentIdentity(
            namespace="polygon",
            external_symbol="AAPL",
            external_venue="NASDAQ",
        ),
        mappings=registry.mappings,
        requested_from=requested_to - timedelta(days=10),
        requested_to=requested_to,
        query_as_of=query_as_of,
    )
    result = asyncio.run(
        PolygonCompletedDailyEvidenceCandidateApplicationService(
            create_polygon_provider()
        ).execute(request)
    )

    authorization = result.artifact.contract_authorization
    assert authorization.authorization_id == (
        "production.polygon_completed_daily_ohlcv"
    )
    assert authorization.authorization_version == "1.0.0"
    assert result.artifact.evidence_type == "polygon_completed_daily_ohlcv"
    assert result.material.api_base == "https://api.polygon.io"
    assert (
        result.material.query_as_of
        <= result.artifact.temporal_identity.platform_received_at
        <= result.artifact.temporal_identity.artifact_created_at
    )
    assert not hasattr(result.artifact, "validation")
    assert not hasattr(result.artifact, "admission")
    assert not hasattr(result.artifact, "consumable")
    serialized = json.dumps(
        {
            "artifact": result.artifact.to_dict(),
            "material": result.material.to_dict(),
        }
    )
    assert settings.polygon_api_key not in serialized
