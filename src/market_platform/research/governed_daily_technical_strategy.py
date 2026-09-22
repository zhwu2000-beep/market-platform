"""Deterministic descriptive Strategy content; selectors confer no authority.

Content-only validation cannot authenticate either result envelope's membership.
The application must authenticate the selected Assessment and its bound
Interpretation separately. No descriptive mode expresses trading intent.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import classic_daily_technical as classic
from market_platform.research import (
    governed_daily_technical_assessment as assessment_domain,
)
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessmentOutcome,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
)
from market_platform.research.daily_technical_strategy import _ALLOWED_MODE_RULE_PAIRS
from market_platform.research.governed_daily_technical_assessment import (
    GovernedDailyTechnicalAssessment,
)
from market_platform.research.governed_daily_technical_interpretation import (
    GovernedDailyTechnicalInterpretation,
    GovernedTechnicalArtifactReference,
    _choice,
    _copy_canonical,
    _fingerprint,
)

GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA = "governed_daily_technical_strategy/v1"
_POLICY_FINGERPRINT = (
    "sha256:acbdd8c9ac7ba7d336f5f5e74b7484b05d0fc15b3a6f24bc81288d1fc8ea817e"
)


def _detach[T](value: T, exact_type: type[T]) -> T:
    """Copy retained state without constructors, projections or digest repair."""
    if type(value) is not exact_type:
        raise TypeError(f"exact {exact_type.__name__} required")
    return deepcopy(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class PolygonCompletedDailyStrategyRequest:
    """Occurrence selector only; assessment_fingerprint identifies the ENVELOPE.

    Namespace, sequence, execution ID and envelope fingerprint cannot be proven
    from Assessment content. They are retained, never authenticated here.
    """

    artifact_reference: GovernedTechnicalArtifactReference
    assessment_history_namespace_id: str
    assessment_history_sequence: int
    assessment_execution_id: str
    assessment_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_reference",
            _detach(self.artifact_reference, GovernedTechnicalArtifactReference),
        )
        self._validate()

    def __copy__(self) -> PolygonCompletedDailyStrategyRequest:
        return deepcopy(self)

    def _validate(self) -> None:
        if type(self.artifact_reference) is not GovernedTechnicalArtifactReference:
            raise TypeError("exact governed artifact reference required")
        self.artifact_reference._validate()
        for value, prefix in (
            (
                self.assessment_history_namespace_id,
                "polygon_completed_daily_assessment_history",
            ),
            (self.assessment_execution_id, "polygon_completed_daily_assessment"),
        ):
            if (
                type(value) is not str
                or re.fullmatch(prefix + r":[0-9a-f]{32}", value) is None
            ):
                raise ValueError("exact Assessment occurrence identity required")
        if (
            type(self.assessment_history_sequence) is not int
            or self.assessment_history_sequence < 1
        ):
            raise ValueError("positive exact Assessment history sequence required")
        _fingerprint(self.assessment_fingerprint)

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "artifact_reference": self.artifact_reference.to_dict(),
            "assessment_history_namespace_id": self.assessment_history_namespace_id,
            "assessment_history_sequence": self.assessment_history_sequence,
            "assessment_execution_id": self.assessment_execution_id,
            "assessment_fingerprint": self.assessment_fingerprint,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedDailyTechnicalStrategyPolicyIdentity:
    """Fixed scalar identity; no configurable policy or retained configuration graph."""

    schema_version: str = field(init=False, default="technical_policy_identity/v1")
    policy_kind: str = field(init=False, default="daily_technical_strategy")
    policy_id: str = field(init=False, default="classic_daily_technical_strategy")
    behavioral_revision: str = field(init=False, default="1.0.0")
    configuration_schema: str = field(
        init=False, default="classic_daily_technical_strategy_configuration/v1"
    )
    fingerprint: str = field(init=False, default=_POLICY_FINGERPRINT)

    def __post_init__(self) -> None:
        self._validate()

    @property
    def configuration(self) -> dict[str, object]:
        return {}

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_kind": self.policy_kind,
            "policy_id": self.policy_id,
            "behavioral_revision": self.behavioral_revision,
            "configuration_schema": self.configuration_schema,
            "configuration": self.configuration,
        }

    def _validate(self) -> None:
        for value, expected in (
            (self.schema_version, "technical_policy_identity/v1"),
            (self.policy_kind, "daily_technical_strategy"),
            (self.policy_id, "classic_daily_technical_strategy"),
            (self.behavioral_revision, "1.0.0"),
            (
                self.configuration_schema,
                "classic_daily_technical_strategy_configuration/v1",
            ),
        ):
            _choice(value, (expected,))
        if type(self.configuration) is not dict or self.configuration:
            raise ValueError("exact empty Strategy configuration required")
        _fingerprint(self.fingerprint)
        if (
            self.fingerprint != _POLICY_FINGERPRINT
            or self.fingerprint != canonical_fingerprint(self._fingerprint_payload())
        ):
            raise ValueError("fixed Strategy policy mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def _validate_categories(mode: str, rule_code: str) -> None:
    # Reuse the released pair contract, not a second source-to-Strategy mapping.
    if type(mode) is not str or type(rule_code) is not str:
        raise ValueError("exact scalar Strategy categories required")
    if (mode, rule_code) not in _ALLOWED_MODE_RULE_PAIRS:
        raise ValueError("unsupported Strategy mode/rule pair")


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedDailyTechnicalStrategy:
    """Detached deterministic content, never an authenticated publication."""

    source_assessment_occurrence: PolygonCompletedDailyStrategyRequest
    source_assessment_content_fingerprint: str
    source_interpretation_content_fingerprint: str
    canonical_instrument_id: CanonicalInstrumentId
    analysis_as_of: datetime
    strategy_policy_identity: GovernedDailyTechnicalStrategyPolicyIdentity
    mode: str
    rule_code: str
    schema_version: str = field(
        init=False, default=GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name, value in (
            (
                "source_assessment_occurrence",
                _detach(
                    self.source_assessment_occurrence,
                    PolygonCompletedDailyStrategyRequest,
                ),
            ),
            (
                "canonical_instrument_id",
                _detach(self.canonical_instrument_id, CanonicalInstrumentId),
            ),
            (
                "strategy_policy_identity",
                _detach(
                    self.strategy_policy_identity,
                    GovernedDailyTechnicalStrategyPolicyIdentity,
                ),
            ),
        ):
            object.__setattr__(self, name, value)
        self._validate_structure()
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def __copy__(self) -> GovernedDailyTechnicalStrategy:
        return deepcopy(self)

    def _validate_structure(self) -> None:
        if (
            type(self.source_assessment_occurrence)
            is not PolygonCompletedDailyStrategyRequest
        ):
            raise TypeError("exact Assessment occurrence required")
        self.source_assessment_occurrence._validate()
        _fingerprint(self.source_assessment_content_fingerprint)
        _fingerprint(self.source_interpretation_content_fingerprint)
        _copy_canonical(self.canonical_instrument_id)
        if (
            type(self.analysis_as_of) is not datetime
            or self.analysis_as_of.tzinfo is not UTC
        ):
            raise ValueError("analysis_as_of must be canonical UTC")
        if (
            type(self.strategy_policy_identity)
            is not GovernedDailyTechnicalStrategyPolicyIdentity
        ):
            raise TypeError("exact governed Strategy policy required")
        self.strategy_policy_identity._validate()
        _validate_categories(self.mode, self.rule_code)
        _choice(self.schema_version, (GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA,))

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "source_assessment_occurrence": self.source_assessment_occurrence.to_dict(),
            "source_assessment_content_fingerprint": (
                self.source_assessment_content_fingerprint
            ),
            "source_interpretation_content_fingerprint": (
                self.source_interpretation_content_fingerprint
            ),
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "strategy_policy_identity": self.strategy_policy_identity.to_dict(),
            "mode": self.mode,
            "rule_code": self.rule_code,
            "schema_version": self.schema_version,
        }

    def _validate(self) -> None:
        self._validate_structure()
        _fingerprint(self.fingerprint)
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("governed Strategy fingerprint mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class _AssessmentSemantics:
    outcome: DailyTechnicalAssessmentOutcome


@dataclass(frozen=True, slots=True)
class _InterpretationSemantics:
    trend_direction: DailyTechnicalDirectionalState
    momentum_direction: DailyTechnicalDirectionalState


type _Sources = tuple[
    GovernedDailyTechnicalAssessment,
    GovernedDailyTechnicalInterpretation,
    PolygonCompletedDailyStrategyRequest,
]


def _prepare_sources(sources: _Sources) -> _Sources:
    assessment, interpretation, occurrence = sources
    detached = (
        _detach(assessment, GovernedDailyTechnicalAssessment),
        _detach(interpretation, GovernedDailyTechnicalInterpretation),
        _detach(occurrence, PolygonCompletedDailyStrategyRequest),
    )
    for value in detached:
        value.to_dict()
    return detached


def _expected_projection(sources: _Sources) -> dict[str, object]:
    assessment, interpretation, occurrence = sources
    if (
        occurrence.artifact_reference.to_dict()
        != assessment.source_interpretation_occurrence.artifact_reference.to_dict()
        or occurrence.artifact_reference.to_dict()
        != interpretation.source_technical_occurrence.artifact_reference.to_dict()
    ):
        raise ValueError("Assessment artifact correspondence mismatch")
    if (
        assessment.source_interpretation_content_fingerprint
        != interpretation.fingerprint
        or assessment.canonical_instrument_id.to_dict()
        != interpretation.canonical_instrument_id.to_dict()
        or assessment.source_trading_identity.to_dict()
        != interpretation.source_trading_identity.to_dict()
        or assessment.analysis_as_of != interpretation.analysis_as_of
        or assessment.source_quality != interpretation.source_quality
        or assessment.source_warnings != interpretation.source_warnings
    ):
        raise ValueError("Assessment/Interpretation source correspondence mismatch")
    # This independently checks complete source facts and committed Assessment
    # semantics, but cannot prove either envelope occurrence's membership.
    assessment_domain.validate_governed_daily_technical_assessment(
        content=assessment,
        interpretation=interpretation,
        source_interpretation_occurrence=assessment.source_interpretation_occurrence,
    )
    assessment_view = _AssessmentSemantics(
        DailyTechnicalAssessmentOutcome(assessment.outcome)
    )
    interpretation_view = _InterpretationSemantics(
        DailyTechnicalDirectionalState(interpretation.trend_direction),
        DailyTechnicalDirectionalState(interpretation.momentum_direction),
    )
    views_before = deepcopy((assessment_view, interpretation_view))
    mode_value, rule_value = classic._classic_strategy_semantics(
        interpretation_view,  # type: ignore[arg-type]
        assessment_view,  # type: ignore[arg-type]
    )
    mode, rule_code = mode_value.value, rule_value.value
    _validate_categories(mode, rule_code)
    if (assessment_view, interpretation_view) != views_before:
        raise ValueError("Strategy semantic adapter drift")
    policy = GovernedDailyTechnicalStrategyPolicyIdentity()
    payload: dict[str, object] = {
        "source_assessment_occurrence": occurrence.to_dict(),
        "source_assessment_content_fingerprint": assessment.fingerprint,
        "source_interpretation_content_fingerprint": interpretation.fingerprint,
        "canonical_instrument_id": assessment.canonical_instrument_id.to_dict(),
        "analysis_as_of": assessment.analysis_as_of.isoformat(),
        "strategy_policy_identity": policy.to_dict(),
        "mode": mode,
        "rule_code": rule_code,
        "schema_version": GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA,
    }
    return {**payload, "fingerprint": canonical_fingerprint(payload)}


def _check_drift(
    sources: _Sources, detached: _Sources, before: tuple[dict[str, object], ...]
) -> None:
    for group in (sources, detached):
        if tuple(value.to_dict() for value in group) != before:
            raise ValueError("Strategy source/occurrence drift")


def derive_governed_daily_technical_strategy(
    *,
    assessment: GovernedDailyTechnicalAssessment,
    interpretation: GovernedDailyTechnicalInterpretation,
    source_assessment_occurrence: PolygonCompletedDailyStrategyRequest,
) -> GovernedDailyTechnicalStrategy:
    """Derive from detached content with one released Strategy helper invocation."""
    sources = (assessment, interpretation, source_assessment_occurrence)
    detached = _prepare_sources(sources)
    before = tuple(value.to_dict() for value in detached)
    expected = _expected_projection(detached)
    a, i, occurrence = detached
    result = GovernedDailyTechnicalStrategy(
        source_assessment_occurrence=occurrence,
        source_assessment_content_fingerprint=a.fingerprint,
        source_interpretation_content_fingerprint=i.fingerprint,
        canonical_instrument_id=a.canonical_instrument_id,
        analysis_as_of=a.analysis_as_of,
        strategy_policy_identity=GovernedDailyTechnicalStrategyPolicyIdentity(),
        mode=cast(str, expected["mode"]),
        rule_code=cast(str, expected["rule_code"]),
    )
    if result.to_dict() != expected:
        raise ValueError("governed Strategy construction correspondence mismatch")
    _check_drift(sources, detached, before)
    return result


def validate_governed_daily_technical_strategy(
    *,
    content: GovernedDailyTechnicalStrategy,
    assessment: GovernedDailyTechnicalAssessment,
    interpretation: GovernedDailyTechnicalInterpretation,
    source_assessment_occurrence: PolygonCompletedDailyStrategyRequest,
) -> None:
    """Independently obtain expected semantics; never authenticate publication."""
    candidate = _detach(content, GovernedDailyTechnicalStrategy)
    candidate_before = candidate.to_dict()
    sources = (assessment, interpretation, source_assessment_occurrence)
    detached = _prepare_sources(sources)
    before = tuple(value.to_dict() for value in detached)
    expected = _expected_projection(detached)
    if (
        candidate.to_dict() != candidate_before
        or content.to_dict() != candidate_before
        or candidate_before != expected
    ):
        raise ValueError("governed Strategy source/semantic correspondence mismatch")
    _check_drift(sources, detached, before)


__all__ = [
    "GOVERNED_DAILY_TECHNICAL_STRATEGY_SCHEMA",
    "PolygonCompletedDailyStrategyRequest",
    "GovernedDailyTechnicalStrategyPolicyIdentity",
    "GovernedDailyTechnicalStrategy",
    "derive_governed_daily_technical_strategy",
    "validate_governed_daily_technical_strategy",
]
