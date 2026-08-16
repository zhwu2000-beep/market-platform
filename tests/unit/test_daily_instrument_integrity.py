from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

import market_platform.research.daily_instrument_integrity as integrity_module
from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
from market_platform.cli import main as cli_main
from market_platform.data.capabilities import DataCapability
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService
from market_platform.instruments import (
    ExternalInstrumentIdentity,
    InstrumentMappingNotFoundError,
    InstrumentMappingSourceIdentity,
    InstrumentResolution,
    resolve_instrument_mapping,
)
from market_platform.research import (
    DailyInstrumentIntegrityEvidence,
    DailyInstrumentIntegrityPolicy,
    DailyTechnicalResearchRequest,
    IntegrityCheckedDailyTechnicalResearchResult,
    IntegrityCheckedDailyTechnicalResearchWorkflow,
    ResearchTimeframe,
    TechnicalAnalysisQuality,
    construct_daily_technical_analysis_profile,
)
from market_platform.trading import TradingInstrumentIdentity


def _registry(tmp_path: Path):
    document = {
        "schema_version": "trusted_instrument_mapping_document/v1",
        "source": {
            "source_id": "synthetic",
            "source_version": "1",
            "configuration_fingerprint": None,
        },
        "instruments": [
            {
                "instrument_id": "old.security",
                "trading_identity": {"symbol": "NVDA", "venue": "NASDAQ"},
                "asset_class": "equity",
                "trading_currency": "USD",
            },
            {
                "instrument_id": "new.security",
                "trading_identity": {"symbol": "NVDA", "venue": "NASDAQ"},
                "asset_class": "equity",
                "trading_currency": "USD",
            },
        ],
        "mappings": [
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "NVDA",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": "old.security",
                "valid_from": "2020-01-01",
                "expires_at": "2026-08-05",
            },
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "NVDA",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": "new.security",
                "valid_from": "2026-08-05",
                "expires_at": None,
            },
        ],
    }
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_trusted_instrument_mapping_registry(path)


def _prices() -> HistoricalPriceSeries:
    dates = pd.date_range("2026-08-03", "2026-08-09", tz=UTC)
    rows = []
    for index, timestamp in enumerate(dates):
        close = 100.0 + index
        rows.append(
            {
                "symbol": "NVDA",
                "timestamp": timestamp,
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000.0,
                "provider": "polygon",
            }
        )
    return HistoricalPriceSeries(pd.DataFrame(rows), symbol="NVDA", provider="polygon")


def _service() -> MarketDataService:
    provider = PolygonProvider(api_key="unused")
    return MarketDataService(
        ProviderSelectionPolicy(
            [
                ProviderCandidate(
                    "polygon",
                    provider,
                    frozenset({DataCapability.DAILY_PRICES}),
                )
            ],
            ["polygon"],
        )
    )


def test_ticker_reuse_trims_before_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired_symbols: list[str] = []

    async def acquire(
        service: object, request: DailyTechnicalResearchRequest
    ) -> HistoricalPriceSeries:
        acquired_symbols.append(request.instrument.symbol)
        return _prices()

    monkeypatch.setattr(integrity_module, "_acquire_polygon_daily_prices", acquire)
    request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("NVDA", "NASDAQ"),
        ResearchTimeframe.DAILY,
        "polygon",
        datetime(2026, 8, 10, tzinfo=UTC),
        construct_daily_technical_analysis_profile(),
    )
    registry = _registry(tmp_path)
    old_mapping, current_mapping = registry.mappings
    assert old_mapping.external_identity.to_dict() == (
        current_mapping.external_identity.to_dict()
    )
    assert old_mapping.canonical_instrument.instrument_id != (
        current_mapping.canonical_instrument.instrument_id
    )
    assert old_mapping.expires_at == current_mapping.valid_from
    result = asyncio.run(
        IntegrityCheckedDailyTechnicalResearchWorkflow(_service()).run(
            request, registry
        )
    )
    assert acquired_symbols == ["NVDA"]
    assert result.integrity.canonical_instrument_id.instrument_id == "new.security"
    assert result.integrity.excluded_before_valid_from_count == 2
    assert result.integrity.excluded_at_or_after_expires_at_count == 0
    assert result.integrity.admitted_bar_count == 4
    assert result.research.snapshot.quality is TechnicalAnalysisQuality.DEGRADED
    assert result.research.snapshot.evidence.dataset_content_fingerprint == (
        result.integrity.admitted_dataset_fingerprint
    )
    assert result.integrity.original_completed_dataset_fingerprint != (
        result.integrity.admitted_dataset_fingerprint
    )
    assert result.integrity.admitted_first_session_date == datetime(2026, 8, 5).date()
    assert result.research.snapshot.evidence.first_used_session_date == (
        datetime(2026, 8, 5).date()
    )
    assert list(result.to_dict()) == ["research", "integrity"]
    rendered_json = cli_main._render_integrity_checked_daily_research_result(
        result, "json"
    )
    assert list(json.loads(rendered_json)) == ["research", "integrity"]
    assert rendered_json == cli_main._render_integrity_checked_daily_research_result(
        result, "json"
    )
    rendered_table = cli_main._render_integrity_checked_daily_research_result(
        result, "table"
    )
    assert len(rendered_table.splitlines()) == 58
    assert "Integrity Evidence Fingerprint" in rendered_table
    object.__setattr__(result.integrity, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="fingerprint"):
        result.to_dict()


def test_missing_exact_identity_fails_before_provider_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def acquire(service: object, request: object) -> HistoricalPriceSeries:
        nonlocal calls
        calls += 1
        return _prices()

    monkeypatch.setattr(integrity_module, "_acquire_polygon_daily_prices", acquire)
    request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("NVDA", "NYSE"),
        ResearchTimeframe.DAILY,
        "polygon",
        datetime(2026, 8, 10, tzinfo=UTC),
        construct_daily_technical_analysis_profile(),
    )
    with pytest.raises(InstrumentMappingNotFoundError):
        asyncio.run(
            IntegrityCheckedDailyTechnicalResearchWorkflow(_service()).run(
                request, _registry(tmp_path)
            )
        )
    assert calls == 0


def test_factory_owned_models_and_policy_are_exact() -> None:
    assert list(DailyInstrumentIntegrityPolicy) == [
        DailyInstrumentIntegrityPolicy.TRIM_TO_MAPPING_INTERVAL
    ]
    with pytest.raises(TypeError):
        DailyInstrumentIntegrityEvidence()
    with pytest.raises(TypeError):
        IntegrityCheckedDailyTechnicalResearchResult()


def _verified_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[
    IntegrityCheckedDailyTechnicalResearchResult,
    DailyTechnicalResearchRequest,
    object,
]:
    async def acquire(service: object, request: object) -> HistoricalPriceSeries:
        return _prices()

    monkeypatch.setattr(integrity_module, "_acquire_polygon_daily_prices", acquire)
    request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("NVDA", "NASDAQ"),
        ResearchTimeframe.DAILY,
        "polygon",
        datetime(2026, 8, 10, tzinfo=UTC),
        construct_daily_technical_analysis_profile(),
    )
    registry = _registry(tmp_path)
    result = asyncio.run(
        IntegrityCheckedDailyTechnicalResearchWorkflow(_service()).run(
            request, registry
        )
    )
    return result, request, registry


def _recreate_evidence(
    result: IntegrityCheckedDailyTechnicalResearchResult,
    request: DailyTechnicalResearchRequest,
    registry: object,
    resolution: InstrumentResolution,
) -> DailyInstrumentIntegrityEvidence:
    evidence = result.integrity
    return DailyInstrumentIntegrityEvidence._create(
        request=request,
        resolution=resolution,
        registry=registry,
        original=integrity_module._prepare(evidence._original, request),
        admitted=integrity_module._prepare(evidence._admitted, request),
        excluded_before=evidence.excluded_before_valid_from_count,
        excluded_after=evidence.excluded_at_or_after_expires_at_count,
        seal=integrity_module._EVIDENCE_SEAL,
    )


def test_evidence_rejects_supplied_inactive_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, request, registry = _verified_result(tmp_path, monkeypatch)
    resolution = resolve_instrument_mapping(
        ExternalInstrumentIdentity("polygon", "NVDA", "NASDAQ"),
        registry.mappings,
        request.analysis_as_of,
    )
    object.__setattr__(resolution, "resolved_as_of", datetime(2026, 8, 4, tzinfo=UTC))
    with pytest.raises(ValueError):
        _recreate_evidence(result, request, registry, resolution)


def test_evidence_rejects_supplied_resolution_external_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, request, registry = _verified_result(tmp_path, monkeypatch)
    resolution = resolve_instrument_mapping(
        ExternalInstrumentIdentity("polygon", "NVDA", "NASDAQ"),
        registry.mappings,
        request.analysis_as_of,
    )
    object.__setattr__(
        resolution,
        "external_identity",
        ExternalInstrumentIdentity("polygon", "OTHER", "NASDAQ"),
    )
    with pytest.raises(ValueError):
        _recreate_evidence(result, request, registry, resolution)


@pytest.mark.parametrize(
    "attribute",
    [
        "canonical_instrument_id",
        "requested_trading_identity",
        "resolved_external_identity",
    ],
)
def test_corrupted_evidence_nested_identity_raises_value_error(
    attribute: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _, _ = _verified_result(tmp_path, monkeypatch)
    object.__setattr__(result.integrity, attribute, object())
    with pytest.raises(ValueError):
        result.integrity.to_dict()


def test_corrupted_evidence_mapping_source_registry_relationship_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _, _ = _verified_result(tmp_path, monkeypatch)
    object.__setattr__(
        result.integrity._mapping,
        "source",
        InstrumentMappingSourceIdentity("untrusted", "1"),
    )
    with pytest.raises(ValueError):
        result.integrity.to_dict()


def test_corrupted_evidence_resolution_instant_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _, _ = _verified_result(tmp_path, monkeypatch)
    object.__setattr__(
        result.integrity, "_resolved_as_of", datetime(2026, 8, 4, tzinfo=UTC)
    )
    with pytest.raises(ValueError):
        result.integrity.to_dict()


def test_coordinated_active_resolution_instant_drift_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _, _ = _verified_result(tmp_path, monkeypatch)
    evidence = result.integrity
    drifted = datetime(2026, 8, 9, tzinfo=UTC)
    assert evidence._mapping.is_active(drifted)
    assert drifted != evidence._creation_resolved_as_of

    object.__setattr__(evidence, "_resolved_as_of", drifted)
    object.__setattr__(evidence._resolution, "resolved_as_of", drifted)

    with pytest.raises(ValueError, match="drifted from creation"):
        evidence.to_dict()


def test_corrupted_evidence_resolution_external_identity_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _, _ = _verified_result(tmp_path, monkeypatch)
    object.__setattr__(
        result.integrity._resolution,
        "external_identity",
        ExternalInstrumentIdentity("polygon", "OTHER", "NASDAQ"),
    )
    with pytest.raises(ValueError):
        result.integrity.to_dict()


@pytest.mark.parametrize("attribute", ["integrity", "research"])
def test_corrupted_verified_nested_model_raises_value_error(
    attribute: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _, _ = _verified_result(tmp_path, monkeypatch)
    object.__setattr__(result, attribute, object())
    with pytest.raises(ValueError):
        result.to_dict()
