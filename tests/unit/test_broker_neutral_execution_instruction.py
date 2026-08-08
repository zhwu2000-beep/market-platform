"""Focused tests for v0.61 broker-neutral execution instructions."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
from enum import StrEnum
from typing import cast

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
    BrokerNeutralExecutionInstruction,
    ExecutionInstructionSide,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    PositionDeltaAction,
    PositionTargetTranslation,
    derive_broker_neutral_execution_instruction,
    translate_position_target,
)
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingSourceIdentity,
    InstrumentResolution,
    resolve_instrument_mapping,
)
from market_platform.risk import (
    EvidenceCoverageScope,
    QuoteEvidenceRequirement,
    RiskEvaluationContext,
    RiskEvidenceCoverage,
    StructuralRiskPolicy,
    evaluate_structural_risk,
)
from market_platform.trading import (
    ExactTargetPositionIntentPolicy,
    OrderIntent,
    TradingInstrumentIdentity,
    TradingSignal,
    TradingSignalSourceIdentity,
    TradingTargetPosition,
    create_order_intent_from_signal,
)
from market_platform.trading_state import (
    AccountCashSnapshot,
    CashBalance,
    MarketQuote,
    MarketQuoteCollectionSnapshot,
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
    PositionRecord,
    StateSnapshotSourceIdentity,
    TradingAccountIdentity,
    TradingEnvironment,
)

BASE = datetime(2026, 1, 2, 15, tzinfo=UTC)
FP = "sha256:" + "a" * 64


class _TranslationSubclass(PositionTargetTranslation):
    pass


class _ForeignSide(StrEnum):
    BUY = "buy"


@dataclass
class _Foreign:
    value: object = None


def _policy() -> StructuralRiskPolicy:
    return StructuralRiskPolicy(
        "structural.default",
        "1.0.0",
        None,
        timedelta(minutes=5),
        timedelta(minutes=5),
        timedelta(minutes=5),
        timedelta(minutes=1),
        timedelta(seconds=30),
        QuoteEvidenceRequirement.LAST,
    )


def _intent(direction: TradingTargetPosition, units: Decimal) -> OrderIntent:
    signal = TradingSignal(
        TradingSignalSourceIdentity("strategy", "1"),
        "event",
        TradingInstrumentIdentity("AAPL", "NASDAQ"),
        "1m",
        direction,
        units,
        BASE - timedelta(hours=2),
        BASE - timedelta(hours=2),
        BASE + timedelta(hours=2),
    )
    return create_order_intent_from_signal(
        signal, ExactTargetPositionIntentPolicy(), BASE - timedelta(hours=1)
    )


def _resolution() -> InstrumentResolution:
    external = ExternalInstrumentIdentity("vendor", "AAPL", "XNAS")
    canonical = CanonicalInstrument(
        CanonicalInstrumentId("instrument.AAPL"),
        TradingInstrumentIdentity("AAPL", "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )
    mapping = InstrumentMapping(
        external,
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        BASE - timedelta(days=1),
        None,
    )
    return resolve_instrument_mapping(external, [mapping], BASE)


def _translation(
    direction: TradingTargetPosition = TradingTargetPosition.LONG,
    units: Decimal = Decimal("10"),
    current: Decimal | None = Decimal("4"),
) -> PositionTargetTranslation:
    account = TradingAccountIdentity(
        "broker", "account-1", TradingEnvironment.PAPER, "USD"
    )
    source = StateSnapshotSourceIdentity("snapshot", "1")
    resolution = _resolution()
    instrument_id = resolution.mapping.canonical_instrument.instrument_id
    positions = [] if current is None else [PositionRecord(instrument_id, current)]
    context = RiskEvaluationContext(
        _intent(direction, units),
        resolution,
        AccountCashSnapshot(
            account,
            source,
            BASE - timedelta(seconds=10),
            [CashBalance("USD", Decimal("1000"))],
        ),
        PositionCollectionSnapshot(
            account, source, BASE - timedelta(seconds=9), positions
        ),
        OpenOrderExposureSnapshot(account, source, BASE - timedelta(seconds=8), []),
        MarketQuoteCollectionSnapshot(
            source,
            BASE - timedelta(seconds=7),
            [MarketQuote(instrument_id, last=Decimal("190"))],
        ),
        RiskEvidenceCoverage(
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
        ),
        _policy(),
        BASE,
    )
    return translate_position_target(context, evaluate_structural_risk(context), BASE)


def _instruction(
    direction: TradingTargetPosition = TradingTargetPosition.LONG,
    units: Decimal = Decimal("10"),
    current: Decimal | None = Decimal("4"),
) -> BrokerNeutralExecutionInstruction:
    result = derive_broker_neutral_execution_instruction(
        _translation(direction, units, current)
    )
    assert result is not None
    return result


def _refingerprint(value: BrokerNeutralExecutionInstruction) -> None:
    object.__setattr__(
        value, "fingerprint", canonical_fingerprint(value._fingerprint_payload())
    )


def test_exact_public_api() -> None:
    prior_twenty_three_exports = {
        "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
        "LIMIT_PRICE_CHOICE_SCHEMA",
        "ORDER_STYLE_CHOICE_SCHEMA",
        "POSITION_TARGET_TRANSLATION_SCHEMA",
        "SESSION_PARTICIPATION_CHOICE_SCHEMA",
        "TIME_IN_FORCE_CHOICE_SCHEMA",
        "BrokerNeutralExecutionInstruction",
        "ExecutionPlanningCorrespondenceError",
        "ExecutionPlanningDomainError",
        "ExecutionPlanningUnavailableError",
        "ExecutionPlanningValidationError",
        "ExecutionInstructionSide",
        "LimitPriceChoice",
        "OrderStyle",
        "OrderStyleChoice",
        "PositionDeltaAction",
        "PositionTargetTranslation",
        "SessionParticipation",
        "SessionParticipationChoice",
        "TimeInForce",
        "TimeInForceChoice",
        "derive_broker_neutral_execution_instruction",
        "translate_position_target",
    }
    approved_v066_additions = {
        "BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA",
        "BrokerNeutralOrderSpecification",
        "construct_broker_neutral_order_specification",
    }
    expected_exports = [
        "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
        "BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA",
        "LIMIT_PRICE_CHOICE_SCHEMA",
        "ORDER_STYLE_CHOICE_SCHEMA",
        "POSITION_TARGET_TRANSLATION_SCHEMA",
        "SESSION_PARTICIPATION_CHOICE_SCHEMA",
        "TIME_IN_FORCE_CHOICE_SCHEMA",
        "BrokerNeutralExecutionInstruction",
        "BrokerNeutralOrderSpecification",
        "ExecutionPlanningCorrespondenceError",
        "ExecutionPlanningDomainError",
        "ExecutionPlanningUnavailableError",
        "ExecutionPlanningValidationError",
        "ExecutionInstructionSide",
        "LimitPriceChoice",
        "OrderStyle",
        "OrderStyleChoice",
        "PositionDeltaAction",
        "PositionTargetTranslation",
        "SessionParticipation",
        "SessionParticipationChoice",
        "TimeInForce",
        "TimeInForceChoice",
        "construct_broker_neutral_order_specification",
        "derive_broker_neutral_execution_instruction",
        "translate_position_target",
        "BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA",
        "BrokerExecutionCapabilityProfile",
        "construct_broker_execution_capability_profile",
        "BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA",
        "BrokerExecutionStructuralCompatibilityOutcome",
        "BrokerExecutionStructuralCompatibilityReason",
        "BrokerExecutionStructuralCompatibilityResult",
        "evaluate_broker_execution_structural_compatibility",
        "BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA",
        "BrokerNativeOrderRepresentation",
        "construct_broker_native_order_representation",
        "BROKER_NATIVE_ORDER_MAPPING_SCHEMA",
        "BrokerNativeOrderMapping",
        "BrokerNativeOrderMapper",
        "map_broker_native_order",
    ]
    assert len(prior_twenty_three_exports) == 23
    assert prior_twenty_three_exports <= set(execution_planning.__all__)
    assert approved_v066_additions <= set(execution_planning.__all__)
    assert execution_planning.__all__ == expected_exports
    assert len(execution_planning.__all__) == 41
    for name in expected_exports:
        assert getattr(execution_planning, name) is not None


def test_exact_schema_enum_and_fields() -> None:
    assert (
        BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA
        == "broker_neutral_execution_instruction/v1"
    )
    assert [item.value for item in ExecutionInstructionSide] == ["buy", "sell"]
    assert [
        field.name
        for field in fields(BrokerNeutralExecutionInstruction)
        if not field.name.startswith("_")
    ] == [
        "side",
        "quantity",
        "source_translation_fingerprint",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "plan_as_of",
        "schema_version",
        "fingerprint",
    ]


@pytest.mark.parametrize(
    "value", [object(), {}, {"action": "buy"}, _Foreign(), "translation"]
)
def test_wrong_input_types_are_validation_errors(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        derive_broker_neutral_execution_instruction(
            cast(PositionTargetTranslation, value)
        )


def test_translation_subclass_is_rejected() -> None:
    value = object.__new__(_TranslationSubclass)
    with pytest.raises(ExecutionPlanningValidationError):
        derive_broker_neutral_execution_instruction(value)


def test_direct_construction_is_rejected() -> None:
    with pytest.raises(TypeError):
        BrokerNeutralExecutionInstruction()


@pytest.mark.parametrize(
    ("direction", "units", "current", "side", "quantity"),
    [
        (TradingTargetPosition.LONG, "10", "4", "buy", "6"),
        (TradingTargetPosition.LONG, "4", "10", "sell", "6"),
        (TradingTargetPosition.FLAT, "0", "4", "sell", "4"),
        (TradingTargetPosition.SHORT, "3", "-8", "buy", "5"),
        (TradingTargetPosition.SHORT, "8", "-3", "sell", "5"),
        (TradingTargetPosition.LONG, "1.2300", "0.23", "buy", "1"),
    ],
)
def test_actionable_derivation(
    direction: TradingTargetPosition, units: str, current: str, side: str, quantity: str
) -> None:
    source = _translation(direction, Decimal(units), Decimal(current))
    result = derive_broker_neutral_execution_instruction(source)
    assert result is not None
    assert result.side.value == side
    assert result.quantity == Decimal(quantity)
    assert result.quantity > 0
    assert result.source_translation_fingerprint == source.fingerprint
    assert (
        result.canonical_instrument_id.to_dict()
        == source.canonical_instrument_id.to_dict()
    )
    assert (
        result.canonical_instrument_fingerprint
        == source.canonical_instrument_fingerprint
    )
    assert result.account_fingerprint == source.account_fingerprint
    assert result.plan_as_of == source.plan_as_of


@pytest.mark.parametrize(
    ("direction", "units", "current"),
    [
        (TradingTargetPosition.FLAT, "0", None),
        (TradingTargetPosition.LONG, "10", "10"),
        (TradingTargetPosition.SHORT, "10", "-10"),
    ],
)
def test_no_action_returns_none(
    direction: TradingTargetPosition, units: str, current: str | None
) -> None:
    source = _translation(
        direction, Decimal(units), None if current is None else Decimal(current)
    )
    assert source.action is PositionDeltaAction.NO_ACTION
    assert derive_broker_neutral_execution_instruction(source) is None
    assert source.to_dict()["action"] == "no_action"


def test_projection_is_exact_json_safe_and_constant_sized() -> None:
    result = _instruction()
    projection = result.to_dict()
    assert list(projection) == [
        "schema_version",
        "side",
        "quantity",
        "source_translation_fingerprint",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "plan_as_of",
        "fingerprint",
    ]
    assert projection["quantity"] == "6"
    assert not any(isinstance(value, Decimal) for value in projection.values())
    assert "_source_translation" not in projection
    assert "risk_context_fingerprint" not in projection
    assert "order_type" not in projection


def test_repeated_derivation_is_deterministic() -> None:
    source = _translation()
    first = derive_broker_neutral_execution_instruction(source)
    second = derive_broker_neutral_execution_instruction(source)
    assert first is not None and second is not None
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize(
    ("precision", "rounding", "trap"),
    [
        (1, "ROUND_DOWN", None),
        (2, "ROUND_UP", None),
        (1, "ROUND_FLOOR", None),
        (2, "ROUND_CEILING", None),
        (1, "ROUND_HALF_EVEN", Inexact),
        (2, "ROUND_HALF_UP", Rounded),
        (1, "ROUND_UP", Inexact),
        (2, "ROUND_DOWN", Rounded),
    ],
)
def test_decimal_context_independence(
    precision: int, rounding: str, trap: type[BaseException] | None
) -> None:
    source = _translation(
        TradingTargetPosition.LONG,
        Decimal("1.234567890123456789"),
        Decimal("0.000000000000000001"),
    )
    expected = derive_broker_neutral_execution_instruction(source)
    assert expected is not None
    with localcontext() as context:
        context.prec = precision
        context.rounding = rounding
        context.Emin = -9
        context.Emax = 9
        if trap is not None:
            context.traps[trap] = True  # type: ignore[index]
        actual = derive_broker_neutral_execution_instruction(source)
    assert actual is not None
    assert actual.to_dict() == expected.to_dict()


@pytest.mark.parametrize(
    "field",
    [
        "side",
        "quantity",
        "source_translation_fingerprint",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "plan_as_of",
        "schema_version",
        "fingerprint",
    ],
)
def test_public_field_mutation_is_rejected(field: str) -> None:
    result = _instruction()
    replacements: dict[str, object] = {
        "side": ExecutionInstructionSide.SELL,
        "quantity": Decimal("7"),
        "source_translation_fingerprint": FP,
        "canonical_instrument_id": CanonicalInstrumentId("instrument.OTHER"),
        "canonical_instrument_fingerprint": FP,
        "account_fingerprint": FP,
        "plan_as_of": BASE + timedelta(microseconds=1),
        "schema_version": "wrong/v1",
        "fingerprint": FP,
    }
    object.__setattr__(result, field, replacements[field])
    if field != "fingerprint":
        with contextlib.suppress(ExecutionPlanningCorrespondenceError):
            _refingerprint(result)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    "field",
    [
        "_token",
        "_source_translation",
        "_constructor_state",
        "_constructor_binding",
        "side",
        "quantity",
        "source_translation_fingerprint",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "plan_as_of",
        "schema_version",
        "fingerprint",
    ],
)
def test_deleted_instruction_slots_are_correspondence_errors(field: str) -> None:
    result = _instruction()
    object.__delattr__(result, field)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    "replacement",
    [
        object(),
        [],
        (),
        (object(),),
        (object(), object()),
        (object(), object(), object()),
        "binding",
    ],
)
def test_malformed_binding_is_rejected(replacement: object) -> None:
    result = _instruction()
    object.__setattr__(result, "_constructor_binding", replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_equal_constructor_state_replacement_is_identity_rejected() -> None:
    result = _instruction()
    original = result._constructor_state
    replacement = tuple([*original])
    assert replacement == original and replacement is not original
    object.__setattr__(result, "_constructor_state", replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_forged_state_and_recomputed_fingerprint_are_rejected() -> None:
    result = _instruction()
    original_binding = result._constructor_binding
    state = list(result._constructor_state)
    state[0], state[1] = "sell", "7"
    object.__setattr__(result, "side", ExecutionInstructionSide.SELL)
    object.__setattr__(result, "quantity", Decimal("7"))
    object.__setattr__(result, "_constructor_state", tuple(state))
    _refingerprint(result)
    assert original_binding[1] is not result._constructor_state
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_foreign_binding_and_source_are_rejected() -> None:
    first = _instruction()
    second = _instruction(TradingTargetPosition.SHORT, Decimal("8"), Decimal("-3"))
    object.__setattr__(first, "_constructor_binding", second._constructor_binding)
    object.__setattr__(first, "_source_translation", second._source_translation)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        first.to_dict()


@pytest.mark.parametrize(
    "field",
    [
        "action",
        "delta_quantity",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "plan_as_of",
        "fingerprint",
    ],
)
def test_mutated_source_translation_is_rejected(field: str) -> None:
    result = _instruction()
    source = result._source_translation
    replacements: dict[str, object] = {
        "action": PositionDeltaAction.SELL,
        "delta_quantity": Decimal("-6"),
        "canonical_instrument_id": CanonicalInstrumentId("instrument.OTHER"),
        "canonical_instrument_fingerprint": FP,
        "account_fingerprint": FP,
        "plan_as_of": BASE + timedelta(microseconds=1),
        "fingerprint": FP,
    }
    object.__setattr__(source, field, replacements[field])
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    "field",
    [
        "_token",
        "_constructor_state",
        "_constructor_binding",
        "action",
        "delta_quantity",
    ],
)
def test_deleted_source_translation_slots_are_rejected(field: str) -> None:
    result = _instruction()
    object.__delattr__(result._source_translation, field)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    "exception_type", [TypeError, ValueError, RuntimeError, AssertionError]
)
def test_unexpected_source_projection_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch, exception_type: type[Exception]
) -> None:
    source = _translation()

    def raise_probe(self: object) -> dict[str, object]:
        raise exception_type("instruction source probe")

    monkeypatch.setattr(PositionTargetTranslation, "to_dict", raise_probe)
    with pytest.raises(exception_type, match="instruction source probe"):
        derive_broker_neutral_execution_instruction(source)


@pytest.mark.parametrize(
    "field",
    [
        "side",
        "quantity",
        "source_translation_fingerprint",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "plan_as_of",
    ],
)
def test_every_public_semantic_field_is_fingerprint_significant(field: str) -> None:
    first = _instruction()
    second = _instruction()
    replacements: dict[str, object] = {
        "side": ExecutionInstructionSide.SELL,
        "quantity": Decimal("7"),
        "source_translation_fingerprint": FP,
        "canonical_instrument_id": CanonicalInstrumentId("instrument.OTHER"),
        "canonical_instrument_fingerprint": FP,
        "account_fingerprint": FP,
        "plan_as_of": BASE + timedelta(microseconds=1),
    }
    object.__setattr__(second, field, replacements[field])
    object.__setattr__(
        second, "fingerprint", canonical_fingerprint(second._fingerprint_payload())
    )
    assert first.fingerprint != second.fingerprint


def test_129_digit_quantity_and_fixed_point_projection() -> None:
    magnitude = Decimal("9" * 128)
    negative_magnitude = Decimal("-" + "9" * 128)
    result = _instruction(TradingTargetPosition.LONG, magnitude, negative_magnitude)
    assert len(str(result.quantity)) == 129
    assert result.to_dict()["quantity"] == "1" + "9" * 127 + "8"
    assert "E" not in cast(str, result.to_dict()["quantity"])


def test_fractional_64_digit_quantity() -> None:
    units = Decimal("0." + "1" * 64)
    result = _instruction(TradingTargetPosition.LONG, units, None)
    assert result.to_dict()["quantity"] == "0." + "1" * 64
