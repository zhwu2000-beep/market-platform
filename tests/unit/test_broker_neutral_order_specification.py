"""Focused tests for v0.66 broker-neutral order specifications."""

from __future__ import annotations

import gc
import inspect
import json
import weakref
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA,
    BrokerNeutralExecutionInstruction,
    BrokerNeutralOrderSpecification,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    LimitPriceChoice,
    OrderStyle,
    OrderStyleChoice,
    PositionTargetTranslation,
    SessionParticipation,
    SessionParticipationChoice,
    TimeInForce,
    TimeInForceChoice,
    construct_broker_neutral_order_specification,
    derive_broker_neutral_execution_instruction,
    translate_position_target,
)
from market_platform.execution_planning import (
    order_specification as specification_module,
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

EXPECTED_EXPORTS = [
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
]


class _EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        return True


class _StringSubclass(str):
    pass


@dataclass
class _Foreign:
    value: object = None


class _ForeignEnum(StrEnum):
    VALUE = "market"


class _InstructionSubclass(BrokerNeutralExecutionInstruction):
    pass


class _InstrumentSubclass(CanonicalInstrument):
    pass


class _StyleSubclass(OrderStyleChoice):
    pass


class _TifSubclass(TimeInForceChoice):
    pass


class _SessionSubclass(SessionParticipationChoice):
    pass


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


def _canonical(
    *,
    instrument_id: str = "instrument.AAPL",
    symbol: str = "AAPL",
    venue: str = "NASDAQ",
    asset_class: InstrumentAssetClass = InstrumentAssetClass.EQUITY,
    currency: str = "USD",
) -> CanonicalInstrument:
    return CanonicalInstrument(
        CanonicalInstrumentId(instrument_id),
        TradingInstrumentIdentity(symbol, venue),
        asset_class,
        currency,
    )


def _resolution() -> InstrumentResolution:
    external = ExternalInstrumentIdentity("vendor", "AAPL", "XNAS")
    mapping = InstrumentMapping(
        external,
        _canonical(),
        InstrumentMappingSourceIdentity("mapping", "1"),
        BASE - timedelta(days=1),
        None,
    )
    return resolve_instrument_mapping(external, [mapping], BASE)


def _intent() -> OrderIntent:
    signal = TradingSignal(
        TradingSignalSourceIdentity("strategy", "1"),
        "event",
        TradingInstrumentIdentity("AAPL", "NASDAQ"),
        "1m",
        TradingTargetPosition.LONG,
        Decimal("10"),
        BASE - timedelta(hours=2),
        BASE - timedelta(hours=2),
        BASE + timedelta(hours=2),
    )
    return create_order_intent_from_signal(
        signal, ExactTargetPositionIntentPolicy(), BASE - timedelta(hours=1)
    )


def _translation() -> PositionTargetTranslation:
    account = TradingAccountIdentity(
        "broker", "account-1", TradingEnvironment.PAPER, "USD"
    )
    source = StateSnapshotSourceIdentity("snapshot", "1")
    resolution = _resolution()
    instrument_id = resolution.mapping.canonical_instrument.instrument_id
    context = RiskEvaluationContext(
        _intent(),
        resolution,
        AccountCashSnapshot(
            account,
            source,
            BASE - timedelta(seconds=10),
            [CashBalance("USD", Decimal("1000"))],
        ),
        PositionCollectionSnapshot(
            account,
            source,
            BASE - timedelta(seconds=9),
            [PositionRecord(instrument_id, Decimal("4"))],
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


def _instruction() -> BrokerNeutralExecutionInstruction:
    result = derive_broker_neutral_execution_instruction(_translation())
    assert result is not None
    return result


def _sources(
    style: OrderStyle = OrderStyle.MARKET,
    *,
    tif: TimeInForce = TimeInForce.DAY,
    session: SessionParticipation = SessionParticipation.REGULAR_ONLY,
) -> dict[str, object]:
    return {
        "instruction": _instruction(),
        "canonical_instrument": _canonical(),
        "order_style_choice": OrderStyleChoice(style),
        "limit_price_choice": (
            None
            if style is OrderStyle.MARKET
            else LimitPriceChoice(Decimal("190.25"), "USD")
        ),
        "time_in_force_choice": TimeInForceChoice(tif),
        "session_participation_choice": SessionParticipationChoice(session),
    }


def _construct(**overrides: object) -> BrokerNeutralOrderSpecification:
    values = _sources()
    values.update(overrides)
    return construct_broker_neutral_order_specification(**values)  # type: ignore[arg-type]


def test_exact_public_api() -> None:
    prior = set(EXPECTED_EXPORTS) - {
        "BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA",
        "BrokerNeutralOrderSpecification",
        "construct_broker_neutral_order_specification",
    }
    assert len(prior) == 23
    assert prior <= set(execution_planning.__all__)
    assert execution_planning.__all__ == EXPECTED_EXPORTS
    assert len(execution_planning.__all__) == 26
    assert all(
        getattr(execution_planning, name) is not None for name in EXPECTED_EXPORTS
    )


def test_exact_schema_and_fingerprint_inventory() -> None:
    assert (
        BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA
        == "broker_neutral_order_specification/v1"
    )
    assert {
        value
        for name, value in vars(execution_planning).items()
        if name.endswith("_SCHEMA") and isinstance(value, str)
    } == {
        "position_target_translation/v1",
        "broker_neutral_execution_instruction/v1",
        "broker_neutral_order_specification/v1",
        "order_style_choice/v1",
        "limit_price_choice/v1",
        "time_in_force_choice/v1",
        "session_participation_choice/v1",
    }
    assert specification_module.__all__ == [
        "BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA",
        "BrokerNeutralOrderSpecification",
        "construct_broker_neutral_order_specification",
    ]


def test_exact_fields_and_factory_owned_shape() -> None:
    all_fields = [field.name for field in fields(BrokerNeutralOrderSpecification)]
    assert all_fields[:8] == [
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "limit_price_choice",
        "time_in_force_choice",
        "session_participation_choice",
        "schema_version",
        "fingerprint",
    ]
    assert all_fields[8:] == ["_constructor_state", "_constructor_binding", "_token"]
    assert BrokerNeutralOrderSpecification.__slots__ == (*all_fields, "__weakref__")


def test_factory_signature_is_exact_and_keyword_only() -> None:
    parameters = list(
        inspect.signature(
            construct_broker_neutral_order_specification
        ).parameters.values()
    )
    assert [parameter.name for parameter in parameters] == [
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "limit_price_choice",
        "time_in_force_choice",
        "session_participation_choice",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in parameters
    )
    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters)


def test_direct_construction_is_prohibited() -> None:
    with pytest.raises(TypeError, match="must be created"):
        BrokerNeutralOrderSpecification()


@pytest.mark.parametrize("tif", list(TimeInForce))
@pytest.mark.parametrize("session", list(SessionParticipation))
def test_valid_market_construction(
    tif: TimeInForce, session: SessionParticipation
) -> None:
    result = construct_broker_neutral_order_specification(
        **_sources(tif=tif, session=session)
    )  # type: ignore[arg-type]
    assert result.limit_price_choice is None
    assert result.to_dict()["limit_price_choice"] is None


@pytest.mark.parametrize("tif", list(TimeInForce))
@pytest.mark.parametrize("session", list(SessionParticipation))
def test_valid_limit_construction(
    tif: TimeInForce, session: SessionParticipation
) -> None:
    result = construct_broker_neutral_order_specification(
        **_sources(OrderStyle.LIMIT, tif=tif, session=session)
    )  # type: ignore[arg-type]
    assert result.limit_price_choice is not None
    assert result.to_dict()["limit_price_choice"]["limit_price"] == "190.25"  # type: ignore[index]


_NON_PRICE_FIELDS = [
    "instruction",
    "canonical_instrument",
    "order_style_choice",
    "time_in_force_choice",
    "session_participation_choice",
]


@pytest.mark.parametrize("field_name", _NON_PRICE_FIELDS)
@pytest.mark.parametrize(
    "bad_kind", ["none", "string", "mapping", "object", "spoof", "subclass"]
)
def test_wrong_non_price_source_types_are_rejected(
    field_name: str, bad_kind: str
) -> None:
    subclasses: dict[str, type[object]] = {
        "instruction": _InstructionSubclass,
        "canonical_instrument": _InstrumentSubclass,
        "order_style_choice": _StyleSubclass,
        "time_in_force_choice": _TifSubclass,
        "session_participation_choice": _SessionSubclass,
    }
    bad: object = {
        "none": None,
        "string": "source",
        "mapping": {},
        "object": _Foreign(),
        "spoof": _EqualitySpoof(),
        "subclass": object.__new__(subclasses[field_name]),
    }[bad_kind]
    with pytest.raises(ExecutionPlanningValidationError):
        _construct(**{field_name: bad})


@pytest.mark.parametrize(
    "missing",
    list(inspect.signature(construct_broker_neutral_order_specification).parameters),
)
def test_every_factory_argument_is_required(missing: str) -> None:
    values = _sources()
    del values[missing]
    with pytest.raises(TypeError):
        construct_broker_neutral_order_specification(**values)  # type: ignore[arg-type]


def test_positional_factory_use_is_rejected() -> None:
    values = _sources()
    with pytest.raises(TypeError):
        construct_broker_neutral_order_specification(*values.values())  # type: ignore[misc]


def test_extra_factory_argument_is_rejected() -> None:
    with pytest.raises(TypeError):
        construct_broker_neutral_order_specification(**_sources(), extra=True)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "price", [LimitPriceChoice(Decimal("1"), "USD"), _ForeignEnum.VALUE, _Foreign()]
)
def test_market_rejects_every_non_null_price(price: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError, match="MARKET"):
        _construct(limit_price_choice=price)


@pytest.mark.parametrize("price", [None, "190", {}, _Foreign(), Decimal("190")])
def test_limit_rejects_missing_or_foreign_price(price: object) -> None:
    values = _sources(OrderStyle.LIMIT)
    values["limit_price_choice"] = price
    with pytest.raises(ExecutionPlanningValidationError, match="LimitPriceChoice"):
        construct_broker_neutral_order_specification(**values)  # type: ignore[arg-type]


def test_limit_currency_mismatch_is_rejected_without_conversion() -> None:
    values = _sources(OrderStyle.LIMIT)
    values["limit_price_choice"] = LimitPriceChoice(Decimal("190.25"), "EUR")
    with pytest.raises(ExecutionPlanningValidationError, match="currency"):
        construct_broker_neutral_order_specification(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changed",
    [
        {"instrument_id": "instrument.MSFT"},
        {"symbol": "MSFT"},
        {"venue": "NYSE"},
        {"asset_class": InstrumentAssetClass.ETF},
        {"currency": "EUR"},
    ],
)
def test_wrong_canonical_descriptor_is_rejected(changed: dict[str, object]) -> None:
    with pytest.raises(ExecutionPlanningValidationError, match="canonical instrument"):
        _construct(canonical_instrument=_canonical(**changed))  # type: ignore[arg-type]


@pytest.mark.parametrize("style", list(OrderStyle))
def test_projection_is_exact_nested_json_safe_and_ordered(style: OrderStyle) -> None:
    result = construct_broker_neutral_order_specification(**_sources(style))  # type: ignore[arg-type]
    projection = result.to_dict()
    assert list(projection) == [
        "schema_version",
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "limit_price_choice",
        "time_in_force_choice",
        "session_participation_choice",
        "fingerprint",
    ]
    assert json.loads(json.dumps(projection, allow_nan=False)) == projection
    assert not ({"side", "quantity", "account", "plan_as_of"} & set(projection))


@pytest.mark.parametrize("style", list(OrderStyle))
def test_fingerprint_is_deterministic_and_payload_is_exact(style: OrderStyle) -> None:
    first = construct_broker_neutral_order_specification(**_sources(style))  # type: ignore[arg-type]
    second = construct_broker_neutral_order_specification(**_sources(style))  # type: ignore[arg-type]
    expected = {
        "schema_version": BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA,
        "instruction_fingerprint": first.instruction.fingerprint,
        "canonical_instrument_fingerprint": first.canonical_instrument.fingerprint,
        "order_style_choice_fingerprint": first.order_style_choice.fingerprint,
        "limit_price_choice_fingerprint": None
        if first.limit_price_choice is None
        else first.limit_price_choice.fingerprint,
        "time_in_force_choice_fingerprint": first.time_in_force_choice.fingerprint,
        "session_participation_choice_fingerprint": (
            first.session_participation_choice.fingerprint
        ),
    }
    assert first.fingerprint == second.fingerprint == canonical_fingerprint(expected)
    assert specification_module._fingerprint_payload(first._validate()) == expected


@pytest.mark.parametrize(
    "source_name",
    [
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "time_in_force_choice",
        "session_participation_choice",
    ],
)
def test_each_required_source_identity_is_fingerprint_significant(
    source_name: str,
) -> None:
    baseline = _construct()
    changed = _sources()
    if source_name == "instruction":
        object.__setattr__(changed[source_name], "fingerprint", "sha256:" + "1" * 64)
        with pytest.raises(ExecutionPlanningCorrespondenceError):
            construct_broker_neutral_order_specification(**changed)  # type: ignore[arg-type]
        return
    replacements = {
        "canonical_instrument": _canonical(currency="EUR"),
        "order_style_choice": OrderStyleChoice(OrderStyle.LIMIT),
        "time_in_force_choice": TimeInForceChoice(TimeInForce.GTC),
        "session_participation_choice": SessionParticipationChoice(
            SessionParticipation.REGULAR_AND_EXTENDED
        ),
    }
    changed[source_name] = replacements[source_name]
    if source_name in {"canonical_instrument", "order_style_choice"}:
        with pytest.raises(ExecutionPlanningValidationError):
            construct_broker_neutral_order_specification(**changed)  # type: ignore[arg-type]
    else:
        result = construct_broker_neutral_order_specification(**changed)  # type: ignore[arg-type]
        assert result.fingerprint != baseline.fingerprint


@pytest.mark.parametrize(
    "source_name",
    [
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "limit_price_choice",
        "time_in_force_choice",
        "session_participation_choice",
    ],
)
def test_value_equal_source_replacement_is_identity_rejected(source_name: str) -> None:
    result = construct_broker_neutral_order_specification(**_sources(OrderStyle.LIMIT))  # type: ignore[arg-type]
    replacement = _sources(OrderStyle.LIMIT)[source_name]
    object.__setattr__(result, source_name, replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError, match="binding"):
        result.to_dict()


@pytest.mark.parametrize(
    "slot",
    [
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "limit_price_choice",
        "time_in_force_choice",
        "session_participation_choice",
        "schema_version",
        "fingerprint",
    ],
)
def test_deleted_public_slots_are_correspondence_errors(slot: str) -> None:
    result = _construct()
    object.__delattr__(result, slot)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    ("slot", "replacement"),
    [
        ("schema_version", "wrong"),
        ("schema_version", _StringSubclass(BROKER_NEUTRAL_ORDER_SPECIFICATION_SCHEMA)),
        ("schema_version", _EqualitySpoof()),
        ("fingerprint", "sha256:" + "0" * 64),
        ("fingerprint", _StringSubclass("sha256:" + "0" * 64)),
        ("fingerprint", _EqualitySpoof()),
    ],
)
def test_top_level_identity_strings_are_hardened(
    slot: str, replacement: object
) -> None:
    result = _construct()
    object.__setattr__(result, slot, replacement)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    "attack",
    [
        "delete_token",
        "replace_token",
        "delete_state",
        "copy_state",
        "delete_binding",
        "malformed_binding",
    ],
)
def test_token_state_and_binding_attacks_are_rejected(attack: str) -> None:
    result = _construct()
    if attack == "delete_token":
        object.__delattr__(result, "_token")
    elif attack == "replace_token":
        object.__setattr__(result, "_token", object())
    elif attack == "delete_state":
        object.__delattr__(result, "_constructor_state")
    elif attack == "copy_state":
        object.__setattr__(
            result, "_constructor_state", tuple(list(result._constructor_state))
        )
    elif attack == "delete_binding":
        object.__delattr__(result, "_constructor_binding")
    else:
        object.__setattr__(result, "_constructor_binding", (_EqualitySpoof(),))
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_coherent_source_state_binding_and_fingerprint_rebase_is_rejected() -> None:
    result = _construct()
    replacement = OrderStyleChoice(OrderStyle.MARKET)
    object.__setattr__(result, "order_style_choice", replacement)
    sources = {
        "instruction": result.instruction,
        "canonical_instrument": result.canonical_instrument,
        "order_style_choice": result.order_style_choice,
        "limit_price_choice": result.limit_price_choice,
        "time_in_force_choice": result.time_in_force_choice,
        "session_participation_choice": result.session_participation_choice,
    }
    state = specification_module._constructor_state(sources)
    binding = (
        state,
        result.instruction,
        result.canonical_instrument,
        result.order_style_choice,
        result.limit_price_choice,
        result.time_in_force_choice,
        result.session_participation_choice,
    )
    object.__setattr__(result, "_constructor_state", state)
    object.__setattr__(result, "_constructor_binding", binding)
    object.__setattr__(
        result,
        "fingerprint",
        canonical_fingerprint(specification_module._fingerprint_payload(sources)),
    )

    with pytest.raises(ExecutionPlanningCorrespondenceError, match="attested"):
        result.to_dict()


def test_equal_but_distinct_state_and_binding_replacement_is_rejected() -> None:
    result = _construct()
    state = tuple(list(result._constructor_state))
    binding = (state, *result._constructor_binding[1:])
    assert state == result._constructor_state
    assert state is not result._constructor_state
    assert binding == result._constructor_binding
    assert binding is not result._constructor_binding
    object.__setattr__(result, "_constructor_state", state)
    object.__setattr__(result, "_constructor_binding", binding)

    with pytest.raises(ExecutionPlanningCorrespondenceError, match="attested"):
        result.to_dict()


def test_rebased_state_equality_spoofs_are_rejected_before_comparison() -> None:
    result = _construct()
    equality_calls: list[object] = []

    class _ExplodingEqualitySpoof:
        def __eq__(self, other: object) -> bool:
            equality_calls.append(other)
            raise AssertionError("constructor-state spoof equality was invoked")

    state_values = list(result._constructor_state)
    state_values[0] = _ExplodingEqualitySpoof()
    state = tuple(state_values)
    binding = (state, *result._constructor_binding[1:])
    object.__setattr__(result, "_constructor_state", state)
    object.__setattr__(result, "_constructor_binding", binding)

    with pytest.raises(ExecutionPlanningCorrespondenceError, match="attested"):
        result.to_dict()
    assert equality_calls == []


def test_mutated_attestation_contents_cannot_redefine_registered_origin() -> None:
    result = _construct()
    attestation = result._token
    replacement = OrderStyleChoice(OrderStyle.MARKET)
    object.__setattr__(result, "order_style_choice", replacement)
    sources = {
        "instruction": result.instruction,
        "canonical_instrument": result.canonical_instrument,
        "order_style_choice": result.order_style_choice,
        "limit_price_choice": result.limit_price_choice,
        "time_in_force_choice": result.time_in_force_choice,
        "session_participation_choice": result.session_participation_choice,
    }
    state = specification_module._constructor_state(sources)
    binding = (
        state,
        *result._constructor_binding[1:3],
        replacement,
        *result._constructor_binding[4:],
    )
    object.__setattr__(result, "_constructor_state", state)
    object.__setattr__(result, "_constructor_binding", binding)
    object.__setattr__(
        result,
        "fingerprint",
        canonical_fingerprint(specification_module._fingerprint_payload(sources)),
    )
    object.__setattr__(attestation, "_original_state", state)
    object.__setattr__(attestation, "_original_binding", binding)
    object.__setattr__(attestation, "_order_style_choice", replacement)

    with pytest.raises(ExecutionPlanningCorrespondenceError, match="original"):
        result.to_dict()


def test_exact_type_reconstructed_attestation_cannot_replace_registered_origin(
) -> None:
    result = _construct()
    attestation_type = type(result._token)
    reconstructed = object.__new__(attestation_type)
    for name, value in (
        ("_original_state", result._constructor_state),
        ("_original_binding", result._constructor_binding),
        ("_instruction", result.instruction),
        ("_canonical_instrument", result.canonical_instrument),
        ("_order_style_choice", result.order_style_choice),
        ("_limit_price_choice", result.limit_price_choice),
        ("_time_in_force_choice", result.time_in_force_choice),
        ("_session_participation_choice", result.session_participation_choice),
    ):
        object.__setattr__(reconstructed, name, value)
    object.__setattr__(result, "_token", reconstructed)

    with pytest.raises(ExecutionPlanningCorrespondenceError, match="not original"):
        result.to_dict()


def test_other_specification_attestation_cannot_replace_registered_origin() -> None:
    gc.collect()
    baseline_count = specification_module._registered_order_specification_origin_count()
    first = _construct()
    second = _construct()
    first_origin = specification_module._get_order_specification_origin(first)
    second_origin = specification_module._get_order_specification_origin(second)
    assert first_origin is not second_origin
    assert first_origin.owner_reference() is first
    assert second_origin.owner_reference() is second
    assert first_origin.attestation is first._token
    assert second_origin.attestation is second._token
    assert first_origin.owner_reference is not second_origin.owner_reference
    assert "origin" not in first.to_dict()
    assert "origin" not in specification_module._fingerprint_payload(first._validate())

    for name in (
        "instruction",
        "canonical_instrument",
        "order_style_choice",
        "limit_price_choice",
        "time_in_force_choice",
        "session_participation_choice",
        "fingerprint",
        "_constructor_state",
        "_constructor_binding",
        "_token",
    ):
        object.__setattr__(first, name, object.__getattribute__(second, name))
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        first.to_dict()

    first_reference = weakref.ref(first)
    del first
    del first_origin
    gc.collect()
    assert first_reference() is None
    assert specification_module._registered_order_specification_origin_count() == (
        baseline_count + 1
    )
    assert specification_module._get_order_specification_origin(second) is second_origin
    del second
    del second_origin
    gc.collect()
    assert specification_module._registered_order_specification_origin_count() == (
        baseline_count
    )


@pytest.mark.parametrize(
    "attack",
    ["instruction", "instrument", "style", "price", "tif", "session", "market_price"],
)
def test_nested_source_mutation_is_rejected(attack: str) -> None:
    result = construct_broker_neutral_order_specification(**_sources(OrderStyle.LIMIT))  # type: ignore[arg-type]
    if attack == "instruction":
        object.__setattr__(result.instruction, "fingerprint", "sha256:" + "1" * 64)
    elif attack == "instrument":
        object.__setattr__(
            result.canonical_instrument.trading_identity, "symbol", "MSFT"
        )
    elif attack == "style":
        object.__setattr__(result.order_style_choice, "style", OrderStyle.MARKET)
    elif attack == "price":
        assert result.limit_price_choice is not None
        object.__setattr__(result.limit_price_choice, "trading_currency", "EUR")
    elif attack == "tif":
        object.__setattr__(
            result.time_in_force_choice, "time_in_force", TimeInForce.GTC
        )
    elif attack == "session":
        object.__setattr__(
            result.session_participation_choice,
            "session_participation",
            SessionParticipation.REGULAR_AND_EXTENDED,
        )
    else:
        object.__setattr__(result.order_style_choice, "style", OrderStyle.MARKET)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize("value", [None, _translation()])
def test_no_action_or_translation_cannot_be_a_specification_instruction(
    value: object,
) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _construct(instruction=value)


@pytest.mark.parametrize("name", ["created_at", "authorization", "broker_request"])
def test_scope_excludes_time_authority_capability_and_broker_state(name: str) -> None:
    result = _construct()
    assert not hasattr(result, name)
    assert name not in result.to_dict()
    assert not hasattr(specification_module, name)
