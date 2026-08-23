"""Focused tests for the bounded Daily Technical Strategy Agent response."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_platform.agent_exposure import (
    DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION,
    DailyTechnicalStrategyAgentResponseProjection,
)
from market_platform.agent_exposure import (
    daily_technical_strategy_response as response_module,
)
from market_platform.application import (
    DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION,
    DailyTechnicalStrategyApplicationResponse,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalAssessmentPolicy,
    ClassicDailyTechnicalInterpretationPolicy,
    ClassicDailyTechnicalStrategyPolicy,
)
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessment,
    DailyTechnicalAssessmentFinding,
    DailyTechnicalAssessmentFindingKind,
    DailyTechnicalAssessmentOutcome,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
    DailyTechnicalExtensionState,
    DailyTechnicalInterpretation,
)
from market_platform.research.daily_technical_strategy import (
    DailyTechnicalStrategy,
    DailyTechnicalStrategyMode,
    DailyTechnicalStrategyRuleCode,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.research.technical_analysis import (
    TechnicalAnalysisQuality,
    TechnicalAnalysisWarning,
)
from market_platform.research.technical_policy import TechnicalPolicyIdentity
from market_platform.trading import TradingInstrumentIdentity


def _fingerprint(character: str) -> str:
    return f"sha256:{character * 64}"


def _validated_application_response() -> DailyTechnicalStrategyApplicationResponse:
    analysis_as_of = datetime(2026, 8, 10, tzinfo=UTC)
    canonical_instrument_id = CanonicalInstrumentId("test.security")
    interpretation = DailyTechnicalInterpretation(
        canonical_instrument_id=canonical_instrument_id,
        requested_trading_identity=TradingInstrumentIdentity("TEST", "NASDAQ"),
        analysis_as_of=analysis_as_of,
        source_technical_analysis_snapshot_fingerprint=_fingerprint("b"),
        source_daily_instrument_integrity_evidence_fingerprint=_fingerprint("c"),
        interpretation_policy_identity=(
            ClassicDailyTechnicalInterpretationPolicy().identity
        ),
        source_quality=TechnicalAnalysisQuality.DEGRADED,
        source_warnings=(TechnicalAnalysisWarning.STALE_EVIDENCE,),
        trend_direction=DailyTechnicalDirectionalState.POSITIVE,
        momentum_direction=DailyTechnicalDirectionalState.MIXED,
        volatility_state=VolatilityState.HIGH,
        extension_state=DailyTechnicalExtensionState.ABOVE_REFERENCE_BAND,
        comparison_evidence=(),
    )
    assessment = DailyTechnicalAssessment(
        canonical_instrument_id=canonical_instrument_id,
        analysis_as_of=analysis_as_of,
        source_interpretation_fingerprint=interpretation.fingerprint,
        assessment_policy_identity=ClassicDailyTechnicalAssessmentPolicy().identity,
        outcome=DailyTechnicalAssessmentOutcome.CAUTION,
        findings=(
            DailyTechnicalAssessmentFinding(
                kind=DailyTechnicalAssessmentFindingKind.CAUTION,
                code="extended_above_reference_band",
                comparison_evidence_ids=(),
            ),
        ),
    )
    strategy = DailyTechnicalStrategy(
        canonical_instrument_id=canonical_instrument_id,
        analysis_as_of=analysis_as_of,
        source_assessment_fingerprint=assessment.fingerprint,
        strategy_policy_identity=(
            ClassicDailyTechnicalStrategyPolicy().policy_identity
        ),
        mode=DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
        rule_code=DailyTechnicalStrategyRuleCode.CAUTION_NO_ACTIVE_STRATEGY,
    )
    response = object.__new__(DailyTechnicalStrategyApplicationResponse)
    object.__setattr__(
        response, "application_request_fingerprint", _fingerprint("a")
    )
    object.__setattr__(response, "interpretation", interpretation)
    object.__setattr__(response, "assessment", assessment)
    object.__setattr__(response, "strategy", strategy)
    object.__setattr__(
        response,
        "schema_version",
        DAILY_TECHNICAL_STRATEGY_APPLICATION_RESPONSE_SCHEMA_VERSION,
    )
    response._validate()
    return response


def test_projection_contract_is_exact_versioned_frozen_and_slotted() -> None:
    factory = DailyTechnicalStrategyAgentResponseProjection.from_application_response
    projection = factory(_validated_application_response())

    assert DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION == (
        "daily_technical_strategy_agent_response_projection/v1"
    )
    assert projection.schema_version == (
        DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION
    )
    assert [item.name for item in fields(projection)] == [
        "application_request_fingerprint",
        "canonical_instrument_id",
        "requested_symbol",
        "requested_venue",
        "analysis_as_of",
        "source_technical_analysis_snapshot_fingerprint",
        "source_daily_instrument_integrity_evidence_fingerprint",
        "interpretation_fingerprint",
        "assessment_fingerprint",
        "strategy_fingerprint",
        "interpretation_policy_id",
        "interpretation_policy_behavioral_revision",
        "interpretation_policy_identity_fingerprint",
        "assessment_policy_id",
        "assessment_policy_behavioral_revision",
        "assessment_policy_identity_fingerprint",
        "strategy_policy_id",
        "strategy_policy_behavioral_revision",
        "strategy_policy_identity_fingerprint",
        "source_quality",
        "source_warnings",
        "trend_direction",
        "momentum_direction",
        "volatility_state",
        "extension_state",
        "assessment_outcome",
        "assessment_finding_codes",
        "strategy_mode",
        "strategy_rule_code",
        "schema_version",
    ]
    assert not hasattr(projection, "__dict__")
    with pytest.raises(FrozenInstanceError):
        projection.strategy_mode = "changed"  # type: ignore[misc]


def test_projection_preserves_request_binding_and_domain_lineage() -> None:
    response = _validated_application_response()
    factory = DailyTechnicalStrategyAgentResponseProjection.from_application_response
    projection = factory(response)

    assert projection.application_request_fingerprint == (
        response.application_request_fingerprint
    )
    assert projection.source_technical_analysis_snapshot_fingerprint == (
        response.interpretation.source_technical_analysis_snapshot_fingerprint
    )
    assert projection.source_daily_instrument_integrity_evidence_fingerprint == (
        response.interpretation.source_daily_instrument_integrity_evidence_fingerprint
    )
    assert projection.interpretation_fingerprint == response.interpretation.fingerprint
    assert projection.assessment_fingerprint == response.assessment.fingerprint
    assert projection.strategy_fingerprint == response.strategy.fingerprint


def test_projection_retains_bounded_policy_profile_provenance() -> None:
    response = _validated_application_response()
    projection = (
        DailyTechnicalStrategyAgentResponseProjection.from_application_response(
            response
        )
    )

    policy_provenance = (
        (
            "interpretation",
            response.interpretation.interpretation_policy_identity,
        ),
        ("assessment", response.assessment.assessment_policy_identity),
        ("strategy", response.strategy.strategy_policy_identity),
    )
    for stage, identity in policy_provenance:
        assert getattr(projection, f"{stage}_policy_id") == identity.policy_id
        assert getattr(
            projection, f"{stage}_policy_behavioral_revision"
        ) == identity.behavioral_revision
        assert getattr(
            projection, f"{stage}_policy_identity_fingerprint"
        ) == identity.fingerprint


def test_projection_exposes_only_flattened_descriptive_intelligence() -> None:
    response = _validated_application_response()
    factory = DailyTechnicalStrategyAgentResponseProjection.from_application_response
    projection = factory(response)

    assert projection.canonical_instrument_id == "test.security"
    assert projection.requested_symbol == "TEST"
    assert projection.requested_venue == "NASDAQ"
    assert projection.analysis_as_of == datetime(2026, 8, 10, tzinfo=UTC)
    assert projection.source_quality == "degraded"
    assert projection.source_warnings == ("stale_evidence",)
    assert projection.trend_direction == "positive"
    assert projection.momentum_direction == "mixed"
    assert projection.volatility_state == "high"
    assert projection.extension_state == "above_reference_band"
    assert projection.assessment_outcome == "caution"
    assert projection.assessment_finding_codes == (
        "extended_above_reference_band",
    )
    assert projection.strategy_mode == "no_active_strategy"
    assert projection.strategy_rule_code == "caution_no_active_strategy"


def test_projection_retains_no_source_graph_or_forbidden_fingerprint_family() -> None:
    factory = DailyTechnicalStrategyAgentResponseProjection.from_application_response
    projection = factory(_validated_application_response())
    field_names = {item.name for item in fields(projection)}

    assert {
        "verified_research",
        "raw_market_data",
        "registry",
        "integrity",
        "interpretation",
        "assessment",
        "strategy",
        "comparison_evidence",
        "policy_identity",
        "policy_configuration",
        "configuration",
        "response_fingerprint",
        "aggregate_fingerprint",
        "exposure_fingerprint",
        "fingerprint",
    }.isdisjoint(field_names)
    assert all(
        not isinstance(
            value,
            (
                DailyTechnicalInterpretation,
                DailyTechnicalAssessment,
                DailyTechnicalStrategy,
                DailyTechnicalStrategyApplicationResponse,
                TechnicalPolicyIdentity,
            ),
        )
        for value in (
            getattr(projection, item.name) for item in fields(projection)
        )
    )
    assert not hasattr(projection, "to_dict")
    assert not hasattr(projection, "from_dict")


def test_projection_requires_an_exact_validated_application_response() -> None:
    with pytest.raises(
        TypeError,
        match="exact DailyTechnicalStrategyApplicationResponse",
    ):
        DailyTechnicalStrategyAgentResponseProjection.from_application_response(  # type: ignore[arg-type]
            object()
        )

    response = _validated_application_response()
    object.__setattr__(response, "schema_version", "forged/v1")
    with pytest.raises(ValueError, match="application response schema is invalid"):
        DailyTechnicalStrategyAgentResponseProjection.from_application_response(
            response
        )


def test_projection_is_factory_only_and_exports_no_private_helper() -> None:
    with pytest.raises(TypeError, match="factory-created"):
        DailyTechnicalStrategyAgentResponseProjection()

    assert response_module.__all__ == [
        "DAILY_TECHNICAL_STRATEGY_AGENT_RESPONSE_PROJECTION_SCHEMA_VERSION",
        "DailyTechnicalStrategyAgentResponseProjection",
    ]
    assert all(not name.startswith("_") for name in response_module.__all__)


def test_projection_depends_only_on_the_application_response_boundary() -> None:
    source_path = Path(inspect.getfile(DailyTechnicalStrategyAgentResponseProjection))
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    market_platform_imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("market_platform")
    }

    assert market_platform_imports == {
        "market_platform.application.daily_technical_strategy"
    }
