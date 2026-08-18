from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments.identity import CanonicalInstrumentId
from market_platform.research.daily_technical_strategy import (
    DAILY_TECHNICAL_STRATEGY_SCHEMA,
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
