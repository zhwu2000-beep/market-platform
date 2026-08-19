"""Classic v1 reference policies for daily technical research."""

from __future__ import annotations

from dataclasses import dataclass, field

from market_platform.research.daily_instrument_integrity import (
    IntegrityCheckedDailyTechnicalResearchResult,
)
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessment,
    DailyTechnicalAssessmentOutcome,
    build_classic_assessment_findings,
    classic_assessment_outcome,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalDirectionalState,
    DailyTechnicalInterpretation,
    build_classic_comparison_evidence,
    classic_states,
)
from market_platform.research.daily_technical_strategy import (
    DailyTechnicalStrategy,
    DailyTechnicalStrategyMode,
    DailyTechnicalStrategyRuleCode,
)
from market_platform.research.technical_policy import (
    CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
    CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA,
    CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA,
    ClassicDailyTechnicalAssessmentConfiguration,
    ClassicDailyTechnicalInterpretationConfiguration,
    ClassicDailyTechnicalStrategyConfiguration,
    TechnicalPolicyIdentity,
    TechnicalPolicyKind,
)


def _classic_strategy_semantics(
    interpretation: DailyTechnicalInterpretation,
    assessment: DailyTechnicalAssessment,
) -> tuple[DailyTechnicalStrategyMode, DailyTechnicalStrategyRuleCode]:
    no_active_strategy = {
        DailyTechnicalAssessmentOutcome.INSUFFICIENT_DATA: (
            DailyTechnicalStrategyRuleCode.INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY
        ),
        DailyTechnicalAssessmentOutcome.MIXED: (
            DailyTechnicalStrategyRuleCode.MIXED_NO_ACTIVE_STRATEGY
        ),
        DailyTechnicalAssessmentOutcome.CAUTION: (
            DailyTechnicalStrategyRuleCode.CAUTION_NO_ACTIVE_STRATEGY
        ),
    }
    rule_code = no_active_strategy.get(assessment.outcome)
    if rule_code is not None:
        return DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY, rule_code
    if assessment.outcome is DailyTechnicalAssessmentOutcome.ALIGNED:
        aligned = {
            (
                DailyTechnicalDirectionalState.POSITIVE,
                DailyTechnicalDirectionalState.POSITIVE,
            ): (
                DailyTechnicalStrategyMode.POSITIVE_DIRECTIONAL_CONTINUATION,
                DailyTechnicalStrategyRuleCode.ALIGNED_POSITIVE_CONTINUATION,
            ),
            (
                DailyTechnicalDirectionalState.NEGATIVE,
                DailyTechnicalDirectionalState.NEGATIVE,
            ): (
                DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
                DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION,
            ),
        }
        directions = (
            interpretation.trend_direction,
            interpretation.momentum_direction,
        )
        try:
            return aligned[directions]
        except KeyError as exc:
            raise ValueError(
                "aligned assessment has unsupported direction semantics"
            ) from exc
    raise ValueError("assessment outcome is unsupported by classic strategy")


@dataclass(frozen=True, slots=True)
class ClassicDailyTechnicalInterpretationPolicy:
    configuration: ClassicDailyTechnicalInterpretationConfiguration = field(
        default_factory=ClassicDailyTechnicalInterpretationConfiguration
    )
    _identity: TechnicalPolicyIdentity = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.configuration)
            is not ClassicDailyTechnicalInterpretationConfiguration
        ):
            raise TypeError(
                "configuration must be an exact classic interpretation configuration"
            )
        configuration = ClassicDailyTechnicalInterpretationConfiguration(
            rsi_neutral=self.configuration.rsi_neutral,
            rsi_elevated=self.configuration.rsi_elevated,
            rsi_depressed=self.configuration.rsi_depressed,
            realized_volatility_low=self.configuration.realized_volatility_low,
            realized_volatility_high=self.configuration.realized_volatility_high,
            ema20_extension_band_percent=(
                self.configuration.ema20_extension_band_percent
            ),
        )
        object.__setattr__(self, "configuration", configuration)
        object.__setattr__(
            self,
            "_identity",
            TechnicalPolicyIdentity(
                policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION,
                policy_id="classic_daily_technical",
                behavioral_revision="1.0.0",
                configuration_schema=(
                    CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA
                ),
                configuration=configuration,
            ),
        )

    @property
    def identity(self) -> TechnicalPolicyIdentity:
        return self._identity

    def interpret(
        self, verified_research: IntegrityCheckedDailyTechnicalResearchResult
    ) -> DailyTechnicalInterpretation:
        if type(verified_research) is not IntegrityCheckedDailyTechnicalResearchResult:
            raise TypeError(
                "verified_research must be an exact integrity-checked result"
            )
        verified_research._validate()
        snapshot = verified_research.research.snapshot
        trend, momentum, volatility, extension = classic_states(
            snapshot, self.configuration
        )
        integrity = verified_research.integrity
        return DailyTechnicalInterpretation(
            canonical_instrument_id=integrity.canonical_instrument_id,
            requested_trading_identity=integrity.requested_trading_identity,
            analysis_as_of=verified_research.research.request.analysis_as_of,
            source_technical_analysis_snapshot_fingerprint=snapshot.fingerprint,
            source_daily_instrument_integrity_evidence_fingerprint=(
                integrity.fingerprint
            ),
            interpretation_policy_identity=self.identity,
            source_quality=snapshot.quality,
            source_warnings=snapshot.warnings,
            trend_direction=trend,
            momentum_direction=momentum,
            volatility_state=volatility,
            extension_state=extension,
            comparison_evidence=build_classic_comparison_evidence(
                snapshot, self.configuration
            ),
        )


@dataclass(frozen=True, slots=True)
class ClassicDailyTechnicalAssessmentPolicy:
    configuration: ClassicDailyTechnicalAssessmentConfiguration = field(
        default_factory=ClassicDailyTechnicalAssessmentConfiguration
    )
    _identity: TechnicalPolicyIdentity = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.configuration) is not ClassicDailyTechnicalAssessmentConfiguration:
            raise TypeError(
                "configuration must be an exact classic assessment configuration"
            )
        configuration = ClassicDailyTechnicalAssessmentConfiguration()
        object.__setattr__(self, "configuration", configuration)
        object.__setattr__(
            self,
            "_identity",
            TechnicalPolicyIdentity(
                policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT,
                policy_id="classic_daily_technical_coherence",
                behavioral_revision="1.0.0",
                configuration_schema=(
                    CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA
                ),
                configuration=configuration,
            ),
        )

    @property
    def identity(self) -> TechnicalPolicyIdentity:
        return self._identity

    def assess(
        self, interpretation: DailyTechnicalInterpretation
    ) -> DailyTechnicalAssessment:
        if type(interpretation) is not DailyTechnicalInterpretation:
            raise TypeError(
                "interpretation must be an exact DailyTechnicalInterpretation"
            )
        interpretation._validate()
        findings = build_classic_assessment_findings(interpretation)
        return DailyTechnicalAssessment(
            canonical_instrument_id=interpretation.canonical_instrument_id,
            analysis_as_of=interpretation.analysis_as_of,
            source_interpretation_fingerprint=interpretation.fingerprint,
            assessment_policy_identity=self.identity,
            outcome=classic_assessment_outcome(interpretation, findings),
            findings=findings,
        )


@dataclass(frozen=True, slots=True)
class ClassicDailyTechnicalStrategyPolicy:
    configuration: ClassicDailyTechnicalStrategyConfiguration = field(
        default_factory=ClassicDailyTechnicalStrategyConfiguration
    )
    _identity: TechnicalPolicyIdentity = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.configuration) is not ClassicDailyTechnicalStrategyConfiguration:
            raise TypeError(
                "configuration must be an exact classic strategy configuration"
            )
        configuration = ClassicDailyTechnicalStrategyConfiguration()
        object.__setattr__(self, "configuration", configuration)
        object.__setattr__(
            self,
            "_identity",
            TechnicalPolicyIdentity(
                policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY,
                policy_id="classic_daily_technical_strategy",
                behavioral_revision="1.0.0",
                configuration_schema=(
                    CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA
                ),
                configuration=configuration,
            ),
        )

    @property
    def policy_identity(self) -> TechnicalPolicyIdentity:
        return self._identity

    def determine(
        self,
        interpretation: DailyTechnicalInterpretation,
        assessment: DailyTechnicalAssessment,
    ) -> DailyTechnicalStrategy:
        if type(interpretation) is not DailyTechnicalInterpretation:
            raise TypeError(
                "interpretation must be an exact DailyTechnicalInterpretation"
            )
        if type(assessment) is not DailyTechnicalAssessment:
            raise TypeError("assessment must be an exact DailyTechnicalAssessment")
        mode, rule_code = _classic_strategy_semantics(interpretation, assessment)
        return DailyTechnicalStrategy(
            canonical_instrument_id=interpretation.canonical_instrument_id,
            analysis_as_of=interpretation.analysis_as_of,
            source_assessment_fingerprint=assessment.fingerprint,
            strategy_policy_identity=self.policy_identity,
            mode=mode,
            rule_code=rule_code,
        )


__all__ = [
    "ClassicDailyTechnicalInterpretationPolicy",
    "ClassicDailyTechnicalAssessmentPolicy",
]
