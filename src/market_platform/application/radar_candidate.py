"""Passive eligibility correspondence, never execution or bearer authority.

The evaluator requires a trusted application-owned result. Structural validation
cannot authenticate a coherent fabrication or prove persistence and delivery.
"""

from dataclasses import dataclass, field, replace
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.radar.application import (
    RadarApplicationResult,
    RadarCheckpointAdvancement,
)
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarGateOccurrence,
    RadarPipelineOutcome,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_CALCULATION_REVISION,
    EMA8_EMA20_OBSERVATION_DEFINITION_ID,
    EMA8_EMA20_OBSERVATION_SCHEMA,
)
from market_platform.radar.meaningful_change import RadarMeaningfulChangeClassification
from market_platform.radar.observation_state import RadarObservationState
from market_platform.radar.pipeline import RadarPipelineResult
from market_platform.radar.resolver import RadarGateImplementationKey
from market_platform.radar.trigger import SESSION_CONTENT_TRIGGER_KEY

RADAR_CANDIDATE_SCHEMA = "radar_candidate/v1"
RADAR_CANDIDATE_ELIGIBILITY_POLICY_ID = "selected_meaningful_transition"
RADAR_CANDIDATE_ELIGIBILITY_POLICY_REVISION = "1"
RADAR_CANDIDATE_ELIGIBILITY_POLICY_SCHEMA = "radar_candidate_eligibility_policy/v1"


@dataclass(frozen=True, slots=True)
class RadarCandidateEligibilityPolicyIdentity:
    policy_id: str = RADAR_CANDIDATE_ELIGIBILITY_POLICY_ID
    behavioral_revision: str = RADAR_CANDIDATE_ELIGIBILITY_POLICY_REVISION
    policy_schema: str = RADAR_CANDIDATE_ELIGIBILITY_POLICY_SCHEMA

    def __post_init__(self) -> None:
        for name, expected in (
            ("policy_id", RADAR_CANDIDATE_ELIGIBILITY_POLICY_ID),
            ("behavioral_revision", RADAR_CANDIDATE_ELIGIBILITY_POLICY_REVISION),
            ("policy_schema", RADAR_CANDIDATE_ELIGIBILITY_POLICY_SCHEMA),
        ):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(f"{name} must be a string")
            if value != expected:
                raise ValueError("Unsupported Candidate eligibility policy")

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "behavioral_revision": self.behavioral_revision,
            "policy_schema": self.policy_schema,
        }


def _policy(
    value: RadarCandidateEligibilityPolicyIdentity,
) -> RadarCandidateEligibilityPolicyIdentity:
    if type(value) is not RadarCandidateEligibilityPolicyIdentity:
        raise TypeError("policy must be RadarCandidateEligibilityPolicyIdentity")
    return replace(value)


class RadarCandidateDecisionReason(StrEnum):
    NOT_SELECTED = "NOT_SELECTED"
    NOT_ADVANCED = "NOT_ADVANCED"
    NO_MEANINGFUL_TRANSITION = "NO_MEANINGFUL_TRANSITION"
    ELIGIBLE = "ELIGIBLE"


@dataclass(frozen=True, slots=True)
class RadarCandidate:
    source_observation_state: RadarObservationState
    eligibility_policy: RadarCandidateEligibilityPolicyIdentity
    schema_version: str = RADAR_CANDIDATE_SCHEMA
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.source_observation_state) is not RadarObservationState:
            raise TypeError("source_observation_state must be RadarObservationState")
        if type(self.schema_version) is not str:
            raise TypeError("schema_version must be a string")
        if self.schema_version != RADAR_CANDIDATE_SCHEMA:
            raise ValueError("Unsupported Candidate schema")
        state = replace(self.source_observation_state)
        state = RadarObservationState.from_dict(state.to_dict())
        if not _state_is_eligible(state):
            raise ValueError(
                "Candidate requires a SELECTED meaningful STATE_TRANSITION"
            )
        object.__setattr__(self, "source_observation_state", state)
        object.__setattr__(self, "eligibility_policy", _policy(self.eligibility_policy))
        object.__setattr__(self, "fingerprint", canonical_fingerprint(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_observation_state": self.source_observation_state.to_dict(),
            "eligibility_policy": self.eligibility_policy.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class RadarCandidateDecision:
    policy: RadarCandidateEligibilityPolicyIdentity
    reason: RadarCandidateDecisionReason
    candidate: RadarCandidate | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", _policy(self.policy))
        if type(self.reason) is not RadarCandidateDecisionReason:
            raise TypeError("reason must be RadarCandidateDecisionReason")
        if self.reason is RadarCandidateDecisionReason.ELIGIBLE:
            if type(self.candidate) is not RadarCandidate:
                raise ValueError("ELIGIBLE requires a RadarCandidate")
            candidate = replace(self.candidate)
            if candidate.eligibility_policy != self.policy:
                raise ValueError("Candidate policy must match decision policy")
            object.__setattr__(self, "candidate", candidate)
        elif self.candidate is not None:
            raise ValueError("Negative decisions forbid a Candidate")

    @property
    def eligible(self) -> bool:
        return self.candidate is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy.to_dict(),
            "reason": self.reason.value,
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
        }


def _occurrence(value: RadarGateOccurrence) -> RadarGateOccurrence:
    if type(value) is not RadarGateOccurrence:
        raise TypeError("Expected a RadarGateOccurrence")
    occurrence = replace(value)
    identity = replace(occurrence.gate_identity)
    if identity != occurrence.gate_identity:
        raise ValueError("Gate identity fingerprint/schema mismatch")
    return replace(occurrence, gate_identity=identity)


def _revalidate(application: RadarApplicationResult) -> RadarApplicationResult:
    if type(application) is not RadarApplicationResult:
        raise TypeError("application_result must be RadarApplicationResult")
    # Re-run existing contracts before inspecting derived outcomes or precedence.
    checked = replace(application)
    pipeline = replace(checked.pipeline_result)
    profile = replace(pipeline.profile)
    profile = replace(profile, gates=tuple(_occurrence(g) for g in profile.gates))
    if profile != pipeline.profile:
        raise ValueError("Profile fingerprint/schema mismatch")
    results = tuple(
        replace(result, occurrence=_occurrence(result.occurrence))
        for result in pipeline.executed_results
    )
    failure = pipeline.failure
    if failure is not None:
        failure = replace(failure, occurrence=_occurrence(failure.occurrence))
    pipeline = replace(
        pipeline,
        profile=profile,
        instrument=replace(pipeline.instrument),
        executed_results=results,
        failure=failure,
    )
    state = checked.saved_state
    if state is not None:
        state = RadarObservationState.from_dict(state.to_dict())
    return replace(checked, pipeline_result=pipeline, saved_state=state)


def _state_is_eligible(state: RadarObservationState) -> bool:
    """Validate current semantics and test eligibility of an already decoded state.

    This establishes no application advancement, Trigger, commit or delivery facts.
    """
    current = state.lightweight_observation
    for name, expected in (
        ("definition_id", EMA8_EMA20_OBSERVATION_DEFINITION_ID),
        ("calculation_revision", EMA8_EMA20_CALCULATION_REVISION),
        ("observation_schema", EMA8_EMA20_OBSERVATION_SCHEMA),
    ):
        if getattr(current, name) != expected:
            raise ValueError("Unsupported current observation semantics")
    # State decoding already validates scope and applied MeaningfulChange policy.
    decision = state.committed_decision
    return (
        state.pipeline_outcome is RadarPipelineOutcome.SELECTED
        and decision.classification
        is RadarMeaningfulChangeClassification.STATE_TRANSITION
        and decision.meaningful_change
    )


def _validate_saved_source(
    pipeline: RadarPipelineResult, state: RadarObservationState
) -> None:
    # Unsupported current semantics must raise even for ordinary negative results.
    _state_is_eligible(state)
    current = state.lightweight_observation
    triggers = [
        occurrence
        for occurrence in pipeline.profile.gates
        if RadarGateImplementationKey(
            occurrence.gate_identity.gate_id,
            occurrence.gate_identity.behavioral_revision,
            occurrence.gate_identity.configuration_schema,
        )
        == SESSION_CONTENT_TRIGGER_KEY
    ]
    if len(triggers) != 1 or triggers[0].gate_identity.configuration:
        raise ValueError("SAVED requires exactly one supported Session/Content Trigger")
    trigger = next(
        (r for r in pipeline.executed_results if r.occurrence == triggers[0]), None
    )
    if trigger is None:
        raise ValueError("SAVED requires an actually executed Trigger")
    decision = state.committed_decision
    prior = decision.prior
    if (
        trigger.disposition is RadarGateDisposition.DROP
        and trigger.reason_code == "UNCHANGED"
        and pipeline.outcome is RadarPipelineOutcome.FILTERED
        and decision.classification
        is RadarMeaningfulChangeClassification.BASELINE_INITIALIZED
        and not decision.meaningful_change
        and prior is None
    ):
        # Legacy content-only bootstrap retains no prior technical observation.
        # This shape cannot authenticate the historical checkpoint's existence.
        return
    if (
        trigger.disposition is not RadarGateDisposition.PASS
        or trigger.reason_code
        not in {
            "BASELINE_REQUIRED",
            "NEW_COMPLETED_SESSION",
            "MARKET_CONTENT_CHANGED",
        }
    ):
        raise ValueError("SAVED requires a qualifying Trigger PASS")
    # No technical prior does not imply no market predecessor: legacy checkpoints
    # retain market content only. The trusted application's Trigger is provenance.
    if prior is not None:
        if trigger.reason_code == "BASELINE_REQUIRED":
            raise ValueError("BASELINE_REQUIRED contradicts retained prior observation")
        # Even incompatible prior semantics retain market comparison provenance.
        if current.completed_session > prior.completed_session:
            expected_reason = "NEW_COMPLETED_SESSION"
        else:
            if (
                current.content_scope != prior.content_scope
                or current.normalized_market_content_identity
                == prior.normalized_market_content_identity
            ):
                raise ValueError("Trigger contradicts prior/current market content")
            expected_reason = "MARKET_CONTENT_CHANGED"
        if trigger.reason_code != expected_reason:
            raise ValueError("Trigger contradicts prior/current completed sessions")


def evaluate_radar_candidate(
    application_result: RadarApplicationResult,
    *,
    policy: RadarCandidateEligibilityPolicyIdentity,
) -> RadarCandidateDecision:
    """Validate a trusted result and record eligibility without performing I/O."""
    policy = _policy(policy)
    application = _revalidate(application_result)
    pipeline = application.pipeline_result
    state = application.saved_state
    if state is not None:
        _validate_saved_source(pipeline, state)
    if pipeline.outcome is not RadarPipelineOutcome.SELECTED:
        reason = RadarCandidateDecisionReason.NOT_SELECTED
    elif application.advancement is not RadarCheckpointAdvancement.SAVED:
        reason = RadarCandidateDecisionReason.NOT_ADVANCED
    else:
        assert state is not None
        if _state_is_eligible(state):
            return RadarCandidateDecision(
                policy,
                RadarCandidateDecisionReason.ELIGIBLE,
                RadarCandidate(state, policy),
            )
        reason = RadarCandidateDecisionReason.NO_MEANINGFUL_TRANSITION
    return RadarCandidateDecision(policy, reason, None)
