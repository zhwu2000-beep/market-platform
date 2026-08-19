from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from types import SimpleNamespace

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.classic_daily_technical import (
    ClassicDailyTechnicalStrategyPolicy,
)
from market_platform.research.daily_technical_assessment import (
    DailyTechnicalAssessment,
    DailyTechnicalAssessmentFinding,
    DailyTechnicalAssessmentFindingKind,
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
    DAILY_TECHNICAL_STRATEGY_SCHEMA,
    DailyTechnicalStrategy,
    DailyTechnicalStrategyMode,
    DailyTechnicalStrategyPolicy,
    DailyTechnicalStrategyRuleCode,
    derive_daily_technical_strategy,
)
from market_platform.research.technical_analysis import TechnicalAnalysisQuality
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
from market_platform.trading import TradingInstrumentIdentity

_ASSESSMENT_FINGERPRINT = "sha256:" + "1" * 64


def _strategy_identity(
    *,
    policy_id: str = "classic_daily_technical_strategy",
    revision: str = "1.0.0",
) -> TechnicalPolicyIdentity:
    return TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY,
        policy_id=policy_id,
        behavioral_revision=revision,
        configuration_schema=(CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA),
        configuration=ClassicDailyTechnicalStrategyConfiguration(),
    )


def _interpretation_identity(
    *,
    policy_id: str = "classic_daily_technical",
    revision: str = "1.0.0",
) -> TechnicalPolicyIdentity:
    return TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION,
        policy_id=policy_id,
        behavioral_revision=revision,
        configuration_schema=(
            CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA
        ),
        configuration=ClassicDailyTechnicalInterpretationConfiguration(),
    )


def _assessment_identity() -> TechnicalPolicyIdentity:
    return TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT,
        policy_id="classic_daily_technical_coherence",
        behavioral_revision="1.0.0",
        configuration_schema=(CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA),
        configuration=ClassicDailyTechnicalAssessmentConfiguration(),
    )


def _strategy(
    *,
    canonical_instrument_id: CanonicalInstrumentId | object | None = None,
    analysis_as_of: datetime = datetime(2026, 8, 18, 8, 30, tzinfo=UTC),
    source_assessment_fingerprint: str = _ASSESSMENT_FINGERPRINT,
    strategy_policy_identity: TechnicalPolicyIdentity | None = None,
    mode: DailyTechnicalStrategyMode = (
        DailyTechnicalStrategyMode.POSITIVE_DIRECTIONAL_CONTINUATION
    ),
    rule_code: DailyTechnicalStrategyRuleCode = (
        DailyTechnicalStrategyRuleCode.ALIGNED_POSITIVE_CONTINUATION
    ),
) -> DailyTechnicalStrategy:
    return DailyTechnicalStrategy(
        canonical_instrument_id=(
            CanonicalInstrumentId("us_equity.aapl")
            if canonical_instrument_id is None
            else canonical_instrument_id
        ),
        analysis_as_of=analysis_as_of,
        source_assessment_fingerprint=source_assessment_fingerprint,
        strategy_policy_identity=(
            _strategy_identity()
            if strategy_policy_identity is None
            else strategy_policy_identity
        ),
        mode=mode,
        rule_code=rule_code,
    )


def _interpretation(
    *,
    snapshot_changes: dict[str, object] | None = None,
    **changes: object,
) -> DailyTechnicalInterpretation:
    configuration = ClassicDailyTechnicalInterpretationConfiguration()
    snapshot_values: dict[str, object] = {
        "ema_8": 12.0,
        "ema_20": 11.0,
        "latest_close": 20.0,
        "ema_144": 10.0,
        "ema_169": 9.0,
        "macd_line": 2.0,
        "macd_signal": 1.0,
        "rsi_14": 60.0,
        "realized_volatility": 0.2,
        "distance_from_ema20_percent": 0.0,
    }
    snapshot_values.update(snapshot_changes or {})
    distance = snapshot_values.pop("distance_from_ema20_percent")
    snapshot = SimpleNamespace(
        **snapshot_values,
        volatility_references=SimpleNamespace(
            distance_from_ema20_percent=distance
        ),
    )
    trend, momentum, volatility, extension = classic_states(
        snapshot,
        configuration,  # type: ignore[arg-type]
    )
    values: dict[str, object] = {
        "canonical_instrument_id": CanonicalInstrumentId("us_equity.aapl"),
        "requested_trading_identity": TradingInstrumentIdentity("AAPL", "NASDAQ"),
        "analysis_as_of": datetime(2026, 8, 18, 8, 30, tzinfo=UTC),
        "source_technical_analysis_snapshot_fingerprint": "sha256:" + "a" * 64,
        "source_daily_instrument_integrity_evidence_fingerprint": (
            "sha256:" + "b" * 64
        ),
        "interpretation_policy_identity": _interpretation_identity(),
        "source_quality": TechnicalAnalysisQuality.COMPLETE,
        "source_warnings": (),
        "trend_direction": trend,
        "momentum_direction": momentum,
        "volatility_state": volatility,
        "extension_state": extension,
        "comparison_evidence": build_classic_comparison_evidence(
            snapshot,
            configuration,  # type: ignore[arg-type]
        ),
    }
    values.update(changes)
    return DailyTechnicalInterpretation(**values)  # type: ignore[arg-type]


def _assessment(
    interpretation: DailyTechnicalInterpretation,
    **changes: object,
) -> DailyTechnicalAssessment:
    findings = build_classic_assessment_findings(interpretation)
    values: dict[str, object] = {
        "canonical_instrument_id": interpretation.canonical_instrument_id,
        "analysis_as_of": interpretation.analysis_as_of,
        "source_interpretation_fingerprint": interpretation.fingerprint,
        "assessment_policy_identity": _assessment_identity(),
        "outcome": classic_assessment_outcome(interpretation, findings),
        "findings": findings,
    }
    values.update(changes)
    return DailyTechnicalAssessment(**values)  # type: ignore[arg-type]


def _source_chain() -> tuple[DailyTechnicalInterpretation, DailyTechnicalAssessment]:
    interpretation = _interpretation()
    return interpretation, _assessment(interpretation)


def _source_chain_for_snapshot(
    **snapshot_changes: object,
) -> tuple[DailyTechnicalInterpretation, DailyTechnicalAssessment]:
    interpretation = _interpretation(snapshot_changes=snapshot_changes)
    return interpretation, _assessment(interpretation)


class _TestStrategyPolicy:
    def __init__(
        self,
        *,
        identity: TechnicalPolicyIdentity | None = None,
        result_changes: dict[str, object] | None = None,
        mutation: Callable[[], None] | None = None,
        error: Exception | None = None,
        returned_result: object | None = None,
    ) -> None:
        self._policy_identity = identity or _strategy_identity()
        self.result_changes = result_changes or {}
        self.mutation = mutation
        self.error = error
        self.returned_result = returned_result
        self.calls = 0
        self.received: (
            tuple[DailyTechnicalInterpretation, DailyTechnicalAssessment] | None
        ) = None

    @property
    def policy_identity(self) -> TechnicalPolicyIdentity:
        return self._policy_identity

    def determine(
        self,
        interpretation: DailyTechnicalInterpretation,
        assessment: DailyTechnicalAssessment,
    ) -> DailyTechnicalStrategy:
        self.calls += 1
        self.received = (interpretation, assessment)
        if self.mutation is not None:
            self.mutation()
        if self.error is not None:
            raise self.error
        if self.returned_result is not None:
            return self.returned_result  # type: ignore[return-value]
        values: dict[str, object] = {
            "canonical_instrument_id": interpretation.canonical_instrument_id,
            "analysis_as_of": interpretation.analysis_as_of,
            "source_assessment_fingerprint": assessment.fingerprint,
            "strategy_policy_identity": self.policy_identity,
            "mode": DailyTechnicalStrategyMode.POSITIVE_DIRECTIONAL_CONTINUATION,
            "rule_code": (DailyTechnicalStrategyRuleCode.ALIGNED_POSITIVE_CONTINUATION),
        }
        values.update(self.result_changes)
        return DailyTechnicalStrategy(**values)  # type: ignore[arg-type]


def test_derivation_rejects_missing_assessment_evidence_reference() -> None:
    interpretation = _interpretation()
    missing_reference = DailyTechnicalAssessmentFinding(
        DailyTechnicalAssessmentFindingKind.CAUTION,
        "fabricated_caution",
        ("missing_evidence",),
    )
    assessment = _assessment(
        interpretation,
        outcome=DailyTechnicalAssessmentOutcome.CAUTION,
        findings=(missing_reference,),
    )
    with pytest.raises(ValueError, match="missing comparison evidence"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )


def test_derivation_rejects_coherently_refingerprinted_assessment_semantics() -> None:
    interpretation, assessment = _source_chain()
    forged_finding = DailyTechnicalAssessmentFinding(
        DailyTechnicalAssessmentFindingKind.CAUTION,
        "fabricated_caution",
        (),
    )
    object.__setattr__(assessment, "findings", (forged_finding,))
    object.__setattr__(assessment, "outcome", DailyTechnicalAssessmentOutcome.CAUTION)
    object.__setattr__(
        assessment,
        "fingerprint",
        canonical_fingerprint(assessment._fingerprint_payload()),
    )
    assessment._validate()

    with pytest.raises(ValueError, match="findings are not complete and exact"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )


def test_derivation_rejects_incorrect_assessment_findings() -> None:
    interpretation = _interpretation()
    incorrect = DailyTechnicalAssessmentFinding(
        DailyTechnicalAssessmentFindingKind.CAUTION,
        "source_quality_degraded",
        (),
    )
    assessment = _assessment(
        interpretation,
        outcome=DailyTechnicalAssessmentOutcome.CAUTION,
        findings=(incorrect,),
    )
    with pytest.raises(ValueError, match="findings are not complete and exact"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )


def test_derivation_rejects_incorrect_assessment_outcome() -> None:
    interpretation = _interpretation()
    assessment = _assessment(
        interpretation,
        outcome=DailyTechnicalAssessmentOutcome.MIXED,
    )
    with pytest.raises(ValueError, match="outcome does not match"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )


def test_derivation_rejects_unsupported_and_malformed_source_identities() -> None:
    incompatible_interpretation = _interpretation(
        interpretation_policy_identity=_interpretation_identity(
            policy_id="other_interpretation_policy"
        )
    )
    with pytest.raises(ValueError, match="incompatible with classic assessment"):
        derive_daily_technical_strategy(
            incompatible_interpretation,
            _assessment(incompatible_interpretation),
            _TestStrategyPolicy(),
        )

    interpretation, assessment = _source_chain()
    object.__setattr__(
        interpretation.interpretation_policy_identity,
        "fingerprint",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="policy identity fingerprint"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )

    interpretation, assessment = _source_chain()
    object.__setattr__(
        assessment.assessment_policy_identity,
        "policy_kind",
        TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY,
    )
    with pytest.raises(ValueError, match="do not correspond"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )

    interpretation, assessment = _source_chain()
    object.__setattr__(
        assessment.assessment_policy_identity,
        "fingerprint",
        "sha256:" + "0" * 64,
    )
    with pytest.raises(ValueError, match="policy identity fingerprint"):
        derive_daily_technical_strategy(
            interpretation, assessment, _TestStrategyPolicy()
        )


def test_derivation_validates_strategy_policy_identity_before_call() -> None:
    interpretation, assessment = _source_chain()
    wrong_kind = _TestStrategyPolicy(identity=_assessment_identity())
    with pytest.raises(ValueError, match="strategy policy identity kind"):
        derive_daily_technical_strategy(interpretation, assessment, wrong_kind)
    assert wrong_kind.calls == 0

    malformed_identity = _strategy_identity()
    object.__setattr__(malformed_identity, "fingerprint", "sha256:" + "0" * 64)
    malformed = _TestStrategyPolicy(identity=malformed_identity)
    with pytest.raises(ValueError, match="strategy policy identity is invalid"):
        derive_daily_technical_strategy(interpretation, assessment, malformed)
    assert malformed.calls == 0


def test_derivation_does_not_require_classic_strategy_policy_id() -> None:
    interpretation, assessment = _source_chain()
    policy = _TestStrategyPolicy(
        identity=_strategy_identity(policy_id="alternative_strategy_policy")
    )
    result = derive_daily_technical_strategy(interpretation, assessment, policy)
    assert result.strategy_policy_identity.policy_id == "alternative_strategy_policy"
    assert policy.calls == 1


def test_derivation_rejects_strategy_policy_identity_drift() -> None:
    interpretation, assessment = _source_chain()
    policy = _TestStrategyPolicy()

    def drift_identity() -> None:
        object.__setattr__(
            policy._policy_identity, "policy_id", "drifted_strategy_policy"
        )
        object.__setattr__(
            policy._policy_identity,
            "fingerprint",
            canonical_fingerprint(policy._policy_identity._fingerprint_payload()),
        )

    policy.mutation = drift_identity
    with pytest.raises(ValueError, match="policy identity drifted"):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_rejects_persistent_interpretation_mutation() -> None:
    interpretation, assessment = _source_chain()

    def mutate() -> None:
        object.__setattr__(
            interpretation,
            "source_quality",
            TechnicalAnalysisQuality.DEGRADED,
        )

    policy = _TestStrategyPolicy(mutation=mutate)
    with pytest.raises(ValueError):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_rejects_persistent_assessment_mutation() -> None:
    interpretation, assessment = _source_chain()

    def mutate() -> None:
        object.__setattr__(assessment, "outcome", DailyTechnicalAssessmentOutcome.MIXED)

    policy = _TestStrategyPolicy(mutation=mutate)
    with pytest.raises(ValueError):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_rejects_coherently_refingerprinted_interpretation_drift() -> None:
    interpretation, assessment = _source_chain()

    def mutate() -> None:
        object.__setattr__(
            interpretation,
            "source_quality",
            TechnicalAnalysisQuality.DEGRADED,
        )
        object.__setattr__(
            interpretation,
            "fingerprint",
            canonical_fingerprint(interpretation._fingerprint_payload()),
        )
        interpretation._validate()

    policy = _TestStrategyPolicy(mutation=mutate)
    with pytest.raises(ValueError, match="source interpretation drifted"):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_rejects_coherently_refingerprinted_assessment_drift() -> None:
    interpretation, assessment = _source_chain()

    def mutate() -> None:
        object.__setattr__(assessment, "outcome", DailyTechnicalAssessmentOutcome.MIXED)
        object.__setattr__(
            assessment,
            "fingerprint",
            canonical_fingerprint(assessment._fingerprint_payload()),
        )
        assessment._validate()

    policy = _TestStrategyPolicy(mutation=mutate)
    with pytest.raises(ValueError, match="source assessment drifted"):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_accepts_temporary_source_mutation_then_exact_reversion() -> None:
    interpretation, assessment = _source_chain()

    def mutate_then_restore() -> None:
        original_interpretation = interpretation.source_quality
        original_assessment = assessment.outcome
        object.__setattr__(
            interpretation,
            "source_quality",
            TechnicalAnalysisQuality.DEGRADED,
        )
        object.__setattr__(assessment, "outcome", DailyTechnicalAssessmentOutcome.MIXED)
        object.__setattr__(interpretation, "source_quality", original_interpretation)
        object.__setattr__(assessment, "outcome", original_assessment)

    policy = _TestStrategyPolicy(mutation=mutate_then_restore)
    derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


@pytest.mark.parametrize(
    "result_changes",
    [
        {"canonical_instrument_id": CanonicalInstrumentId("us_equity.msft")},
        {"analysis_as_of": datetime(2026, 8, 19, 8, 30, tzinfo=UTC)},
        {"source_assessment_fingerprint": "sha256:" + "d" * 64},
    ],
)
def test_derivation_rejects_strategy_source_mismatches(
    result_changes: dict[str, object],
) -> None:
    interpretation, assessment = _source_chain()
    policy = _TestStrategyPolicy(result_changes=result_changes)
    with pytest.raises(ValueError, match="strategy source correspondence"):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_rejects_strategy_result_policy_identity_mismatch() -> None:
    interpretation, assessment = _source_chain()
    policy = _TestStrategyPolicy(
        result_changes={
            "strategy_policy_identity": _strategy_identity(
                policy_id="other_strategy_policy"
            )
        }
    )
    with pytest.raises(ValueError, match="pre-call policy identity"):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_derivation_accepts_structurally_valid_alternative_strategy_semantics() -> None:
    interpretation, assessment = _source_chain()
    assert assessment.outcome is DailyTechnicalAssessmentOutcome.ALIGNED
    policy = _TestStrategyPolicy(
        result_changes={
            "mode": DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
            "rule_code": (DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION),
        }
    )

    result = derive_daily_technical_strategy(interpretation, assessment, policy)

    assert result.mode is DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION
    assert result.rule_code is (
        DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION
    )
    assert policy.calls == 1


def test_derivation_propagates_policy_exception_without_retry() -> None:
    interpretation, assessment = _source_chain()
    policy = _TestStrategyPolicy(error=RuntimeError("strategy policy failed"))
    with pytest.raises(RuntimeError, match="strategy policy failed"):
        derive_daily_technical_strategy(interpretation, assessment, policy)
    assert policy.calls == 1


def test_strategy_policy_kind_and_empty_configuration_are_closed() -> None:
    assert [item.value for item in TechnicalPolicyKind] == [
        "daily_technical_interpretation",
        "daily_technical_assessment",
        "daily_technical_strategy",
    ]
    configuration = ClassicDailyTechnicalStrategyConfiguration()
    assert configuration.to_dict() == {}
    assert not hasattr(configuration, "__dict__")


def test_strategy_policy_identity_is_deterministic_and_canonical() -> None:
    first = _strategy_identity()
    second = _strategy_identity()
    expected = {
        "schema_version": "technical_policy_identity/v1",
        "policy_kind": "daily_technical_strategy",
        "policy_id": "classic_daily_technical_strategy",
        "behavioral_revision": "1.0.0",
        "configuration_schema": ("classic_daily_technical_strategy_configuration/v1"),
        "configuration": {},
        "fingerprint": (
            "sha256:acbdd8c9ac7ba7d336f5f5e74b7484b05d0fc15b3a6f24bc81288d1fc8ea817e"
        ),
    }
    assert first.to_dict() == expected
    assert second.to_dict() == expected
    assert first.fingerprint == second.fingerprint


def test_classic_strategy_policy_has_exact_deterministic_identity_and_configuration(
) -> None:
    first = ClassicDailyTechnicalStrategyPolicy()
    second = ClassicDailyTechnicalStrategyPolicy()

    assert isinstance(first, DailyTechnicalStrategyPolicy)
    assert type(first.configuration) is ClassicDailyTechnicalStrategyConfiguration
    assert first.configuration.to_dict() == {}
    assert not hasattr(first.configuration, "__dict__")
    assert first.policy_identity.to_dict() == _strategy_identity().to_dict()
    assert second.policy_identity.to_dict() == first.policy_identity.to_dict()
    assert second.policy_identity.fingerprint == first.policy_identity.fingerprint


@pytest.mark.parametrize(
    (
        "snapshot_changes",
        "trend_direction",
        "momentum_direction",
        "outcome",
        "mode",
        "rule_code",
    ),
    [
        (
            {},
            DailyTechnicalDirectionalState.POSITIVE,
            DailyTechnicalDirectionalState.POSITIVE,
            DailyTechnicalAssessmentOutcome.ALIGNED,
            DailyTechnicalStrategyMode.POSITIVE_DIRECTIONAL_CONTINUATION,
            DailyTechnicalStrategyRuleCode.ALIGNED_POSITIVE_CONTINUATION,
        ),
        (
            {
                "ema_8": 8.0,
                "ema_20": 11.0,
                "latest_close": 5.0,
                "ema_144": 10.0,
                "ema_169": 9.0,
                "macd_line": -2.0,
                "macd_signal": -1.0,
                "rsi_14": 40.0,
            },
            DailyTechnicalDirectionalState.NEGATIVE,
            DailyTechnicalDirectionalState.NEGATIVE,
            DailyTechnicalAssessmentOutcome.ALIGNED,
            DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
            DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION,
        ),
        (
            {"latest_close": 5.0},
            DailyTechnicalDirectionalState.MIXED,
            DailyTechnicalDirectionalState.POSITIVE,
            DailyTechnicalAssessmentOutcome.MIXED,
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.MIXED_NO_ACTIVE_STRATEGY,
        ),
        (
            {"rsi_14": 75.0},
            DailyTechnicalDirectionalState.POSITIVE,
            DailyTechnicalDirectionalState.POSITIVE,
            DailyTechnicalAssessmentOutcome.CAUTION,
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            DailyTechnicalStrategyRuleCode.CAUTION_NO_ACTIVE_STRATEGY,
        ),
        (
            {"macd_line": None},
            DailyTechnicalDirectionalState.POSITIVE,
            DailyTechnicalDirectionalState.UNAVAILABLE,
            DailyTechnicalAssessmentOutcome.INSUFFICIENT_DATA,
            DailyTechnicalStrategyMode.NO_ACTIVE_STRATEGY,
            (
                DailyTechnicalStrategyRuleCode
                .INSUFFICIENT_DATA_NO_ACTIVE_STRATEGY
            ),
        ),
    ],
)
def test_classic_strategy_policy_implements_exact_five_row_mapping(
    snapshot_changes: dict[str, object],
    trend_direction: DailyTechnicalDirectionalState,
    momentum_direction: DailyTechnicalDirectionalState,
    outcome: DailyTechnicalAssessmentOutcome,
    mode: DailyTechnicalStrategyMode,
    rule_code: DailyTechnicalStrategyRuleCode,
) -> None:
    interpretation, assessment = _source_chain_for_snapshot(**snapshot_changes)

    assert interpretation.trend_direction is trend_direction
    assert interpretation.momentum_direction is momentum_direction
    assert assessment.outcome is outcome

    result = ClassicDailyTechnicalStrategyPolicy().determine(
        interpretation, assessment
    )

    assert result.mode is mode
    assert result.rule_code is rule_code
    assert result.canonical_instrument_id.to_dict() == (
        interpretation.canonical_instrument_id.to_dict()
    )
    assert result.analysis_as_of == interpretation.analysis_as_of
    assert result.source_assessment_fingerprint == assessment.fingerprint
    assert result.strategy_policy_identity.to_dict() == (
        ClassicDailyTechnicalStrategyPolicy().policy_identity.to_dict()
    )
    assert set(result.to_dict()) == {
        "schema_version",
        "canonical_instrument_id",
        "analysis_as_of",
        "source_assessment_fingerprint",
        "strategy_policy_identity",
        "mode",
        "rule_code",
        "fingerprint",
    }


def test_classic_strategy_policy_fails_closed_for_forged_aligned_mixed_state(
) -> None:
    interpretation, assessment = _source_chain_for_snapshot(latest_close=5.0)
    assert interpretation.trend_direction is DailyTechnicalDirectionalState.MIXED
    assert assessment.outcome is DailyTechnicalAssessmentOutcome.MIXED

    object.__setattr__(
        assessment,
        "outcome",
        DailyTechnicalAssessmentOutcome.ALIGNED,
    )
    object.__setattr__(
        assessment,
        "fingerprint",
        canonical_fingerprint(assessment._fingerprint_payload()),
    )
    assessment._validate()

    with pytest.raises(
        ValueError, match="aligned assessment has unsupported direction semantics"
    ):
        ClassicDailyTechnicalStrategyPolicy().determine(interpretation, assessment)


def test_classic_strategy_policy_is_deterministic_and_succeeds_through_runner(
) -> None:
    interpretation, assessment = _source_chain()
    policy = ClassicDailyTechnicalStrategyPolicy()

    direct_first = policy.determine(interpretation, assessment)
    direct_second = policy.determine(interpretation, assessment)
    derived = derive_daily_technical_strategy(interpretation, assessment, policy)

    assert direct_first.to_dict() == direct_second.to_dict()
    assert direct_first.fingerprint == direct_second.fingerprint
    assert derived.to_dict() == direct_first.to_dict()
    assert derived.fingerprint == direct_first.fingerprint


def test_classic_strategy_semantics_do_not_depend_on_raw_indicator_values() -> None:
    baseline_interpretation, baseline_assessment = _source_chain()
    changed_interpretation, changed_assessment = _source_chain_for_snapshot(
        ema_8=13.0,
        ema_20=10.0,
        latest_close=21.0,
        ema_144=9.0,
        ema_169=8.0,
        macd_line=3.0,
        macd_signal=0.0,
        rsi_14=55.0,
        realized_volatility=0.22,
        distance_from_ema20_percent=1.0,
    )
    assert baseline_interpretation.fingerprint != changed_interpretation.fingerprint
    assert baseline_assessment.fingerprint != changed_assessment.fingerprint
    assert (
        baseline_interpretation.trend_direction,
        baseline_interpretation.momentum_direction,
        baseline_assessment.outcome,
    ) == (
        changed_interpretation.trend_direction,
        changed_interpretation.momentum_direction,
        changed_assessment.outcome,
    )

    policy = ClassicDailyTechnicalStrategyPolicy()
    baseline = policy.determine(baseline_interpretation, baseline_assessment)
    changed = policy.determine(changed_interpretation, changed_assessment)

    assert (baseline.mode, baseline.rule_code) == (changed.mode, changed.rule_code)


def test_released_interpretation_policy_identity_is_unchanged() -> None:
    identity = TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_INTERPRETATION,
        policy_id="classic_daily_technical",
        behavioral_revision="1.0.0",
        configuration_schema=(
            CLASSIC_DAILY_TECHNICAL_INTERPRETATION_CONFIGURATION_SCHEMA
        ),
        configuration=ClassicDailyTechnicalInterpretationConfiguration(),
    )
    assert identity.to_dict() == {
        "schema_version": "technical_policy_identity/v1",
        "policy_kind": "daily_technical_interpretation",
        "policy_id": "classic_daily_technical",
        "behavioral_revision": "1.0.0",
        "configuration_schema": (
            "classic_daily_technical_interpretation_configuration/v1"
        ),
        "configuration": {
            "rsi_neutral": 50.0,
            "rsi_elevated": 70.0,
            "rsi_depressed": 30.0,
            "realized_volatility_low": 0.15,
            "realized_volatility_high": 0.3,
            "ema20_extension_band_percent": 5.0,
        },
        "fingerprint": (
            "sha256:9d81e49a6d45d27071e804b46486ae247d71f650184e8032a792586807fc3d02"
        ),
    }


def test_released_assessment_policy_identity_is_unchanged() -> None:
    identity = TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT,
        policy_id="classic_daily_technical_coherence",
        behavioral_revision="1.0.0",
        configuration_schema=(CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA),
        configuration=ClassicDailyTechnicalAssessmentConfiguration(),
    )
    assert identity.to_dict() == {
        "schema_version": "technical_policy_identity/v1",
        "policy_kind": "daily_technical_assessment",
        "policy_id": "classic_daily_technical_coherence",
        "behavioral_revision": "1.0.0",
        "configuration_schema": ("classic_daily_technical_assessment_configuration/v1"),
        "configuration": {},
        "fingerprint": (
            "sha256:dbdf4bdb4eeb3880d5a6ad4f90d17d9934782f6e1d0d455cb3af93a20d74874f"
        ),
    }


@pytest.mark.parametrize(
    ("mode", "rule_code"),
    [
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
    ],
)
def test_all_valid_strategy_mode_rule_pairs(
    mode: DailyTechnicalStrategyMode,
    rule_code: DailyTechnicalStrategyRuleCode,
) -> None:
    strategy = _strategy(mode=mode, rule_code=rule_code)
    assert strategy.mode is mode
    assert strategy.rule_code is rule_code


def test_all_invalid_strategy_mode_rule_pairs_are_rejected() -> None:
    allowed = {
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
    for mode in DailyTechnicalStrategyMode:
        for rule_code in DailyTechnicalStrategyRuleCode:
            if (mode, rule_code) in allowed:
                continue
            with pytest.raises(ValueError, match="do not correspond"):
                _strategy(mode=mode, rule_code=rule_code)


def test_canonical_instrument_is_validated_and_detached() -> None:
    supplied = CanonicalInstrumentId("us_equity.aapl")
    strategy = _strategy(canonical_instrument_id=supplied)
    assert strategy.canonical_instrument_id is not supplied
    assert strategy.canonical_instrument_id.to_dict() == supplied.to_dict()

    object.__setattr__(supplied, "instrument_id", "malformed identity")
    assert strategy.canonical_instrument_id.instrument_id == "us_equity.aapl"
    strategy.to_dict()

    with pytest.raises(ValueError, match="canonical instrument ID"):
        _strategy(canonical_instrument_id="us_equity.aapl")

    malformed = CanonicalInstrumentId("us_equity.aapl")
    object.__setattr__(malformed, "instrument_id", "malformed identity")
    with pytest.raises(ValueError, match="canonical instrument ID"):
        _strategy(canonical_instrument_id=malformed)

    class CanonicalInstrumentIdSubclass(CanonicalInstrumentId):
        pass

    with pytest.raises(ValueError, match="canonical instrument ID"):
        _strategy(
            canonical_instrument_id=CanonicalInstrumentIdSubclass("us_equity.aapl")
        )


def test_analysis_as_of_requires_exact_canonical_utc_datetime() -> None:
    with pytest.raises(ValueError, match="canonical UTC"):
        _strategy(analysis_as_of=datetime(2026, 8, 18, 8, 30))
    with pytest.raises(ValueError, match="canonical UTC"):
        _strategy(
            analysis_as_of=datetime(
                2026,
                8,
                18,
                8,
                30,
                tzinfo=timezone(timedelta(hours=1)),
            )
        )

    class DatetimeSubclass(datetime):
        pass

    with pytest.raises(ValueError, match="canonical UTC"):
        _strategy(analysis_as_of=DatetimeSubclass(2026, 8, 18, 8, 30, tzinfo=UTC))


@pytest.mark.parametrize(
    "fingerprint",
    [
        "1" * 64,
        "sha256:" + "1" * 63,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
    ],
)
def test_source_assessment_fingerprint_must_be_canonical(
    fingerprint: str,
) -> None:
    with pytest.raises(ValueError, match="source_assessment_fingerprint"):
        _strategy(source_assessment_fingerprint=fingerprint)

    class FingerprintSubclass(str):
        pass

    with pytest.raises(ValueError, match="source_assessment_fingerprint"):
        _strategy(
            source_assessment_fingerprint=FingerprintSubclass(_ASSESSMENT_FINGERPRINT)
        )


def test_strategy_rejects_non_strategy_policy_kind() -> None:
    assessment_identity = TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_ASSESSMENT,
        policy_id="classic_daily_technical_coherence",
        behavioral_revision="1.0.0",
        configuration_schema=(CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA),
        configuration=ClassicDailyTechnicalAssessmentConfiguration(),
    )
    with pytest.raises(ValueError, match="policy kind"):
        _strategy(strategy_policy_identity=assessment_identity)


def test_strategy_rejects_policy_configuration_schema_mismatches() -> None:
    wrong_schema = _strategy_identity()
    object.__setattr__(
        wrong_schema,
        "configuration_schema",
        CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
    )
    object.__setattr__(
        wrong_schema,
        "fingerprint",
        canonical_fingerprint(wrong_schema._fingerprint_payload()),
    )
    with pytest.raises(ValueError, match="do not correspond"):
        _strategy(strategy_policy_identity=wrong_schema)

    wrong_configuration = _strategy_identity()
    object.__setattr__(
        wrong_configuration,
        "configuration",
        ClassicDailyTechnicalAssessmentConfiguration(),
    )
    object.__setattr__(
        wrong_configuration,
        "configuration_schema",
        CLASSIC_DAILY_TECHNICAL_ASSESSMENT_CONFIGURATION_SCHEMA,
    )
    object.__setattr__(
        wrong_configuration,
        "fingerprint",
        canonical_fingerprint(wrong_configuration._fingerprint_payload()),
    )
    with pytest.raises(ValueError, match="do not correspond"):
        _strategy(strategy_policy_identity=wrong_configuration)


def test_strategy_enums_require_exact_types_and_reject_free_form_strings() -> None:
    class OtherMode(StrEnum):
        VALUE = "positive_directional_continuation"

    class OtherRuleCode(StrEnum):
        VALUE = "aligned_positive_continuation"

    with pytest.raises(ValueError, match="mode"):
        _strategy(mode=OtherMode.VALUE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="rule code"):
        _strategy(rule_code=OtherRuleCode.VALUE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mode"):
        _strategy(mode="positive_directional_continuation")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="rule code"):
        _strategy(rule_code="aligned_positive_continuation")  # type: ignore[arg-type]


def test_strategy_projection_and_fingerprint_are_deterministic() -> None:
    first = _strategy()
    second = _strategy()
    expected_payload = {
        "schema_version": DAILY_TECHNICAL_STRATEGY_SCHEMA,
        "canonical_instrument_id": {"instrument_id": "us_equity.aapl"},
        "analysis_as_of": "2026-08-18T08:30:00+00:00",
        "source_assessment_fingerprint": _ASSESSMENT_FINGERPRINT,
        "strategy_policy_identity": _strategy_identity().to_dict(),
        "mode": "positive_directional_continuation",
        "rule_code": "aligned_positive_continuation",
    }
    assert first._fingerprint_payload() == expected_payload
    assert "fingerprint" not in first._fingerprint_payload()
    assert first.fingerprint == canonical_fingerprint(expected_payload)
    assert first.fingerprint == second.fingerprint
    assert first.to_dict() == {**expected_payload, "fingerprint": first.fingerprint}
    assert first.to_dict() == second.to_dict()


def test_policy_revision_and_identity_change_strategy_fingerprint() -> None:
    baseline = _strategy()
    revised = _strategy(strategy_policy_identity=_strategy_identity(revision="1.0.1"))
    different_policy = _strategy(
        strategy_policy_identity=_strategy_identity(policy_id="other_strategy_policy")
    )
    assert revised.fingerprint != baseline.fingerprint
    assert different_policy.fingerprint != baseline.fingerprint


def test_policy_configuration_and_identity_are_detached_and_revalidated() -> None:
    configuration = ClassicDailyTechnicalStrategyConfiguration()
    identity = TechnicalPolicyIdentity(
        policy_kind=TechnicalPolicyKind.DAILY_TECHNICAL_STRATEGY,
        policy_id="classic_daily_technical_strategy",
        behavioral_revision="1.0.0",
        configuration_schema=(CLASSIC_DAILY_TECHNICAL_STRATEGY_CONFIGURATION_SCHEMA),
        configuration=configuration,
    )
    strategy = _strategy(strategy_policy_identity=identity)
    assert identity.configuration is not configuration
    assert strategy.strategy_policy_identity is not identity
    assert strategy.strategy_policy_identity.configuration is not identity.configuration

    object.__setattr__(identity, "behavioral_revision", "1.0.1")
    assert strategy.strategy_policy_identity.behavioral_revision == "1.0.0"
    strategy.to_dict()

    object.__setattr__(
        strategy.strategy_policy_identity,
        "behavioral_revision",
        "1.0.1",
    )
    with pytest.raises(ValueError, match="fingerprint"):
        strategy.to_dict()


def test_strategy_is_frozen_slotted_and_revalidates_forged_state() -> None:
    strategy = _strategy()
    assert not hasattr(strategy, "__dict__")
    with pytest.raises(FrozenInstanceError):
        strategy.mode = DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION

    object.__setattr__(
        strategy,
        "mode",
        DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
    )
    object.__setattr__(
        strategy,
        "fingerprint",
        canonical_fingerprint(strategy._fingerprint_payload()),
    )
    with pytest.raises(ValueError, match="do not correspond"):
        strategy.to_dict()


def test_fingerprint_changes_with_each_meaningfully_variable_semantic_field() -> None:
    baseline = _strategy()
    changed = [
        _strategy(canonical_instrument_id=CanonicalInstrumentId("us_equity.msft")),
        _strategy(analysis_as_of=datetime(2026, 8, 19, 8, 30, tzinfo=UTC)),
        _strategy(source_assessment_fingerprint="sha256:" + "2" * 64),
        _strategy(
            strategy_policy_identity=_strategy_identity(
                policy_id="other_strategy_policy"
            )
        ),
        _strategy(strategy_policy_identity=_strategy_identity(revision="1.0.1")),
        _strategy(
            mode=DailyTechnicalStrategyMode.NEGATIVE_DIRECTIONAL_CONTINUATION,
            rule_code=(DailyTechnicalStrategyRuleCode.ALIGNED_NEGATIVE_CONTINUATION),
        ),
    ]
    fingerprints = {baseline.fingerprint, *(item.fingerprint for item in changed)}
    assert len(fingerprints) == len(changed) + 1


def test_strategy_contract_contains_only_approved_non_actionable_fields() -> None:
    assert tuple(DailyTechnicalStrategy.__dataclass_fields__) == (
        "canonical_instrument_id",
        "analysis_as_of",
        "source_assessment_fingerprint",
        "strategy_policy_identity",
        "mode",
        "rule_code",
        "schema_version",
        "fingerprint",
    )
    strategy = _strategy()
    assert set(strategy.to_dict()) == {
        "schema_version",
        "canonical_instrument_id",
        "analysis_as_of",
        "source_assessment_fingerprint",
        "strategy_policy_identity",
        "mode",
        "rule_code",
        "fingerprint",
    }
    prohibited = {
        "recommendation",
        "rationale",
        "action",
        "side",
        "entry",
        "exit",
        "stop",
        "target",
        "price",
        "quantity",
        "position",
        "portfolio",
        "score",
        "confidence",
        "constraints",
        "evidence",
    }
    assert not prohibited.intersection(strategy.to_dict())


def test_derivation_succeeds_once_with_only_official_unchanged_sources() -> None:
    interpretation, assessment = _source_chain()
    interpretation_before = interpretation.to_dict()
    assessment_before = assessment.to_dict()
    policy = _TestStrategyPolicy()
    assert isinstance(policy, DailyTechnicalStrategyPolicy)

    result = derive_daily_technical_strategy(interpretation, assessment, policy)

    assert policy.calls == 1
    assert policy.received == (interpretation, assessment)
    assert result.source_assessment_fingerprint == assessment.fingerprint
    assert interpretation.to_dict() == interpretation_before
    assert assessment.to_dict() == assessment_before


def test_derivation_rejects_source_and_result_subclasses() -> None:
    interpretation, assessment = _source_chain()

    class InterpretationSubclass(DailyTechnicalInterpretation):
        pass

    interpretation_subclass = object.__new__(InterpretationSubclass)
    for name in DailyTechnicalInterpretation.__dataclass_fields__:
        object.__setattr__(interpretation_subclass, name, getattr(interpretation, name))
    policy = _TestStrategyPolicy()
    with pytest.raises(TypeError, match="exact DailyTechnicalInterpretation"):
        derive_daily_technical_strategy(
            interpretation_subclass,
            assessment,
            policy,  # type: ignore[arg-type]
        )
    assert policy.calls == 0

    class AssessmentSubclass(DailyTechnicalAssessment):
        pass

    assessment_subclass = object.__new__(AssessmentSubclass)
    for name in DailyTechnicalAssessment.__dataclass_fields__:
        object.__setattr__(assessment_subclass, name, getattr(assessment, name))
    with pytest.raises(TypeError, match="exact DailyTechnicalAssessment"):
        derive_daily_technical_strategy(
            interpretation,
            assessment_subclass,
            policy,  # type: ignore[arg-type]
        )
    assert policy.calls == 0

    class StrategySubclass(DailyTechnicalStrategy):
        pass

    valid_result = _strategy(source_assessment_fingerprint=assessment.fingerprint)
    strategy_subclass = object.__new__(StrategySubclass)
    for name in DailyTechnicalStrategy.__dataclass_fields__:
        object.__setattr__(strategy_subclass, name, getattr(valid_result, name))
    result_policy = _TestStrategyPolicy(returned_result=strategy_subclass)
    with pytest.raises(TypeError, match="exact DailyTechnicalStrategy"):
        derive_daily_technical_strategy(interpretation, assessment, result_policy)
    assert result_policy.calls == 1


def test_derivation_rejects_two_source_identity_and_time_mismatches() -> None:
    interpretation = _interpretation()
    mismatches = (
        _assessment(
            interpretation,
            canonical_instrument_id=CanonicalInstrumentId("us_equity.msft"),
        ),
        _assessment(
            interpretation,
            analysis_as_of=datetime(2026, 8, 19, 8, 30, tzinfo=UTC),
        ),
        _assessment(
            interpretation,
            source_interpretation_fingerprint="sha256:" + "c" * 64,
        ),
    )
    for assessment in mismatches:
        policy = _TestStrategyPolicy()
        with pytest.raises(ValueError, match="source chain"):
            derive_daily_technical_strategy(interpretation, assessment, policy)
        assert policy.calls == 0
