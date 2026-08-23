from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

import market_platform.application as application_package
import market_platform.application.daily_technical_strategy as contract_module
import market_platform.application.daily_technical_strategy_service as service_module
import market_platform.research as research_package
import market_platform.research.daily_instrument_integrity as integrity_module
import market_platform.research.daily_technical_assessment as assessment_module
import market_platform.research.daily_technical_interpretation as interpretation_module
import market_platform.research.daily_technical_strategy as strategy_module
from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION,
    DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION,
    DailyTechnicalStrategyApplicationRequest,
    DailyTechnicalStrategyApplicationResponse,
    DailyTechnicalStrategyApplicationService,
)
from market_platform.application.instrument_mapping_codec import (
    load_trusted_instrument_mapping_registry,
)
from market_platform.data.capabilities import DataCapability
from market_platform.data.historical import HistoricalPriceSeries
from market_platform.data.providers.polygon import PolygonProvider
from market_platform.data.selection import ProviderCandidate, ProviderSelectionPolicy
from market_platform.data.service import MarketDataService
from market_platform.research import (
    DailyTechnicalAssessment,
    DailyTechnicalInterpretation,
    DailyTechnicalResearchRequest,
    DailyTechnicalStrategy,
    IntegrityCheckedDailyTechnicalResearchResult,
    IntegrityCheckedDailyTechnicalResearchWorkflow,
    ResearchTimeframe,
    assess_daily_technical_interpretation,
    construct_daily_technical_analysis_profile,
    derive_daily_technical_strategy,
    interpret_daily_technical_research,
)
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalAssessmentPolicy,
    ClassicDailyTechnicalInterpretationPolicy,
    ClassicDailyTechnicalStrategyPolicy,
)
from market_platform.research.technical_policy import TechnicalPolicyIdentity
from market_platform.trading import TradingInstrumentIdentity

PRE_V075_APPLICATION_EXPORTS = [
    "HISTORICAL_REPLAY_RESEARCH_APPLICATION_REQUEST_SCHEMA_VERSION",
    "HISTORICAL_REPLAY_RESEARCH_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION",
    "ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION",
    "TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "BuiltInHistoricalReplayResearchStateModelResolver",
    "BuiltInHistoricalReplayResearchStrategyResolver",
    "CreateOrderIntentApplicationResponse",
    "CreateOrderIntentApplicationService",
    "CreateTradingSignalApplicationResponse",
    "CreateTradingSignalApplicationService",
    "HistoricalReplayResearchApplicationError",
    "HistoricalReplayResearchApplicationRequest",
    "HistoricalReplayResearchApplicationRequestError",
    "HistoricalReplayResearchApplicationResponse",
    "HistoricalReplayResearchApplicationService",
    "HistoricalReplayResearchInlineSourceRequest",
    "HistoricalReplayResearchMemberRequest",
    "HistoricalReplayResearchPriceRowRequest",
    "HistoricalReplayResearchStateModelRequest",
    "HistoricalReplayResearchStateModelResolver",
    "HistoricalReplayResearchStrategyRequest",
    "HistoricalReplayResearchStrategyResolver",
    "HistoricalSourceValidationError",
    "OrderIntentApplicationRequest",
    "ResolverIdentityMismatchError",
    "StateModelResolutionError",
    "StrategyResolutionError",
    "TradingApplicationCorrespondenceError",
    "TradingApplicationError",
    "TradingApplicationRequestError",
    "TradingApplicationResourceLimitError",
    "TradingInstrumentApplicationInput",
    "TradingSignalApplicationInput",
    "TradingSignalApplicationRequest",
    "TradingSignalSourceApplicationInput",
    "TradingTargetPositionApplicationInput",
    "UnsupportedApplicationSchemaError",
    "UnsupportedTradingApplicationSchemaError",
    "decode_order_intent_application_request",
    "decode_trading_signal_application_request",
    "decode_historical_replay_research_application_request",
]
V075_APPLICATION_EXPORTS = [
    "DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION",
    "DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "DailyTechnicalStrategyApplicationRequest",
    "DailyTechnicalStrategyApplicationResponse",
    "DailyTechnicalStrategyApplicationService",
]
DAILY_TECHNICAL_RESEARCH_PACKAGE_EXPORTS = [
    "DailyTechnicalResearchRequest",
    "DailyTechnicalResearchResult",
    "DailyTechnicalResearchWorkflow",
    "DAILY_INSTRUMENT_INTEGRITY_EVIDENCE_SCHEMA",
    "TRUSTED_INSTRUMENT_MAPPING_REGISTRY_SCHEMA",
    "DailyInstrumentIntegrityPolicy",
    "DailyInstrumentIntegrityEvidence",
    "TrustedInstrumentMappingRegistry",
    "IntegrityCheckedDailyTechnicalResearchResult",
    "IntegrityCheckedDailyTechnicalResearchWorkflow",
    "DailyTechnicalInterpretationPolicy",
    "DailyTechnicalAssessmentPolicy",
    "DailyTechnicalInterpretation",
    "DailyTechnicalAssessment",
    "interpret_daily_technical_research",
    "assess_daily_technical_interpretation",
    "DailyTechnicalStrategyPolicy",
    "DailyTechnicalStrategy",
    "derive_daily_technical_strategy",
]


def test_daily_technical_strategy_public_application_api_is_stable() -> None:
    assert application_package.__all__ == [
        *PRE_V075_APPLICATION_EXPORTS,
        *V075_APPLICATION_EXPORTS,
    ]
    assert contract_module.__all__ == V075_APPLICATION_EXPORTS[:2] + [
        "DailyTechnicalStrategyApplicationRequest",
        "DailyTechnicalStrategyApplicationResponse",
    ]
    assert service_module.__all__ == [
        "DailyTechnicalStrategyApplicationService"
    ]

    assert (
        application_package.DailyTechnicalStrategyApplicationRequest
        is contract_module.DailyTechnicalStrategyApplicationRequest
    )
    assert (
        application_package.DailyTechnicalStrategyApplicationResponse
        is contract_module.DailyTechnicalStrategyApplicationResponse
    )
    assert (
        application_package.DailyTechnicalStrategyApplicationService
        is service_module.DailyTechnicalStrategyApplicationService
    )


def test_daily_technical_strategy_schema_constants_are_public_and_exact() -> None:
    assert DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION == (
        "daily_technical_strategy_application_request/v1"
    )
    assert DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION == (
        "daily_technical_strategy_application_response/v1"
    )
    assert (
        application_package.DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
        == contract_module.DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
    )
    assert (
        application_package.DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION
        == contract_module.DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION
    )


def test_daily_technical_strategy_internals_are_not_supported_exports() -> None:
    unsupported_names = {
        "ClassicDailyTechnicalAssessmentConfiguration",
        "ClassicDailyTechnicalInterpretationConfiguration",
        "ClassicDailyTechnicalStrategyConfiguration",
        "_EXPECTED_ASSESSMENT_POLICY_IDENTITY",
        "_EXPECTED_INTERPRETATION_POLICY_IDENTITY",
        "_EXPECTED_STRATEGY_POLICY_IDENTITY",
        "_FINGERPRINT_PATTERN",
        "_require_expected_identity",
        "_validate_application_correspondence",
        "_validate_completed_domain_chain",
        "_validate_verified_research",
        "canonical_fingerprint",
        "construct_daily_technical_analysis_profile",
    }

    assert unsupported_names.isdisjoint(application_package.__all__)
    assert unsupported_names.isdisjoint(contract_module.__all__)
    assert unsupported_names.isdisjoint(service_module.__all__)


def test_daily_technical_research_domain_exports_remain_unchanged() -> None:
    export_count = len(DAILY_TECHNICAL_RESEARCH_PACKAGE_EXPORTS)

    assert (
        research_package.__all__[-export_count:]
        == DAILY_TECHNICAL_RESEARCH_PACKAGE_EXPORTS
    )
    assert integrity_module.__all__ == [
        "DAILY_INSTRUMENT_INTEGRITY_EVIDENCE_SCHEMA",
        "TRUSTED_INSTRUMENT_MAPPING_REGISTRY_SCHEMA",
        "DailyInstrumentIntegrityPolicy",
        "DailyInstrumentIntegrityEvidence",
        "TrustedInstrumentMappingRegistry",
        "IntegrityCheckedDailyTechnicalResearchResult",
        "IntegrityCheckedDailyTechnicalResearchWorkflow",
    ]
    assert interpretation_module.__all__ == [
        "DAILY_TECHNICAL_INTERPRETATION_SCHEMA",
        "DailyTechnicalDirectionalState",
        "DailyTechnicalExtensionState",
        "TechnicalComparisonOperandSource",
        "TechnicalComparisonOperator",
        "TechnicalComparisonOperand",
        "TechnicalComparisonEvidence",
        "DailyTechnicalInterpretationPolicy",
        "DailyTechnicalInterpretation",
        "interpret_daily_technical_research",
    ]
    assert assessment_module.__all__ == [
        "DAILY_TECHNICAL_ASSESSMENT_SCHEMA",
        "DailyTechnicalAssessmentOutcome",
        "DailyTechnicalAssessmentFindingKind",
        "DailyTechnicalAssessmentFinding",
        "DailyTechnicalAssessmentPolicy",
        "DailyTechnicalAssessment",
        "assess_daily_technical_interpretation",
    ]
    assert strategy_module.__all__ == [
        "DailyTechnicalStrategyPolicy",
        "derive_daily_technical_strategy",
        "DAILY_TECHNICAL_STRATEGY_SCHEMA",
        "DailyTechnicalStrategy",
        "DailyTechnicalStrategyMode",
        "DailyTechnicalStrategyRuleCode",
    ]
    assert set(V075_APPLICATION_EXPORTS).isdisjoint(research_package.__all__)


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


def _registry(tmp_path: Path):
    document = {
        "schema_version": "trusted_instrument_mapping_document/v1",
        "source": {
            "source_id": "test",
            "source_version": "1",
            "configuration_fingerprint": None,
        },
        "instruments": [
            {
                "instrument_id": "test.security",
                "trading_identity": {"symbol": "TEST", "venue": "NASDAQ"},
                "asset_class": "equity",
                "trading_currency": "USD",
            }
        ],
        "mappings": [
            {
                "external_identity": {
                    "namespace": "polygon",
                    "external_symbol": "TEST",
                    "external_venue": "NASDAQ",
                },
                "canonical_instrument_id": "test.security",
                "valid_from": "2020-01-01",
                "expires_at": None,
            }
        ],
    }
    path = tmp_path / "technical_mapping.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_trusted_instrument_mapping_registry(path)


def _build_completed_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    price_offset: float = 0.0,
) -> tuple[
    IntegrityCheckedDailyTechnicalResearchResult,
    DailyTechnicalInterpretation,
    DailyTechnicalAssessment,
    DailyTechnicalStrategy,
]:
    dates = pd.date_range(end="2026-08-09", periods=300, tz=UTC)
    prices = HistoricalPriceSeries(
        pd.DataFrame(
            [
                {
                    "symbol": "TEST",
                    "timestamp": timestamp,
                    "open": 100.0 + index + price_offset,
                    "high": 101.0 + index + price_offset,
                    "low": 99.0 + index + price_offset,
                    "close": 100.0 + index + price_offset,
                    "volume": 1000.0,
                    "provider": "polygon",
                }
                for index, timestamp in enumerate(dates)
            ]
        ),
        symbol="TEST",
        provider="polygon",
    )

    async def acquire(service: object, request: object) -> HistoricalPriceSeries:
        return prices

    monkeypatch.setattr(integrity_module, "_acquire_polygon_daily_prices", acquire)
    research_request = DailyTechnicalResearchRequest(
        TradingInstrumentIdentity("TEST", "NASDAQ"),
        ResearchTimeframe.DAILY,
        "polygon",
        datetime(2026, 8, 10, tzinfo=UTC),
        construct_daily_technical_analysis_profile(),
    )
    verified = asyncio.run(
        IntegrityCheckedDailyTechnicalResearchWorkflow(_service()).run(
            research_request,
            _registry(tmp_path),
        )
    )
    interpretation = interpret_daily_technical_research(
        verified,
        ClassicDailyTechnicalInterpretationPolicy(),
    )
    assessment = assess_daily_technical_interpretation(
        interpretation,
        ClassicDailyTechnicalAssessmentPolicy(),
    )
    strategy = derive_daily_technical_strategy(
        interpretation,
        assessment,
        ClassicDailyTechnicalStrategyPolicy(),
    )
    return verified, interpretation, assessment, strategy


@pytest.fixture
def completed_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    IntegrityCheckedDailyTechnicalResearchResult,
    DailyTechnicalInterpretation,
    DailyTechnicalAssessment,
    DailyTechnicalStrategy,
]:
    return _build_completed_chain(tmp_path, monkeypatch)


@pytest.fixture
def unrelated_completed_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    IntegrityCheckedDailyTechnicalResearchResult,
    DailyTechnicalInterpretation,
    DailyTechnicalAssessment,
    DailyTechnicalStrategy,
]:
    return _build_completed_chain(tmp_path, monkeypatch, price_offset=25.0)


def test_request_valid_construction_and_schema(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain

    request = DailyTechnicalStrategyApplicationRequest(verified)

    assert request.verified_research is verified
    assert request.schema_version == (
        DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION
    )
    request._validate()


def test_request_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="exact integrity-checked"):
        DailyTechnicalStrategyApplicationRequest(object())  # type: ignore[arg-type]


def test_request_rejects_verified_research_subclass(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain

    class DerivedVerifiedResearch(IntegrityCheckedDailyTechnicalResearchResult):
        pass

    derived = object.__new__(DerivedVerifiedResearch)
    object.__setattr__(derived, "research", verified.research)
    object.__setattr__(derived, "integrity", verified.integrity)

    with pytest.raises(TypeError, match="exact integrity-checked"):
        DailyTechnicalStrategyApplicationRequest(derived)


def test_request_is_frozen_and_slotted(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    request = DailyTechnicalStrategyApplicationRequest(completed_chain[0])

    assert not hasattr(request, "__dict__")
    assert [item.name for item in fields(request)] == [
        "verified_research",
        "schema_version",
        "request_fingerprint",
    ]
    with pytest.raises(FrozenInstanceError):
        request.schema_version = "other/v1"  # type: ignore[misc]


def test_request_fingerprint_is_deterministic_and_canonical(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain
    first = DailyTechnicalStrategyApplicationRequest(verified)
    second = DailyTechnicalStrategyApplicationRequest(verified)
    expected_payload = {
        "schema_version": (DAILY_TECHNICAL_STRATEGY_APPLICATION_REQUEST_SCHEMA_VERSION),
        "verified_research": verified.to_dict(),
    }

    assert first.request_fingerprint == second.request_fingerprint
    assert first.request_fingerprint == canonical_fingerprint(expected_payload)


def test_request_fingerprint_cannot_be_supplied(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    with pytest.raises(TypeError):
        DailyTechnicalStrategyApplicationRequest(
            completed_chain[0],
            request_fingerprint="sha256:" + "0" * 64,  # type: ignore[call-arg]
        )


def test_request_rejects_forged_verified_research(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain
    forged = object.__new__(IntegrityCheckedDailyTechnicalResearchResult)
    object.__setattr__(forged, "research", object())
    object.__setattr__(forged, "integrity", verified.integrity)

    with pytest.raises(ValueError, match="verified result retained state"):
        DailyTechnicalStrategyApplicationRequest(forged)


def test_request_rejects_forged_mixed_verified_research(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
    unrelated_completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain
    unrelated_verified, _, _, _ = unrelated_completed_chain
    forged = object.__new__(IntegrityCheckedDailyTechnicalResearchResult)
    object.__setattr__(forged, "research", verified.research)
    object.__setattr__(forged, "integrity", unrelated_verified.integrity)

    with pytest.raises(ValueError, match="verified result retained state"):
        DailyTechnicalStrategyApplicationRequest(forged)


def test_request_detects_nested_verified_research_mutation(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain
    request = DailyTechnicalStrategyApplicationRequest(verified)
    object.__setattr__(
        verified.research.request.instrument,
        "instrument_fingerprint",
        "sha256:" + "0" * 64,
    )

    with pytest.raises(ValueError, match="verified result retained state"):
        request._validate()


def test_request_detects_request_fingerprint_drift(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    request = DailyTechnicalStrategyApplicationRequest(completed_chain[0])
    object.__setattr__(request, "request_fingerprint", "sha256:" + "0" * 64)

    with pytest.raises(ValueError, match="request fingerprint"):
        request._validate()


def test_request_rejects_stale_nested_retained_state(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain
    request = DailyTechnicalStrategyApplicationRequest(verified)
    object.__setattr__(
        verified.integrity,
        "_creation_fingerprint",
        "sha256:" + "0" * 64,
    )

    with pytest.raises(ValueError, match="verified result retained state"):
        request._validate()


def test_request_rejects_stale_verified_research(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, _, _, _ = completed_chain
    object.__setattr__(
        verified.research.snapshot,
        "fingerprint",
        "sha256:" + "0" * 64,
    )

    with pytest.raises(ValueError):
        DailyTechnicalStrategyApplicationRequest(verified)


def _response(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> DailyTechnicalStrategyApplicationResponse:
    verified, interpretation, assessment, strategy = completed_chain
    request = DailyTechnicalStrategyApplicationRequest(verified)
    return DailyTechnicalStrategyApplicationResponse._create(
        request,
        interpretation,
        assessment,
        strategy,
    )


def test_response_rejects_direct_construction() -> None:
    with pytest.raises(TypeError, match="factory-created"):
        DailyTechnicalStrategyApplicationResponse()


def test_response_has_fixed_schema_and_validates_it(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    response = _response(completed_chain)

    assert response.schema_version == (
        DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION
    )
    response._validate()
    object.__setattr__(response, "schema_version", "other/v1")
    with pytest.raises(ValueError, match="response schema"):
        response._validate()


def test_response_retains_exact_frozen_fields(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, interpretation, assessment, strategy = completed_chain
    request = DailyTechnicalStrategyApplicationRequest(verified)
    response = DailyTechnicalStrategyApplicationResponse._create(
        request,
        interpretation,
        assessment,
        strategy,
    )

    assert [item.name for item in fields(response)] == [
        "application_request_fingerprint",
        "interpretation",
        "assessment",
        "strategy",
        "schema_version",
    ]
    assert response.application_request_fingerprint == request.request_fingerprint
    assert response.interpretation is interpretation
    assert response.assessment is assessment
    assert response.strategy is strategy
    assert not hasattr(response, "__dict__")
    with pytest.raises(FrozenInstanceError):
        response.schema_version = "other/v1"  # type: ignore[misc]


def test_response_has_no_fingerprint_family(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    response = _response(completed_chain)
    retained_names = {item.name for item in fields(response)}

    assert "response_fingerprint" not in retained_names
    assert "pipeline_fingerprint" not in retained_names
    assert "aggregate_fingerprint" not in retained_names
    assert "fingerprint" not in retained_names
    assert not hasattr(response, "response_fingerprint")
    assert not hasattr(response, "pipeline_fingerprint")
    assert not hasattr(response, "aggregate_fingerprint")
    assert not hasattr(response, "fingerprint")


def test_response_rejects_unrelated_and_mixed_lineage_chains(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
    unrelated_completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, interpretation, assessment, strategy = completed_chain
    (
        unrelated_verified,
        unrelated_interpretation,
        unrelated_assessment,
        unrelated_strategy,
    ) = unrelated_completed_chain
    unrelated_verified._validate()
    unrelated_interpretation._validate()
    unrelated_assessment._validate()
    unrelated_strategy._validate()
    request = DailyTechnicalStrategyApplicationRequest(verified)
    cases = (
        (
            unrelated_interpretation,
            unrelated_assessment,
            unrelated_strategy,
            "interpretation does not correspond",
        ),
        (
            interpretation,
            unrelated_assessment,
            unrelated_strategy,
            "assessment does not correspond",
        ),
        (
            interpretation,
            assessment,
            unrelated_strategy,
            "strategy does not correspond",
        ),
        (
            interpretation,
            unrelated_assessment,
            strategy,
            "assessment does not correspond",
        ),
    )

    for supplied_interpretation, supplied_assessment, supplied_strategy, error in cases:
        with pytest.raises(ValueError, match=error):
            DailyTechnicalStrategyApplicationResponse._create(
                request,
                supplied_interpretation,
                supplied_assessment,
                supplied_strategy,
            )


def test_response_accepts_independently_reconstructed_canonical_chain(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, interpretation, assessment, strategy = completed_chain
    reconstructed_interpretation = replace(interpretation)
    reconstructed_assessment = replace(assessment)
    reconstructed_strategy = replace(strategy)

    assert reconstructed_interpretation is not interpretation
    assert reconstructed_assessment is not assessment
    assert reconstructed_strategy is not strategy
    assert reconstructed_interpretation.to_dict() == interpretation.to_dict()
    assert reconstructed_assessment.to_dict() == assessment.to_dict()
    assert reconstructed_strategy.to_dict() == strategy.to_dict()

    response = DailyTechnicalStrategyApplicationResponse._create(
        DailyTechnicalStrategyApplicationRequest(verified),
        reconstructed_interpretation,
        reconstructed_assessment,
        reconstructed_strategy,
    )

    assert response.interpretation is reconstructed_interpretation
    assert response.assessment is reconstructed_assessment
    assert response.strategy is reconstructed_strategy


def test_response_correspondence_does_not_recompute_domain_semantics(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_recomputation(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("application correspondence must not recompute semantics")

    semantic_helpers = (
        (interpretation_module, "build_classic_comparison_evidence"),
        (interpretation_module, "classic_states"),
        (assessment_module, "build_classic_assessment_findings"),
        (assessment_module, "classic_assessment_outcome"),
        (strategy_module, "build_classic_assessment_findings"),
        (strategy_module, "classic_assessment_outcome"),
    )
    for module, name in semantic_helpers:
        monkeypatch.setattr(module, name, unexpected_recomputation)

    response = _response(completed_chain)

    assert response.interpretation is completed_chain[1]
    assert response.assessment is completed_chain[2]
    assert response.strategy is completed_chain[3]


def test_application_modules_do_not_import_private_domain_semantic_helpers() -> None:
    semantic_helper_names = {
        "_detach_assessment_semantics",
        "_detach_interpretation_semantics",
        "build_classic_assessment_findings",
        "build_classic_comparison_evidence",
        "classic_assessment_outcome",
        "classic_states",
    }
    forbidden_imports: set[tuple[str, str]] = set()

    for application_module in (contract_module, service_module):
        module_path = application_module.__file__
        assert module_path is not None
        tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None or not node.module.startswith(
                "market_platform.research"
            ):
                continue
            forbidden_imports.update(
                (node.module, alias.name)
                for alias in node.names
                if alias.name.startswith("_")
                or alias.name in semantic_helper_names
            )

    assert forbidden_imports == set()


class _InterpretationPolicyStub:
    def __init__(
        self,
        identity: TechnicalPolicyIdentity,
        events: list[str],
    ) -> None:
        self._identity = identity
        self._events = events

    @property
    def identity(self) -> TechnicalPolicyIdentity:
        self._events.append("interpretation_identity")
        return self._identity

    def interpret(
        self,
        verified_research: IntegrityCheckedDailyTechnicalResearchResult,
    ) -> DailyTechnicalInterpretation:
        del verified_research
        raise AssertionError("service must use the interpretation runner")


class _AssessmentPolicyStub:
    def __init__(
        self,
        identity: TechnicalPolicyIdentity,
        events: list[str],
    ) -> None:
        self._identity = identity
        self._events = events

    @property
    def identity(self) -> TechnicalPolicyIdentity:
        self._events.append("assessment_identity")
        return self._identity

    def assess(
        self,
        interpretation: DailyTechnicalInterpretation,
    ) -> DailyTechnicalAssessment:
        del interpretation
        raise AssertionError("service must use the assessment runner")


class _StrategyPolicyStub:
    def __init__(
        self,
        identity: TechnicalPolicyIdentity,
        events: list[str],
    ) -> None:
        self._identity = identity
        self._events = events

    @property
    def policy_identity(self) -> TechnicalPolicyIdentity:
        self._events.append("strategy_identity")
        return self._identity

    def determine(
        self,
        interpretation: DailyTechnicalInterpretation,
        assessment: DailyTechnicalAssessment,
    ) -> DailyTechnicalStrategy:
        del interpretation, assessment
        raise AssertionError("service must use the strategy runner")


def test_service_executes_each_stage_once_in_order_with_exact_inputs(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified, interpretation, assessment, strategy = completed_chain
    events: list[str] = []
    interpretation_policy = _InterpretationPolicyStub(
        ClassicDailyTechnicalInterpretationPolicy().identity,
        events,
    )
    assessment_policy = _AssessmentPolicyStub(
        ClassicDailyTechnicalAssessmentPolicy().identity,
        events,
    )
    strategy_policy = _StrategyPolicyStub(
        ClassicDailyTechnicalStrategyPolicy().policy_identity,
        events,
    )
    service = DailyTechnicalStrategyApplicationService(
        interpretation_policy,
        assessment_policy,
        strategy_policy,
    )
    events.clear()

    def run_interpretation(
        source: IntegrityCheckedDailyTechnicalResearchResult,
        policy: object,
    ) -> DailyTechnicalInterpretation:
        events.append("interpret")
        assert source is verified
        assert policy is interpretation_policy
        return interpretation

    def run_assessment(
        source: DailyTechnicalInterpretation,
        policy: object,
    ) -> DailyTechnicalAssessment:
        events.append("assess")
        assert source is interpretation
        assert policy is assessment_policy
        return assessment

    def run_strategy(
        interpretation_source: DailyTechnicalInterpretation,
        assessment_source: DailyTechnicalAssessment,
        policy: object,
    ) -> DailyTechnicalStrategy:
        events.append("strategy")
        assert interpretation_source is interpretation
        assert assessment_source is assessment
        assert policy is strategy_policy
        return strategy

    response_type = DailyTechnicalStrategyApplicationResponse

    class ResponseFactorySpy:
        @classmethod
        def _create(
            cls,
            request_arg: DailyTechnicalStrategyApplicationRequest,
            interpretation_arg: DailyTechnicalInterpretation,
            assessment_arg: DailyTechnicalAssessment,
            strategy_arg: DailyTechnicalStrategy,
        ) -> DailyTechnicalStrategyApplicationResponse:
            del cls
            events.append("response")
            return response_type._create(
                request_arg,
                interpretation_arg,
                assessment_arg,
                strategy_arg,
            )

    monkeypatch.setattr(
        service_module,
        "interpret_daily_technical_research",
        run_interpretation,
    )
    monkeypatch.setattr(
        service_module,
        "assess_daily_technical_interpretation",
        run_assessment,
    )
    monkeypatch.setattr(
        service_module,
        "derive_daily_technical_strategy",
        run_strategy,
    )
    monkeypatch.setattr(
        service_module,
        "DailyTechnicalStrategyApplicationResponse",
        ResponseFactorySpy,
    )

    request = DailyTechnicalStrategyApplicationRequest(verified)
    response = asyncio.run(service.execute(request))

    assert events == [
        "interpretation_identity",
        "assessment_identity",
        "strategy_identity",
        "interpret",
        "assess",
        "strategy",
        "response",
    ]
    assert response.interpretation is interpretation
    assert response.assessment is assessment
    assert response.strategy is strategy


def test_service_executes_real_classic_profile_successfully(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    verified, expected_interpretation, expected_assessment, expected_strategy = (
        completed_chain
    )
    request = DailyTechnicalStrategyApplicationRequest(verified)
    service = DailyTechnicalStrategyApplicationService(
        ClassicDailyTechnicalInterpretationPolicy(),
        ClassicDailyTechnicalAssessmentPolicy(),
        ClassicDailyTechnicalStrategyPolicy(),
    )

    response = asyncio.run(service.execute(request))

    assert type(response) is DailyTechnicalStrategyApplicationResponse
    assert response.application_request_fingerprint == request.request_fingerprint
    assert type(response.interpretation) is DailyTechnicalInterpretation
    assert type(response.assessment) is DailyTechnicalAssessment
    assert type(response.strategy) is DailyTechnicalStrategy
    assert response.interpretation.to_dict() == expected_interpretation.to_dict()
    assert response.assessment.to_dict() == expected_assessment.to_dict()
    assert response.strategy.to_dict() == expected_strategy.to_dict()
    assert response.assessment.source_interpretation_fingerprint == (
        response.interpretation.fingerprint
    )
    assert response.strategy.source_assessment_fingerprint == (
        response.assessment.fingerprint
    )


def test_service_validates_request_before_policy_identities_or_runners(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    events: list[str] = []
    service = DailyTechnicalStrategyApplicationService(
        _InterpretationPolicyStub(
            ClassicDailyTechnicalInterpretationPolicy().identity,
            events,
        ),
        _AssessmentPolicyStub(
            ClassicDailyTechnicalAssessmentPolicy().identity,
            events,
        ),
        _StrategyPolicyStub(
            ClassicDailyTechnicalStrategyPolicy().policy_identity,
            events,
        ),
    )
    events.clear()
    request = DailyTechnicalStrategyApplicationRequest(completed_chain[0])
    object.__setattr__(request, "request_fingerprint", "sha256:" + "0" * 64)

    with pytest.raises(ValueError, match="request fingerprint"):
        asyncio.run(service.execute(request))

    assert events == []


@pytest.mark.parametrize(
    "mismatch_stage",
    ["interpretation", "assessment", "strategy"],
)
def test_policy_mismatch_prevents_all_runner_invocations(
    mismatch_stage: str,
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    identities = {
        "interpretation": ClassicDailyTechnicalInterpretationPolicy().identity,
        "assessment": ClassicDailyTechnicalAssessmentPolicy().identity,
        "strategy": ClassicDailyTechnicalStrategyPolicy().policy_identity,
    }
    original = identities[mismatch_stage]
    identities[mismatch_stage] = TechnicalPolicyIdentity(
        policy_kind=original.policy_kind,
        policy_id=original.policy_id,
        behavioral_revision="1.0.1",
        configuration_schema=original.configuration_schema,
        configuration=original.configuration,
    )
    service = DailyTechnicalStrategyApplicationService(
        _InterpretationPolicyStub(identities["interpretation"], events),
        _AssessmentPolicyStub(identities["assessment"], events),
        _StrategyPolicyStub(identities["strategy"], events),
    )
    events.clear()
    runner_calls: list[str] = []

    def unexpected_runner(*args: object) -> object:
        del args
        runner_calls.append("runner")
        raise AssertionError("policy mismatch must prevent every runner")

    monkeypatch.setattr(
        service_module,
        "interpret_daily_technical_research",
        unexpected_runner,
    )
    monkeypatch.setattr(
        service_module,
        "assess_daily_technical_interpretation",
        unexpected_runner,
    )
    monkeypatch.setattr(
        service_module,
        "derive_daily_technical_strategy",
        unexpected_runner,
    )
    request = DailyTechnicalStrategyApplicationRequest(completed_chain[0])

    with pytest.raises(ValueError, match="fixed application profile"):
        asyncio.run(service.execute(request))

    assert events == [
        "interpretation_identity",
        "assessment_identity",
        "strategy_identity",
    ]
    assert runner_calls == []


def test_policy_identity_validation_does_not_trust_fingerprint_alone(
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
) -> None:
    events: list[str] = []
    forged = ClassicDailyTechnicalInterpretationPolicy().identity
    object.__setattr__(forged, "behavioral_revision", "1.0.1")
    service = DailyTechnicalStrategyApplicationService(
        _InterpretationPolicyStub(forged, events),
        _AssessmentPolicyStub(
            ClassicDailyTechnicalAssessmentPolicy().identity,
            events,
        ),
        _StrategyPolicyStub(
            ClassicDailyTechnicalStrategyPolicy().policy_identity,
            events,
        ),
    )
    events.clear()

    with pytest.raises(ValueError, match="fingerprint does not match content"):
        asyncio.run(
            service.execute(
                DailyTechnicalStrategyApplicationRequest(completed_chain[0])
            )
        )

    assert events == [
        "interpretation_identity",
        "assessment_identity",
        "strategy_identity",
    ]


@pytest.mark.parametrize(
    ("failure_stage", "expected_calls"),
    [
        ("interpret", {"interpret": 1, "assess": 0, "strategy": 0}),
        ("assess", {"interpret": 1, "assess": 1, "strategy": 0}),
        ("strategy", {"interpret": 1, "assess": 1, "strategy": 1}),
    ],
)
def test_service_propagates_original_stage_exception_without_response(
    failure_stage: str,
    expected_calls: dict[str, int],
    completed_chain: tuple[
        IntegrityCheckedDailyTechnicalResearchResult,
        DailyTechnicalInterpretation,
        DailyTechnicalAssessment,
        DailyTechnicalStrategy,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified, interpretation, assessment, strategy = completed_chain
    service = DailyTechnicalStrategyApplicationService(
        ClassicDailyTechnicalInterpretationPolicy(),
        ClassicDailyTechnicalAssessmentPolicy(),
        ClassicDailyTechnicalStrategyPolicy(),
    )
    calls = {"interpret": 0, "assess": 0, "strategy": 0}
    response_calls: list[str] = []
    error = RuntimeError(f"{failure_stage} failed")

    def run_interpretation(*args: object) -> DailyTechnicalInterpretation:
        del args
        calls["interpret"] += 1
        if failure_stage == "interpret":
            raise error
        return interpretation

    def run_assessment(*args: object) -> DailyTechnicalAssessment:
        del args
        calls["assess"] += 1
        if failure_stage == "assess":
            raise error
        return assessment

    def run_strategy(*args: object) -> DailyTechnicalStrategy:
        del args
        calls["strategy"] += 1
        if failure_stage == "strategy":
            raise error
        return strategy

    class UnexpectedResponseFactory:
        @classmethod
        def _create(cls, *args: object) -> object:
            del cls, args
            response_calls.append("response")
            raise AssertionError("a failed execution must not create a response")

    monkeypatch.setattr(
        service_module,
        "interpret_daily_technical_research",
        run_interpretation,
    )
    monkeypatch.setattr(
        service_module,
        "assess_daily_technical_interpretation",
        run_assessment,
    )
    monkeypatch.setattr(
        service_module,
        "derive_daily_technical_strategy",
        run_strategy,
    )
    monkeypatch.setattr(
        service_module,
        "DailyTechnicalStrategyApplicationResponse",
        UnexpectedResponseFactory,
    )

    with pytest.raises(RuntimeError) as raised:
        asyncio.run(service.execute(DailyTechnicalStrategyApplicationRequest(verified)))

    assert raised.value is error
    assert calls == expected_calls
    assert response_calls == []
