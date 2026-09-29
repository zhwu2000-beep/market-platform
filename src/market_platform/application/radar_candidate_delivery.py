"""Opt-in, single-owner source recovery; stops at durable pending work.

Records and their codecs establish correspondence, never bearer authority. Only
an owned publication/reconciliation followed by durable acceptance feeds the
private reconstruction path. Trusted local storage and no bypass writers are
required; this is not authentication of arbitrary caller JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.radar_candidate import (
    RadarCandidate,
    RadarCandidateDecision,
    RadarCandidateDecisionReason,
    RadarCandidateEligibilityPolicyIdentity,
    evaluate_radar_candidate,
)
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.application import (
    RadarApplicationResult,
    RadarCheckpointAdvancement,
)
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateIdentity,
    RadarGateOccurrence,
    RadarGateResult,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.meaningful_change import evaluate_meaningful_change
from market_platform.radar.observation import RadarObservationCheckpoint
from market_platform.radar.observation_state import (
    RadarObservationState,
    RadarObservationStateLookupResult,
)
from market_platform.radar.observation_state import (
    RadarObservationStateLookupStatus as LookupStatus,
)
from market_platform.radar.pipeline import (
    RadarPipelineFailure,
    RadarPipelineFailureCategory,
    RadarPipelineResult,
)
from market_platform.radar.resolver import RadarGateImplementationKey
from market_platform.radar.trigger import SESSION_CONTENT_TRIGGER_KEY

if TYPE_CHECKING:
    from market_platform.application.radar_candidate_delivery_store import (
        RadarCandidateDeliveryFileStore,
    )

PREPARED_SCHEMA = "radar_prepared_source/v1"
ACCEPTED_SCHEMA = "radar_accepted_source/v1"
DECISION_SCHEMA = "radar_candidate_decision_record/v1"
PENDING_SCHEMA = "radar_pending_candidate/v1"


class DeliveryFailure(StrEnum):
    PREPARED = "PREPARED_PERSISTENCE"
    CHECKPOINT = "UNCERTAIN_CHECKPOINT_PUBLICATION"
    RECOVERY = "RECOVERY_MISMATCH"
    ACCEPTED = "ACCEPTED_PERSISTENCE"
    DECISION = "DECISION_PERSISTENCE"
    PENDING = "PENDING_PERSISTENCE"
    CONFLICT = "IMMUTABLE_CONTENT_CONFLICT"
    INVARIANT = "STRICT_RECONSTRUCTION_OR_CANDIDATE_INVARIANT"


class RadarCandidateDeliveryError(RuntimeError):
    """Bounded stage plus publication uncertainty; never a Candidate reason.

    None means a store/reconstruction operation has no checkpoint-phase context.
    True includes uncertainty, and must never be interpreted as rollback.
    Completed source context is diagnostic only, never SAVED or Candidate authority.
    """

    def __init__(
        self,
        failure: DeliveryFailure,
        checkpoint_may_be_published: bool | None = None,
        *,
        conflict: bool = False,
    ) -> None:
        self.pipeline_result: RadarPipelineResult | None = None
        self.prepared_state: RadarObservationState | None = None
        self.failure = failure
        self.checkpoint_may_be_published = checkpoint_may_be_published
        self.conflict = conflict or failure is DeliveryFailure.CONFLICT
        super().__init__(f"Radar Candidate delivery: {failure.value}")


def _object(value: object, keys: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError("Unexpected recovery record fields")
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if type(value) is not str:
        raise TypeError("Expected a string")
    return value


def _array(value: object) -> list[object]:
    if type(value) is not list:
        raise TypeError("Expected an ordered array")
    return cast(list[object], value)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _equal(left: object, right: object) -> bool:
    # Python mapping equality alone conflates bool/int and int/float scalars.
    return _canonical(left) == _canonical(right)


def _check_projection(raw: object, projection: object) -> None:
    if not _equal(raw, projection):
        raise ValueError("Noncanonical or contradictory recovery payload")


def _fingerprint(value: object) -> str:
    text = _text(value)
    if re.fullmatch(r"sha256:[0-9a-f]{64}", text) is None:
        raise ValueError("Invalid recovery fingerprint")
    return text


def _instrument(value: object) -> CanonicalInstrumentId:
    raw = _object(value, "instrument_id")
    return CanonicalInstrumentId(_text(raw["instrument_id"]))


def _policy(value: object) -> RadarCandidateEligibilityPolicyIdentity:
    raw = _object(value, "policy_id behavioral_revision policy_schema")
    return RadarCandidateEligibilityPolicyIdentity(
        _text(raw["policy_id"]),
        _text(raw["behavioral_revision"]),
        _text(raw["policy_schema"]),
    )


def _occurrence(value: object) -> RadarGateOccurrence:
    raw = _object(value, "occurrence_id gate_identity")
    gate = _object(
        raw["gate_identity"],
        "gate_id behavioral_revision configuration_schema configuration "
        "schema_version fingerprint",
    )
    configuration = gate["configuration"]
    if type(configuration) is not dict:
        raise TypeError("Expected Gate configuration object")
    result = RadarGateOccurrence(
        _text(raw["occurrence_id"]),
        RadarGateIdentity(
            _text(gate["gate_id"]),
            _text(gate["behavioral_revision"]),
            _text(gate["configuration_schema"]),
            configuration,
        ),
    )
    _check_projection(value, result.to_dict())
    return result


def _pipeline_payload(value: RadarPipelineResult) -> dict[str, object]:
    return {
        "profile": value.profile.to_dict(),
        "instrument": value.instrument.to_dict(),
        "as_of": value.as_of.isoformat(),
        "executed_results": [
            {
                "occurrence": item.occurrence.to_dict(),
                "disposition": item.disposition.value,
                "reason_code": item.reason_code,
                "detail": item.detail,
            }
            for item in value.executed_results
        ],
        "failure": None
        if value.failure is None
        else {
            "occurrence": value.failure.occurrence.to_dict(),
            "category": value.failure.category.value,
        },
        "outcome": value.outcome.value,
    }


def _pipeline(value: object) -> RadarPipelineResult:
    raw = _object(value, "profile instrument as_of executed_results failure outcome")
    profile = _object(
        raw["profile"],
        "profile_id behavioral_revision configuration_schema configuration gates "
        "schema_version fingerprint",
    )
    configuration = profile["configuration"]
    if type(configuration) is not dict:
        raise TypeError("Expected Profile configuration object")
    reconstructed = RadarProfile(
        _text(profile["profile_id"]),
        _text(profile["behavioral_revision"]),
        _text(profile["configuration_schema"]),
        tuple(_occurrence(item) for item in _array(profile["gates"])),
        configuration,
    )
    _check_projection(profile, reconstructed.to_dict())
    results = []
    for item in _array(raw["executed_results"]):
        row = _object(item, "occurrence disposition reason_code detail")
        results.append(
            RadarGateResult(
                _occurrence(row["occurrence"]),
                RadarGateDisposition(_text(row["disposition"])),
                _text(row["reason_code"]),
                None if row["detail"] is None else _text(row["detail"]),
            )
        )
    failure = None
    if raw["failure"] is not None:
        failed = _object(raw["failure"], "occurrence category")
        failure = RadarPipelineFailure(
            _occurrence(failed["occurrence"]),
            RadarPipelineFailureCategory(_text(failed["category"])),
        )
    result = RadarPipelineResult(
        reconstructed,
        _instrument(raw["instrument"]),
        datetime.fromisoformat(_text(raw["as_of"])),
        tuple(results),
        failure,
    )
    _check_projection(value, _pipeline_payload(result))
    return result


@dataclass(frozen=True, slots=True)
class SourceRecoveryIdentity:
    fingerprint: str

    def __post_init__(self) -> None:
        _fingerprint(self.fingerprint)


@dataclass(frozen=True, slots=True)
class RadarPredecessorWitness:
    status: LookupStatus
    legacy_checkpoint: RadarObservationCheckpoint | None = None
    state: RadarObservationState | None = None

    def __post_init__(self) -> None:
        RadarObservationStateLookupResult(
            self.status, self.legacy_checkpoint, self.state
        )
        if self.status is LookupStatus.UNAVAILABLE:
            raise ValueError("Unavailable predecessor cannot prepare a source")
        if self.legacy_checkpoint is not None:
            object.__setattr__(
                self,
                "legacy_checkpoint",
                RadarObservationCheckpoint.from_dict(self.legacy_checkpoint.to_dict()),
            )
        if self.state is not None:
            object.__setattr__(
                self, "state", RadarObservationState.from_dict(self.state.to_dict())
            )

    @classmethod
    def from_lookup(
        cls, value: RadarObservationStateLookupResult
    ) -> RadarPredecessorWitness:
        if type(value) is not RadarObservationStateLookupResult:
            raise TypeError("Expected strict predecessor lookup")
        return cls(value.status, value.legacy_checkpoint, value.state)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "legacy_checkpoint": None
            if self.legacy_checkpoint is None
            else self.legacy_checkpoint.to_dict(),
            "state": None if self.state is None else self.state.to_dict(),
        }


def _witness(value: object) -> RadarPredecessorWitness:
    raw = _object(value, "status legacy_checkpoint state")
    result = RadarPredecessorWitness(
        LookupStatus(_text(raw["status"])),
        None
        if raw["legacy_checkpoint"] is None
        else RadarObservationCheckpoint.from_dict(raw["legacy_checkpoint"]),
        None if raw["state"] is None else RadarObservationState.from_dict(raw["state"]),
    )
    _check_projection(value, result.to_dict())
    return result


def _validate_prepared(source: PreparedSourceIntent) -> None:
    """Validate advancement correspondence without creating a SAVED application."""
    pipeline, state, prior = source.pipeline, source.proposed_state, source.predecessor
    if (
        pipeline.instrument != source.instrument
        or state.market_observation.instrument != source.instrument
        or state.profile_fingerprint != pipeline.profile.fingerprint
        or state.pipeline_outcome is not pipeline.outcome
        or state.lightweight_observation.as_of != pipeline.as_of
    ):
        raise ValueError("Prepared Pipeline/state correspondence mismatch")
    previous = None if prior.state is None else prior.state.lightweight_observation
    expected = evaluate_meaningful_change(previous, state.lightweight_observation)
    _check_projection(state.committed_decision.to_dict(), expected.to_dict())
    market = (
        prior.legacy_checkpoint
        if prior.state is None
        else prior.state.market_observation
    )
    current = state.market_observation
    reason = "BASELINE_REQUIRED"
    if market is not None:
        if (
            market.instrument != source.instrument
            or market.observed_completed_session > current.observed_completed_session
        ):
            raise ValueError("Invalid predecessor market correspondence")
        if market.observed_completed_session < current.observed_completed_session:
            reason = "NEW_COMPLETED_SESSION"
        else:
            if market.content_scope != current.content_scope:
                raise ValueError("Same-session scope mismatch")
            reason = (
                "UNCHANGED"
                if market.normalized_market_content_identity
                == current.normalized_market_content_identity
                else "MARKET_CONTENT_CHANGED"
            )
    triggers = [
        gate
        for gate in pipeline.profile.gates
        if RadarGateImplementationKey(
            gate.gate_identity.gate_id,
            gate.gate_identity.behavioral_revision,
            gate.gate_identity.configuration_schema,
        )
        == SESSION_CONTENT_TRIGGER_KEY
    ]
    if len(triggers) != 1 or triggers[0].gate_identity.configuration:
        raise ValueError("Expected one supported Trigger")
    trigger = next(
        (item for item in pipeline.executed_results if item.occurrence == triggers[0]),
        None,
    )
    disposition = RadarGateDisposition.PASS
    if reason == "UNCHANGED":
        if prior.status is not LookupStatus.LEGACY_CONTENT_ONLY:
            raise ValueError("Only legacy UNCHANGED advances")
        disposition = RadarGateDisposition.DROP
    if (
        trigger is None
        or trigger.reason_code != reason
        or trigger.disposition is not disposition
    ):
        raise ValueError("Trigger/predecessor correspondence mismatch")
    if prior.state is not None and _equal(prior.state.to_dict(), state.to_dict()):
        raise ValueError("Ambiguous predecessor/proposal")


@dataclass(frozen=True, slots=True)
class PreparedSourceIntent:
    instrument: CanonicalInstrumentId
    pipeline: RadarPipelineResult
    proposed_state: RadarObservationState
    predecessor: RadarPredecessorWitness
    policy: RadarCandidateEligibilityPolicyIdentity
    schema_version: str = PREPARED_SCHEMA
    identity: SourceRecoveryIdentity = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != PREPARED_SCHEMA
        ):
            raise ValueError("Unsupported Prepared schema")
        for name, expected in (
            ("instrument", CanonicalInstrumentId),
            ("pipeline", RadarPipelineResult),
            ("proposed_state", RadarObservationState),
            ("predecessor", RadarPredecessorWitness),
            ("policy", RadarCandidateEligibilityPolicyIdentity),
        ):
            if type(getattr(self, name)) is not expected:
                raise TypeError("Invalid Prepared field type")
        object.__setattr__(self, "instrument", _instrument(self.instrument.to_dict()))
        object.__setattr__(
            self, "pipeline", _pipeline(_pipeline_payload(self.pipeline))
        )
        object.__setattr__(
            self,
            "proposed_state",
            RadarObservationState.from_dict(self.proposed_state.to_dict()),
        )
        object.__setattr__(self, "predecessor", _witness(self.predecessor.to_dict()))
        object.__setattr__(self, "policy", _policy(self.policy.to_dict()))
        _validate_prepared(self)
        object.__setattr__(
            self,
            "identity",
            SourceRecoveryIdentity(canonical_fingerprint(self._payload())),
        )

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "instrument": self.instrument.to_dict(),
            "pipeline": _pipeline_payload(self.pipeline),
            "proposed_state": self.proposed_state.to_dict(),
            "predecessor": self.predecessor.to_dict(),
            "policy": self.policy.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "source_identity": self.identity.fingerprint}


def _prepared(value: object) -> PreparedSourceIntent:
    raw = _object(
        value,
        "schema_version instrument pipeline proposed_state predecessor policy "
        "source_identity",
    )
    result = PreparedSourceIntent(
        _instrument(raw["instrument"]),
        _pipeline(raw["pipeline"]),
        RadarObservationState.from_dict(raw["proposed_state"]),
        _witness(raw["predecessor"]),
        _policy(raw["policy"]),
        _text(raw["schema_version"]),
    )
    _check_projection(value, result.to_dict())
    return result


@dataclass(frozen=True, slots=True)
class AcceptedSource:
    """Passive durable correspondence; constructing this is not acceptance."""

    source_identity: SourceRecoveryIdentity
    accepted_state: RadarObservationState
    schema_version: str = ACCEPTED_SCHEMA

    def __post_init__(self) -> None:
        _record_header(self.schema_version, ACCEPTED_SCHEMA, self.source_identity)
        if type(self.accepted_state) is not RadarObservationState:
            raise TypeError("Expected accepted state")
        object.__setattr__(
            self,
            "accepted_state",
            RadarObservationState.from_dict(self.accepted_state.to_dict()),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_identity": self.source_identity.fingerprint,
            "accepted_state": self.accepted_state.to_dict(),
        }


def _record_header(
    schema: str, expected: str, identity: SourceRecoveryIdentity
) -> None:
    if type(schema) is not str or schema != expected:
        raise ValueError("Unsupported delivery schema")
    if type(identity) is not SourceRecoveryIdentity:
        raise TypeError("Expected source recovery identity")
    _fingerprint(identity.fingerprint)


def _candidate(value: object) -> RadarCandidate:
    raw = _object(
        value, "schema_version source_observation_state eligibility_policy fingerprint"
    )
    result = RadarCandidate(
        RadarObservationState.from_dict(raw["source_observation_state"]),
        _policy(raw["eligibility_policy"]),
        _text(raw["schema_version"]),
    )
    _check_projection(value, result.to_dict())
    return result


def _decision(value: object) -> RadarCandidateDecision:
    raw = _object(value, "policy reason candidate")
    result = RadarCandidateDecision(
        _policy(raw["policy"]),
        RadarCandidateDecisionReason(_text(raw["reason"])),
        None if raw["candidate"] is None else _candidate(raw["candidate"]),
    )
    _check_projection(value, result.to_dict())
    return result


@dataclass(frozen=True, slots=True)
class CandidateDecisionRecord:
    source_identity: SourceRecoveryIdentity
    decision: RadarCandidateDecision
    schema_version: str = DECISION_SCHEMA

    def __post_init__(self) -> None:
        _record_header(self.schema_version, DECISION_SCHEMA, self.source_identity)
        if type(self.decision) is not RadarCandidateDecision:
            raise TypeError("Expected Candidate decision")
        object.__setattr__(self, "decision", _decision(self.decision.to_dict()))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_identity": self.source_identity.fingerprint,
            "decision": self.decision.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PendingCandidateWork:
    source_identity: SourceRecoveryIdentity
    decision: RadarCandidateDecision
    schema_version: str = PENDING_SCHEMA

    def __post_init__(self) -> None:
        _record_header(self.schema_version, PENDING_SCHEMA, self.source_identity)
        if type(self.decision) is not RadarCandidateDecision:
            raise TypeError("Expected eligible Candidate decision")
        decision = _decision(self.decision.to_dict())
        if not decision.eligible:
            raise ValueError("Pending requires ELIGIBLE")
        object.__setattr__(self, "decision", decision)

    @property
    def candidate_fingerprint(self) -> str:
        assert self.decision.candidate is not None
        return self.decision.candidate.fingerprint

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_identity": self.source_identity.fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
            "decision": self.decision.to_dict(),
        }


type DeliveryRecord = (
    PreparedSourceIntent
    | AcceptedSource
    | CandidateDecisionRecord
    | PendingCandidateWork
)


def _decode_record(value: object) -> DeliveryRecord:
    """Private structural codec. Never returns a trusted application result."""
    try:
        if type(value) is not dict:
            raise TypeError("Expected delivery object")
        schema = value.get("schema_version")
        result: DeliveryRecord
        if schema == PREPARED_SCHEMA:
            result = _prepared(value)
        elif schema == ACCEPTED_SCHEMA:
            raw = _object(value, "schema_version source_identity accepted_state")
            result = AcceptedSource(
                SourceRecoveryIdentity(_text(raw["source_identity"])),
                RadarObservationState.from_dict(raw["accepted_state"]),
                _text(schema),
            )
        elif schema in (DECISION_SCHEMA, PENDING_SCHEMA):
            raw = _object(
                value,
                "schema_version source_identity decision"
                + (" candidate_fingerprint" if schema == PENDING_SCHEMA else ""),
            )
            identity = SourceRecoveryIdentity(_text(raw["source_identity"]))
            decision = _decision(raw["decision"])
            result = (
                CandidateDecisionRecord(identity, decision)
                if schema == DECISION_SCHEMA
                else PendingCandidateWork(identity, decision)
            )
        else:
            raise ValueError("Unsupported delivery schema")
        _check_projection(value, result.to_dict())
        return result
    except Exception as exc:
        raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT) from exc


def _verify_links(
    source: PreparedSourceIntent,
    accepted: AcceptedSource,
    decision: CandidateDecisionRecord | None = None,
    pending: PendingCandidateWork | None = None,
) -> None:
    """Structural links only; does not create a trusted source or run evaluation."""
    if accepted.source_identity != source.identity or not _equal(
        accepted.accepted_state.to_dict(), source.proposed_state.to_dict()
    ):
        raise ValueError("Accepted/source mismatch")
    if decision is not None:
        if (
            decision.source_identity != source.identity
            or decision.decision.policy != source.policy
        ):
            raise ValueError("Decision/source mismatch")
        state = source.proposed_state
        expected_reason = (
            RadarCandidateDecisionReason.NOT_SELECTED
            if source.pipeline.outcome is not RadarPipelineOutcome.SELECTED
            else RadarCandidateDecisionReason.ELIGIBLE
            if state.committed_decision.meaningful_change
            else RadarCandidateDecisionReason.NO_MEANINGFUL_TRANSITION
        )
        if decision.decision.reason is not expected_reason:
            raise ValueError("Decision/source outcome mismatch")
        candidate = decision.decision.candidate
        if candidate is not None and not _equal(
            candidate.source_observation_state.to_dict(), state.to_dict()
        ):
            raise ValueError("Candidate/source mismatch")
    if pending is not None and (
        decision is None
        or pending.source_identity != source.identity
        or not _equal(pending.decision.to_dict(), decision.decision.to_dict())
    ):
        raise ValueError("Pending/decision mismatch")


class RadarCandidateDeliveryCoordinator:
    """Explicit composition only; the Radar seam supplies its checkpoint store.

    Public operations accept execution context or an instrument, never an Accepted
    token to reconstruct as SAVED. A trusted root/producer, not a dataclass or
    digest, supplies historical authority. There is no consumer or provider here.
    """

    def __init__(
        self,
        store: RadarCandidateDeliveryFileStore,
        *,
        policy: RadarCandidateEligibilityPolicyIdentity,
    ) -> None:
        if type(policy) is not RadarCandidateEligibilityPolicyIdentity:
            raise TypeError("Expected Candidate policy")
        self._store = store
        self._policy = _policy(policy.to_dict())

    def _current(
        self,
        instrument: CanonicalInstrumentId,
        checkpoint_store: RadarCheckpointFileStore,
    ) -> RadarPredecessorWitness:
        try:
            witness = RadarPredecessorWitness.from_lookup(
                checkpoint_store.lookup_state(instrument)
            )
            market = (
                witness.legacy_checkpoint
                if witness.state is None
                else witness.state.market_observation
            )
            if market is not None and market.instrument != instrument:
                raise ValueError("Checkpoint instrument mismatch")
            return witness
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.RECOVERY, True) from exc

    def recover(
        self,
        instrument: CanonicalInstrumentId,
        checkpoint_store: RadarCheckpointFileStore,
    ) -> None:
        try:
            sources = self._store.unresolved(instrument)
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.RECOVERY, True) from exc
        for source in sources:
            current = self._current(instrument, checkpoint_store)
            try:
                accepted = self._store.read_accepted(source.identity)
            except Exception as exc:
                raise RadarCandidateDeliveryError(
                    DeliveryFailure.RECOVERY, True
                ) from exc
            proposed_current = current.state is not None and _equal(
                current.state.to_dict(), source.proposed_state.to_dict()
            )
            if accepted is not None:
                if not proposed_current:
                    raise RadarCandidateDeliveryError(DeliveryFailure.RECOVERY, True)
            elif not proposed_current:
                if not _equal(current.to_dict(), source.predecessor.to_dict()):
                    raise RadarCandidateDeliveryError(DeliveryFailure.RECOVERY, True)
                self._save(source, checkpoint_store)
            self._complete(source)

    def publish(
        self,
        instrument: CanonicalInstrumentId,
        pipeline: RadarPipelineResult,
        state: RadarObservationState,
        predecessor: RadarObservationStateLookupResult,
        checkpoint_store: RadarCheckpointFileStore,
    ) -> None:
        try:
            try:
                if self._store.unresolved(instrument):
                    raise ValueError("Unresolved source before publication")
            except Exception as exc:
                raise RadarCandidateDeliveryError(
                    DeliveryFailure.RECOVERY, False
                ) from exc
            try:
                source = PreparedSourceIntent(
                    instrument,
                    pipeline,
                    state,
                    RadarPredecessorWitness.from_lookup(predecessor),
                    self._policy,
                )
            except Exception as exc:
                raise RadarCandidateDeliveryError(
                    DeliveryFailure.INVARIANT, False
                ) from exc
            self._persist(source, DeliveryFailure.PREPARED, False)
            try:
                current = self._current(instrument, checkpoint_store)
                if not _equal(current.to_dict(), source.predecessor.to_dict()):
                    raise ValueError("Predecessor changed before publication")
            except Exception as exc:
                raise RadarCandidateDeliveryError(
                    DeliveryFailure.RECOVERY, False
                ) from exc
            self._save(source, checkpoint_store)
            self._complete(source)
        except RadarCandidateDeliveryError as exc:
            # The seam supplied a completed Pipeline and validated proposal. Keep
            # detached diagnostics even when no Prepared bytes became durable.
            # Recovery before a new evaluation does not pass through this boundary.
            exc.pipeline_result = _pipeline(_pipeline_payload(pipeline))
            exc.prepared_state = RadarObservationState.from_dict(state.to_dict())
            raise

    def _save(
        self, source: PreparedSourceIntent, checkpoint_store: RadarCheckpointFileStore
    ) -> None:
        try:
            checkpoint_store.save_state(source.proposed_state)
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.CHECKPOINT, True) from exc

    def _persist(
        self, record: DeliveryRecord, stage: DeliveryFailure, after_checkpoint: bool
    ) -> None:
        try:
            if isinstance(record, PreparedSourceIntent):
                self._store.publish_prepared(record)
            elif isinstance(record, AcceptedSource):
                self._store.publish_accepted(record)
            elif isinstance(record, CandidateDecisionRecord):
                self._store.publish_decision(record)
            else:
                self._store.publish_pending(record)
        except Exception as exc:
            raise RadarCandidateDeliveryError(
                stage,
                after_checkpoint,
                conflict=isinstance(exc, RadarCandidateDeliveryError) and exc.conflict,
            ) from exc

    def _complete(self, source: PreparedSourceIntent) -> None:
        self._persist(
            AcceptedSource(source.identity, source.proposed_state),
            DeliveryFailure.ACCEPTED,
            True,
        )
        try:
            # Re-read owned durable bytes. No public JSON/dataclass-to-SAVED API.
            retained = self._store.read_prepared(source.instrument, source.identity)
            accepted = self._store.read_accepted(source.identity)
            if retained is None or accepted is None:
                raise ValueError("Missing owned accepted source")
            _check_projection(source.to_dict(), retained.to_dict())
            _verify_links(retained, accepted)
            state = accepted.accepted_state
            application = RadarApplicationResult(
                retained.pipeline,
                RadarCheckpointAdvancement.SAVED,
                state.market_observation,
                state.committed_decision,
                state,
            )
            decision = evaluate_radar_candidate(application, policy=retained.policy)
            record = CandidateDecisionRecord(retained.identity, decision)
        except Exception as exc:
            raise RadarCandidateDeliveryError(DeliveryFailure.INVARIANT, True) from exc
        self._persist(record, DeliveryFailure.DECISION, True)
        if decision.eligible:
            self._persist(
                PendingCandidateWork(source.identity, decision),
                DeliveryFailure.PENDING,
                True,
            )
