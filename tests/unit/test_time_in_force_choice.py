"""Focused tests for explicit canonical time-in-force choices."""

from __future__ import annotations

import json
from dataclasses import MISSING, FrozenInstanceError, fields
from enum import StrEnum
from typing import cast

import pytest

import market_platform.execution_planning as execution_planning
import market_platform.execution_planning.time_in_force as time_in_force_module
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    TIME_IN_FORCE_CHOICE_SCHEMA,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    TimeInForce,
    TimeInForceChoice,
)


class _ForeignTimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"


class _EqualitySpoof:
    def __eq__(self, _other: object) -> bool:
        return True


class _StringSubclass(str):
    pass


EXPECTED_EXPORTS = [
    "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
    "LIMIT_PRICE_CHOICE_SCHEMA",
    "ORDER_STYLE_CHOICE_SCHEMA",
    "POSITION_TARGET_TRANSLATION_SCHEMA",
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
    "TimeInForce",
    "TimeInForceChoice",
    "derive_broker_neutral_execution_instruction",
    "translate_position_target",
]


def test_exact_public_api() -> None:
    prior_seventeen = set(EXPECTED_EXPORTS) - {
        "TIME_IN_FORCE_CHOICE_SCHEMA",
        "TimeInForce",
        "TimeInForceChoice",
    }
    additions = {
        "TIME_IN_FORCE_CHOICE_SCHEMA",
        "TimeInForce",
        "TimeInForceChoice",
    }
    assert prior_seventeen <= set(execution_planning.__all__)
    assert additions <= set(execution_planning.__all__)
    assert execution_planning.__all__ == EXPECTED_EXPORTS
    assert len(execution_planning.__all__) == 20
    for name in EXPECTED_EXPORTS:
        assert getattr(execution_planning, name) is not None


def test_exact_schema_and_fingerprint_inventory() -> None:
    assert TIME_IN_FORCE_CHOICE_SCHEMA == "time_in_force_choice/v1"
    assert {
        execution_planning.POSITION_TARGET_TRANSLATION_SCHEMA,
        execution_planning.BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
        execution_planning.ORDER_STYLE_CHOICE_SCHEMA,
        execution_planning.LIMIT_PRICE_CHOICE_SCHEMA,
        execution_planning.TIME_IN_FORCE_CHOICE_SCHEMA,
    } == {
        "position_target_translation/v1",
        "broker_neutral_execution_instruction/v1",
        "order_style_choice/v1",
        "limit_price_choice/v1",
        "time_in_force_choice/v1",
    }


def test_exact_enum_inventory() -> None:
    assert list(TimeInForce) == [
        TimeInForce.DAY,
        TimeInForce.GTC,
        TimeInForce.IOC,
        TimeInForce.FOK,
    ]
    assert [member.value for member in TimeInForce] == ["day", "gtc", "ioc", "fok"]
    assert [member.name for member in TimeInForce] == ["DAY", "GTC", "IOC", "FOK"]
    assert len(TimeInForce.__members__) == 4
    for name in ("GTD", "UNKNOWN", "UNSPECIFIED", "DEFAULT", "NO_ACTION"):
        assert name not in TimeInForce.__members__


def test_exact_fields_immutability_and_scope() -> None:
    assert [item.name for item in fields(TimeInForceChoice)] == [
        "time_in_force",
        "schema_version",
        "fingerprint",
    ]
    choice = TimeInForceChoice(TimeInForce.DAY)
    assert not hasattr(choice, "__dict__")
    with pytest.raises(FrozenInstanceError):
        choice.time_in_force = TimeInForce.GTC  # type: ignore[misc]
    for name in (
        "_token",
        "_constructor_state",
        "_constructor_binding",
        "_source",
        "_source_instruction",
        "style",
        "limit_price",
        "instruction",
        "instrument",
        "account",
        "selected_as_of",
        "expires_at",
        "session",
        "capability",
        "authorization",
        "broker",
    ):
        assert not hasattr(choice, name)


@pytest.mark.parametrize(
    "time_in_force",
    [TimeInForce.DAY, TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK],
)
def test_each_explicit_choice_constructs(time_in_force: TimeInForce) -> None:
    choice = TimeInForceChoice(time_in_force)
    assert choice.time_in_force is time_in_force
    assert type(choice.schema_version) is str
    assert type(choice.fingerprint) is str


def test_plain_strings_are_rejected_without_conversion() -> None:
    for value in ("day", "gtc", "ioc", "fok"):
        with pytest.raises(
            ExecutionPlanningValidationError,
            match="time_in_force must be a TimeInForce",
        ):
            TimeInForceChoice(cast(TimeInForce, value))


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        True,
        {},
        object(),
        _ForeignTimeInForce.DAY,
        _ForeignTimeInForce.GTC,
    ],
)
def test_other_malformed_direct_values_are_rejected(value: object) -> None:
    with pytest.raises(
        ExecutionPlanningValidationError,
        match="time_in_force must be a TimeInForce",
    ):
        TimeInForceChoice(cast(TimeInForce, value))


def test_missing_choice_uses_python_signature_error() -> None:
    with pytest.raises(TypeError):
        TimeInForceChoice()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("arguments", "keywords"),
    [
        ((TimeInForce.DAY, "extra"), {}),
        ((TimeInForce.DAY,), {"schema_version": TIME_IN_FORCE_CHOICE_SCHEMA}),
        ((TimeInForce.DAY,), {"fingerprint": "sha256:" + "0" * 64}),
        ((TimeInForce.DAY,), {"expiry": "2026-08-04T00:00:00+00:00"}),
    ],
)
def test_unsupported_constructor_signatures_are_rejected(
    arguments: tuple[object, ...], keywords: dict[str, object]
) -> None:
    with pytest.raises(TypeError):
        TimeInForceChoice(*arguments, **keywords)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("time_in_force", "value"),
    [
        (TimeInForce.DAY, "day"),
        (TimeInForce.GTC, "gtc"),
        (TimeInForce.IOC, "ioc"),
        (TimeInForce.FOK, "fok"),
    ],
)
def test_projection_is_exact_json_safe_and_bounded(
    time_in_force: TimeInForce, value: str
) -> None:
    projection = TimeInForceChoice(time_in_force).to_dict()
    assert list(projection) == ["schema_version", "time_in_force", "fingerprint"]
    assert projection["schema_version"] == TIME_IN_FORCE_CHOICE_SCHEMA
    assert projection["time_in_force"] == value
    assert type(projection["time_in_force"]) is str
    assert json.loads(json.dumps(projection)) == projection
    assert len(json.dumps(projection, sort_keys=True)) < 190


@pytest.mark.parametrize(
    "time_in_force",
    [TimeInForce.DAY, TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK],
)
def test_repeated_choices_are_deterministic(time_in_force: TimeInForce) -> None:
    first = TimeInForceChoice(time_in_force)
    second = TimeInForceChoice(time_in_force)
    assert first == second
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint == second.fingerprint


def test_all_choice_fingerprints_are_distinct() -> None:
    assert len(
        {
            TimeInForceChoice(time_in_force).fingerprint
            for time_in_force in TimeInForce
        }
    ) == 4


@pytest.mark.parametrize(
    "time_in_force",
    [TimeInForce.DAY, TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK],
)
def test_fingerprint_payload_is_exact(time_in_force: TimeInForce) -> None:
    choice = TimeInForceChoice(time_in_force)
    assert choice._fingerprint_payload() == {
        "schema_version": TIME_IN_FORCE_CHOICE_SCHEMA,
        "time_in_force": time_in_force.value,
    }
    assert "fingerprint" not in choice._fingerprint_payload()
    assert choice.fingerprint == canonical_fingerprint(choice._fingerprint_payload())


def test_no_implicit_day_parser_factory_or_gtd_api() -> None:
    assert TimeInForceChoice.__dataclass_fields__["time_in_force"].default is MISSING
    assert "GTD" not in TimeInForce.__members__
    for name in (
        "parse",
        "from_string",
        "from_optional",
        "derive_time_in_force_choice",
        "GoodTilDateChoice",
        "BrokerNeutralOrderSpecification",
    ):
        assert not hasattr(time_in_force_module, name)
        assert name not in execution_planning.__all__


@pytest.mark.parametrize(
    "replacement",
    [
        "day",
        _ForeignTimeInForce.DAY,
        _EqualitySpoof(),
        TimeInForce.GTC,
    ],
)
def test_malformed_or_stale_retained_tif_is_rejected(replacement: object) -> None:
    choice = TimeInForceChoice(TimeInForce.DAY)
    object.__setattr__(choice, "time_in_force", replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("schema_version", "wrong/v1"),
        ("fingerprint", "sha256:" + "0" * 64),
        ("schema_version", _EqualitySpoof()),
        ("schema_version", _StringSubclass(TIME_IN_FORCE_CHOICE_SCHEMA)),
        ("fingerprint", _EqualitySpoof()),
        (
            "fingerprint",
            _StringSubclass(TimeInForceChoice(TimeInForce.DAY).fingerprint),
        ),
    ],
)
def test_retained_schema_and_fingerprint_require_exact_strings(
    field: str, replacement: object
) -> None:
    choice = TimeInForceChoice(TimeInForce.DAY)
    object.__setattr__(choice, field, replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    "field", ["time_in_force", "schema_version", "fingerprint"]
)
def test_deleted_required_slots_are_correspondence_errors(field: str) -> None:
    choice = TimeInForceChoice(TimeInForce.DAY)
    object.__delattr__(choice, field)
    with pytest.raises(
        ExecutionPlanningCorrespondenceError,
        match="time-in-force choice is missing required retained state",
    ):
        choice.to_dict()


@pytest.mark.parametrize(
    "exception_type",
    [TypeError, ValueError, RuntimeError, AssertionError],
)
def test_unexpected_fingerprint_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch, exception_type: type[Exception]
) -> None:
    choice = TimeInForceChoice(TimeInForce.DAY)

    def raise_probe(payload: object) -> str:
        raise exception_type("time-in-force probe")

    monkeypatch.setattr(time_in_force_module, "canonical_fingerprint", raise_probe)
    with pytest.raises(exception_type, match="time-in-force probe"):
        choice.to_dict()
