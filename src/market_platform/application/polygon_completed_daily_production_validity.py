"""Separate initial ACTIVE issuance from authentic production admission history."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum
from threading import Lock
from uuid import uuid4

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_admission as admission,
)
from market_platform.evidence import (
    EvidenceAdmissionDisposition,
    EvidenceArtifactReference,
    EvidenceIdentityReference,
    EvidenceValidityEvent,
    EvidenceValidityReference,
    EvidenceValidityStatus,
    create_evidence_validity_event,
)

_PROFILE = admission._PROFILE
_SCHEMA = "polygon_completed_daily_initial_active_execution/v1"
_SEAL = object()


def _identity(namespace: str, name: str) -> EvidenceIdentityReference:
    return EvidenceIdentityReference(
        namespace=namespace,
        identity_id=name,
        identity_version="1.0.0",
        identity_fingerprint=canonical_fingerprint(
            {
                "schema_version": "polygon_completed_daily_initial_active_identity/v1",
                "namespace": namespace,
                "identity_id": name,
                "definition": _PROFILE.initial_validity.to_dict(),
                "profile_fingerprint": _PROFILE.fingerprint,
            }
        ),
    )


_OPERATION = _identity(
    "market_platform.application.operation",
    "production.polygon_completed_daily.validity.initial_active",
)
_ACTOR = _identity(
    "market_platform.evidence_validity_authority",
    "polygon_completed_daily_production_validity",
)
_CAPABILITY = _identity(
    "market_platform.application.capability",
    "issue_polygon_completed_daily_initial_active",
)


class PolygonCompletedDailyValidityRefusalReason(StrEnum):
    ADMISSION_UNAVAILABLE = "admission_unavailable"
    TARGET_MISMATCH = "target_mismatch"
    PRIOR_VALIDITY = "prior_validity"
    TEMPORAL_FAILURE = "temporal_failure"
    HISTORY_CONFLICT_OR_CORRUPTION = "history_conflict_or_corruption"


class PolygonCompletedDailyValidityIssuanceRefused(RuntimeError):
    """The initial ACTIVE operation published no event."""

    def __init__(
        self, reason: PolygonCompletedDailyValidityRefusalReason, message: str
    ) -> None:
        if type(reason) is not PolygonCompletedDailyValidityRefusalReason:
            raise TypeError("reason must be an exact validity refusal reason")
        self.reason = reason
        super().__init__(message)


class PolygonCompletedDailyValidityHistoryError(RuntimeError):
    """Validity history cannot establish complete authentic events."""


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyInitialActiveRequest:
    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            admission._copy_artifact_reference(self.artifact_reference),
        )
        admission._construction_execution_id(self.construction_execution_id)

    def _validate(self) -> None:
        admission._copy_artifact_reference(self.artifact_reference)
        admission._construction_execution_id(self.construction_execution_id)


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyValidityExecutionCompanion:
    """Issuance provenance; the released event is the sole validity lifecycle."""

    execution_id: str
    history_namespace_id: str
    history_sequence: int
    operation: EvidenceIdentityReference
    actor: EvidenceIdentityReference
    capability: EvidenceIdentityReference
    executor: EvidenceIdentityReference
    production_profile_reference: EvidenceIdentityReference
    production_profile_fingerprint: str
    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str
    construction_receipt_fingerprint: str
    admission_execution_reference: (
        admission.PolygonCompletedDailyAdmissionExecutionReference
    )
    admission_history_fingerprint: str
    prior_validity_references: tuple[EvidenceValidityReference, ...]
    prior_validity_history_fingerprint: str
    validity_reference: EvidenceValidityReference
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("validity companion is issued only by trusted validity history")

    @classmethod
    def _create(
        cls,
        *,
        sequence: int,
        namespace: str,
        support: admission.PolygonCompletedDailyProductionAdmissionResult,
        admission_context: str,
        event: EvidenceValidityEvent,
        started: datetime,
        completed: datetime,
        available: datetime,
        seal: object,
    ) -> PolygonCompletedDailyValidityExecutionCompanion:
        if seal is not _SEAL:
            raise TypeError("validity companion issuance is private")
        result = object.__new__(cls)
        values: dict[str, object] = {
            "execution_id": f"polygon_completed_daily_validity:{uuid4().hex}",
            "history_namespace_id": namespace,
            "history_sequence": sequence,
            "operation": _OPERATION,
            "actor": _ACTOR,
            "capability": _CAPABILITY,
            "executor": admission._EXECUTOR,
            "production_profile_reference": admission._PROFILE_REFERENCE,
            "production_profile_fingerprint": _PROFILE.fingerprint,
            "artifact_reference": event.artifact_reference,
            "construction_execution_id": support.companion.construction_execution_id,
            "construction_receipt_fingerprint": (
                support.companion.construction_receipt_fingerprint
            ),
            "admission_execution_reference": support.companion.execution_reference(),
            "admission_history_fingerprint": admission_context,
            "prior_validity_references": (),
            "prior_validity_history_fingerprint": _prior_context(
                namespace, event.artifact_reference
            ),
            "validity_reference": event.reference(),
            "execution_started_at": started,
            "execution_completed_at": completed,
            "available_at": available,
            "schema_version": _SCHEMA,
        }
        for key, value in values.items():
            object.__setattr__(result, key, value)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._payload())
        )
        result._validate()
        return result

    def _payload(self) -> dict[str, object]:
        return {
            item.name: _project(getattr(self, item.name))
            for item in fields(self)
            if item.name != "fingerprint"
        }

    def _validate(self) -> None:
        _issued_id(self.execution_id, "polygon_completed_daily_validity:")
        _issued_id(
            self.history_namespace_id, "polygon_completed_daily_validity_history:"
        )
        admission._positive_integer(self.history_sequence, "history_sequence")
        if (
            self.schema_version != _SCHEMA
            or self.operation != _OPERATION
            or self.actor != _ACTOR
            or self.capability != _CAPABILITY
            or self.executor != admission._EXECUTOR
            or self.production_profile_reference != admission._PROFILE_REFERENCE
            or self.production_profile_fingerprint != _PROFILE.fingerprint
        ):
            raise ValueError("validity execution identity is not approved")
        self.admission_execution_reference.to_dict()
        self.validity_reference._validate()
        if (
            self.prior_validity_references != ()
            or self.prior_validity_history_fingerprint
            != _prior_context(self.history_namespace_id, self.artifact_reference)
            or self.validity_reference.status is not EvidenceValidityStatus.ACTIVE
            or self.validity_reference.scope != _PROFILE.scope
            or self.validity_reference.artifact_reference != self.artifact_reference
            or (
                self.admission_execution_reference.admission_record_reference.artifact_reference
            )
            != self.artifact_reference
            or self.admission_execution_reference.construction_execution_id
            != self.construction_execution_id
        ):
            raise ValueError("initial validity correspondence is invalid")
        started = admission._require_canonical_timestamp(
            self.execution_started_at, "started"
        )
        completed = admission._require_canonical_timestamp(
            self.execution_completed_at, "completed"
        )
        available = admission._require_canonical_timestamp(
            self.available_at, "available"
        )
        if (
            not self.admission_execution_reference.available_at
            <= started
            <= completed
            <= available
            or self.validity_reference.recorded_at != completed
            or self.validity_reference.effective_at != completed
        ):
            raise ValueError("validity issuance chronology is incoherent")
        if self.fingerprint != canonical_fingerprint(self._payload()):
            raise ValueError("validity companion fingerprint is invalid")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyProductionValidityResult:
    admission_result: admission.PolygonCompletedDailyProductionAdmissionResult
    validity_event: EvidenceValidityEvent
    companion: PolygonCompletedDailyValidityExecutionCompanion
    _admission_history: tuple[
        admission.PolygonCompletedDailyProductionAdmissionResult, ...
    ]

    def __init__(self) -> None:
        raise TypeError("validity result is issued only by trusted validity history")

    def _validate(self) -> None:
        self.admission_result._validate()
        self.validity_event._validate()
        self.companion._validate()
        if (
            self.validity_event.reference() != self.companion.validity_reference
            or self.validity_event.actor_identity != _ACTOR
            or self.validity_event.capability_identity != _CAPABILITY
            or self.validity_event.predecessor_validity_event_reference is not None
            or self.admission_result.companion.execution_reference()
            != self.companion.admission_execution_reference
            or self.admission_result.companion.construction_receipt_fingerprint
            != self.companion.construction_receipt_fingerprint
            or self.admission_result.admission_record.effective_at
            > self.validity_event.effective_at
            or _admission_context(self._admission_history)
            != self.companion.admission_history_fingerprint
        ):
            raise ValueError("validity result correspondence is invalid")


class _InMemoryPolygonCompletedDailyValidityHistory:
    __slots__ = ("_lock", "_namespace_id", "_state", "_pending")

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = f"polygon_completed_daily_validity_history:{uuid4().hex}"
        self._state: tuple[
            int, tuple[PolygonCompletedDailyProductionValidityResult, ...]
        ] = (1, ())
        self._pending: PolygonCompletedDailyProductionValidityResult | None = None

    def _validate(self) -> None:
        admission._require_complete_sequence(self._state[0], self._state[1])
        seen: set[tuple[str, str]] = set()
        execution_ids: set[str] = set()
        previous: datetime | None = None
        for result in self._state[1]:
            if type(result) is not PolygonCompletedDailyProductionValidityResult:
                raise ValueError("invalid validity history result type")
            result._validate()
            companion = result.companion
            key = (
                companion.artifact_reference.artifact_id,
                companion.artifact_reference.artifact_version,
            )
            if (
                key in seen
                or companion.execution_id in execution_ids
                or companion.history_namespace_id != self._namespace_id
                or (previous is not None and companion.available_at < previous)
            ):
                raise ValueError("conflicting or corrupt initial validity history")
            seen.add(key)
            execution_ids.add(companion.execution_id)
            previous = companion.available_at

    def _stage_publication(
        self, staged: PolygonCompletedDailyProductionValidityResult
    ) -> None:
        staged._validate()
        self._pending = staged


class PolygonCompletedDailyProductionValidityApplicationService:
    """Issue initial ACTIVE separately, and retain complete issuance history."""

    __slots__ = ("_admission_service", "_execution_clock", "_history")

    def __init__(
        self,
        admission_service: (
            admission.PolygonCompletedDailyProductionAdmissionApplicationService
        ),
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(admission_service)
            is not admission.PolygonCompletedDailyProductionAdmissionApplicationService
        ):
            raise TypeError("admission_service must be the exact trusted service")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._admission_service = admission_service
        self._execution_clock = (
            admission._utc_now if execution_clock is None else execution_clock
        )
        self._history = _InMemoryPolygonCompletedDailyValidityHistory()

    def issue_initial_active(
        self,
        request: PolygonCompletedDailyInitialActiveRequest,
    ) -> PolygonCompletedDailyProductionValidityResult:
        if type(request) is not PolygonCompletedDailyInitialActiveRequest:
            raise TypeError("request must be an exact initial ACTIVE request")
        request._validate()
        source = self._admission_service
        # Lock order agrees with admission issuance; no combined transaction exists.
        with (
            source._construction_service._history._lock,
            source._history._lock,
            self._history._lock,
        ):
            try:
                return self._issue_locked(request)
            except PolygonCompletedDailyValidityIssuanceRefused:
                raise
            except (TypeError, ValueError, RuntimeError) as error:
                raise PolygonCompletedDailyValidityIssuanceRefused(
                    PolygonCompletedDailyValidityRefusalReason.HISTORY_CONFLICT_OR_CORRUPTION,
                    "trusted validity issuance failed",
                ) from error
            finally:
                self._history._pending = None

    def _issue_locked(
        self, request: PolygonCompletedDailyInitialActiveRequest
    ) -> PolygonCompletedDailyProductionValidityResult:
        started = admission._timestamp(self._execution_clock())
        self._history._validate()
        initial_state = self._history._state
        source = self._admission_service
        construction = source._resolve_construction(
            admission.PolygonCompletedDailyAdmissionRequest(
                request.artifact_reference, request.construction_execution_id
            ),
            started,
        )
        next_admission, all_admissions = source._history._state
        admission._require_complete_sequence(next_admission, all_admissions)
        admission._validate_retained_entries(
            all_admissions, source._history._namespace_id
        )
        history = admission._relevant_admission_entries(
            all_admissions, request.artifact_reference, started
        )
        selected, occurrences = admission._resolve_effective_admission_results(
            history,
            request.artifact_reference,
            started,
            allow_empty=True,
        )
        if (
            selected is None
            or selected.disposition is not EvidenceAdmissionDisposition.ADMITTED
        ):
            raise PolygonCompletedDailyValidityIssuanceRefused(
                PolygonCompletedDailyValidityRefusalReason.ADMISSION_UNAVAILABLE,
                "authentic effective ADMITTED support is unavailable",
            )
        support = occurrences[0]
        if support.construction_result != construction or any(
            item.companion.artifact_reference != request.artifact_reference
            for item in history
        ):
            raise PolygonCompletedDailyValidityIssuanceRefused(
                PolygonCompletedDailyValidityRefusalReason.TARGET_MISMATCH,
                "selected admission does not bind the requested construction",
            )
        if any(
            _same_version(
                item.validity_event.artifact_reference, request.artifact_reference
            )
            for item in self._history._state[1]
        ):
            raise PolygonCompletedDailyValidityIssuanceRefused(
                PolygonCompletedDailyValidityRefusalReason.PRIOR_VALIDITY,
                "initial ACTIVE requires an empty validity history",
            )
        completed = admission._timestamp(self._execution_clock())
        if completed < started:
            raise PolygonCompletedDailyValidityIssuanceRefused(
                PolygonCompletedDailyValidityRefusalReason.TEMPORAL_FAILURE,
                "validity issuance time moved backward",
            )
        event = create_evidence_validity_event(
            validity_event_id=f"validity.polygon_completed_daily:{uuid4().hex}",
            artifact_reference=request.artifact_reference,
            status=EvidenceValidityStatus.ACTIVE,
            recorded_at=completed,
            effective_at=completed,
            actor_identity=_ACTOR,
            capability_identity=_CAPABILITY,
            reason="Authentic production admission supports initial activation.",
            scope=_PROFILE.scope,
        )
        sequence, entries = self._history._state
        companion = PolygonCompletedDailyValidityExecutionCompanion._create(
            sequence=sequence,
            namespace=self._history._namespace_id,
            support=support,
            admission_context=_admission_context(history),
            event=event,
            started=started,
            completed=completed,
            available=max(
                completed, entries[-1].companion.available_at if entries else completed
            ),
            seal=_SEAL,
        )
        result = object.__new__(PolygonCompletedDailyProductionValidityResult)
        for key, value in {
            "admission_result": support,
            "validity_event": event,
            "companion": companion,
            "_admission_history": history,
        }.items():
            object.__setattr__(result, key, value)
        self._history._stage_publication(result)
        available = admission._timestamp(self._execution_clock())
        if available < companion.available_at:
            raise PolygonCompletedDailyValidityIssuanceRefused(
                PolygonCompletedDailyValidityRefusalReason.TEMPORAL_FAILURE,
                "validity availability moved backward",
            )
        final_companion = object.__new__(
            PolygonCompletedDailyValidityExecutionCompanion
        )
        for item in fields(companion):
            object.__setattr__(
                final_companion, item.name, getattr(companion, item.name)
            )
        object.__setattr__(final_companion, "available_at", available)
        object.__setattr__(
            final_companion,
            "fingerprint",
            canonical_fingerprint(final_companion._payload()),
        )
        object.__setattr__(result, "companion", final_companion)
        result._validate()
        if source._history._state != (next_admission, all_admissions):
            raise ValueError("admission history changed during activation")
        if self._history._state != initial_state:
            raise ValueError("validity history changed during activation")
        admission._validate_retained_entries(
            all_admissions, source._history._namespace_id
        )
        source._resolve_construction(
            admission.PolygonCompletedDailyAdmissionRequest(
                request.artifact_reference, request.construction_execution_id
            ),
            started,
        )
        self._history._validate()
        self._history._state = (sequence + 1, (*entries, result))
        return result

    def get_validity_history(
        self,
        artifact_reference: EvidenceArtifactReference,
    ) -> tuple[PolygonCompletedDailyProductionValidityResult, ...]:
        return self._get_history(artifact_reference, None)

    def get_validity_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyProductionValidityResult, ...]:
        return self._get_history(
            artifact_reference, admission._timestamp(knowledge_as_of)
        )

    def _get_history(
        self,
        reference: EvidenceArtifactReference,
        cutoff: datetime | None,
    ) -> tuple[PolygonCompletedDailyProductionValidityResult, ...]:
        admission._copy_artifact_reference(reference)
        with self._history._lock:
            try:
                self._history._validate()
            except (TypeError, ValueError) as error:
                raise PolygonCompletedDailyValidityHistoryError(
                    "invalid validity history"
                ) from error
            results = tuple(
                item
                for item in self._history._state[1]
                if _same_version(item.validity_event.artifact_reference, reference)
                and (cutoff is None or item.companion.available_at <= cutoff)
            )
            if any(
                item.validity_event.artifact_reference != reference for item in results
            ):
                raise PolygonCompletedDailyValidityHistoryError(
                    "conflicting artifact identity"
                )
            return results


def _same_version(
    left: EvidenceArtifactReference, right: EvidenceArtifactReference
) -> bool:
    return (left.artifact_id, left.artifact_version) == (
        right.artifact_id,
        right.artifact_version,
    )


def _issued_id(value: str, prefix: str) -> None:
    if not value.startswith(prefix) or len(value.removeprefix(prefix)) != 32:
        raise ValueError("invalid platform execution identity")
    if any(char not in "0123456789abcdef" for char in value.removeprefix(prefix)):
        raise ValueError("invalid platform execution identity")


def _prior_context(namespace: str, reference: EvidenceArtifactReference) -> str:
    return canonical_fingerprint(
        {
            "schema_version": "polygon_completed_daily_initial_validity_history/v1",
            "namespace": namespace,
            "artifact_reference": reference.to_dict(),
            "scope": _PROFILE.scope,
            "prior_events": [],
        }
    )


def _admission_context(
    history: tuple[admission.PolygonCompletedDailyProductionAdmissionResult, ...],
) -> str:
    return canonical_fingerprint(
        {
            "schema_version": "polygon_completed_daily_activation_admission_history/v1",
            "admissions": [
                item.companion.execution_reference().to_dict() for item in history
            ],
        }
    )


def _project(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_project(item) for item in value]
    if isinstance(
        value,
        (
            EvidenceIdentityReference,
            EvidenceArtifactReference,
            EvidenceValidityReference,
            admission.PolygonCompletedDailyAdmissionExecutionReference,
        ),
    ):
        return value.to_dict()
    return value


__all__ = [
    "PolygonCompletedDailyInitialActiveRequest",
    "PolygonCompletedDailyProductionValidityApplicationService",
    "PolygonCompletedDailyProductionValidityResult",
    "PolygonCompletedDailyValidityExecutionCompanion",
    "PolygonCompletedDailyValidityHistoryError",
    "PolygonCompletedDailyValidityIssuanceRefused",
    "PolygonCompletedDailyValidityRefusalReason",
]
