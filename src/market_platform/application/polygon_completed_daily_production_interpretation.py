"""Trusted retained Polygon technical occurrence to governed Interpretation."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.evidence import EvidenceArtifactReference, EvidenceSubjectReference
from market_platform.instruments.identity import (
    CanonicalInstrument,
    CanonicalInstrumentId,
)
from market_platform.research import governed_daily_technical_interpretation as domain
from market_platform.research.governed_daily_technical_interpretation import (
    GovernedDailyTechnicalInterpretation,
    PolygonCompletedDailyInterpretationRequest,
)
from market_platform.research.technical_policy import (
    ClassicDailyTechnicalInterpretationConfiguration,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

_OPERATION = (
    "production.polygon_completed_daily.daily_technical_interpretation.application"
)
_VERSION = "1.0.0"
_EXECUTOR = (
    "market_platform.application.polygon_completed_daily_production_interpretation/v1"
)
_PREFIX = "polygon_completed_daily_interpretation"


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
        self._history = _InterpretationHistory()
        self._history_owner = self._history
        self._namespace = self._history._namespace_id
        # The service pins its current commitment independently of the history view.
        self._committed = self._history._state
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
        stack.enter_context(self._history._lock)

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
        self._history._validate()
        if (
            self._history is not self._history_owner
            or self._history._namespace_id != self._namespace
            or self._history._state is not self._committed
        ):
            raise ValueError("Interpretation history replaced or truncated")
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
        state = self._history._state
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
            self._history._stage_publication(staged)
            if self._history._pending is not staged or staged.to_dict() != expected:
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
            if self._history._state is not state:
                raise ValueError("history changed during publication")
            _check_copy(public, published, expected)
            self._committed = next_state
            self._history._state = next_state
            return public
        finally:
            self._history._pending = None

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
                for fact in self._history._state[1]:
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
