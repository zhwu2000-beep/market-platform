"""Focused tests for explicit canonical limit-price choices."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_UP,
    Decimal,
    Inexact,
    Rounded,
    localcontext,
)
from enum import Enum
from fractions import Fraction

import pytest

import market_platform.execution_planning as execution_planning
import market_platform.execution_planning.limit_price as limit_price_module
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    LIMIT_PRICE_CHOICE_SCHEMA,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    LimitPriceChoice,
)
from market_platform.instruments import CanonicalInstrumentId
from market_platform.trading_state import MarketQuote

EXPECTED_EXPORTS = [
    "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
    "LIMIT_PRICE_CHOICE_SCHEMA",
    "ORDER_STYLE_CHOICE_SCHEMA",
    "POSITION_TARGET_TRANSLATION_SCHEMA",
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
    "derive_broker_neutral_execution_instruction",
    "translate_position_target",
]


class _DecimalSubclass(Decimal):
    pass


class _StringSubclass(str):
    pass


class _ForeignCurrency(Enum):
    USD = "USD"


class _EqualitySpoof:
    def __eq__(self, _other: object) -> bool:
        return True


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
    ]
    assert len(prior_twenty_three_exports) == 23
    assert prior_twenty_three_exports <= set(execution_planning.__all__)
    assert approved_v066_additions <= set(execution_planning.__all__)
    assert execution_planning.__all__ == expected_exports
    assert len(execution_planning.__all__) == 34
    for name in expected_exports:
        assert getattr(execution_planning, name) is not None


def test_exact_public_fields() -> None:
    assert [item.name for item in fields(LimitPriceChoice)] == [
        "limit_price",
        "trading_currency",
        "schema_version",
        "fingerprint",
    ]


def test_exact_schema_and_fingerprint_inventory() -> None:
    assert LIMIT_PRICE_CHOICE_SCHEMA == "limit_price_choice/v1"
    assert {
        execution_planning.POSITION_TARGET_TRANSLATION_SCHEMA,
        execution_planning.BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
        execution_planning.ORDER_STYLE_CHOICE_SCHEMA,
        execution_planning.LIMIT_PRICE_CHOICE_SCHEMA,
    } == {
        "position_target_translation/v1",
        "broker_neutral_execution_instruction/v1",
        "order_style_choice/v1",
        "limit_price_choice/v1",
    }


@pytest.mark.parametrize(
    ("source", "currency", "expected"),
    [
        ("123.4500", "USD", "123.45"),
        ("0.125", "EUR", "0.125"),
        ("1E+2", "JPY", "100"),
        ("1E-2", "USD", "0.01"),
        ("100.0", "EUR", "100"),
        ("7", "JPY", "7"),
    ],
)
def test_valid_prices_are_canonical(source: str, currency: str, expected: str) -> None:
    choice = LimitPriceChoice(Decimal(source), currency)
    assert type(choice.limit_price) is Decimal
    assert choice.limit_price.as_tuple() == Decimal(expected).as_tuple()
    assert choice.to_dict()["limit_price"] == expected
    assert choice.trading_currency == currency


def test_equivalent_scales_have_equal_identity() -> None:
    variants = [
        LimitPriceChoice(Decimal("1.23"), "USD"),
        LimitPriceChoice(Decimal("1.230"), "USD"),
        LimitPriceChoice(Decimal("1.2300"), "USD"),
    ]
    assert len({item.limit_price.as_tuple() for item in variants}) == 1
    assert len({item.fingerprint for item in variants}) == 1
    assert len({json.dumps(item.to_dict(), sort_keys=True) for item in variants}) == 1


def test_wrong_price_runtime_types_are_rejected() -> None:
    values = [1, 1.0, "1", True, None, object(), {"value": "1"}, Fraction(1, 2)]
    for value in values:
        with pytest.raises(ExecutionPlanningValidationError):
            LimitPriceChoice(value, "USD")  # type: ignore[arg-type]
    with pytest.raises(ExecutionPlanningValidationError):
        LimitPriceChoice(_DecimalSubclass("1"), "USD")


@pytest.mark.parametrize(
    "value",
    [
        Decimal("0"),
        Decimal("-0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_nonpositive_or_nonfinite_prices_are_rejected(value: Decimal) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        LimitPriceChoice(value, "USD")


def test_unsupported_constructor_signatures_raise_type_error() -> None:
    with pytest.raises(TypeError):
        LimitPriceChoice()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LimitPriceChoice(Decimal("1"))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LimitPriceChoice(Decimal("1"), "USD", "extra")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LimitPriceChoice(
            Decimal("1"), "USD", schema_version="false"
        )  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LimitPriceChoice(
            Decimal("1"), "USD", fingerprint="false"
        )  # type: ignore[call-arg]


def test_currency_requires_exact_ascii_uppercase_three_letters() -> None:
    invalid = [
        "usd",
        "Usd",
        " USD",
        "USD ",
        "US",
        "USDD",
        "U1D",
        "U-D",
        "ＵＳＤ",
        None,
        _StringSubclass("USD"),
        _ForeignCurrency.USD,
    ]
    for value in invalid:
        with pytest.raises(ExecutionPlanningValidationError):
            LimitPriceChoice(Decimal("1"), value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        Decimal("9" * 128),
        Decimal("0." + ("0" * 63) + "1"),
        Decimal("1.2300"),
    ],
)
def test_released_price_boundaries_accept_canonicalizable_values(
    value: Decimal,
) -> None:
    assert LimitPriceChoice(value, "USD").to_dict()["limit_price"]


@pytest.mark.parametrize(
    "value",
    [
        Decimal("9" * 129),
        Decimal("0." + ("0" * 64) + "1"),
        Decimal("1E+255"),
        Decimal("1E+256"),
        Decimal("1E-1000000"),
    ],
)
def test_resource_overruns_are_rejected(value: Decimal) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        LimitPriceChoice(value, "USD")


def test_fixed_point_character_preflight_matches_released_bound() -> None:
    assert limit_price_module._project_price_size(Decimal("1E+255")) == (256, 0, 256)
    assert limit_price_module._project_price_size(Decimal("1E+256")) == (257, 0, 257)


def test_huge_exponent_is_rejected_before_formatting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_format(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("fixed-point formatting was reached")

    monkeypatch.setattr(limit_price_module, "format", forbidden_format, raising=False)
    with pytest.raises(ExecutionPlanningValidationError):
        LimitPriceChoice(Decimal("1E+1000000"), "USD")


@pytest.mark.parametrize(
    ("precision", "rounding"),
    [
        (1, ROUND_DOWN),
        (1, ROUND_UP),
        (2, ROUND_FLOOR),
        (2, ROUND_CEILING),
        (1, ROUND_FLOOR),
        (2, ROUND_UP),
    ],
)
def test_decimal_context_does_not_change_identity(
    precision: int, rounding: str
) -> None:
    baseline = LimitPriceChoice(Decimal("123.4500"), "USD")
    with localcontext() as context:
        context.prec = precision
        context.rounding = rounding
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        context.Emin = -9
        context.Emax = 9
        observed = LimitPriceChoice(Decimal("123.4500"), "USD")
    assert observed.limit_price.as_tuple() == baseline.limit_price.as_tuple()
    assert observed.to_dict() == baseline.to_dict()
    assert observed.fingerprint == baseline.fingerprint


def test_projection_is_exact_json_safe_and_bounded() -> None:
    choice = LimitPriceChoice(Decimal("123.4500"), "USD")
    assert choice.to_dict() == {
        "schema_version": "limit_price_choice/v1",
        "limit_price": "123.45",
        "trading_currency": "USD",
        "fingerprint": choice.fingerprint,
    }
    assert json.loads(json.dumps(choice.to_dict())) == choice.to_dict()
    assert type(choice.to_dict()["limit_price"]) is str


def test_fingerprint_payload_is_exact_and_semantic() -> None:
    choice = LimitPriceChoice(Decimal("123.4500"), "USD")
    assert choice.fingerprint == canonical_fingerprint(
        {
            "schema_version": "limit_price_choice/v1",
            "limit_price": "123.45",
            "trading_currency": "USD",
        }
    )
    assert choice.fingerprint != LimitPriceChoice(Decimal("123.46"), "USD").fingerprint
    assert choice.fingerprint != LimitPriceChoice(Decimal("123.45"), "EUR").fingerprint


@pytest.mark.parametrize("source", ["1", "1.2300", "0.01", "1E+2"])
def test_market_quote_price_contract_parity(source: str) -> None:
    price = Decimal(source)
    choice = LimitPriceChoice(price, "USD")
    quote = MarketQuote(CanonicalInstrumentId("parity_instrument"), last=price)
    assert choice.limit_price.as_tuple() == quote.last.as_tuple()
    assert choice.to_dict()["limit_price"] == quote.to_dict()["last"]


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1.2300"),
        Decimal("-1"),
        Decimal("0"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("9" * 129),
        Decimal("1E+1000000"),
    ],
)
def test_malformed_retained_price_is_rejected(value: Decimal) -> None:
    choice = LimitPriceChoice(Decimal("1.23"), "USD")
    object.__setattr__(choice, "limit_price", value)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


def test_malformed_retained_currency_is_rejected() -> None:
    for value in ["usd", " USD", "US", "U1D", _StringSubclass("USD"), None]:
        choice = LimitPriceChoice(Decimal("1.23"), "USD")
        object.__setattr__(choice, "trading_currency", value)
        with pytest.raises(ExecutionPlanningCorrespondenceError):
            choice.to_dict()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("schema_version", "false/v1"), ("fingerprint", "sha256:" + ("0" * 64))],
)
def test_stale_schema_or_fingerprint_is_rejected(
    field_name: str, value: object
) -> None:
    choice = LimitPriceChoice(Decimal("1.23"), "USD")
    object.__setattr__(choice, field_name, value)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    ("field_name", "replacement_factory"),
    [
        ("schema_version", lambda _choice: _EqualitySpoof()),
        (
            "schema_version",
            lambda choice: _StringSubclass(choice.schema_version),
        ),
        ("fingerprint", lambda _choice: _EqualitySpoof()),
        ("fingerprint", lambda choice: _StringSubclass(choice.fingerprint)),
    ],
    ids=[
        "schema-equality-spoof",
        "schema-string-subclass",
        "fingerprint-equality-spoof",
        "fingerprint-string-subclass",
    ],
)
def test_retained_identity_strings_require_exact_builtin_types(
    field_name: str,
    replacement_factory: Callable[[LimitPriceChoice], object],
) -> None:
    choice = LimitPriceChoice(Decimal("1.23"), "USD")
    replacement = replacement_factory(choice)
    assert replacement == object.__getattribute__(choice, field_name)
    object.__setattr__(choice, field_name, replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    "field_name",
    ["limit_price", "trading_currency", "schema_version", "fingerprint"],
)
def test_deleted_required_slots_are_correspondence_errors(field_name: str) -> None:
    choice = LimitPriceChoice(Decimal("1.23"), "USD")
    object.__delattr__(choice, field_name)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda: TypeError("controlled"),
        lambda: ValueError("controlled"),
        lambda: RuntimeError("controlled"),
        lambda: AssertionError("controlled"),
    ],
)
def test_unexpected_fingerprint_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch,
    exception_factory: Callable[[], BaseException],
) -> None:
    choice = LimitPriceChoice(Decimal("1.23"), "USD")

    def fail(_payload: object) -> str:
        raise exception_factory()

    monkeypatch.setattr(limit_price_module, "canonical_fingerprint", fail)
    with pytest.raises(type(exception_factory()), match="controlled"):
        choice.to_dict()


def test_caller_authored_value_has_no_provenance_hardening() -> None:
    choice = LimitPriceChoice(Decimal("1.23"), "USD")
    assert choice == LimitPriceChoice(Decimal("1.230"), "USD")
    for name in (
        "_construction_token",
        "_constructor_state",
        "_identity_binding",
        "_retained_source",
    ):
        assert not hasattr(choice, name)
    assert not hasattr(limit_price_module, "derive_limit_price_choice")


def test_scope_is_limited_to_price_and_currency_choice() -> None:
    public_fields = {item.name for item in fields(LimitPriceChoice)}
    assert public_fields == {
        "limit_price",
        "trading_currency",
        "schema_version",
        "fingerprint",
    }
    forbidden = {
        "style",
        "instruction",
        "instrument",
        "account",
        "timestamp",
        "quote",
        "time_in_force",
        "session",
        "tick_size",
        "authorization",
        "broker",
    }
    assert public_fields.isdisjoint(forbidden)
    for name in (
        "BrokerNeutralOrderSpecification",
        "construct_broker_neutral_order_specification",
        "derive_broker_neutral_order_specification",
        "map_to_broker_order",
    ):
        assert not hasattr(limit_price_module, name)
    for method in (
        "construct_specification",
        "bind_instrument",
        "validate_tick_size",
        "convert_currency",
        "authorize",
        "submit",
    ):
        assert not hasattr(LimitPriceChoice, method)
