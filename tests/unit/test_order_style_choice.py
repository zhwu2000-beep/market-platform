"""Tests for the v0.62 explicit order-style choice foundation."""

from __future__ import annotations

import json
from dataclasses import fields
from enum import StrEnum
from typing import cast

import pytest

import market_platform.execution_planning as execution_planning
import market_platform.execution_planning.order_style as order_style_module
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
    ORDER_STYLE_CHOICE_SCHEMA,
    POSITION_TARGET_TRANSLATION_SCHEMA,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    OrderStyle,
    OrderStyleChoice,
)


class _ForeignStyle(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class _ForeignObject:
    pass


EXPECTED_EXPORTS = [
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


def test_exact_public_api() -> None:
    historical_v062_exports = set(EXPECTED_EXPORTS)
    approved_v063_additions = {
        "LIMIT_PRICE_CHOICE_SCHEMA",
        "LimitPriceChoice",
    }
    approved_v064_additions = {
        "TIME_IN_FORCE_CHOICE_SCHEMA",
        "TimeInForce",
        "TimeInForceChoice",
    }
    approved_v065_additions = {
        'SESSION_PARTICIPATION_CHOICE_SCHEMA',
        'SessionParticipation',
        'SessionParticipationChoice',
    }
    expected_exports = [
        "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
        "LIMIT_PRICE_CHOICE_SCHEMA",
        "ORDER_STYLE_CHOICE_SCHEMA",
        "POSITION_TARGET_TRANSLATION_SCHEMA",
        'SESSION_PARTICIPATION_CHOICE_SCHEMA',
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
        'SessionParticipation',
        'SessionParticipationChoice',
        "TimeInForce",
        "TimeInForceChoice",
        "derive_broker_neutral_execution_instruction",
        "translate_position_target",
    ]

    assert historical_v062_exports <= set(execution_planning.__all__)
    assert approved_v063_additions <= set(execution_planning.__all__)
    assert approved_v064_additions <= set(execution_planning.__all__)
    assert approved_v065_additions <= set(execution_planning.__all__)
    assert execution_planning.__all__ == expected_exports
    assert len(execution_planning.__all__) == 23
    for name in expected_exports:
        assert getattr(execution_planning, name) is not None


def test_exact_schema_and_fingerprint_inventory() -> None:
    assert POSITION_TARGET_TRANSLATION_SCHEMA == "position_target_translation/v1"
    assert (
        BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA
        == "broker_neutral_execution_instruction/v1"
    )
    assert ORDER_STYLE_CHOICE_SCHEMA == "order_style_choice/v1"


def test_exact_enum_inventory() -> None:
    assert list(OrderStyle) == [OrderStyle.MARKET, OrderStyle.LIMIT]
    assert [member.value for member in OrderStyle] == ["market", "limit"]
    assert type(OrderStyle.MARKET) is OrderStyle
    assert type(OrderStyle.LIMIT) is OrderStyle


def test_exact_public_fields() -> None:
    assert [item.name for item in fields(OrderStyleChoice)] == [
        "style",
        "schema_version",
        "fingerprint",
    ]


@pytest.mark.parametrize("style", [OrderStyle.MARKET, OrderStyle.LIMIT])
def test_explicit_choices_construct(style: OrderStyle) -> None:
    choice = OrderStyleChoice(style)
    assert choice.style is style
    assert choice.schema_version == ORDER_STYLE_CHOICE_SCHEMA
    assert choice.fingerprint.startswith("sha256:")


@pytest.mark.parametrize(
    "value",
    [
        "market",
        "limit",
        "",
        "unknown",
        None,
        object(),
        {},
        {"style": "market"},
        _ForeignStyle.MARKET,
        _ForeignStyle.LIMIT,
        _ForeignObject(),
    ],
)
def test_malformed_direct_style_is_rejected(value: object) -> None:
    with pytest.raises(
        ExecutionPlanningValidationError, match="style must be an OrderStyle"
    ):
        OrderStyleChoice(cast(OrderStyle, value))


def test_missing_style_uses_python_signature_error() -> None:
    with pytest.raises(TypeError):
        OrderStyleChoice()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "arguments",
    [
        (OrderStyle.MARKET, "extra"),
        (OrderStyle.LIMIT, object()),
    ],
)
def test_extra_positional_arguments_are_rejected(arguments: tuple[object, ...]) -> None:
    with pytest.raises(TypeError):
        OrderStyleChoice(*arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "extra",
    [
        {"schema_version": ORDER_STYLE_CHOICE_SCHEMA},
        {"fingerprint": "sha256:" + "0" * 64},
        {"price": "1"},
        {"time_in_force": "DAY"},
    ],
)
def test_extra_keyword_arguments_are_rejected(extra: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        OrderStyleChoice(OrderStyle.MARKET, **extra)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("style", "value"),
    [(OrderStyle.MARKET, "market"), (OrderStyle.LIMIT, "limit")],
)
def test_projection_is_exact_json_safe_and_bounded(
    style: OrderStyle, value: str
) -> None:
    projection = OrderStyleChoice(style).to_dict()
    assert list(projection) == ["schema_version", "style", "fingerprint"]
    assert projection["schema_version"] == ORDER_STYLE_CHOICE_SCHEMA
    assert projection["style"] == value
    assert isinstance(projection["fingerprint"], str)
    assert json.loads(json.dumps(projection)) == projection
    assert len(json.dumps(projection, sort_keys=True)) < 180


@pytest.mark.parametrize("style", [OrderStyle.MARKET, OrderStyle.LIMIT])
def test_repeated_choices_are_deterministic(style: OrderStyle) -> None:
    first = OrderStyleChoice(style)
    second = OrderStyleChoice(style)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint == second.fingerprint


def test_market_and_limit_fingerprints_differ() -> None:
    assert (
        OrderStyleChoice(OrderStyle.MARKET).fingerprint
        != OrderStyleChoice(OrderStyle.LIMIT).fingerprint
    )


@pytest.mark.parametrize("style", [OrderStyle.MARKET, OrderStyle.LIMIT])
def test_fingerprint_payload_is_exact(style: OrderStyle) -> None:
    choice = OrderStyleChoice(style)
    assert choice._fingerprint_payload() == {
        "schema_version": ORDER_STYLE_CHOICE_SCHEMA,
        "style": style.value,
    }
    assert "fingerprint" not in choice._fingerprint_payload()
    assert choice.fingerprint == canonical_fingerprint(choice._fingerprint_payload())


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("style", OrderStyle.LIMIT),
        ("schema_version", "wrong/v1"),
        ("fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_stale_retained_state_is_rejected(field: str, replacement: object) -> None:
    choice = OrderStyleChoice(OrderStyle.MARKET)
    object.__setattr__(choice, field, replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    "replacement",
    ["market", "limit", _ForeignStyle.MARKET, object(), None],
)
def test_wrong_retained_style_type_is_rejected(replacement: object) -> None:
    choice = OrderStyleChoice(OrderStyle.MARKET)
    object.__setattr__(choice, "style", replacement)
    with pytest.raises(
        ExecutionPlanningCorrespondenceError,
        match="order style choice retains invalid style",
    ):
        choice.to_dict()


@pytest.mark.parametrize("field", ["style", "schema_version", "fingerprint"])
def test_deleted_required_slots_are_correspondence_errors(field: str) -> None:
    choice = OrderStyleChoice(OrderStyle.MARKET)
    object.__delattr__(choice, field)
    with pytest.raises(
        ExecutionPlanningCorrespondenceError,
        match="order style choice is missing required retained state",
    ):
        choice.to_dict()


@pytest.mark.parametrize(
    "exception_type",
    [TypeError, ValueError, RuntimeError, AssertionError],
)
def test_unexpected_fingerprint_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch, exception_type: type[Exception]
) -> None:
    choice = OrderStyleChoice(OrderStyle.MARKET)

    def raise_probe(payload: object) -> str:
        raise exception_type("order style probe")

    monkeypatch.setattr(order_style_module, "canonical_fingerprint", raise_probe)
    with pytest.raises(exception_type, match="order style probe"):
        choice.to_dict()


def test_no_implicit_market_or_parser_api() -> None:
    assert not hasattr(OrderStyleChoice, "from_optional_style")
    assert not hasattr(OrderStyleChoice, "parse")
    assert not hasattr(order_style_module, "parse_style")
    assert not hasattr(order_style_module, "derive_order_style_choice")


def test_choice_has_no_factory_provenance_state() -> None:
    choice = OrderStyleChoice(OrderStyle.MARKET)
    assert not hasattr(choice, "_token")
    assert not hasattr(choice, "_constructor_state")
    assert not hasattr(choice, "_constructor_binding")
    assert not hasattr(choice, "_source_instruction")


def test_choice_has_no_order_specification_fields() -> None:
    public_fields = {item.name for item in fields(OrderStyleChoice)}
    prohibited = {
        "instruction",
        "instruction_fingerprint",
        "account_fingerprint",
        "canonical_instrument_id",
        "plan_as_of",
        "selected_as_of",
        "created_at",
        "valid_until",
        "price",
        "limit_price",
        "stop_price",
        "time_in_force",
        "extended_hours",
        "allow_short",
        "reduce_only",
        "route",
        "authorization",
        "broker",
    }
    assert public_fields.isdisjoint(prohibited)


def test_no_specification_or_derivation_export_exists() -> None:
    prohibited = {
        "BrokerNeutralOrderSpecification",
        "OrderSpecification",
        "derive_broker_neutral_order_specification",
        "derive_order_style_choice",
    }
    assert set(execution_planning.__all__).isdisjoint(prohibited)


def test_caller_may_construct_each_valid_choice_independently() -> None:
    market = OrderStyleChoice(OrderStyle.MARKET)
    limit = OrderStyleChoice(OrderStyle.LIMIT)
    assert market.to_dict()["style"] == "market"
    assert limit.to_dict()["style"] == "limit"
