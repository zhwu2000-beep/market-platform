"""Single-instrument execution and successful observation advancement."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.checkpoint_store import RadarCheckpointFileStore
from market_platform.radar.context import (
    RadarEvaluationContext,
    RadarFactKey,
)
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.lightweight_observation import (
    EMA8_EMA20_OBSERVATION_LOOKUP,
    RadarLightweightObservationLookupStatus,
)
from market_platform.radar.meaningful_change import (
    RadarMeaningfulChangeDecision,
    evaluate_meaningful_change,
)
from market_platform.radar.observation import (
    RadarObservationCheckpoint,
    RadarObservationLookupResult,
    RadarObservationLookupStatus,
)
from market_platform.radar.observation_state import (
    RadarObservationState,
    RadarObservationStateLookupResult,
    RadarObservationStateLookupStatus,
)
from market_platform.radar.pipeline import RadarPipeline, RadarPipelineResult
from market_platform.radar.resolver import RadarGateImplementationKey, RadarGateResolver
from market_platform.radar.trigger import (
    CURRENT_MARKET_CONTENT_LOOKUP,
    PRIOR_OBSERVATION_LOOKUP,
    SESSION_CONTENT_TRIGGER_KEY,
    RadarCurrentMarketContentLookupStatus,
)


class RadarApplicationConfigurationError(ValueError):
    """Ambiguous Trigger wiring or a caller-owned reserved fact binding."""


class RadarApplicationInvariantError(RuntimeError):
    """A qualifying Trigger PASS did not retain valid current content."""


class RadarObservationPreparationError(RadarApplicationInvariantError):
    """Coordinated preparation failed; the completed Pipeline remains intact."""

    def __init__(self, pipeline_result: RadarPipelineResult) -> None:
        self.pipeline_result = pipeline_result
        super().__init__("Radar observation preparation failed")


class RadarCheckpointAdvancementError(Exception):
    """Persistence failed after execution; the completed result remains intact."""

    def __init__(
        self,
        pipeline_result: RadarPipelineResult,
        prepared_state: RadarObservationState | None = None,
    ) -> None:
        self.pipeline_result = pipeline_result
        self.prepared_state = prepared_state
        super().__init__("Radar checkpoint save failed")


class RadarCheckpointAdvancement(StrEnum):
    NOT_ADVANCED = "NOT_ADVANCED"
    SAVED = "SAVED"


@dataclass(frozen=True, slots=True)
class RadarApplicationResult:
    pipeline_result: RadarPipelineResult
    advancement: RadarCheckpointAdvancement
    saved_checkpoint: RadarObservationCheckpoint | None = None
    meaningful_change_decision: RadarMeaningfulChangeDecision | None = None
    saved_state: RadarObservationState | None = None

    def __post_init__(self) -> None:
        if type(self.pipeline_result) is not RadarPipelineResult:
            raise TypeError("pipeline_result must be a RadarPipelineResult")
        if type(self.advancement) is not RadarCheckpointAdvancement:
            raise TypeError("advancement must be RadarCheckpointAdvancement")
        if self.advancement is RadarCheckpointAdvancement.SAVED:
            if type(self.saved_checkpoint) is not RadarObservationCheckpoint:
                raise ValueError("SAVED requires a checkpoint")
            if type(self.saved_state) is not RadarObservationState:
                raise ValueError("SAVED requires coordinated state")
            if (
                type(self.meaningful_change_decision)
                is not RadarMeaningfulChangeDecision
            ):
                raise ValueError("SAVED requires a meaningful-change decision")
            state = replace(self.saved_state)
            pipeline = self.pipeline_result
            if (
                self.saved_checkpoint != state.market_observation
                or self.meaningful_change_decision != state.committed_decision
                or state.market_observation.instrument != pipeline.instrument
                or state.profile_fingerprint != pipeline.profile.fingerprint
                or state.pipeline_outcome is not pipeline.outcome
                or state.lightweight_observation.as_of != pipeline.as_of
            ):
                raise ValueError(
                    "Saved state must correspond to the actual Pipeline and result"
                )
        elif any(
            value is not None
            for value in (
                self.saved_checkpoint,
                self.meaningful_change_decision,
                self.saved_state,
            )
        ):
            raise ValueError("NOT_ADVANCED forbids checkpoint, decision and state")


class RadarApplicationService:
    """Compose one execution; the caller must prevent overlapping instrument runs."""

    def __init__(
        self,
        resolver: RadarGateResolver,
        checkpoint_store: RadarCheckpointFileStore,
        completion_clock: Callable[[], datetime],
    ) -> None:
        self._resolver = resolver
        self._checkpoint_store = checkpoint_store
        self._completion_clock = completion_clock

    def evaluate(
        self,
        profile: RadarProfile,
        instrument: CanonicalInstrumentId,
        as_of: datetime,
        loaders: Mapping[RadarFactKey[object], Callable[[], object]],
    ) -> RadarApplicationResult:
        if type(profile) is not RadarProfile:
            raise TypeError("profile must be a RadarProfile")
        triggers = [
            occurrence
            for occurrence in profile.gates
            if RadarGateImplementationKey(
                occurrence.gate_identity.gate_id,
                occurrence.gate_identity.behavioral_revision,
                occurrence.gate_identity.configuration_schema,
            )
            == SESSION_CONTENT_TRIGGER_KEY
        ]
        if len(triggers) > 1:
            raise RadarApplicationConfigurationError(
                "Multiple session/content Triggers"
            )
        detached = dict(loaders)
        if any(
            isinstance(key, RadarFactKey)
            and key.fact_id == PRIOR_OBSERVATION_LOOKUP.fact_id
            for key in detached
        ):
            raise RadarApplicationConfigurationError(
                "Prior observation fact is reserved"
            )
        prior: RadarObservationStateLookupResult | None = None

        def prior_state() -> RadarObservationStateLookupResult:
            nonlocal prior
            if prior is None:
                loaded = self._checkpoint_store.lookup_state(instrument)
                if type(loaded) is not RadarObservationStateLookupResult:
                    raise TypeError("Expected a state-aware prior lookup")
                prior = replace(loaded)
            return prior

        def prior_observation() -> RadarObservationLookupResult:
            retained = prior_state()
            if retained.checkpoint is not None:
                return RadarObservationLookupResult(
                    RadarObservationLookupStatus.PRESENT, retained.checkpoint
                )
            return RadarObservationLookupResult(
                RadarObservationLookupStatus(retained.status.value)
            )

        detached[PRIOR_OBSERVATION_LOOKUP] = prior_observation
        resolved = self._resolver.resolve_profile(profile)
        pipeline = RadarPipeline(profile, resolved)
        context = RadarEvaluationContext(instrument, as_of, detached)
        result = pipeline.evaluate(context)
        if (
            result.outcome
            not in (RadarPipelineOutcome.FILTERED, RadarPipelineOutcome.SELECTED)
            or not triggers
        ):
            return RadarApplicationResult(
                result, RadarCheckpointAdvancement.NOT_ADVANCED
            )

        trigger_result = next(
            (
                item
                for item in result.executed_results
                if item.occurrence == triggers[0]
            ),
            None,
        )
        ordinary = trigger_result is not None and (
            trigger_result.disposition is RadarGateDisposition.PASS
            and trigger_result.reason_code
            in {"BASELINE_REQUIRED", "NEW_COMPLETED_SESSION", "MARKET_CONTENT_CHANGED"}
        )
        unchanged = trigger_result is not None and (
            trigger_result.disposition is RadarGateDisposition.DROP
            and trigger_result.reason_code == "UNCHANGED"
            and result.outcome is RadarPipelineOutcome.FILTERED
        )
        if not ordinary and not unchanged:
            return RadarApplicationResult(
                result, RadarCheckpointAdvancement.NOT_ADVANCED
            )

        try:
            retained = prior_state()
            if not ordinary and (
                retained.status
                is not RadarObservationStateLookupStatus.LEGACY_CONTENT_ONLY
            ):
                return RadarApplicationResult(
                    result, RadarCheckpointAdvancement.NOT_ADVANCED
                )
            assert trigger_result is not None
            state = self._prepare_state(
                context, result, retained, trigger_result.reason_code
            )
            # Validate every return-value invariant before the authoritative commit.
            application_result = RadarApplicationResult(
                result,
                RadarCheckpointAdvancement.SAVED,
                state.market_observation,
                state.committed_decision,
                state,
            )
        except Exception as exc:
            raise RadarObservationPreparationError(result) from exc
        try:
            self._checkpoint_store.save_state(state)
        except Exception as exc:
            raise RadarCheckpointAdvancementError(result, state) from exc
        return application_result

    def _prepare_state(
        self,
        context: RadarEvaluationContext,
        result: RadarPipelineResult,
        prior: RadarObservationStateLookupResult,
        trigger_reason: str,
    ) -> RadarObservationState:
        current = context.get_fact(CURRENT_MARKET_CONTENT_LOOKUP)
        replace(current)
        content = current.content
        if (
            current.status is not RadarCurrentMarketContentLookupStatus.PRESENT
            or content is None
            or content.instrument != result.instrument
        ):
            raise ValueError("Advancement requires corresponding current content")
        replace(content)
        if prior.status is RadarObservationStateLookupStatus.UNAVAILABLE:
            raise ValueError("Unavailable prior state cannot advance")
        if prior.state is not None:
            replace(prior.state)
        checkpoint = prior.checkpoint
        expected_reason = "BASELINE_REQUIRED"
        if checkpoint is not None:
            RadarObservationCheckpoint.from_dict(checkpoint.to_dict())
            if (
                checkpoint.instrument != result.instrument
                or checkpoint.observed_completed_session > content.completed_session
            ):
                raise ValueError("Prior market correspondence mismatch")
            if checkpoint.observed_completed_session < content.completed_session:
                expected_reason = "NEW_COMPLETED_SESSION"
            else:
                if checkpoint.content_scope != content.content_scope:
                    raise ValueError("Same-session content scope mismatch")
                expected_reason = (
                    "UNCHANGED"
                    if checkpoint.normalized_market_content_identity
                    == content.normalized_market_content_identity
                    else "MARKET_CONTENT_CHANGED"
                )
        if trigger_reason != expected_reason:
            raise ValueError(
                "Trigger result contradicts retained market correspondence"
            )
        lookup = context.get_fact(EMA8_EMA20_OBSERVATION_LOOKUP)
        replace(lookup)
        observation = lookup.observation
        if (
            lookup.status is not RadarLightweightObservationLookupStatus.PRESENT
            or observation is None
            or observation.as_of != result.as_of
        ):
            raise ValueError("Advancement requires a current lightweight observation")
        decision = evaluate_meaningful_change(
            None if prior.state is None else prior.state.lightweight_observation,
            observation,
        )
        return RadarObservationState(
            market_observation=RadarObservationCheckpoint(
                instrument=result.instrument,
                observed_completed_session=content.completed_session,
                normalized_market_content_identity=content.normalized_market_content_identity,
                observed_at=self._completion_clock(),
                content_scope=content.content_scope,
            ),
            lightweight_observation=observation,
            committed_decision=decision,
            profile_fingerprint=result.profile.fingerprint,
            pipeline_outcome=result.outcome,
        )
