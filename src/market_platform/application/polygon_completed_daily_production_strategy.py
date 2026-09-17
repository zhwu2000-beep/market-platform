"""Governed Strategy execution and atomic canonical publication."""

from __future__ import annotations

import json
import math
from _thread import LockType
from collections.abc import Callable
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application import (
    polygon_completed_daily_production_admission as a,
)
from market_platform.application import (
    polygon_completed_daily_production_assessment as assessment,
)
from market_platform.application import (
    polygon_completed_daily_production_technical as t,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import (
    governed_daily_technical_assessment as assessment_domain,
)
from market_platform.research import governed_daily_technical_strategy as domain
from market_platform.research.governed_daily_technical_interpretation import (
    GovernedTechnicalArtifactReference,
    _choice,
    _fingerprint,
)
from market_platform.research.governed_daily_technical_strategy import (
    GovernedDailyTechnicalStrategy,
)

_SCHEMA = "polygon_completed_daily_strategy_result/v1"
_OPERATION = "production.polygon_completed_daily.daily_technical_strategy.application"
_VERSION = "1.0.0"
_EXECUTOR = "market_platform.application/polygon_completed_daily_production_strategy/v1"
_PREFIX = "polygon_completed_daily_strategy"


class PolygonCompletedDailyStrategyRefusalReason:
    ASSESSMENT_UNAVAILABLE = "assessment_occurrence_unavailable"
    HISTORY_INVALID = "history_incomplete_or_corrupt"
    SOURCE_MISMATCH = "source_lineage_mismatch"
    SEMANTIC_FAILED = "semantic_execution_or_correspondence_failed"
    TEMPORAL_FAILURE = "temporal_failure"
    PUBLICATION_FAILED = "strategy_publication_or_copy_failed"


class PolygonCompletedDailyStrategyRefused(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        if type(message) is not str:
            raise TypeError("exact refusal message string required")
        _choice(
            reason,
            (
                "assessment_occurrence_unavailable",
                "history_incomplete_or_corrupt",
                "source_lineage_mismatch",
                "semantic_execution_or_correspondence_failed",
                "temporal_failure",
                "strategy_publication_or_copy_failed",
            ),
        )
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True, slots=True, init=False)
class PolygonCompletedDailyStrategyResult:
    strategy: GovernedDailyTechnicalStrategy
    assessment_available_at: datetime
    execution_id: str
    history_namespace_id: str
    history_sequence: int
    execution_started_at: datetime
    execution_completed_at: datetime
    available_at: datetime
    fingerprint: str

    def __init__(self) -> None:
        raise TypeError("Strategy results require trusted execution")

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "strategy": self.strategy.to_dict(),
            "assessment_available_at": self.assessment_available_at.isoformat(),
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
        if type(self.strategy) is not GovernedDailyTechnicalStrategy:
            raise ValueError("exact governed Strategy content required")
        self.strategy._validate()
        t._identity(self.execution_id, _PREFIX)
        t._identity(self.history_namespace_id, _PREFIX + "_history")
        t._sequence(self.history_sequence)
        for instant in (
            self.assessment_available_at,
            self.execution_started_at,
            self.execution_completed_at,
            self.available_at,
        ):
            a._require_canonical_timestamp(instant, "Strategy occurrence time")
        if not (
            self.assessment_available_at
            <= self.execution_started_at
            <= self.execution_completed_at
            <= self.available_at
        ):
            raise ValueError("Strategy occurrence chronology invalid")
        payload = self._payload()
        _fingerprint(self.fingerprint)
        if canonical_fingerprint(payload) != self.fingerprint:
            raise ValueError("Strategy envelope fingerprint mismatch")
        return deepcopy({**payload, "fingerprint": self.fingerprint})


def _public_result_copy(
    retained: PolygonCompletedDailyStrategyResult,
) -> PolygonCompletedDailyStrategyResult:
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


def _encode_result(result: PolygonCompletedDailyStrategyResult) -> bytes:
    if type(result) is not PolygonCompletedDailyStrategyResult:
        raise TypeError("exact Strategy result required")
    return _canonical_bytes(result.to_dict())


def _decode_result(fact: bytes) -> dict[str, Any]:
    if type(fact) is not bytes:
        raise TypeError("exact immutable Strategy bytes required")
    value = json.loads(fact)
    if type(value) is not dict or _canonical_bytes(value) != fact:
        raise ValueError("noncanonical Strategy encoding")
    return value


def _reconstruct_result(fact: bytes) -> PolygonCompletedDailyStrategyResult:
    """Rebuild caller-owned values and check the entire original scalar encoding."""
    projection = _decode_result(fact)
    content = projection["strategy"]
    occurrence = content["source_assessment_occurrence"]
    artifact = occurrence["artifact_reference"]
    artifact_value = object.__new__(GovernedTechnicalArtifactReference)
    for item in fields(artifact_value):
        object.__setattr__(artifact_value, item.name, artifact[item.name])
    request = domain.PolygonCompletedDailyStrategyRequest(
        **{**occurrence, "artifact_reference": artifact_value}
    )
    policy = content["strategy_policy_identity"]
    policy_value = object.__new__(domain.GovernedDailyTechnicalStrategyPolicyIdentity)
    for item in fields(policy_value):
        object.__setattr__(policy_value, item.name, policy[item.name])
    strategy = object.__new__(GovernedDailyTechnicalStrategy)
    replacements = {
        "source_assessment_occurrence": request,
        "canonical_instrument_id": CanonicalInstrumentId(
            **content["canonical_instrument_id"]
        ),
        "analysis_as_of": datetime.fromisoformat(content["analysis_as_of"]),
        "strategy_policy_identity": policy_value,
    }
    for item in fields(strategy):
        value = (
            replacements[item.name] if item.name in replacements else content[item.name]
        )
        object.__setattr__(strategy, item.name, value)
    result = object.__new__(PolygonCompletedDailyStrategyResult)
    for item in fields(result):
        value = projection[item.name] if item.name != "strategy" else strategy
        if item.name.endswith("_at"):
            value = datetime.fromisoformat(projection[item.name])
        object.__setattr__(result, item.name, value)
    # Preserve supplied hashes and bind every key, scalar and nested projection.
    if _encode_result(result) != fact:
        raise ValueError("Strategy scalar reconstruction mismatch")
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
    public: PolygonCompletedDailyStrategyResult,
    retained: PolygonCompletedDailyStrategyResult,
    expected: dict[str, object],
) -> None:
    if (
        type(public) is not PolygonCompletedDailyStrategyResult
        or public.to_dict() != expected
        or retained.to_dict() != expected
        or _graph_ids(public) & _graph_ids(retained)
    ):
        raise ValueError("public result changed content or aliases retained state")


class _StrategyHistory:
    """Canonical committed facts; transient pending staging grants no authority."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._namespace_id = f"{_PREFIX}_history:{uuid4().hex}"
        self.__namespace = self._namespace_id
        self._state: tuple[int, tuple[bytes, ...]] = (
            1,
            (),
        )
        self._pending: PolygonCompletedDailyStrategyResult | None = None

    def _stage_publication(self, result: PolygonCompletedDailyStrategyResult) -> None:
        if type(result) is not PolygonCompletedDailyStrategyResult:
            raise TypeError("exact Strategy result required")
        result.to_dict()
        self._pending = result

    def _validate(self) -> None:
        if type(self._state) is not tuple or len(self._state) != 2:
            raise ValueError("exact history state tuple required")
        sequence, entries = self._state
        t._sequence(sequence)
        if self._namespace_id is not self.__namespace:
            raise ValueError("original Strategy history namespace required")
        t._identity(self._namespace_id, _PREFIX + "_history")
        if type(entries) is not tuple or sequence != len(entries) + 1:
            raise ValueError("Strategy history incomplete")
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
                raise ValueError("Strategy history corrupt")
            ids.add(item.execution_id)
            previous = item.available_at


@dataclass(frozen=True, slots=True)
class _StrategyRoot:
    """Construction anchors; neither a public capability nor occurrence authority."""

    owner: _StrategyHistory
    namespace: str
    lock: LockType
    publisher: assessment.PolygonCompletedDailyProductionAssessmentApplicationService
    assessment_owner: assessment._AssessmentHistory
    assessment_namespace: str
    assessment_roots: tuple[Any, ...]
    assessment_lock: LockType
    interpretation_lock: LockType


class PolygonCompletedDailyProductionStrategyApplicationService:
    def __init__(
        self,
        assessment_service: (
            assessment.PolygonCompletedDailyProductionAssessmentApplicationService
        ),
        execution_clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(assessment_service) is not (
            assessment.PolygonCompletedDailyProductionAssessmentApplicationService
        ):
            raise TypeError("exact trusted Assessment service required")
        if execution_clock is not None and not callable(execution_clock):
            raise TypeError("execution_clock must be callable")
        self._clock = a._utc_now if execution_clock is None else execution_clock
        self.__assessment_service = assessment_service
        self.__history_owner = _StrategyHistory()
        self.__namespace = self.__history_owner._namespace_id
        self._committed = self.__history_owner._state
        # Capture existing roots without authenticating, observing or sampling time.
        source_roots = vars(assessment_service)[
            "_PolygonCompletedDailyProductionAssessmentApplicationService__consumption_roots"
        ]
        source_owner = source_roots[0]
        self.__root = _StrategyRoot(
            self.__history_owner,
            self.__namespace,
            self.__history_owner._lock,
            assessment_service,
            source_owner,
            source_roots[1],
            source_roots,
            source_owner._lock,
            source_roots[3]._lock,
        )

    @property
    def _assessment_service(
        self,
    ) -> assessment.PolygonCompletedDailyProductionAssessmentApplicationService:
        return self.__assessment_service

    @property
    def _history_owner(self) -> _StrategyHistory:
        return self.__history_owner

    @property
    def _namespace(self) -> str:
        return self.__namespace

    def _check_roots(self) -> None:
        """Direct root checks; no occurrence or inventory authentication."""
        root = self.__root
        publisher = root.publisher
        source_roots = root.assessment_roots
        publisher_state = vars(publisher)
        if (
            self.__history_owner is not root.owner
            or self.__namespace is not root.namespace
            or root.owner._namespace_id is not root.namespace
            or root.owner._lock is not root.lock
            or self.__assessment_service is not publisher
            or publisher_state.get(
                "_PolygonCompletedDailyProductionAssessmentApplicationService__history_owner"
            )
            is not source_roots[0]
            or publisher_state.get(
                "_PolygonCompletedDailyProductionAssessmentApplicationService__namespace"
            )
            is not source_roots[1]
            or root.assessment_owner._namespace_id is not root.assessment_namespace
            or root.assessment_owner._lock is not root.assessment_lock
            or publisher_state.get(
                "_PolygonCompletedDailyProductionAssessmentApplicationService__consumption_roots"
            )
            is not source_roots
            or publisher_state.get(
                "_PolygonCompletedDailyProductionAssessmentApplicationService__interpretation_service"
            )
            is not source_roots[2]
            or source_roots[2]._history_owner is not source_roots[3]
            or source_roots[2]._namespace is not source_roots[4]
            or source_roots[3]._namespace_id is not source_roots[4]
            or source_roots[3]._lock is not root.interpretation_lock
        ):
            raise ValueError("original Strategy/Assessment roots or commitment changed")

    def _check_locked_roots(self) -> None:
        # Check current commitments only under the acquired chain, never before a wait.
        self._check_roots()
        root = self.__root
        if (
            not root.lock.locked()
            or root.owner._state is not self._committed
            or root.owner._pending is not None
        ):
            raise ValueError("original Strategy lock and idle commitment required")
        # Assessment checks the roots actually selected by its existing lock seam,
        # including upstream replacement followed by restoration after selection.
        root.publisher._check_consumption_roots(
            root.publisher._committed, root.assessment_roots[2]._committed
        )

    def _lock_inputs(self, stack: ExitStack) -> None:
        self._check_roots()
        root = self.__root
        root.publisher._lock_inputs(stack)
        stack.enter_context(root.lock)
        self._check_locked_roots()

    def _check_transaction(
        self,
        root: _StrategyRoot,
        state: tuple[int, tuple[bytes, ...]],
        pending: PolygonCompletedDailyStrategyResult | None,
    ) -> None:
        try:
            self._check_roots()
        except Exception as error:
            raise PolygonCompletedDailyStrategyRefused(
                PolygonCompletedDailyStrategyRefusalReason.HISTORY_INVALID, str(error)
            ) from error
        if (
            self.__root is not root
            or self._committed is not state
            or root.owner._state is not state
            or root.owner._pending is not pending
        ):
            raise PolygonCompletedDailyStrategyRefused(
                PolygonCompletedDailyStrategyRefusalReason.HISTORY_INVALID,
                "Strategy transaction authority changed",
            )

    def _authenticate_history_locked(
        self, root: _StrategyRoot, state: tuple[int, tuple[bytes, ...]]
    ) -> tuple[PolygonCompletedDailyStrategyResult, ...]:
        root.owner._validate()
        prior = tuple(_reconstruct_result(fact) for fact in state[1])
        for item, fact in zip(prior, state[1], strict=True):
            request = item.strategy.source_assessment_occurrence
            try:
                pair = root.publisher._authenticate_assessment_occurrence(request)
            except assessment._AssessmentOccurrenceUnavailable as error:
                raise assessment._AssessmentHistoryInvalid(
                    "committed Strategy source unavailable"
                ) from error
            _check_pair(request.to_dict(), pair)
            _check_strategy_source(item, pair)
            _validate_committed_assessment(pair)
            domain.validate_governed_daily_technical_strategy(
                content=item.strategy,
                assessment=pair.assessment.assessment,
                interpretation=pair.interpretation.interpretation,
                source_assessment_occurrence=request,
            )
            if _encode_result(item) != fact:
                raise ValueError("committed Strategy changed during authentication")
            _check_pair(request.to_dict(), pair)
        return prior

    def execute(
        self, request: domain.PolygonCompletedDailyStrategyRequest
    ) -> PolygonCompletedDailyStrategyResult:
        if type(request) is not domain.PolygonCompletedDailyStrategyRequest:
            raise TypeError("only exact Strategy selector requests are accepted")
        if type(request.artifact_reference) is not GovernedTechnicalArtifactReference:
            raise TypeError("exact governed artifact reference required")
        reasons = PolygonCompletedDailyStrategyRefusalReason
        try:
            request = deepcopy(request)
        except Exception as error:
            raise PolygonCompletedDailyStrategyRefused(
                reasons.PUBLICATION_FAILED, str(error)
            ) from error
        # Malformed detached values remain boundary TypeError/ValueError failures.
        projection = request.to_dict()
        try:
            request_before = deepcopy(projection)
        except Exception as error:
            raise PolygonCompletedDailyStrategyRefused(
                reasons.PUBLICATION_FAILED, str(error)
            ) from error
        reason = reasons.TEMPORAL_FAILURE
        try:
            started = a._timestamp(self._clock())
            root = self.__root
            owner, publisher = root.owner, root.publisher
            reason = reasons.HISTORY_INVALID
            with ExitStack() as stack:
                self._lock_inputs(stack)
                # A predecessor may commit while this execution waits for the chain.
                state = self._committed
                staged = None
                staging = False
                try:
                    self._check_transaction(root, state, None)
                    prior = self._authenticate_history_locked(root, state)
                    self._check_transaction(root, state, None)
                    inventory = publisher._authenticate_assessment_inventory()
                    inventory_facts = tuple(
                        (pair.assessment_fact, pair.interpretation_fact)
                        for pair in inventory
                    )
                    self._check_transaction(root, state, None)
                    pair = publisher._authenticate_assessment_occurrence(request)
                    _check_pair(request_before, pair)
                    if (pair.assessment_fact, pair.interpretation_fact) not in (
                        inventory_facts
                    ):
                        raise assessment._AssessmentSourceMismatch(
                            "selected pair differs from complete captured inventory"
                        )
                    source_available = pair.assessment.available_at
                    if source_available > started:
                        raise assessment._AssessmentOccurrenceUnavailable(
                            "Assessment unavailable at Strategy start"
                        )
                    self._check_transaction(root, state, None)
                    _validate_committed_assessment(pair)
                    reason = reasons.SEMANTIC_FAILED
                    content = domain.derive_governed_daily_technical_strategy(
                        assessment=pair.assessment.assessment,
                        interpretation=pair.interpretation.interpretation,
                        source_assessment_occurrence=request,
                    )
                    domain.validate_governed_daily_technical_strategy(
                        content=content,
                        assessment=pair.assessment.assessment,
                        interpretation=pair.interpretation.interpretation,
                        source_assessment_occurrence=request,
                    )
                    content_before = content.to_dict()
                    reason = reasons.TEMPORAL_FAILURE
                    completed = a._timestamp(self._clock())
                    if completed < started:
                        raise ValueError("Strategy completion clock moved backward")
                    reason = reasons.PUBLICATION_FAILED
                    sequence, entries = state
                    previous = prior[-1].available_at if prior else None
                    execution_ids = {item.execution_id for item in prior}
                    execution_id = f"{_PREFIX}:{uuid4().hex}"
                    if execution_id in execution_ids:
                        raise ValueError("duplicate Strategy execution ID")
                    staged = object.__new__(PolygonCompletedDailyStrategyResult)
                    values = {
                        "strategy": deepcopy(content),
                        "assessment_available_at": source_available,
                        "execution_id": execution_id,
                        "history_namespace_id": root.namespace,
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
                    if staged.strategy.to_dict() != content_before:
                        raise ValueError("staging changed Strategy content")
                    self._check_transaction(root, state, None)
                    staging = True
                    owner._stage_publication(staged)
                    self._check_transaction(root, state, staged)
                    if staged.to_dict() != staged_before:
                        raise ValueError("staging changed Strategy occurrence")
                    reason = reasons.TEMPORAL_FAILURE
                    available = a._timestamp(self._clock())
                    if available < completed or (
                        previous is not None and available < previous
                    ):
                        raise ValueError("Strategy publication clock moved backward")
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
                    fact = _encode_result(published)
                    retained = _reconstruct_result(fact)
                    public = _public_result_copy(retained)
                    next_state = sequence + 1, (*entries, fact)

                    reason = reasons.HISTORY_INVALID
                    self._check_transaction(root, state, staged)
                    self._authenticate_history_locked(root, state)
                    _validate_committed_assessment(pair)
                    reason = reasons.SEMANTIC_FAILED
                    domain.validate_governed_daily_technical_strategy(
                        content=retained.strategy,
                        assessment=pair.assessment.assessment,
                        interpretation=pair.interpretation.interpretation,
                        source_assessment_occurrence=request,
                    )
                    reason = reasons.SOURCE_MISMATCH
                    if request.to_dict() != request_before:
                        raise ValueError("detached Strategy selectors changed")
                    _check_pair(request_before, pair)
                    _check_strategy_source(retained, pair)
                    if (
                        tuple(
                            (item.assessment_fact, item.interpretation_fact)
                            for item in inventory
                        )
                        != inventory_facts
                    ):
                        raise ValueError("captured complete pair facts changed")
                    reason = reasons.PUBLICATION_FAILED
                    if (
                        content.to_dict() != content_before
                        or staged.to_dict() != staged_before
                    ):
                        raise ValueError("prepared Strategy changed")
                    graphs = [_graph_ids(content)]
                    for value in (staged, published, retained, public):
                        projection = value.to_dict()
                        if projection != (
                            staged_before if value is staged else expected
                        ):
                            raise ValueError("prepared Strategy envelope changed")
                        current = _graph_ids(value)
                        if any(current & earlier for earlier in graphs):
                            raise ValueError("Strategy publication graphs alias")
                        graphs.append(current)
                    if type(fact) is not bytes or any(
                        _encode_result(value) != fact
                        for value in (published, retained, public)
                    ):
                        raise ValueError("Strategy final canonical fact differs")
                    if (
                        public.execution_id != execution_id
                        or public.execution_id in execution_ids
                        or public.history_sequence != sequence
                        or public.history_namespace_id != root.namespace
                    ):
                        raise ValueError("prepared occurrence identity differs")
                    reason = reasons.HISTORY_INVALID
                    self._check_transaction(root, state, staged)
                    # Capture direct dictionaries before the final support seal.
                    own = vars(self)
                    source = vars(publisher)
                    namespace = root.namespace
                    source_roots = root.assessment_roots
                    source_state = publisher._committed
                    # Every fallible local operation and the entire next state are
                    # complete. This seals ALL captured pairs, including unrelated ones.
                    publisher._revalidate_assessment_inventory(inventory)
                    if (
                        object.__getattribute__(self, "__dict__") is not own
                        or object.__getattribute__(publisher, "__dict__") is not source
                        or own[
                            "_PolygonCompletedDailyProductionStrategyApplicationService"
                            "__root"
                        ]
                        is not root
                        or own[
                            "_PolygonCompletedDailyProductionStrategyApplicationService"
                            "__history_owner"
                        ]
                        is not owner
                        or own[
                            "_PolygonCompletedDailyProductionStrategyApplicationService"
                            "__namespace"
                        ]
                        is not namespace
                        or own[
                            "_PolygonCompletedDailyProductionStrategyApplicationService"
                            "__assessment_service"
                        ]
                        is not publisher
                        or own["_committed"] is not state
                        or root.owner is not owner
                        or root.namespace is not namespace
                        or root.publisher is not publisher
                        or owner._lock is not root.lock
                        or owner._namespace_id is not namespace
                        or owner._state is not state
                        or owner._pending is not staged
                        or source[
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__consumption_roots"
                        ]
                        is not source_roots
                        or source[
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__history_owner"
                        ]
                        is not source_roots[0]
                        or source[
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__namespace"
                        ]
                        is not source_roots[1]
                        or source[
                            "_PolygonCompletedDailyProductionAssessmentApplicationService"
                            "__interpretation_service"
                        ]
                        is not source_roots[2]
                        or source["_committed"] is not source_state
                        or source_roots[0]._state is not source_state
                        or source_roots[0]._namespace_id is not source_roots[1]
                        or source_roots[0]._pending is not None
                        or source_roots[0]._lock is not root.assessment_lock
                    ):
                        raise ValueError("Strategy authority changed during final seal")
                finally:
                    if staging:
                        object.__setattr__(owner, "_pending", None)
                object.__setattr__(self, "_committed", next_state)
                object.__setattr__(owner, "_state", next_state)
                return public
        except PolygonCompletedDailyStrategyRefused:
            raise
        except assessment._AssessmentOccurrenceUnavailable as error:
            raise PolygonCompletedDailyStrategyRefused(
                reasons.ASSESSMENT_UNAVAILABLE, str(error)
            ) from error
        except assessment._AssessmentHistoryInvalid as error:
            raise PolygonCompletedDailyStrategyRefused(
                reasons.HISTORY_INVALID, str(error)
            ) from error
        except assessment._AssessmentSourceMismatch as error:
            raise PolygonCompletedDailyStrategyRefused(
                reasons.SOURCE_MISMATCH, str(error)
            ) from error
        except Exception as error:
            raise PolygonCompletedDailyStrategyRefused(reason, str(error)) from error


def _validate_committed_assessment(pair: assessment._AssessmentPair) -> None:
    # This retained-decision check is a distinct application validation stage;
    # private source authentication and the final support seal remain structural.
    content = pair.assessment.assessment
    try:
        assessment_domain.validate_governed_daily_technical_assessment(
            content=content,
            interpretation=pair.interpretation.interpretation,
            source_interpretation_occurrence=content.source_interpretation_occurrence,
        )
    except Exception as error:
        raise PolygonCompletedDailyStrategyRefused(
            PolygonCompletedDailyStrategyRefusalReason.HISTORY_INVALID, str(error)
        ) from error


def _check_pair(selectors: dict[str, object], pair: assessment._AssessmentPair) -> None:
    if type(pair) is not assessment._AssessmentPair:
        raise assessment._AssessmentSourceMismatch("exact authenticated pair required")
    source = pair.assessment
    if (
        selectors
        != {
            "artifact_reference": (
                source.assessment.source_interpretation_occurrence.artifact_reference.to_dict()
            ),
            "assessment_history_namespace_id": source.history_namespace_id,
            "assessment_history_sequence": source.history_sequence,
            "assessment_execution_id": source.execution_id,
            "assessment_fingerprint": source.fingerprint,
        }
        or assessment._encode_result(source) != pair.assessment_fact
        or _canonical_bytes(pair.interpretation.to_dict()) != pair.interpretation_fact
    ):
        raise assessment._AssessmentSourceMismatch("authenticated pair changed")


def _check_strategy_source(
    item: PolygonCompletedDailyStrategyResult, pair: assessment._AssessmentPair
) -> None:
    content = item.strategy
    if (
        item.assessment_available_at != pair.assessment.available_at
        or content.source_assessment_content_fingerprint
        != pair.assessment.assessment.fingerprint
        or content.source_interpretation_content_fingerprint
        != pair.interpretation.interpretation.fingerprint
        or content.canonical_instrument_id.to_dict()
        != pair.assessment.assessment.canonical_instrument_id.to_dict()
        or content.analysis_as_of != pair.assessment.assessment.analysis_as_of
    ):
        raise assessment._AssessmentSourceMismatch("retained Strategy source differs")


__all__ = [
    "PolygonCompletedDailyStrategyRefusalReason",
    "PolygonCompletedDailyStrategyRefused",
    "PolygonCompletedDailyStrategyResult",
    "PolygonCompletedDailyProductionStrategyApplicationService",
]
