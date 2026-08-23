"""Application orchestration for the fixed daily technical Strategy profile."""

from __future__ import annotations

from market_platform.application.daily_technical_strategy import (
    DailyTechnicalStrategyApplicationRequest,
    DailyTechnicalStrategyApplicationResponse,
)
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessmentPolicy,
    assess_daily_technical_interpretation,
)
from market_platform.research.daily_technical_interpretation import (
    DailyTechnicalInterpretationPolicy,
    interpret_daily_technical_research,
)
from market_platform.research.daily_technical_strategy import (
    DailyTechnicalStrategyPolicy,
    derive_daily_technical_strategy,
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

_EXPECTED_INTERPRETATION_POLICY_IDENTITY = TechnicalPolicyIdentity(
    policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION,
    policy_id="classic_daily_technical",
    behavioral_revision="1.0.0",
    configuration_schema=(CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA),
    configuration=ClassicDailyTechnicalInterpretationConfiguration(),
)
_EXPECTED_ASSESSMENT_POLICY_IDENTITY = TechnicalPolicyIdentity(
    policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT,
    policy_id="classic_daily_technical_coherence",
    behavioral_revision="1.0.0",
    configuration_schema=CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
    configuration=ClassicDailyTechnicalAssessmentConfiguration(),
)
_EXPECTED_STRATEGY_POLICY_IDENTITY = TechnicalPolicyIdentity(
    policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY,
    policy_id="classic_daily_technical_strategy",
    behavioral_revision="1.0.0",
    configuration_schema=CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA,
    configuration=ClassicDailyTechnicalStrategyConfiguration(),
)


class DailyTechnicalStrategyApplicationService:
    """Compose the released daily technical domain boundaries once and in order."""

    __slots__ = (
        "_assessment_policy",
        "_interpretation_policy",
        "_strategy_policy",
    )

    def __init__(
        self,
        interpretation_policy: DailyTechnicalInterpretationPolicy,
        assessment_policy: DailyTechnicalAssessmentPolicy,
        strategy_policy: DailyTechnicalStrategyPolicy,
    ) -> None:
        if not isinstance(interpretation_policy, DailyTechnicalInterpretationPolicy):
            raise TypeError(
                "interpretation_policy must implement "
                "DailyTechnicalInterpretationPolicy"
            )
        if not isinstance(assessment_policy, DailyTechnicalAssessmentPolicy):
            raise TypeError(
                "assessment_policy must implement DailyTechnicalAssessmentPolicy"
            )
        if not isinstance(strategy_policy, DailyTechnicalStrategyPolicy):
            raise TypeError(
                "strategy_policy must implement DailyTechnicalStrategyPolicy"
            )
        self._interpretation_policy = interpretation_policy
        self._assessment_policy = assessment_policy
        self._strategy_policy = strategy_policy

    async def execute(
        self,
        request: DailyTechnicalStrategyApplicationRequest,
    ) -> DailyTechnicalStrategyApplicationResponse:
        """Execute the fixed v0.75 daily technical Strategy profile."""

        if type(request) is not DailyTechnicalStrategyApplicationRequest:
            raise TypeError(
                "request must be an exact DailyTechnicalStrategyApplicationRequest"
            )
        request._validate()

        identities = (
            self._interpretation_policy.identity,
            self._assessment_policy.identity,
            self._strategy_policy.policy_identity,
        )
        _require_expected_identity(
            "interpretation",
            identities[0],
            _EXPECTED_INTERPRETATION_POLICY_IDENTITY,
        )
        _require_expected_identity(
            "assessment",
            identities[1],
            _EXPECTED_ASSESSMENT_POLICY_IDENTITY,
        )
        _require_expected_identity(
            "strategy",
            identities[2],
            _EXPECTED_STRATEGY_POLICY_IDENTITY,
        )

        interpretation = interpret_daily_technical_research(
            request.verified_research,
            self._interpretation_policy,
        )
        assessment = assess_daily_technical_interpretation(
            interpretation,
            self._assessment_policy,
        )
        strategy = derive_daily_technical_strategy(
            interpretation,
            assessment,
            self._strategy_policy,
        )
        return DailyTechnicalStrategyApplicationResponse._create(
            request,
            interpretation,
            assessment,
            strategy,
        )


def _require_expected_identity(
    stage: str,
    actual: object,
    expected: TechnicalPolicyIdentity,
) -> None:
    if type(actual) is not TechnicalPolicyIdentity:
        raise ValueError(f"{stage} policy identity is invalid")
    if actual.to_dict() != expected.to_dict():
        raise ValueError(
            f"{stage} policy identity does not match the fixed application profile"
        )


__all__ = ["DailyTechnicalStrategyApplicationService"]
