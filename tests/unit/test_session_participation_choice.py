import json
from dataclasses import FrozenInstanceError, fields
from enum import StrEnum
from typing import Any

import pytest

import market_platform.execution_planning as execution_planning
from market_platform.execution_planning import (
    SESSION_PARTICIPATION_CHOICE_SCHEMA,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    SessionParticipation,
    SessionParticipationChoice,
)
from market_platform.execution_planning import (
    session_participation as session_participation_module,
)

EXPECTED_EXPORTS = [
    'BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA',
    'LIMIT_PRICE_CHOICE_SCHEMA',
    'ORDER_STYLE_CHOICE_SCHEMA',
    'POSITION_TARGET_TRANSLATION_SCHEMA',
    'SESSION_PARTICIPATION_CHOICE_SCHEMA',
    'TIME_IN_FORCE_CHOICE_SCHEMA',
    'BrokerNeutralExecutionInstruction',
    'ExecutionPlanningCorrespondenceError',
    'ExecutionPlanningDomainError',
    'ExecutionPlanningUnavailableError',
    'ExecutionPlanningValidationError',
    'ExecutionInstructionSide',
    'LimitPriceChoice',
    'OrderStyle',
    'OrderStyleChoice',
    'PositionDeltaAction',
    'PositionTargetTranslation',
    'SessionParticipation',
    'SessionParticipationChoice',
    'TimeInForce',
    'TimeInForceChoice',
    'derive_broker_neutral_execution_instruction',
    'translate_position_target',
]


class _ForeignSession(StrEnum):
    REGULAR_ONLY = 'regular_only'


class _EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        return True


class _StringSubclass(str):
    pass


def _valid_choice() -> SessionParticipationChoice:
    return SessionParticipationChoice(SessionParticipation.REGULAR_ONLY)


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


def test_exact_schema_and_fingerprint_inventory() -> None:
    assert SESSION_PARTICIPATION_CHOICE_SCHEMA == 'session_participation_choice/v1'
    assert {
        execution_planning.POSITION_TARGET_TRANSLATION_SCHEMA,
        execution_planning.BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
        execution_planning.ORDER_STYLE_CHOICE_SCHEMA,
        execution_planning.LIMIT_PRICE_CHOICE_SCHEMA,
        execution_planning.TIME_IN_FORCE_CHOICE_SCHEMA,
        execution_planning.SESSION_PARTICIPATION_CHOICE_SCHEMA,
    } == {
        'position_target_translation/v1',
        'broker_neutral_execution_instruction/v1',
        'order_style_choice/v1',
        'limit_price_choice/v1',
        'time_in_force_choice/v1',
        'session_participation_choice/v1',
    }


def test_exact_enum_inventory() -> None:
    assert list(SessionParticipation) == [
        SessionParticipation.REGULAR_ONLY,
        SessionParticipation.REGULAR_AND_EXTENDED,
    ]
    assert [member.value for member in SessionParticipation] == [
        'regular_only',
        'regular_and_extended',
    ]
    assert len(SessionParticipation.__members__) == 2
    for prohibited in (
        'EXTENDED_ONLY',
        'ALL_ELIGIBLE_SESSIONS',
        'BROKER_DEFAULT',
        'UNSPECIFIED',
        'DEFAULT',
        'UNKNOWN',
        'NO_ACTION',
    ):
        assert prohibited not in SessionParticipation.__members__


def test_exact_fields_and_scope_absence() -> None:
    assert [item.name for item in fields(SessionParticipationChoice)] == [
        'session_participation',
        'schema_version',
        'fingerprint',
    ]
    prohibited = {
        'calendar', 'timezone', 'created_at', 'selected_as_of', 'plan_as_of',
        'valid_until', 'expires_at', 'current_open', 'instrument', 'venue',
        'style', 'limit_price', 'time_in_force', 'instruction', 'account',
        'capability', 'authorization', 'specification', 'broker', 'submission',
        'lifecycle', '_token', '_constructor_state', '_source',
    }
    assert prohibited.isdisjoint(
        item.name for item in fields(SessionParticipationChoice)
    )
    assert not hasattr(_valid_choice(), '__dict__')


@pytest.mark.parametrize('value', list(SessionParticipation))
def test_valid_direct_construction(value: SessionParticipation) -> None:
    choice = SessionParticipationChoice(value)
    assert choice.session_participation is value
    assert choice.schema_version == SESSION_PARTICIPATION_CHOICE_SCHEMA
    assert type(choice.schema_version) is str
    assert type(choice.fingerprint) is str


def test_plain_strings_are_rejected() -> None:
    for value in ('regular_only', 'regular_and_extended', 'REGULAR_ONLY', ''):
        with pytest.raises(ExecutionPlanningValidationError):
            SessionParticipationChoice(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    'value',
    [None, 1, True, {}, object(), _ForeignSession.REGULAR_ONLY, _EqualitySpoof()],
)
def test_malformed_direct_values_are_rejected(value: Any) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        SessionParticipationChoice(value)


def test_missing_argument_fails_without_implicit_default() -> None:
    with pytest.raises(TypeError):
        SessionParticipationChoice()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    'kwargs',
    [
        {'schema_version': SESSION_PARTICIPATION_CHOICE_SCHEMA},
        {'fingerprint': 'sha256:fabricated'},
        {'calendar': object()},
    ],
)
def test_caller_cannot_supply_derived_or_extra_fields(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        SessionParticipationChoice(SessionParticipation.REGULAR_ONLY, **kwargs)


@pytest.mark.parametrize('value', list(SessionParticipation))
def test_projection_is_exact_and_lowercase(value: SessionParticipation) -> None:
    choice = SessionParticipationChoice(value)
    assert choice.to_dict() == {
        'schema_version': SESSION_PARTICIPATION_CHOICE_SCHEMA,
        'session_participation': value.value,
        'fingerprint': choice.fingerprint,
    }
    assert type(choice.to_dict()['session_participation']) is str


@pytest.mark.parametrize('value', list(SessionParticipation))
def test_reconstruction_is_deterministic(value: SessionParticipation) -> None:
    first = SessionParticipationChoice(value)
    second = SessionParticipationChoice(value)
    assert first == second
    assert first.to_dict() == second.to_dict()


def test_participation_changes_fingerprint() -> None:
    regular = SessionParticipationChoice(SessionParticipation.REGULAR_ONLY)
    extended = SessionParticipationChoice(SessionParticipation.REGULAR_AND_EXTENDED)
    assert regular.fingerprint != extended.fingerprint


@pytest.mark.parametrize('value', list(SessionParticipation))
def test_fingerprint_payload_is_exact(value: SessionParticipation) -> None:
    choice = SessionParticipationChoice(value)
    assert choice._fingerprint_payload() == {
        'schema_version': SESSION_PARTICIPATION_CHOICE_SCHEMA,
        'session_participation': value.value,
    }
    assert 'fingerprint' not in choice._fingerprint_payload()


def test_choice_is_frozen() -> None:
    choice = _valid_choice()
    with pytest.raises(FrozenInstanceError):
        choice.session_participation = SessionParticipation.REGULAR_AND_EXTENDED


def test_no_parser_default_or_local_choice_factory_api() -> None:
    for name in (
        'parse_session_participation',
        'derive_session_participation_choice',
        'BROKER_DEFAULT',
        'DEFAULT_SESSION_PARTICIPATION',
    ):
        assert not hasattr(session_participation_module, name)
        assert not hasattr(execution_planning, name)
    for method in (
        'parse',
        'from_string',
        'from_optional',
        'construct_specification',
        'derive_specification',
    ):
        assert not hasattr(SessionParticipationChoice, method)
    assert callable(execution_planning.construct_broker_neutral_order_specification)


@pytest.mark.parametrize(
    'retained',
    [
        'regular_only',
        _ForeignSession.REGULAR_ONLY,
        object(),
        _EqualitySpoof(),
        SessionParticipation.REGULAR_AND_EXTENDED,
    ],
)
def test_malformed_or_stale_retained_session_is_rejected(retained: Any) -> None:
    choice = _valid_choice()
    object.__setattr__(choice, 'session_participation', retained)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    ('slot', 'retained'),
    [
        ('schema_version', 'wrong/v1'),
        ('fingerprint', 'sha256:wrong'),
        ('schema_version', _EqualitySpoof()),
        (
            'schema_version',
            _StringSubclass(SESSION_PARTICIPATION_CHOICE_SCHEMA),
        ),
        ('fingerprint', _EqualitySpoof()),
        ('fingerprint', _StringSubclass(_valid_choice().fingerprint)),
    ],
)
def test_retained_schema_and_fingerprint_require_exact_strings(
    slot: str,
    retained: Any,
) -> None:
    choice = _valid_choice()
    object.__setattr__(choice, slot, retained)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    'slot',
    ['session_participation', 'schema_version', 'fingerprint'],
)
def test_deleted_required_slots_become_correspondence_errors(slot: str) -> None:
    choice = _valid_choice()
    object.__delattr__(choice, slot)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        choice.to_dict()


@pytest.mark.parametrize(
    'exception_type',
    [TypeError, ValueError, RuntimeError, AssertionError],
)
def test_unexpected_fingerprint_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[Exception],
) -> None:
    choice = _valid_choice()

    def raise_probe(payload: object) -> str:
        raise exception_type('session-participation probe')

    monkeypatch.setattr(
        session_participation_module, 'canonical_fingerprint', raise_probe
    )
    with pytest.raises(exception_type, match='session-participation probe'):
        choice.to_dict()


def test_projection_is_json_safe() -> None:
    projection = _valid_choice().to_dict()
    assert json.loads(json.dumps(projection)) == projection


def test_module_exports_only_approved_public_names() -> None:
    assert session_participation_module.__all__ == [
        'SESSION_PARTICIPATION_CHOICE_SCHEMA',
        'SessionParticipation',
        'SessionParticipationChoice',
    ]


def test_valid_exact_retained_strings_still_project() -> None:
    choice = _valid_choice()
    assert type(choice.schema_version) is str
    assert type(choice.fingerprint) is str
    assert choice.to_dict()['fingerprint'] == choice.fingerprint


def test_equality_spoof_is_a_genuine_old_equality_attack() -> None:
    spoof = _EqualitySpoof()
    assert type(spoof) is not str
    assert spoof == SESSION_PARTICIPATION_CHOICE_SCHEMA


def test_no_boolean_extended_hours_replacement() -> None:
    choice = _valid_choice()
    assert not hasattr(choice, 'extended_hours')
    assert not hasattr(SessionParticipationChoice, 'extended_hours')


def test_no_temporal_or_calendar_behavior() -> None:
    choice = _valid_choice()
    for name in ('is_open', 'session_window', 'calendar', 'expires_at', 'timezone'):
        assert not hasattr(choice, name)


def test_each_caller_authored_choice_can_exist_independently() -> None:
    choices = [SessionParticipationChoice(value) for value in SessionParticipation]
    assert [choice.session_participation for choice in choices] == list(
        SessionParticipation
    )
