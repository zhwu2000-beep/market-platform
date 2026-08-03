"""Focused tests for v0.60 position target translation foundations."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, localcontext
from enum import StrEnum

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    POSITION_TARGET_TRANSLATION_SCHEMA,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningDomainError,
    ExecutionPlanningUnavailableError,
    ExecutionPlanningValidationError,
    PositionDeltaAction,
    PositionTargetTranslation,
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
    RiskDecisionOutcome,
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
    OpenOrderExposure,
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
    PositionRecord,
    StateSnapshotSourceIdentity,
    TradingAccountIdentity,
    TradingEnvironment,
)

BASE = datetime(2025, 1, 2, 12, tzinfo=UTC)


class _DatetimeSubclass(datetime):
    pass


class _ForeignAction(StrEnum):
    BUY = "buy"


@dataclass
class _ForeignRetainedValue:
    value: object = None


class _TupleSubclass(tuple[object, ...]):
    pass


class _HostileIterable:
    def __iter__(self) -> Iterator[object]:
        raise AssertionError("hostile iterable must not be consumed")


class _CashBalanceSubclass(CashBalance):
    pass


class _PositionRecordSubclass(PositionRecord):
    pass


class _OpenOrderExposureSubclass(OpenOrderExposure):
    pass


class _MarketQuoteSubclass(MarketQuote):
    pass


SNAPSHOT_HEADER_FIELDS = {
    "cash": (
        "account",
        "source",
        "as_of",
        "balances",
        "schema_version",
        "fingerprint",
    ),
    "positions": (
        "account",
        "source",
        "as_of",
        "positions",
        "schema_version",
        "fingerprint",
    ),
    "open_orders": (
        "account",
        "source",
        "as_of",
        "exposures",
        "schema_version",
        "fingerprint",
    ),
    "quotes": ("source", "as_of", "quotes", "schema_version", "fingerprint"),
}

SNAPSHOT_ROW_FIELDS = {
    "cash": ("currency", "amount"),
    "positions": ("instrument_id", "quantity"),
    "open_orders": ("external_order_id", "instrument_id", "remaining_quantity"),
    "quotes": ("instrument_id", "bid", "ask", "last"),
}


def _policy() -> StructuralRiskPolicy:
    return StructuralRiskPolicy(
        policy_id="structural.default",
        policy_version="1.0.0",
        configuration_fingerprint=None,
        maximum_cash_age=timedelta(minutes=5),
        maximum_position_age=timedelta(minutes=5),
        maximum_open_order_age=timedelta(minutes=5),
        maximum_quote_age=timedelta(minutes=1),
        maximum_state_skew=timedelta(seconds=30),
        quote_requirement=QuoteEvidenceRequirement.LAST,
    )


def _intent(
    direction: TradingTargetPosition = TradingTargetPosition.LONG,
    units: Decimal = Decimal("10"),
) -> OrderIntent:
    signal = TradingSignal(
        source=TradingSignalSourceIdentity("strategy", "1.0.0"),
        source_event_id="event-1",
        instrument=TradingInstrumentIdentity("AAPL", "NASDAQ"),
        timeframe="1m",
        target_position=direction,
        target_units=units,
        generated_at=BASE - timedelta(hours=2, minutes=1),
        valid_from=BASE - timedelta(hours=2),
        expires_at=BASE + timedelta(hours=2),
    )
    return create_order_intent_from_signal(
        signal,
        ExactTargetPositionIntentPolicy(),
        BASE - timedelta(hours=2),
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


def _account() -> TradingAccountIdentity:
    return TradingAccountIdentity(
        "broker", "account-1", TradingEnvironment.PAPER, "USD"
    )


def _context(
    *,
    direction: TradingTargetPosition = TradingTargetPosition.LONG,
    units: Decimal = Decimal("10"),
    current: Decimal | None = None,
    positions_override: tuple[PositionRecord, ...] | None = None,
    exposures: tuple[OpenOrderExposure, ...] = (),
    cash_balances_override: tuple[CashBalance, ...] | None = None,
    quotes_override: tuple[MarketQuote, ...] | None = None,
    evaluation_as_of: datetime = BASE,
) -> RiskEvaluationContext:
    account = _account()
    source = StateSnapshotSourceIdentity("snapshot", "1")
    resolution = _resolution()
    instrument_id = resolution.mapping.canonical_instrument.instrument_id
    positions = (
        list(positions_override)
        if positions_override is not None
        else (
            []
            if current is None
            else [PositionRecord(instrument_id, current)]
        )
    )
    return RiskEvaluationContext(
        order_intent=_intent(direction, units),
        instrument_resolution=resolution,
        cash_snapshot=AccountCashSnapshot(
            account,
            source,
            BASE - timedelta(seconds=10),
            (
                cash_balances_override
                if cash_balances_override is not None
                else [CashBalance("USD", Decimal("1000"))]
            ),
        ),
        position_snapshot=PositionCollectionSnapshot(
            account,
            source,
            BASE - timedelta(seconds=9),
            positions,
        ),
        open_order_snapshot=OpenOrderExposureSnapshot(
            account,
            source,
            BASE - timedelta(seconds=8),
            exposures,
        ),
        quote_snapshot=MarketQuoteCollectionSnapshot(
            source,
            BASE - timedelta(seconds=7),
            (
                quotes_override
                if quotes_override is not None
                else [MarketQuote(instrument_id, last=Decimal("190"))]
            ),
        ),
        coverage=RiskEvidenceCoverage(
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
        ),
        policy=_policy(),
        evaluation_as_of=evaluation_as_of,
    )


def _translation(**context_changes: object) -> PositionTargetTranslation:
    context = _context(**context_changes)  # type: ignore[arg-type]
    return translate_position_target(context, evaluate_structural_risk(context), BASE)


def _rewrite_fingerprint(value: PositionTargetTranslation) -> None:
    object.__setattr__(
        value,
        "fingerprint",
        canonical_fingerprint(value._fingerprint_payload()),
    )


def _snapshot(context: RiskEvaluationContext, family: str) -> object:
    return {
        "cash": context.cash_snapshot,
        "positions": context.position_snapshot,
        "open_orders": context.open_order_snapshot,
        "quotes": context.quote_snapshot,
    }[family]


def _collection_field(family: str) -> str:
    return {
        "cash": "balances",
        "positions": "positions",
        "open_orders": "exposures",
        "quotes": "quotes",
    }[family]


def _context_with_row(family: str) -> RiskEvaluationContext:
    if family == "positions":
        return _context(current=Decimal("5"))
    if family == "open_orders":
        target_id = _resolution().mapping.canonical_instrument.instrument_id
        return _context(
            exposures=(OpenOrderExposure("order-1", target_id, Decimal("1")),)
        )
    return _context()


def _empty_context_for_header(family: str) -> RiskEvaluationContext:
    if family == "cash":
        return _context(cash_balances_override=())
    if family == "quotes":
        return _context(quotes_override=())
    return _context()


def _foreign_snapshot(context: RiskEvaluationContext, family: str) -> object:
    if family == "cash":
        return context.position_snapshot
    return context.cash_snapshot


def _foreign_row(family: str, kind: str) -> object:
    target_id = _resolution().mapping.canonical_instrument.instrument_id
    if kind == "object":
        return object()
    if kind == "foreign":
        return _ForeignRetainedValue()
    if family == "cash":
        return _CashBalanceSubclass("USD", Decimal("1"))
    if family == "positions":
        return _PositionRecordSubclass(target_id, Decimal("1"))
    if family == "open_orders":
        return _OpenOrderExposureSubclass("order-1", target_id, Decimal("1"))
    return _MarketQuoteSubclass(target_id, last=Decimal("1"))


def test_exact_public_api() -> None:
    original_v060_exports = {
        "POSITION_TARGET_TRANSLATION_SCHEMA",
        "ExecutionPlanningCorrespondenceError",
        "ExecutionPlanningDomainError",
        "ExecutionPlanningUnavailableError",
        "ExecutionPlanningValidationError",
        "PositionDeltaAction",
        "PositionTargetTranslation",
        "translate_position_target",
    }

    assert original_v060_exports <= set(execution_planning.__all__)
    original_v061_exports = {
        "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
        "BrokerNeutralExecutionInstruction",
        "ExecutionInstructionSide",
        "derive_broker_neutral_execution_instruction",
    }
    approved_v062_exports = {
        "ORDER_STYLE_CHOICE_SCHEMA",
        "OrderStyle",
        "OrderStyleChoice",
    }

    assert original_v061_exports <= set(execution_planning.__all__)
    assert approved_v062_exports <= set(execution_planning.__all__)
    assert execution_planning.__all__ == [
        "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
        "ORDER_STYLE_CHOICE_SCHEMA",
        "POSITION_TARGET_TRANSLATION_SCHEMA",
        "BrokerNeutralExecutionInstruction",
        "ExecutionPlanningCorrespondenceError",
        "ExecutionPlanningDomainError",
        "ExecutionPlanningUnavailableError",
        "ExecutionPlanningValidationError",
        "ExecutionInstructionSide",
        "OrderStyle",
        "OrderStyleChoice",
        "PositionDeltaAction",
        "PositionTargetTranslation",
        "derive_broker_neutral_execution_instruction",
        "translate_position_target",
    ]
    assert len(execution_planning.__all__) == 15


def test_exact_schema_and_enum_inventory() -> None:
    assert POSITION_TARGET_TRANSLATION_SCHEMA == "position_target_translation/v1"
    assert [item.value for item in PositionDeltaAction] == [
        "buy",
        "sell",
        "no_action",
    ]


def test_error_hierarchy() -> None:
    assert issubclass(ExecutionPlanningValidationError, ExecutionPlanningDomainError)
    assert issubclass(
        ExecutionPlanningCorrespondenceError, ExecutionPlanningDomainError
    )
    assert issubclass(ExecutionPlanningUnavailableError, ExecutionPlanningDomainError)


def test_translation_is_factory_owned() -> None:
    with pytest.raises(TypeError):
        PositionTargetTranslation()


@pytest.mark.parametrize(
    ("direction", "target", "current", "expected_target", "delta", "action"),
    [
        (TradingTargetPosition.LONG, "10", None, "10", "10", "buy"),
        (TradingTargetPosition.FLAT, "0", None, "0", "0", "no_action"),
        (TradingTargetPosition.SHORT, "10", None, "-10", "-10", "sell"),
        (TradingTargetPosition.LONG, "10", "5", "10", "5", "buy"),
        (TradingTargetPosition.LONG, "5", "10", "5", "-5", "sell"),
        (TradingTargetPosition.FLAT, "0", "10", "0", "-10", "sell"),
        (TradingTargetPosition.SHORT, "5", "10", "-5", "-15", "sell"),
        (TradingTargetPosition.SHORT, "10", "-5", "-10", "-5", "sell"),
        (TradingTargetPosition.SHORT, "5", "-10", "-5", "5", "buy"),
        (TradingTargetPosition.FLAT, "0", "-10", "0", "10", "buy"),
        (TradingTargetPosition.LONG, "5", "-10", "5", "15", "buy"),
        (TradingTargetPosition.LONG, "10", "10", "10", "0", "no_action"),
        (TradingTargetPosition.SHORT, "10", "-10", "-10", "0", "no_action"),
        (TradingTargetPosition.LONG, "1.25", ".5", "1.25", ".75", "buy"),
        (TradingTargetPosition.SHORT, ".25", "-.125", "-.25", "-.125", "sell"),
    ],
)
def test_position_transitions(
    direction: TradingTargetPosition,
    target: str,
    current: str | None,
    expected_target: str,
    delta: str,
    action: str,
) -> None:
    translation = _translation(
        direction=direction,
        units=Decimal(target),
        current=None if current is None else Decimal(current),
    )
    assert translation.target_quantity == Decimal(expected_target)
    assert translation.current_quantity == Decimal(current or "0")
    assert translation.delta_quantity == Decimal(delta)
    assert translation.action.value == action


@pytest.mark.parametrize("remaining", ["1", "-1", "0.5", "-0.5"])
def test_target_open_order_exposure_blocks(remaining: str) -> None:
    instrument_id = _resolution().mapping.canonical_instrument.instrument_id
    exposure = OpenOrderExposure("order-1", instrument_id, Decimal(remaining))
    context = _context(exposures=(exposure,))
    with pytest.raises(ExecutionPlanningUnavailableError):
        translate_position_target(context, evaluate_structural_risk(context), BASE)


def test_multiple_offsetting_target_exposures_still_block() -> None:
    instrument_id = _resolution().mapping.canonical_instrument.instrument_id
    context = _context(
        exposures=(
            OpenOrderExposure("buy", instrument_id, Decimal("5")),
            OpenOrderExposure("sell", instrument_id, Decimal("-5")),
        )
    )
    with pytest.raises(ExecutionPlanningUnavailableError):
        translate_position_target(context, evaluate_structural_risk(context), BASE)


def test_unrelated_open_order_exposure_does_not_block() -> None:
    exposure = OpenOrderExposure(
        "order-1", CanonicalInstrumentId("instrument.MSFT"), Decimal("4")
    )
    assert _translation(exposures=(exposure,)).action is PositionDeltaAction.BUY


@pytest.mark.parametrize("bad", [None, object(), {}, [], "context"])
def test_wrong_context_type_is_validation_error(bad: object) -> None:
    context = _context()
    with pytest.raises(ExecutionPlanningValidationError):
        translate_position_target(bad, evaluate_structural_risk(context), BASE)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, object(), {}, [], "decision"])
def test_wrong_decision_type_is_validation_error(bad: object) -> None:
    context = _context()
    with pytest.raises(ExecutionPlanningValidationError):
        translate_position_target(context, bad, BASE)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, object(), "2025-01-02", 1])
def test_wrong_plan_time_type_is_validation_error(bad: object) -> None:
    context = _context()
    with pytest.raises(ExecutionPlanningValidationError):
        translate_position_target(
            context,
            evaluate_structural_risk(context),
            bad,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "bad",
    [
        datetime(2025, 1, 2, 12),
        datetime(2025, 1, 2, 13, tzinfo=timezone(timedelta(hours=1))),
        _DatetimeSubclass(2025, 1, 2, 12, tzinfo=UTC),
    ],
)
def test_noncanonical_plan_time_is_validation_error(bad: datetime) -> None:
    context = _context()
    with pytest.raises(ExecutionPlanningValidationError):
        translate_position_target(context, evaluate_structural_risk(context), bad)


@pytest.mark.parametrize("offset", [-1, 1])
def test_different_canonical_plan_time_is_unavailable(offset: int) -> None:
    context = _context()
    with pytest.raises(ExecutionPlanningUnavailableError):
        translate_position_target(
            context,
            evaluate_structural_risk(context),
            BASE + timedelta(microseconds=offset),
        )


def test_decision_from_another_context_is_correspondence_error() -> None:
    first = _context(units=Decimal("10"))
    second = _context(units=Decimal("11"))
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(first, evaluate_structural_risk(second), BASE)


def test_fabricated_context_fingerprint_is_correspondence_error() -> None:
    context = _context()
    decision = evaluate_structural_risk(context)
    object.__setattr__(context, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


def test_fabricated_decision_fingerprint_is_correspondence_error() -> None:
    context = _context()
    decision = evaluate_structural_risk(context)
    object.__setattr__(decision, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


def test_nonapproved_canonical_decision_is_unavailable() -> None:
    context = _context(evaluation_as_of=BASE + timedelta(hours=3))
    decision = evaluate_structural_risk(context)
    assert decision.outcome is RiskDecisionOutcome.REJECTED
    with pytest.raises(ExecutionPlanningUnavailableError):
        translate_position_target(context, decision, context.evaluation_as_of)


@pytest.mark.parametrize("digits", [129, 130, 200])
def test_oversized_released_target_is_unavailable(digits: int) -> None:
    context = _context(units=Decimal("1" + "0" * (digits - 1)))
    with pytest.raises(ExecutionPlanningUnavailableError):
        translate_position_target(context, evaluate_structural_risk(context), BASE)


@pytest.mark.parametrize("fractional_digits", [65, 66, 80])
def test_excess_fractional_target_is_unavailable(fractional_digits: int) -> None:
    units = Decimal("0." + "0" * (fractional_digits - 1) + "1")
    context = _context(units=units)
    with pytest.raises(ExecutionPlanningUnavailableError):
        translate_position_target(context, evaluate_structural_risk(context), BASE)


def test_exact_fractional_bound_is_accepted() -> None:
    units = Decimal("0." + "0" * 63 + "1")
    assert _translation(units=units).target_quantity == units


def test_hostile_decimal_context_cannot_round_delta() -> None:
    with localcontext() as decimal_context:
        decimal_context.prec = 2
        decimal_context.rounding = ROUND_CEILING
        translation = _translation(
            units=Decimal("123456789.123456789"),
            current=Decimal("23.000000001"),
        )
    assert translation.delta_quantity == Decimal("123456766.123456788")


def test_carry_digit_boundary_is_exact() -> None:
    target = Decimal("9" * 128)
    current = Decimal("-" + "9" * 128)
    translation = _translation(units=target, current=current)
    assert len(format(translation.delta_quantity, "f")) == 129
    assert translation.delta_quantity == Decimal("1" + "9" * 127 + "8")


def test_public_projection_is_exact_and_bounded() -> None:
    translation = _translation()
    projection = translation.to_dict()
    assert list(projection) == [
        "schema_version",
        "action",
        "risk_context_fingerprint",
        "risk_decision_fingerprint",
        "order_intent_fingerprint",
        "canonical_instrument_id",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "position_snapshot_fingerprint",
        "open_order_snapshot_fingerprint",
        "plan_as_of",
        "target_quantity",
        "current_quantity",
        "delta_quantity",
        "fingerprint",
    ]
    assert "positions" not in repr(projection)
    assert "exposures" not in repr(projection)
    assert len(repr(projection)) < 1400


def test_projection_size_is_independent_of_large_position_snapshot() -> None:
    positions = tuple(
        PositionRecord(CanonicalInstrumentId(f"instrument.EXTRA{i}"), Decimal("1"))
        for i in range(1000)
    )
    small = _translation().to_dict()
    large = _translation(positions_override=positions).to_dict()
    assert large.keys() == small.keys()
    assert abs(len(repr(large)) - len(repr(small))) < 10
    assert "EXTRA" not in repr(large)


def test_repeated_translation_is_deterministic() -> None:
    context = _context(current=Decimal("3"))
    decision = evaluate_structural_risk(context)
    first = translate_position_target(context, decision, BASE)
    second = translate_position_target(context, decision, BASE)
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize(
    "field_name",
    [
        "risk_context_fingerprint",
        "risk_decision_fingerprint",
        "order_intent_fingerprint",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "position_snapshot_fingerprint",
        "open_order_snapshot_fingerprint",
    ],
)
def test_public_evidence_mutation_is_rejected(field_name: str) -> None:
    translation = _translation()
    object.__setattr__(translation, field_name, "sha256:" + "0" * 64)
    _rewrite_fingerprint(translation)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


@pytest.mark.parametrize(
    "field_name",
    [
        "action",
        "canonical_instrument_id",
        "plan_as_of",
        "target_quantity",
        "current_quantity",
        "delta_quantity",
    ],
)
def test_public_semantic_mutation_is_rejected(field_name: str) -> None:
    translation = _translation()
    replacements: dict[str, object] = {
        "action": PositionDeltaAction.SELL,
        "canonical_instrument_id": CanonicalInstrumentId("instrument.MSFT"),
        "plan_as_of": BASE + timedelta(microseconds=1),
        "target_quantity": Decimal("11"),
        "current_quantity": Decimal("1"),
        "delta_quantity": Decimal("11"),
    }
    object.__setattr__(translation, field_name, replacements[field_name])
    _rewrite_fingerprint(translation)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


@pytest.mark.parametrize("bad", [object(), "10", Decimal("NaN"), Decimal("-0")])
def test_malformed_retained_quantity_is_correspondence_error(bad: object) -> None:
    translation = _translation()
    object.__setattr__(translation, "target_quantity", bad)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


@pytest.mark.parametrize(
    "field_name",
    [
        "_token",
        "_constructor_state",
        "_constructor_binding",
        "action",
        "risk_context_fingerprint",
        "canonical_instrument_id",
        "target_quantity",
        "fingerprint",
    ],
)
def test_deleted_retained_slots_are_correspondence_errors(field_name: str) -> None:
    translation = _translation()
    object.__delattr__(translation, field_name)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


@pytest.mark.parametrize(
    "replacement",
    [object(), [], (), (object(),), (object(), object())],
)
def test_malformed_constructor_binding_is_rejected(replacement: object) -> None:
    translation = _translation()
    object.__setattr__(translation, "_constructor_binding", replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


def test_equal_constructor_state_replacement_is_rejected_by_identity() -> None:
    translation = _translation()
    original = translation._constructor_state
    replacement = tuple([*original])
    assert replacement == original
    assert replacement is not original
    object.__setattr__(translation, "_constructor_state", replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


def test_forged_well_formed_state_and_public_values_are_rejected() -> None:
    translation = _translation(current=Decimal("15"))
    object.__setattr__(translation, "action", PositionDeltaAction.NO_ACTION)
    object.__setattr__(translation, "current_quantity", Decimal("10"))
    object.__setattr__(translation, "delta_quantity", Decimal("0"))
    state = list(translation._constructor_state)
    state[0] = "no_action"
    state[11] = "10"
    state[12] = "0"
    object.__setattr__(translation, "_constructor_state", tuple(state))
    _rewrite_fingerprint(translation)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


def test_binding_copied_from_another_translation_is_rejected() -> None:
    first = _translation(units=Decimal("10"))
    second = _translation(units=Decimal("11"))
    object.__setattr__(first, "_constructor_binding", second._constructor_binding)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        first.to_dict()


def test_synchronized_public_and_state_mutation_is_rejected() -> None:
    translation = _translation(current=Decimal("15"))
    state = list(translation._constructor_state)
    state[0] = "buy"
    object.__setattr__(translation, "action", PositionDeltaAction.BUY)
    object.__setattr__(translation, "_constructor_state", tuple(state))
    _rewrite_fingerprint(translation)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


def test_schema_and_fingerprint_are_derived() -> None:
    names = {item.name for item in fields(PositionTargetTranslation)}
    assert {"schema_version", "fingerprint"} <= names
    translation = _translation()
    object.__setattr__(translation, "schema_version", "position_target_translation/v2")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translation.to_dict()


def test_plain_and_foreign_action_values_are_not_accepted() -> None:
    for bad in ("buy", _ForeignAction.BUY, object()):
        translation = _translation()
        object.__setattr__(translation, "action", bad)
        with pytest.raises(ExecutionPlanningCorrespondenceError):
            translation.to_dict()


def test_no_negative_zero_is_projected() -> None:
    projection = _translation(
        direction=TradingTargetPosition.FLAT,
        units=Decimal("0"),
    ).to_dict()
    assert projection["target_quantity"] == "0"
    assert projection["current_quantity"] == "0"
    assert projection["delta_quantity"] == "0"


def test_microseconds_are_fingerprint_significant() -> None:
    first_context = _context(evaluation_as_of=BASE)
    second_time = BASE + timedelta(microseconds=1)
    second_context = _context(evaluation_as_of=second_time)
    first = translate_position_target(
        first_context, evaluate_structural_risk(first_context), BASE
    )
    second = translate_position_target(
        second_context, evaluate_structural_risk(second_context), second_time
    )
    assert first.fingerprint != second.fingerprint


def test_aapl_nasdaq_released_identity_is_unchanged() -> None:
    identity = TradingInstrumentIdentity("AAPL", "NASDAQ")
    assert identity.instrument_fingerprint == (
        "sha256:dc586683e7966f5f6a9060934d37a28a594fe22b6cd42f40b5f5228e13cba433"
    )


@pytest.mark.parametrize(
    ("family", "field_name"),
    [
        (family, field_name)
        for family, field_names in SNAPSHOT_ROW_FIELDS.items()
        for field_name in field_names
    ],
)
def test_deleted_snapshot_row_slots_are_correspondence_errors(
    family: str,
    field_name: str,
) -> None:
    context = _context_with_row(family)
    decision = evaluate_structural_risk(context)
    rows = object.__getattribute__(
        _snapshot(context, family), _collection_field(family)
    )
    row = rows[0]
    object.__delattr__(row, field_name)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


@pytest.mark.parametrize(
    ("family", "field_name"),
    [
        (family, field_name)
        for family, field_names in SNAPSHOT_HEADER_FIELDS.items()
        for field_name in field_names
    ],
)
def test_deleted_snapshot_header_slots_are_correspondence_errors(
    family: str,
    field_name: str,
) -> None:
    context = _empty_context_for_header(family)
    decision = evaluate_structural_risk(context)
    object.__delattr__(_snapshot(context, family), field_name)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


@pytest.mark.parametrize("family", tuple(SNAPSHOT_HEADER_FIELDS))
@pytest.mark.parametrize("kind", ("object", "foreign", "other_snapshot"))
def test_wrong_snapshot_runtime_types_are_correspondence_errors(
    family: str,
    kind: str,
) -> None:
    context = _context()
    decision = evaluate_structural_risk(context)
    replacement = (
        object()
        if kind == "object"
        else (
            _ForeignRetainedValue()
            if kind == "foreign"
            else _foreign_snapshot(context, family)
        )
    )
    attribute = {
        "cash": "cash_snapshot",
        "positions": "position_snapshot",
        "open_orders": "open_order_snapshot",
        "quotes": "quote_snapshot",
    }[family]
    object.__setattr__(context, attribute, replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


@pytest.mark.parametrize("family", tuple(SNAPSHOT_ROW_FIELDS))
@pytest.mark.parametrize("kind", ("object", "foreign", "subclass"))
def test_wrong_snapshot_row_runtime_types_are_correspondence_errors(
    family: str,
    kind: str,
) -> None:
    context = _context_with_row(family)
    decision = evaluate_structural_risk(context)
    snapshot = _snapshot(context, family)
    object.__setattr__(
        snapshot,
        _collection_field(family),
        (_foreign_row(family, kind),),
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


@pytest.mark.parametrize("family", tuple(SNAPSHOT_ROW_FIELDS))
@pytest.mark.parametrize(
    "kind",
    ("list", "tuple_subclass", "generator", "hostile", "mapping", "bytes"),
)
def test_wrong_snapshot_container_types_are_correspondence_errors(
    family: str,
    kind: str,
) -> None:
    context = _context_with_row(family)
    decision = evaluate_structural_risk(context)
    snapshot = _snapshot(context, family)
    rows = object.__getattribute__(snapshot, _collection_field(family))
    replacements: dict[str, object] = {
        "list": list(rows),
        "tuple_subclass": _TupleSubclass(rows),
        "generator": (row for row in rows),
        "hostile": _HostileIterable(),
        "mapping": {"row": rows[0]},
        "bytes": b"rows",
    }
    object.__setattr__(snapshot, _collection_field(family), replacements[kind])
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        translate_position_target(context, decision, BASE)


@pytest.mark.parametrize(
    ("family", "snapshot_type"),
    (
        ("cash", AccountCashSnapshot),
        ("positions", PositionCollectionSnapshot),
        ("open_orders", OpenOrderExposureSnapshot),
        ("quotes", MarketQuoteCollectionSnapshot),
    ),
)
@pytest.mark.parametrize(
    "exception_type",
    (TypeError, ValueError, RuntimeError, AssertionError),
)
def test_unexpected_snapshot_projection_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    snapshot_type: type[object],
    exception_type: type[Exception],
) -> None:
    context = _context_with_row(family)
    decision = evaluate_structural_risk(context)

    def raise_probe(self: object) -> dict[str, object]:
        raise exception_type("snapshot projection probe")

    monkeypatch.setattr(snapshot_type, "to_dict", raise_probe)
    with pytest.raises(exception_type, match="snapshot projection probe"):
        translate_position_target(context, decision, BASE)
