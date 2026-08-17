"""Policy boundary and immutable result for daily technical assessment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
    DailyTechnicalExtensionState,
    DailyTechnicalInterpretation,
    TechnicalComparisonEvidence,
    TechnicalComparisonOperand,
)
from market_platform.research.interpretation import VolatilityState
from market_platform.research.technical_analysis import (
    TechnicalAnalysisQuality,
    TechnicalAnalysisWarning,
)
from market_platform.research.technical_policy import (
    CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
    ClassicDailyTechnicalAssessmentConfiguration,
    ClassicDailyTechnicalInterpretationConfiguration,
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
    copy_technical_policy_identity,
)

DAILY_TECHNICAL_ASSESSMENT_SCHEMA = "daily_technical_assessment/v1"
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)
_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,127}", re.ASCII)


class DailyTechnicalAssessmentOutcome(StrEnum):
    ALIGNED = "aligned"
    MIXED = "mixed"
    CAUTION = "caution"
    INSUFFICIENT_DATA = "insufficient_data"


class DailyTechnicalAssessmentFindingKind(StrEnum):
    CONFLICT = "conflict"
    CAUTION = "caution"


@dataclass(frozen=True, slots=True)
class DailyTechnicalAssessmentFinding:
    kind: DailyTechnicalAssessmentFindingKind
    code: str
    comparison_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if type(self.kind) is not DailyTechnicalAssessmentFindingKind:
            raise TypeError("finding kind is invalid")
        if type(self.code) is not str or _CODE_PATTERN.fullmatch(self.code) is None:
            raise ValueError("finding code is invalid")
        if type(self.comparison_evidence_ids) is not tuple or any(
            type(item) is not str or _CODE_PATTERN.fullmatch(item) is None
            for item in self.comparison_evidence_ids
        ):
            raise ValueError("finding evidence references are invalid")
        if len(set(self.comparison_evidence_ids)) != len(self.comparison_evidence_ids):
            raise ValueError("finding evidence references must be unique")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "kind": self.kind.value,
            "code": self.code,
            "comparison_evidence_ids": list(self.comparison_evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class DailyTechnicalAssessment:
    canonical_instrument_id: CanonicalInstrumentId
    analysis_as_of: datetime
    source_interpretation_fingerprint: str
    assessment_policy_identity: TechnicalPolicyIdentity
    outcome: DailyTechnicalAssessmentOutcome
    findings: tuple[DailyTechnicalAssessmentFinding, ...]
    schema_version: str = field(init=False, default=DAILY_TECHNICAL_ASSESSMENT_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assessment_policy_identity",
            copy_technical_policy_identity(self.assessment_policy_identity),
        )
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "source_interpretation_fingerprint": self.source_interpretation_fingerprint,
            "assessment_policy_identity": self.assessment_policy_identity.to_dict(),
            "outcome": self.outcome.value,
            "findings": [item.to_dict() for item in self.findings],
        }

    def _fingerprint_payload(self) -> dict[str, object]:
        return self._projection()

    def _validate(self) -> None:
        try:
            values = {
                name: object.__getattribute__(self, name)
                for name in (
                    "canonical_instrument_id",
                    "analysis_as_of",
                    "source_interpretation_fingerprint",
                    "assessment_policy_identity",
                    "outcome",
                    "findings",
                    "schema_version",
                    "fingerprint",
                )
            }
        except AttributeError as exc:
            raise ValueError("assessment retained state is incomplete") from exc
        if type(values["canonical_instrument_id"]) is not CanonicalInstrumentId:
            raise ValueError("assessment canonical instrument ID is invalid")
        fixed_id = CanonicalInstrumentId(self.canonical_instrument_id.instrument_id)
        if fixed_id.to_dict() != self.canonical_instrument_id.to_dict():
            raise ValueError("assessment canonical instrument ID is noncanonical")
        if (
            type(values["analysis_as_of"]) is not datetime
            or self.analysis_as_of.tzinfo is not UTC
        ):
            raise ValueError("assessment analysis_as_of must be canonical UTC")
        for name in ("source_interpretation_fingerprint", "fingerprint"):
            if (
                type(values[name]) is not str
                or _FINGERPRINT_PATTERN.fullmatch(values[name]) is None
            ):
                raise ValueError(f"assessment {name} is invalid")
        if type(values["assessment_policy_identity"]) is not TechnicalPolicyIdentity:
            raise ValueError("assessment policy identity is invalid")
        self.assessment_policy_identity._validate()
        if (
            self.assessment_policy_identity.policy_kind
            is not TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT
        ):
            raise ValueError("assessment policy kind is invalid")
        if type(values["outcome"]) is not DailyTechnicalAssessmentOutcome:
            raise ValueError("assessment outcome is invalid")
        if type(values["findings"]) is not tuple:
            raise ValueError("assessment findings must be a tuple")
        pairs: list[tuple[DailyTechnicalAssessmentFindingKind, str]] = []
        for finding in self.findings:
            if type(finding) is not DailyTechnicalAssessmentFinding:
                raise ValueError("assessment finding is invalid")
            finding._validate()
            pairs.append((finding.kind, finding.code))
        if len(set(pairs)) != len(pairs):
            raise ValueError("assessment finding kind/code pairs must be unique")
        if self.schema_version != DAILY_TECHNICAL_ASSESSMENT_SCHEMA:
            raise ValueError("assessment schema is invalid")
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("assessment fingerprint does not match content")

    def _validate_references(
        self, interpretation: DailyTechnicalInterpretation
    ) -> None:
        available = {item.evidence_id for item in interpretation.comparison_evidence}
        if any(
            evidence_id not in available
            for finding in self.findings
            for evidence_id in finding.comparison_evidence_ids
        ):
            raise ValueError(
                "assessment finding references missing comparison evidence"
            )

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


@runtime_checkable
class DailyTechnicalAssessmentPolicy(Protocol):
    @property
    def identity(self) -> TechnicalPolicyIdentity: ...

    def assess(
        self, interpretation: DailyTechnicalInterpretation
    ) -> DailyTechnicalAssessment: ...


@dataclass(frozen=True, slots=True)
class _DetachedInterpretationSemantics:
    schema_version: str
    canonical_instrument_id: tuple[tuple[str, object], ...]
    requested_trading_identity: tuple[tuple[str, object], ...]
    analysis_as_of: datetime
    fingerprint: str
    interpretation_policy_identity: TechnicalPolicyIdentity
    source_technical_analysis_snapshot_fingerprint: str
    source_daily_instrument_integrity_evidence_fingerprint: str
    source_quality: TechnicalAnalysisQuality
    source_warnings: tuple[TechnicalAnalysisWarning, ...]
    trend_direction: DailyTechnicalDirectionalState
    momentum_direction: DailyTechnicalDirectionalState
    volatility_state: VolatilityState
    extension_state: DailyTechnicalExtensionState
    comparison_evidence: tuple[TechnicalComparisonEvidence, ...]
    comparison_evidence_ids: frozenset[str]
    complete_source_projection: str


def _detach_interpretation_semantics(
    interpretation: DailyTechnicalInterpretation,
) -> _DetachedInterpretationSemantics:
    evidence = tuple(
        TechnicalComparisonEvidence(
            item.evidence_id,
            TechnicalComparisonOperand(
                item.left_operand.source,
                item.left_operand.field,
                item.left_operand.value,
            ),
            item.operator,
            TechnicalComparisonOperand(
                item.right_operand.source,
                item.right_operand.field,
                item.right_operand.value,
            ),
            item.satisfied,
        )
        for item in interpretation.comparison_evidence
    )
    return _DetachedInterpretationSemantics(
        schema_version=interpretation.schema_version,
        canonical_instrument_id=tuple(
            sorted(interpretation.canonical_instrument_id.to_dict().items())
        ),
        requested_trading_identity=tuple(
            sorted(interpretation.requested_trading_identity.to_dict().items())
        ),
        analysis_as_of=interpretation.analysis_as_of,
        fingerprint=interpretation.fingerprint,
        interpretation_policy_identity=copy_technical_policy_identity(
            interpretation.interpretation_policy_identity
        ),
        source_technical_analysis_snapshot_fingerprint=(
            interpretation.source_technical_analysis_snapshot_fingerprint
        ),
        source_daily_instrument_integrity_evidence_fingerprint=(
            interpretation.source_daily_instrument_integrity_evidence_fingerprint
        ),
        source_quality=interpretation.source_quality,
        source_warnings=tuple(interpretation.source_warnings),
        trend_direction=interpretation.trend_direction,
        momentum_direction=interpretation.momentum_direction,
        volatility_state=interpretation.volatility_state,
        extension_state=interpretation.extension_state,
        comparison_evidence=evidence,
        comparison_evidence_ids=frozenset(item.evidence_id for item in evidence),
        complete_source_projection=json.dumps(
            interpretation.to_dict(), sort_keys=True, separators=(",", ":")
        ),
    )


def build_classic_assessment_findings(
    interpretation: DailyTechnicalInterpretation,
) -> tuple[DailyTechnicalAssessmentFinding, ...]:
    """Build every independently true classic coherence finding in fixed order."""

    evidence = {item.evidence_id: item for item in interpretation.comparison_evidence}

    def satisfied(evidence_id: str) -> bool:
        item = evidence.get(evidence_id)
        return item is not None and item.satisfied

    findings: list[DailyTechnicalAssessmentFinding] = []
    opposition_refs: tuple[str, ...] | None = None
    if (
        interpretation.trend_direction is DailyTechnicalDirectionalState.POSITIVE
        and interpretation.momentum_direction is DailyTechnicalDirectionalState.NEGATIVE
    ):
        opposition_refs = (
            "trend_ema8_above_ema20",
            "trend_close_above_ema144",
            "trend_close_above_ema169",
            "momentum_macd_line_below_signal",
            "momentum_rsi_below_neutral",
        )
    elif (
        interpretation.trend_direction is DailyTechnicalDirectionalState.NEGATIVE
        and interpretation.momentum_direction is DailyTechnicalDirectionalState.POSITIVE
    ):
        opposition_refs = (
            "trend_ema8_below_ema20",
            "trend_close_below_ema144",
            "trend_close_below_ema169",
            "momentum_macd_line_above_signal",
            "momentum_rsi_at_or_above_neutral",
        )
    if opposition_refs is not None:
        if not all(satisfied(item) for item in opposition_refs):
            raise ValueError("direction opposition lacks satisfied supporting evidence")
        findings.append(
            DailyTechnicalAssessmentFinding(
                DailyTechnicalAssessmentFindingKind.CONFLICT,
                "direction_opposition",
                opposition_refs,
            )
        )
    evidence_findings = (
        ("rsi_elevated", "rsi_at_or_above_elevated"),
        ("rsi_depressed", "rsi_at_or_below_depressed"),
        ("ema20_above_reference_band", "extension_above_positive_band"),
        ("ema20_below_reference_band", "extension_below_negative_band"),
        ("high_realized_volatility", "volatility_at_or_above_high"),
    )
    for code, evidence_id in evidence_findings:
        if satisfied(evidence_id):
            findings.append(
                DailyTechnicalAssessmentFinding(
                    DailyTechnicalAssessmentFindingKind.CAUTION,
                    code,
                    (evidence_id,),
                )
            )
    if interpretation.source_quality is TechnicalAnalysisQuality.DEGRADED:
        findings.append(
            DailyTechnicalAssessmentFinding(
                DailyTechnicalAssessmentFindingKind.CAUTION,
                "source_quality_degraded",
                (),
            )
        )
    warning_findings = (
        (
            TechnicalAnalysisWarning.INSUFFICIENT_PROFILE_HISTORY,
            "source_warning_insufficient_profile_history",
        ),
        (TechnicalAnalysisWarning.STALE_EVIDENCE, "source_warning_stale_evidence"),
    )
    for warning, code in warning_findings:
        if warning in interpretation.source_warnings:
            findings.append(
                DailyTechnicalAssessmentFinding(
                    DailyTechnicalAssessmentFindingKind.CAUTION, code, ()
                )
            )
    return tuple(findings)


def classic_assessment_outcome(
    interpretation: DailyTechnicalInterpretation,
    findings: tuple[DailyTechnicalAssessmentFinding, ...],
) -> DailyTechnicalAssessmentOutcome:
    has_unavailable = (
        interpretation.trend_direction is DailyTechnicalDirectionalState.UNAVAILABLE
        or interpretation.momentum_direction
        is DailyTechnicalDirectionalState.UNAVAILABLE
        or interpretation.volatility_state is VolatilityState.UNAVAILABLE
        or interpretation.extension_state is DailyTechnicalExtensionState.UNAVAILABLE
    )
    has_mixed = (
        interpretation.trend_direction is DailyTechnicalDirectionalState.MIXED
        or interpretation.momentum_direction is DailyTechnicalDirectionalState.MIXED
        or any(
            item.kind is DailyTechnicalAssessmentFindingKind.CONFLICT
            and item.code == "direction_opposition"
            for item in findings
        )
    )
    has_caution = any(
        item.kind is DailyTechnicalAssessmentFindingKind.CAUTION for item in findings
    )
    if has_unavailable:
        return DailyTechnicalAssessmentOutcome.INSUFFICIENT_DATA
    if has_mixed:
        return DailyTechnicalAssessmentOutcome.MIXED
    if has_caution:
        return DailyTechnicalAssessmentOutcome.CAUTION
    return DailyTechnicalAssessmentOutcome.ALIGNED


def assess_daily_technical_interpretation(
    interpretation: DailyTechnicalInterpretation,
    policy: DailyTechnicalAssessmentPolicy,
) -> DailyTechnicalAssessment:
    if type(interpretation) is not DailyTechnicalInterpretation:
        raise TypeError("interpretation must be an exact DailyTechnicalInterpretation")
    interpretation._validate()
    source_before = _detach_interpretation_semantics(interpretation)
    source_policy = source_before.interpretation_policy_identity
    if (
        source_policy.policy_id != "classic_daily_technical"
        or source_policy.behavioral_revision != "1.0.0"
        or source_policy.configuration_schema
        != CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA
        or type(source_policy.configuration)
        is not ClassicDailyTechnicalInterpretationConfiguration
    ):
        raise ValueError(
            "interpretation policy is incompatible with classic assessment"
        )
    expected_findings = build_classic_assessment_findings(
        source_before  # type: ignore[arg-type]
    )
    expected_outcome = classic_assessment_outcome(
        source_before,  # type: ignore[arg-type]
        expected_findings,
    )
    try:
        before = copy_technical_policy_identity(policy.identity)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("assessment policy identity is invalid") from exc
    if before.policy_kind is not TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT:
        raise ValueError("assessment policy identity kind is invalid")
    if type(before.configuration) is not ClassicDailyTechnicalAssessmentConfiguration:
        raise ValueError("assessment policy configuration type is unsupported")
    result = policy.assess(interpretation)
    interpretation._validate()
    source_after = _detach_interpretation_semantics(interpretation)
    if source_after != source_before:
        raise ValueError("source interpretation drifted during invocation")
    try:
        after = copy_technical_policy_identity(policy.identity)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("post-call assessment policy identity is invalid") from exc
    if before.to_dict() != after.to_dict():
        raise ValueError("assessment policy identity drifted during invocation")
    if type(result) is not DailyTechnicalAssessment:
        raise TypeError("policy must return an exact DailyTechnicalAssessment")
    result._validate()
    if result.assessment_policy_identity.to_dict() != before.to_dict():
        raise ValueError("assessment does not correspond to pre-call policy identity")
    if (
        result.source_interpretation_fingerprint != source_before.fingerprint
        or tuple(sorted(result.canonical_instrument_id.to_dict().items()))
        != source_before.canonical_instrument_id
        or result.analysis_as_of != source_before.analysis_as_of
    ):
        raise ValueError("assessment source correspondence is invalid")
    if any(
        evidence_id not in source_before.comparison_evidence_ids
        for finding in result.findings
        for evidence_id in finding.comparison_evidence_ids
    ):
        raise ValueError("assessment finding references missing comparison evidence")
    if result.findings != expected_findings:
        raise ValueError("assessment findings are not complete and exact")
    if result.outcome is not expected_outcome:
        raise ValueError("assessment outcome does not match precedence rules")
    return result


__all__ = [
    "DAILY_TECHNICAL_ASSESSMENT_SCHEMA",
    "DailyTechnicalAssessmentOutcome",
    "DailyTechnicalAssessmentFindingKind",
    "DailyTechnicalAssessmentFinding",
    "DailyTechnicalAssessmentPolicy",
    "DailyTechnicalAssessment",
    "assess_daily_technical_interpretation",
]
