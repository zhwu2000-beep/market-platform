"""Trusted whole-material qualification; canonical Evidence remains decisive."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime, time
from enum import StrEnum
from threading import Lock
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_construction as c,
)
from market_platform.application import (
    polygon_completed_daily_production_freshness as f,
)
from market_platform.application import (
    polygon_completed_daily_production_governance as g,
)
from market_platform.application import (
    polygon_completed_daily_production_validation as v,
)
from market_platform.application import (
    polygon_completed_daily_production_validity as av,
)
from market_platform.evidence import (
    EvidenceAdmissionState,
    EvidenceArtifactReference,
    evaluation,
)

_PROFILE = g._POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
_PROFILE_FINGERPRINT = (
    "sha256:341279ccfd6839287e5e5c9af46f9eb834577a07e9ffd1a16c0e27ccc35cfd49"
)
_ANALYSIS_FINGERPRINT = (
    "sha256:c2f1ccd7f9cfa51281c07cec7f62ac43940a72c6af1f8d162f9c8fbf97af78f7"
)
_NY = ZoneInfo("America/New_York")


class PolygonCompletedDailyQualificationRefusalReason(StrEnum):
    INPUT_UNAVAILABLE = "input_unavailable"
    HISTORY_INCOMPLETE = "history_incomplete_or_corrupt"
    TEMPORAL_FAILURE = "temporal_failure"
    PROFILE_MISMATCH = "profile_mismatch"
    TASK_UNAVAILABLE = "task_freshness_unavailable"
    LIFECYCLE_REFUSED = "canonical_lifecycle_refused"
    MAPPING_FAILURE = "historical_mapping_coverage_failure"
    INCOMPLETE_MATERIAL = "whole_material_not_completed"
    PUBLICATION_FAILED = "qualification_publication_failed"


class PolygonCompletedDailyQualificationRefused(RuntimeError):
    """No qualification published; a canonical refusal retains its full state."""

    def __init__(
        self,
        reason: PolygonCompletedDailyQualificationRefusalReason,
        message: str,
        *,
        canonical_state: EvidenceAdmissionState | None = None,
    ) -> None:
        self.reason = reason
        self.canonical_state = canonical_state
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyQualificationRequest:
    artifact_reference: EvidenceArtifactReference
    construction_execution_id: str
    analysis_as_of: datetime
    knowledge_as_of: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            a._copy_artifact_reference(self.artifact_reference),
        )
        a._construction_execution_id(self.construction_execution_id)
        object.__setattr__(self, "analysis_as_of", a._timestamp(self.analysis_as_of))
        if self.knowledge_as_of is not None:
            object.__setattr__(
                self, "knowledge_as_of", a._timestamp(self.knowledge_as_of)
            )
            if self.analysis_as_of > self.knowledge_as_of:
                raise PolygonCompletedDailyQualificationRefused(
                    PolygonCompletedDailyQualificationRefusalReason.TEMPORAL_FAILURE,
                    "analysis/effective cutoff is after knowledge cutoff",
                )


@dataclass(frozen=True, slots=True)
class _TrustedHistory:
    constructions: tuple[c.PolygonCompletedDailyProductionConstructionResult, ...]
    validations: tuple[v.PolygonCompletedDailyProductionValidationResult, ...]
    freshness: tuple[f.PolygonCompletedDailyProductionFreshnessResult, ...]
    admissions: tuple[a.PolygonCompletedDailyProductionAdmissionResult, ...]
    validity: tuple[av.PolygonCompletedDailyProductionValidityResult, ...]
    knowledge_as_of: datetime
    namespaces: tuple[str, ...]

    def projection(self) -> dict[str, object]:
        return {
            "schema_version": "polygon_completed_daily_qualification_history/v1",
            "knowledge_as_of": self.knowledge_as_of.isoformat(),
            "namespaces": list(self.namespaces),
            "construction": [item.receipt.to_dict() for item in self.constructions],
            "validation": [item.companion.to_dict() for item in self.validations],
            "freshness": [item.companion.to_dict() for item in self.freshness],
            "admission": [item.companion.to_dict() for item in self.admissions],
            "validity": [item.companion.to_dict() for item in self.validity],
        }

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self.projection())


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyQualifiedUse:
    """Retained occurrence, never a portable permission token or import authority."""

    execution_id: str
    history_sequence: int
    history_namespace_id: str
    construction_result: c.PolygonCompletedDailyProductionConstructionResult
    production_profile: g._ProductionGovernanceProfile
    analysis_as_of: datetime
    effective_as_of: datetime
    knowledge_as_of: datetime
    task_freshness_result: f.PolygonCompletedDailyProductionFreshnessResult
    canonical_state: EvidenceAdmissionState
    history_context: _TrustedHistory
    mapping_context_fingerprint: str
    all_row_mapping_covered: bool
    whole_material_completed: bool
    original_row_count: int
    original_ordered_dates: tuple[str, ...]
    original_row_date_fingerprint: str
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("qualified use is published only by trusted qualification")

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": "polygon_completed_daily_qualified_use/v1",
            "execution_id": self.execution_id,
            "history_sequence": self.history_sequence,
            "history_namespace_id": self.history_namespace_id,
            "construction_receipt": self.construction_result.receipt.to_dict(),
            "material_fingerprint": self.construction_result.material.fingerprint,
            "production_profile": self.production_profile.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "effective_as_of": self.effective_as_of.isoformat(),
            "knowledge_as_of": self.knowledge_as_of.isoformat(),
            "task_freshness": self.task_freshness_result.companion.to_dict(),
            "canonical_state": self.canonical_state.to_dict(),
            "canonical_is_consumable_required": True,
            "history_context": self.history_context.projection(),
            "history_context_fingerprint": self.history_context.fingerprint,
            "mapping_context_fingerprint": self.mapping_context_fingerprint,
            "all_row_mapping_covered": self.all_row_mapping_covered,
            "whole_material_completed": self.whole_material_completed,
            "original_row_count": self.original_row_count,
            "original_ordered_dates": list(self.original_ordered_dates),
            "original_row_date_fingerprint": self.original_row_date_fingerprint,
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError(
                "qualified use fingerprint does not match retained content"
            )
        return {**payload, "fingerprint": self.fingerprint}


class _QualificationHistory:
    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = (
            f"polygon_completed_daily_qualification_history:{uuid4().hex}"
        )
        self._state: tuple[int, tuple[PolygonCompletedDailyQualifiedUse, ...]] = (1, ())
        self._pending: PolygonCompletedDailyQualifiedUse | None = None

    def _stage_publication(self, result: PolygonCompletedDailyQualifiedUse) -> None:
        result.to_dict()
        self._pending = result


class PolygonCompletedDailyProductionQualificationApplicationService:
    """Authenticate all retained history, require canonical admission, qualify use."""

    def __init__(
        self,
        validity_service: av.PolygonCompletedDailyProductionValidityApplicationService,
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(validity_service)
            is not av.PolygonCompletedDailyProductionValidityApplicationService
        ):
            raise TypeError("validity_service must be the exact trusted service")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._validity_service = validity_service
        self._clock = a._utc_now if execution_clock is None else execution_clock
        self._history = _QualificationHistory()

    def qualify(
        self, request: PolygonCompletedDailyQualificationRequest
    ) -> PolygonCompletedDailyQualifiedUse:
        if type(request) is not PolygonCompletedDailyQualificationRequest:
            raise TypeError("request must be an exact qualification request")
        request = replace(request)
        started = a._timestamp(self._clock())
        if request.knowledge_as_of is not None and request.knowledge_as_of > started:
            raise PolygonCompletedDailyQualificationRefused(
                PolygonCompletedDailyQualificationRefusalReason.TEMPORAL_FAILURE,
                "knowledge cutoff cannot claim future knowledge",
            )
        try:
            _approved_profile()
            source = self._validity_service._admission_service
            with ExitStack() as stack:
                self._lock_inputs(stack)
                initial = self._snapshot(request, request.knowledge_as_of or started)
                _target(initial, request)
            tasks = tuple(
                item
                for item in initial.freshness
                if item.companion.construction_execution_id
                == request.construction_execution_id
                and item.freshness_record.freshness_rule == _PROFILE.task_freshness.rule
                and item.freshness_record.evaluation_as_of == request.analysis_as_of
            )
            # Historical replay reuses only an actual retained exact-context execution.
            if request.knowledge_as_of is not None and tasks:
                task = tasks[-1]
            else:
                task = source._freshness_service.execute_task(
                    f.PolygonCompletedDailyTaskFreshnessRequest(
                        request.artifact_reference,
                        request.construction_execution_id,
                        request.analysis_as_of,
                    )
                )
                if task.companion.execution_started_at < started:
                    raise ValueError(
                        "task execution clock precedes qualification start"
                    )
            with ExitStack() as stack:
                self._lock_inputs(stack)
                stack.enter_context(self._history._lock)
                captured = a._timestamp(self._clock())
                cutoff = request.knowledge_as_of or captured
                if captured < started or cutoff < request.analysis_as_of:
                    raise PolygonCompletedDailyQualificationRefused(
                        PolygonCompletedDailyQualificationRefusalReason.TEMPORAL_FAILURE,
                        "qualification clock or effective cutoff is incoherent",
                    )
                history = self._snapshot(request, cutoff)
                target = _target(history, request)
                if (
                    task not in history.freshness
                    or task.companion.available_at > cutoff
                ):
                    raise PolygonCompletedDailyQualificationRefused(
                        PolygonCompletedDailyQualificationRefusalReason.TASK_UNAVAILABLE,
                        "exact task freshness was not available by knowledge cutoff",
                    )
                state = evaluation.evaluate_evidence_admission_as_of(
                    artifact=target.artifact,
                    admission_scope=_PROFILE.scope,
                    validation_records=_unique(
                        tuple(item.validation_record for item in history.validations)
                    ),
                    freshness_evaluations=_unique(
                        tuple(item.freshness_record for item in history.freshness)
                    ),
                    admission_records=_unique(
                        tuple(item.admission_record for item in history.admissions)
                    ),
                    validity_events=_unique(
                        tuple(item.validity_event for item in history.validity)
                    ),
                    admission_ruleset=_PROFILE.admission_ruleset,
                    knowledge_as_of=cutoff,
                    effective_as_of=request.analysis_as_of,
                )
                if state.is_consumable is not True:
                    raise PolygonCompletedDailyQualificationRefused(
                        PolygonCompletedDailyQualificationRefusalReason.LIFECYCLE_REFUSED,
                        "canonical Evidence admission evaluation refused consumption",
                        canonical_state=state,
                    )
                profile = _approved_profile()
                mapping_context, dates = _qualify_material(
                    target, request.analysis_as_of, cutoff
                )
                completed = a._timestamp(self._clock())
                if completed < captured or completed < task.companion.available_at:
                    raise ValueError("qualification completion clock moved backward")
                return self._publish(
                    target,
                    history,
                    task,
                    state,
                    profile,
                    mapping_context,
                    dates,
                    request.analysis_as_of,
                    started,
                    completed,
                )
        except PolygonCompletedDailyQualificationRefused:
            raise
        except f.PolygonCompletedDailyFreshnessExecutionRefused as error:
            raise PolygonCompletedDailyQualificationRefused(
                PolygonCompletedDailyQualificationRefusalReason.TASK_UNAVAILABLE,
                "exact task freshness execution failed; no repair attempted",
            ) from error
        except (TypeError, ValueError, RuntimeError) as error:
            raise PolygonCompletedDailyQualificationRefused(
                PolygonCompletedDailyQualificationRefusalReason.HISTORY_INCOMPLETE,
                "trusted qualification context cannot be authenticated",
            ) from error

    def _lock_inputs(self, stack: ExitStack) -> None:
        source = self._validity_service._admission_service
        for lock in (
            source._construction_service._history._lock,
            source._validation_service._history._lock,
            source._freshness_service._history._lock,
            source._history._lock,
            self._validity_service._history._lock,
        ):
            stack.enter_context(lock)

    def _snapshot(
        self, request: PolygonCompletedDailyQualificationRequest, cutoff: datetime
    ) -> _TrustedHistory:
        source = self._validity_service._admission_service
        cs = source._construction_service._history
        vs = source._validation_service._history
        fs = source._freshness_service._history
        ads = source._history
        vals = self._validity_service._history
        a._require_complete_sequence(*cs._state, attribute="receipt")
        for store in (vs, fs, ads, vals):
            a._require_complete_sequence(*store._state)
        c._validate_retained_entries(
            cs._state[1], expected_namespace_id=cs._namespace_id
        )
        v._validate_retained_entries(
            vs._state[1], expected_namespace_id=vs._namespace_id
        )
        f._validate_retained_entries(
            fs._state[1], expected_namespace_id=fs._namespace_id
        )
        a._validate_retained_entries(ads._state[1], ads._namespace_id)
        vals._validate()
        reference = request.artifact_reference
        constructions = tuple(
            item
            for item in cs._state[1]
            if av._same_version(item.receipt.artifact_reference, reference)
            and item.receipt.available_at <= cutoff
        )
        validations = tuple(
            item for item in vs._state[1] if _visible(item.companion, reference, cutoff)
        )
        fresh = tuple(
            item for item in fs._state[1] if _visible(item.companion, reference, cutoff)
        )
        admissions = tuple(
            item
            for item in ads._state[1]
            if _visible(item.companion, reference, cutoff)
        )
        events = tuple(
            item
            for item in vals._state[1]
            if _visible(item.companion, reference, cutoff)
        )
        for item in constructions:
            if (
                item.artifact.reference() != reference
                or item.receipt.production_profile_fingerprint != _PROFILE_FINGERPRINT
            ):
                raise ValueError("construction artifact/profile mismatch")
        results: tuple[
            v.PolygonCompletedDailyProductionValidationResult
            | f.PolygonCompletedDailyProductionFreshnessResult
            | a.PolygonCompletedDailyProductionAdmissionResult,
            ...,
        ] = (*validations, *fresh, *admissions)
        for result in results:
            if (
                result.construction_result not in constructions
                or result.companion.artifact_reference != reference
            ):
                raise ValueError(
                    "lifecycle execution lacks exact available construction"
                )
        # Embedded issuance provenance must resolve to actual retained inputs.
        for issued in admissions:
            support = issued._prerequisites
            for concern_history in support.validation_histories:
                if any(item not in validations for item in concern_history):
                    raise ValueError("admission validation provenance unavailable")
            if any(item not in fresh for item in support.freshness_history):
                raise ValueError("admission freshness provenance unavailable")
        for event in events:
            if event.admission_result not in admissions or any(
                item not in admissions for item in event._admission_history
            ):
                raise ValueError("validity admission provenance unavailable")
        return _TrustedHistory(
            constructions,
            validations,
            fresh,
            admissions,
            events,
            cutoff,
            (
                cs._namespace_id,
                vs._namespace_id,
                fs._namespace_id,
                ads._namespace_id,
                vals._namespace_id,
            ),
        )

    def _publish(
        self,
        target: c.PolygonCompletedDailyProductionConstructionResult,
        history: _TrustedHistory,
        task: f.PolygonCompletedDailyProductionFreshnessResult,
        state: EvidenceAdmissionState,
        profile: g._ProductionGovernanceProfile,
        mapping_context: str,
        dates: tuple[str, ...],
        analysis: datetime,
        started: datetime,
        completed: datetime,
    ) -> PolygonCompletedDailyQualifiedUse:
        self._check_history()
        sequence, entries = self._history._state
        result = object.__new__(PolygonCompletedDailyQualifiedUse)
        values: dict[str, object] = {
            "execution_id": f"polygon_completed_daily_qualification:{uuid4().hex}",
            "history_sequence": sequence,
            "history_namespace_id": self._history._namespace_id,
            "construction_result": target,
            "production_profile": profile,
            "analysis_as_of": analysis,
            "effective_as_of": analysis,
            "knowledge_as_of": history.knowledge_as_of,
            "task_freshness_result": task,
            "canonical_state": state,
            "history_context": history,
            "mapping_context_fingerprint": mapping_context,
            "all_row_mapping_covered": True,
            "whole_material_completed": True,
            "original_row_count": len(dates),
            "original_ordered_dates": dates,
            "original_row_date_fingerprint": canonical_fingerprint(
                {
                    "schema_version": "polygon_completed_daily_row_dates/v1",
                    "ordered_session_dates": list(dates),
                    "row_count": len(dates),
                }
            ),
            "execution_started_at": started,
            "execution_completed_at": completed,
            "available_at": completed,
        }
        for key, value in values.items():
            object.__setattr__(result, key, value)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._payload())
        )
        try:
            self._history._stage_publication(result)
            available = a._timestamp(self._clock())
            if available < completed or (
                entries and available < entries[-1].available_at
            ):
                raise ValueError("qualification publication clock moved backward")
            published = object.__new__(PolygonCompletedDailyQualifiedUse)
            for item in fields(result):
                object.__setattr__(published, item.name, getattr(result, item.name))
            object.__setattr__(published, "available_at", available)
            object.__setattr__(
                published, "fingerprint", canonical_fingerprint(published._payload())
            )
            self._history._state = (sequence + 1, (*entries, published))
            return published
        except (TypeError, ValueError, RuntimeError) as error:
            raise PolygonCompletedDailyQualificationRefused(
                PolygonCompletedDailyQualificationRefusalReason.PUBLICATION_FAILED,
                "qualification publication failed; no success exposed",
            ) from error
        finally:
            self._history._pending = None

    def _check_history(self) -> None:
        sequence, entries = self._history._state
        if sequence != len(entries) + 1:
            raise ValueError("qualification history incomplete")
        previous: datetime | None = None
        ids: set[str] = set()
        for index, item in enumerate(entries, 1):
            item.to_dict()
            if (
                item.history_sequence != index
                or item.history_namespace_id != self._history._namespace_id
                or item.execution_id in ids
            ):
                raise ValueError("qualification occurrence identity corrupt")
            if previous is not None and item.available_at < previous:
                raise ValueError("qualification history availability moved backward")
            ids.add(item.execution_id)
            previous = item.available_at

    def get_qualification_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyQualifiedUse, ...]:
        reference = a._copy_artifact_reference(artifact_reference)
        cutoff = a._timestamp(knowledge_as_of)
        with self._history._lock:
            self._check_history()
            return tuple(
                item
                for item in self._history._state[1]
                if item.construction_result.artifact.reference() == reference
                and item.available_at <= cutoff
            )


def _unique[T](records: tuple[T, ...]) -> tuple[T, ...]:
    """Collapse content-identical records only; retain all execution companions."""
    result: list[T] = []
    for record in records:
        if record not in result:
            result.append(record)
    return tuple(result)


def _visible(
    companion: v.PolygonCompletedDailyValidationExecutionCompanion
    | f.PolygonCompletedDailyFreshnessExecutionCompanion
    | a.PolygonCompletedDailyAdmissionExecutionCompanion
    | av.PolygonCompletedDailyValidityExecutionCompanion,
    reference: EvidenceArtifactReference,
    cutoff: datetime,
) -> bool:
    return (
        av._same_version(companion.artifact_reference, reference)
        and companion.available_at <= cutoff
    )


def _target(
    history: _TrustedHistory, request: PolygonCompletedDailyQualificationRequest
) -> c.PolygonCompletedDailyProductionConstructionResult:
    matches = tuple(
        item
        for item in history.constructions
        if item.receipt.execution_id == request.construction_execution_id
    )
    if len(matches) != 1:
        raise PolygonCompletedDailyQualificationRefused(
            PolygonCompletedDailyQualificationRefusalReason.INPUT_UNAVAILABLE,
            "retained construction/material/mapping context unavailable by cutoff",
        )
    return matches[0]


def _approved_profile() -> g._ProductionGovernanceProfile:
    try:
        profile = g._resolve_approved_polygon_completed_daily_production_profile(
            _PROFILE
        )
        if (
            profile.fingerprint != _PROFILE_FINGERPRINT
            or profile.analysis_profile.get("profile_fingerprint")
            != _ANALYSIS_FINGERPRINT
        ):
            raise ValueError("frozen production/analysis profile mismatch")
        return profile
    except (TypeError, ValueError) as error:
        raise PolygonCompletedDailyQualificationRefused(
            PolygonCompletedDailyQualificationRefusalReason.PROFILE_MISMATCH,
            "exact approved consumer/use/analysis/transformation is required",
        ) from error


def _qualify_material(
    target: c.PolygonCompletedDailyProductionConstructionResult,
    analysis: datetime,
    cutoff: datetime,
) -> tuple[str, tuple[str, ...]]:
    # Slice 2 retains the entire immutable registry/request at receipt availability.
    if target.receipt.available_at > cutoff:
        raise PolygonCompletedDailyQualificationRefused(
            PolygonCompletedDailyQualificationRefusalReason.INPUT_UNAVAILABLE,
            "trusted retained mapping context unavailable",
        )
    request = target.request
    selected = target.material.mapping_resolution_provenance.mapping
    mappings = tuple(
        item
        for item in request.mappings
        if item.external_identity == request.external_identity
    )
    dates = tuple(row.session_date for row in target.material.rows)
    for mapping in mappings:
        for bound in (mapping.valid_from, mapping.expires_at):
            if bound is not None and (
                bound.tzinfo is not UTC or bound.time() != time()
            ):
                raise PolygonCompletedDailyQualificationRefused(
                    PolygonCompletedDailyQualificationRefusalReason.MAPPING_FAILURE,
                    "partial-day mapping interval unsupported",
                )
    # Date-label comparison only after proving supported midnight-UTC interval form.
    # No research timestamp or numeric representation is constructed.
    for label in dates:
        covering = tuple(
            item
            for item in mappings
            if item.valid_from.date().isoformat() <= label
            and (item.expires_at is None or label < item.expires_at.date().isoformat())
        )
        if len(covering) != 1 or covering[0] != selected:
            raise PolygonCompletedDailyQualificationRefused(
                PolygonCompletedDailyQualificationRefusalReason.MAPPING_FAILURE,
                "every original row requires the same exact unambiguous mapping",
            )
    if not dates or any(
        label >= analysis.astimezone(_NY).date().isoformat() for label in dates
    ):
        raise PolygonCompletedDailyQualificationRefused(
            PolygonCompletedDailyQualificationRefusalReason.INCOMPLETE_MATERIAL,
            "every original row must precede the New York analysis date",
        )
    return canonical_fingerprint(
        {
            "schema_version": "polygon_completed_daily_mapping_coverage/v1",
            "construction_receipt_fingerprint": target.receipt.fingerprint,
            "available_at": target.receipt.available_at.isoformat(),
            "external_identity": request.external_identity.to_dict(),
            "registry": [item.to_dict() for item in request.mappings],
            "selected_mapping": selected.to_dict(),
            "ordered_session_dates": list(dates),
            "all_rows_covered": True,
        }
    ), dates


__all__ = [
    "PolygonCompletedDailyProductionQualificationApplicationService",
    "PolygonCompletedDailyQualificationRefusalReason",
    "PolygonCompletedDailyQualificationRefused",
    "PolygonCompletedDailyQualificationRequest",
    "PolygonCompletedDailyQualifiedUse",
]
