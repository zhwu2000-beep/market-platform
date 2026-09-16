"""Deterministic Assessment values; detached selectors confer no authority.

This boundary consumes governed Interpretation content without authenticating a
publication or recomputing Interpretation semantics from technical inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research import daily_technical_assessment as classic
from market_platform.research.daily_technical_assessment import (
    build_classic_assessment_findings,
    classic_assessment_outcome,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
    DailyTechnicalExtensionState,
)
from market_platform.research.governed_daily_technical_interpretation import (
    GovernedDailyTechnicalInterpretation,
    GovernedTechnicalArtifactReference,
    _choice,
    _copy_canonical,
    _copy_trading,
    _fingerprint,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.research.technical_analysis import (
    TechnicalAnalysisQuality,
    TechnicalAnalysisWarning,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA = "governed_daily_technical_assessment/v1"
_POLICY_FINGERPRINT = (
    "sha256:dbdf4bdb4eeb3880d5a6ad4f90d17d9934782f6e1d0d455cb3af93a20d74874f"
)
_WARNINGS = ("insufficient_profile_history", "stale_evidence")
# Closed value contracts only; finding triggers belong exclusively to the helpers.
_OPPOSITION_SUPPORT = (
    (
        "trend_ema8_above_ema20",
        "trend_close_above_ema144",
        "trend_close_above_ema169",
        "momentum_macd_line_below_signal",
        "momentum_rsi_below_neutral",
    ),
    (
        "trend_ema8_below_ema20",
        "trend_close_below_ema144",
        "trend_close_below_ema169",
        "momentum_macd_line_above_signal",
        "momentum_rsi_at_or_above_neutral",
    ),
)
_FINDING_SUPPORT = {
    "direction_opposition": _OPPOSITION_SUPPORT,
    "rsi_elevated": (("rsi_at_or_above_elevated",),),
    "rsi_depressed": (("rsi_at_or_below_depressed",),),
    "ema20_above_reference_band": (("extension_above_positive_band",),),
    "ema20_below_reference_band": (("extension_below_negative_band",),),
    "high_realized_volatility": (("volatility_at_or_above_high",),),
    "source_quality_degraded": ((),),
    "source_warning_insufficient_profile_history": ((),),
    "source_warning_stale_evidence": ((),),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class PolygonCompletedDailyAssessmentRequest:
    """Five detached Interpretation selectors, never proof of publication.

    interpretation_fingerprint identifies the source RESULT ENVELOPE, not content.
    The research placement follows PolygonCompletedDailyInterpretationRequest.
    """

    artifact_reference: GovernedTechnicalArtifactReference
    interpretation_history_namespace_id: str
    interpretation_history_sequence: int
    interpretation_execution_id: str
    interpretation_fingerprint: str

    def __post_init__(self) -> None:
        self._validate()
        object.__setattr__(self, "artifact_reference", replace(self.artifact_reference))

    def _validate(self) -> None:
        if type(self.artifact_reference) is not GovernedTechnicalArtifactReference:
            raise TypeError("exact governed artifact reference required")
        self.artifact_reference._validate()
        for value, prefix in (
            (
                self.interpretation_history_namespace_id,
                "polygon_completed_daily_interpretation_history",
            ),
            (
                self.interpretation_execution_id,
                "polygon_completed_daily_interpretation",
            ),
        ):
            if (
                type(value) is not str
                or re.fullmatch(prefix + r":[0-9a-f]{32}", value) is None
            ):
                raise ValueError("exact Interpretation occurrence identity required")
        if (
            type(self.interpretation_history_sequence) is not int
            or self.interpretation_history_sequence < 1
        ):
            raise ValueError("positive exact Interpretation history sequence required")
        _fingerprint(self.interpretation_fingerprint)

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "artifact_reference": self.artifact_reference.to_dict(),
            "interpretation_history_namespace_id": (
                self.interpretation_history_namespace_id
            ),
            "interpretation_history_sequence": self.interpretation_history_sequence,
            "interpretation_execution_id": self.interpretation_execution_id,
            "interpretation_fingerprint": self.interpretation_fingerprint,
        }


def _copy_occurrence(
    value: PolygonCompletedDailyAssessmentRequest,
) -> PolygonCompletedDailyAssessmentRequest:
    if type(value) is not PolygonCompletedDailyAssessmentRequest:
        raise TypeError("exact Interpretation occurrence reference required")
    value._validate()
    return replace(value)


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedDailyTechnicalAssessmentPolicyIdentity:
    policy_kind: str = "daily_technical_assessment"
    policy_id: str = "classic_daily_technical_coherence"
    behavioral_revision: str = "1.0.0"
    configuration_schema: str = "classic_daily_technical_assessment_configuration/v1"
    configuration: dict[str, object] = field(default_factory=dict)
    schema_version: str = field(init=False, default="technical_policy_identity/v1")
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_structure()
        object.__setattr__(self, "configuration", {})
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _validate_structure(self) -> None:
        for value, expected in (
            (self.schema_version, "technical_policy_identity/v1"),
            (self.policy_kind, "daily_technical_assessment"),
            (self.policy_id, "classic_daily_technical_coherence"),
            (self.behavioral_revision, "1.0.0"),
            (
                self.configuration_schema,
                "classic_daily_technical_assessment_configuration/v1",
            ),
        ):
            _choice(value, (expected,))
        if type(self.configuration) is not dict or self.configuration:
            raise ValueError("exact empty Assessment configuration required")

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_kind": self.policy_kind,
            "policy_id": self.policy_id,
            "behavioral_revision": self.behavioral_revision,
            "configuration_schema": self.configuration_schema,
            "configuration": dict(self.configuration),
        }

    def _validate(self) -> None:
        self._validate_structure()
        _fingerprint(self.fingerprint)
        if (
            self.fingerprint != _POLICY_FINGERPRINT
            or self.fingerprint != canonical_fingerprint(self._fingerprint_payload())
        ):
            raise ValueError("fixed Assessment policy mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class GovernedDailyTechnicalAssessmentFinding:
    kind: str
    code: str
    comparison_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        _choice(self.kind, ("conflict", "caution"))
        _choice(self.code, tuple(_FINDING_SUPPORT))
        if self.kind != (
            "conflict" if self.code == "direction_opposition" else "caution"
        ):
            raise ValueError("finding kind/code mismatch")
        if type(self.comparison_evidence_ids) is not tuple or any(
            type(item) is not str for item in self.comparison_evidence_ids
        ):
            raise TypeError("exact scalar finding references required")
        if self.comparison_evidence_ids not in _FINDING_SUPPORT[self.code]:
            raise ValueError("finding support/order mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "kind": self.kind,
            "code": self.code,
            "comparison_evidence_ids": list(self.comparison_evidence_ids),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class GovernedDailyTechnicalAssessment:
    """Detached deterministic content; use the validator for source correspondence."""

    source_interpretation_occurrence: PolygonCompletedDailyAssessmentRequest
    source_interpretation_content_fingerprint: str
    canonical_instrument_id: CanonicalInstrumentId
    source_trading_identity: TradingInstrumentIdentity
    analysis_as_of: datetime
    assessment_policy_identity: GovernedDailyTechnicalAssessmentPolicyIdentity
    source_quality: str
    source_warnings: tuple[str, ...]
    outcome: str
    findings: tuple[GovernedDailyTechnicalAssessmentFinding, ...]
    schema_version: str = field(
        init=False, default=GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_structure()
        for name, copied in (
            (
                "source_interpretation_occurrence",
                _copy_occurrence(self.source_interpretation_occurrence),
            ),
            ("canonical_instrument_id", _copy_canonical(self.canonical_instrument_id)),
            ("source_trading_identity", _copy_trading(self.source_trading_identity)),
            ("assessment_policy_identity", replace(self.assessment_policy_identity)),
            ("findings", tuple(replace(item) for item in self.findings)),
        ):
            object.__setattr__(self, name, copied)
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _validate_structure(self) -> None:
        _copy_occurrence(self.source_interpretation_occurrence)
        _fingerprint(self.source_interpretation_content_fingerprint)
        _copy_canonical(self.canonical_instrument_id)
        _copy_trading(self.source_trading_identity)
        if (
            type(self.analysis_as_of) is not datetime
            or self.analysis_as_of.tzinfo is not UTC
        ):
            raise ValueError("analysis_as_of must be canonical UTC")
        if (
            type(self.assessment_policy_identity)
            is not GovernedDailyTechnicalAssessmentPolicyIdentity
        ):
            raise TypeError("exact governed Assessment policy required")
        self.assessment_policy_identity._validate()
        _choice(self.source_quality, ("complete", "degraded"))
        if type(self.source_warnings) is not tuple:
            raise TypeError("exact source warning tuple required")
        for item in self.source_warnings:
            _choice(item, _WARNINGS)
        if self.source_warnings != tuple(
            w for w in _WARNINGS if w in self.source_warnings
        ):
            raise ValueError("source warning order/duplicates invalid")
        _choice(self.outcome, ("aligned", "mixed", "caution", "insufficient_data"))
        if type(self.findings) is not tuple:
            raise TypeError("exact finding tuple required")
        for finding in self.findings:
            if type(finding) is not GovernedDailyTechnicalAssessmentFinding:
                raise TypeError("exact governed finding required")
            finding._validate()
        codes = tuple(item.code for item in self.findings)
        if codes != tuple(code for code in _FINDING_SUPPORT if code in codes):
            raise ValueError("finding order/duplicates invalid")
        _choice(self.schema_version, (GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA,))

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source_interpretation_occurrence": (
                self.source_interpretation_occurrence.to_dict()
            ),
            "source_interpretation_content_fingerprint": (
                self.source_interpretation_content_fingerprint
            ),
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "source_trading_identity": self.source_trading_identity.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "assessment_policy_identity": self.assessment_policy_identity.to_dict(),
            "source_quality": self.source_quality,
            "source_warnings": list(self.source_warnings),
            "outcome": self.outcome,
            "findings": [item.to_dict() for item in self.findings],
        }

    def _validate(self) -> None:
        try:
            for item in fields(self):
                object.__getattribute__(self, item.name)
        except AttributeError as exc:
            raise ValueError("governed Assessment retained state incomplete") from exc
        self._validate_structure()
        _fingerprint(self.fingerprint)
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("governed Assessment fingerprint mismatch")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


@dataclass(frozen=True, slots=True)
class _ComparisonTruth:
    evidence_id: str
    satisfied: bool


@dataclass(frozen=True, slots=True)
class _DetachedInterpretationSemantics:
    trend_direction: DailyTechnicalDirectionalState
    momentum_direction: DailyTechnicalDirectionalState
    volatility_state: VolatilityState
    extension_state: DailyTechnicalExtensionState
    comparison_evidence: tuple[_ComparisonTruth, ...]
    source_quality: TechnicalAnalysisQuality
    source_warnings: tuple[TechnicalAnalysisWarning, ...]


def _semantic_view(
    source: GovernedDailyTechnicalInterpretation,
) -> _DetachedInterpretationSemantics:
    return _DetachedInterpretationSemantics(
        DailyTechnicalDirectionalState(source.trend_direction),
        DailyTechnicalDirectionalState(source.momentum_direction),
        VolatilityState(source.volatility_state),
        DailyTechnicalExtensionState(source.extension_state),
        tuple(
            _ComparisonTruth(item.evidence_id, item.satisfied)
            for item in source.comparison_evidence
        ),
        TechnicalAnalysisQuality(source.source_quality),
        tuple(TechnicalAnalysisWarning(item) for item in source.source_warnings),
    )


def _derive_assessment(
    source: GovernedDailyTechnicalInterpretation,
    occurrence: PolygonCompletedDailyAssessmentRequest,
    *,
    independent: bool,
) -> GovernedDailyTechnicalAssessment:
    if type(source) is not GovernedDailyTechnicalInterpretation:
        raise TypeError("exact governed Interpretation source required")
    source_before = source.to_dict()
    reference = _copy_occurrence(occurrence)
    occurrence_before = reference.to_dict()
    detached = replace(source)
    if detached.to_dict() != source_before:
        raise ValueError("Interpretation detachment mismatch")
    if reference.artifact_reference.to_dict() != (
        detached.source_technical_occurrence.artifact_reference.to_dict()
    ):
        raise ValueError("source artifact correspondence mismatch")
    policy = GovernedDailyTechnicalAssessmentPolicyIdentity()
    view = _semantic_view(detached)
    # The released helpers accept this structural view at runtime, just as their
    # own private detached boundary does. No legacy provenance carrier is made.
    finding_helper = (
        classic.build_classic_assessment_findings
        if independent
        else build_classic_assessment_findings
    )
    outcome_helper = (
        classic.classic_assessment_outcome
        if independent
        else classic_assessment_outcome
    )
    legacy_findings = finding_helper(view)  # type: ignore[arg-type]
    findings = tuple(
        GovernedDailyTechnicalAssessmentFinding(
            str(item.kind.value),
            str(item.code),
            tuple(str(ref) for ref in item.comparison_evidence_ids),
        )
        for item in legacy_findings
    )
    outcome = str(outcome_helper(view, legacy_findings).value)  # type: ignore[arg-type]
    expected: dict[str, object] = {
        "schema_version": GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA,
        "source_interpretation_occurrence": occurrence_before,
        "source_interpretation_content_fingerprint": detached.fingerprint,
        "canonical_instrument_id": detached.canonical_instrument_id.to_dict(),
        "source_trading_identity": detached.source_trading_identity.to_dict(),
        "analysis_as_of": detached.analysis_as_of.isoformat(),
        "assessment_policy_identity": policy.to_dict(),
        "source_quality": detached.source_quality,
        "source_warnings": list(detached.source_warnings),
        "outcome": outcome,
        "findings": [item.to_dict() for item in findings],
    }
    result = GovernedDailyTechnicalAssessment(
        source_interpretation_occurrence=reference,
        source_interpretation_content_fingerprint=detached.fingerprint,
        canonical_instrument_id=detached.canonical_instrument_id,
        source_trading_identity=detached.source_trading_identity,
        analysis_as_of=detached.analysis_as_of,
        assessment_policy_identity=policy,
        source_quality=detached.source_quality,
        source_warnings=detached.source_warnings,
        outcome=outcome,
        findings=findings,
    )
    for item in (source, detached):
        if item.to_dict() != source_before:
            raise ValueError("Interpretation source drift during Assessment")
    for ref in (occurrence, reference):
        if ref.to_dict() != occurrence_before:
            raise ValueError("Interpretation occurrence drift during Assessment")
    policy._validate()
    if view != _semantic_view(detached):
        raise ValueError("detached semantic view drift during Assessment")
    if result.to_dict() != {**expected, "fingerprint": canonical_fingerprint(expected)}:
        raise ValueError("governed Assessment construction correspondence mismatch")
    return result


def validate_governed_daily_technical_assessment(
    *,
    content: GovernedDailyTechnicalAssessment,
    interpretation: GovernedDailyTechnicalInterpretation,
    source_interpretation_occurrence: PolygonCompletedDailyAssessmentRequest,
) -> None:
    """Derive fresh expected semantics and check all content, without authority."""
    if type(content) is not GovernedDailyTechnicalAssessment:
        raise TypeError("exact governed Assessment content required")
    before = content.to_dict()
    expected = _derive_assessment(
        interpretation, source_interpretation_occurrence, independent=True
    )
    if content.to_dict() != before or before != expected.to_dict():
        raise ValueError("governed Assessment source/semantic correspondence mismatch")


def assess_governed_daily_technical_interpretation(
    *,
    interpretation: GovernedDailyTechnicalInterpretation,
    source_interpretation_occurrence: PolygonCompletedDailyAssessmentRequest,
) -> GovernedDailyTechnicalAssessment:
    """Assess detached source content; neither authenticate nor issue an occurrence."""
    result = _derive_assessment(
        interpretation, source_interpretation_occurrence, independent=False
    )
    validate_governed_daily_technical_assessment(
        content=result,
        interpretation=interpretation,
        source_interpretation_occurrence=source_interpretation_occurrence,
    )
    return result


__all__ = [
    "GOVERNED_DAILY_TECHNICAL_ASSESSMENT_SCHEMA",
    "PolygonCompletedDailyAssessmentRequest",
    "GovernedDailyTechnicalAssessmentPolicyIdentity",
    "GovernedDailyTechnicalAssessmentFinding",
    "GovernedDailyTechnicalAssessment",
    "assess_governed_daily_technical_interpretation",
    "validate_governed_daily_technical_assessment",
]
