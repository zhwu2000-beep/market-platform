"""Single-instrument execution and successful observation advancement."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.radar.checkpoint_store import (
    RadarCheckpointFileStore,
    RadarCheckpointStoreError,
)
from market_platform.radar.context import (
    RadarContextError,
    RadarEvaluationContext,
    RadarFactKey,
)
from market_platform.radar.core import (
    RadarGateDisposition,
    RadarPipelineOutcome,
    RadarProfile,
)
from market_platform.radar.observation import RadarObservationCheckpoint
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


class RadarCheckpointAdvancementError(Exception):
    """Persistence failed after execution; the completed result remains intact."""

    def __init__(self, pipeline_result: RadarPipelineResult) -> None:
        self.pipeline_result = pipeline_result
        super().__init__("Radar checkpoint save failed")


class RadarCheckpointAdvancement(StrEnum):
    NOT_ADVANCED = "NOT_ADVANCED"
    SAVED = "SAVED"


@dataclass(frozen=True, slots=True)
class RadarApplicationResult:
    pipeline_result: RadarPipelineResult
    advancement: RadarCheckpointAdvancement
    saved_checkpoint: RadarObservationCheckpoint | None = None

    def __post_init__(self) -> None:
        if type(self.pipeline_result) is not RadarPipelineResult:
            raise TypeError("pipeline_result must be a RadarPipelineResult")
        if type(self.advancement) is not RadarCheckpointAdvancement:
            raise TypeError("advancement must be RadarCheckpointAdvancement")
        if self.advancement is RadarCheckpointAdvancement.SAVED:
            if type(self.saved_checkpoint) is not RadarObservationCheckpoint:
                raise ValueError("SAVED requires a checkpoint")
        elif self.saved_checkpoint is not None:
            raise ValueError("NOT_ADVANCED forbids a checkpoint")


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
        detached[PRIOR_OBSERVATION_LOOKUP] = lambda: self._checkpoint_store.lookup(
            instrument
        )
        resolved = self._resolver.resolve_profile(profile)
        pipeline = RadarPipeline(profile, resolved)
        context = RadarEvaluationContext(instrument, as_of, detached)
        result = pipeline.evaluate(context)
        if (
            result.outcome
            not in (RadarPipelineOutcome.FILTERED, RadarPipelineOutcome.SELECTED)
            or not triggers
            or not any(
                gate_result.occurrence == triggers[0]
                and gate_result.disposition is RadarGateDisposition.PASS
                and gate_result.reason_code
                in {
                    "BASELINE_REQUIRED",
                    "NEW_COMPLETED_SESSION",
                    "MARKET_CONTENT_CHANGED",
                }
                for gate_result in result.executed_results
            )
        ):
            return RadarApplicationResult(
                result, RadarCheckpointAdvancement.NOT_ADVANCED
            )

        try:
            current = context.get_fact(CURRENT_MARKET_CONTENT_LOOKUP)
        except RadarContextError as exc:
            raise RadarApplicationInvariantError(
                "Trigger PASS requires a valid current-content fact"
            ) from exc
        content = current.content
        if (
            current.status is not RadarCurrentMarketContentLookupStatus.PRESENT
            or content is None
            or content.instrument != context.instrument
        ):
            raise RadarApplicationInvariantError(
                "Trigger PASS requires current content"
            )
        checkpoint = RadarObservationCheckpoint(
            instrument=context.instrument,
            observed_completed_session=content.completed_session,
            normalized_market_content_identity=content.normalized_market_content_identity,
            observed_at=self._completion_clock(),
            content_scope=content.content_scope,
        )
        try:
            self._checkpoint_store.save(checkpoint)
        except (OSError, RadarCheckpointStoreError) as exc:
            raise RadarCheckpointAdvancementError(result) from exc
        return RadarApplicationResult(
            result, RadarCheckpointAdvancement.SAVED, checkpoint
        )
