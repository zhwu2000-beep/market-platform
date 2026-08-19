"""Immutable strategy vocabulary for daily technical assessments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessment,
    DailyTechnicalAssessmentFinding,
    DailyTechnicalAssessmentOutcome,
    _detach_interpretation_semantics,
    build_classic_assessment_findings,
    classic_assessment_outcome,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalInterpretation,
)
from market_platform.research.technical_policy import (
    CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
    ClassicDailyTechnicalAssessmentConfiguration,
    ClassicDailyTechnicalInterpretationConfiguration,
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
    copy_technical_policy_identity,
)

DAILY_TECHNICAL_STRATEGY_SCHEMA = "daily_technical_strategy/v1"
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", re.ASCII)


class DailyTechnicalStrategyMode(StrEnum):
    POSITIVE_DIRECTIONAL_CONTINUATION = "positive_directional_continuation"
    NEGATIVE_DIRECTIONAL_CONTINUATION = "negative_directional_continuation"
    NO_ACTIVE_STRATEGY = "no_active_strategy"


class DailyTechnicalStrategyRuleCode(StrEnum):
    ALIGNED_POSITIVE_CONTINUATION = "aligned_positive_continuation"
    ALIGNED_NEGATIVE_CONTINUATION = "aligned_negative_continuation"
    CAUTION_NO_ACTIVE_STRATEGY = "caution_no_active_strategy"
    MIXED_NO_ACTIVE_STRATEGY = "mixed_no_active_strategy"
    INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY = "insufficient_data_no_active_strategy"


_ALLOWED_MODE_RULE_PAIRS = frozenset(
    {
        (
            DailyTechnicalStrategyMode.POSITIVE_DIRECTIONAL_CONTINUATION,
            DailyTechnicalStrategyRuleCode.ALIGNED_POSITIVE_CONTINUATION,
        ),
        (
            DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
            DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION,
        ),
        (
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.CAUTION_NO_ACTIVE_STRATEGY,
        ),
        (
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.MIXED_NO_ACTIVE_STRATEGY,
        ),
        (
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY,
        ),
    }
)


def _copy_canonical_instrument_id(value: object) -> CanonicalInstrumentId:
    if type(value) is not CanonicalInstrumentId:
        raise ValueError("strategy canonical instrument ID is invalid")
    try:
        reconstructed = CanonicalInstrumentId(value.instrument_id)
        retained = value.to_dict()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("strategy canonical instrument ID is invalid") from exc
    if retained != reconstructed.to_dict():
        raise ValueError("strategy canonical instrument ID is noncanonical")
    return reconstructed


@dataclass(frozen=True, slots=True)
class DailyTechnicalStrategy:
    canonical_instrument_id: CanonicalInstrumentId
    analysis_as_of: datetime
    source_assessment_fingerprint: str
    strategy_policy_identity: TechnicalPolicyIdentity
    mode: DailyTechnicalStrategyMode
    rule_code: DailyTechnicalStrategyRuleCode
    schema_version: str = field(init=False, default=DAILY_TECHNICAL_STRATEGY_SCHEMA)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "canonical_instrument_id",
            _copy_canonical_instrument_id(self.canonical_instrument_id),
        )
        object.__setattr__(
            self,
            "strategy_policy_identity",
            copy_technical_policy_identity(self.strategy_policy_identity),
        )
        if type(self.mode) is not DailyTechnicalStrategyMode:
            raise ValueError("strategy mode is invalid")
        if type(self.rule_code) is not DailyTechnicalStrategyRuleCode:
            raise ValueError("strategy rule code is invalid")
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )
        self._validate()

    def _projection(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "analysis_as_of": self.analysis_as_of.isoformat(),
            "source_assessment_fingerprint": self.source_assessment_fingerprint,
            "strategy_policy_identity": self.strategy_policy_identity.to_dict(),
            "mode": self.mode.value,
            "rule_code": self.rule_code.value,
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
                    "source_assessment_fingerprint",
                    "strategy_policy_identity",
                    "mode",
                    "rule_code",
                    "schema_version",
                    "fingerprint",
                )
            }
        except AttributeError as exc:
            raise ValueError("strategy retained state is incomplete") from exc
        _copy_canonical_instrument_id(values["canonical_instrument_id"])
        if (
            type(values["analysis_as_of"]) is not datetime
            or values["analysis_as_of"].tzinfo is not UTC
        ):
            raise ValueError("strategy analysis_as_of must be canonical UTC")
        for name in ("source_assessment_fingerprint", "fingerprint"):
            if (
                type(values[name]) is not str
                or _FINGERPRINT_PATTERN.fullmatch(values[name]) is None
            ):
                raise ValueError(f"strategy {name} is invalid")
        if type(values["strategy_policy_identity"]) is not TechnicalPolicyIdentity:
            raise ValueError("strategy policy identity is invalid")
        self.strategy_policy_identity._validate()
        if (
            self.strategy_policy_identity.policy_kind
            is not TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY
        ):
            raise ValueError("strategy policy kind is invalid")
        if type(values["mode"]) is not DailyTechnicalStrategyMode:
            raise ValueError("strategy mode is invalid")
        if type(values["rule_code"]) is not DailyTechnicalStrategyRuleCode:
            raise ValueError("strategy rule code is invalid")
        if (self.mode, self.rule_code) not in _ALLOWED_MODE_RULE_PAIRS:
            raise ValueError("strategy mode and rule code do not correspond")
        if values["schema_version"] != DAILY_TECHNICAL_STRATEGY_SCHEMA:
            raise ValueError("strategy schema is invalid")
        if self.fingerprint != canonical_fingerprint(self._fingerprint_payload()):
            raise ValueError("strategy fingerprint does not match content")

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {**self._projection(), "fingerprint": self.fingerprint}


@runtime_checkable
class DailyTechnicalStrategyPolicy(Protocol):
    @property
    def policy_identity(self) -> TechnicalPolicyIdentity: ...

    def determine(
        self,
        interpretation: DailyTechnicalInterpretation,
        assessment: DailyTechnicalAssessment,
    ) -> DailyTechnicalStrategy: ...


@dataclass(frozen=True, slots=True)
class _DetachedAssessmentSemantics:
    schema_version: str
    canonical_instrument_id: tuple[tuple[str, object], ...]
    analysis_as_of: datetime
    source_interpretation_fingerprint: str
    assessment_policy_identity: TechnicalPolicyIdentity
    outcome: DailyTechnicalAssessmentOutcome
    findings: tuple[DailyTechnicalAssessmentFinding, ...]
    fingerprint: str
    complete_source_projection: str


def _detach_assessment_semantics(
    assessment: DailyTechnicalAssessment,
) -> _DetachedAssessmentSemantics:
    findings = tuple(
        DailyTechnicalAssessmentFinding(
            item.kind,
            item.code,
            tuple(item.comparison_evidence_ids),
        )
        for item in assessment.findings
    )
    return _DetachedAssessmentSemantics(
        schema_version=assessment.schema_version,
        canonical_instrument_id=tuple(
            sorted(assessment.canonical_instrument_id.to_dict().items())
        ),
        analysis_as_of=assessment.analysis_as_of,
        source_interpretation_fingerprint=(
            assessment.source_interpretation_fingerprint
        ),
        assessment_policy_identity=copy_technical_policy_identity(
            assessment.assessment_policy_identity
        ),
        outcome=assessment.outcome,
        findings=findings,
        fingerprint=assessment.fingerprint,
        complete_source_projection=json.dumps(
            assessment.to_dict(), sort_keys=True, separators=(",", ":")
        ),
    )


def derive_daily_technical_strategy(
    interpretation: DailyTechnicalInterpretation,
    assessment: DailyTechnicalAssessment,
    policy: DailyTechnicalStrategyPolicy,
) -> DailyTechnicalStrategy:
    if type(interpretation) is not DailyTechnicalInterpretation:
        raise TypeError("interpretation must be an exact DailyTechnicalInterpretation")
    if type(assessment) is not DailyTechnicalAssessment:
        raise TypeError("assessment must be an exact DailyTechnicalAssessment")
    interpretation._validate()
    assessment._validate()
    interpretation_before = _detach_interpretation_semantics(interpretation)
    assessment_before = _detach_assessment_semantics(assessment)
    interpretation_policy = interpretation_before.interpretation_policy_identity
    if (
        interpretation_policy.policy_id != "classic_daily_technical"
        or interpretation_policy.behavioral_revision != "1.0.0"
        or interpretation_policy.configuration_schema
        != CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA
        or type(interpretation_policy.configuration)
        is not ClassicDailyTechnicalInterpretationConfiguration
    ):
        raise ValueError(
            "interpretation policy is incompatible with classic assessment"
        )
    assessment_policy = assessment_before.assessment_policy_identity
    if (
        assessment_policy.policy_kind
        is not TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT
    ):
        raise ValueError("assessment policy identity kind is invalid")
    if type(assessment_policy.configuration) is not (
        ClassicDailyTechnicalAssessmentConfiguration
    ):
        raise ValueError("assessment policy configuration type is unsupported")
    if (
        assessment_before.canonical_instrument_id
        != interpretation_before.canonical_instrument_id
        or assessment_before.analysis_as_of != interpretation_before.analysis_as_of
        or assessment_before.source_interpretation_fingerprint
        != interpretation_before.fingerprint
    ):
        raise ValueError("interpretation and assessment source chain is incoherent")
    if any(
        evidence_id not in interpretation_before.comparison_evidence_ids
        for finding in assessment_before.findings
        for evidence_id in finding.comparison_evidence_ids
    ):
        raise ValueError("assessment finding references missing comparison evidence")
    expected_findings = build_classic_assessment_findings(
        interpretation_before  # type: ignore[arg-type]
    )
    if assessment_before.findings != expected_findings:
        raise ValueError("assessment findings are not complete and exact")
    expected_outcome = classic_assessment_outcome(
        interpretation_before,  # type: ignore[arg-type]
        expected_findings,
    )
    if assessment_before.outcome is not expected_outcome:
        raise ValueError("assessment outcome does not match precedence rules")
    try:
        policy_before = copy_technical_policy_identity(policy.policy_identity)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("strategy policy identity is invalid") from exc
    if policy_before.policy_kind is not TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY:
        raise ValueError("strategy policy identity kind is invalid")
    result = policy.determine(interpretation, assessment)
    interpretation._validate()
    assessment._validate()
    interpretation_after = _detach_interpretation_semantics(interpretation)
    assessment_after = _detach_assessment_semantics(assessment)
    if interpretation_after != interpretation_before:
        raise ValueError("source interpretation drifted during invocation")
    if assessment_after != assessment_before:
        raise ValueError("source assessment drifted during invocation")
    try:
        policy_after = copy_technical_policy_identity(policy.policy_identity)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("post-call strategy policy identity is invalid") from exc
    if policy_before.to_dict() != policy_after.to_dict():
        raise ValueError("strategy policy identity drifted during invocation")
    if type(result) is not DailyTechnicalStrategy:
        raise TypeError("policy must return an exact DailyTechnicalStrategy")
    result._validate()
    if result.strategy_policy_identity.to_dict() != policy_before.to_dict():
        raise ValueError("strategy does not correspond to pre-call policy identity")
    result_instrument = tuple(sorted(result.canonical_instrument_id.to_dict().items()))
    if (
        result_instrument != interpretation_before.canonical_instrument_id
        or result_instrument != assessment_before.canonical_instrument_id
        or result.analysis_as_of != interpretation_before.analysis_as_of
        or result.analysis_as_of != assessment_before.analysis_as_of
        or result.source_assessment_fingerprint != assessment_before.fingerprint
    ):
        raise ValueError("strategy source correspondence is invalid")
    return result


__all__ = [
    "DailyTechnicalStrategyPolicy",
    "derive_daily_technical_strategy",
    "DAILY_TECHNICAL_STRATEGY_SCHEMA",
    "DailyTechnicalStrategy",
    "DailyTechnicalStrategyMode",
    "DailyTechnicalStrategyRuleCode",
]
