"""Trusted production construction history for Polygon completed-daily Evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.polygon_completed_daily_evidence_candidate import (
    PolygonCompletedDailyAcquirer,
    PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    PolygonCompletedDailyEvidenceCandidateApplicationService,
)
from market_platform.application.polygon_completed_daily_production_governance import (
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE,
    _resolve_approved_polygon_completed_daily_production_profile,
)
from market_platform.evidence.authorization import EvidenceContractAuthorization
from market_platform.evidence.models import EvidenceArtifact
from market_platform.evidence.references import (
    EvidenceArtifactReference,
    EvidenceIdentityReference,
)
from market_platform.evidence_ingress import (
    PolygonCompletedDailyOhlcvEvidenceIngressResult,
    PolygonCompletedDailyOhlcvMaterial,
)

_VERSION = "1.0.0"
_PACKAGE_VERSION = "0.1.0"
_RECEIPT_SCHEMA = "polygon_completed_daily_construction_execution_receipt/v1"
_REQUEST_SCHEMA = "polygon_completed_daily_construction_request_identity/v1"
_RESULT_SCHEMA = "polygon_completed_daily_construction_result_identity/v1"
_OPERATION_SCHEMA = "polygon_completed_daily_production_construction_operation/v1"
_EXECUTOR_SCHEMA = "market_platform_software_executor/v1"
_EXECUTION_ID_PATTERN = re.compile(
    r"polygon_completed_daily_construction:[0-9a-f]{32}", flags=re.ASCII
)
_HISTORY_NAMESPACE_PATTERN = re.compile(
    r"polygon_completed_daily_construction_history:[0-9a-f]{32}", flags=re.ASCII
)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)
_RECEIPT_SEAL = object()
_RESULT_SEAL = object()
_HISTORY_SEAL = object()

_PROFILE = _resolve_approved_polygon_completed_daily_production_profile(
    _POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
)
_CONSTRUCTION_AUTHORIZATION = _PROFILE.construction_authorization
_OPERATION = EvidenceIdentityReference(
    namespace="market_platform.application.operation",
    identity_id="polygon_completed_daily_production_construction",
    identity_version=_VERSION,
    identity_fingerprint=canonical_fingerprint(
        {
            "schema_version": _OPERATION_SCHEMA,
            "operation_id": "polygon_completed_daily_production_construction",
            "operation_version": _VERSION,
            "construction_authorization_fingerprint": (
                _CONSTRUCTION_AUTHORIZATION.fingerprint
            ),
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


class PolygonCompletedDailyConstructionHistoryError(RuntimeError):
    """Trusted construction history is incomplete or internally inconsistent."""


class PolygonCompletedDailyConstructionHistoryConflictError(
    PolygonCompletedDailyConstructionHistoryError
):
    """One retained artifact identity resolves to conflicting construction facts."""


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyConstructionExecutionReceipt:
    """Immutable receipt for one retained trusted construction occurrence."""

    execution_id: str
    history_sequence: int
    history_namespace_id: str
    operation: EvidenceIdentityReference
    executor: EvidenceIdentityReference
    production_profile_fingerprint: str
    request_fingerprint: str
    construction_authorization: EvidenceContractAuthorization
    resolved_mapping_fingerprint: str
    artifact_reference: EvidenceArtifactReference
    material_fingerprint: str
    result_content_fingerprint: str
    execution_started_at: datetime
    response_received_at: datetime
    artifact_created_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    schema_version: str
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyConstructionExecutionReceipt is issued only by "
            "the trusted production construction history"
        )

    @classmethod
    def _create(
        cls,
        *,
        execution_id: str,
        history_sequence: int,
        history_namespace_id: str,
        request_fingerprint: str,
        resolved_mapping_fingerprint: str,
        artifact_reference: EvidenceArtifactReference,
        material_fingerprint: str,
        execution_started_at: datetime,
        response_received_at: datetime,
        artifact_created_at: datetime,
        execution_completed_at: datetime,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyConstructionExecutionReceipt:
        if seal is not _RECEIPT_SEAL:
            raise TypeError("construction execution receipt issuance is private")
        result = object.__new__(cls)
        artifact = _copy_artifact_reference(artifact_reference)
        values: dict[str, object] = {
            "execution_id": _execution_id(execution_id),
            "history_sequence": _positive_integer(
                history_sequence, "history_sequence"
            ),
            "history_namespace_id": _history_namespace_id(history_namespace_id),
            "operation": _copy_identity_reference(_OPERATION),
            "executor": _copy_identity_reference(_EXECUTOR),
            "production_profile_fingerprint": _fingerprint(
                _PROFILE.fingerprint, "production_profile_fingerprint"
            ),
            "request_fingerprint": _fingerprint(
                request_fingerprint, "request_fingerprint"
            ),
            "construction_authorization": _CONSTRUCTION_AUTHORIZATION,
            "resolved_mapping_fingerprint": _fingerprint(
                resolved_mapping_fingerprint, "resolved_mapping_fingerprint"
            ),
            "artifact_reference": artifact,
            "material_fingerprint": _fingerprint(
                material_fingerprint, "material_fingerprint"
            ),
            "result_content_fingerprint": _result_content_fingerprint(
                artifact, material_fingerprint
            ),
            "execution_started_at": _timestamp(
                execution_started_at, "execution_started_at"
            ),
            "response_received_at": _timestamp(
                response_received_at, "response_received_at"
            ),
            "artifact_created_at": _timestamp(
                artifact_created_at, "artifact_created_at"
            ),
            "execution_completed_at": _timestamp(
                execution_completed_at, "execution_completed_at"
            ),
            "available_at": _timestamp(available_at, "available_at"),
            "schema_version": _RECEIPT_SCHEMA,
        }
        for name, value in values.items():
            object.__setattr__(result, name, value)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "history_sequence": self.history_sequence,
            "history_namespace_id": self.history_namespace_id,
            "operation": self.operation.to_dict(),
            "executor": self.executor.to_dict(),
            "production_profile_fingerprint": self.production_profile_fingerprint,
            "request_fingerprint": self.request_fingerprint,
            "construction_authorization": self.construction_authorization.to_dict(),
            "resolved_mapping_fingerprint": self.resolved_mapping_fingerprint,
            "artifact_reference": self.artifact_reference.to_dict(),
            "material_fingerprint": self.material_fingerprint,
            "result_content_fingerprint": self.result_content_fingerprint,
            "execution_started_at": self.execution_started_at.isoformat(),
            "response_received_at": self.response_received_at.isoformat(),
            "artifact_created_at": self.artifact_created_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    @classmethod
    def _with_available_at(
        cls,
        staged: PolygonCompletedDailyConstructionExecutionReceipt,
        *,
        available_at: datetime,
        seal: object,
    ) -> PolygonCompletedDailyConstructionExecutionReceipt:
        if seal is not _RECEIPT_SEAL:
            raise TypeError("construction execution receipt publication is private")
        result = object.__new__(cls)
        for name in (
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
            "schema_version",
        ):
            object.__setattr__(result, name, getattr(staged, name))
        object.__setattr__(result, "available_at", available_at)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        return result

    def _validate(self) -> None:
        if self.schema_version != _RECEIPT_SCHEMA:
            raise ValueError("construction execution receipt schema is invalid")
        _execution_id(self.execution_id)
        _positive_integer(self.history_sequence, "history_sequence")
        _history_namespace_id(self.history_namespace_id)
        self.operation._validate()
        self.executor._validate()
        if (
            self.operation != _OPERATION
            or self.operation.fingerprint != _OPERATION.fingerprint
        ):
            raise ValueError("construction operation identity is not approved")
        if (
            self.executor != _EXECUTOR
            or self.executor.fingerprint != _EXECUTOR.fingerprint
        ):
            raise ValueError("construction executor identity is not approved")
        if self.production_profile_fingerprint != _PROFILE.fingerprint:
            raise ValueError("production profile fingerprint is not approved")
        _fingerprint(self.request_fingerprint, "request_fingerprint")
        if type(self.construction_authorization) is not EvidenceContractAuthorization:
            raise TypeError("construction_authorization type is invalid")
        self.construction_authorization.to_dict()
        if (
            self.construction_authorization != _CONSTRUCTION_AUTHORIZATION
            or self.construction_authorization.fingerprint
            != _CONSTRUCTION_AUTHORIZATION.fingerprint
        ):
            raise ValueError("construction authorization is not approved")
        _fingerprint(
            self.resolved_mapping_fingerprint, "resolved_mapping_fingerprint"
        )
        self.artifact_reference._validate()
        _fingerprint(self.material_fingerprint, "material_fingerprint")
        expected_result = _result_content_fingerprint(
            self.artifact_reference, self.material_fingerprint
        )
        if self.result_content_fingerprint != expected_result:
            raise ValueError("construction result content fingerprint is invalid")
        for name in (
            "execution_started_at",
            "response_received_at",
            "artifact_created_at",
            "execution_completed_at",
            "available_at",
        ):
            _require_canonical_timestamp(getattr(self, name), name)
        if not (
            self.execution_started_at
            <= self.response_received_at
            <= self.artifact_created_at
            <= self.execution_completed_at
            <= self.available_at
        ):
            raise ValueError("construction execution chronology is incoherent")
        expected = canonical_fingerprint(self._fingerprint_payload())
        if self.fingerprint != expected:
            raise ValueError("construction execution receipt fingerprint is invalid")

    def to_dict(self) -> dict[str, object]:
        """Return the exact bounded receipt projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyProductionConstructionResult:
    """Exact Candidate, material, request, and retained construction receipt."""

    request: PolygonCompletedDailyEvidenceCandidateApplicationRequest
    candidate_result: PolygonCompletedDailyOhlcvEvidenceIngressResult
    receipt: PolygonCompletedDailyConstructionExecutionReceipt

    def __init__(self) -> None:
        raise TypeError(
            "PolygonCompletedDailyProductionConstructionResult is created only by "
            "trusted production construction history"
        )

    @classmethod
    def _create(
        cls,
        *,
        request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
        candidate_result: PolygonCompletedDailyOhlcvEvidenceIngressResult,
        receipt: PolygonCompletedDailyConstructionExecutionReceipt,
        seal: object,
    ) -> PolygonCompletedDailyProductionConstructionResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production construction result creation is private")
        result = object.__new__(cls)
        object.__setattr__(result, "request", request)
        object.__setattr__(result, "candidate_result", candidate_result)
        object.__setattr__(result, "receipt", receipt)
        result._validate()
        return result

    @classmethod
    def _with_receipt(
        cls,
        staged: PolygonCompletedDailyProductionConstructionResult,
        *,
        receipt: PolygonCompletedDailyConstructionExecutionReceipt,
        seal: object,
    ) -> PolygonCompletedDailyProductionConstructionResult:
        if seal is not _RESULT_SEAL:
            raise TypeError("production construction result publication is private")
        result = object.__new__(cls)
        object.__setattr__(result, "request", staged.request)
        object.__setattr__(result, "candidate_result", staged.candidate_result)
        object.__setattr__(result, "receipt", receipt)
        return result

    @property
    def artifact(self) -> EvidenceArtifact:
        """Return the exact retained Candidate artifact."""

        self._validate()
        return self.candidate_result.artifact

    @property
    def material(self) -> PolygonCompletedDailyOhlcvMaterial:
        """Return the exact retained governed material."""

        self._validate()
        return self.candidate_result.material

    def _validate(self) -> None:
        _validate_candidate_correspondence(self.request, self.candidate_result)
        if type(self.receipt) is not PolygonCompletedDailyConstructionExecutionReceipt:
            raise TypeError("receipt type is invalid")
        self.receipt._validate()
        material = self.candidate_result.material
        artifact = self.candidate_result.artifact
        resolution = material.mapping_resolution_provenance
        if self.receipt.request_fingerprint != _request_fingerprint(self.request):
            raise ValueError("receipt does not bind the retained construction request")
        if self.receipt.artifact_reference != artifact.reference():
            raise ValueError("receipt does not bind the retained Candidate artifact")
        if self.receipt.material_fingerprint != material.fingerprint:
            raise ValueError("receipt does not bind the retained governed material")
        if self.receipt.resolved_mapping_fingerprint != resolution.mapping.fingerprint:
            raise ValueError("receipt does not bind the resolved mapping")
        temporal = artifact.temporal_identity
        if self.receipt.response_received_at != temporal.platform_received_at:
            raise ValueError("receipt does not bind the acquisition response time")
        if self.receipt.artifact_created_at != temporal.artifact_created_at:
            raise ValueError("receipt does not bind the Candidate creation time")


class _InMemoryPolygonCompletedDailyConstructionHistory:
    """Private complete history for the supported construction operation."""

    __slots__ = ("_lock", "_namespace_id", "_pending", "_state")

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = _issue_history_namespace_id()
        self._pending: PolygonCompletedDailyProductionConstructionResult | None = None
        self._state: tuple[
            int, tuple[PolygonCompletedDailyProductionConstructionResult, ...]
        ] = (1, ())

    def _retain(
        self,
        *,
        execution_id: str,
        request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
        candidate_result: PolygonCompletedDailyOhlcvEvidenceIngressResult,
        execution_started_at: datetime,
        completion_clock: Callable[[], datetime],
        availability_clock: Callable[[], datetime],
        seal: object,
    ) -> PolygonCompletedDailyProductionConstructionResult:
        if seal is not _HISTORY_SEAL:
            raise TypeError("trusted construction history retention is private")
        if not callable(completion_clock) or not callable(availability_clock):
            raise TypeError("completion and availability clocks must be callable")
        _execution_id(execution_id)
        _validate_candidate_correspondence(request, candidate_result)
        started_at = _timestamp(execution_started_at, "execution_started_at")
        completed_at = _timestamp(completion_clock(), "execution_completed_at")
        artifact = candidate_result.artifact
        material = candidate_result.material
        response_received_at = artifact.temporal_identity.platform_received_at
        artifact_created_at = artifact.temporal_identity.artifact_created_at

        with self._lock:
            next_sequence, entries = self._state
            _validate_retained_entries(
                entries,
                expected_namespace_id=self._namespace_id,
            )
            staged_available_at = max(
                completed_at,
                entries[-1].receipt.available_at if entries else completed_at,
            )
            staged_receipt = (
                PolygonCompletedDailyConstructionExecutionReceipt._create(
                    execution_id=execution_id,
                    history_sequence=next_sequence,
                    history_namespace_id=self._namespace_id,
                    request_fingerprint=_request_fingerprint(request),
                    resolved_mapping_fingerprint=(
                        material.mapping_resolution_provenance.mapping.fingerprint
                    ),
                    artifact_reference=artifact.reference(),
                    material_fingerprint=material.fingerprint,
                    execution_started_at=started_at,
                    response_received_at=response_received_at,
                    artifact_created_at=artifact_created_at,
                    execution_completed_at=completed_at,
                    available_at=staged_available_at,
                    seal=_RECEIPT_SEAL,
                )
            )
            staged = PolygonCompletedDailyProductionConstructionResult._create(
                request=request,
                candidate_result=candidate_result,
                receipt=staged_receipt,
                seal=_RESULT_SEAL,
            )
            try:
                self._stage_retention(staged)
                available_at = _timestamp(availability_clock(), "available_at")
                if available_at < completed_at:
                    raise ValueError("construction execution chronology is incoherent")
                if entries and available_at < entries[-1].receipt.available_at:
                    raise ValueError(
                        "construction availability must not move backward"
                    )
                receipt = (
                    PolygonCompletedDailyConstructionExecutionReceipt._with_available_at(
                        staged.receipt,
                        available_at=available_at,
                        seal=_RECEIPT_SEAL,
                    )
                )
                retained = (
                    PolygonCompletedDailyProductionConstructionResult._with_receipt(
                        staged,
                        receipt=receipt,
                        seal=_RESULT_SEAL,
                    )
                )
                self._state = (next_sequence + 1, (*entries, retained))
                return retained
            finally:
                self._pending = None

    def _stage_retention(
        self,
        staged: PolygonCompletedDailyProductionConstructionResult,
    ) -> None:
        staged._validate()
        self._pending = staged

    def _history(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime | None,
    ) -> tuple[PolygonCompletedDailyProductionConstructionResult, ...]:
        reference = _copy_artifact_reference(artifact_reference)
        cutoff = (
            None
            if knowledge_as_of is None
            else _timestamp(knowledge_as_of, "knowledge_as_of")
        )
        with self._lock:
            entries = self._state[1]
        try:
            _validate_retained_entries(
                entries,
                expected_namespace_id=self._namespace_id,
            )
        except (TypeError, ValueError) as error:
            raise PolygonCompletedDailyConstructionHistoryError(
                "retained construction history is incomplete or corrupt"
            ) from error
        relevant = tuple(
            item
            for item in entries
            if item.receipt.artifact_reference.artifact_id == reference.artifact_id
            and item.receipt.artifact_reference.artifact_version
            == reference.artifact_version
            and (cutoff is None or item.receipt.available_at <= cutoff)
        )
        if any(item.receipt.artifact_reference != reference for item in relevant):
            raise PolygonCompletedDailyConstructionHistoryConflictError(
                "artifact identity has conflicting retained construction history"
            )
        return tuple(sorted(relevant, key=lambda item: item.receipt.history_sequence))


class PolygonCompletedDailyProductionConstructionApplicationService:
    """Execute and retain the approved Polygon Candidate construction operation."""

    __slots__ = ("_candidate_service", "_execution_clock", "_history")

    def __init__(
        self,
        acquirer: PolygonCompletedDailyAcquirer,
        *,
        creation_clock: Callable[[], datetime] | None = None,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._candidate_service = (
            PolygonCompletedDailyEvidenceCandidateApplicationService(
                acquirer,
                creation_clock=creation_clock,
            )
        )
        self._execution_clock = _utc_now if execution_clock is None else execution_clock
        self._history = _InMemoryPolygonCompletedDailyConstructionHistory()

    async def execute(
        self,
        request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    ) -> PolygonCompletedDailyProductionConstructionResult:
        """Construct and atomically retain one authentic available result."""

        if (
            type(request)
            is not PolygonCompletedDailyEvidenceCandidateApplicationRequest
        ):
            raise TypeError(
                "request must be an exact "
                "PolygonCompletedDailyEvidenceCandidateApplicationRequest"
            )
        request._validate()
        execution_started_at = _timestamp(
            self._execution_clock(), "execution_started_at"
        )
        execution_id = _issue_execution_id()
        candidate_result = await self._candidate_service.execute(request)
        return self._history._retain(
            execution_id=execution_id,
            request=request,
            candidate_result=candidate_result,
            execution_started_at=execution_started_at,
            completion_clock=self._execution_clock,
            availability_clock=self._execution_clock,
            seal=_HISTORY_SEAL,
        )

    def get_construction_history(
        self,
        artifact_reference: EvidenceArtifactReference,
    ) -> tuple[PolygonCompletedDailyProductionConstructionResult, ...]:
        """Return complete retained construction history for an exact version."""

        return self._history._history(artifact_reference, knowledge_as_of=None)

    def get_construction_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyProductionConstructionResult, ...]:
        """Return authentic results actually available by one knowledge cutoff."""

        return self._history._history(
            artifact_reference,
            knowledge_as_of=knowledge_as_of,
        )


def _validate_candidate_correspondence(
    request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
    candidate_result: PolygonCompletedDailyOhlcvEvidenceIngressResult,
) -> None:
    if type(request) is not PolygonCompletedDailyEvidenceCandidateApplicationRequest:
        raise TypeError("retained construction request type is invalid")
    request._validate()
    if type(candidate_result) is not PolygonCompletedDailyOhlcvEvidenceIngressResult:
        raise TypeError("candidate_result type is invalid")
    material = candidate_result.material
    artifact = candidate_result.artifact
    if type(material) is not PolygonCompletedDailyOhlcvMaterial:
        raise TypeError("retained material type is invalid")
    if type(artifact) is not EvidenceArtifact:
        raise TypeError("retained Candidate artifact type is invalid")
    artifact._validate()
    material.mapping_resolution_provenance._validate()
    expected_material_fingerprint = canonical_fingerprint(
        material._fingerprint_payload()
    )
    if material.fingerprint != expected_material_fingerprint:
        raise ValueError("retained material fingerprint does not match content")
    if artifact.material_fingerprint != material.fingerprint:
        raise ValueError("Candidate artifact and governed material do not correspond")
    if artifact.contract_authorization != _CONSTRUCTION_AUTHORIZATION:
        raise ValueError("Candidate does not retain the approved authorization")
    if artifact.contract_authorization.fingerprint != (
        _CONSTRUCTION_AUTHORIZATION.fingerprint
    ):
        raise ValueError("Candidate authorization fingerprint is not approved")
    if artifact.provenance.producer != _PROFILE.construction_producer:
        raise ValueError("Candidate producer is not the approved producer")
    if artifact.subjects != (material.canonical_subject,):
        raise ValueError("Candidate subject does not match governed material")
    temporal = artifact.temporal_identity
    if temporal.source_revision != material.fingerprint:
        raise ValueError("Candidate source revision does not match governed material")
    if material.external_instrument_identity != request.external_identity:
        raise ValueError("retained material does not match requested external identity")
    if material.query_as_of != request.query_as_of:
        raise ValueError("retained material does not match request query_as_of")
    if material.start_session_date != request.requested_from.isoformat():
        raise ValueError("retained material does not match requested_from")
    if material.end_session_date != request.requested_to.isoformat():
        raise ValueError("retained material does not match requested_to")
    provenance = material.request_provenance
    if (
        provenance.requested_ticker != request.external_identity.external_symbol
        or provenance.requested_from != request.requested_from.isoformat()
        or provenance.requested_to != request.requested_to.isoformat()
    ):
        raise ValueError("retained request provenance does not match request")
    resolution = material.mapping_resolution_provenance
    if (
        resolution.external_identity != request.external_identity
        or resolution.resolved_as_of != request.query_as_of
        or not any(
            mapping == resolution.mapping
            and mapping.fingerprint == resolution.mapping.fingerprint
            for mapping in request.mappings
        )
    ):
        raise ValueError("retained mapping resolution does not match request context")


def _validate_retained_entries(
    entries: tuple[PolygonCompletedDailyProductionConstructionResult, ...],
    *,
    expected_namespace_id: str,
) -> None:
    if type(entries) is not tuple:
        raise TypeError("construction history must be an exact tuple")
    execution_ids: set[str] = set()
    sequences: set[int] = set()
    prior_sequence = 0
    prior_availability: datetime | None = None
    namespace_id = _history_namespace_id(expected_namespace_id)
    for item in entries:
        if type(item) is not PolygonCompletedDailyProductionConstructionResult:
            raise TypeError("construction history contains an invalid result type")
        item._validate()
        receipt = item.receipt
        if receipt.history_namespace_id != namespace_id:
            raise ValueError("construction history namespace does not correspond")
        if receipt.execution_id in execution_ids:
            raise ValueError("construction history duplicates an execution identity")
        if receipt.history_sequence in sequences:
            raise ValueError("construction history duplicates a sequence")
        if receipt.history_sequence <= prior_sequence:
            raise ValueError("construction history sequence is not increasing")
        if (
            prior_availability is not None
            and receipt.available_at < prior_availability
        ):
            raise ValueError("construction history availability moves backward")
        execution_ids.add(receipt.execution_id)
        sequences.add(receipt.history_sequence)
        prior_sequence = receipt.history_sequence
        prior_availability = receipt.available_at


def _request_fingerprint(
    request: PolygonCompletedDailyEvidenceCandidateApplicationRequest,
) -> str:
    request._validate()
    return canonical_fingerprint(
        {
            "schema_version": _REQUEST_SCHEMA,
            "external_identity": request.external_identity.to_dict(),
            "mappings": [mapping.to_dict() for mapping in request.mappings],
            "requested_from": request.requested_from.isoformat(),
            "requested_to": request.requested_to.isoformat(),
            "query_as_of": request.query_as_of.isoformat(),
        }
    )


def _result_content_fingerprint(
    artifact_reference: EvidenceArtifactReference,
    material_fingerprint: str,
) -> str:
    return canonical_fingerprint(
        {
            "schema_version": _RESULT_SCHEMA,
            "artifact_reference": artifact_reference.to_dict(),
            "material_fingerprint": _fingerprint(
                material_fingerprint, "material_fingerprint"
            ),
        }
    )


def _copy_identity_reference(
    value: EvidenceIdentityReference,
) -> EvidenceIdentityReference:
    if type(value) is not EvidenceIdentityReference:
        raise TypeError("identity must be an EvidenceIdentityReference")
    value._validate()
    return EvidenceIdentityReference(
        namespace=value.namespace,
        identity_id=value.identity_id,
        identity_version=value.identity_version,
        identity_fingerprint=value.identity_fingerprint,
    )


def _copy_artifact_reference(
    value: EvidenceArtifactReference,
) -> EvidenceArtifactReference:
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
    if value is not canonical and (
        type(value) is not datetime
        or value.tzinfo is not UTC
        or value.isoformat() != canonical.isoformat()
    ):
        raise ValueError(f"{field_name} must retain canonical UTC state")
    return canonical


def _fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase sha256 fingerprint")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a positive exact integer")
    return value


def _execution_id(value: object) -> str:
    if type(value) is not str or _EXECUTION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("execution_id is not a platform-issued canonical identity")
    return value


def _history_namespace_id(value: object) -> str:
    if type(value) is not str or _HISTORY_NAMESPACE_PATTERN.fullmatch(value) is None:
        raise ValueError("history_namespace_id is not a canonical identity")
    return value


def _issue_execution_id() -> str:
    return f"polygon_completed_daily_construction:{uuid4().hex}"


def _issue_history_namespace_id() -> str:
    return f"polygon_completed_daily_construction_history:{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "PolygonCompletedDailyConstructionExecutionReceipt",
    "PolygonCompletedDailyConstructionHistoryConflictError",
    "PolygonCompletedDailyConstructionHistoryError",
    "PolygonCompletedDailyProductionConstructionApplicationService",
    "PolygonCompletedDailyProductionConstructionResult",
]
