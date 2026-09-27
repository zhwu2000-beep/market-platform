"""Passive coordinated observation state; no advancement or research authority."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from market_platform.radar.core import RadarPipelineOutcome
from market_platform.radar.lightweight_observation import RadarLightweightObservation
from market_platform.radar.meaningful_change import (
    RadarComparisonKind,
    RadarMeaningfulChangeClassification,
    RadarMeaningfulChangeDecision,
    RadarMeaningfulChangePolicyIdentity,
    RadarMeaningfulChangeReason,
    RadarObservationIncompatibility,
)
from market_platform.radar.observation import (
    RadarObservationCheckpoint,
    RadarObservationStateError,
)

RADAR_OBSERVATION_STATE_SCHEMA = "radar_observation_state/v1"


def _object(value: object, fields: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise RadarObservationStateError("Expected exactly the required state fields")
    return value


def _text(value: object) -> str:
    if type(value) is not str:
        raise RadarObservationStateError("Expected a plain string")
    return value


def _decision(value: object) -> RadarMeaningfulChangeDecision:
    # The decision exposes a projection and validated constructor, but no decoder.
    raw = _object(
        value,
        {
            "prior",
            "current",
            "policy",
            "classification",
            "reason",
            "comparison_kind",
            "incompatibilities",
            "meaningful_change",
        },
    )
    policy = _object(
        raw["policy"],
        {
            "policy_id",
            "behavioral_revision",
            "decision_schema",
        },
    )
    categories = raw["incompatibilities"]
    if type(categories) is not list:
        raise RadarObservationStateError("incompatibilities must be a list")
    result = RadarMeaningfulChangeDecision(
        prior=(
            None
            if raw["prior"] is None
            else RadarLightweightObservation.from_dict(raw["prior"])
        ),
        current=RadarLightweightObservation.from_dict(raw["current"]),
        policy=RadarMeaningfulChangePolicyIdentity(
            _text(policy["policy_id"]),
            _text(policy["behavioral_revision"]),
            _text(policy["decision_schema"]),
        ),
        classification=RadarMeaningfulChangeClassification(
            _text(raw["classification"])
        ),
        reason=RadarMeaningfulChangeReason(_text(raw["reason"])),
        comparison_kind=RadarComparisonKind(_text(raw["comparison_kind"])),
        incompatibilities=tuple(
            RadarObservationIncompatibility(_text(v)) for v in categories
        ),
    )
    if (
        type(raw["meaningful_change"]) is not bool
        or raw["meaningful_change"] is not result.meaningful_change
    ):
        raise RadarObservationStateError("Contradictory meaningful_change")
    return result


@dataclass(frozen=True, slots=True)
class RadarObservationState:
    """One complete accepted record with bounded evaluation correspondence.

    The caller supplies the actual Profile fingerprint and completed outcome.
    Structural validation cannot prove execution or a qualifying Trigger PASS;
    advancement eligibility remains application-owned.
    """

    market_observation: RadarObservationCheckpoint
    lightweight_observation: RadarLightweightObservation
    committed_decision: RadarMeaningfulChangeDecision
    profile_fingerprint: str
    pipeline_outcome: RadarPipelineOutcome
    schema_version: str = RADAR_OBSERVATION_STATE_SCHEMA

    def __post_init__(self) -> None:
        for name, expected in (
            ("market_observation", RadarObservationCheckpoint),
            ("lightweight_observation", RadarLightweightObservation),
            ("committed_decision", RadarMeaningfulChangeDecision),
            ("pipeline_outcome", RadarPipelineOutcome),
        ):
            if type(getattr(self, name)) is not expected:
                raise RadarObservationStateError(f"{name} must be {expected.__name__}")
        if _text(self.schema_version) != RADAR_OBSERVATION_STATE_SCHEMA:
            raise RadarObservationStateError("Unsupported observation state schema")
        if (
            re.fullmatch(r"sha256:[0-9a-f]{64}", _text(self.profile_fingerprint))
            is None
        ):
            raise RadarObservationStateError("Invalid Profile fingerprint")
        if self.pipeline_outcome not in (
            RadarPipelineOutcome.SELECTED,
            RadarPipelineOutcome.FILTERED,
        ):
            raise RadarObservationStateError("Only SELECTED/FILTERED can be committed")
        try:
            RadarObservationCheckpoint.from_dict(self.market_observation.to_dict())
            replace(self.lightweight_observation)
            replace(self.committed_decision)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RadarObservationStateError(
                f"Invalid nested observation state: {exc}"
            ) from exc
        market, light = self.market_observation, self.lightweight_observation
        for market_field, light_field in (
            ("instrument", "instrument"),
            ("observed_completed_session", "completed_session"),
            (
                "normalized_market_content_identity",
                "normalized_market_content_identity",
            ),
            ("content_scope", "content_scope"),
        ):
            if getattr(market, market_field) != getattr(light, light_field):
                raise RadarObservationStateError(f"Observation {market_field} mismatch")
        if self.committed_decision.current != light:
            raise RadarObservationStateError("Decision current observation mismatch")

    def to_dict(self) -> dict[str, object]:
        """Detached deterministic JSON-safe projection."""
        return {
            "schema_version": self.schema_version,
            "market_observation": self.market_observation.to_dict(),
            "lightweight_observation": self.lightweight_observation.to_dict(),
            "committed_decision": self.committed_decision.to_dict(),
            "profile_fingerprint": self.profile_fingerprint,
            "pipeline_outcome": self.pipeline_outcome.value,
        }

    @classmethod
    def from_dict(cls, value: object) -> RadarObservationState:
        """Reject incomplete, unknown or contradictory state, including nested data."""
        raw = _object(
            value,
            {
                "schema_version",
                "market_observation",
                "lightweight_observation",
                "committed_decision",
                "profile_fingerprint",
                "pipeline_outcome",
            },
        )
        try:
            return cls(
                RadarObservationCheckpoint.from_dict(raw["market_observation"]),
                RadarLightweightObservation.from_dict(raw["lightweight_observation"]),
                _decision(raw["committed_decision"]),
                _text(raw["profile_fingerprint"]),
                RadarPipelineOutcome(_text(raw["pipeline_outcome"])),
                _text(raw["schema_version"]),
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise RadarObservationStateError(
                f"Malformed observation state: {exc}"
            ) from exc


class RadarObservationStateLookupStatus(StrEnum):
    ABSENT = "ABSENT"
    UNAVAILABLE = "UNAVAILABLE"
    LEGACY_CONTENT_ONLY = "LEGACY_CONTENT_ONLY"
    PRESENT_COMPLETE_STATE = "PRESENT_COMPLETE_STATE"


@dataclass(frozen=True, slots=True)
class RadarObservationStateLookupResult:
    """Legacy content is retained explicitly, never interpreted as technical state."""

    status: RadarObservationStateLookupStatus
    legacy_checkpoint: RadarObservationCheckpoint | None = None
    state: RadarObservationState | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not RadarObservationStateLookupStatus:
            raise RadarObservationStateError("Invalid state lookup status")
        if self.status is RadarObservationStateLookupStatus.LEGACY_CONTENT_ONLY:
            valid = (
                type(self.legacy_checkpoint) is RadarObservationCheckpoint
                and self.state is None
            )
        elif self.status is RadarObservationStateLookupStatus.PRESENT_COMPLETE_STATE:
            valid = (
                type(self.state) is RadarObservationState
                and self.legacy_checkpoint is None
            )
        else:
            valid = self.state is None and self.legacy_checkpoint is None
        if not valid:
            raise RadarObservationStateError("State lookup payload contradicts status")

    @property
    def checkpoint(self) -> RadarObservationCheckpoint | None:
        """Market-only projection for callers that do not consume technical state."""
        return (
            self.state.market_observation
            if self.state is not None
            else self.legacy_checkpoint
        )
