"""Closed production governance definitions for Polygon completed-daily use."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.evidence.authorization import (
    _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,
    EvidenceContractAuthorization,
)
from market_platform.evidence.policy import (
    EvidenceAdmissionRuleSet,
    EvidenceValidationRequirement,
)
from market_platform.evidence.references import EvidenceIdentityReference
from market_platform.evidence.temporal import EvidenceFreshnessRule
from market_platform.evidence.validation import EvidenceValidationConcern
from market_platform.evidence_ingress.polygon_completed_daily_ohlcv import _PRODUCER
from market_platform.research.technical_analysis import (
    construct_daily_technical_analysis_profile,
)

_VERSION = "1.0.0"
_SCOPE = "research.daily_technical.completed_daily"
_PROFILE_SCHEMA = "polygon_completed_daily_production_governance_profile/v1"
_DEFINITION_SCHEMA = "polygon_completed_daily_closed_definition/v1"
_VALIDATION_SCHEMA = "polygon_completed_daily_validation_definition/v1"
_FRESHNESS_SCHEMA = "polygon_completed_daily_freshness_definition/v1"
_IDENTITY_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,255}", flags=re.ASCII)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)

type _ConfigurationValue = str | int | bool | None | tuple[str, ...]
type _Configuration = tuple[tuple[str, _ConfigurationValue], ...]


class _FingerprintedDefinition:
    schema_version: str
    fingerprint: str

    def _fingerprint_payload(self) -> dict[str, object]:
        raise NotImplementedError

    def _set_fingerprint(self) -> None:
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _validate_fingerprint(self, expected_schema: str, owner: str) -> None:
        if self.schema_version != expected_schema:
            raise ValueError(f"{owner} schema is invalid")
        if _fingerprint(self.fingerprint, f"{owner} fingerprint") != (
            canonical_fingerprint(self._fingerprint_payload())
        ):
            raise ValueError(f"{owner} fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        payload = self._fingerprint_payload()
        self._validate()
        return {**payload, "fingerprint": self.fingerprint}

    def _validate(self) -> None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class _ClosedDefinition(_FingerprintedDefinition):
    definition_kind: str
    definition_id: str
    definition_version: str
    scope: str
    configuration: _Configuration
    schema_version: str = field(init=False, default=_DEFINITION_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "definition_kind", _identity(self.definition_kind))
        object.__setattr__(self, "definition_id", _identity(self.definition_id))
        object.__setattr__(self, "definition_version", _text(self.definition_version))
        object.__setattr__(self, "scope", _identity(self.scope))
        object.__setattr__(self, "configuration", _configuration(self.configuration))
        self._set_fingerprint()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "definition_kind": self.definition_kind,
            "definition_id": self.definition_id,
            "definition_version": self.definition_version,
            "scope": self.scope,
            "configuration": _project_configuration(self.configuration),
        }

    def _validate(self) -> None:
        _identity(self.definition_kind)
        _identity(self.definition_id)
        _text(self.definition_version)
        _identity(self.scope)
        _configuration(self.configuration)
        self._validate_fingerprint(_DEFINITION_SCHEMA, "closed definition")

    def get(self, name: str) -> _ConfigurationValue:
        self._validate()
        try:
            return dict(self.configuration)[name]
        except KeyError as exc:
            raise KeyError(f"definition has no configuration value {name}") from exc


@dataclass(frozen=True, slots=True)
class _ValidationRuleDefinition(_FingerprintedDefinition):
    requirement: EvidenceValidationRequirement
    semantic_requirements: tuple[str, ...]
    exclusions: tuple[str, ...]
    schema_version: str = field(init=False, default=_VALIDATION_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.requirement) is not EvidenceValidationRequirement:
            raise TypeError("requirement must be an EvidenceValidationRequirement")
        self.requirement.to_dict()
        object.__setattr__(
            self, "semantic_requirements", _string_tuple(self.semantic_requirements)
        )
        object.__setattr__(self, "exclusions", _string_tuple(self.exclusions))
        self._set_fingerprint()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "requirement": self.requirement.to_dict(),
            "semantic_requirements": list(self.semantic_requirements),
            "exclusions": list(self.exclusions),
        }

    def _validate(self) -> None:
        if type(self.requirement) is not EvidenceValidationRequirement:
            raise ValueError("validation requirement type is invalid")
        self.requirement.to_dict()
        _string_tuple(self.semantic_requirements)
        _string_tuple(self.exclusions)
        self._validate_fingerprint(_VALIDATION_SCHEMA, "validation definition")


@dataclass(frozen=True, slots=True)
class _FreshnessRuleDefinition(_FingerprintedDefinition):
    rule: EvidenceFreshnessRule
    configuration: _Configuration
    schema_version: str = field(init=False, default=_FRESHNESS_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.rule) is not EvidenceFreshnessRule:
            raise TypeError("rule must be an EvidenceFreshnessRule")
        self.rule.to_dict()
        object.__setattr__(self, "configuration", _configuration(self.configuration))
        self._set_fingerprint()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rule": self.rule.to_dict(),
            "configuration": self._configuration_payload(),
        }

    def _configuration_payload(self) -> dict[str, object]:
        return _project_configuration(self.configuration)

    def _validate(self) -> None:
        if type(self.rule) is not EvidenceFreshnessRule:
            raise ValueError("freshness rule type is invalid")
        self.rule.to_dict()
        _configuration(self.configuration)
        self._validate_fingerprint(_FRESHNESS_SCHEMA, "freshness definition")

    def get(self, name: str) -> _ConfigurationValue:
        self._validate()
        try:
            return dict(self.configuration)[name]
        except KeyError as exc:
            raise KeyError(f"freshness definition has no value {name}") from exc


@dataclass(frozen=True, slots=True)
class _ProductionGovernanceProfile(_FingerprintedDefinition):
    profile_id: str
    profile_version: str
    scope: str
    construction_authorization: EvidenceContractAuthorization
    construction_producer: EvidenceIdentityReference
    validation_definitions: tuple[_ValidationRuleDefinition, ...]
    admission_ruleset: EvidenceAdmissionRuleSet
    admission_freshness: _FreshnessRuleDefinition
    task_freshness: _FreshnessRuleDefinition
    initial_validity: _ClosedDefinition
    consumer: _ClosedDefinition
    use: _ClosedDefinition
    analysis_profile: _ClosedDefinition
    transformation: _ClosedDefinition
    schema_version: str = field(init=False, default=_PROFILE_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _identity(self.profile_id))
        object.__setattr__(self, "profile_version", _text(self.profile_version))
        object.__setattr__(self, "scope", _identity(self.scope))
        self._validate_constituent_types()
        self._set_fingerprint()

    def _validate_constituent_types(self) -> None:
        if type(self.construction_authorization) is not EvidenceContractAuthorization:
            raise TypeError("construction authorization type is invalid")
        if type(self.construction_producer) is not EvidenceIdentityReference:
            raise TypeError("construction producer type is invalid")
        if type(self.validation_definitions) is not tuple or not (
            self.validation_definitions
        ):
            raise TypeError("validation definitions must be a nonempty exact tuple")
        if any(
            type(item) is not _ValidationRuleDefinition
            for item in self.validation_definitions
        ):
            raise TypeError("validation definition type is invalid")
        concerns = tuple(
            item.requirement.concern for item in self.validation_definitions
        )
        if len(set(concerns)) != len(concerns):
            raise ValueError("validation definitions must not duplicate a concern")
        if type(self.admission_ruleset) is not EvidenceAdmissionRuleSet:
            raise TypeError("admission ruleset type is invalid")
        if (
            type(self.admission_freshness) is not _FreshnessRuleDefinition
            or type(self.task_freshness) is not _FreshnessRuleDefinition
        ):
            raise TypeError("freshness definition type is invalid")
        for value in (
            self.initial_validity,
            self.consumer,
            self.use,
            self.analysis_profile,
            self.transformation,
        ):
            if type(value) is not _ClosedDefinition:
                raise TypeError("closed constituent definition type is invalid")

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "scope": self.scope,
            "construction_authorization": self.construction_authorization.to_dict(),
            "construction_producer": self.construction_producer.to_dict(),
            "validation_definitions": [
                item.to_dict() for item in self.validation_definitions
            ],
            "admission_ruleset": self.admission_ruleset.to_dict(),
            "admission_freshness": self.admission_freshness.to_dict(),
            "task_freshness": self.task_freshness.to_dict(),
            "initial_validity": self.initial_validity.to_dict(),
            "consumer": self.consumer.to_dict(),
            "use": self.use.to_dict(),
            "analysis_profile": self.analysis_profile.to_dict(),
            "transformation": self.transformation.to_dict(),
        }

    def _validate(self) -> None:
        _identity(self.profile_id)
        _text(self.profile_version)
        _identity(self.scope)
        self._validate_constituent_types()
        self.construction_authorization.to_dict()
        self.construction_producer.to_dict()
        for item in self.validation_definitions:
            item._validate()
        self.admission_ruleset.to_dict()
        self.admission_freshness._validate()
        self.task_freshness._validate()
        for value in (
            self.initial_validity,
            self.consumer,
            self.use,
            self.analysis_profile,
            self.transformation,
        ):
            value._validate()
        self._validate_fingerprint(_PROFILE_SCHEMA, "production governance profile")


@dataclass(frozen=True, slots=True)
class _ProductionGovernanceApprovalCatalog:
    profiles: tuple[_ProductionGovernanceProfile, ...]

    def __post_init__(self) -> None:
        if type(self.profiles) is not tuple or not self.profiles:
            raise TypeError("approved profiles must be a nonempty exact tuple")
        for profile in self.profiles:
            if type(profile) is not _ProductionGovernanceProfile:
                raise TypeError("approved profile type is invalid")
            profile._validate()
        if len({profile.fingerprint for profile in self.profiles}) != len(
            self.profiles
        ):
            raise ValueError("approved profiles must not contain duplicates")

    def resolve(
        self, profile: _ProductionGovernanceProfile
    ) -> _ProductionGovernanceProfile:
        if type(profile) is not _ProductionGovernanceProfile:
            raise TypeError("profile must use the exact production profile type")
        profile._validate()
        for approved in self.profiles:
            if profile.fingerprint == approved.fingerprint and profile == approved:
                return replace(approved)
        raise ValueError("production Evidence governance profile is not approved")


def _identity(value: object) -> str:
    if type(value) is not str or _IDENTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("value must be a canonical governance identity")
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(
            "value must be a nonempty exact string without edge whitespace"
        )
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("value must be a nonempty exact tuple")
    result = tuple(_text(item) for item in cast(tuple[object, ...], value))
    if len(set(result)) != len(result):
        raise ValueError("tuple must not contain duplicates")
    return result


def _configuration(value: object) -> _Configuration:
    if type(value) is not tuple or not value:
        raise TypeError("configuration must be a nonempty exact tuple")
    result: list[tuple[str, _ConfigurationValue]] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not tuple or len(item) != 2:
            raise TypeError("configuration entries must be exact name/value tuples")
        name, raw = cast(tuple[object, object], item)
        key = _identity(name)
        if type(raw) is tuple:
            normalized: _ConfigurationValue = _string_tuple(raw)
        elif raw is None or type(raw) in (str, int, bool):
            normalized = (
                _text(raw) if type(raw) is str else cast(int | bool | None, raw)
            )
        else:
            raise TypeError("configuration values must be canonical scalar or tuples")
        result.append((key, normalized))
    if len({name for name, _ in result}) != len(result):
        raise ValueError("configuration names must be unique")
    return tuple(sorted(result, key=lambda item: item[0]))


def _project_configuration(value: _Configuration) -> dict[str, object]:
    return {
        name: list(item) if type(item) is tuple else item
        for name, item in _configuration(value)
    }


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _validation(
    concern: EvidenceValidationConcern,
    rule_id: str,
    requirements: tuple[str, ...],
    exclusions: tuple[str, ...],
) -> _ValidationRuleDefinition:
    return _ValidationRuleDefinition(
        EvidenceValidationRequirement(concern, _SCOPE, rule_id, _VERSION),
        requirements,
        exclusions,
    )


_VALIDATION_DEFINITIONS = (
    _validation(
        EvidenceValidationConcern.AUTHORITY,
        "production.polygon_completed_daily.validation.authority",
        (
            "exact_released_construction_authorization_membership",
            "exact_authority_information_class_and_governance_scope",
        ),
        ("downstream_research_permission", "authority_class_promotion"),
    ),
    _validation(
        EvidenceValidationConcern.FRESHNESS_CONTRACT,
        "production.polygon_completed_daily.validation.freshness_contract",
        ("material_and_temporal_contract_supports_both_exact_freshness_rules",),
        ("freshness_outcome_issuance",),
    ),
    _validation(
        EvidenceValidationConcern.IDENTITY,
        "production.polygon_completed_daily.validation.identity",
        (
            "exact_artifact_material_source_contract_subject_and_mapping_identity",
            "recomputable_evidence_identity_correspondence",
        ),
        ("source_truth", "research_permission"),
    ),
    _validation(
        EvidenceValidationConcern.INTEGRITY,
        "production.polygon_completed_daily.validation.integrity",
        ("exact_retained_material_artifact_and_fingerprint_correspondence",),
        ("material_repair", "material_mutation"),
    ),
    _validation(
        EvidenceValidationConcern.PROVENANCE,
        "production.polygon_completed_daily.validation.provenance",
        (
            "exact_retained_source_request_producer_mapping_and_construction_provenance",
            "approved_trusted_construction_lineage",
        ),
        ("invented_unretained_provenance",),
    ),
    _validation(
        EvidenceValidationConcern.SCHEMA,
        "production.polygon_completed_daily.validation.schema",
        ("exact_material_v1_row_dates_numeric_strings_and_structural_metadata",),
        ("schema_repair", "implicit_schema_upgrade"),
    ),
    _validation(
        EvidenceValidationConcern.SOURCE_QUALITY,
        "production.polygon_completed_daily.validation.source_quality",
        (
            "retained_material_nonempty",
            "ohlcv_exact_numeric_values_finite",
            "ohlc_strictly_positive",
            "volume_zero_or_positive",
            "high_not_below_low",
            "open_between_low_and_high_inclusive",
            "close_between_low_and_high_inclusive",
            "session_dates_unique",
            "session_dates_strictly_increasing",
        ),
        (
            "float_conversion_limits",
            "market_ranking_or_plausibility",
            "expected_exchange_session_completeness",
            "minimum_history_for_complete_technical_analysis",
        ),
    ),
    _validation(
        EvidenceValidationConcern.TEMPORAL_COHERENCE,
        "production.polygon_completed_daily.validation.temporal_coherence",
        (
            "requested_interval_completed_date_ordering_and_temporal_coherence",
            "retained_execution_time_support",
        ),
        ("carried_timestamps_self_authenticate_availability",),
    ),
)

_FRESHNESS_CONFIGURATION: _Configuration = (
    ("completion_basis", "retained_session_date_strictly_before_new_york_civil_date"),
    ("expected_session_calendar", None),
    (
        "excluded_decisions",
        (
            "historical_instrument_mapping_coverage",
            "consumer_authorization",
            "bridge_convertibility",
            "research_history_sufficiency_or_analyzer_quality",
            "canonical_lifecycle_consumability",
        ),
    ),
    ("holiday_exception_extension", None),
    ("market_timezone", "America/New_York"),
    ("maximum_calendar_lag_days", 4),
    ("maximum_lag_inclusive", True),
    ("minimum_calendar_lag_days", 1),
    (
        "predicate_semantics",
        "recency_not_exchange_session_completeness__greatest_eligible_retained_date_"
        "exists_and_calendar_lag_is_between_1_and_4_inclusive",
    ),
    ("publication_time_inference", "prohibited"),
)


def _freshness(rule_id: str) -> _FreshnessRuleDefinition:
    return _FreshnessRuleDefinition(
        EvidenceFreshnessRule(
            rule_id,
            _VERSION,
            "latest_retained_completed_session_date",
            _SCOPE,
        ),
        _FRESHNESS_CONFIGURATION,
    )


_ADMISSION_FRESHNESS = _freshness(
    "production.polygon_completed_daily.freshness.admission"
)
_TASK_FRESHNESS = _freshness(
    "production.polygon_completed_daily.freshness.daily_technical"
)
_ADMISSION_RULESET = EvidenceAdmissionRuleSet(
    "production.polygon_completed_daily.admission.daily_technical",
    _VERSION,
    _SCOPE,
    tuple(item.requirement for item in _VALIDATION_DEFINITIONS),
    True,
    _ADMISSION_FRESHNESS.rule,
    True,
    _TASK_FRESHNESS.rule,
    True,
)


def _closed(
    kind: str, definition_id: str, configuration: _Configuration
) -> _ClosedDefinition:
    return _ClosedDefinition(kind, definition_id, _VERSION, _SCOPE, configuration)


_INITIAL_VALIDITY = _closed(
    "initial_validity",
    "production.polygon_completed_daily.validity.initial_active",
    (
        (
            "semantic_requirements",
            (
                "separate_from_admission",
                "exact_artifact_and_scope",
                "authentic_admitted_prerequisite",
                "actual_admission_availability_before_activation",
                "complete_initial_validity_history",
                "approved_platform_execution",
                "no_automatic_reactivation_of_terminal_validity",
            ),
        ),
    ),
)
_CONSUMER = _closed(
    "consumer",
    "market_platform.research.daily_technical",
    (("consumer_kind", "daily_technical_research"),),
)
_RELEASED_ANALYSIS_PROFILE = construct_daily_technical_analysis_profile()
_ANALYSIS_PROFILE = _closed(
    "analysis_profile",
    _RELEASED_ANALYSIS_PROFILE.profile_id,
    (
        ("profile_schema_version", _RELEASED_ANALYSIS_PROFILE.schema_version),
        ("profile_fingerprint", _RELEASED_ANALYSIS_PROFILE.fingerprint),
    ),
)
_TRANSFORMATION = _closed(
    "transformation",
    "production.polygon_completed_daily.transform.completed_daily_price_series",
    (
        (
            "date_label_non_temporal_meanings",
            (
                "not_publication_time",
                "not_source_observation_time",
                "not_market_close_time",
                "not_availability_time",
            ),
        ),
        ("date_conversion", "canonical_session_date_to_same_date_midnight_utc"),
        (
            "input_material_schema_fingerprint",
            _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION.contract_definition.material_schema.fingerprint,
        ),
        (
            "input_semantics",
            "entire_retained_polygon_completed_daily_ohlcv_material_v1",
        ),
        ("intermediate_row_removal", "refuse_governed_use"),
        ("no_drop_basis", "retained_governed_material"),
        ("numeric_conversion", "canonical_exact_decimal_direct_to_binary64"),
        (
            "numeric_preconditions",
            (
                "ohlc_strictly_positive",
                "volume_zero_or_positive",
                "nonzero_input_within_supported_positive_normal_binary64_range",
            ),
        ),
        ("numeric_result", "finite_normal_sign_preserving"),
        (
            "output_type",
            "market_platform.research.daily_evidence.CompletedDailyPriceSeries",
        ),
        (
            "prohibited_operations",
            (
                "display_rounding",
                "intermediate_quantization",
                "clipping",
                "imputation",
                "repair",
                "rescaling",
            ),
        ),
        (
            "refusal_conditions",
            (
                "non_finite",
                "overflow",
                "unsupported_subnormal",
                "destructive_underflow_or_nonzero_to_zero",
                "unsupported_date_representation",
            ),
        ),
        ("rounding_mode", "round_to_nearest_ties_to_even"),
        ("subset_selection_authorized", False),
        ("supported_first_date", "1677-09-22"),
        ("supported_last_date", "2262-04-11"),
        ("zero_volume_result", "positive_zero"),
    ),
)
_USE = _closed(
    "use",
    "production.polygon_completed_daily.use.daily_technical",
    (
        ("analysis_profile_definition_fingerprint", _ANALYSIS_PROFILE.fingerprint),
        ("consumer_definition_fingerprint", _CONSUMER.fingerprint),
        (
            "semantic_requirements",
            (
                "canonical_EvidenceAdmissionState.is_consumable",
                "exact_task_freshness_rule",
                "historical_all_row_mapping_coverage",
                "whole_material_completion_for_exact_analysis_cutoff",
                "end_to_end_no_drop_correspondence",
                "exact_approved_bridge_transformation",
            ),
        ),
        ("task_freshness_definition_fingerprint", _TASK_FRESHNESS.fingerprint),
        ("transformation_definition_fingerprint", _TRANSFORMATION.fingerprint),
    ),
)

_POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE = _ProductionGovernanceProfile(
    "production.polygon_completed_daily.daily_technical",
    _VERSION,
    _SCOPE,
    _POLYGON_COMPLETED_DAILY_OHLCV_AUTHORIZATION,
    _PRODUCER,
    _VALIDATION_DEFINITIONS,
    _ADMISSION_RULESET,
    _ADMISSION_FRESHNESS,
    _TASK_FRESHNESS,
    _INITIAL_VALIDITY,
    _CONSUMER,
    _USE,
    _ANALYSIS_PROFILE,
    _TRANSFORMATION,
)
_PRODUCTION_GOVERNANCE_APPROVAL_CATALOG = _ProductionGovernanceApprovalCatalog(
    (_POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE,)
)


def _resolve_approved_polygon_completed_daily_production_profile(
    profile: _ProductionGovernanceProfile,
) -> _ProductionGovernanceProfile:
    return _PRODUCTION_GOVERNANCE_APPROVAL_CATALOG.resolve(profile)


__all__: list[str] = []
