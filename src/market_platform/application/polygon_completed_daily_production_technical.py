"""Governed Daily Technical execution over an authentic retained bridge occurrence."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from datetime import datetime
from enum import StrEnum
from threading import Lock
from typing import NamedTuple
from uuid import uuid4

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import polygon_completed_daily_production_bridge as b
from market_platform.application import (
    polygon_completed_daily_production_governance as g,
)
from market_platform.evidence import EvidenceArtifactReference
from market_platform.research import technical_analysis as technical
from market_platform.research.daily_evidence import DailyResearchEvidence

_OPERATION = "production.polygon_completed_daily.daily_technical.application"
_VERSION = "1.0.0"
_EXECUTOR = (
    "market_platform.application.polygon_completed_daily_production_technical/v1"
)
_ANALYZER = (
    "market_platform.research.technical_analysis.analyze_daily_technical_snapshot"
)
_PROFILE_FINGERPRINT = (
    "sha256:341279ccfd6839287e5e5c9af46f9eb834577a07e9ffd1a16c0e27ccc35cfd49"
)
_AUTHORIZATION_FINGERPRINT = (
    "sha256:e9d8057dde8e20c5fb297ea08be7bcc723131cea42fab0e8a528f5b40c343387"
)
_ANALYSIS_FINGERPRINT = (
    "sha256:c2f1ccd7f9cfa51281c07cec7f62ac43940a72c6af1f8d162f9c8fbf97af78f7"
)
_TRANSFORMATION_FINGERPRINT = (
    "sha256:3f29cda80a15b92a37a3c2545a7baaaef9c756439d3e4642f4da1f489438076f"
)


class PolygonCompletedDailyTechnicalRefusalReason(StrEnum):
    BRIDGE_UNAVAILABLE = "bridge_unavailable"
    HISTORY_INVALID = "history_incomplete_or_corrupt"
    PROFILE_MISMATCH = "profile_mismatch"
    ANALYSIS_FAILED = "analysis_failed"
    CORRESPONDENCE_FAILED = "snapshot_correspondence_failed"
    TEMPORAL_FAILURE = "temporal_failure"
    PUBLICATION_FAILED = "technical_publication_failed"


class PolygonCompletedDailyTechnicalRefused(RuntimeError):
    def __init__(
        self, reason: PolygonCompletedDailyTechnicalRefusalReason, message: str
    ) -> None:
        self.reason = reason
        super().__init__(message)


def _identity(value: str, prefix: str) -> None:
    if type(value) is not str or re.fullmatch(prefix + r":[0-9a-f]{32}", value) is None:
        raise ValueError(f"exact {prefix} identity required")


def _sequence(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("positive exact history sequence required")


def _fixed_profile() -> technical.DailyTechnicalAnalysisProfile:
    profile = technical.construct_daily_technical_analysis_profile()
    approved = g._resolve_approved_polygon_completed_daily_production_profile(
        g._POLYGON_COMPLETED_DAILY_PRODUCTION_PROFILE
    )
    profile._validate()
    if (
        type(profile) is not technical.DailyTechnicalAnalysisProfile
        or profile.profile_id != "daily_technical_analysis_default"
        or profile.profile_version != _VERSION
        or profile.fingerprint != _ANALYSIS_FINGERPRINT
        or approved.fingerprint != _PROFILE_FINGERPRINT
        or approved.construction_authorization.fingerprint != _AUTHORIZATION_FINGERPRINT
        or approved.analysis_profile.definition_id != profile.profile_id
        or approved.analysis_profile.definition_version != profile.profile_version
        or approved.analysis_profile.get("profile_fingerprint") != profile.fingerprint
        or approved.transformation.definition_id
        != "production.polygon_completed_daily.transform.completed_daily_price_series"
        or approved.transformation.definition_version != _VERSION
        or approved.transformation.fingerprint != _TRANSFORMATION_FINGERPRINT
    ):
        raise ValueError("frozen production/analysis/transformation identity mismatch")
    return profile


@dataclass(frozen=True, slots=True)
class PolygonCompletedDailyTechnicalRequest:
    artifact_reference: EvidenceArtifactReference
    bridge_history_namespace_id: str
    bridge_history_sequence: int
    bridge_execution_id: str
    bridge_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            a._copy_artifact_reference(self.artifact_reference),
        )
        _identity(
            self.bridge_history_namespace_id, "polygon_completed_daily_bridge_history"
        )
        _sequence(self.bridge_history_sequence)
        _identity(self.bridge_execution_id, "polygon_completed_daily_bridge")
        g._fingerprint(self.bridge_fingerprint, "bridge fingerprint")

    def to_dict(self) -> dict[str, object]:
        replace(self)
        return {
            "artifact_reference": self.artifact_reference.to_dict(),
            "bridge_history_namespace_id": self.bridge_history_namespace_id,
            "bridge_history_sequence": self.bridge_history_sequence,
            "bridge_execution_id": self.bridge_execution_id,
            "bridge_fingerprint": self.bridge_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class _SourceLineage:
    """Detached values only; the service retains the resolvable upstream boundary."""

    bridge_reference: PolygonCompletedDailyTechnicalRequest
    construction_execution_id: str
    construction_receipt_fingerprint: str
    qualification_execution_id: str
    qualification_history_namespace_id: str
    qualification_history_sequence: int
    qualification_fingerprint: str
    source_material_fingerprint: str
    dataset_fingerprint: str
    no_drop_proof_fingerprint: str
    row_date_fingerprint: str
    evidence: DailyResearchEvidence
    qualification_knowledge_as_of: datetime
    bridge_available_at: datetime

    def to_dict(self) -> dict[str, object]:
        if type(self.bridge_reference) is not PolygonCompletedDailyTechnicalRequest:
            raise ValueError("exact bridge reference required")
        _identity(
            self.construction_execution_id, "polygon_completed_daily_construction"
        )
        _identity(
            self.qualification_execution_id, "polygon_completed_daily_qualification"
        )
        _identity(
            self.qualification_history_namespace_id,
            "polygon_completed_daily_qualification_history",
        )
        _sequence(self.qualification_history_sequence)
        result: dict[str, object] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name.endswith("fingerprint"):
                g._fingerprint(value, field.name)
            result[field.name] = value
        if type(self.evidence) is not DailyResearchEvidence:
            raise ValueError("exact retained research evidence required")
        for instant in (self.qualification_knowledge_as_of, self.bridge_available_at):
            a._require_canonical_timestamp(instant, "source availability")
        if self.qualification_knowledge_as_of > self.bridge_available_at:
            raise ValueError("source chronology invalid")
        result["bridge_reference"] = self.bridge_reference.to_dict()
        result["evidence"] = self.evidence.to_dict()
        result["qualification_knowledge_as_of"] = (
            self.qualification_knowledge_as_of.isoformat()
        )
        result["bridge_available_at"] = self.bridge_available_at.isoformat()
        return result


def _source_lineage(bridge: b.PolygonCompletedDailyBridgeResult) -> _SourceLineage:
    qualified = bridge.qualification
    construction = qualified.construction_result
    return deepcopy(
        _SourceLineage(
            PolygonCompletedDailyTechnicalRequest(
                construction.artifact.reference(),
                bridge.history_namespace_id,
                bridge.history_sequence,
                bridge.execution_id,
                bridge.fingerprint,
            ),
            construction.receipt.execution_id,
            construction.receipt.fingerprint,
            qualified.execution_id,
            qualified.history_namespace_id,
            qualified.history_sequence,
            qualified.fingerprint,
            construction.material.fingerprint,
            bridge.dataset_fingerprint,
            bridge.no_drop_proof_fingerprint,
            bridge.target_row_date_fingerprint,
            bridge.completed_prices.evidence,
            qualified.knowledge_as_of,
            bridge.available_at,
        )
    )


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyTechnicalResult:
    source: _SourceLineage
    snapshot: technical.TechnicalAnalysisSnapshot
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("technical results are published only by trusted execution")

    @property
    def analysis_as_of(self) -> datetime:
        return self.source.evidence.analysis_as_of

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": "polygon_completed_daily_technical_result/v1",
            "source": self.source.to_dict(),
            "production_profile_fingerprint": _PROFILE_FINGERPRINT,
            "transformation": {
                "id": (
                    "production.polygon_completed_daily.transform."
                    "completed_daily_price_series"
                ),
                "version": _VERSION,
                "fingerprint": _TRANSFORMATION_FINGERPRINT,
            },
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "snapshot": self.snapshot.to_dict(),
            "operation": _OPERATION,
            "operation_version": _VERSION,
            "executor": _EXECUTOR,
            "analyzer": _ANALYZER,
            "analyzer_rules_version": self.snapshot.profile.rules_version,
            "execution_id": self.execution_id,
            "history_namespace_id": self.history_namespace_id,
            "history_sequence": self.history_sequence,
            "execution_started_at": self.execution_started_at.isoformat(),
            "execution_completed_at": self.execution_completed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
        }

    def to_dict(self) -> dict[str, object]:
        if type(self.source) is not _SourceLineage:
            raise ValueError("exact source lineage required")
        _check_snapshot(self.snapshot, self.source.evidence, _fixed_profile())
        _identity(self.execution_id, "polygon_completed_daily_technical")
        _identity(
            self.history_namespace_id, "polygon_completed_daily_technical_history"
        )
        _sequence(self.history_sequence)
        for instant in (
            self.execution_started_at,
            self.execution_completed_at,
            self.available_at,
        ):
            a._require_canonical_timestamp(instant, "technical execution time")
        if not (
            self.source.bridge_available_at
            <= self.execution_started_at
            <= self.execution_completed_at
            <= self.available_at
        ):
            raise ValueError("technical occurrence chronology invalid")
        payload = self._payload()
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError("technical envelope fingerprint mismatch")
        return {**payload, "fingerprint": self.fingerprint}


def _check_snapshot(
    snapshot: technical.TechnicalAnalysisSnapshot,
    evidence: DailyResearchEvidence,
    profile: technical.DailyTechnicalAnalysisProfile,
) -> None:
    if type(snapshot) is not technical.TechnicalAnalysisSnapshot:
        raise ValueError("exact analyzer-owned snapshot required")
    snapshot._validate()
    if (
        snapshot.evidence.to_dict() != evidence.to_dict()
        or snapshot.profile.to_dict() != profile.to_dict()
        or snapshot.profile.fingerprint != _ANALYSIS_FINGERPRINT
    ):
        raise ValueError(
            "snapshot does not match authenticated bridge evidence/profile"
        )


def _public_result_copy(
    retained: PolygonCompletedDailyTechnicalResult,
) -> PolygonCompletedDailyTechnicalResult:
    expected = retained.to_dict()
    public = deepcopy(retained)
    if public.to_dict() != expected:
        raise ValueError("public copy changed technical result content")
    return public


def _issuance_bytes(projection: object) -> bytes:
    """Encode only the complete validated public scalar projection, privately."""

    def validate(value: object) -> None:
        if value is None or type(value) in (str, bool, int):
            return
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("nonfinite issuance scalar")
            return
        if type(value) is list:
            for item in value:
                validate(item)
            return
        if type(value) is dict:
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("exact string issuance key required")
                validate(item)
            return
        raise ValueError("exact built-in issuance projection required")

    validate(projection)
    return json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class _TechnicalCommitment(NamedTuple):
    # Strong references pin original occurrence lifetimes independently of the view.
    owner: _TechnicalHistory
    namespace: str
    state: tuple[int, tuple[PolygonCompletedDailyTechnicalResult, ...]]
    issuance: tuple[bytes, ...]


class _TechnicalHistory:
    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = f"polygon_completed_daily_technical_history:{uuid4().hex}"
        self._state: tuple[int, tuple[PolygonCompletedDailyTechnicalResult, ...]] = (
            1,
            (),
        )
        self._pending: PolygonCompletedDailyTechnicalResult | None = None
        self._issuance: tuple[bytes, ...] = ()

    def _stage_publication(self, result: PolygonCompletedDailyTechnicalResult) -> None:
        result.to_dict()
        self._pending = result

    def _validate(self) -> None:
        sequence, entries = self._state
        _sequence(sequence)
        if type(entries) is not tuple or sequence != len(entries) + 1:
            raise ValueError("technical history incomplete")
        ids: set[str] = set()
        previous: datetime | None = None
        for index, item in enumerate(entries, 1):
            if type(item) is not PolygonCompletedDailyTechnicalResult:
                raise ValueError("technical history type invalid")
            item.to_dict()
            if (
                item.history_sequence != index
                or item.history_namespace_id != self._namespace_id
                or item.execution_id in ids
                or (previous is not None and item.available_at < previous)
            ):
                raise ValueError("technical occurrence history corrupt")
            ids.add(item.execution_id)
            previous = item.available_at


class PolygonCompletedDailyProductionTechnicalApplicationService:
    def __init__(
        self,
        bridge_service: b.PolygonCompletedDailyProductionBridgeApplicationService,
        *,
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            type(bridge_service)
            is not b.PolygonCompletedDailyProductionBridgeApplicationService
        ):
            raise TypeError("exact trusted bridge service required")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._bridge_service = bridge_service
        self._clock = a._utc_now if execution_clock is None else execution_clock
        self._history = _TechnicalHistory()
        self.__committed = _TechnicalCommitment(
            self._history, self._history._namespace_id, self._history._state, ()
        )

    def _validate_authority(self) -> None:
        """Validate the whole publication root under the already held input locks."""
        root = self.__committed
        history = self._history
        if (
            history is not root.owner
            or type(history._namespace_id) is not str
            or history._namespace_id != root.namespace
            or history._state is not root.state
            or type(history._issuance) is not tuple
            or any(type(fact) is not bytes for fact in history._issuance)
            or history._issuance != root.issuance
            or len(root.issuance) != len(root.state[1])
        ):
            raise ValueError("technical publication commitment replaced or incomplete")
        _identity(root.namespace, "polygon_completed_daily_technical_history")
        history._validate()
        for item, fact in zip(root.state[1], root.issuance, strict=True):
            if type(fact) is not bytes or _issuance_bytes(item.to_dict()) != fact:
                raise ValueError("technical occurrence differs from original issuance")

    def _authenticate_occurrence(
        self,
        *,
        artifact_reference: EvidenceArtifactReference,
        technical_history_namespace_id: str,
        technical_history_sequence: int,
        technical_execution_id: str,
        technical_fingerprint: str,
    ) -> tuple[
        PolygonCompletedDailyTechnicalResult, b.PolygonCompletedDailyBridgeResult
    ]:
        """Resolve original issuance/provenance under the caller's input locks."""
        self._validate_authority()
        reference = a._copy_artifact_reference(artifact_reference).to_dict()
        _identity(
            technical_history_namespace_id, "polygon_completed_daily_technical_history"
        )
        _sequence(technical_history_sequence)
        _identity(technical_execution_id, "polygon_completed_daily_technical")
        g._fingerprint(technical_fingerprint, "technical fingerprint")
        matches = tuple(
            item
            for item in self.__committed.state[1]
            if item.source.bridge_reference.artifact_reference.to_dict() == reference
            and item.history_namespace_id == technical_history_namespace_id
            and item.history_sequence == technical_history_sequence
            and item.execution_id == technical_execution_id
            and item.fingerprint == technical_fingerprint
        )
        if len(matches) != 1:
            raise ValueError("exact issued technical occurrence unavailable")
        item = matches[0]
        bridge = self._resolve(item.source.bridge_reference, item.execution_started_at)
        if _source_lineage(bridge) != item.source:
            raise ValueError("retained technical lineage differs from original bridge")
        self._validate_authority()
        return item, bridge

    def _lock_inputs(self, stack: ExitStack) -> None:
        source = self._bridge_service
        source._qualification_service._lock_inputs(stack)
        stack.enter_context(source._qualification_service._history._lock)
        stack.enter_context(source._history._lock)
        stack.enter_context(self.__committed.owner._lock)

    def _resolve(
        self, request: PolygonCompletedDailyTechnicalRequest, started: datetime
    ) -> b.PolygonCompletedDailyBridgeResult:
        source = self._bridge_service
        source._history._validate()
        matches = tuple(
            item
            for item in source._history._state[1]
            if item.execution_id == request.bridge_execution_id
            and item.fingerprint == request.bridge_fingerprint
            and item.history_namespace_id == request.bridge_history_namespace_id
            and item.history_sequence == request.bridge_history_sequence
            and item.available_at <= started
            and item.qualification.construction_result.artifact.reference()
            == request.artifact_reference
        )
        if len(matches) != 1:
            raise PolygonCompletedDailyTechnicalRefused(
                PolygonCompletedDailyTechnicalRefusalReason.BRIDGE_UNAVAILABLE,
                "exact bridge occurrence unavailable in trusted history",
            )
        bridge = matches[0]
        bridge.to_dict()
        qualified = bridge.qualification
        # Resolve the bridge's original prerequisites at its original execution time.
        # This released resolver reads history; it performs no qualification/conversion.
        resolved = source._resolve(
            b.PolygonCompletedDailyBridgeRequest(
                request.artifact_reference,
                qualified.construction_result.receipt.execution_id,
                qualified.execution_id,
                qualified.fingerprint,
            ),
            bridge.execution_started_at,
        )
        if resolved is not qualified:
            raise ValueError(
                "bridge qualification is not the authentic retained occurrence"
            )
        return bridge

    def execute(
        self, request: PolygonCompletedDailyTechnicalRequest
    ) -> PolygonCompletedDailyTechnicalResult:
        if type(request) is not PolygonCompletedDailyTechnicalRequest:
            raise TypeError(
                "only exact technical intent/reference requests are accepted"
            )
        request = replace(request)
        reason = PolygonCompletedDailyTechnicalRefusalReason.TEMPORAL_FAILURE
        try:
            started = a._timestamp(self._clock())
            with ExitStack() as stack:
                self._lock_inputs(stack)
                reason = PolygonCompletedDailyTechnicalRefusalReason.HISTORY_INVALID
                self._validate_authority()
                reason = PolygonCompletedDailyTechnicalRefusalReason.PROFILE_MISMATCH
                profile = _fixed_profile()
                reason = PolygonCompletedDailyTechnicalRefusalReason.HISTORY_INVALID
                bridge = self._resolve(request, started)
                lineage = _source_lineage(bridge)
                reason = PolygonCompletedDailyTechnicalRefusalReason.ANALYSIS_FAILED
                snapshot = technical.analyze_daily_technical_snapshot(
                    completed_prices=bridge.completed_prices, profile=profile
                )
                reason = (
                    PolygonCompletedDailyTechnicalRefusalReason.CORRESPONDENCE_FAILED
                )
                _check_snapshot(snapshot, lineage.evidence, profile)
                bridge.to_dict()
                if _source_lineage(bridge) != lineage:
                    raise ValueError("authenticated bridge changed during analysis")
                reason = PolygonCompletedDailyTechnicalRefusalReason.TEMPORAL_FAILURE
                completed = a._timestamp(self._clock())
                if completed < started:
                    raise ValueError("technical completion clock moved backward")
                reason = PolygonCompletedDailyTechnicalRefusalReason.PUBLICATION_FAILED
                return self._publish(lineage, snapshot, started, completed)
        except PolygonCompletedDailyTechnicalRefused:
            raise
        except Exception as error:
            raise PolygonCompletedDailyTechnicalRefused(reason, str(error)) from error

    def _publish(
        self,
        lineage: _SourceLineage,
        snapshot: technical.TechnicalAnalysisSnapshot,
        started: datetime,
        completed: datetime,
    ) -> PolygonCompletedDailyTechnicalResult:
        root = self.__committed
        self._validate_authority()
        sequence, entries = root.state
        staged = object.__new__(PolygonCompletedDailyTechnicalResult)
        values: dict[str, object] = {
            "source": deepcopy(lineage),
            "snapshot": deepcopy(snapshot),
            "execution_id": f"polygon_completed_daily_technical:{uuid4().hex}",
            "history_namespace_id": self._history._namespace_id,
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
        try:
            self._history._stage_publication(staged)
            available = a._timestamp(self._clock())
            if available < completed or (
                entries and available < entries[-1].available_at
            ):
                raise PolygonCompletedDailyTechnicalRefused(
                    PolygonCompletedDailyTechnicalRefusalReason.TEMPORAL_FAILURE,
                    "technical publication clock moved backward",
                )
            published = deepcopy(staged)
            object.__setattr__(published, "available_at", available)
            object.__setattr__(
                published, "fingerprint", canonical_fingerprint(published._payload())
            )
            published.to_dict()
            if (
                published.source != lineage
                or published.snapshot != snapshot
                or published.execution_id != values["execution_id"]
                or published.history_namespace_id != self._history._namespace_id
                or published.history_sequence != sequence
                or published.execution_started_at != started
                or published.execution_completed_at != completed
                or any(item.execution_id == published.execution_id for item in entries)
            ):
                raise ValueError("staging changed authenticated analysis content")
            final_projection = published.to_dict()
            public = _public_result_copy(published)
            issuance = _issuance_bytes(final_projection)
            next_state = sequence + 1, (*entries, published)
            next_issuance = (*root.issuance, issuance)
            next_root = _TechnicalCommitment(
                root.owner, root.namespace, next_state, next_issuance
            )
            # Recheck retained provenance after every fallible publication seam.
            bridge = self._resolve(lineage.bridge_reference, started)
            if _source_lineage(bridge) != lineage:
                raise ValueError("source lineage changed during publication")
            self._validate_authority()
            if self.__committed is not root:
                raise ValueError("technical history changed during publication")
            if (
                self._history._pending is not staged
                or type(published) is not PolygonCompletedDailyTechnicalResult
                or type(public) is not PolygonCompletedDailyTechnicalResult
                or public is published
                or public is staged
                or published is staged
                or _issuance_bytes(published.to_dict()) != issuance
                or _issuance_bytes(public.to_dict()) != issuance
            ):
                raise ValueError("final technical publication correspondence changed")
            # Everything fallible is complete. Readers hold this same technical lock.
            self.__committed = next_root
            root.owner._state = next_state
            root.owner._issuance = next_issuance
            return public
        finally:
            root.owner._pending = None

    def get_result_history_as_of(
        self,
        artifact_reference: EvidenceArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyTechnicalResult, ...]:
        reference = a._copy_artifact_reference(artifact_reference)
        cutoff = a._timestamp(knowledge_as_of)
        try:
            with ExitStack() as stack:
                self._lock_inputs(stack)
                self._validate_authority()
                results = []
                for item in self._history._state[1]:
                    if (
                        item.source.bridge_reference.artifact_reference == reference
                        and item.available_at <= cutoff
                    ):
                        bridge = self._resolve(
                            item.source.bridge_reference, item.execution_started_at
                        )
                        if _source_lineage(bridge) != item.source:
                            raise ValueError(
                                "retained result source correspondence changed"
                            )
                        results.append(_public_result_copy(item))
                public = tuple(results)
                self._validate_authority()
                return public
        except Exception as error:
            raise PolygonCompletedDailyTechnicalRefused(
                PolygonCompletedDailyTechnicalRefusalReason.HISTORY_INVALID, str(error)
            ) from error


__all__ = [
    "PolygonCompletedDailyTechnicalRefusalReason",
    "PolygonCompletedDailyTechnicalRefused",
    "PolygonCompletedDailyTechnicalRequest",
    "PolygonCompletedDailyTechnicalResult",
    "PolygonCompletedDailyProductionTechnicalApplicationService",
]
