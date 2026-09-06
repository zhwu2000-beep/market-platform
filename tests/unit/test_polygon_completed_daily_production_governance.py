from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC

import pandas as pd
import pytest

import market_platform.application as application
import market_platform.evidence as evidence
from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_governance as governance,
)
from market_platform.evidence import authorization as evidence_authorization
from market_platform.evidence.policy import EvidenceAdmissionRuleSet
from market_platform.evidence.temporal import EvidenceFreshnessRule
from market_platform.evidence.validation import EvidenceValidationConcern
from market_platform.evidence_ingress import polygon_completed_daily_ohlcv as ingress
from market_platform.research.technical_analysis import (
    construct_daily_technical_analysis_profile,
)

PROFILE = governance._POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
CATALOG = governance._PRODUCTION_GOVERNANCE_APPROVAL_CATALOG
SCOPE = "research.daily_technical.completed_daily"
VERSION = "1.0.0"
EXPECTED_PROFILE_FINGERPRINT = (
    "sha256:6bff0d17036920f657e44816f434ca357c803d99d77a06bd877b3c00aa64036f"
)


def _with_configuration(definition, name: str, value):
    configuration = tuple(
        (key, value if key == name else retained)
        for key, retained in definition.configuration
    )
    return replace(definition, configuration=configuration)


def _ruleset_without_source_quality() -> EvidenceAdmissionRuleSet:
    ruleset = PROFILE.admission_ruleset
    requirements = tuple(
        item
        for item in ruleset.mandatory_validation_requirements
        if item.concern is not EvidenceValidationConcern.SOURCE_QUALITY
    )
    return EvidenceAdmissionRuleSet(
        ruleset.ruleset_id,
        ruleset.ruleset_version,
        ruleset.admission_scope,
        requirements,
        True,
        ruleset.admission_freshness_rule,
        True,
        ruleset.task_freshness_rule,
        True,
    )


def _unapproved_construction_authorization():
    approved = PROFILE.construction_authorization
    return evidence_authorization._create_evidence_contract_authorization_record(
        authorization_id="production.polygon_completed_daily_ohlcv.lookalike",
        authorization_version=VERSION,
        contract_definition=approved.contract_definition,
        authorized_source=approved.authorized_source,
        authority=approved.authority,
    )


def test_exact_profile_identity_scope_and_closed_membership() -> None:
    resolved = governance._resolve_approved_polygon_completed_daily_production_profile(
        PROFILE
    )

    assert PROFILE.profile_id == "production.polygon_completed_daily.daily_technical"
    assert PROFILE.profile_version == VERSION
    assert PROFILE.scope == SCOPE
    assert CATALOG.profiles == (PROFILE,)
    assert resolved == PROFILE
    assert resolved is not PROFILE


def test_exact_eight_validation_definitions_and_source_quality_floor() -> None:
    expected = {
        concern: f"production.polygon_completed_daily.validation.{concern.value}"
        for concern in EvidenceValidationConcern
    }
    actual = {
        item.requirement.concern: item.requirement.ruleset_id
        for item in PROFILE.validation_definitions
    }

    assert actual == expected
    assert len(actual) == 8
    assert all(
        item.requirement.ruleset_version == VERSION and item.requirement.scope == SCOPE
        for item in PROFILE.validation_definitions
    )
    assert set(PROFILE.admission_ruleset.mandatory_validation_concerns) == set(
        EvidenceValidationConcern
    )
    source_quality = next(
        item
        for item in PROFILE.validation_definitions
        if item.requirement.concern is EvidenceValidationConcern.SOURCE_QUALITY
    )
    assert "retained_material_nonempty" in source_quality.semantic_requirements
    assert "ohlc_strictly_positive" in source_quality.semantic_requirements
    assert "minimum_history_for_complete_technical_analysis" in (
        source_quality.exclusions
    )


def test_ruleset_and_distinct_equal_configuration_freshness_are_exact() -> None:
    ruleset = PROFILE.admission_ruleset
    admission = PROFILE.admission_freshness
    task = PROFILE.task_freshness

    assert ruleset.ruleset_id == (
        "production.polygon_completed_daily.admission.daily_technical"
    )
    assert ruleset.ruleset_version == VERSION
    assert ruleset.admission_scope == SCOPE
    assert ruleset.admission_freshness_required
    assert ruleset.task_freshness_required
    assert ruleset.active_validity_required
    assert admission.rule.rule_id == (
        "production.polygon_completed_daily.freshness.admission"
    )
    assert task.rule.rule_id == (
        "production.polygon_completed_daily.freshness.daily_technical"
    )
    assert admission.rule != task.rule
    assert admission._configuration_payload() == task._configuration_payload()
    assert admission.get("market_timezone") == "America/New_York"
    assert admission.get("minimum_calendar_lag_days") == 1
    assert admission.get("maximum_calendar_lag_days") == 4
    assert admission.get("maximum_lag_inclusive") is True
    assert admission.get("expected_session_calendar") is None
    assert admission.get("publication_time_inference") == "prohibited"
    assert admission.get("holiday_exception_extension") is None
    assert str(admission.get("predicate_semantics")).startswith(
        "recency_not_exchange_session_completeness"
    )
    assert "canonical_lifecycle_consumability" in admission.get("excluded_decisions")


def test_existing_construction_authorization_and_producer_are_unchanged() -> None:
    authorization = PROFILE.construction_authorization

    assert authorization == (
        evidence_authorization._POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION
    )
    assert authorization.authorization_id == "production.polygon_completed_daily_ohlcv"
    assert authorization.authorization_version == VERSION
    assert authorization.fingerprint == (
        "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
    )
    assert PROFILE.construction_producer == ingress._PRODUCER


def test_validity_consumer_analysis_and_use_definitions_are_exact() -> None:
    released = construct_daily_technical_analysis_profile()

    assert PROFILE.initial_validity.definition_id == (
        "production.polygon_completed_daily.validity.initial_active"
    )
    assert PROFILE.initial_validity.definition_version == VERSION
    assert "authentic_admitted_prerequisite" in PROFILE.initial_validity.get(
        "semantic_requirements"
    )
    assert "no_automatic_reactivation_of_terminal_validity" in (
        PROFILE.initial_validity.get("semantic_requirements")
    )
    assert PROFILE.consumer.definition_id == "market_platform.research.daily_technical"
    assert PROFILE.consumer.definition_version == VERSION
    assert PROFILE.analysis_profile.definition_id == "daily_technical_analysis_default"
    assert PROFILE.analysis_profile.get("profile_fingerprint") == released.fingerprint
    assert released.fingerprint == (
        "sha256:c2f1ccd7f9cfa51281c07cec7f62ac43940a72c6af1f8d162f9c8fbf97af78f7"
    )
    assert PROFILE.use.definition_id == (
        "production.polygon_completed_daily.use.daily_technical"
    )
    assert PROFILE.use.definition_version == VERSION
    assert PROFILE.use.get("consumer_definition_fingerprint") == (
        PROFILE.consumer.fingerprint
    )
    assert PROFILE.use.get("analysis_profile_definition_fingerprint") == (
        PROFILE.analysis_profile.fingerprint
    )
    assert "canonical_EvidenceAdmissionState.is_consumable" in PROFILE.use.get(
        "semantic_requirements"
    )
    assert "end_to_end_no_drop_correspondence" in PROFILE.use.get(
        "semantic_requirements"
    )


def test_bridge_definition_and_datetime64_runtime_bounds_are_exact() -> None:
    transformation = PROFILE.transformation

    assert transformation.definition_id == (
        "production.polygon_completed_daily.transform.completed_daily_price_series"
    )
    assert transformation.definition_version == VERSION
    assert transformation.get("input_material_schema_fingerprint") == (
        PROFILE.construction_authorization.contract_definition.material_schema.fingerprint
    )
    assert transformation.get("input_semantics") == (
        "entire_retained_polygon_completed_daily_ohlcv_material_v1"
    )
    assert transformation.get("output_type") == (
        "market_platform.research.daily_evidence.CompletedDailyPriceSeries"
    )
    assert transformation.get("supported_first_date") == "1677-09-22"
    assert transformation.get("supported_last_date") == "2262-04-11"
    assert transformation.get("rounding_mode") == "round_to_nearest_ties_to_even"
    assert transformation.get("zero_volume_result") == "positive_zero"
    assert transformation.get("subset_selection_authorized") is False
    assert transformation.get("no_drop_basis") == "retained_governed_material"
    assert "unsupported_subnormal" in transformation.get("refusal_conditions")
    assert "imputation" in transformation.get("prohibited_operations")

    for boundary in ("1677-09-22", "2262-04-11"):
        result = pd.Series(
            [pd.Timestamp(boundary, tz=UTC)], dtype="datetime64[ns, UTC]"
        )
        assert result.iloc[0].date().isoformat() == boundary
    for outside in ("1677-09-21", "2262-04-12"):
        with pytest.raises(pd.errors.OutOfBoundsDatetime):
            pd.Series([pd.Timestamp(outside, tz=UTC)], dtype="datetime64[ns, UTC]")


def test_aggregate_fingerprint_is_deterministic_and_canonical() -> None:
    resolved = CATALOG.resolve(replace(PROFILE))

    assert PROFILE.fingerprint == EXPECTED_PROFILE_FINGERPRINT
    assert PROFILE.fingerprint == canonical_fingerprint(PROFILE._fingerprint_payload())
    assert resolved.fingerprint == PROFILE.fingerprint
    assert resolved.to_dict() == PROFILE.to_dict()


def test_changed_threshold_with_matching_name_and_version_is_not_approved() -> None:
    admission = _with_configuration(
        PROFILE.admission_freshness, "maximum_calendar_lag_days", 5
    )
    task = _with_configuration(PROFILE.task_freshness, "maximum_calendar_lag_days", 5)
    candidate = replace(PROFILE, admission_freshness=admission, task_freshness=task)

    assert candidate.profile_id == PROFILE.profile_id
    assert candidate.profile_version == PROFILE.profile_version
    assert candidate.fingerprint != PROFILE.fingerprint
    with pytest.raises(ValueError, match="not approved"):
        CATALOG.resolve(candidate)


def test_omitted_source_quality_is_not_approved() -> None:
    definitions = tuple(
        item
        for item in PROFILE.validation_definitions
        if item.requirement.concern is not EvidenceValidationConcern.SOURCE_QUALITY
    )
    candidate = replace(
        PROFILE,
        validation_definitions=definitions,
        admission_ruleset=_ruleset_without_source_quality(),
    )

    assert len(candidate.validation_definitions) == 7
    with pytest.raises(ValueError, match="not approved"):
        CATALOG.resolve(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        replace(PROFILE, scope="research.daily_technical.lookalike"),
        replace(
            PROFILE,
            consumer=replace(
                PROFILE.consumer,
                definition_id="market_platform.research.daily_technical.lookalike",
            ),
        ),
        replace(
            PROFILE,
            analysis_profile=_with_configuration(
                PROFILE.analysis_profile,
                "profile_fingerprint",
                "sha256:" + ("0" * 64),
            ),
        ),
        replace(
            PROFILE,
            transformation=_with_configuration(
                PROFILE.transformation,
                "date_conversion",
                "canonical_session_date_to_midnight_local",
            ),
        ),
        replace(
            PROFILE,
            construction_authorization=_unapproved_construction_authorization(),
        ),
        replace(
            PROFILE,
            initial_validity=_with_configuration(
                PROFILE.initial_validity,
                "semantic_requirements",
                ("admission_implies_active",),
            ),
        ),
    ],
    ids=(
        "scope",
        "consumer",
        "analysis_profile",
        "transformation",
        "construction_authorization",
        "initial_validity",
    ),
)
def test_changed_constituent_is_not_approved(candidate) -> None:
    with pytest.raises(ValueError, match="not approved"):
        CATALOG.resolve(candidate)


def test_changed_validation_quality_or_freshness_identity_is_not_approved() -> None:
    identity = next(
        item
        for item in PROFILE.validation_definitions
        if item.requirement.concern is EvidenceValidationConcern.IDENTITY
    )
    changed_rule = replace(
        identity,
        requirement=replace(
            identity.requirement,
            ruleset_id="production.polygon_completed_daily.validation.identity.lookalike",
        ),
    )
    source_quality = next(
        item
        for item in PROFILE.validation_definitions
        if item.requirement.concern is EvidenceValidationConcern.SOURCE_QUALITY
    )
    changed_quality = replace(
        source_quality,
        semantic_requirements=source_quality.semantic_requirements
        + ("expected_exchange_session_completeness",),
    )
    changed_freshness = replace(
        PROFILE.task_freshness,
        rule=EvidenceFreshnessRule(
            "production.polygon_completed_daily.freshness.lookalike",
            VERSION,
            PROFILE.task_freshness.rule.declared_temporal_anchor,
            SCOPE,
        ),
    )

    for old, new, field in (
        (identity, changed_rule, "validation_definitions"),
        (source_quality, changed_quality, "validation_definitions"),
    ):
        definitions = tuple(
            new if item is old else item for item in PROFILE.validation_definitions
        )
        with pytest.raises(ValueError, match="not approved"):
            CATALOG.resolve(replace(PROFILE, **{field: definitions}))
    with pytest.raises(ValueError, match="not approved"):
        CATALOG.resolve(replace(PROFILE, task_freshness=changed_freshness))


def test_no_lifecycle_or_research_execution_and_no_public_authority() -> None:
    lifecycle_types = (
        evidence.EvidenceValidationRecord,
        evidence.EvidenceFreshnessEvaluationRecord,
        evidence.EvidenceAdmissionRecord,
        evidence.EvidenceValidityEvent,
        evidence.EvidenceAdmissionState,
    )
    source = inspect.getsource(governance)
    forbidden_calls = {
        "create_evidence_validation_record",
        "create_evidence_freshness_evaluation_record",
        "create_evidence_admission_record",
        "create_evidence_validity_event",
        "evaluate_evidence_admission_as_of",
        "prepare_completed_daily_price_series",
        "analyze_daily_technical_snapshot",
    }

    assert not any(
        isinstance(value, lifecycle_types) for value in vars(governance).values()
    )
    assert all(name not in source for name in forbidden_calls)
    assert governance.__all__ == []
    assert not hasattr(application, "register_production_governance_profile")
    assert not hasattr(application, "create_production_governance_profile")
    assert tuple(evidence.__all__) == tuple(dict.fromkeys(evidence.__all__))
    assert len(evidence.__all__) == 69
