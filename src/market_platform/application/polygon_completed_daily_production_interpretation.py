"""Trusted retained Polygon technical occurrence to governed Interpretation."""

from __future__ import annotations

import json
import math
from _thread import LockType
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from threading import Lock, get_ident
from types import GetSetDescriptorType, MemberDescriptorType
from typing import Any
from uuid import uuid4

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_evidence_candidate as _support_candidate,
)
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_bridge as _support_bridge,
)
from market_platform.application import (
    polygon_completed_daily_production_construction as _support_construction,
)
from market_platform.application import (
    polygon_completed_daily_production_freshness as _support_freshness,
)
from market_platform.application import (
    polygon_completed_daily_production_governance as _support_governance,
)
from market_platform.application import (
    polygon_completed_daily_production_qualification as _support_qualification,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.application import (
    polygon_completed_daily_production_validation as _support_app_validation,
)
from market_platform.application import (
    polygon_completed_daily_production_validity as _support_app_validity,
)
from market_platform.data import historical as _historical
from market_platform.evidence import EvidenceArtifactReference, EvidenceSubjectReference
from market_platform.evidence import admission as _support_admission
from market_platform.evidence import authorization as _support_authorization
from market_platform.evidence import classification as _support_classification
from market_platform.evidence import models as _support_models
from market_platform.evidence import policy as _support_policy
from market_platform.evidence import references as _support_references
from market_platform.evidence import temporal as _support_temporal
from market_platform.evidence import validation as _support_validation
from market_platform.evidence import validity as _support_validity
from market_platform.evidence_ingress import (
    polygon_completed_daily_ohlcv as _support_ohlcv,
)
from market_platform.instruments import identity as _support_identity
from market_platform.instruments import mapping as _support_mapping
from market_platform.instruments import resolver as _support_resolver
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
)
from market_platform.research import daily_evidence as _support_daily_evidence
from market_platform.research import governed_daily_technical_interpretation as domain
from market_platform.research import interpretation as _support_research_interpretation
from market_platform.research import technical_analysis as _support_technical_analysis
from market_platform.research.governed_daily_technical_interpretation import (
    GovernedDailyTechnicalInterpretation,
    PolygonCompletedDailyInterpretationRequest,
)
from market_platform.research.technical_policy import (
    ClassicDailyTechnicalInterpretationConfiguration,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

_INTERPRETATION_SUPPORT_FIELDS: dict[type[Any], tuple[str, ...]] = {
    _support_candidate.PolygonCompletedDailyEvidenceCandidateApplicationRequest: (
        "external_identity",
        "mappings",
        "requested_from",
        "requested_to",
        "query_as_of",
    ),
    a.PolygonCompletedDailyAdmissionExecutionCompanion: (
        "execution_id",
        "history_sequence",
        "history_namespace_id",
        "operation",
        "deciding_actor",
        "deciding_capability",
        "executor",
        "production_profile_reference",
        "production_profile_fingerprint",
        "artifact_reference",
        "material_fingerprint",
        "construction_history_namespace_id",
        "construction_history_sequence",
        "construction_execution_id",
        "construction_receipt_fingerprint",
        "admission_ruleset_reference",
        "selected_validation_record_references",
        "selected_validation_execution_references",
        "admission_freshness_evaluation_reference",
        "admission_freshness_execution_references",
        "prerequisite_knowledge_as_of",
        "prerequisite_history_fingerprint",
        "admission_record_reference",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "schema_version",
        "fingerprint",
    ),
    a.PolygonCompletedDailyAdmissionExecutionReference: (
        "admission_record_reference",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "construction_execution_id",
        "available_at",
        "companion_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    a.PolygonCompletedDailyFreshnessExecutionReference: (
        "freshness_evaluation_reference",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "available_at",
        "companion_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    a.PolygonCompletedDailyProductionAdmissionResult: (
        "construction_result",
        "admission_record",
        "companion",
        "_prerequisites",
    ),
    a.PolygonCompletedDailyValidationExecutionReference: (
        "validation_record_reference",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "available_at",
        "companion_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    a._AdmissionPrerequisites: (
        "construction_result",
        "validation_records",
        "validation_execution_references",
        "freshness_record",
        "freshness_execution_references",
        "knowledge_as_of",
        "history_fingerprint",
        "validation_histories",
        "freshness_history",
    ),
    _support_bridge.PolygonCompletedDailyBridgeResult: (
        "qualification",
        "completed_prices",
        "_expected",
        "dataset_fingerprint",
        "no_drop_proof_fingerprint",
        "target_row_date_fingerprint",
        "execution_id",
        "history_sequence",
        "history_namespace_id",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "fingerprint",
    ),
    _support_bridge._ConvertedRow: ("session_date", "timestamp", "source", "values"),
    _support_construction.PolygonCompletedDailyConstructionExecutionReceipt: (
        "execution_id",
        "history_sequence",
        "history_namespace_id",
        "operation",
        "executor",
        "production_profile_fingerprint",
        "request_fingerprint",
        "construction_authorization",
        "resolved_mapping_fingerprint",
        "artifact_reference",
        "material_fingerprint",
        "result_content_fingerprint",
        "execution_started_at",
        "response_received_at",
        "artifact_created_at",
        "execution_completed_at",
        "available_at",
        "schema_version",
        "fingerprint",
    ),
    _support_construction.PolygonCompletedDailyProductionConstructionResult: (
        "request",
        "candidate_result",
        "receipt",
    ),
    _support_freshness.PolygonCompletedDailyFreshnessExecutionCompanion: (
        "execution_id",
        "history_sequence",
        "history_namespace_id",
        "execution_kind",
        "operation",
        "executor",
        "production_profile_reference",
        "production_profile_fingerprint",
        "construction_history_namespace_id",
        "construction_history_sequence",
        "construction_execution_id",
        "construction_receipt_fingerprint",
        "artifact_reference",
        "material_fingerprint",
        "freshness_rule",
        "freshness_definition_fingerprint",
        "governance_scope",
        "observation_period_start",
        "observation_period_end",
        "evaluation_as_of",
        "new_york_evaluation_date",
        "retained_material_row_count",
        "first_retained_session_date",
        "latest_retained_session_date",
        "eligible_completed_session_count",
        "latest_eligible_completed_session_date",
        "calendar_lag_days",
        "outcome",
        "freshness_evaluation_reference",
        "result",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "schema_version",
        "fingerprint",
    ),
    _support_freshness.PolygonCompletedDailyProductionFreshnessResult: (
        "construction_result",
        "freshness_record",
        "companion",
    ),
    _support_governance._ClosedDefinition: (
        "definition_kind",
        "definition_id",
        "definition_version",
        "scope",
        "configuration",
        "schema_version",
        "fingerprint",
    ),
    _support_governance._FreshnessRuleDefinition: (
        "rule",
        "configuration",
        "schema_version",
        "fingerprint",
    ),
    _support_governance._ProductionGovernanceProfile: (
        "profile_id",
        "profile_version",
        "scope",
        "construction_authorization",
        "construction_producer",
        "validation_definitions",
        "admission_ruleset",
        "admission_freshness",
        "task_freshness",
        "initial_validity",
        "consumer",
        "use",
        "analysis_profile",
        "transformation",
        "schema_version",
        "fingerprint",
    ),
    _support_governance._ValidationRuleDefinition: (
        "requirement",
        "semantic_requirements",
        "exclusions",
        "schema_version",
        "fingerprint",
    ),
    _support_qualification.PolygonCompletedDailyQualifiedUse: (
        "execution_id",
        "history_sequence",
        "history_namespace_id",
        "construction_result",
        "production_profile",
        "analysis_as_of",
        "effective_as_of",
        "knowledge_as_of",
        "task_freshness_result",
        "canonical_state",
        "history_context",
        "mapping_context_fingerprint",
        "all_row_mapping_covered",
        "whole_material_completed",
        "original_row_count",
        "original_ordered_dates",
        "original_row_date_fingerprint",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "fingerprint",
    ),
    _support_qualification._TrustedHistory: (
        "constructions",
        "validations",
        "freshness",
        "admissions",
        "validity",
        "knowledge_as_of",
        "namespaces",
    ),
    t.PolygonCompletedDailyTechnicalRequest: (
        "artifact_reference",
        "bridge_history_namespace_id",
        "bridge_history_sequence",
        "bridge_execution_id",
        "bridge_fingerprint",
    ),
    t.PolygonCompletedDailyTechnicalResult: (
        "source",
        "snapshot",
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "fingerprint",
    ),
    t._SourceLineage: (
        "bridge_reference",
        "construction_execution_id",
        "construction_receipt_fingerprint",
        "qualification_execution_id",
        "qualification_history_namespace_id",
        "qualification_history_sequence",
        "qualification_fingerprint",
        "source_material_fingerprint",
        "dataset_fingerprint",
        "no_drop_proof_fingerprint",
        "row_date_fingerprint",
        "evidence",
        "qualification_knowledge_as_of",
        "bridge_available_at",
    ),
    _support_app_validation.PolygonCompletedDailyProductionValidationResult: (
        "construction_result",
        "validation_record",
        "companion",
    ),
    _support_app_validation.PolygonCompletedDailyValidationExecutionCompanion: (
        "execution_id",
        "history_sequence",
        "history_namespace_id",
        "operation",
        "executor",
        "validator",
        "validator_capability",
        "production_profile_reference",
        "production_profile_fingerprint",
        "validation_requirement",
        "validation_definition_fingerprint",
        "construction_history_namespace_id",
        "construction_history_sequence",
        "construction_execution_id",
        "construction_receipt_fingerprint",
        "construction_result_content_fingerprint",
        "artifact_reference",
        "material_fingerprint",
        "request_fingerprint",
        "resolved_mapping_fingerprint",
        "construction_authorization_fingerprint",
        "trusted_support_fingerprint",
        "validation_reference",
        "disposition",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "schema_version",
        "fingerprint",
    ),
    _support_app_validity.PolygonCompletedDailyProductionValidityResult: (
        "admission_result",
        "validity_event",
        "companion",
        "_admission_history",
    ),
    _support_app_validity.PolygonCompletedDailyValidityExecutionCompanion: (
        "execution_id",
        "history_namespace_id",
        "history_sequence",
        "operation",
        "actor",
        "capability",
        "executor",
        "production_profile_reference",
        "production_profile_fingerprint",
        "artifact_reference",
        "construction_execution_id",
        "construction_receipt_fingerprint",
        "admission_execution_reference",
        "admission_history_fingerprint",
        "prior_validity_references",
        "prior_validity_history_fingerprint",
        "validity_reference",
        "execution_started_at",
        "execution_completed_at",
        "available_at",
        "schema_version",
        "fingerprint",
    ),
    _support_admission.EvidenceAdmissionRecord: (
        "admission_record_id",
        "artifact_reference",
        "admission_ruleset_reference",
        "admission_scope",
        "selected_validation_record_references",
        "admission_freshness_evaluation_reference",
        "deciding_actor_identity",
        "deciding_capability_identity",
        "predecessor_admission_record_reference",
        "disposition",
        "recorded_at",
        "effective_at",
        "findings",
        "schema_version",
        "fingerprint",
    ),
    _support_admission.EvidenceAdmissionRecordReference: (
        "admission_record_id",
        "artifact_reference",
        "admission_scope",
        "admission_ruleset_reference",
        "disposition",
        "admission_record_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_admission.EvidenceAdmissionState: (
        "artifact_reference",
        "admission_scope",
        "knowledge_as_of",
        "effective_as_of",
        "ruleset_reference",
        "required_validation_concerns",
        "required_validation_requirements",
        "admission_freshness_required",
        "task_freshness_required",
        "active_validity_required",
        "admission_freshness_rule_fingerprint",
        "task_freshness_rule_fingerprint",
        "disposition",
        "selected_validation_record_references",
        "admission_freshness_evaluation_reference",
        "task_freshness_evaluation_reference",
        "selected_admission_record_reference",
        "selected_validity_reference",
        "resolved_validation_supersession_references",
        "resolved_admission_predecessor_references",
        "resolved_validity_predecessor_references",
        "findings",
        "schema_version",
    ),
    _support_authorization.EvidenceContractAuthorization: (
        "authorization_id",
        "authorization_version",
        "contract_definition",
        "authorized_source",
        "authority",
        "schema_version",
        "fingerprint",
    ),
    _support_authorization.EvidenceContractDefinition: (
        "governing_contract",
        "evidence_type",
        "information_class",
        "material_schema",
        "schema_version",
        "fingerprint",
    ),
    _support_authorization.EvidenceMaterialSchemaReference: (
        "schema_id",
        "schema_version_id",
        "schema_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_models.EvidenceArtifact: (
        "artifact_id",
        "artifact_version",
        "evidence_type",
        "information_class",
        "subjects",
        "authority",
        "temporal_identity",
        "provenance",
        "governing_contract",
        "material_schema_version",
        "contract_authorization",
        "material_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_models.EvidenceProvenance: (
        "origin",
        "producer",
        "source_references",
        "transformations",
        "predecessors",
        "schema_version",
        "fingerprint",
    ),
    _support_models.EvidenceTemporalIdentity: (
        "platform_received_at",
        "artifact_created_at",
        "observed_at",
        "observation_period_start",
        "observation_period_end",
        "effective_from",
        "effective_until",
        "published_at",
        "source_revision",
        "schema_version",
        "fingerprint",
    ),
    _support_policy.EvidenceAdmissionRuleSet: (
        "ruleset_id",
        "ruleset_version",
        "admission_scope",
        "mandatory_validation_requirements",
        "admission_freshness_required",
        "admission_freshness_rule",
        "task_freshness_required",
        "task_freshness_rule",
        "active_validity_required",
        "schema_version",
        "fingerprint",
    ),
    _support_policy.EvidenceAdmissionRuleSetReference: (
        "ruleset_id",
        "ruleset_version",
        "admission_scope",
        "ruleset_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_policy.EvidenceValidationRequirement: (
        "concern",
        "scope",
        "ruleset_id",
        "ruleset_version",
        "schema_version",
        "fingerprint",
    ),
    _support_references.EvidenceArtifactReference: (
        "artifact_id",
        "artifact_version",
        "artifact_fingerprint",
        "information_class",
        "authority",
        "schema_version",
        "fingerprint",
    ),
    _support_references.EvidenceContractReference: (
        "namespace",
        "contract_id",
        "contract_version",
        "information_class",
        "contract_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_references.EvidenceIdentityReference: (
        "namespace",
        "identity_id",
        "identity_version",
        "identity_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_references.EvidenceSourceReference: (
        "namespace",
        "source_id",
        "source_version",
        "authority",
        "source_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_references.EvidenceSubjectReference: (
        "namespace",
        "subject_id",
        "subject_version",
        "subject_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_temporal.EvidenceFreshnessEvaluationRecord: (
        "artifact_reference",
        "freshness_rule",
        "evaluation_as_of",
        "evaluated_temporal_values",
        "result",
        "findings",
        "schema_version",
        "fingerprint",
    ),
    _support_temporal.EvidenceFreshnessEvaluationReference: (
        "artifact_reference",
        "freshness_rule_fingerprint",
        "evaluation_scope",
        "evaluation_as_of",
        "result",
        "evaluation_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_temporal.EvidenceFreshnessRule: (
        "rule_id",
        "rule_version",
        "declared_temporal_anchor",
        "evaluation_scope",
        "schema_version",
        "fingerprint",
    ),
    _support_validation.EvidenceValidationRecord: (
        "validation_record_id",
        "artifact_reference",
        "concern",
        "scope",
        "disposition",
        "validator_identity",
        "validator_capability_identity",
        "ruleset_id",
        "ruleset_version",
        "predecessor_validation_record_reference",
        "recorded_at",
        "effective_at",
        "findings",
        "schema_version",
        "fingerprint",
    ),
    _support_validation.EvidenceValidationRecordReference: (
        "validation_record_id",
        "artifact_reference",
        "concern",
        "scope",
        "disposition",
        "ruleset_id",
        "ruleset_version",
        "validation_record_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_validity.EvidenceValidityEvent: (
        "validity_event_id",
        "artifact_reference",
        "status",
        "recorded_at",
        "effective_at",
        "actor_identity",
        "capability_identity",
        "predecessor_validity_event_reference",
        "reason",
        "scope",
        "schema_version",
        "fingerprint",
    ),
    _support_validity.EvidenceValidityReference: (
        "validity_event_id",
        "artifact_reference",
        "status",
        "scope",
        "recorded_at",
        "effective_at",
        "validity_event_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_ohlcv.PolygonCompletedDailyOhlcvEvidenceIngressResult: (
        "material",
        "artifact",
    ),
    _support_ohlcv.PolygonCompletedDailyOhlcvMaterial: (
        "external_instrument_identity",
        "canonical_subject",
        "mapping_resolution_provenance",
        "start_session_date",
        "end_session_date",
        "query_as_of",
        "request_provenance",
        "provider_request_id",
        "rows",
        "schema_version",
        "material_schema",
        "source_reference",
        "vendor_service",
        "api_base",
        "route_template",
        "multiplier",
        "timespan",
        "adjusted",
        "sort",
        "limit",
        "market_timezone",
        "session_scope",
        "price_adjustment",
        "adjusted_response",
        "row_count",
        "fingerprint",
    ),
    _support_ohlcv.PolygonCompletedDailyOhlcvMaterialRow: (
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ),
    _support_ohlcv._PolygonCompletedDailyOhlcvRequestProvenance: (
        "resolved_route",
        "requested_ticker",
        "requested_from",
        "requested_to",
        "schema_version",
        "api_base",
        "multiplier",
        "timespan",
        "adjusted",
        "sort",
        "limit",
    ),
    _support_identity.CanonicalInstrument: (
        "instrument_id",
        "trading_identity",
        "asset_class",
        "trading_currency",
        "schema_version",
        "fingerprint",
    ),
    _support_identity.CanonicalInstrumentId: ("instrument_id",),
    _support_identity.ExternalInstrumentIdentity: (
        "namespace",
        "external_symbol",
        "external_venue",
        "schema_version",
        "fingerprint",
    ),
    _support_identity.InstrumentMappingSourceIdentity: (
        "source_id",
        "source_version",
        "configuration_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_mapping.InstrumentMapping: (
        "external_identity",
        "canonical_instrument",
        "source",
        "valid_from",
        "expires_at",
        "schema_version",
        "fingerprint",
    ),
    _support_resolver.InstrumentResolution: (
        "external_identity",
        "mapping",
        "resolved_as_of",
        "schema_version",
    ),
    _support_daily_evidence.CompletedDailyPriceSeries: ("_prices", "_evidence"),
    _support_daily_evidence.DailyResearchEvidence: (
        "instrument",
        "timeframe",
        "session_scope",
        "market_timezone",
        "adjustment_policy",
        "analysis_as_of",
        "cutoff_session_date",
        "first_used_session_date",
        "latest_completed_bar_session_date",
        "bar_count",
        "excluded_current_session_row_count",
        "calendar_lag_days",
        "provider",
        "dataset_content_fingerprint",
        "schema_version",
        "fingerprint",
    ),
    _support_technical_analysis.DailyTechnicalAnalysisProfile: (
        "profile_id",
        "profile_version",
        "ema_fast_period",
        "ema_slow_period",
        "tunnel_fast_period",
        "tunnel_slow_period",
        "macd_fast_period",
        "macd_slow_period",
        "macd_signal_period",
        "rsi_period",
        "atr_period",
        "minimum_bar_count",
        "stale_after_calendar_days",
        "realized_volatility_low_threshold",
        "realized_volatility_high_threshold",
        "rules_version",
        "schema_version",
        "fingerprint",
    ),
    _support_technical_analysis.ResearchVolatilityReferences: (
        "atr",
        "one_atr_below",
        "one_atr_above",
        "one_and_half_atr_below",
        "one_and_half_atr_above",
        "two_atr_below",
        "two_atr_above",
        "distance_from_ema20_percent",
    ),
    _support_technical_analysis.TechnicalAnalysisSnapshot: (
        "evidence",
        "profile",
        "latest_close",
        "ema_8",
        "ema_20",
        "ema_144",
        "ema_169",
        "ema_alignment",
        "tunnel_position",
        "macd_line",
        "macd_signal",
        "macd_histogram",
        "rsi_14",
        "wilder_atr_14",
        "atr_percent_14",
        "realized_volatility",
        "current_drawdown",
        "trend_state",
        "momentum_state",
        "volatility_state",
        "volatility_references",
        "quality",
        "unavailable",
        "warnings",
        "schema_version",
        "fingerprint",
    ),
    _support_technical_analysis.TechnicalAnalysisUnavailable: (
        "component",
        "reason",
        "required_bars",
        "available_bars",
    ),
    TradingInstrumentIdentity: (
        "symbol",
        "venue",
        "schema_version",
        "instrument_fingerprint",
    ),
}

_INTERPRETATION_SUPPORT_ENUMS = (
    _support_freshness.PolygonCompletedDailyFreshnessExecutionKind,
    _support_freshness.PolygonCompletedDailyFreshnessOutcome,
    _support_admission.EvidenceAdmissionDisposition,
    _support_validation.EvidenceValidationConcern,
    _support_validation.EvidenceValidationDisposition,
    _support_validity.EvidenceValidityStatus,
    _support_identity.InstrumentAssetClass,
    _support_daily_evidence.ResearchTimeframe,
    _support_daily_evidence.DailyAnalysisSessionScope,
    _support_daily_evidence.PriceAdjustmentPolicy,
    _support_technical_analysis.TechnicalAnalysisQuality,
    _support_technical_analysis.TechnicalTrendState,
    _support_technical_analysis.TechnicalMomentumState,
    _support_technical_analysis.EmaAlignment,
    _support_technical_analysis.TunnelPosition,
    _support_technical_analysis.TechnicalAnalysisComponent,
    _support_technical_analysis.TechnicalAnalysisUnavailableReason,
    _support_technical_analysis.TechnicalAnalysisWarning,
    _support_classification.EvidenceAuthority,
    _support_classification.EvidenceInformationClass,
    _support_research_interpretation.VolatilityState,
)

_OPERATION = (
    "production.polygon_completed_daily.daily_technical_interpretation.application"
)
_VERSION = "1.0.0"
_EXECUTOR = (
    "market_platform.application.polygon_completed_daily_production_interpretation/v1"
)
_PREFIX = "polygon_completed_daily_interpretation"


class _InterpretationOccurrenceUnavailable(ValueError):
    """Valid authentic inventory contains no exact selected occurrence."""


class _InterpretationHistoryInvalid(ValueError):
    """Publisher authority, inventory or original historical support is invalid."""


class _InterpretationSourceMismatch(ValueError):
    """Authenticated retained source correspondence differs."""


class PolygonCompletedDailyInterpretationRefusalReason:
    TECHNICAL_UNAVAILABLE = "technical_occurrence_unavailable"
    HISTORY_INVALID = "history_incomplete_or_corrupt"
    SOURCE_MISMATCH = "source_lineage_mismatch"
    SEMANTIC_FAILED = "semantic_execution_or_correspondence_failed"
    TEMPORAL_FAILURE = "temporal_failure"
    PUBLICATION_FAILED = "interpretation_publication_or_copy_failed"


class PolygonCompletedDailyInterpretationRefused(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        if type(message) is not str:
            raise TypeError("exact refusal message string required")
        domain._choice(
            reason,
            (
                "technical_occurrence_unavailable",
                "history_incomplete_or_corrupt",
                "source_lineage_mismatch",
                "semantic_execution_or_correspondence_failed",
                "temporal_failure",
                "interpretation_publication_or_copy_failed",
            ),
        )
        self.reason = reason
        super().__init__(message)


_R = PolygonCompletedDailyInterpretationRefusalReason
type _Resolved = tuple[
    t.PolygonCompletedDailyTechnicalResult, CanonicalInstrument, dict[str, object]
]


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyInterpretationResult:
    interpretation: GovernedDailyTechnicalInterpretation
    technical_available_at: datetime
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("Interpretation results require trusted execution")

    @property
    def source_technical_occurrence(self) -> PolygonCompletedDailyInterpretationRequest:
        return self.interpretation.source_technical_occurrence

    @property
    def source_content_fingerprint(self) -> str:
        return self.interpretation.source_technical_analysis_snapshot_fingerprint

    @property
    def analysis_as_of(self) -> datetime:
        return self.interpretation.analysis_as_of

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": "polygon_completed_daily_interpretation_result/v1",
            "interpretation": self.interpretation.to_dict(),
            "technical_available_at": self.technical_available_at.isoformat(),
            "operation": _OPERATION,
            "operation_version": _VERSION,
            "executor": _EXECUTOR,
            "execution_id": self.execution_id,
            "history_namespace_id": self.history_namespace_id,
            "history_sequence": self.history_sequence,
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def to_dict(self) -> dict[str, object]:
        if type(self.interpretation) is not GovernedDailyTechnicalInterpretation:
            raise ValueError("exact governed Interpretation content required")
        self.interpretation._validate()
        t._identity(self.execution_id, _PREFIX)
        t._identity(self.history_namespace_id, _PREFIX + "_history")
        t._sequence(self.history_sequence)
        for instant in (
            self.technical_available_at,
            self.execution_started_at,
            self.execution_completed_at,
            self.available_at,
        ):
            a._require_canonical_timestamp(instant, "Interpretation occurrence time")
        if not (
            self.technical_available_at
            <= self.execution_started_at
            <= self.execution_completed_at
            <= self.available_at
        ):
            raise ValueError("Interpretation occurrence chronology invalid")
        payload = self._payload()
        domain._fingerprint(self.fingerprint)
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError("Interpretation envelope fingerprint mismatch")
        return deepcopy({**payload, "fingerprint": self.fingerprint})


def _public_result_copy(
    retained: PolygonCompletedDailyInterpretationResult,
) -> PolygonCompletedDailyInterpretationResult:
    expected = retained.to_dict()
    public = _reconstruct_result(_encode_result(retained))
    if public is retained or public.to_dict() != expected:
        raise ValueError("public copy changed Interpretation content")
    return public


def _check_scalars(value: object) -> None:
    """Accept only exact JSON scalars/containers; never coerce user objects."""
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("exact scalar projection keys required")
            _check_scalars(item)
    elif type(value) is list:
        for item in value:
            _check_scalars(item)
    elif type(value) is float:
        if not math.isfinite(value) or (
            value == 0.0 and math.copysign(1.0, value) < 0.0
        ):
            raise ValueError("canonical finite scalar required")
    elif type(value) not in (str, int, bool, type(None)):
        raise TypeError("exact scalar projection required")


def _canonical_bytes(projection: object) -> bytes:
    _check_scalars(projection)
    return json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _encode_result(result: PolygonCompletedDailyInterpretationResult) -> bytes:
    if type(result) is not PolygonCompletedDailyInterpretationResult:
        raise TypeError("exact Interpretation result required")
    return _canonical_bytes(result.to_dict())


def _decode_result(fact: bytes) -> dict[str, Any]:
    if type(fact) is not bytes:
        raise TypeError("exact immutable Interpretation bytes required")
    value = json.loads(fact)
    if type(value) is not dict or _canonical_bytes(value) != fact:
        raise ValueError("noncanonical Interpretation encoding")
    return value


def _reconstruct_result(fact: bytes) -> PolygonCompletedDailyInterpretationResult:
    """Rebuild caller-owned values and check the entire original scalar encoding."""
    projection = _decode_result(fact)
    content = projection["interpretation"]
    occurrence = content["source_technical_occurrence"]
    artifact = occurrence["artifact_reference"]
    artifact_value = domain.GovernedTechnicalArtifactReference(
        **{
            key: value
            for key, value in artifact.items()
            if key not in ("schema_version", "fingerprint")
        }
    )
    request = PolygonCompletedDailyInterpretationRequest(
        **{
            **occurrence,
            "artifact_reference": artifact_value,
        }
    )
    policy = content["interpretation_policy_identity"]
    configuration = policy["configuration"]
    if type(configuration) is not dict or any(
        type(value) is not float for value in configuration.values()
    ):
        raise TypeError("exact configuration float scalars required")
    policy_value = domain.GovernedTechnicalPolicyIdentity(
        **{
            **{
                key: value
                for key, value in policy.items()
                if key not in ("schema_version", "fingerprint", "configuration")
            },
            "configuration": ClassicDailyTechnicalInterpretationConfiguration(
                **configuration
            ),
        }
    )
    comparisons = tuple(
        domain.GovernedTechnicalComparisonEvidence(
            **{
                **item,
                "left_operand": domain.GovernedTechnicalComparisonOperand(
                    **item["left_operand"]
                ),
                "right_operand": domain.GovernedTechnicalComparisonOperand(
                    **item["right_operand"]
                ),
            }
        )
        for item in content["comparison_evidence"]
    )
    trading = content["source_trading_identity"]
    interpretation = GovernedDailyTechnicalInterpretation(
        **{
            **{
                key: value
                for key, value in content.items()
                if key not in ("schema_version", "fingerprint")
            },
            "source_technical_occurrence": request,
            "canonical_instrument_id": CanonicalInstrumentId(
                **content["canonical_instrument_id"]
            ),
            "source_trading_identity": TradingInstrumentIdentity(
                trading["symbol"], trading["venue"]
            ),
            "analysis_as_of": datetime.fromisoformat(content["analysis_as_of"]),
            "interpretation_policy_identity": policy_value,
            "source_warnings": tuple(content["source_warnings"]),
            "comparison_evidence": comparisons,
        }
    )
    result = object.__new__(PolygonCompletedDailyInterpretationResult)
    for item in fields(result):
        value = (
            projection[item.name] if item.name != "interpretation" else interpretation
        )
        if item.name.endswith("_at"):
            value = datetime.fromisoformat(projection[item.name])
        object.__setattr__(result, item.name, value)
    # Binds every key, numeric type, timestamp, nested identity and both hashes.
    if _encode_result(result) != fact:
        raise ValueError("Interpretation scalar reconstruction mismatch")
    return result


def _graph_ids(value: object) -> set[int]:
    """Frozen dataclass instances remain mutable through object.__setattr__."""
    if is_dataclass(value) and not isinstance(value, type):
        result = {id(value)}
        for field in fields(value):
            result.update(_graph_ids(getattr(value, field.name)))
        return result
    if isinstance(value, tuple):
        return set().union(*(_graph_ids(item) for item in value))
    return set()


def _check_copy(
    public: PolygonCompletedDailyInterpretationResult,
    retained: PolygonCompletedDailyInterpretationResult,
    expected: dict[str, object],
) -> None:
    if (
        type(public) is not PolygonCompletedDailyInterpretationResult
        or public.to_dict() != expected
        or retained.to_dict() != expected
        or _graph_ids(public) & _graph_ids(retained)
    ):
        raise ValueError("public result changed content or aliases retained state")


class _InterpretationHistory:
    """Canonical committed facts; transient pending staging grants no authority."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = f"{_PREFIX}_history:{uuid4().hex}"
        self._state: tuple[int, tuple[bytes, ...]] = (
            1,
            (),
        )
        self._pending: PolygonCompletedDailyInterpretationResult | None = None

    def _stage_publication(
        self, result: PolygonCompletedDailyInterpretationResult
    ) -> None:
        result.to_dict()
        self._pending = result

    def _validate(self) -> None:
        if type(self._state) is not tuple or len(self._state) != 2:
            raise ValueError("exact history state tuple required")
        sequence, entries = self._state
        t._sequence(sequence)
        t._identity(self._namespace_id, _PREFIX + "_history")
        if type(entries) is not tuple or sequence != len(entries) + 1:
            raise ValueError("Interpretation history incomplete")
        ids: set[str] = set()
        previous: datetime | None = None
        for index, fact in enumerate(entries, 1):
            item = _reconstruct_result(fact)
            if (
                item.history_namespace_id != self._namespace_id
                or item.history_sequence != index
                or item.execution_id in ids
                or (previous is not None and item.available_at < previous)
            ):
                raise ValueError("Interpretation history corrupt")
            ids.add(item.execution_id)
            previous = item.available_at


def _reference(
    item: t.PolygonCompletedDailyTechnicalResult,
) -> PolygonCompletedDailyInterpretationRequest:
    return PolygonCompletedDailyInterpretationRequest(
        artifact_reference=domain._copy_artifact(
            item.source.bridge_reference.artifact_reference
        ),
        technical_history_namespace_id=item.history_namespace_id,
        technical_history_sequence=item.history_sequence,
        technical_execution_id=item.execution_id,
        technical_fingerprint=item.fingerprint,
    )


@dataclass(frozen=True, slots=True)
class _PreparedInterpretationInventory:
    """Detached correspondence data; possession never authenticates a call."""

    items: tuple[PolygonCompletedDailyInterpretationResult, ...]
    facts: tuple[bytes, ...]
    selectors: tuple[bytes, ...]
    technical_selectors: tuple[bytes, ...]
    support_facts: tuple[bytes, ...]

    def __reduce__(self) -> Any:
        raise TypeError("prepared Interpretation data is not serializable")


@dataclass(slots=True, init=False)
class _InterpretationTransaction:
    """Trusted call-local anchors, kept outside the detached inventory."""

    publisher: PolygonCompletedDailyProductionInterpretationApplicationService
    state: tuple[int, tuple[bytes, ...]]
    dictionaries: tuple[tuple[Any, dict[str, Any]], ...]
    anchors: tuple[tuple[dict[str, Any], str, Any], ...]
    slot_anchors: tuple[tuple[object, str, Any], ...]
    slot_descriptors: tuple[tuple[Any, str, MemberDescriptorType], ...]
    witness: _InterpretationOwnership
    phase: str
    native_support: tuple[tuple[Any, ...], tuple[Any, ...]]
    active: bool = True
    prepared: _PreparedInterpretationInventory | None = None
    sources: tuple[object, ...] = ()
    support_facts: tuple[bytes, ...] = ()
    retention: object = None

    def __init__(self) -> None:
        raise TypeError("Interpretation transaction requires a held-lock context")

    def __reduce__(self) -> Any:
        raise TypeError("Interpretation transaction cannot be copied or serialized")


@dataclass(slots=True)
class _InterpretationOwnership:
    """Strategy-local witness created only after its complete lock acquisition."""

    thread: int
    locks: tuple[Any, ...]
    assessment_owner: Any
    strategy_owner: Any
    activation: object | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.thread) is not int
            or self.thread != get_ident()
            or type(self.locks) is not tuple
            or len(self.locks) != 11
            or any(
                type(lock) is not LockType or not lock.locked() for lock in self.locks
            )
            or len({id(lock) for lock in self.locks}) != 11
        ):
            raise _InterpretationHistoryInvalid(
                "complete owner-thread lock scope required"
            )

    def __reduce__(self) -> Any:
        raise TypeError("ownership witness cannot be copied or serialized")


def _capture_interpretation_native_support(
    roots: tuple[object, ...],
) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    """Capture the finite retained support schema, before support callbacks.

    Field names are explicitly enumerated above; no dataclass discovery, generic
    object reflection, projections, validation, equality or copying is used.
    """
    nodes: list[Any] = []
    prices: list[Any] = []
    visited: set[int] = set()

    def visit(value: Any) -> None:
        kind = type(value)
        if any(
            kind is allowed
            for allowed in (
                str,
                bytes,
                int,
                bool,
                float,
                type(None),
                datetime,
                date,
                Decimal,
            )
        ):
            return
        if id(value) in visited:
            return
        visited.add(id(value))
        if kind is _historical.HistoricalPriceSeries:
            prices.append((value, *_historical._capture_storage_continuity(value)))
            return
        if any(kind is allowed for allowed in _INTERPRETATION_SUPPORT_ENUMS):
            mapping = object.__getattribute__(value, "__dict__")
            if (
                type(mapping) is not dict
                or any(type(key) is not str for key in mapping)
                or set(mapping) != {"_value_", "_name_", "__objclass__", "_sort_order_"}
                or type(mapping["_value_"]) is not str
                or type(mapping["_name_"]) is not str
                or mapping["__objclass__"] is not kind
                or type(mapping["_sort_order_"]) is not int
            ):
                raise _InterpretationHistoryInvalid("unsupported retained enum")
            nodes.append((value, kind, "enum", mapping, tuple(mapping.items())))
            return
        if kind is tuple or kind is list:
            children = tuple(value)
            nodes.append((value, kind, "sequence", children))
        elif kind is dict:
            if any(type(key) is not str for key in value):
                raise _InterpretationHistoryInvalid("unsupported retained mapping")
            pairs = tuple(value.items())
            nodes.append((value, kind, "mapping", pairs))
            children = tuple(item for _, item in pairs)
        else:
            names = next(
                (
                    names
                    for allowed, names in _INTERPRETATION_SUPPORT_FIELDS.items()
                    if kind is allowed
                ),
                None,
            )
            if names is None:
                raise _InterpretationHistoryInvalid("unsupported retained record")
            members = vars(kind)
            slots = members.get("__slots__")
            if (
                type(slots) is not tuple
                or any(type(name) is not str for name in slots)
                or slots != names
            ):
                raise _InterpretationHistoryInvalid(
                    "unsupported retained record layout"
                )
            descriptors = tuple(members[name] for name in names)
            if any(type(field) is not MemberDescriptorType for field in descriptors):
                raise _InterpretationHistoryInvalid("native retained fields required")
            if any(
                kind is allowed
                for allowed in (
                    _support_governance._ClosedDefinition,
                    _support_governance._FreshnessRuleDefinition,
                    _support_governance._ProductionGovernanceProfile,
                    _support_governance._ValidationRuleDefinition,
                )
            ):
                descriptor = vars(_support_governance._FingerprintedDefinition)[
                    "__dict__"
                ]
                if (
                    type(descriptor) is not GetSetDescriptorType
                    or "__dict__" in members
                ):
                    raise _InterpretationHistoryInvalid(
                        "native definition dictionary required"
                    )
                names = (*names, "__dict__")
                descriptors = (*descriptors, descriptor)
            children = tuple(object.__getattribute__(value, name) for name in names)
            nodes.append((value, kind, "record", names, descriptors, children))
        for child in children:
            visit(child)

    for root in roots:
        visit(root)
    return tuple(nodes), tuple(prices)


def _compare_interpretation_native_support(
    expectation: tuple[tuple[Any, ...], tuple[Any, ...]],
) -> None:
    """S2: reread every original native edge and current Historical storage."""
    nodes, prices = expectation
    for node in nodes:
        value, kind, category = node[:3]
        if type(value) is not kind:
            raise _InterpretationHistoryInvalid("retained record type changed")
        if category == "record":
            names, descriptors, originals = node[3:]
            members = vars(kind)
            for name, descriptor, original in zip(
                names, descriptors, originals, strict=True
            ):
                current_descriptor = (
                    vars(_support_governance._FingerprintedDefinition)["__dict__"]
                    if name == "__dict__" and name not in members
                    else members[name]
                )
                if current_descriptor is not descriptor:
                    raise _InterpretationHistoryInvalid("retained descriptor changed")
                if object.__getattribute__(value, name) is not original:
                    raise _InterpretationHistoryInvalid("retained field changed")
        elif category == "sequence":
            originals = node[3]
            if len(value) != len(originals) or any(
                current is not original
                for current, original in zip(value, originals, strict=True)
            ):
                raise _InterpretationHistoryInvalid("retained sequence changed")
        else:
            if category == "enum":
                mapping, originals = node[3:]
                if object.__getattribute__(value, "__dict__") is not mapping:
                    raise _InterpretationHistoryInvalid("retained enum changed")
            else:
                mapping, originals = value, node[3]
            if len(mapping) != len(originals) or any(
                key is not old_key or item is not old_item
                for (key, item), (old_key, old_item) in zip(
                    mapping.items(), originals, strict=True
                )
            ):
                raise _InterpretationHistoryInvalid("retained mapping changed")
    for series, data, attachments in prices:
        _historical._compare_storage_continuity(series, data, attachments)


def _check_interpretation_lifetime(
    transaction: _InterpretationTransaction, phase: str
) -> None:
    if type(transaction) is not _InterpretationTransaction:
        raise _InterpretationHistoryInvalid("original transaction required")
    witness = transaction.witness
    if (
        type(witness) is not _InterpretationOwnership
        or type(witness.closed) is not bool
        or witness.closed
        or type(witness.thread) is not int
        or witness.thread != get_ident()
        or witness.activation is not transaction
        or type(transaction.active) is not bool
        or not transaction.active
        or type(transaction.phase) is not str
        or transaction.phase != phase
        or type(witness.locks) is not tuple
        or len(witness.locks) != 11
        or witness.assessment_owner._lock is not witness.locks[9]
        or witness.strategy_owner._lock is not witness.locks[10]
        or any(
            type(lock) is not LockType or not lock.locked() for lock in witness.locks
        )
    ):
        raise _InterpretationHistoryInvalid("inactive or reentrant transaction")


def _interpretation_selector_fact(
    item: PolygonCompletedDailyInterpretationResult,
) -> bytes:
    return _canonical_bytes(
        {
            "artifact_reference": (
                item.source_technical_occurrence.artifact_reference.to_dict()
            ),
            "interpretation_history_namespace_id": item.history_namespace_id,
            "interpretation_history_sequence": item.history_sequence,
            "interpretation_execution_id": item.execution_id,
            "interpretation_fingerprint": item.fingerprint,
        }
    )


def _check_prepared_interpretation_facts(
    prepared: _PreparedInterpretationInventory,
    facts: tuple[bytes, ...],
) -> None:
    """One complete canonical pass, after ALL inventory-wide preparation."""
    try:
        if type(prepared) is not _PreparedInterpretationInventory:
            raise TypeError("exact private Interpretation inventory required")
        if (
            type(prepared.items) is not tuple
            or type(prepared.facts) is not tuple
            or type(prepared.selectors) is not tuple
            or type(prepared.technical_selectors) is not tuple
            or type(prepared.support_facts) is not tuple
            or prepared.facts != facts
            or not (
                len(prepared.items)
                == len(facts)
                == len(prepared.selectors)
                == len(prepared.technical_selectors)
                == len(prepared.support_facts)
            )
        ):
            raise ValueError("complete prepared Interpretation inventory changed")
        for item, fact, selector, technical, support in zip(
            prepared.items,
            prepared.facts,
            prepared.selectors,
            prepared.technical_selectors,
            prepared.support_facts,
            strict=True,
        ):
            if (
                type(fact) is not bytes
                or type(selector) is not bytes
                or type(technical) is not bytes
                or type(support) is not bytes
                or _encode_result(item) != fact
                or _interpretation_selector_fact(item) != selector
                or _canonical_bytes(item.source_technical_occurrence.to_dict())
                != technical
            ):
                raise ValueError("prepared Interpretation correspondence changed")
    except Exception as error:
        raise _InterpretationSourceMismatch(str(error)) from error


def _select_prepared_interpretation(
    prepared: _PreparedInterpretationInventory,
    selector: bytes,
    transaction: _InterpretationTransaction,
) -> PolygonCompletedDailyInterpretationResult:
    """Select local data in the original prepared lifetime, without authentication."""
    _check_interpretation_lifetime(transaction, "PREPARED")
    if type(prepared) is not _PreparedInterpretationInventory:
        raise TypeError("exact private Interpretation inventory required")
    if transaction.prepared is not prepared:
        raise _InterpretationHistoryInvalid("original prepared inventory required")
    _check_prepared_interpretation_facts(prepared, prepared.facts)
    _check_interpretation_lifetime(transaction, "PREPARED")
    matches = tuple(
        item
        for item, expected in zip(prepared.items, prepared.selectors, strict=True)
        if type(selector) is bytes and selector == expected
    )
    if len(matches) != 1:
        raise _InterpretationOccurrenceUnavailable(
            "exact committed Interpretation occurrence unavailable"
        )
    return matches[0]


def _check_content(
    content: GovernedDailyTechnicalInterpretation,
    source: t.PolygonCompletedDailyTechnicalResult,
    instrument: CanonicalInstrument,
) -> None:
    domain.validate_governed_daily_technical_interpretation(
        content=content,
        snapshot=source.snapshot,
        source_technical_occurrence=_reference(source),
        canonical_instrument=instrument,
        source_governed_dataset_fingerprint=source.source.dataset_fingerprint,
    )


class PolygonCompletedDailyProductionInterpretationApplicationService:
    def __init__(
        self,
        technical_service: t.PolygonCompletedDailyProductionTechnicalApplicationService,
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(technical_service) is not (
            t.PolygonCompletedDailyProductionTechnicalApplicationService
        ):
            raise TypeError("exact trusted technical service required")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._technical_service = technical_service
        self._clock = a._utc_now if execution_clock is None else execution_clock
        self._history_owner = _InterpretationHistory()
        self._history = self._history_owner
        self._namespace = self._history_owner._namespace_id
        # The service pins its current commitment independently of the history view.
        self._committed = self._history_owner._state
        self._technical_history = technical_service._history
        self._technical_namespace = self._technical_history._namespace_id
        # Observational anchors never confer import authority. Preserve identities
        # and complete detached projections, not mutable upstream result graphs.
        self._observed: tuple[tuple[int, dict[str, object]], ...] = ()
        self._retention: tuple[tuple[int, str, tuple[int, ...]], ...] = ()
        try:
            with ExitStack() as stack:
                self._lock_inputs(stack)
                self._observe_technical_history()
        except Exception as error:
            raise PolygonCompletedDailyInterpretationRefused(
                _R.HISTORY_INVALID, str(error)
            ) from error

    def _lock_inputs(self, stack: ExitStack) -> None:
        self._technical_service._lock_inputs(stack)
        stack.enter_context(self._history_owner._lock)

    def _authentication_retention(
        self,
    ) -> tuple[tuple[int, str, int, tuple[tuple[int, bytes], ...]], ...]:
        """Check existing upstream anchors without adopting observations."""
        self._technical_service._validate_authority()
        bridge = self._technical_service._bridge_service
        qualification = bridge._qualification_service
        validity = qualification._validity_service
        admission = validity._admission_service
        stores = (
            admission._construction_service._history,
            admission._validation_service._history,
            admission._freshness_service._history,
            admission._history,
            validity._history,
            qualification._history,
            bridge._history,
            self._technical_service._history,
        )
        if len(self._retention) != len(stores):
            raise ValueError("original upstream retention anchors incomplete")
        retention = []
        for index, (store, (identity, namespace, entries)) in enumerate(
            zip(stores, self._retention, strict=True)
        ):
            state = getattr(store, "_state")  # noqa: B009
            current_namespace = getattr(store, "_namespace_id")  # noqa: B009
            if (
                id(store) != identity
                or type(current_namespace) is not str
                or current_namespace != namespace
                or type(state) is not tuple
                or len(state) != 2
                or type(state[0]) is not int
                or type(state[1]) is not tuple
                or state[0] != len(state[1]) + 1
            ):
                raise ValueError("original upstream history changed or incomplete")
            current_entries = tuple(id(item) for item in state[1])
            if current_entries[: len(entries)] != entries:
                raise ValueError("original upstream occurrences replaced or lost")
            projections = []
            for item in state[1]:
                # Earlier lifecycle results expose receipts/companions rather
                # than a result projection. Their validators bind all backing
                # material and records to those complete occurrence projections.
                if index < 5:
                    item._validate()
                    carrier = item.receipt if index == 0 else item.companion
                    projection = carrier.to_dict()
                else:
                    projection = item.to_dict()
                projections.append((id(item), t._issuance_bytes(projection)))
            retention.append(
                (
                    identity,
                    namespace,
                    id(state),
                    tuple(projections),
                )
            )
        history = self._technical_service._history
        if (
            history is not self._technical_history
            or history._namespace_id != self._technical_namespace
            or len(history._state[1]) < len(self._observed)
        ):
            raise ValueError("original technical history replaced or lost")
        for item, (identity, projection) in zip(
            history._state[1], self._observed, strict=False
        ):
            if id(item) != identity or item.to_dict() != projection:
                raise ValueError("original technical occurrence changed")
        return tuple(retention)

    def _authenticate_interpretation_support(
        self, item: PolygonCompletedDailyInterpretationResult
    ) -> _Resolved:
        """Authenticate original support without deriving Interpretation semantics."""
        matches = tuple(
            source
            for source in self._technical_history._state[1]
            if _reference(source) == item.source_technical_occurrence
        )
        if len(matches) != 1:
            raise ValueError("original technical occurrence unavailable")
        source = matches[0]
        instrument, projection = self._authenticate(source)
        content = item.interpretation
        if (
            item.technical_available_at != source.available_at
            or source.available_at > item.execution_started_at
            or content.canonical_instrument_id.to_dict()
            != instrument.instrument_id.to_dict()
            or content.source_trading_identity.to_dict()
            != source.snapshot.evidence.instrument.to_dict()
            or content.analysis_as_of != source.snapshot.evidence.analysis_as_of
            or content.source_technical_analysis_snapshot_fingerprint
            != source.snapshot.fingerprint
            or content.source_governed_dataset_fingerprint
            != source.source.dataset_fingerprint
            or content.source_research_dataset_content_fingerprint
            != source.snapshot.evidence.dataset_content_fingerprint
            or content.source_quality != source.snapshot.quality.value
            or content.source_warnings
            != tuple(warning.value for warning in source.snapshot.warnings)
        ):
            raise _InterpretationSourceMismatch(
                "retained Interpretation source lineage mismatch"
            )
        return source, instrument, projection

    @contextmanager
    def _interpretation_transaction(
        self, witness: _InterpretationOwnership
    ) -> Iterator[_InterpretationTransaction]:
        """Capture trusted anchors under the caller's already-held complete chain.

        The caller owns this context in locals and exits it before releasing locks.
        Nothing is installed on a service, owner, request or detached inventory.
        """
        if (
            type(witness) is not _InterpretationOwnership
            or witness.closed
            or witness.activation is not None
            or witness.thread != get_ident()
        ):
            if type(witness) is _InterpretationOwnership:
                witness.closed = True
            raise _InterpretationHistoryInvalid("fresh owner-thread witness required")
        try:
            technical = self._technical_service
            bridge = technical._bridge_service
            qualification = bridge._qualification_service
            validity = qualification._validity_service
            admission = validity._admission_service
            services = (
                admission._construction_service,
                admission._validation_service,
                admission._freshness_service,
                admission,
                validity,
                qualification,
                bridge,
                technical,
                self,
            )
            owners = tuple(service._history for service in services)
            expected_locks = tuple(owner._lock for owner in owners) + (
                witness.assessment_owner._lock,
                witness.strategy_owner._lock,
            )
            if (
                len(witness.locks) != 11
                or any(
                    actual is not expected
                    for actual, expected in zip(
                        witness.locks, expected_locks, strict=True
                    )
                )
                or not all(lock.locked() for lock in expected_locks)
            ):
                raise _InterpretationHistoryInvalid(
                    "complete eleven-lock witness required"
                )
            authorities = (*services, *owners)
            dictionaries = tuple(
                (value, vars(value))
                for value in authorities
                if hasattr(value, "__dict__")
            )
            # Only authority fields are anchored, never replaceable test/codec helpers.
            names = (
                "_history",
                "_history_owner",
                "_namespace",
                "_committed",
                "_observed",
                "_retention",
                "_technical_history",
                "_technical_namespace",
                "_technical_service",
                "_bridge_service",
                "_qualification_service",
                "_validity_service",
                "_admission_service",
                "_construction_service",
                "_validation_service",
                "_freshness_service",
                "_state",
                "_namespace_id",
                "_lock",
                "_pending",
                "_issuance",
                "_PolygonCompletedDailyProductionTechnicalApplicationService__committed",
            )
            anchors = tuple(
                (mapping, name, mapping[name])
                for _, mapping in dictionaries
                for name in names
                if name in mapping
            )
            slot_anchors = tuple(
                (value, name, object.__getattribute__(value, name))
                for value in authorities
                if not hasattr(value, "__dict__")
                for name in names
                if name in vars(type(value)).get("__slots__", ())
            )
            slot_descriptors = tuple(
                (vars(type(value)), name, vars(type(value))[name])
                for value, name, _ in slot_anchors
            )
            if any(
                type(descriptor) is not MemberDescriptorType
                for _, _, descriptor in slot_descriptors
            ):
                raise _InterpretationHistoryInvalid(
                    "original native authority slots required"
                )
            transaction = object.__new__(_InterpretationTransaction)
            transaction.publisher = self
            transaction.state = self._committed
            transaction.dictionaries = dictionaries
            transaction.anchors = anchors
            transaction.slot_anchors = slot_anchors
            transaction.slot_descriptors = slot_descriptors
            transaction.witness = witness
            transaction.phase = "ACTIVE"
            witness.activation = transaction
            transaction.active = True
            transaction.prepared = None
            transaction.sources = ()
            transaction.support_facts = ()
            transaction.retention = None
            transaction.native_support = _capture_interpretation_native_support(
                tuple(owner._state for owner in owners)
                + tuple(
                    mapping[name]
                    for _, mapping in dictionaries
                    for name in ("_observed", "_retention", "_issuance")
                    if name in mapping
                )
            )
            try:
                if (
                    type(self._history_owner) is not _InterpretationHistory
                    or self._history is not self._history_owner
                    or self._history_owner._state is not transaction.state
                    or self._history_owner._namespace_id is not self._namespace
                    or self._history_owner._pending is not None
                    or not all(owner._lock.locked() for owner in owners)
                ):
                    raise _InterpretationHistoryInvalid(
                        "original held Interpretation roots required"
                    )
                yield transaction
            finally:
                transaction.phase = "CLOSED"
                transaction.active = False
                transaction.prepared = None
                transaction.sources = ()
                transaction.support_facts = ()
                transaction.retention = None
        finally:
            witness.closed = True
            witness.activation = None

    def _prepare_interpretation_inventory(
        self,
        transaction: _InterpretationTransaction,
    ) -> _PreparedInterpretationInventory:
        """Two complete support passes, without selection or lock acquisition."""
        try:
            _check_interpretation_lifetime(transaction, "ACTIVE")
            transaction.phase = "PREPARING"
            if (
                type(transaction) is not _InterpretationTransaction
                or not transaction.active
                or transaction.publisher is not self
                or transaction.prepared is not None
                or self._committed is not transaction.state
            ):
                raise _InterpretationHistoryInvalid(
                    "fresh Interpretation transaction required"
                )
            for value, mapping in transaction.dictionaries:
                if object.__getattribute__(value, "__dict__") is not mapping:
                    raise _InterpretationHistoryInvalid(
                        "original authority dictionary changed"
                    )
            for mapping, name, original in transaction.anchors:
                if mapping[name] is not original:
                    raise _InterpretationHistoryInvalid(
                        "original Interpretation authority changed"
                    )
            # Prove these remain native slots before direct reads; no properties.
            for members, name, descriptor in transaction.slot_descriptors:
                if members[name] is not descriptor:
                    raise _InterpretationHistoryInvalid(
                        "original authority slot changed"
                    )
            for value, name, original in transaction.slot_anchors:
                if object.__getattribute__(value, name) is not original:
                    raise _InterpretationHistoryInvalid(
                        "original slotted authority changed"
                    )
            # P1: finish ALL fallible inventory and first-support preparation.
            self._history_owner._validate()
            transaction.retention = self._authentication_retention()
            items = tuple(_reconstruct_result(fact) for fact in transaction.state[1])
            support = tuple(
                self._authenticate_interpretation_support(item) for item in items
            )
            transaction.sources = tuple(value[0] for value in support)
            transaction.support_facts = tuple(
                t._issuance_bytes(value[2]) for value in support
            )
            prepared = _PreparedInterpretationInventory(
                items,
                transaction.state[1],
                tuple(_interpretation_selector_fact(item) for item in items),
                tuple(
                    _canonical_bytes(item.source_technical_occurrence.to_dict())
                    for item in items
                ),
                transaction.support_facts,
            )
            self._prepare_interpretation_correspondence(prepared, transaction)
            # P2: later-entry preparation cannot leave an earlier graph unchecked.
            _check_prepared_interpretation_facts(prepared, transaction.state[1])
            if prepared.support_facts != transaction.support_facts:
                raise _InterpretationSourceMismatch(
                    "original support expectations changed"
                )
            transaction.prepared = prepared
            # P3 includes the second entry-support pass AND complete retention sweep.
            self._confirm_interpretation_support(prepared, transaction)
            # P4: direct identities only after the final fresh support boundary.
            for value, mapping in transaction.dictionaries:
                if object.__getattribute__(value, "__dict__") is not mapping:
                    raise _InterpretationHistoryInvalid(
                        "original authority dictionary changed"
                    )
            for mapping, name, original in transaction.anchors:
                if mapping[name] is not original:
                    raise _InterpretationHistoryInvalid(
                        "original Interpretation authority changed"
                    )
            # Prove these remain native slots before direct reads; no properties.
            for members, name, descriptor in transaction.slot_descriptors:
                if members[name] is not descriptor:
                    raise _InterpretationHistoryInvalid(
                        "original authority slot changed"
                    )
            for value, name, original in transaction.slot_anchors:
                if object.__getattribute__(value, name) is not original:
                    raise _InterpretationHistoryInvalid(
                        "original slotted authority changed"
                    )
            transaction.phase = "PREPARED"
            return prepared
        except _InterpretationHistoryInvalid, _InterpretationSourceMismatch:
            if type(transaction) is _InterpretationTransaction:
                transaction.active = False
                transaction.phase = "CLOSED"
            raise
        except Exception as error:
            if type(transaction) is _InterpretationTransaction:
                transaction.active = False
                transaction.phase = "CLOSED"
            raise _InterpretationHistoryInvalid(str(error)) from error

    def _prepare_interpretation_correspondence(
        self,
        prepared: _PreparedInterpretationInventory,
        transaction: _InterpretationTransaction,
    ) -> None:
        """Entire fallible reconstruction/copy pass before the canonical recheck."""
        self._history_owner._validate()
        if self._committed is not transaction.state:
            raise _InterpretationHistoryInvalid(
                "original Interpretation commitment changed"
            )
        for item, fact in zip(prepared.items, transaction.state[1], strict=True):
            try:
                _check_copy(item, _reconstruct_result(fact), _decode_result(fact))
            except Exception as error:
                raise _InterpretationSourceMismatch(str(error)) from error

    def _confirm_interpretation_support(
        self,
        prepared: _PreparedInterpretationInventory,
        transaction: _InterpretationTransaction,
    ) -> None:
        """Complete fresh lineage proof, then retained-support confirmation.

        The final sweep catches persistent earlier-support loss/replacement caused
        by later entry authentication. Shared Technical selectors never coalesce
        independently retained Interpretation lineage obligations.
        """
        phase = transaction.phase
        if type(phase) is not str or phase not in ("PREPARING", "SEALING"):
            raise _InterpretationHistoryInvalid("active support preparation required")
        _check_interpretation_lifetime(transaction, phase)
        for item, source, fact in zip(
            prepared.items, transaction.sources, transaction.support_facts, strict=True
        ):
            resolved, _, projection = self._authenticate_interpretation_support(item)
            if resolved is not source:
                raise _InterpretationHistoryInvalid(
                    "original Technical occurrence replaced"
                )
            if t._issuance_bytes(projection) != fact:
                raise _InterpretationSourceMismatch(
                    "original Interpretation support changed"
                )
        if self._authentication_retention() != transaction.retention:
            raise _InterpretationHistoryInvalid("original upstream inventory changed")
        # S1 is complete for the ENTIRE inventory. S2 performs native live reads
        # only; acceptance (S3) precedes the callers' direct-only S4 tails.
        _check_interpretation_lifetime(transaction, phase)
        _compare_interpretation_native_support(transaction.native_support)

    def _seal_prepared_interpretation_inventory(
        self,
        prepared: _PreparedInterpretationInventory,
        transaction: _InterpretationTransaction,
    ) -> None:
        """Four-phase complete seal using ORIGINAL call-local authority anchors."""
        try:
            _check_interpretation_lifetime(transaction, "PREPARED")
            transaction.phase = "SEALING"
            if (
                type(transaction) is not _InterpretationTransaction
                or not transaction.active
                or transaction.publisher is not self
                or transaction.prepared is not prepared
                or self._committed is not transaction.state
            ):
                raise _InterpretationHistoryInvalid(
                    "original Interpretation transaction required"
                )
            for value, mapping in transaction.dictionaries:
                if object.__getattribute__(value, "__dict__") is not mapping:
                    raise _InterpretationHistoryInvalid(
                        "original authority dictionary changed"
                    )
            for mapping, name, original in transaction.anchors:
                if mapping[name] is not original:
                    raise _InterpretationHistoryInvalid(
                        "original Interpretation authority changed"
                    )
            # Prove these remain native slots before direct reads; no properties.
            for members, name, descriptor in transaction.slot_descriptors:
                if members[name] is not descriptor:
                    raise _InterpretationHistoryInvalid(
                        "original authority slot changed"
                    )
            for value, name, original in transaction.slot_anchors:
                if object.__getattribute__(value, name) is not original:
                    raise _InterpretationHistoryInvalid(
                        "original slotted authority changed"
                    )
            # Phase 1: finish fallible preparation for the ENTIRE inventory.
            self._prepare_interpretation_correspondence(prepared, transaction)
            # Phase 2: canonical working facts/bindings AFTER all Phase-1 work.
            _check_prepared_interpretation_facts(prepared, transaction.state[1])
            if prepared.support_facts != transaction.support_facts:
                raise _InterpretationSourceMismatch(
                    "original support expectations changed"
                )
            # Phase 3: every original lineage, including unselected/invisible entries.
            self._confirm_interpretation_support(prepared, transaction)
            # Phase 4: direct-only tail. No codecs, copies, callbacks or preparation.
            for value, mapping in transaction.dictionaries:
                if object.__getattribute__(value, "__dict__") is not mapping:
                    raise _InterpretationHistoryInvalid(
                        "original authority dictionary changed"
                    )
            for mapping, name, original in transaction.anchors:
                if mapping[name] is not original:
                    raise _InterpretationHistoryInvalid(
                        "original Interpretation authority changed"
                    )
            # Prove these remain native slots before direct reads; no properties.
            for members, name, descriptor in transaction.slot_descriptors:
                if members[name] is not descriptor:
                    raise _InterpretationHistoryInvalid(
                        "original authority slot changed"
                    )
            for value, name, original in transaction.slot_anchors:
                if object.__getattribute__(value, name) is not original:
                    raise _InterpretationHistoryInvalid(
                        "original slotted authority changed"
                    )
            transaction.phase = "SEALED"
        except _InterpretationHistoryInvalid, _InterpretationSourceMismatch:
            if type(transaction) is _InterpretationTransaction:
                transaction.active = False
                transaction.phase = "CLOSED"
            raise
        except Exception as error:
            if type(transaction) is _InterpretationTransaction:
                transaction.active = False
                transaction.phase = "CLOSED"
            raise _InterpretationHistoryInvalid(str(error)) from error

    def _authenticate_interpretation_occurrence(
        self,
        *,
        artifact_reference: domain.GovernedTechnicalArtifactReference,
        interpretation_history_namespace_id: str,
        interpretation_history_sequence: int,
        interpretation_execution_id: str,
        interpretation_fingerprint: str,
    ) -> PolygonCompletedDailyInterpretationResult:
        """Authenticate committed membership under the caller's complete input locks.

        The caller must already hold the upstream-through-pinned-Interpretation
        lock chain. This method acquires no locks, updates no observations, and
        uses the source envelope fingerprint, never content equivalence.
        """
        if type(artifact_reference) is not domain.GovernedTechnicalArtifactReference:
            raise TypeError("exact governed artifact reference required")
        reference = artifact_reference.to_dict()
        t._identity(interpretation_history_namespace_id, _PREFIX + "_history")
        t._sequence(interpretation_history_sequence)
        t._identity(interpretation_execution_id, _PREFIX)
        domain._fingerprint(interpretation_fingerprint)
        try:
            owner = self._history_owner
            namespace = self._namespace
            state = self._committed
            observed, retention = self._observed, self._retention

            def check_authority() -> None:
                if (
                    type(owner) is not _InterpretationHistory
                    or self._history_owner is not owner
                    or self._history is not owner
                    or type(self._namespace) is not str
                    or self._namespace != namespace
                    or type(owner._namespace_id) is not str
                    or owner._namespace_id != namespace
                    or self._committed is not state
                    or owner._state is not state
                    or self._observed is not observed
                    or self._retention is not retention
                ):
                    raise ValueError("Interpretation authority changed or incomplete")

            check_authority()
            owner._validate()
            upstream_before = self._authentication_retention()
            items = tuple(_reconstruct_result(fact) for fact in state[1])
            support_before = tuple(
                self._authenticate_interpretation_support(item) for item in items
            )
            matches = tuple(
                index
                for index, item in enumerate(items)
                if (
                    item.source_technical_occurrence.artifact_reference.to_dict()
                    == reference
                )
                and item.history_namespace_id == interpretation_history_namespace_id
                and item.history_sequence == interpretation_history_sequence
                and item.execution_id == interpretation_execution_id
                and item.fingerprint == interpretation_fingerprint
            )
            if len(matches) != 1:
                check_authority()
                owner._validate()
                if self._authentication_retention() != upstream_before:
                    raise _InterpretationHistoryInvalid(
                        "upstream inventory changed during authentication"
                    )
                check_authority()
                raise _InterpretationOccurrenceUnavailable(
                    "exact committed Interpretation occurrence unavailable"
                )
            fact = state[1][matches[0]]
            public = _reconstruct_result(fact)
            _check_copy(public, items[matches[0]], _decode_result(fact))
            # Revalidate the entire inventory and its original support after the
            # return reconstruction. No observation may adopt changed source facts.
            check_authority()
            owner._validate()
            for original, retained_fact in zip(support_before, state[1], strict=True):
                source, _, before = original
                resolved, _, after = self._authenticate_interpretation_support(
                    _reconstruct_result(retained_fact)
                )
                if resolved is not source:
                    raise _InterpretationHistoryInvalid(
                        "original Interpretation support changed"
                    )
                if after != before:
                    raise _InterpretationSourceMismatch(
                        "original Interpretation support changed"
                    )
            _check_copy(public, items[matches[0]], _decode_result(fact))
            if (
                _encode_result(public) != fact
                or artifact_reference.to_dict() != reference
            ):
                raise _InterpretationSourceMismatch(
                    "selected Interpretation correspondence changed"
                )
            if self._authentication_retention() != upstream_before:
                raise ValueError("upstream inventory changed during authentication")
            check_authority()
            return public
        except (
            _InterpretationOccurrenceUnavailable,
            _InterpretationHistoryInvalid,
            _InterpretationSourceMismatch,
        ):
            raise
        except Exception as error:
            raise _InterpretationHistoryInvalid(str(error)) from error

    def _authenticate(
        self, item: t.PolygonCompletedDailyTechnicalResult
    ) -> tuple[CanonicalInstrument, dict[str, object]]:
        issued, bridge = self._technical_service._authenticate_occurrence(
            artifact_reference=domain._legacy_artifact(
                _reference(item).artifact_reference
            ),
            technical_history_namespace_id=item.history_namespace_id,
            technical_history_sequence=item.history_sequence,
            technical_execution_id=item.execution_id,
            technical_fingerprint=item.fingerprint,
        )
        if issued is not item:
            raise ValueError("technical occurrence is not the original issuance")
        material = bridge.qualification.construction_result.material
        instrument = material.mapping_resolution_provenance.mapping.canonical_instrument
        instrument._validate()
        subject = EvidenceSubjectReference(
            namespace="canonical_instrument",
            subject_id=instrument.instrument_id.instrument_id,
            subject_version=instrument.schema_version,
            subject_fingerprint=instrument.fingerprint,
        )
        if (
            subject != material.canonical_subject
            or instrument.trading_identity != item.snapshot.evidence.instrument
        ):
            raise ValueError("authenticated mapping subject/trading identity mismatch")
        return instrument, deepcopy(
            {
                "technical": item.to_dict(),
                "bridge": bridge.to_dict(),
                "canonical_instrument": instrument.to_dict(),
            }
        )

    def _observe_technical_history(self) -> None:
        # Observation can add retention checks only after publisher authentication.
        self._technical_service._validate_authority()
        bridge = self._technical_service._bridge_service
        qualification = bridge._qualification_service
        validity = qualification._validity_service
        admission = validity._admission_service
        stores = (
            admission._construction_service._history,
            admission._validation_service._history,
            admission._freshness_service._history,
            admission._history,
            validity._history,
            qualification._history,
            bridge._history,
            self._technical_service._history,
        )
        retention = []
        for index, store in enumerate(stores):
            # Released private stores have distinct concrete types, no shared base.
            state = getattr(store, "_state")  # noqa: B009
            namespace = getattr(store, "_namespace_id")  # noqa: B009
            if (
                type(namespace) is not str
                or type(state) is not tuple
                or len(state) != 2
                or type(state[0]) is not int
                or type(state[1]) is not tuple
                or state[0] != len(state[1]) + 1
            ):
                raise ValueError("upstream history shape/inventory incomplete")
            entry_ids = tuple(id(item) for item in state[1])
            store_identity = id(store), namespace, entry_ids
            if self._retention:
                old_store, old_namespace, old_entries = self._retention[index]
                if (
                    id(store) != old_store
                    or namespace != old_namespace
                    or entry_ids[: len(old_entries)] != old_entries
                ):
                    raise ValueError(
                        "upstream store/retained occurrence replaced or lost"
                    )
            retention.append(store_identity)
        history = self._technical_service._history
        if (
            history is not self._technical_history
            or history._namespace_id != self._technical_namespace
            or type(history._state) is not tuple
            or len(history._state) != 2
        ):
            raise ValueError("technical history replaced or malformed")
        t._identity(history._namespace_id, "polygon_completed_daily_technical_history")
        history._validate()
        entries = history._state[1]
        if len(entries) < len(self._observed):
            raise ValueError("previously observed technical history truncated")
        observed = []
        for index, item in enumerate(entries):
            identity = (id(item), deepcopy(item.to_dict()))
            if index < len(self._observed) and identity != self._observed[index]:
                raise ValueError("retained technical occurrence replaced or changed")
            observed.append(identity)
        self._observed = tuple(observed)
        self._retention = tuple(retention)

    def _resolve(
        self, request: PolygonCompletedDailyInterpretationRequest, started: datetime
    ) -> _Resolved:
        self._observe_technical_history()
        matches = tuple(
            item
            for item in self._technical_history._state[1]
            if _reference(item) == request
        )
        if len(matches) != 1 or matches[0].available_at > started:
            raise PolygonCompletedDailyInterpretationRefused(
                _R.TECHNICAL_UNAVAILABLE,
                "exact technical occurrence unavailable by start",
            )
        item = matches[0]
        instrument, projection = self._authenticate(item)
        return item, instrument, projection

    def _check_history(self) -> tuple[_Resolved, ...]:
        owner = self._history_owner
        if (
            self._history is not owner
            or owner._namespace_id != self._namespace
            or owner._state is not self._committed
        ):
            raise ValueError("Interpretation history replaced or truncated")
        owner._validate()
        self._observe_technical_history()
        resolved = tuple(
            (source, *self._authenticate(source))
            for source in self._technical_history._state[1]
        )
        for fact in self._committed[1]:
            item = _reconstruct_result(fact)
            source, instrument, _ = self._select(
                resolved, item.source_technical_occurrence, item.execution_started_at
            )
            _check_content(item.interpretation, source, instrument)
            if item.technical_available_at != source.available_at:
                raise ValueError("retained technical availability changed")
        if self._committed[1]:
            # Semantic verification is fallible domain work too. Reauthenticate
            # complete provenance after it, while the original locks remain held.
            self._observe_technical_history()
            for source, _, before in resolved:
                _, after = self._authenticate(source)
                if after != before:
                    raise ValueError(
                        "source changed during history semantic verification"
                    )
        return resolved

    @staticmethod
    def _select(
        resolved: tuple[_Resolved, ...],
        request: PolygonCompletedDailyInterpretationRequest,
        started: datetime,
    ) -> _Resolved:
        matches = tuple(item for item in resolved if _reference(item[0]) == request)
        if len(matches) != 1 or matches[0][0].available_at > started:
            raise PolygonCompletedDailyInterpretationRefused(
                _R.TECHNICAL_UNAVAILABLE,
                "exact technical occurrence unavailable by start",
            )
        return matches[0]

    def _recheck_source(
        self,
        request: PolygonCompletedDailyInterpretationRequest,
        started: datetime,
        source: t.PolygonCompletedDailyTechnicalResult,
        expected: dict[str, object],
    ) -> None:
        resolved, _, projection = self._resolve(request, started)
        if resolved is not source or projection != expected:
            raise ValueError("authenticated source changed during Interpretation")

    def execute(
        self, request: PolygonCompletedDailyInterpretationRequest
    ) -> PolygonCompletedDailyInterpretationResult:
        if type(request) is not PolygonCompletedDailyInterpretationRequest:
            raise TypeError("only exact Interpretation selector requests are accepted")
        request = replace(request)
        reason = _R.TEMPORAL_FAILURE
        try:
            started = a._timestamp(self._clock())
            with ExitStack() as stack:
                self._lock_inputs(stack)
                reason = _R.HISTORY_INVALID
                source, instrument, before = self._select(
                    self._check_history(), request, started
                )
                reason = _R.SEMANTIC_FAILED
                content = domain.interpret_governed_daily_technical_snapshot(
                    snapshot=source.snapshot,
                    source_technical_occurrence=replace(request),
                    canonical_instrument=deepcopy(instrument),
                    source_governed_dataset_fingerprint=source.source.dataset_fingerprint,
                )
                _check_content(content, source, instrument)
                content_before = deepcopy(content.to_dict())
                reason = _R.SOURCE_MISMATCH
                self._recheck_source(request, started, source, before)
                reason = _R.TEMPORAL_FAILURE
                completed = a._timestamp(self._clock())
                if completed < started:
                    raise ValueError("Interpretation completion clock moved backward")
                reason = _R.PUBLICATION_FAILED
                return self._publish(
                    request,
                    source,
                    instrument,
                    before,
                    content,
                    content_before,
                    started,
                    completed,
                )
        except PolygonCompletedDailyInterpretationRefused:
            raise
        except Exception as error:
            raise PolygonCompletedDailyInterpretationRefused(
                reason, str(error)
            ) from error

    def _publish(
        self,
        request: PolygonCompletedDailyInterpretationRequest,
        source: t.PolygonCompletedDailyTechnicalResult,
        instrument: CanonicalInstrument,
        source_before: dict[str, object],
        content: GovernedDailyTechnicalInterpretation,
        content_before: dict[str, object],
        started: datetime,
        completed: datetime,
    ) -> PolygonCompletedDailyInterpretationResult:
        owner = self._history_owner
        state = owner._state
        sequence, entries = state
        staged = object.__new__(PolygonCompletedDailyInterpretationResult)
        values: dict[str, object] = {
            "interpretation": deepcopy(content),
            "technical_available_at": source.available_at,
            "execution_id": f"{_PREFIX}:{uuid4().hex}",
            "history_namespace_id": self._namespace,
            "history_sequence": sequence,
            "execution_started_at": started,
            "execution_completed_at": completed,
            "available_at": completed,
        }
        for name, value in values.items():
            object.__setattr__(staged, name, value)
        object.__setattr__(
            staged, "fingerprint", canonical_fingerprint(staged._payload())
        )
        expected = staged.to_dict()
        if staged.interpretation.to_dict() != content_before:
            raise ValueError("content changed during staging copy")
        try:
            owner._stage_publication(staged)
            if owner._pending is not staged or staged.to_dict() != expected:
                raise ValueError("staging changed Interpretation")
            available = a._timestamp(self._clock())
            if available < completed or (
                entries and available < _reconstruct_result(entries[-1]).available_at
            ):
                raise PolygonCompletedDailyInterpretationRefused(
                    _R.TEMPORAL_FAILURE,
                    "Interpretation publication clock moved backward",
                )
            published = deepcopy(staged)
            object.__setattr__(published, "available_at", available)
            object.__setattr__(
                published, "fingerprint", canonical_fingerprint(published._payload())
            )
            expected["available_at"] = available.isoformat()
            expected.pop("fingerprint")
            expected["fingerprint"] = canonical_fingerprint(expected)
            if published.to_dict() != expected or any(
                _reconstruct_result(item).execution_id == published.execution_id
                for item in entries
            ):
                raise ValueError(
                    "publication changed content/occurrence or duplicated ID"
                )
            fact = _encode_result(published)
            public = _public_result_copy(published)
            _check_copy(public, published, expected)
            if _graph_ids(staged) & _graph_ids(published):
                raise ValueError("staging aliases authoritative publication")
            next_state = sequence + 1, (*entries, fact)
            _check_content(published.interpretation, source, instrument)
            if _encode_result(public) != fact or _encode_result(published) != fact:
                raise ValueError("prepared Interpretation bytes changed")
            # All fallible work remains before the single authoritative append.
            resolved, _, projection = self._select(
                self._check_history(), request, started
            )
            if resolved is not source or projection != source_before:
                raise ValueError("source changed during publication")
            if self._history is not owner or owner._state is not state:
                raise ValueError("history changed during publication")
            _check_copy(public, published, expected)
            self._committed = next_state
            owner._state = next_state
            return public
        finally:
            owner._pending = None

    def get_result_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference
        | domain.GovernedTechnicalArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyInterpretationResult, ...]:
        reference = domain._copy_artifact(artifact_reference)
        cutoff = a._timestamp(knowledge_as_of)
        reason = _R.HISTORY_INVALID
        try:
            with ExitStack() as stack:
                self._lock_inputs(stack)
                self._check_history()
                reason = _R.PUBLICATION_FAILED
                copies = []
                for fact in self._history_owner._state[1]:
                    item = _reconstruct_result(fact)
                    if (
                        item.source_technical_occurrence.artifact_reference == reference
                        and item.available_at <= cutoff
                    ):
                        expected = item.to_dict()
                        public = _public_result_copy(item)
                        _check_copy(public, item, expected)
                        copies.append((public, item, expected))
                reason = _R.HISTORY_INVALID
                self._check_history()
                reason = _R.PUBLICATION_FAILED
                for public, item, expected in copies:
                    _check_copy(public, item, expected)
                return tuple(public for public, _, _ in copies)
        except Exception as error:
            raise PolygonCompletedDailyInterpretationRefused(
                reason, str(error)
            ) from error


__all__ = [
    "PolygonCompletedDailyInterpretationRefusalReason",
    "PolygonCompletedDailyInterpretationRefused",
    "PolygonCompletedDailyInterpretationRequest",
    "PolygonCompletedDailyInterpretationResult",
    "PolygonCompletedDailyProductionInterpretationApplicationService",
]
