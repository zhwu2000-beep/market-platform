"""Focused tests for v0.67 broker execution capability profiles."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from enum import StrEnum

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA,
    BrokerExecutionCapabilityProfile,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    OrderStyle,
    SessionParticipation,
    TimeInForce,
    construct_broker_execution_capability_profile,
)
from market_platform.execution_planning import capability as capability_module
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    InstrumentAssetClass,
)
from market_platform.trading import TradingInstrumentIdentity


class _StringSubclass(str):
    pass


class _ForeignEnum(StrEnum):
    VALUE = "market"


class _EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        raise AssertionError("equality must not be used before exact-type validation")

    def __hash__(self) -> int:
        raise AssertionError("hash must not be used before exact-type validation")


MARKET_DAY_REGULAR = (
    OrderStyle.MARKET,
    TimeInForce.DAY,
    SessionParticipation.REGULAR_ONLY,
)


def _profile(**overrides: object) -> BrokerExecutionCapabilityProfile:
    values: dict[str, object] = {
        "execution_target_id": "broker.paper",
        "supported_asset_classes": (InstrumentAssetClass.EQUITY,),
        "supported_trading_currencies": ("USD",),
        "supported_venues": ("NASDAQ",),
        "supported_order_combinations": (MARKET_DAY_REGULAR,),
    }
    values.update(overrides)
    return construct_broker_execution_capability_profile(**values)  # type: ignore[arg-type]


def _canonical_accepts_currency(value: object) -> bool:
    try:
        CanonicalInstrument(
            CanonicalInstrumentId("instrument.TEST"),
            TradingInstrumentIdentity("TEST", "NASDAQ"),
            InstrumentAssetClass.EQUITY,
            value,  # type: ignore[arg-type]
        )
    except TypeError, ValueError:
        return False
    return True


def _canonical_retains_venue_exactly(value: object) -> bool:
    try:
        identity = TradingInstrumentIdentity("TEST", value)  # type: ignore[arg-type]
        canonical = CanonicalInstrument(
            CanonicalInstrumentId("instrument.TEST"),
            identity,
            InstrumentAssetClass.EQUITY,
            "USD",
        )
    except TypeError, ValueError:
        return False
    return type(value) is str and canonical.trading_identity.venue == value


def test_exact_profile_public_api_additions_exist() -> None:
    assert execution_planning.BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA is (
        BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA
    )
    assert execution_planning.BrokerExecutionCapabilityProfile is (
        BrokerExecutionCapabilityProfile
    )
    assert execution_planning.construct_broker_execution_capability_profile is (
        construct_broker_execution_capability_profile
    )


def test_schema_is_exact() -> None:
    assert (
        BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA
        == "broker_execution_capability_profile/v1"
    )


def test_factory_signature_is_exact_and_keyword_only() -> None:
    signature = inspect.signature(construct_broker_execution_capability_profile)
    assert list(signature.parameters) == [
        "execution_target_id",
        "supported_asset_classes",
        "supported_trading_currencies",
        "supported_venues",
        "supported_order_combinations",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )


def test_direct_construction_is_rejected() -> None:
    with pytest.raises(TypeError):
        BrokerExecutionCapabilityProfile()


def test_valid_minimal_profile_and_exact_field_order() -> None:
    profile = _profile()
    assert [item.name for item in fields(profile)] == [
        "execution_target_id",
        "supported_asset_classes",
        "supported_trading_currencies",
        "supported_venues",
        "supported_order_combinations",
        "schema_version",
        "fingerprint",
    ]
    assert profile.schema_version == BROKER_EXECUTION_CAPABILITY_PROFILE_SCHEMA


def test_complete_v1_cartesian_profile_is_accepted() -> None:
    combinations = tuple(
        (style, tif, session)
        for style in (OrderStyle.MARKET, OrderStyle.LIMIT)
        for tif in (TimeInForce.DAY, TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK)
        for session in (
            SessionParticipation.REGULAR_ONLY,
            SessionParticipation.REGULAR_AND_EXTENDED,
        )
    )
    profile = _profile(
        supported_asset_classes=(InstrumentAssetClass.EQUITY, InstrumentAssetClass.ETF),
        supported_trading_currencies=("EUR", "USD"),
        supported_venues=("NASDAQ", "NYSE"),
        supported_order_combinations=combinations,
    )
    assert len(profile.supported_order_combinations) == 16


@pytest.mark.parametrize("value", ["A", "a" * 128, "0", "A._-z"])
def test_execution_target_boundaries_are_accepted(value: str) -> None:
    assert _profile(execution_target_id=value).execution_target_id == value


@pytest.mark.parametrize(
    "value",
    ["", "a" * 129, "-bad", "_bad", ".bad", "a/b", "a b", "?", 1, True],
)
def test_invalid_execution_target_values_are_rejected(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(execution_target_id=value)


def test_execution_target_string_subclass_is_rejected() -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(execution_target_id=_StringSubclass("broker"))


@pytest.mark.parametrize("value", [[], set(), frozenset(), iter(())])
def test_asset_collection_requires_exact_tuple(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_asset_classes=value)


@pytest.mark.parametrize(
    "value",
    [
        (),
        (InstrumentAssetClass.EQUITY, InstrumentAssetClass.EQUITY),
        (InstrumentAssetClass.ETF, InstrumentAssetClass.EQUITY),
        ("equity",),
        (_ForeignEnum.VALUE,),
        (_EqualitySpoof(),),
    ],
)
def test_invalid_asset_domains_are_rejected(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_asset_classes=value)


def test_asset_v1_rank_map_matches_current_enum_inventory() -> None:
    assert tuple(capability_module._ASSET_CLASS_RANK) == (
        InstrumentAssetClass.EQUITY,
        InstrumentAssetClass.ETF,
    )
    assert set(capability_module._ASSET_CLASS_RANK) == set(InstrumentAssetClass)
    assert set(capability_module._ASSET_CLASS_RANK.values()) == {0, 1}


@pytest.mark.parametrize("value", ["USD", "EUR", "JPY", "AAA", "ZZZ"])
def test_currency_rule_matches_canonical_instrument_for_accepted_values(
    value: str,
) -> None:
    assert _canonical_accepts_currency(value)
    assert _profile(
        supported_trading_currencies=(value,)
    ).supported_trading_currencies == (value,)


@pytest.mark.parametrize(
    "value", ["usd", "Usd", "US", "USDD", " U", " USD", "USD ", "?SD", "???", 1, True]
)
def test_currency_rule_matches_canonical_instrument_for_rejected_values(
    value: object,
) -> None:
    assert not _canonical_accepts_currency(value)
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_trading_currencies=(value,))


def test_currency_string_subclass_is_rejected_by_both_boundaries() -> None:
    value = _StringSubclass("USD")
    assert not _canonical_accepts_currency(value)
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_trading_currencies=(value,))


@pytest.mark.parametrize("value", [(), ["USD"], ("USD", "USD"), ("USD", "EUR")])
def test_invalid_currency_collections_are_rejected(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_trading_currencies=value)


@pytest.mark.parametrize("value", ["NASDAQ", "XNAS", "A:B", "\u03a3", "\x00"])
def test_venue_rule_matches_exact_canonical_retention_for_accepted_values(
    value: str,
) -> None:
    assert _canonical_retains_venue_exactly(value)
    assert _profile(supported_venues=(value,)).supported_venues == (value,)


@pytest.mark.parametrize(
    "value",
    ["", "nasdaq", " Nasdaq", "NASDAQ ", "NAS DAQ", "NAS\tDAQ", "\u00df", 1, True],
)
def test_venue_rule_matches_exact_canonical_retention_for_rejected_values(
    value: object,
) -> None:
    assert not _canonical_retains_venue_exactly(value)
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_venues=(value,))


def test_venue_string_subclass_rejected_despite_constructor_normalization() -> None:
    value = _StringSubclass("NASDAQ")
    assert not _canonical_retains_venue_exactly(value)
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_venues=(value,))


@pytest.mark.parametrize(
    "value", [(), ["NASDAQ"], ("NASDAQ", "NASDAQ"), ("NYSE", "NASDAQ")]
)
def test_invalid_venue_collections_are_rejected(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_venues=value)


@pytest.mark.parametrize("value", [(), [MARKET_DAY_REGULAR], set()])
def test_order_combination_collection_requires_nonempty_exact_tuple(
    value: object,
) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_order_combinations=value)


@pytest.mark.parametrize(
    "value",
    [
        ((OrderStyle.MARKET, TimeInForce.DAY),),
        (
            (
                OrderStyle.MARKET,
                TimeInForce.DAY,
                SessionParticipation.REGULAR_ONLY,
                None,
            ),
        ),
        ([OrderStyle.MARKET, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY],),
        (("market", TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),),
        ((OrderStyle.MARKET, "day", SessionParticipation.REGULAR_ONLY),),
        ((OrderStyle.MARKET, TimeInForce.DAY, "regular_only"),),
        ((_EqualitySpoof(), TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),),
    ],
)
def test_invalid_inner_order_combinations_are_rejected(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_order_combinations=value)


def test_duplicate_and_noncanonical_combinations_are_rejected() -> None:
    limit = (OrderStyle.LIMIT, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY)
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_order_combinations=(MARKET_DAY_REGULAR, MARKET_DAY_REGULAR))
    with pytest.raises(ExecutionPlanningValidationError):
        _profile(supported_order_combinations=(limit, MARKET_DAY_REGULAR))


def test_v1_combination_rank_maps_are_exhaustive_unique_and_contiguous() -> None:
    expected = (
        (capability_module._ORDER_STYLE_RANK, set(OrderStyle)),
        (capability_module._TIME_IN_FORCE_RANK, set(TimeInForce)),
        (capability_module._SESSION_PARTICIPATION_RANK, set(SessionParticipation)),
    )
    for ranks, members in expected:
        assert set(ranks) == members
        assert set(ranks.values()) == set(range(len(ranks)))
    assert capability_module._MAX_ORDER_COMBINATIONS == 16


def test_projection_key_order_shapes_and_json_safety_are_exact() -> None:
    projection = _profile().to_dict()
    assert list(projection) == [
        "schema_version",
        "execution_target_id",
        "supported_asset_classes",
        "supported_trading_currencies",
        "supported_venues",
        "supported_order_combinations",
        "fingerprint",
    ]
    assert projection["supported_asset_classes"] == ["equity"]
    assert projection["supported_trading_currencies"] == ["USD"]
    assert projection["supported_venues"] == ["NASDAQ"]
    combination = projection["supported_order_combinations"][0]  # type: ignore[index]
    assert list(combination) == [
        "order_style",
        "time_in_force",
        "session_participation",
    ]
    assert combination == {
        "order_style": "market",
        "time_in_force": "day",
        "session_participation": "regular_only",
    }
    json.dumps(projection)


def test_fingerprint_is_deterministic_and_matches_exact_payload() -> None:
    left = _profile()
    right = _profile()
    payload = left.to_dict().copy()
    payload.pop("fingerprint")
    assert left.to_dict() == right.to_dict()
    assert left.fingerprint == canonical_fingerprint(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("execution_target_id", " bad"),
        ("supported_asset_classes", ()),
        ("supported_trading_currencies", ("usd",)),
        ("supported_venues", ("nasdaq",)),
        ("supported_order_combinations", ()),
        ("schema_version", "wrong/v1"),
        ("fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_malformed_retained_state_is_rejected(field_name: str, value: object) -> None:
    profile = _profile()
    object.__setattr__(profile, field_name, value)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        profile.to_dict()


@pytest.mark.parametrize(
    "field_name", [item.name for item in fields(BrokerExecutionCapabilityProfile)]
)
def test_deleted_retained_slots_are_rejected(field_name: str) -> None:
    profile = _profile()
    object.__delattr__(profile, field_name)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        profile.to_dict()


def test_controlled_unrelated_runtime_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(payload: object) -> str:
        raise RuntimeError("controlled")

    monkeypatch.setattr(capability_module, "canonical_fingerprint", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        _profile()
