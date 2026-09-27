"""Pure ADR0049 comparisons; no selection, persistence or research authority.

Operands must already have passed production calendar/acquisition acceptance.
Structural validation here cannot prove a 250-session window or its cutoff.
"""

from dataclasses import dataclass, replace
from enum import StrEnum

from market_platform.radar.lightweight_observation import RadarLightweightObservation

MEANINGFUL_CHANGE_POLICY_ID = "ema8_ema20_relation_transition"
MEANINGFUL_CHANGE_BEHAVIORAL_REVISION = "1"
MEANINGFUL_CHANGE_DECISION_SCHEMA = "radar_meaningful_change_decision/v1"


@dataclass(frozen=True, slots=True)
class RadarMeaningfulChangePolicyIdentity:
    policy_id: str = MEANINGFUL_CHANGE_POLICY_ID
    behavioral_revision: str = MEANINGFUL_CHANGE_BEHAVIORAL_REVISION
    decision_schema: str = MEANINGFUL_CHANGE_DECISION_SCHEMA

    def __post_init__(self) -> None:
        for name, expected in (
            ("policy_id", MEANINGFUL_CHANGE_POLICY_ID),
            ("behavioral_revision", MEANINGFUL_CHANGE_BEHAVIORAL_REVISION),
            ("decision_schema", MEANINGFUL_CHANGE_DECISION_SCHEMA),
        ):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(f"{name} must be a string")
            if value != expected:
                raise ValueError("Unsupported meaningful-change policy")

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "behavioral_revision": self.behavioral_revision,
            "decision_schema": self.decision_schema,
        }


class RadarMeaningfulChangeClassification(StrEnum):
    BASELINE_INITIALIZED = "BASELINE_INITIALIZED"
    INCOMPARABLE_BASELINE_INITIALIZED = "INCOMPARABLE_BASELINE_INITIALIZED"
    STATE_UNCHANGED = "STATE_UNCHANGED"
    STATE_TRANSITION = "STATE_TRANSITION"


class RadarMeaningfulChangeReason(StrEnum):
    BASELINE_INITIALIZED = "BASELINE_INITIALIZED"
    INCOMPARABLE_BASELINE_INITIALIZED = "INCOMPARABLE_BASELINE_INITIALIZED"
    STATE_UNCHANGED = "STATE_UNCHANGED"
    NEW_SESSION_STATE_TRANSITION = "NEW_SESSION_STATE_TRANSITION"
    CORRECTED_CONTENT_STATE_TRANSITION = "CORRECTED_CONTENT_STATE_TRANSITION"


class RadarComparisonKind(StrEnum):
    MISSING_PRIOR = "MISSING_PRIOR"
    INCOMPATIBLE_PRIOR = "INCOMPATIBLE_PRIOR"
    SAME_CONTENT = "SAME_CONTENT"
    NEW_SESSION = "NEW_SESSION"
    CORRECTED_CONTENT = "CORRECTED_CONTENT"


class RadarObservationIncompatibility(StrEnum):
    DEFINITION_MISMATCH = "DEFINITION_MISMATCH"
    CALCULATION_REVISION_MISMATCH = "CALCULATION_REVISION_MISMATCH"
    OBSERVATION_SCHEMA_MISMATCH = "OBSERVATION_SCHEMA_MISMATCH"
    # Reserved: RadarMarketContentScope currently admits only valid schema v1.
    # A future supported schema requires explicit comparison handling. Unknown
    # or malformed scopes are errors, never this incompatibility category.
    CONTENT_SCOPE_SEMANTICS_MISMATCH = "CONTENT_SCOPE_SEMANTICS_MISMATCH"


@dataclass(frozen=True, slots=True)
class RadarMeaningfulChangeDecision:
    prior: RadarLightweightObservation | None
    current: RadarLightweightObservation
    policy: RadarMeaningfulChangePolicyIdentity
    classification: RadarMeaningfulChangeClassification
    reason: RadarMeaningfulChangeReason
    comparison_kind: RadarComparisonKind
    incompatibilities: tuple[RadarObservationIncompatibility, ...] = ()

    def __post_init__(self) -> None:
        for name, expected_type in (
            ("policy", RadarMeaningfulChangePolicyIdentity),
            ("classification", RadarMeaningfulChangeClassification),
            ("reason", RadarMeaningfulChangeReason),
            ("comparison_kind", RadarComparisonKind),
        ):
            if type(getattr(self, name)) is not expected_type:
                raise TypeError(f"{name} must be {expected_type.__name__}")
        replace(self.policy)
        if type(self.incompatibilities) is not tuple or any(
            type(item) is not RadarObservationIncompatibility
            for item in self.incompatibilities
        ):
            raise TypeError("incompatibilities must be a tuple of bounded categories")
        actual = (
            self.classification,
            self.reason,
            self.comparison_kind,
            self.incompatibilities,
        )
        if actual != _classify(self.prior, self.current):
            raise ValueError(
                "Decision contradicts observation correspondence or policy"
            )

    @property
    def meaningful_change(self) -> bool:
        return (
            self.classification is RadarMeaningfulChangeClassification.STATE_TRANSITION
        )

    def to_dict(self) -> dict[str, object]:
        """Detached passive projection, not an accepted or persisted decision."""
        return {
            "prior": None if self.prior is None else self.prior.to_dict(),
            "current": self.current.to_dict(),
            "policy": self.policy.to_dict(),
            "classification": self.classification.value,
            "reason": self.reason.value,
            "comparison_kind": self.comparison_kind.value,
            "incompatibilities": [item.value for item in self.incompatibilities],
            "meaningful_change": self.meaningful_change,
        }


def _classify(
    prior: RadarLightweightObservation | None,
    current: RadarLightweightObservation,
) -> tuple[
    RadarMeaningfulChangeClassification,
    RadarMeaningfulChangeReason,
    RadarComparisonKind,
    tuple[RadarObservationIncompatibility, ...],
]:
    if type(current) is not RadarLightweightObservation:
        raise TypeError("current must be RadarLightweightObservation")
    replace(current)
    if prior is None:
        return (
            RadarMeaningfulChangeClassification.BASELINE_INITIALIZED,
            RadarMeaningfulChangeReason.BASELINE_INITIALIZED,
            RadarComparisonKind.MISSING_PRIOR,
            (),
        )
    if type(prior) is not RadarLightweightObservation:
        raise TypeError("prior must be RadarLightweightObservation or None")
    replace(prior)
    if prior.instrument != current.instrument:
        raise ValueError("Observation instrument mismatch")
    if current.completed_session < prior.completed_session:
        raise ValueError("Observation session order is reversed")
    incompatibilities = tuple(
        category
        for field, category in (
            ("definition_id", RadarObservationIncompatibility.DEFINITION_MISMATCH),
            (
                "calculation_revision",
                RadarObservationIncompatibility.CALCULATION_REVISION_MISMATCH,
            ),
            (
                "observation_schema",
                RadarObservationIncompatibility.OBSERVATION_SCHEMA_MISMATCH,
            ),
        )
        if getattr(prior, field) != getattr(current, field)
    )
    if incompatibilities:
        return (
            RadarMeaningfulChangeClassification.INCOMPARABLE_BASELINE_INITIALIZED,
            RadarMeaningfulChangeReason.INCOMPARABLE_BASELINE_INITIALIZED,
            RadarComparisonKind.INCOMPATIBLE_PRIOR,
            incompatibilities,
        )
    if current.completed_session > prior.completed_session:
        kind = RadarComparisonKind.NEW_SESSION
        transition = RadarMeaningfulChangeReason.NEW_SESSION_STATE_TRANSITION
    else:
        if current.content_scope != prior.content_scope:
            raise ValueError("Same-session observations require equal concrete scope")
        if (
            current.normalized_market_content_identity
            == prior.normalized_market_content_identity
        ):
            if current.relation is not prior.relation:
                raise ValueError(
                    "Identical content with changed relation is incoherent"
                )
            kind = RadarComparisonKind.SAME_CONTENT
        else:
            kind = RadarComparisonKind.CORRECTED_CONTENT
        transition = RadarMeaningfulChangeReason.CORRECTED_CONTENT_STATE_TRANSITION
    if current.relation is prior.relation:
        return (
            RadarMeaningfulChangeClassification.STATE_UNCHANGED,
            RadarMeaningfulChangeReason.STATE_UNCHANGED,
            kind,
            (),
        )
    return (
        RadarMeaningfulChangeClassification.STATE_TRANSITION,
        transition,
        kind,
        (),
    )


def evaluate_meaningful_change(
    prior: RadarLightweightObservation | None,
    current: RadarLightweightObservation,
) -> RadarMeaningfulChangeDecision:
    """Compare accepted-input correspondence, without granting acceptance itself."""
    classification, reason, kind, incompatibilities = _classify(prior, current)
    return RadarMeaningfulChangeDecision(
        prior,
        current,
        RadarMeaningfulChangePolicyIdentity(),
        classification,
        reason,
        kind,
        incompatibilities,
    )
