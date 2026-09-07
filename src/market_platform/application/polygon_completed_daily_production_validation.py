"""Trusted production validation for Polygon completed-daily Evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from threading import Lock
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.polygon_completed_daily_evidence_candidate import (
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
)
from market_platform.application.polygon_completed_daily_production_construction import (  # noqa: E501
    PolygonCompletedDailyConstructionExecutionReceipt,
    PolygonCompletedDailyConstructionHistoryError,
    PolygonCompletedDailyProductionConstructionApplicationService,
    PolygonCompletedDailyProductionConstructionResult,
    _request_fingerprint,
    _result_content_fingerprint,
)
from market_platform.application.polygon_completed_daily_production_governance import (
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE,
    _ProductionGovernanceProfile,
    _resolve_approved_polygon_completed_daily_production_profile,
    _ValidationRuleDefinition,
)
from market_platform.evidence.classification import (
    EvidenceAuthority,
    EvidenceInformationClass,
)
from market_platform.evidence.models import EvidenceArtifact
from market_platform.evidence.policy import EvidenceValidationRequirement
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
    EvidenceSubjectReference,
)
from market_platform.evidence.validation import (
    EvidenceValidationConcern,
    EvidenceValidationDisposition,
    EvidenceValidationRecord,
    EvidenceValidationRecordReference,
    create_evidence_validation_record,
)
from market_platform.evidence_ingress import polygon_completed_daily_ohlcv as ingress
from market_platform.evidence_ingress.polygon_completed_daily_ohlcv import (
    MAX_CANONICAL_NUMERIC_TEXT_LENGTH,
    PolygonCompletedDailyOhlcvMaterial,
    PolygonCompletedDailyOhlcvMaterialRow,
    _canonical_numeric_text,
    _PolygonCompletedDailyOhlcvRequestProvenance,
)
from market_platform.instruments import (
    CANONICAL_INSTRUMENT_SCHEMA_VERSION,
    ExternalInstrumentIdentity,
    InstrumentResolution,
)

_VERSION = "1.0.0"
_PACKAGE_VERSION = "0.1.0"
_SCHEMA = "polygon_completed_daily_validation_execution/v1"
_SUPPORT_SCHEMA = "polygon_completed_daily_validation_support/v1"
_RECORD_ID_SCHEMA = "polygon_completed_daily_validation_record_identity/v1"
_OPERATION_SCHEMA = "polygon_completed_daily_validation_operation/v1"
_VALIDATOR_SCHEMA = "polygon_completed_daily_validation_actor/v1"
_CAPABILITY_SCHEMA = "polygon_completed_daily_validation_capability/v1"
_EXECUTOR_SCHEMA = "market_platform_software_executor/v1"
_PROFILE_REFERENCE_NAMESPACE = "market_platform.production_governance_profile"
_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_validation:[0-9a-f]{32}", flags=re.ASCII
)
_CONSTRUCTION_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_construction:[0-9a-f]{32}", flags=re.ASCII
)
_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_validation_history:[0-9a-f]{32}", flags=re.ASCII
)
_CONSTRUCTION_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_construction_history:[0-9a-f]{32}", flags=re.ASCII
)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_MARKET_TIMEZONE = ZoneInfo("America/New_York")
_COMPANION_SEAL = object()
_RESULT_SEAL = object()
_HISTORY_SEAL = object()

_PROFILE = _resolve_approved_polygon_completed_daily_production_profile(
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
)
_PROFILE_REFERENCE = EvidenceIdentityReference(
    namespace=_PROFILE_REFERENCE_NAMESPACE,
    identity_id=_PROFILE.profile_id,
    identity_version=_PROFILE.profile_version,
    identity_fingerprint=_PROFILE.fingerprint,
)
_VALIDATOR = EvidenceIdentityReference(
    namespace="market_platform.evidence_validator",
    identity_id="polygon_completed_daily_production_validation",
    identity_version=_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _VALIDATOR_SCHEMA,
            "validator_id": "polygon_completed_daily_production_validation",
            "validator_version": _VERSION,
            "production_profile_fingerprint": _PROFILE.fingerprint,
        }
    ),
)
_CAPABILITY = EvidenceIdentityReference(
    namespace="market_platform.application.capability",
    identity_id="validate_polygon_completed_daily_production_evidence",
    identity_version=_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _CAPABILITY_SCHEMA,
            "capability_id": ("validate_polygon_completed_daily_production_evidence"),
            "capability_version": _VERSION,
            "scope": _PROFILE.scope,
            "production_profile_fingerprint": _PROFILE.fingerprint,
        }
    ),
)
_EXECUTOR = EvidenceIdentityReference(
    namespace="market_platform.software",
    identity_id="market_platform",
    identity_version=_PACKAGE_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _EXECUTOR_SCHEMA,
            "software_id": "market_platform",
            "software_version": _PACKAGE_VERSION,
        }
    ),
)


class PolygonCompletedDailyValidationRefusalReason(StrEnum):
    """Stable reasons why no trusted validation record was published."""

    TRUSTED_CONSTRUCTION_UNAVAILABLE = "trusted_construction_unavailable"
    ARTIFACT_TARGET_MISMATCH = "artifact_target_mismatch"
    POLICY_REQUIREMENT_MISMATCH = "policy_requirement_mismatch"
    TEMPORAL_EXECUTION_FAILURE = "temporal_execution_failure"
    HISTORY_CONFLICT_OR_CORRUPTION = "history_conflict_or_corruption"


class PolygonCompletedDailyValidationExecutionRefused(RuntimeError):
    """The supported operation refused to publish validation history."""

    reason: PolygonCompletedDailyValidationRefusalReason

    def __init__(
        self, reason: PolygonCompletedDailyValidationRefusalReason, message: str
    ) -> None:
        if type(reason) is not PolygonCompletedDailyValidationRefusalReason:
            raise TypeError("reason must be a validation refusal reason")
        self.reason = reason
        super().__init__(message)


class PolygonCompletedDailyValidationHistoryError(RuntimeError):
    """Trusted validation history is incomplete or internally inconsistent."""


class PolygonCompletedDailyValidationHistoryConflictError(
    PolygonCompletedDailyValidationHistoryError
):
    """Retained validation facts conflict for one exact history query."""


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyValidationRequest:
    """Permitted intent for the exact closed eight-concern profile."""

    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            _copy_artifact_reference(self.artifact_reference),
        )
        object.__setattr__(
            self,
            "construction_execution_id",
            _construction_execution_id(self.construction_execution_id),
        )

    def _validate(self) -> None:
        _copy_artifact_reference(self.artifact_reference)
        _construction_execution_id(self.construction_execution_id)


@dataclass(frozen=True, slots=True)
class _ValidationSupport:
    """Shared immutable facts; it deliberately carries no rule disposition."""

    construction_result: PolygonCompletedDailyProductionConstructionResult
    receipt: PolygonCompletedDailyConstructionExecutionReceipt | None
    request: PolygonCompletedDailyEvidenceCandidateApplicationRequest | None
    artifact: EvidenceArtifact | None
    material: PolygonCompletedDailyOhlcvMaterial | None
    mapping_resolution: InstrumentResolution | None
    approved_profile: _ProductionGovernanceProfile | None


@dataclass(frozen=True, slots=True)
class _RuleConclusion:
    disposition: EvidenceValidationDisposition
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyValidationExecutionCompanion:
    """Occurrence provenance for one canonical validation lifecycle record."""

    execution_id: str
    history_sequence: int
    history_namespace_id: str
    operation: EvidenceIdentityReference
    executor: EvidenceIdentityReference
    validator: EvidenceIdentityReference
    validator_capability: EvidenceIdentityReference
    production_profile_reference: EvidenceIdentityReference
    production_profile_fingerprint: str
    validation_requirement: EvidenceValidationRequirement
    validation_definition_fingerprint: str
    construction_history_namespace_id: str
    construction_history_sequence: int
    construction_execution_id: str
    construction_receipt_fingerprint: str
    construction_result_content_fingerprint: str
    artifact_reference: EvidenceArtifactReference
    material_fingerprint: str
    request_fingerprint: str
    resolved_mapping_fingerprint: str
    construction_authorization_fingerprint: str
    trusted_support_fingerprint: str
    validation_reference: EvidenceValidationRecordReference
    disposition: EvidenceValidationDisposition
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyValidationExecutionCompanion is issued only by "
            "trusted production validation history"
        )

    @classmethod
    def _create(
        cls,
        *,
        execution_id: str,
        history_sequence: int,
        history_namespace_id: str,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        definition: _ValidationRuleDefinition,
        validation_record: EvidenceValidationRecord,
        execution_started_at: datetime,
        execution_completed_at: datetime,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyValidationExecutionCompanion:
        if seal is not _COMPANION_SEAL:
            raise TypeError("validation execution companion issuance is private")
        receipt = _authentic_receipt(construction_result)
        companion = object.__new__(cls)
        values: dict[str, object] = {
            "execution_id": _execution_id(execution_id),
            "history_sequence": _positive_integer(history_sequence, "history_sequence"),
            "history_namespace_id": _history_namespace_id(history_namespace_id),
            "operation": _copy_identity_reference(_operation(definition)),
            "executor": _copy_identity_reference(_EXECUTOR),
            "validator": _copy_identity_reference(_VALIDATOR),
            "validator_capability": _copy_identity_reference(_CAPABILITY),
            "production_profile_reference": _copy_identity_reference(
                _PROFILE_REFERENCE
            ),
            "production_profile_fingerprint": _PROFILE.fingerprint,
            "validation_requirement": _copy_requirement(definition.requirement),
            "validation_definition_fingerprint": definition.fingerprint,
            "construction_history_namespace_id": receipt.history_namespace_id,
            "construction_history_sequence": receipt.history_sequence,
            "construction_execution_id": receipt.execution_id,
            "construction_receipt_fingerprint": receipt.fingerprint,
            "construction_result_content_fingerprint": (
                receipt.result_content_fingerprint
            ),
            "artifact_reference": _copy_artifact_reference(receipt.artifact_reference),
            "material_fingerprint": receipt.material_fingerprint,
            "request_fingerprint": receipt.request_fingerprint,
            "resolved_mapping_fingerprint": receipt.resolved_mapping_fingerprint,
            "construction_authorization_fingerprint": (
                receipt.construction_authorization.fingerprint
            ),
            "trusted_support_fingerprint": _trusted_support_fingerprint(
                receipt, definition.requirement
            ),
            "validation_reference": _copy_validation_reference(
                validation_record.reference()
            ),
            "disposition": validation_record.disposition,
            "execution_started_at": _timestamp(
                execution_started_at, "execution_started_at"
            ),
            "execution_completed_at": _timestamp(
                execution_completed_at, "execution_completed_at"
            ),
            "available_at": _timestamp(available_at, "available_at"),
            "schema_version": _SCHEMA,
        }
        for name, value in values.items():
            object.__setattr__(companion, name, value)
        object.__setattr__(
            companion,
            "fingerprint",
            canonical_fingerprint(companion._fingerprint_payload()),
        )
        companion._validate()
        return companion

    @classmethod
    def _with_available_at(
        cls,
        staged: PolygonCompletedDailyValidationExecutionCompanion,
        *,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyValidationExecutionCompanion:
        if seal is not _COMPANION_SEAL:
            raise TypeError("validation companion publication is private")
        companion = object.__new__(cls)
        for item in fields(cls):
            if item.name not in {"available_at", "fingerprint"}:
                object.__setattr__(companion, item.name, getattr(staged, item.name))
        object.__setattr__(
            companion, "available_at", _timestamp(available_at, "available_at")
        )
        object.__setattr__(
            companion,
            "fingerprint",
            canonical_fingerprint(companion._fingerprint_payload()),
        )
        companion._validate()
        return companion

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "history_sequence": self.history_sequence,
            "history_namespace_id": self.history_namespace_id,
            "operation": self.operation.to_dict(),
            "executor": self.executor.to_dict(),
            "validator": self.validator.to_dict(),
            "validator_capability": self.validator_capability.to_dict(),
            "production_profile_reference": self.production_profile_reference.to_dict(),
            "production_profile_fingerprint": self.production_profile_fingerprint,
            "validation_requirement": self.validation_requirement.to_dict(),
            "validation_definition_fingerprint": (
                self.validation_definition_fingerprint
            ),
            "construction_history_namespace_id": (
                self.construction_history_namespace_id
            ),
            "construction_history_sequence": self.construction_history_sequence,
            "construction_execution_id": self.construction_execution_id,
            "construction_receipt_fingerprint": (self.construction_receipt_fingerprint),
            "construction_result_content_fingerprint": (
                self.construction_result_content_fingerprint
            ),
            "artifact_reference": self.artifact_reference.to_dict(),
            "material_fingerprint": self.material_fingerprint,
            "request_fingerprint": self.request_fingerprint,
            "resolved_mapping_fingerprint": self.resolved_mapping_fingerprint,
            "construction_authorization_fingerprint": (
                self.construction_authorization_fingerprint
            ),
            "trusted_support_fingerprint": self.trusted_support_fingerprint,
            "validation_reference": self.validation_reference.to_dict(),
            "disposition": self.disposition.value,
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def _validate(self) -> None:
        if self.schema_version != _SCHEMA:
            raise ValueError("validation companion schema is invalid")
        _execution_id(self.execution_id)
        _positive_integer(self.history_sequence, "history_sequence")
        _history_namespace_id(self.history_namespace_id)
        definition = _approved_definition(self.validation_requirement.concern)
        for identity in (
            self.operation,
            self.executor,
            self.validator,
            self.validator_capability,
            self.production_profile_reference,
        ):
            identity._validate()
        if self.operation != _operation(definition):
            raise ValueError("validation operation identity is not approved")
        if self.executor != _EXECUTOR:
            raise ValueError("validation executor identity is not approved")
        if self.validator != _VALIDATOR or self.validator_capability != _CAPABILITY:
            raise ValueError("validation actor/capability identity is not approved")
        if self.production_profile_reference != _PROFILE_REFERENCE:
            raise ValueError("production profile reference is not approved")
        if self.production_profile_fingerprint != _PROFILE.fingerprint:
            raise ValueError("production profile fingerprint is not approved")
        self.validation_requirement._validate()
        if self.validation_requirement != definition.requirement:
            raise ValueError("validation requirement is not approved")
        if self.validation_definition_fingerprint != definition.fingerprint:
            raise ValueError("validation definition fingerprint is not approved")
        _construction_history_namespace_id(self.construction_history_namespace_id)
        _positive_integer(
            self.construction_history_sequence, "construction_history_sequence"
        )
        _construction_execution_id(self.construction_execution_id)
        for name in (
            "construction_receipt_fingerprint",
            "construction_result_content_fingerprint",
            "material_fingerprint",
            "request_fingerprint",
            "resolved_mapping_fingerprint",
            "construction_authorization_fingerprint",
            "trusted_support_fingerprint",
        ):
            _fingerprint(getattr(self, name), name)
        self.artifact_reference._validate()
        self.validation_reference._validate()
        reference = self.validation_reference
        requirement = self.validation_requirement
        if (
            reference.artifact_reference != self.artifact_reference
            or reference.concern is not requirement.concern
            or reference.scope != requirement.scope
            or reference.ruleset_id != requirement.ruleset_id
            or reference.ruleset_version != requirement.ruleset_version
            or reference.disposition is not self.disposition
        ):
            raise ValueError("validation lifecycle reference does not correspond")
        if type(self.disposition) is not EvidenceValidationDisposition:
            raise TypeError("disposition must be an exact validation disposition")
        started = _require_canonical_timestamp(
            self.execution_started_at, "execution_started_at"
        )
        completed = _require_canonical_timestamp(
            self.execution_completed_at, "execution_completed_at"
        )
        available = _require_canonical_timestamp(self.available_at, "available_at")
        if not started <= completed <= available:
            raise ValueError("validation execution chronology is incoherent")
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("validation companion fingerprint is invalid")

    def to_dict(self) -> dict[str, object]:
        """Return the exact source-specific validation execution projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyProductionValidationResult:
    """One lifecycle validation record with authentic occurrence provenance."""

    construction_result: PolygonCompletedDailyProductionConstructionResult
    validation_record: EvidenceValidationRecord
    companion: PolygonCompletedDailyValidationExecutionCompanion

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyProductionValidationResult is created only by "
            "trusted production validation history"
        )

    @classmethod
    def _create(
        cls,
        *,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        validation_record: EvidenceValidationRecord,
        companion: PolygonCompletedDailyValidationExecutionCompanion,
        seal: object,
    ) -> PolygonCompletedDailyProductionValidationResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production validation result creation is private")
        result = object.__new__(cls)
        object.__setattr__(result, "construction_result", construction_result)
        object.__setattr__(result, "validation_record", validation_record)
        object.__setattr__(result, "companion", companion)
        result._validate()
        return result

    @classmethod
    def _with_companion(
        cls,
        staged: PolygonCompletedDailyProductionValidationResult,
        *,
        companion: PolygonCompletedDailyValidationExecutionCompanion,
        seal: object,
    ) -> PolygonCompletedDailyProductionValidationResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production validation result publication is private")
        result = object.__new__(cls)
        object.__setattr__(result, "construction_result", staged.construction_result)
        object.__setattr__(result, "validation_record", staged.validation_record)
        object.__setattr__(result, "companion", companion)
        return result

    def _validate(self) -> None:
        _validate_result_correspondence(
            self.construction_result, self.validation_record, self.companion
        )


class _InMemoryPolygonCompletedDailyValidationHistory:
    """Private complete history for the exact production validation profile."""

    __slots__ = ("_lock", "_namespace_id", "_pending", "_state")

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = _issue_history_namespace_id()
        self._pending: PolygonCompletedDailyProductionValidationResult | None = None
        self._state: tuple[
            int, tuple[PolygonCompletedDailyProductionValidationResult, ...]
        ] = (1, ())

    def _retain(
        self,
        *,
        execution_id: str,
        construction_result: PolygonCompletedDailyProductionConstructionResult,
        definition: _ValidationRuleDefinition,
        conclusion: _RuleConclusion,
        execution_started_at: datetime,
        completion_clock: Callable[[], datetime],
        availability_clock: Callable[[], datetime],
        seal: object,
    ) -> PolygonCompletedDailyProductionValidationResult:
        if seal is not _HISTORY_SEAL:
            raise TypeError("trusted validation history retention is private")
        if not callable(completion_clock) or not callable(availability_clock):
            raise TypeError("completion and availability clocks must be callable")
        support = _derive_support(construction_result)
        expected = _evaluate_definition(definition, support)
        if conclusion != expected:
            raise ValueError("validation conclusion does not match trusted support")
        receipt = _authentic_receipt(construction_result)
        started_at = _timestamp(execution_started_at, "execution_started_at")
        if receipt.available_at > started_at:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "validation execution started before construction became available",
            )
        completed_at = _timestamp(completion_clock(), "execution_completed_at")
        if completed_at < started_at:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                "validation completion precedes execution start",
            )

        with self._lock:
            next_sequence, entries = self._state
            try:
                _validate_retained_entries(
                    entries, expected_namespace_id=self._namespace_id
                )
            except (TypeError, ValueError) as error:
                raise PolygonCompletedDailyValidationHistoryError(
                    "retained validation history is incomplete or corrupt"
                ) from error
            record = _create_validation_record(
                receipt.artifact_reference,
                definition,
                conclusion,
                completed_at=completed_at,
            )
            staged_available_at = max(
                completed_at,
                entries[-1].companion.available_at if entries else completed_at,
            )
            staged_companion = (
                PolygonCompletedDailyValidationExecutionCompanion._create(
                    execution_id=execution_id,
                    history_sequence=next_sequence,
                    history_namespace_id=self._namespace_id,
                    construction_result=construction_result,
                    definition=definition,
                    validation_record=record,
                    execution_started_at=started_at,
                    execution_completed_at=completed_at,
                    available_at=staged_available_at,
                    seal=_COMPANION_SEAL,
                )
            )
            staged = PolygonCompletedDailyProductionValidationResult._create(
                construction_result=construction_result,
                validation_record=record,
                companion=staged_companion,
                seal=_RESULT_SEAL,
            )
            try:
                self._stage_publication(staged)
                available_at = _timestamp(availability_clock(), "available_at")
                if available_at < completed_at:
                    raise PolygonCompletedDailyValidationExecutionRefused(
                        PolygonCompletedDailyValidationRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                        "validation availability precedes execution completion",
                    )
                if entries and available_at < entries[-1].companion.available_at:
                    raise PolygonCompletedDailyValidationExecutionRefused(
                        PolygonCompletedDailyValidationRefusalReason.TEMPORAL_EXECUTION_FAILURE,
                        "validation availability must not move backward",
                    )
                companion = PolygonCompletedDailyValidationExecutionCompanion._with_available_at(  # noqa: E501
                    staged.companion,
                    available_at=available_at,
                    seal=_COMPANION_SEAL,
                )
                retained = (
                    PolygonCompletedDailyProductionValidationResult._with_companion(
                        staged, companion=companion, seal=_RESULT_SEAL
                    )
                )
                retained._validate()
                self._state = (next_sequence + 1, (*entries, retained))
                return retained
            finally:
                self._pending = None

    def _stage_publication(
        self, staged: PolygonCompletedDailyProductionValidationResult
    ) -> None:
        staged._validate()
        self._pending = staged

    def _history(
        self,
        artifact_reference: EvidenceArtifactReference,
        construction_execution_id: str,
        concern: EvidenceValidationConcern,
        *,
        knowledge_as_of: datetime | None,
    ) -> tuple[PolygonCompletedDailyProductionValidationResult, ...]:
        reference = _copy_artifact_reference(artifact_reference)
        construction_id = _construction_execution_id(construction_execution_id)
        definition = _approved_definition(concern)
        cutoff = (
            None
            if knowledge_as_of is None
            else _timestamp(knowledge_as_of, "knowledge_as_of")
        )
        with self._lock:
            entries = self._state[1]
        try:
            _validate_retained_entries(
                entries, expected_namespace_id=self._namespace_id
            )
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyValidationHistoryError(
                "retained validation history is incomplete or corrupt"
            ) from error
        relevant = tuple(
            item
            for item in entries
            if item.companion.artifact_reference.artifact_id == reference.artifact_id
            and item.companion.artifact_reference.artifact_version
            == reference.artifact_version
            and item.companion.construction_execution_id == construction_id
            and item.companion.validation_requirement == definition.requirement
            and (cutoff is None or item.companion.available_at <= cutoff)
        )
        if any(item.companion.artifact_reference != reference for item in relevant):
            raise PolygonCompletedDailyValidationHistoryConflictError(
                "artifact identity has conflicting retained validation history"
            )
        return tuple(sorted(relevant, key=lambda item: item.companion.history_sequence))


class PolygonCompletedDailyProductionValidationApplicationService:
    """Execute and retain the closed eight-rule production validation profile."""

    __slots__ = ("_construction_service", "_execution_clock", "_history")

    def __init__(
        self,
        construction_service: (
            PolygonCompletedDailyProductionConstructionApplicationService
        ),
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(construction_service)
            is not PolygonCompletedDailyProductionConstructionApplicationService
        ):
            raise TypeError(
                "construction_service must be the exact trusted production "
                "construction service"
            )
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._construction_service = construction_service
        self._execution_clock = _utc_now if execution_clock is None else execution_clock
        self._history = _InMemoryPolygonCompletedDailyValidationHistory()

    def execute_profile(
        self, request: PolygonCompletedDailyValidationRequest
    ) -> tuple[PolygonCompletedDailyProductionValidationResult, ...]:
        """Execute all eight approved concerns; no reduced-set input is accepted."""

        if type(request) is not PolygonCompletedDailyValidationRequest:
            raise TypeError(
                "request must be an exact PolygonCompletedDailyValidationRequest"
            )
        request._validate()
        construction_result = self._resolve_construction(request)
        try:
            definitions = _approved_definitions()
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.POLICY_REQUIREMENT_MISMATCH,
                "the exact approved eight-rule validation profile is unavailable",
            ) from error
        results: list[PolygonCompletedDailyProductionValidationResult] = []
        for definition in definitions:
            started_at = _timestamp(self._execution_clock(), "execution_started_at")
            support = _derive_support(construction_result)
            conclusion = _evaluate_definition(definition, support)
            try:
                result = self._history._retain(
                    execution_id=_issue_execution_id(),
                    construction_result=construction_result,
                    definition=definition,
                    conclusion=conclusion,
                    execution_started_at=started_at,
                    completion_clock=self._execution_clock,
                    availability_clock=self._execution_clock,
                    seal=_HISTORY_SEAL,
                )
            except PolygonCompletedDailyValidationExecutionRefused:
                raise
            except PolygonCompletedDailyValidationHistoryError as error:
                raise PolygonCompletedDailyValidationExecutionRefused(
                    PolygonCompletedDailyValidationRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                    "trusted validation history cannot publish the result",
                ) from error
            except (TypeError, ValueError, RuntimeError) as error:
                raise PolygonCompletedDailyValidationExecutionRefused(
                    PolygonCompletedDailyValidationRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                    "trusted validation publication failed",
                ) from error
            results.append(result)
        return tuple(results)

    def _resolve_construction(
        self, request: PolygonCompletedDailyValidationRequest
    ) -> PolygonCompletedDailyProductionConstructionResult:
        try:
            history = self._construction_service.get_construction_history(
                request.artifact_reference
            )
        except PolygonCompletedDailyConstructionHistoryError as error:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "trusted construction history is incomplete or conflicting",
            ) from error
        matches = tuple(
            item
            for item in history
            if item.receipt.execution_id == request.construction_execution_id
        )
        if not matches:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.TRUSTED_CONSTRUCTION_UNAVAILABLE,
                "exact trusted construction occurrence is unavailable",
            )
        if len(matches) != 1:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                "construction occurrence identity is ambiguous",
            )
        result = matches[0]
        try:
            receipt = _authentic_receipt(result)
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.ARTIFACT_TARGET_MISMATCH,
                "trusted construction receipt cannot establish a validation target",
            ) from error
        if receipt.artifact_reference != request.artifact_reference:
            raise PolygonCompletedDailyValidationExecutionRefused(
                PolygonCompletedDailyValidationRefusalReason.ARTIFACT_TARGET_MISMATCH,
                "requested artifact does not match the construction occurrence",
            )
        return result

    def get_validation_history(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        construction_execution_id: str,
        concern: EvidenceValidationConcern,
    ) -> tuple[PolygonCompletedDailyProductionValidationResult, ...]:
        """Return every authentic outcome for one exact concern and occurrence."""

        return self._history._history(
            artifact_reference,
            construction_execution_id,
            concern,
            knowledge_as_of=None,
        )

    def get_validation_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        construction_execution_id: str,
        concern: EvidenceValidationConcern,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyProductionValidationResult, ...]:
        """Return all outcomes available by the inclusive knowledge cutoff."""

        return self._history._history(
            artifact_reference,
            construction_execution_id,
            concern,
            knowledge_as_of=knowledge_as_of,
        )


def _approved_definitions() -> tuple[_ValidationRuleDefinition, ...]:
    profile = _resolve_approved_polygon_completed_daily_production_profile(_PROFILE)
    definitions = profile.validation_definitions
    if len(definitions) != len(EvidenceValidationConcern):
        raise ValueError("approved validation profile must contain exactly eight rules")
    if {item.requirement.concern for item in definitions} != set(
        EvidenceValidationConcern
    ):
        raise ValueError("approved validation profile concern set is incomplete")
    for item in definitions:
        item._validate()
        if (
            item.requirement.scope != _PROFILE.scope
            or item.requirement.ruleset_version != _VERSION
            or item.requirement.ruleset_id
            != (
                "production.polygon_completed_daily.validation."
                f"{item.requirement.concern.value}"
            )
        ):
            raise ValueError("approved validation definition identity is invalid")
    return definitions


def _approved_definition(
    concern: EvidenceValidationConcern,
) -> _ValidationRuleDefinition:
    if type(concern) is not EvidenceValidationConcern:
        raise TypeError("concern must be an exact EvidenceValidationConcern")
    matches = tuple(
        item for item in _approved_definitions() if item.requirement.concern is concern
    )
    if len(matches) != 1:
        raise ValueError("validation concern does not resolve exactly once")
    return matches[0]


def _operation(definition: _ValidationRuleDefinition) -> EvidenceIdentityReference:
    definition._validate()
    return EvidenceIdentityReference(
        namespace="market_platform.application.operation",
        identity_id=f"polygon_completed_daily_validation_{definition.requirement.concern.value}",
        identity_version=_VERSION,
        identity_fingerprint=canonical_fingerprint(
            {
                "schema_version": _OPERATION_SCHEMA,
                "operation_id": (
                    f"polygon_completed_daily_validation_"
                    f"{definition.requirement.concern.value}"
                ),
                "operation_version": _VERSION,
                "validation_requirement": definition.requirement.to_dict(),
                "validation_definition_fingerprint": definition.fingerprint,
                "production_profile_fingerprint": _PROFILE.fingerprint,
            }
        ),
    )


def _derive_support(
    result: PolygonCompletedDailyProductionConstructionResult,
) -> _ValidationSupport:
    if type(result) is not PolygonCompletedDailyProductionConstructionResult:
        raise TypeError("construction result type is invalid")
    receipt = getattr(result, "receipt", None)
    request = getattr(result, "request", None)
    candidate = getattr(result, "candidate_result", None)
    artifact = getattr(candidate, "artifact", None)
    material = getattr(candidate, "material", None)
    exact_receipt = (
        receipt
        if type(receipt) is PolygonCompletedDailyConstructionExecutionReceipt
        else None
    )
    exact_request = (
        request
        if type(request) is PolygonCompletedDailyEvidenceCandidateApplicationRequest
        else None
    )
    exact_artifact = artifact if type(artifact) is EvidenceArtifact else None
    exact_material = (
        material if type(material) is PolygonCompletedDailyOhlcvMaterial else None
    )
    resolution = (
        getattr(exact_material, "mapping_resolution_provenance", None)
        if exact_material is not None
        else None
    )
    exact_resolution = resolution if type(resolution) is InstrumentResolution else None
    try:
        profile: _ProductionGovernanceProfile | None = (
            _resolve_approved_polygon_completed_daily_production_profile(_PROFILE)
        )
    except TypeError, ValueError:
        profile = None
    return _ValidationSupport(
        construction_result=result,
        receipt=exact_receipt,
        request=exact_request,
        artifact=exact_artifact,
        material=exact_material,
        mapping_resolution=exact_resolution,
        approved_profile=profile,
    )


def _evaluate_definition(
    definition: _ValidationRuleDefinition, support: _ValidationSupport
) -> _RuleConclusion:
    definition._validate()
    concern = definition.requirement.concern
    executor = {
        EvidenceValidationConcern.IDENTITY: _evaluate_identity,
        EvidenceValidationConcern.INTEGRITY: _evaluate_integrity,
        EvidenceValidationConcern.PROVENANCE: _evaluate_provenance,
        EvidenceValidationConcern.AUTHORITY: _evaluate_authority,
        EvidenceValidationConcern.SCHEMA: _evaluate_schema,
        EvidenceValidationConcern.TEMPORAL_COHERENCE: _evaluate_temporal_coherence,
        EvidenceValidationConcern.FRESHNESS_CONTRACT: _evaluate_freshness_contract,
        EvidenceValidationConcern.SOURCE_QUALITY: _evaluate_source_quality,
    }[concern]
    return executor(support)


def _evaluate_identity(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    artifact = support.artifact
    material = support.material
    request = support.request
    resolution = support.mapping_resolution
    profile = support.approved_profile
    receipt = support.receipt
    _require_support(artifact, "authentic artifact", missing)
    _require_support(material, "complete retained material", missing)
    _require_support(request, "trusted construction request", missing)
    _require_support(resolution, "trusted mapping context", missing)
    _require_support(profile, "approved policy", missing)
    _require_support(receipt, "trusted construction occurrence", missing)
    if artifact is not None and profile is not None:
        definition = profile.construction_authorization.contract_definition
        _violate_if(
            artifact.evidence_type != definition.evidence_type,
            "Evidence type differs from the approved contract",
            violations,
        )
        _violate_if(
            artifact.governing_contract != definition.governing_contract,
            "governing contract differs from the approved contract",
            violations,
        )
        _violate_if(
            artifact.provenance.origin
            != profile.construction_authorization.authorized_source,
            "artifact source differs from the approved source",
            violations,
        )
        _violate_if(
            len(artifact.subjects) != 1,
            "artifact does not bind one canonical subject",
            violations,
        )
        try:
            artifact._validate()
        except TypeError, ValueError:
            violations.append("artifact retained identity is noncanonical")
    if material is not None and resolution is not None:
        mapping = resolution.mapping
        expected_subject = EvidenceSubjectReference(
            namespace="canonical_instrument",
            subject_id=mapping.canonical_instrument.instrument_id.instrument_id,
            subject_version=CANONICAL_INSTRUMENT_SCHEMA_VERSION,
            subject_fingerprint=mapping.canonical_instrument.fingerprint,
        )
        _violate_if(
            material.canonical_subject != expected_subject,
            "retained canonical subject differs from mapping",
            violations,
        )
        _violate_if(
            material.external_instrument_identity != resolution.external_identity,
            "retained external identity differs from mapping resolution",
            violations,
        )
        try:
            resolution._validate()
        except TypeError, ValueError:
            violations.append("retained mapping identity is noncanonical")
    if material is not None and request is not None:
        _violate_if(
            material.external_instrument_identity != request.external_identity,
            "material subject differs from trusted request",
            violations,
        )
        if resolution is not None:
            _violate_if(
                resolution.resolved_as_of != request.query_as_of
                or not any(
                    mapping == resolution.mapping
                    and mapping.fingerprint == resolution.mapping.fingerprint
                    for mapping in request.mappings
                ),
                "mapping identity differs from trusted request context",
                violations,
            )
    if artifact is not None and material is not None:
        _violate_if(
            artifact.subjects != (material.canonical_subject,),
            "artifact and material subjects differ",
            violations,
        )
        _violate_if(
            artifact.material_fingerprint != material.fingerprint
            or artifact.temporal_identity.source_revision != material.fingerprint,
            "artifact and material binding differs",
            violations,
        )
        if resolution is not None and profile is not None:
            try:
                expected_id = _expected_artifact_id(material, resolution, profile)
                expected_version = _expected_artifact_version(
                    artifact, material, expected_id
                )
                _violate_if(
                    artifact.artifact_id != expected_id,
                    "artifact ID projection does not recompute",
                    violations,
                )
                _violate_if(
                    artifact.artifact_version != expected_version,
                    "artifact version projection does not recompute",
                    violations,
                )
            except AttributeError, TypeError, ValueError:
                violations.append("artifact identity projections are malformed")
    if artifact is not None and receipt is not None:
        _violate_if(
            not _artifact_matches_reference(artifact, receipt.artifact_reference),
            "artifact content is rebound from construction reference",
            violations,
        )
    if material is not None and receipt is not None:
        _violate_if(
            receipt.material_fingerprint != material.fingerprint,
            "material is rebound from construction receipt",
            violations,
        )
    return _conclude(
        EvidenceValidationConcern.IDENTITY,
        violations,
        missing,
        "exact source, contract, subject, mapping, projections, and binding correspond",
    )


def _evaluate_integrity(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    artifact = support.artifact
    material = support.material
    receipt = support.receipt
    _require_support(artifact, "authentic artifact", missing)
    _require_support(material, "exact retained material", missing)
    _require_support(receipt, "trusted construction output", missing)
    recomputed: str | None = None
    if material is not None:
        try:
            recomputed = canonical_fingerprint(material._fingerprint_payload())
        except AttributeError, TypeError, ValueError:
            violations.append("complete retained material cannot be fingerprinted")
        else:
            _violate_if(
                recomputed != material.fingerprint,
                "retained material fingerprint differs from complete content",
                violations,
            )
        _violate_if(
            type(material.rows) is not tuple
            or type(material.row_count) is not int
            or material.row_count != len(material.rows),
            "retained row count differs from exact tuple length",
            violations,
        )
    if artifact is not None and material is not None:
        _violate_if(
            artifact.material_fingerprint != material.fingerprint,
            "artifact and material fingerprints differ",
            violations,
        )
    if receipt is not None and material is not None:
        _violate_if(
            receipt.material_fingerprint != material.fingerprint,
            "construction output binds different retained content",
            violations,
        )
    if receipt is not None and artifact is not None:
        _violate_if(
            not _artifact_matches_reference(artifact, receipt.artifact_reference),
            "artifact content differs from construction reference",
            violations,
        )
        _violate_if(
            receipt.result_content_fingerprint
            != _result_content_fingerprint(
                receipt.artifact_reference, receipt.material_fingerprint
            ),
            "construction result content binding is inconsistent",
            violations,
        )
    return _conclude(
        EvidenceValidationConcern.INTEGRITY,
        violations,
        missing,
        "complete material fingerprint, row count, artifact, and construction "
        "output bind exactly",
    )


def _evaluate_provenance(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    artifact = support.artifact
    material = support.material
    request = support.request
    resolution = support.mapping_resolution
    receipt = support.receipt
    profile = support.approved_profile
    for value, name in (
        (artifact, "authentic artifact provenance"),
        (material, "retained acquisition context"),
        (request, "trusted construction request"),
        (resolution, "retained mapping context"),
        (receipt, "exact trusted construction execution"),
        (profile, "approved construction lineage"),
    ):
        _require_support(value, name, missing)
    if artifact is not None and profile is not None:
        expected_source = profile.construction_authorization.authorized_source
        provenance = artifact.provenance
        _violate_if(
            provenance.origin != expected_source
            or provenance.source_references != (expected_source,),
            "origin/source provenance differs from approved source",
            violations,
        )
        _violate_if(
            provenance.producer != profile.construction_producer,
            "producer provenance differs from approved producer",
            violations,
        )
        _violate_if(
            provenance.transformations != () or provenance.predecessors != (),
            "artifact lineage differs from released construction lineage",
            violations,
        )
    if material is not None and profile is not None:
        _violate_if(
            material.source_reference
            != profile.construction_authorization.authorized_source,
            "material source vintage differs from approved source",
            violations,
        )
    if material is not None and request is not None:
        request_provenance = material.request_provenance
        _violate_if(
            request_provenance.requested_ticker
            != request.external_identity.external_symbol
            or request_provenance.requested_from != request.requested_from.isoformat()
            or request_provenance.requested_to != request.requested_to.isoformat()
            or material.query_as_of != request.query_as_of,
            "retained request provenance differs from trusted request",
            violations,
        )
    if resolution is not None and request is not None:
        _violate_if(
            resolution.external_identity != request.external_identity
            or resolution.resolved_as_of != request.query_as_of
            or not any(
                item == resolution.mapping
                and item.fingerprint == resolution.mapping.fingerprint
                for item in request.mappings
            ),
            "mapping provenance differs from trusted request",
            violations,
        )
    if receipt is not None:
        try:
            receipt._validate()
        except TypeError, ValueError:
            violations.append("trusted construction occurrence is noncanonical")
        if request is not None:
            try:
                _violate_if(
                    receipt.request_fingerprint != _request_fingerprint(request),
                    "construction receipt binds a different request",
                    violations,
                )
            except TypeError, ValueError:
                violations.append("trusted request provenance is noncanonical")
        if resolution is not None:
            _violate_if(
                receipt.resolved_mapping_fingerprint != resolution.mapping.fingerprint,
                "construction receipt binds a different mapping resolution",
                violations,
            )
    return _conclude(
        EvidenceValidationConcern.PROVENANCE,
        violations,
        missing,
        "retained source, request, producer, mapping, vintage, and construction "
        "lineage correspond",
    )


def _evaluate_authority(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    artifact = support.artifact
    receipt = support.receipt
    profile = support.approved_profile
    _require_support(artifact, "authentic artifact authority", missing)
    _require_support(receipt, "trusted construction authorization", missing)
    _require_support(profile, "corrected approved production policy", missing)
    if artifact is not None and profile is not None:
        _violate_if(
            profile != _PROFILE or profile.fingerprint != _PROFILE.fingerprint,
            "production governance profile is not the corrected approved profile",
            violations,
        )
        authorization = profile.construction_authorization
        definition = authorization.contract_definition
        _violate_if(
            artifact.authority is not EvidenceAuthority.EXTERNAL_ORIGIN
            or artifact.authority is not authorization.authority,
            "authority class differs from approved external origin",
            violations,
        )
        _violate_if(
            artifact.information_class
            is not EvidenceInformationClass.SOURCE_MEASUREMENT
            or artifact.information_class is not definition.information_class,
            "information class differs from approved source measurement",
            violations,
        )
        _violate_if(
            artifact.contract_authorization != authorization
            or artifact.contract_authorization.fingerprint != authorization.fingerprint,
            "construction authorization is not the frozen approved member",
            violations,
        )
        _violate_if(
            artifact.governing_contract != definition.governing_contract
            or artifact.provenance.origin != authorization.authorized_source,
            "source/contract conjunction is not approved",
            violations,
        )
        _violate_if(
            profile.scope != "research.daily_technical.completed_daily",
            "governance scope does not permit this validation profile",
            violations,
        )
    if receipt is not None and profile is not None:
        _violate_if(
            receipt.construction_authorization != profile.construction_authorization
            or receipt.production_profile_fingerprint != profile.fingerprint,
            "trusted construction execution has different authority lineage",
            violations,
        )
    return _conclude(
        EvidenceValidationConcern.AUTHORITY,
        violations,
        missing,
        "frozen construction authorization, classes, source/contract, and "
        "governance scope correspond; no downstream permission is granted",
    )


def _evaluate_schema(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    material = support.material
    profile = support.approved_profile
    _require_support(material, "complete retained material", missing)
    _require_support(profile, "approved material/schema definition", missing)
    if material is not None and profile is not None:
        expected_schema = (
            profile.construction_authorization.contract_definition.material_schema
        )
        _violate_if(
            material.schema_version != "polygon_completed_daily_ohlcv_material/1.0.0"
            or material.material_schema != expected_schema,
            "material/schema identity differs from approved material v1",
            violations,
        )
        _violate_if(
            material.source_reference
            != profile.construction_authorization.authorized_source,
            "material source reference differs from material v1",
            violations,
        )
        expected_material_fields = (
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
        )
        _violate_if(
            tuple(item.name for item in fields(type(material)))
            != expected_material_fields,
            "material has unsupported or missing field structure",
            violations,
        )
        _validate_material_metadata(material, violations)
        if type(material.rows) is not tuple:
            violations.append("rows must be retained as an exact tuple")
        else:
            _violate_if(
                type(material.row_count) is not int
                or material.row_count != len(material.rows)
                or material.row_count > ingress._LIMIT,
                "row_count metadata/resource limit is invalid",
                violations,
            )
            for index, row in enumerate(material.rows):
                if type(row) is not PolygonCompletedDailyOhlcvMaterialRow:
                    violations.append(f"row {index} has unsupported structure")
                    continue
                if tuple(item.name for item in fields(type(row))) != (
                    "session_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ):
                    violations.append(f"row {index} has unsupported fields")
                try:
                    _canonical_session_date(row.session_date)
                except TypeError, ValueError:
                    violations.append(f"row {index} session_date is noncanonical")
                for name in ("open", "high", "low", "close", "volume"):
                    try:
                        _canonical_decimal(getattr(row, name), name)
                    except TypeError, ValueError:
                        violations.append(f"row {index} {name} is noncanonical")
    return _conclude(
        EvidenceValidationConcern.SCHEMA,
        violations,
        missing,
        "material v1 fields, row fields, canonical dates/decimals, metadata, "
        "counts, and resource limits correspond",
    )


def _evaluate_temporal_coherence(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    artifact = support.artifact
    material = support.material
    request = support.request
    receipt = support.receipt
    for value, name in (
        (artifact, "authentic artifact temporal identity"),
        (material, "retained material temporal support"),
        (request, "trusted request/query context"),
        (receipt, "trusted construction execution/availability history"),
    ):
        _require_support(value, name, missing)
    if artifact is not None and material is not None:
        temporal = artifact.temporal_identity
        try:
            start_date = _canonical_session_date(material.start_session_date)
            end_date = _canonical_session_date(material.end_session_date)
            expected_start = datetime.combine(
                start_date, time.min, tzinfo=_MARKET_TIMEZONE
            ).astimezone(UTC)
            expected_end = datetime.combine(
                end_date + timedelta(days=1), time.min, tzinfo=_MARKET_TIMEZONE
            ).astimezone(UTC)
            _violate_if(
                temporal.observation_period_start != expected_start
                or temporal.observation_period_end != expected_end,
                "requested bounds do not reproduce the New York half-open interval",
                violations,
            )
            query_date = material.query_as_of.astimezone(_MARKET_TIMEZONE).date()
            if type(material.rows) is not tuple:
                violations.append("retained temporal rows are malformed")
            else:
                for index, row in enumerate(material.rows):
                    if type(row) is not PolygonCompletedDailyOhlcvMaterialRow:
                        violations.append(f"row {index} lacks temporal structure")
                        continue
                    session = _canonical_session_date(row.session_date)
                    _violate_if(
                        not start_date <= session <= end_date,
                        f"row {index} is outside requested interval",
                        violations,
                    )
                    _violate_if(
                        session >= query_date,
                        f"row {index} is not completed before query New York date",
                        violations,
                    )
        except AttributeError, OverflowError, TypeError, ValueError:
            violations.append("requested temporal interval is malformed")
        _violate_if(
            temporal.observed_at is not None
            or temporal.published_at is not None
            or temporal.effective_from is not None
            or temporal.effective_until is not None,
            "unknown source/publication/effective timestamps were invented",
            violations,
        )
        _violate_if(
            temporal.source_revision != material.fingerprint,
            "temporal source revision differs from retained material",
            violations,
        )
    if artifact is not None and material is not None and receipt is not None:
        temporal = artifact.temporal_identity
        _violate_if(
            not (
                material.query_as_of
                <= receipt.response_received_at
                == temporal.platform_received_at
                <= receipt.artifact_created_at
                == temporal.artifact_created_at
                <= receipt.execution_completed_at
                <= receipt.available_at
            ),
            "query/receipt/create/construction/availability chronology contradicts",
            violations,
        )
        _violate_if(
            receipt.execution_started_at > receipt.response_received_at,
            "construction execution chronology contradicts response receipt",
            violations,
        )
    if request is not None and material is not None:
        _violate_if(
            request.query_as_of != material.query_as_of
            or request.requested_from.isoformat() != material.start_session_date
            or request.requested_to.isoformat() != material.end_session_date,
            "trusted request temporal context differs from material",
            violations,
        )
    return _conclude(
        EvidenceValidationConcern.TEMPORAL_COHERENCE,
        violations,
        missing,
        "requested interval, completed rows, query/receipt/create chronology, "
        "and trusted construction availability are coherent",
    )


def _evaluate_freshness_contract(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    artifact = support.artifact
    material = support.material
    profile = support.approved_profile
    _require_support(artifact, "artifact observation_period_end anchor", missing)
    _require_support(material, "retained session-date support", missing)
    _require_support(profile, "approved freshness definitions/profile", missing)
    if profile is not None:
        _violate_if(
            profile != _PROFILE or profile.fingerprint != _PROFILE.fingerprint,
            "production governance profile is not the corrected approved profile",
            violations,
        )
        definitions = (profile.admission_freshness, profile.task_freshness)
        expected_ids = (
            "production.polygon_completed_daily.freshness.admission",
            "production.polygon_completed_daily.freshness.daily_technical",
        )
        for definition, expected_id in zip(definitions, expected_ids, strict=True):
            try:
                definition._validate()
                configuration = definition._configuration_payload()
            except TypeError, ValueError:
                violations.append("approved freshness definition is noncanonical")
                continue
            rule = definition.rule
            _violate_if(
                rule.rule_id != expected_id
                or rule.rule_version != _VERSION
                or rule.evaluation_scope != _PROFILE.scope
                or rule.declared_temporal_anchor != "observation_period_end",
                "freshness rule identity/scope/declared anchor is incompatible",
                violations,
            )
            _violate_if(
                configuration.get("market_timezone") != "America/New_York"
                or configuration.get("minimum_calendar_lag_days") != 1
                or configuration.get("maximum_calendar_lag_days") != 4
                or configuration.get("maximum_lag_inclusive") is not True
                or configuration.get("expected_session_calendar") is not None,
                "freshness predicate representation differs from approved "
                "4-day contract",
                violations,
            )
    if artifact is not None:
        _violate_if(
            artifact.temporal_identity.observation_period_end is None,
            "artifact does not supply observation_period_end",
            violations,
        )
    if material is not None:
        if type(material.rows) is not tuple:
            violations.append("retained material cannot supply session-date semantics")
        else:
            prior: date | None = None
            for index, row in enumerate(material.rows):
                if type(row) is not PolygonCompletedDailyOhlcvMaterialRow:
                    violations.append(f"row {index} cannot supply a session date")
                    continue
                try:
                    session = _canonical_session_date(row.session_date)
                except TypeError, ValueError:
                    violations.append(f"row {index} session semantics are incompatible")
                    continue
                if prior is not None and session <= prior:
                    violations.append(
                        "retained session ordering cannot derive latest eligible "
                        "session"
                    )
                prior = session
    return _conclude(
        EvidenceValidationConcern.FRESHNESS_CONTRACT,
        violations,
        missing,
        "both approved observation_period_end rules and retained session semantics "
        "support the inclusive 4-calendar-day predicate; no freshness outcome "
        "was inspected",
    )


def _evaluate_source_quality(support: _ValidationSupport) -> _RuleConclusion:
    violations: list[str] = []
    missing: list[str] = []
    material = support.material
    _require_support(material, "exact retained numeric/session material", missing)
    if material is not None:
        if type(material.rows) is not tuple:
            violations.append("retained rows are malformed")
        elif not material.rows:
            violations.append("authentic retained material is empty")
        else:
            seen: set[date] = set()
            prior: date | None = None
            for index, row in enumerate(material.rows):
                if type(row) is not PolygonCompletedDailyOhlcvMaterialRow:
                    violations.append(f"row {index} is malformed")
                    continue
                try:
                    session = _canonical_session_date(row.session_date)
                except TypeError, ValueError:
                    violations.append(f"row {index} session date is noncanonical")
                    continue
                if session in seen:
                    violations.append(f"row {index} duplicates a session date")
                if prior is not None and session <= prior:
                    violations.append(f"row {index} session order is not increasing")
                seen.add(session)
                prior = session
                numeric: dict[str, Decimal] = {}
                for name in ("open", "high", "low", "close", "volume"):
                    try:
                        numeric[name] = _canonical_decimal(getattr(row, name), name)
                    except TypeError, ValueError:
                        violations.append(
                            f"row {index} {name} is not finite canonical numeric"
                        )
                if len(numeric) != 5:
                    continue
                for name in ("open", "high", "low", "close"):
                    if numeric[name] <= 0:
                        violations.append(
                            f"row {index} {name} is not strictly positive"
                        )
                if numeric["volume"] < 0:
                    violations.append(f"row {index} volume is negative")
                if numeric["high"] < numeric["low"]:
                    violations.append(f"row {index} high is below low")
                if not numeric["low"] <= numeric["open"] <= numeric["high"]:
                    violations.append(f"row {index} open is outside [low, high]")
                if not numeric["low"] <= numeric["close"] <= numeric["high"]:
                    violations.append(f"row {index} close is outside [low, high]")
    return _conclude(
        EvidenceValidationConcern.SOURCE_QUALITY,
        violations,
        missing,
        "nonempty exact decimal OHLCV rows satisfy positivity/range rules and "
        "session dates are unique and strictly increasing",
    )


def _validate_material_metadata(
    material: PolygonCompletedDailyOhlcvMaterial, violations: list[str]
) -> None:
    exact_values: tuple[tuple[object, type[object], object], ...] = (
        (material.vendor_service, str, "massive.com_formerly_polygon.io"),
        (material.api_base, str, ingress._API_BASE),
        (material.route_template, str, ingress._ROUTE_TEMPLATE),
        (material.multiplier, int, ingress._MULTIPLIER),
        (material.timespan, str, ingress._MATERIAL_TIMESPAN),
        (material.adjusted, bool, ingress._ADJUSTED),
        (material.sort, str, ingress._SORT),
        (material.limit, int, ingress._LIMIT),
        (material.market_timezone, str, ingress._MARKET_TIMEZONE_NAME),
        (material.session_scope, str, ingress._SESSION_SCOPE),
        (material.price_adjustment, str, ingress._PRICE_ADJUSTMENT),
        (material.adjusted_response, bool, True),
    )
    if any(
        type(value) is not expected_type or value != expected
        for value, expected_type, expected in exact_values
    ):
        violations.append("material structural metadata differs from material v1")
    if type(material.external_instrument_identity) is not ExternalInstrumentIdentity:
        violations.append("external instrument identity type is invalid")
    else:
        try:
            material.external_instrument_identity._validate()
        except TypeError, ValueError:
            violations.append("external instrument identity is noncanonical")
    if type(material.canonical_subject) is not EvidenceSubjectReference:
        violations.append("canonical subject type is invalid")
    else:
        try:
            material.canonical_subject._validate()
        except TypeError, ValueError:
            violations.append("canonical subject is noncanonical")
    if type(material.mapping_resolution_provenance) is not InstrumentResolution:
        violations.append("mapping resolution structure is invalid")
    else:
        try:
            material.mapping_resolution_provenance._validate()
        except TypeError, ValueError:
            violations.append("mapping resolution is noncanonical")
    for name in ("start_session_date", "end_session_date"):
        try:
            _canonical_session_date(getattr(material, name))
        except TypeError, ValueError:
            violations.append(f"{name} is noncanonical")
    try:
        _require_canonical_timestamp(material.query_as_of, "query_as_of")
    except TypeError, ValueError:
        violations.append("query_as_of is noncanonical")
    provenance = material.request_provenance
    if type(provenance) is not _PolygonCompletedDailyOhlcvRequestProvenance:
        violations.append("request provenance structure is invalid")
    else:
        expected_route = (
            f"/v2/aggs/ticker/{quote(str(provenance.requested_ticker), safe='')}"
            "/range/1/day/"
            f"{provenance.requested_from}/{provenance.requested_to}"
        )
        exact_request_values: tuple[tuple[object, type[object], object], ...] = (
            (
                provenance.schema_version,
                str,
                ingress._REQUEST_PROVENANCE_SCHEMA_VERSION,
            ),
            (provenance.api_base, str, ingress._API_BASE),
            (provenance.resolved_route, str, expected_route),
            (provenance.multiplier, int, ingress._MULTIPLIER),
            (provenance.timespan, str, ingress._REQUEST_TIMESPAN),
            (provenance.adjusted, bool, True),
            (provenance.sort, str, ingress._SORT),
            (provenance.limit, int, ingress._LIMIT),
        )
        if any(
            type(value) is not expected_type or value != expected
            for value, expected_type, expected in exact_request_values
        ):
            violations.append("request provenance fields are unsupported")
        if type(provenance.requested_ticker) is not str:
            violations.append("request provenance ticker has invalid type")
        for name in ("requested_from", "requested_to"):
            try:
                _canonical_session_date(getattr(provenance, name))
            except TypeError, ValueError:
                violations.append(f"request provenance {name} is noncanonical")
    if (
        material.provider_request_id is not None
        and type(material.provider_request_id) is not str
    ):
        violations.append("provider_request_id has invalid type")
    try:
        _fingerprint(material.fingerprint, "material fingerprint")
    except ValueError:
        violations.append("material fingerprint has invalid structure")


def _validate_result_correspondence(
    construction_result: PolygonCompletedDailyProductionConstructionResult,
    validation_record: EvidenceValidationRecord,
    companion: PolygonCompletedDailyValidationExecutionCompanion,
) -> None:
    receipt = _authentic_receipt(construction_result)
    if type(validation_record) is not EvidenceValidationRecord:
        raise TypeError("validation_record type is invalid")
    validation_record._validate()
    if type(companion) is not PolygonCompletedDailyValidationExecutionCompanion:
        raise TypeError("companion type is invalid")
    companion._validate()
    definition = _approved_definition(companion.validation_requirement.concern)
    expected = _evaluate_definition(definition, _derive_support(construction_result))
    if (
        validation_record.disposition is not expected.disposition
        or validation_record.findings != expected.findings
    ):
        raise ValueError("validation record does not match trusted rule execution")
    if (
        companion.construction_history_namespace_id != receipt.history_namespace_id
        or companion.construction_history_sequence != receipt.history_sequence
        or companion.construction_execution_id != receipt.execution_id
        or companion.construction_receipt_fingerprint != receipt.fingerprint
        or companion.construction_result_content_fingerprint
        != receipt.result_content_fingerprint
    ):
        raise ValueError("companion does not bind exact construction occurrence")
    if (
        companion.artifact_reference != receipt.artifact_reference
        or companion.material_fingerprint != receipt.material_fingerprint
        or companion.request_fingerprint != receipt.request_fingerprint
        or companion.resolved_mapping_fingerprint
        != receipt.resolved_mapping_fingerprint
        or companion.construction_authorization_fingerprint
        != receipt.construction_authorization.fingerprint
        or companion.trusted_support_fingerprint
        != _trusted_support_fingerprint(receipt, definition.requirement)
    ):
        raise ValueError("companion support binding does not correspond")
    if companion.validation_reference != validation_record.reference():
        raise ValueError("companion does not bind exact validation record")
    if validation_record.validator_identity != _VALIDATOR:
        raise ValueError("validation lifecycle actor is not approved")
    if validation_record.validator_capability_identity != _CAPABILITY:
        raise ValueError("validation lifecycle capability is not approved")
    requirement = definition.requirement
    if (
        validation_record.artifact_reference != receipt.artifact_reference
        or validation_record.concern is not requirement.concern
        or validation_record.scope != requirement.scope
        or validation_record.ruleset_id != requirement.ruleset_id
        or validation_record.ruleset_version != requirement.ruleset_version
        or validation_record.recorded_at != companion.execution_completed_at
        or validation_record.effective_at != companion.execution_completed_at
    ):
        raise ValueError("lifecycle validation record correspondence is invalid")


def _validate_retained_entries(
    entries: tuple[PolygonCompletedDailyProductionValidationResult, ...],
    *,
    expected_namespace_id: str,
) -> None:
    if type(entries) is not tuple:
        raise TypeError("validation history must be an exact tuple")
    namespace_id = _history_namespace_id(expected_namespace_id)
    execution_ids: set[str] = set()
    sequences: set[int] = set()
    records: dict[str, EvidenceValidationRecord] = {}
    prior_sequence = 0
    prior_availability: datetime | None = None
    for item in entries:
        if type(item) is not PolygonCompletedDailyProductionValidationResult:
            raise TypeError("validation history contains an invalid result type")
        item._validate()
        companion = item.companion
        if companion.history_namespace_id != namespace_id:
            raise ValueError("validation history namespace does not correspond")
        if companion.execution_id in execution_ids:
            raise ValueError("validation history duplicates an execution identity")
        if companion.history_sequence in sequences:
            raise ValueError("validation history duplicates a sequence")
        if companion.history_sequence <= prior_sequence:
            raise ValueError("validation history sequence is not increasing")
        if (
            prior_availability is not None
            and companion.available_at < prior_availability
        ):
            raise ValueError("validation history availability moves backward")
        retained = records.get(item.validation_record.validation_record_id)
        if retained is not None and retained != item.validation_record:
            raise ValueError(
                "validation record identity resolves to conflicting content"
            )
        records[item.validation_record.validation_record_id] = item.validation_record
        execution_ids.add(companion.execution_id)
        sequences.add(companion.history_sequence)
        prior_sequence = companion.history_sequence
        prior_availability = companion.available_at


def _create_validation_record(
    artifact_reference: EvidenceArtifactReference,
    definition: _ValidationRuleDefinition,
    conclusion: _RuleConclusion,
    *,
    completed_at: datetime,
) -> EvidenceValidationRecord:
    requirement = definition.requirement
    record_identity = canonical_fingerprint(
        {
            "schema_version": _RECORD_ID_SCHEMA,
            "artifact_reference": artifact_reference.to_dict(),
            "validation_requirement": requirement.to_dict(),
            "disposition": conclusion.disposition.value,
            "findings": list(conclusion.findings),
            "recorded_at": completed_at.isoformat(),
            "effective_at": completed_at.isoformat(),
        }
    ).removeprefix("sha256:")
    return create_evidence_validation_record(
        validation_record_id=(
            f"validation.polygon_completed_daily.{requirement.concern.value}:"
            f"{record_identity}"
        ),
        artifact_reference=artifact_reference,
        concern=requirement.concern,
        scope=requirement.scope,
        disposition=conclusion.disposition,
        validator_identity=_VALIDATOR,
        validator_capability_identity=_CAPABILITY,
        ruleset_id=requirement.ruleset_id,
        ruleset_version=requirement.ruleset_version,
        recorded_at=completed_at,
        effective_at=completed_at,
        findings=conclusion.findings,
    )


def _expected_artifact_id(
    material: PolygonCompletedDailyOhlcvMaterial,
    resolution: InstrumentResolution,
    profile: _ProductionGovernanceProfile,
) -> str:
    return canonical_fingerprint(
        {
            "schema_version": ingress._ARTIFACT_IDENTITY_SCHEMA_VERSION,
            "governing_contract": (
                profile.construction_authorization.contract_definition.governing_contract.to_dict()
            ),
            "canonical_subject_id": (
                resolution.mapping.canonical_instrument.instrument_id.to_dict()
            ),
            "requested_from": material.start_session_date,
            "requested_to": material.end_session_date,
        }
    )


def _expected_artifact_version(
    artifact: EvidenceArtifact,
    material: PolygonCompletedDailyOhlcvMaterial,
    artifact_id: str,
) -> str:
    return canonical_fingerprint(
        {
            "schema_version": ingress._ARTIFACT_VERSION_SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "material_fingerprint": material.fingerprint,
            "temporal_identity": artifact.temporal_identity.to_dict(),
            "provenance": artifact.provenance.to_dict(),
        }
    )


def _conclude(
    concern: EvidenceValidationConcern,
    violations: list[str],
    missing: list[str],
    passed_basis: str,
) -> _RuleConclusion:
    if violations:
        return _RuleConclusion(
            EvidenceValidationDisposition.REJECTED,
            (
                f"Established {concern.value} violation: "
                f"{_bounded_finding_details(violations)}.",
            ),
        )
    if missing:
        return _RuleConclusion(
            EvidenceValidationDisposition.UNABLE_TO_VALIDATE,
            (
                f"Mandatory {concern.value} support could not be authentically "
                f"established: {_bounded_finding_details(missing)}.",
            ),
        )
    return _RuleConclusion(
        EvidenceValidationDisposition.PASSED,
        (f"Approved {concern.value} predicates established: {passed_basis}.",),
    )


def _bounded_finding_details(items: list[str]) -> str:
    retained = items[:8]
    details = "; ".join(retained)
    remaining = len(items) - len(retained)
    if remaining:
        details += f"; {remaining} additional established issue(s)"
    return details[:1800]


def _require_support(value: object, name: str, missing: list[str]) -> None:
    if value is None:
        missing.append(name)


def _violate_if(condition: bool, message: str, violations: list[str]) -> None:
    if condition:
        violations.append(message)


def _canonical_session_date(value: object) -> date:
    if type(value) is not str:
        raise TypeError("session_date must be an exact string")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("session_date must be exact YYYY-MM-DD")
    return parsed


def _canonical_decimal(value: object, field_name: str) -> Decimal:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact string")
    if len(value) > MAX_CANONICAL_NUMERIC_TEXT_LENGTH:
        raise ValueError(f"{field_name} exceeds canonical resource limit")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field_name} is not decimal numeric") from error
    if not parsed.is_finite() or _canonical_numeric_text(parsed, field_name) != value:
        raise ValueError(f"{field_name} is not canonical finite decimal")
    return parsed


def _artifact_matches_reference(
    artifact: EvidenceArtifact, reference: EvidenceArtifactReference
) -> bool:
    try:
        return artifact.reference() == reference
    except TypeError, ValueError:
        return False


def _authentic_receipt(
    result: PolygonCompletedDailyProductionConstructionResult,
) -> PolygonCompletedDailyConstructionExecutionReceipt:
    if type(result) is not PolygonCompletedDailyProductionConstructionResult:
        raise TypeError("construction result type is invalid")
    receipt = getattr(result, "receipt", None)
    if type(receipt) is not PolygonCompletedDailyConstructionExecutionReceipt:
        raise TypeError("construction receipt is unavailable")
    receipt._validate()
    return receipt


def _trusted_support_fingerprint(
    receipt: PolygonCompletedDailyConstructionExecutionReceipt,
    requirement: EvidenceValidationRequirement,
) -> str:
    receipt._validate()
    requirement._validate()
    return canonical_fingerprint(
        {
            "schema_version": _SUPPORT_SCHEMA,
            "construction_receipt_fingerprint": receipt.fingerprint,
            "construction_result_content_fingerprint": (
                receipt.result_content_fingerprint
            ),
            "artifact_reference": receipt.artifact_reference.to_dict(),
            "material_fingerprint": receipt.material_fingerprint,
            "request_fingerprint": receipt.request_fingerprint,
            "resolved_mapping_fingerprint": receipt.resolved_mapping_fingerprint,
            "construction_authorization_fingerprint": (
                receipt.construction_authorization.fingerprint
            ),
            "validation_requirement": requirement.to_dict(),
        }
    )


def _copy_artifact_reference(value: object) -> EvidenceArtifactReference:
    if type(value) is not EvidenceArtifactReference:
        raise TypeError("artifact_reference must be an EvidenceArtifactReference")
    value._validate()
    return EvidenceArtifactReference(
        artifact_id=value.artifact_id,
        artifact_version=value.artifact_version,
        artifact_fingerprint=value.artifact_fingerprint,
        information_class=value.information_class,
        authority=value.authority,
    )


def _copy_identity_reference(value: object) -> EvidenceIdentityReference:
    if type(value) is not EvidenceIdentityReference:
        raise TypeError("identity must be an EvidenceIdentityReference")
    value._validate()
    return EvidenceIdentityReference(
        namespace=value.namespace,
        identity_id=value.identity_id,
        identity_version=value.identity_version,
        identity_fingerprint=value.identity_fingerprint,
    )


def _copy_requirement(value: object) -> EvidenceValidationRequirement:
    if type(value) is not EvidenceValidationRequirement:
        raise TypeError("validation requirement type is invalid")
    value._validate()
    return EvidenceValidationRequirement(
        concern=value.concern,
        scope=value.scope,
        ruleset_id=value.ruleset_id,
        ruleset_version=value.ruleset_version,
    )


def _copy_validation_reference(value: object) -> EvidenceValidationRecordReference:
    if type(value) is not EvidenceValidationRecordReference:
        raise TypeError("validation_reference type is invalid")
    value._validate()
    return EvidenceValidationRecordReference(
        validation_record_id=value.validation_record_id,
        artifact_reference=value.artifact_reference,
        concern=value.concern,
        scope=value.scope,
        disposition=value.disposition,
        ruleset_id=value.ruleset_id,
        ruleset_version=value.ruleset_version,
        validation_record_fingerprint=value.validation_record_fingerprint,
    )


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be an exact datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{field_name} is outside supported range") from error


def _require_canonical_timestamp(value: object, field_name: str) -> datetime:
    canonical = _timestamp(value, field_name)
    if (
        type(value) is not datetime
        or value.tzinfo is not UTC
        or value.isoformat() != canonical.isoformat()
    ):
        raise ValueError(f"{field_name} must retain canonical UTC state")
    return canonical


def _positive_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive exact integer")
    return value


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _execution_id(value: object) -> str:
    if type(value) is not str or _EXECUTION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("execution_id is not a platform-issued canonical identity")
    return value


def _construction_execution_id(value: object) -> str:
    if (
        type(value) is not str
        or _CONSTRUCTION_EXECUTION_ID_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("construction_execution_id is not a canonical identity")
    return value


def _history_namespace_id(value: object) -> str:
    if type(value) is not str or _HISTORY_NAMESPACE_PATTERN.fullmatch(value) is None:
        raise ValueError("history_namespace_id is not a canonical identity")
    return value


def _construction_history_namespace_id(value: object) -> str:
    if (
        type(value) is not str
        or _CONSTRUCTION_HISTORY_NAMESPACE_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("construction_history_namespace_id is not canonical")
    return value


def _issue_execution_id() -> str:
    return f"polygon_completed_daily_validation:{uuid4().hex}"


def _issue_history_namespace_id() -> str:
    return f"polygon_completed_daily_validation_history:{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "PolygonCompletedDailyProductionValidationApplicationService",
    "PolygonCompletedDailyProductionValidationResult",
    "PolygonCompletedDailyValidationExecutionCompanion",
    "PolygonCompletedDailyValidationExecutionRefused",
    "PolygonCompletedDailyValidationHistoryConflictError",
    "PolygonCompletedDailyValidationHistoryError",
    "PolygonCompletedDailyValidationRefusalReason",
    "PolygonCompletedDailyValidationRequest",
]
