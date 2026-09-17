"""Governed Assessment preparation and atomic canonical publication."""

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
    polygon_completed_daily_production_interpretation as i,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import governed_daily_technical_assessment as domain
from market_platform.research.governed_daily_technical_assessment import (
    GovernedDailyTechnicalAssessment,
)
from market_platform.research.governed_daily_technical_interpretation import (
    GovernedTechnicalArtifactReference,
    _choice,
    _fingerprint,
)
from market_platform.research.governed_daily_technical_strategy import (
    PolygonCompletedDailyStrategyRequest as _StrategyRequest,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

_SCHEMA = "polygon_completed_daily_assessment_result/v1"
_OPERATION = "production.polygon_completed_daily.daily_technical_assessment.application"
_VERSION = "1.0.0"
_EXECUTOR = (
    "market_platform.application/polygon_completed_daily_production_assessment/v1"
)
_PREFIX = "polygon_completed_daily_assessment"


class _AssessmentOccurrenceUnavailable(ValueError):
    """Valid complete history contains no exact requested occurrence."""


class _AssessmentHistoryInvalid(ValueError):
    """Pinned authority, committed inventory or required support is invalid."""


class _AssessmentSourceMismatch(ValueError):
    """Authenticated retained source correspondence differs."""


class PolygonCompletedDailyAssessmentRefusalReason:
    INTERPRETATION_UNAVAILABLE = "interpretation_occurrence_unavailable"
    HISTORY_INVALID = "history_incomplete_or_corrupt"
    SOURCE_MISMATCH = "source_lineage_mismatch"
    SEMANTIC_FAILED = "semantic_execution_or_correspondence_failed"
    TEMPORAL_FAILURE = "temporal_failure"
    PUBLICATION_FAILED = "assessment_publication_or_copy_failed"


class PolygonCompletedDailyAssessmentRefused(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        if type(message) is not str:
            raise TypeError("exact refusal message string required")
        _choice(
            reason,
            (
                "interpretation_occurrence_unavailable",
                "history_incomplete_or_corrupt",
                "source_lineage_mismatch",
                "semantic_execution_or_correspondence_failed",
                "temporal_failure",
                "assessment_publication_or_copy_failed",
            ),
        )
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyAssessmentResult:
    assessment: GovernedDailyTechnicalAssessment
    interpretation_available_at: datetime
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("Assessment results require trusted execution")

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "assessment": self.assessment.to_dict(),
            "interpretation_available_at": self.interpretation_available_at.isoformat(),
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
        if type(self.assessment) is not GovernedDailyTechnicalAssessment:
            raise ValueError("exact governed Assessment content required")
        self.assessment._validate()
        t._identity(self.execution_id, _PREFIX)
        t._identity(self.history_namespace_id, _PREFIX + "_history")
        t._sequence(self.history_sequence)
        for instant in (
            self.interpretation_available_at,
            self.execution_started_at,
            self.execution_completed_at,
            self.available_at,
        ):
            a._require_canonical_timestamp(instant, "Assessment occurrence time")
        if not (
            self.interpretation_available_at
            <= self.execution_started_at
            <= self.execution_completed_at
            <= self.available_at
        ):
            raise ValueError("Assessment occurrence chronology invalid")
        payload = self._payload()
        _fingerprint(self.fingerprint)
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError("Assessment envelope fingerprint mismatch")
        return deepcopy({**payload, "fingerprint": self.fingerprint})


def _public_result_copy(
    retained: PolygonCompletedDailyAssessmentResult,
) -> PolygonCompletedDailyAssessmentResult:
    expected = retained.to_dict()
    public = _reconstruct_result(_encode_result(retained))
    _check_copy(public, retained, expected)
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


def _encode_result(result: PolygonCompletedDailyAssessmentResult) -> bytes:
    if type(result) is not PolygonCompletedDailyAssessmentResult:
        raise TypeError("exact Assessment result required")
    return _canonical_bytes(result.to_dict())


def _decode_result(fact: bytes) -> dict[str, Any]:
    if type(fact) is not bytes:
        raise TypeError("exact immutable Assessment bytes required")
    value = json.loads(fact)
    if type(value) is not dict or _canonical_bytes(value) != fact:
        raise ValueError("noncanonical Assessment encoding")
    return value


def _reconstruct_result(fact: bytes) -> PolygonCompletedDailyAssessmentResult:
    """Rebuild caller-owned values and check the entire original scalar encoding."""
    projection = _decode_result(fact)
    content = projection["assessment"]
    occurrence = content["source_interpretation_occurrence"]
    artifact = occurrence["artifact_reference"]
    artifact_value = GovernedTechnicalArtifactReference(
        **{
            key: value
            for key, value in artifact.items()
            if key not in ("schema_version", "fingerprint")
        }
    )
    request = domain.PolygonCompletedDailyAssessmentRequest(
        **{**occurrence, "artifact_reference": artifact_value}
    )
    policy = content["assessment_policy_identity"]
    policy_value = domain.GovernedDailyTechnicalAssessmentPolicyIdentity(
        **{
            key: value
            for key, value in policy.items()
            if key not in ("schema_version", "fingerprint")
        }
    )
    findings = tuple(
        domain.GovernedDailyTechnicalAssessmentFinding(
            **{
                **item,
                "comparison_evidence_ids": tuple(item["comparison_evidence_ids"]),
            }
        )
        for item in content["findings"]
    )
    assessment = GovernedDailyTechnicalAssessment(
        **{
            **{
                key: value
                for key, value in content.items()
                if key not in ("schema_version", "fingerprint")
            },
            "source_interpretation_occurrence": request,
            "canonical_instrument_id": CanonicalInstrumentId(
                **content["canonical_instrument_id"]
            ),
            "source_trading_identity": TradingInstrumentIdentity(
                content["source_trading_identity"]["symbol"],
                content["source_trading_identity"]["venue"],
            ),
            "analysis_as_of": datetime.fromisoformat(content["analysis_as_of"]),
            "assessment_policy_identity": policy_value,
            "source_warnings": tuple(content["source_warnings"]),
            "findings": findings,
        }
    )
    result = object.__new__(PolygonCompletedDailyAssessmentResult)
    for item in fields(result):
        value = projection[item.name] if item.name != "assessment" else assessment
        if item.name.endswith("_at"):
            value = datetime.fromisoformat(projection[item.name])
        object.__setattr__(result, item.name, value)
    # Binds every key, numeric type, timestamp, nested identity and both hashes.
    if _encode_result(result) != fact:
        raise ValueError("Assessment scalar reconstruction mismatch")
    return result


def _graph_ids(value: object) -> set[int]:
    """Frozen dataclass instances remain mutable through object.__setattr__."""
    if is_dataclass(value) and not isinstance(value, type):
        result = {id(value)}
        for field in fields(value):
            result.update(_graph_ids(getattr(value, field.name)))
        return result
    if type(value) is dict:
        return {id(value)} | set().union(*(_graph_ids(item) for item in value.values()))
    if type(value) is list:
        return {id(value)} | set().union(*(_graph_ids(item) for item in value))
    if type(value) is tuple:
        return set().union(*(_graph_ids(item) for item in value))
    return set()


def _check_copy(
    public: PolygonCompletedDailyAssessmentResult,
    retained: PolygonCompletedDailyAssessmentResult,
    expected: dict[str, object],
) -> None:
    if (
        type(public) is not PolygonCompletedDailyAssessmentResult
        or public.to_dict() != expected
        or retained.to_dict() != expected
        or _graph_ids(public) & _graph_ids(retained)
    ):
        raise ValueError("public result changed content or aliases retained state")


class _AssessmentHistory:
    """Canonical committed facts; transient pending staging grants no authority."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = f"{_PREFIX}_history:{uuid4().hex}"
        self._state: tuple[int, tuple[bytes, ...]] = (
            1,
            (),
        )
        self._pending: PolygonCompletedDailyAssessmentResult | None = None

    def _stage_publication(self, result: PolygonCompletedDailyAssessmentResult) -> None:
        if type(result) is not PolygonCompletedDailyAssessmentResult:
            raise TypeError("exact Assessment result required")
        result.to_dict()
        self._pending = result

    def _validate(self) -> None:
        if type(self._state) is not tuple or len(self._state) != 2:
            raise ValueError("exact history state tuple required")
        sequence, entries = self._state
        t._sequence(sequence)
        t._identity(self._namespace_id, _PREFIX + "_history")
        if type(entries) is not tuple or sequence != len(entries) + 1:
            raise ValueError("Assessment history incomplete")
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
                raise ValueError("Assessment history corrupt")
            ids.add(item.execution_id)
            previous = item.available_at


@dataclass(frozen=True, slots=True)
class _PreparedAssessment:
    """Detached prospective facts, without Assessment occurrence authority."""

    request: domain.PolygonCompletedDailyAssessmentRequest
    source_projection: dict[str, object]
    assessment: GovernedDailyTechnicalAssessment
    interpretation_available_at: datetime
    started: datetime


@dataclass(frozen=True, slots=True)
class _AssessmentPair:
    """Detached values and immutable facts, never publication authority."""

    assessment: PolygonCompletedDailyAssessmentResult
    interpretation: i.PolygonCompletedDailyInterpretationResult
    assessment_fact: bytes
    interpretation_fact: bytes


def _check_assessment_pair(
    item: PolygonCompletedDailyAssessmentResult,
    source: i.PolygonCompletedDailyInterpretationResult,
) -> None:
    # These codecs validate retained structure, policies and comparison relational
    # self-consistency. They do not derive findings, outcomes or Interpretation states.
    item.to_dict()
    source.to_dict()
    content = item.assessment
    interpretation = source.interpretation
    request = content.source_interpretation_occurrence
    if (
        request.to_dict()
        != {
            "artifact_reference": (
                source.source_technical_occurrence.artifact_reference.to_dict()
            ),
            "interpretation_history_namespace_id": source.history_namespace_id,
            "interpretation_history_sequence": source.history_sequence,
            "interpretation_execution_id": source.execution_id,
            "interpretation_fingerprint": source.fingerprint,
        }
        or content.source_interpretation_content_fingerprint
        != interpretation.fingerprint
        or content.canonical_instrument_id.to_dict()
        != interpretation.canonical_instrument_id.to_dict()
        or content.source_trading_identity.to_dict()
        != interpretation.source_trading_identity.to_dict()
        or content.analysis_as_of != interpretation.analysis_as_of
        or content.source_quality != interpretation.source_quality
        or content.source_warnings != interpretation.source_warnings
        or item.interpretation_available_at != source.available_at
        or source.available_at > item.execution_started_at
    ):
        raise _AssessmentSourceMismatch(
            "retained Assessment source correspondence differs"
        )
    comparison_ids = {value.evidence_id for value in interpretation.comparison_evidence}
    if any(
        reference not in comparison_ids
        for finding in content.findings
        for reference in finding.comparison_evidence_ids
    ):
        raise _AssessmentSourceMismatch(
            "retained finding comparison reference unavailable"
        )


class PolygonCompletedDailyProductionAssessmentApplicationService:
    def __init__(
        self,
        interpretation_service: (
            i.PolygonCompletedDailyProductionInterpretationApplicationService
        ),
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(interpretation_service) is not (
            i.PolygonCompletedDailyProductionInterpretationApplicationService
        ):
            raise TypeError("exact trusted Interpretation service required")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._clock = a._utc_now if execution_clock is None else execution_clock
        self.__interpretation_service = interpretation_service
        self.__history_owner = _AssessmentHistory()
        self.__namespace = self._history_owner._namespace_id
        self._committed = self._history_owner._state
        self.__consumption_roots = (
            self.__history_owner,
            self.__namespace,
            interpretation_service,
            vars(interpretation_service).get("_history_owner"),
            vars(interpretation_service).get("_namespace"),
        )
        self.__consumption_locks: tuple[object, ...] | None = None

    @property
    def _interpretation_service(
        self,
    ) -> i.PolygonCompletedDailyProductionInterpretationApplicationService:
        """Read-only access to the constructor-pinned Interpretation publisher."""
        return self.__interpretation_service

    @property
    def _history_owner(self) -> _AssessmentHistory:
        """The original owner also supplies the final lock; no replaceable view."""
        return self.__history_owner

    @property
    def _namespace(self) -> str:
        return self.__namespace

    def _lock_inputs(
        self, stack: ExitStack
    ) -> i.PolygonCompletedDailyProductionInterpretationApplicationService:
        publisher = self.__interpretation_service
        owner = self.__history_owner
        consumption_locks = (
            publisher,
            owner,
            vars(publisher).get("_history_owner"),
        )
        publisher._lock_inputs(stack)
        stack.enter_context(owner._lock)
        self.__consumption_locks = consumption_locks
        return publisher

    def _check_consumption_roots(
        self,
        state: tuple[int, tuple[bytes, ...]],
        interpretation_state: tuple[int, tuple[bytes, ...]],
    ) -> None:
        owner, namespace, publisher, source_owner, source_namespace = (
            self.__consumption_roots
        )
        locks = self.__consumption_locks
        if (
            self.__history_owner is not owner
            or self.__namespace is not namespace
            or owner._namespace_id is not namespace
            or self.__interpretation_service is not publisher
            or self._committed is not state
            or owner._state is not state
            or owner._pending is not None
            or type(source_owner) is not i._InterpretationHistory
            or not owner._lock.locked()
            or not source_owner._lock.locked()
            or publisher._history_owner is not source_owner
            or publisher._history is not source_owner
            or publisher._namespace is not source_namespace
            or source_owner._namespace_id is not source_namespace
            or publisher._committed is not interpretation_state
            or source_owner._state is not interpretation_state
            or source_owner._pending is not None
            or locks is None
            or locks[0] is not publisher
            or locks[1] is not owner
            or locks[2] is not source_owner
        ):
            raise _AssessmentHistoryInvalid(
                "original Assessment consumption roots changed"
            )

    def _authenticate_consumption_source(
        self,
        request: domain.PolygonCompletedDailyAssessmentRequest,
    ) -> i.PolygonCompletedDailyInterpretationResult:
        publisher = self.__consumption_roots[2]
        try:
            return publisher._authenticate_interpretation_occurrence(
                artifact_reference=request.artifact_reference,
                interpretation_history_namespace_id=request.interpretation_history_namespace_id,
                interpretation_history_sequence=request.interpretation_history_sequence,
                interpretation_execution_id=request.interpretation_execution_id,
                interpretation_fingerprint=request.interpretation_fingerprint,
            )
        except (
            i._InterpretationOccurrenceUnavailable,
            i._InterpretationHistoryInvalid,
        ) as error:
            raise _AssessmentHistoryInvalid(str(error)) from error
        except i._InterpretationSourceMismatch as error:
            raise _AssessmentSourceMismatch(str(error)) from error

    def _consume_assessments(
        self,
        request: _StrategyRequest | None,
        expected: tuple[_AssessmentPair, ...] | None,
    ) -> tuple[_AssessmentPair, ...]:
        """One resolution/recheck contract under the already held ten-lock chain.

        All local preparation precedes final authentication of EVERY bound pair
        in inventory order. Each released Interpretation call also authenticates
        its complete inventory/support, including sources checked earlier in
        this operation. State identities bind the inventory throughout.
        """
        try:
            owner, namespace, publisher, source_owner, source_namespace = (
                self.__consumption_roots
            )
            roots = self.__consumption_roots
            locks = self.__consumption_locks
            state, source_state = self._committed, publisher._committed
            self._check_consumption_roots(state, source_state)
            request_before = request.to_dict() if request is not None else None
            # Authenticate every committed Assessment before resolving any source.
            owner._validate()
            items = tuple(_reconstruct_result(fact) for fact in state[1])
            self._check_consumption_roots(state, source_state)
            pairs = []
            for item, fact in zip(items, state[1], strict=True):
                source = self._authenticate_consumption_source(
                    item.assessment.source_interpretation_occurrence
                )
                self._check_consumption_roots(state, source_state)
                source_fact = i._encode_result(source)
                # Membership comes from the publisher, not the returned object.
                if source_fact not in source_state[1]:
                    raise _AssessmentSourceMismatch(
                        "authenticated source fact differs from commitment"
                    )
                pairs.append(_AssessmentPair(item, source, fact, source_fact))
            prepared = tuple(pairs)
            for pair in prepared:
                _check_assessment_pair(pair.assessment, pair.interpretation)
            if expected is not None:
                if type(expected) is not tuple or len(expected) != len(prepared):
                    raise _AssessmentHistoryInvalid(
                        "expected complete Assessment inventory differs"
                    )
                for before, current in zip(expected, prepared, strict=True):
                    if (
                        type(before) is not _AssessmentPair
                        or type(before.assessment_fact) is not bytes
                        or type(before.interpretation_fact) is not bytes
                        or before.assessment_fact != current.assessment_fact
                        or before.interpretation_fact != current.interpretation_fact
                        or _encode_result(before.assessment) != before.assessment_fact
                        or i._encode_result(before.interpretation)
                        != before.interpretation_fact
                    ):
                        raise _AssessmentSourceMismatch(
                            "expected Assessment pair or facts changed"
                        )
            # Selection follows COMPLETE inventory and pair authentication.
            selected = prepared
            if request is not None:
                selected = tuple(
                    pair
                    for pair in prepared
                    if (
                        pair.assessment.assessment.source_interpretation_occurrence.artifact_reference.to_dict()
                    )
                    == request.artifact_reference.to_dict()
                    and pair.assessment.history_namespace_id
                    == request.assessment_history_namespace_id
                    and pair.assessment.history_sequence
                    == request.assessment_history_sequence
                    and pair.assessment.execution_id == request.assessment_execution_id
                    and pair.assessment.fingerprint == request.assessment_fingerprint
                )
            graphs: set[int] = set()
            for pair in prepared:
                if (
                    _encode_result(pair.assessment) != pair.assessment_fact
                    or i._encode_result(pair.interpretation) != pair.interpretation_fact
                ):
                    raise _AssessmentSourceMismatch("prepared pair changed")
                for value in (pair.assessment, pair.interpretation):
                    graph = _graph_ids(value)
                    if graphs & graph:
                        raise _AssessmentHistoryInvalid(
                            "consumption result graphs alias"
                        )
                    graphs.update(graph)
            if request is not None and request.to_dict() != request_before:
                raise _AssessmentSourceMismatch("Assessment selectors changed")
            owner._validate()
            self._check_consumption_roots(state, source_state)
            # Prepare every request and exact scalar expectation before sealing.
            seal_expectations = tuple(
                (
                    deepcopy(
                        pair.assessment.assessment.source_interpretation_occurrence
                    ),
                    pair.interpretation.history_namespace_id,
                    pair.interpretation.history_sequence,
                    pair.interpretation.execution_id,
                    pair.interpretation.fingerprint,
                )
                for pair in prepared
            )
            missing = request is not None and len(selected) != 1
            self._check_consumption_roots(state, source_state)
            for (
                seal_request,
                seal_namespace,
                seal_sequence,
                seal_execution,
                seal_fingerprint,
            ) in seal_expectations:
                sealed = self._authenticate_consumption_source(seal_request)
                if (
                    type(sealed) is not i.PolygonCompletedDailyInterpretationResult
                    or type(sealed.history_namespace_id) is not str
                    or type(sealed.history_sequence) is not int
                    or type(sealed.execution_id) is not str
                    or type(sealed.fingerprint) is not str
                    or sealed.history_namespace_id != seal_namespace
                    or sealed.history_sequence != seal_sequence
                    or sealed.execution_id != seal_execution
                    or sealed.fingerprint != seal_fingerprint
                ):
                    raise _AssessmentSourceMismatch(
                        "sealed Interpretation occurrence changed"
                    )
            # Direct identity checks only after the complete upstream support seal.
            if (
                self.__consumption_roots is not roots
                or self.__consumption_locks is not locks
                or self.__history_owner is not owner
                or self.__namespace is not namespace
                or owner._namespace_id is not namespace
                or self.__interpretation_service is not publisher
                or self._committed is not state
                or owner._state is not state
                or owner._pending is not None
                or publisher._history_owner is not source_owner
                or publisher._history is not source_owner
                or publisher._namespace is not source_namespace
                or source_owner._namespace_id is not source_namespace
                or publisher._committed is not source_state
                or source_owner._state is not source_state
                or source_owner._pending is not None
            ):
                raise _AssessmentHistoryInvalid(
                    "consumption authority changed during support seal"
                )
            if missing:
                raise _AssessmentOccurrenceUnavailable(
                    "exact committed Assessment occurrence unavailable"
                )
            return selected
        except (
            _AssessmentOccurrenceUnavailable,
            _AssessmentHistoryInvalid,
            _AssessmentSourceMismatch,
        ):
            raise
        except Exception as error:
            raise _AssessmentHistoryInvalid(str(error)) from error

    def _authenticate_assessment_occurrence(
        self,
        request: _StrategyRequest,
    ) -> _AssessmentPair:
        """Resolve only Assessment selectors; the bound Interpretation is internal."""
        if type(request) is not _StrategyRequest:
            raise TypeError("exact Strategy selector request required")
        detached = deepcopy(request)
        detached.to_dict()
        return self._consume_assessments(detached, None)[0]

    def _authenticate_assessment_inventory(self) -> tuple[_AssessmentPair, ...]:
        """Capture all detached pairs for a subsequent complete revalidation."""
        return self._consume_assessments(None, None)

    def _revalidate_assessment_inventory(
        self, expected: tuple[_AssessmentPair, ...]
    ) -> None:
        """Reauthenticate every fact/support; expected values grant no authority."""
        if type(expected) is not tuple:
            raise TypeError("exact complete Assessment pair tuple required")
        self._consume_assessments(None, expected)

    def _check_history(self) -> None:
        """Check structural authority under held locks, without adopting state."""
        owner = self._history_owner
        if (
            type(owner) is not _AssessmentHistory
            or type(owner._namespace_id) is not str
            or owner._namespace_id != self._namespace
            or owner._state is not self._committed
        ):
            raise ValueError("Assessment publication commitment replaced or incomplete")
        owner._validate()

    def execute(
        self, request: domain.PolygonCompletedDailyAssessmentRequest
    ) -> PolygonCompletedDailyAssessmentResult:
        if type(request) is not domain.PolygonCompletedDailyAssessmentRequest:
            raise TypeError("only exact Assessment selector requests are accepted")
        request = replace(request)
        owner, namespace = self._history_owner, self._namespace
        original_publisher = self.__interpretation_service
        reasons = PolygonCompletedDailyAssessmentRefusalReason
        reason = reasons.TEMPORAL_FAILURE
        try:
            request_before = request.to_dict()
            started = a._timestamp(self._clock())
            reason = reasons.HISTORY_INVALID
            with ExitStack() as stack:
                publisher = self._lock_inputs(stack)
                # Capture the current commitment after serialization, so another
                # successful concurrent execution can legitimately precede this one.
                state = self._committed
                staged = None
                try:
                    if publisher is not original_publisher:
                        raise ValueError("acquired Interpretation publisher changed")
                    self._check_authority(owner, namespace, state, publisher, None)
                    prepared = self._prepare_assessment_locked(
                        request, started, publisher
                    )
                    reason = reasons.PUBLICATION_FAILED
                    content_before = deepcopy(prepared.assessment.to_dict())
                    source_before = deepcopy(prepared.source_projection)
                    source_available = prepared.interpretation_available_at

                    def check_prepared() -> None:
                        try:
                            if (
                                request.to_dict() != request_before
                                or prepared.request.to_dict() != request_before
                                or prepared.source_projection != source_before
                                or prepared.interpretation_available_at
                                != source_available
                                or prepared.started != started
                            ):
                                raise ValueError("prepared source/request changed")
                        except Exception as error:
                            raise PolygonCompletedDailyAssessmentRefused(
                                reasons.SOURCE_MISMATCH, str(error)
                            ) from error
                        try:
                            if prepared.assessment.to_dict() != content_before:
                                raise ValueError("prepared Assessment content changed")
                        except Exception as error:
                            raise PolygonCompletedDailyAssessmentRefused(
                                reasons.SEMANTIC_FAILED, str(error)
                            ) from error

                    def reauthenticate() -> None:
                        self._check_authority(
                            owner, namespace, state, publisher, staged
                        )
                        check_prepared()
                        source = self._authenticate_source(request, publisher)
                        self._check_authority(
                            owner, namespace, state, publisher, staged
                        )
                        if (
                            type(source)
                            is not i.PolygonCompletedDailyInterpretationResult
                            or source.to_dict() != source_before
                        ):
                            raise PolygonCompletedDailyAssessmentRefused(
                                reasons.SOURCE_MISMATCH,
                                "source changed during Assessment publication",
                            )
                        check_prepared()

                    reason = reasons.TEMPORAL_FAILURE
                    completed = a._timestamp(self._clock())
                    if completed < started:
                        raise ValueError("Assessment completion clock moved backward")
                    reason = reasons.HISTORY_INVALID
                    self._check_authority(owner, namespace, state, publisher, None)
                    self._check_history()
                    reason = reasons.SOURCE_MISMATCH
                    reauthenticate()

                    reason = reasons.PUBLICATION_FAILED
                    sequence, entries = state
                    prior = tuple(_reconstruct_result(fact) for fact in entries)
                    previous = prior[-1].available_at if prior else None
                    execution_ids = {item.execution_id for item in prior}
                    staged = object.__new__(PolygonCompletedDailyAssessmentResult)
                    values: dict[str, object] = {
                        "assessment": replace(prepared.assessment),
                        "interpretation_available_at": source_available,
                        "execution_id": f"{_PREFIX}:{uuid4().hex}",
                        "history_namespace_id": namespace,
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
                    staged_before = staged.to_dict()
                    if (
                        staged.assessment.to_dict() != content_before
                        or staged.execution_id in execution_ids
                    ):
                        raise ValueError("staging changed content or duplicated ID")
                    owner._stage_publication(staged)
                    self._check_authority(owner, namespace, state, publisher, staged)
                    if staged.to_dict() != staged_before:
                        raise ValueError("staging changed Assessment occurrence")

                    reason = reasons.TEMPORAL_FAILURE
                    available = a._timestamp(self._clock())
                    if available < completed or (
                        previous is not None and available < previous
                    ):
                        raise ValueError("Assessment publication clock moved backward")
                    self._check_authority(owner, namespace, state, publisher, staged)
                    check_prepared()
                    reason = reasons.PUBLICATION_FAILED
                    published = deepcopy(staged)
                    object.__setattr__(published, "available_at", available)
                    object.__setattr__(
                        published,
                        "fingerprint",
                        canonical_fingerprint(published._payload()),
                    )
                    expected = {**staged_before, "available_at": available.isoformat()}
                    expected.pop("fingerprint")
                    expected["fingerprint"] = canonical_fingerprint(expected)
                    if published.to_dict() != expected:
                        raise ValueError("publication changed Assessment occurrence")
                    fact = _encode_result(published)
                    retained = _reconstruct_result(fact)
                    public = _public_result_copy(retained)

                    def check_publication() -> None:
                        if staged.to_dict() != staged_before:
                            raise ValueError("staged Assessment changed")
                        for value in (published, retained, public):
                            if (
                                type(value) is not PolygonCompletedDailyAssessmentResult
                                or value.to_dict() != expected
                            ):
                                raise ValueError("final Assessment projection changed")
                        graphs = [
                            _graph_ids(value)
                            for value in (staged, published, retained, public)
                        ]
                        for index, graph in enumerate(graphs):
                            if any(graph & other for other in graphs[:index]):
                                raise ValueError("Assessment publication graphs alias")

                    check_publication()
                    if type(fact) is not bytes or any(
                        _encode_result(value) != fact
                        for value in (published, retained, public)
                    ):
                        raise ValueError(
                            "public Assessment bytes differ from final fact"
                        )
                    next_state = sequence + 1, (*entries, fact)
                    reason = reasons.HISTORY_INVALID
                    self._check_authority(owner, namespace, state, publisher, staged)
                    reason = reasons.SOURCE_MISMATCH
                    reauthenticate()
                    reason = reasons.PUBLICATION_FAILED
                    check_publication()
                    reason = reasons.HISTORY_INVALID
                    self._check_history()
                    check_prepared()
                    self._check_authority(owner, namespace, state, publisher, staged)
                    if state != (sequence, entries):
                        raise PolygonCompletedDailyAssessmentRefused(
                            reasons.HISTORY_INVALID, "committed inventory changed"
                        )
                    reason = reasons.PUBLICATION_FAILED
                    if public.execution_id in execution_ids:
                        raise ValueError("duplicate Assessment execution ID")
                    if available < completed or (
                        previous is not None and available < previous
                    ):
                        raise PolygonCompletedDailyAssessmentRefused(
                            reasons.TEMPORAL_FAILURE, "publication chronology changed"
                        )
                    selectors = (
                        request.interpretation_history_namespace_id,
                        request.interpretation_history_sequence,
                        request.interpretation_execution_id,
                        request.interpretation_fingerprint,
                    )
                    namespace_root = self.__namespace
                    owner_namespace_root = owner._namespace_id
                    # Final source/support seal: every local validation, traversal,
                    # allocation and callback above must precede this authentication.
                    reason = reasons.SOURCE_MISMATCH
                    sealed = self._authenticate_source(request, publisher)
                    if (
                        type(sealed) is not i.PolygonCompletedDailyInterpretationResult
                        or type(sealed.history_namespace_id) is not str
                        or type(sealed.history_sequence) is not int
                        or type(sealed.execution_id) is not str
                        or type(sealed.fingerprint) is not str
                        or sealed.history_namespace_id != selectors[0]
                        or sealed.history_sequence != selectors[1]
                        or sealed.execution_id != selectors[2]
                        or sealed.fingerprint != selectors[3]
                    ):
                        raise PolygonCompletedDailyAssessmentRefused(
                            reasons.SOURCE_MISMATCH, "sealed source occurrence changed"
                        )
                    # Direct identity reads only after the seal: no property,
                    # projection, codec, graph or history validation dispatch.
                    reason = reasons.HISTORY_INVALID
                    if (
                        object.__getattribute__(self, "_committed") is not state
                        or object.__getattribute__(
                            self,
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__interpretation_service",
                        )
                        is not publisher
                        or object.__getattribute__(
                            self,
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__history_owner",
                        )
                        is not owner
                        or object.__getattribute__(
                            self,
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__namespace",
                        )
                        is not namespace_root
                        or object.__getattribute__(owner, "_namespace_id")
                        is not owner_namespace_root
                        or object.__getattribute__(owner, "_state") is not state
                        or object.__getattribute__(owner, "_pending") is not staged
                    ):
                        raise PolygonCompletedDailyAssessmentRefused(
                            reasons.HISTORY_INVALID,
                            "Assessment authority changed during source seal",
                        )
                finally:
                    # Cleanup cannot be redirected by a changed service/private root.
                    # On success it precedes commit; no mutation follows the append.
                    object.__setattr__(owner, "_pending", None)
                self._committed = next_state
                owner._state = next_state
                return public
        except PolygonCompletedDailyAssessmentRefused:
            raise
        except Exception as error:
            raise PolygonCompletedDailyAssessmentRefused(reason, str(error)) from error

    def get_result_history_as_of(
        self,
        artifact_reference: GovernedTechnicalArtifactReference,
        *,
        knowledge_as_of: datetime,
    ) -> tuple[PolygonCompletedDailyAssessmentResult, ...]:
        """Read authentic publications in sequence order, without changing authority."""
        if type(artifact_reference) is not GovernedTechnicalArtifactReference:
            raise TypeError("exact governed artifact reference required")
        # Preserve and validate the supplied fingerprint rather than regenerating it.
        reference = deepcopy(artifact_reference)
        reference_before = reference.to_dict()
        owner, namespace = self._history_owner, self._namespace
        original_publisher = self.__interpretation_service
        reasons = PolygonCompletedDailyAssessmentRefusalReason
        reason = reasons.TEMPORAL_FAILURE
        try:
            cutoff = a._timestamp(knowledge_as_of)
            reason = reasons.HISTORY_INVALID
            with ExitStack() as stack:
                publisher = self._lock_inputs(stack)
                state = self._committed
                if (
                    publisher is not original_publisher
                    or self.__history_owner is not owner
                    or self.__namespace is not namespace
                    or owner._namespace_id is not namespace
                ):
                    raise ValueError("acquired Assessment history authority changed")
                self._check_authority(owner, namespace, state, publisher, None)
                retained = self._authenticate_history_locked(state, publisher)
                self._check_authority(owner, namespace, state, publisher, None)

                reason = reasons.PUBLICATION_FAILED
                copies = []
                for (item, _), fact in zip(retained, state[1], strict=True):
                    if (
                        item.assessment.source_interpretation_occurrence.artifact_reference.to_dict()
                        == reference_before
                        and item.available_at <= cutoff
                    ):
                        public = _public_result_copy(item)
                        _check_copy(public, item, _decode_result(fact))
                        if _encode_result(public) != fact:
                            raise ValueError("public Assessment bytes changed")
                        copies.append(public)
                public_results = tuple(copies)
                retained_graph = set().union(
                    *(_graph_ids(item) for item, _ in retained)
                )
                public_graph: set[int] = set()
                for public in public_results:
                    graph = _graph_ids(public)
                    if graph & (retained_graph | public_graph):
                        raise ValueError("Assessment history result graphs alias")
                    public_graph.update(graph)
                if reference.to_dict() != reference_before:
                    raise ValueError("history artifact reference changed")

                # Recheck every retained fact/source, including invisible occurrences,
                # after all public reconstruction and isolation work.
                reason = reasons.HISTORY_INVALID
                self._check_authority(owner, namespace, state, publisher, None)
                reauthenticated = self._authenticate_history_locked(state, publisher)
                for (before, source_before), (after, source_after), fact in zip(
                    retained, reauthenticated, state[1], strict=True
                ):
                    if _encode_result(before) != fact or _encode_result(after) != fact:
                        raise ValueError("retained Assessment fact changed")
                    if source_before != source_after:
                        raise PolygonCompletedDailyAssessmentRefused(
                            reasons.SOURCE_MISMATCH,
                            "retained Interpretation projection changed",
                        )
                requests = tuple(
                    replace(item.assessment.source_interpretation_occurrence)
                    for item, _ in retained
                )
                selectors = tuple(
                    (
                        request.interpretation_history_namespace_id,
                        request.interpretation_history_sequence,
                        request.interpretation_execution_id,
                        request.interpretation_fingerprint,
                    )
                    for request in requests
                )
                self._check_authority(owner, namespace, state, publisher, None)
                # Final complete source/support seal. All local projections, codecs,
                # graphs, history/domain validation and preparation precede this loop.
                for request, selected in zip(requests, selectors, strict=True):
                    sealed = self._authenticate_retained_source(request, publisher)
                    if (
                        type(sealed) is not i.PolygonCompletedDailyInterpretationResult
                        or type(sealed.history_namespace_id) is not str
                        or type(sealed.history_sequence) is not int
                        or type(sealed.execution_id) is not str
                        or type(sealed.fingerprint) is not str
                        or sealed.history_namespace_id != selected[0]
                        or sealed.history_sequence != selected[1]
                        or sealed.execution_id != selected[2]
                        or sealed.fingerprint != selected[3]
                    ):
                        raise PolygonCompletedDailyAssessmentRefused(
                            reasons.SOURCE_MISMATCH, "sealed source occurrence changed"
                        )
                # Only direct identity reads remain after the complete seal.
                if (
                    object.__getattribute__(self, "_committed") is not state
                    or object.__getattribute__(
                        self,
                        "_PolygonCompletedDailyProductionAssessmentApplicationService"
                        "__interpretation_service",
                    )
                    is not publisher
                    or object.__getattribute__(
                        self,
                        "_PolygonCompletedDailyProductionAssessmentApplicationService"
                        "__history_owner",
                    )
                    is not owner
                    or object.__getattribute__(
                        self,
                        "_PolygonCompletedDailyProductionAssessmentApplicationService"
                        "__namespace",
                    )
                    is not namespace
                    or object.__getattribute__(owner, "_namespace_id") is not namespace
                    or object.__getattribute__(owner, "_state") is not state
                    or object.__getattribute__(owner, "_pending") is not None
                ):
                    raise ValueError("Assessment authority changed during read seal")
                return public_results
        except PolygonCompletedDailyAssessmentRefused:
            raise
        except Exception as error:
            raise PolygonCompletedDailyAssessmentRefused(reason, str(error)) from error

    def _authenticate_retained_source(
        self,
        request: domain.PolygonCompletedDailyAssessmentRequest,
        publisher: i.PolygonCompletedDailyProductionInterpretationApplicationService,
    ) -> i.PolygonCompletedDailyInterpretationResult:
        """A committed Assessment losing its exact source is invalid history."""
        try:
            return self._authenticate_source(request, publisher)
        except PolygonCompletedDailyAssessmentRefused as error:
            if error.reason == (
                PolygonCompletedDailyAssessmentRefusalReason.INTERPRETATION_UNAVAILABLE
            ):
                raise PolygonCompletedDailyAssessmentRefused(
                    PolygonCompletedDailyAssessmentRefusalReason.HISTORY_INVALID,
                    "retained Assessment source occurrence unavailable",
                ) from error
            raise

    def _authenticate_history_locked(
        self,
        state: tuple[int, tuple[bytes, ...]],
        publisher: i.PolygonCompletedDailyProductionInterpretationApplicationService,
    ) -> tuple[tuple[PolygonCompletedDailyAssessmentResult, bytes], ...]:
        """Authenticate the complete inventory under held locks; retain no authority."""
        self._check_history()
        authenticated = []
        reasons = PolygonCompletedDailyAssessmentRefusalReason
        for fact in state[1]:
            item = _reconstruct_result(fact)
            request = item.assessment.source_interpretation_occurrence
            request_before = request.to_dict()
            source = self._authenticate_retained_source(request, publisher)
            try:
                if type(source) is not i.PolygonCompletedDailyInterpretationResult:
                    raise ValueError("exact authenticated Interpretation required")
                source_fact = i._encode_result(source)
                if (
                    request_before
                    != {
                        "artifact_reference": (
                            source.source_technical_occurrence.artifact_reference.to_dict()
                        ),
                        "interpretation_history_namespace_id": (
                            source.history_namespace_id
                        ),
                        "interpretation_history_sequence": source.history_sequence,
                        "interpretation_execution_id": source.execution_id,
                        "interpretation_fingerprint": source.fingerprint,
                    }
                    or item.interpretation_available_at != source.available_at
                ):
                    raise ValueError("retained Interpretation correspondence mismatch")
            except Exception as error:
                raise PolygonCompletedDailyAssessmentRefused(
                    reasons.SOURCE_MISMATCH, str(error)
                ) from error
            domain.validate_governed_daily_technical_assessment(
                content=item.assessment,
                interpretation=source.interpretation,
                source_interpretation_occurrence=request,
            )
            if _encode_result(item) != fact or request.to_dict() != request_before:
                raise ValueError("retained Assessment changed during validation")
            if i._encode_result(source) != source_fact:
                raise PolygonCompletedDailyAssessmentRefused(
                    reasons.SOURCE_MISMATCH,
                    "retained Interpretation changed during validation",
                )
            authenticated.append((item, source_fact))
        return tuple(authenticated)

    def _prepare_assessment(
        self,
        request: domain.PolygonCompletedDailyAssessmentRequest,
        started: datetime,
    ) -> _PreparedAssessment:
        """Convenience preparation boundary; no clocks or publication."""
        if type(request) is not domain.PolygonCompletedDailyAssessmentRequest:
            raise TypeError("only exact Assessment selector requests are accepted")
        request = replace(request)
        owner, namespace, state = self._history_owner, self._namespace, self._committed
        reasons = PolygonCompletedDailyAssessmentRefusalReason
        reason = reasons.TEMPORAL_FAILURE
        try:
            a._require_canonical_timestamp(started, "Assessment start")
            reason = reasons.HISTORY_INVALID
            with ExitStack() as stack:
                publisher = self._lock_inputs(stack)
                self._check_authority(owner, namespace, state, publisher, None)
                return self._prepare_assessment_locked(request, started, publisher)
        except PolygonCompletedDailyAssessmentRefused:
            raise
        except Exception as error:
            raise PolygonCompletedDailyAssessmentRefused(reason, str(error)) from error

    def _check_authority(
        self,
        owner: _AssessmentHistory,
        namespace: str,
        state: tuple[int, tuple[bytes, ...]],
        publisher: i.PolygonCompletedDailyProductionInterpretationApplicationService,
        pending: PolygonCompletedDailyAssessmentResult | None,
    ) -> None:
        if (
            type(owner) is not _AssessmentHistory
            or self.__interpretation_service is not publisher
            or self._history_owner is not owner
            or type(self._namespace) is not str
            or self._namespace != namespace
            or type(owner._namespace_id) is not str
            or owner._namespace_id != namespace
            or self._committed is not state
            or owner._state is not state
            or owner._pending is not pending
        ):
            raise PolygonCompletedDailyAssessmentRefused(
                PolygonCompletedDailyAssessmentRefusalReason.HISTORY_INVALID,
                "Assessment publication authority changed",
            )

    @staticmethod
    def _authenticate_source(
        request: domain.PolygonCompletedDailyAssessmentRequest,
        publisher: i.PolygonCompletedDailyProductionInterpretationApplicationService,
    ) -> i.PolygonCompletedDailyInterpretationResult:
        reasons = PolygonCompletedDailyAssessmentRefusalReason
        try:
            return publisher._authenticate_interpretation_occurrence(
                artifact_reference=request.artifact_reference,
                interpretation_history_namespace_id=(
                    request.interpretation_history_namespace_id
                ),
                interpretation_history_sequence=request.interpretation_history_sequence,
                interpretation_execution_id=request.interpretation_execution_id,
                interpretation_fingerprint=request.interpretation_fingerprint,
            )
        except i._InterpretationOccurrenceUnavailable as error:
            raise PolygonCompletedDailyAssessmentRefused(
                reasons.INTERPRETATION_UNAVAILABLE, str(error)
            ) from error
        except i._InterpretationHistoryInvalid as error:
            raise PolygonCompletedDailyAssessmentRefused(
                reasons.HISTORY_INVALID, str(error)
            ) from error
        except i._InterpretationSourceMismatch as error:
            raise PolygonCompletedDailyAssessmentRefused(
                reasons.SOURCE_MISMATCH, str(error)
            ) from error

    def _prepare_assessment_locked(
        self,
        request: domain.PolygonCompletedDailyAssessmentRequest,
        started: datetime,
        publisher: i.PolygonCompletedDailyProductionInterpretationApplicationService,
    ) -> _PreparedAssessment:
        """Resolve and assess with the complete input lock chain already held."""
        if type(request) is not domain.PolygonCompletedDailyAssessmentRequest:
            raise TypeError("only exact Assessment selector requests are accepted")
        reasons = PolygonCompletedDailyAssessmentRefusalReason
        reason = reasons.TEMPORAL_FAILURE
        try:
            a._require_canonical_timestamp(started, "Assessment start")
            owner, namespace, state = (
                self._history_owner,
                self._namespace,
                self._committed,
            )

            def check_authority() -> None:
                self._check_authority(owner, namespace, state, publisher, None)

            def authenticate() -> i.PolygonCompletedDailyInterpretationResult:
                check_authority()
                source = self._authenticate_source(request, publisher)
                check_authority()
                return source

            reason = reasons.HISTORY_INVALID
            check_authority()
            self._check_history()
            check_authority()
            reason = reasons.SOURCE_MISMATCH
            request_before = deepcopy(request.to_dict())
            reason = reasons.HISTORY_INVALID
            source = authenticate()
            reason = reasons.SOURCE_MISMATCH
            if type(source) is not i.PolygonCompletedDailyInterpretationResult:
                raise ValueError("exact authenticated Interpretation result required")
            source_before = deepcopy(source.to_dict())
            interpretation_before = deepcopy(source.interpretation.to_dict())
            if request_before != {
                "artifact_reference": (
                    source.source_technical_occurrence.artifact_reference.to_dict()
                ),
                "interpretation_history_namespace_id": source.history_namespace_id,
                "interpretation_history_sequence": source.history_sequence,
                "interpretation_execution_id": source.execution_id,
                "interpretation_fingerprint": source.fingerprint,
            }:
                raise ValueError("authenticated Interpretation selectors differ")
            if source.available_at > started:
                raise PolygonCompletedDailyAssessmentRefused(
                    reasons.INTERPRETATION_UNAVAILABLE,
                    "exact Interpretation occurrence unavailable by start",
                )
            reason = reasons.SEMANTIC_FAILED
            content = domain.assess_governed_daily_technical_interpretation(
                interpretation=source.interpretation,
                source_interpretation_occurrence=request,
            )
            if type(content) is not GovernedDailyTechnicalAssessment:
                raise TypeError("exact governed Assessment content required")
            content_before = deepcopy(content.to_dict())
            domain.validate_governed_daily_technical_assessment(
                content=content,
                interpretation=source.interpretation,
                source_interpretation_occurrence=request,
            )
            prepared = _PreparedAssessment(
                request, source_before, content, source.available_at, started
            )
            reason = reasons.SOURCE_MISMATCH
            if request.to_dict() != request_before:
                raise ValueError("Assessment request changed during preparation")
            reason = reasons.HISTORY_INVALID
            self._check_history()
            check_authority()
            reason = reasons.SOURCE_MISMATCH
            # Fresh reconstructions require complete fact correspondence.
            reauthenticated = authenticate()
            if (
                type(reauthenticated) is not i.PolygonCompletedDailyInterpretationResult
                or reauthenticated.to_dict() != source_before
                or source.to_dict() != source_before
                or source.interpretation.to_dict() != interpretation_before
                or request.to_dict() != request_before
            ):
                raise ValueError(
                    "authenticated Interpretation changed during preparation"
                )
            reason = reasons.SEMANTIC_FAILED
            if content.to_dict() != content_before:
                raise ValueError("prepared Assessment content changed")
            check_authority()
            return prepared
        except PolygonCompletedDailyAssessmentRefused:
            raise
        except Exception as error:
            raise PolygonCompletedDailyAssessmentRefused(reason, str(error)) from error


__all__ = [
    "PolygonCompletedDailyAssessmentRefusalReason",
    "PolygonCompletedDailyAssessmentRefused",
    "PolygonCompletedDailyAssessmentResult",
    "PolygonCompletedDailyProductionAssessmentApplicationService",
]
