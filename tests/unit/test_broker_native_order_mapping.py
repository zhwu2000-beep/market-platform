"""Focused tests for v0.68 broker-native order mapping."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_NATIVE_ORDER_MAPPING_SCHEMA,
    BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA,
    BrokerNativeOrderMapper,
    BrokerNativeOrderMapping,
    BrokerNativeOrderRepresentation,
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
    construct_broker_execution_capability_profile,
    construct_broker_native_order_representation,
    construct_broker_neutral_order_specification,
    derive_broker_neutral_execution_instruction,
    evaluate_broker_execution_structural_compatibility,
    map_broker_native_order,
    translate_position_target,
)
from market_platform.execution_planning import native_order_mapping as mapping_module
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
POLICY_FINGERPRINT = canonical_fingerprint({"schema_version": "test_mapping_policy/v1"})


class _StringSubclass(str):
    pass


class _EqualitySpoof:
    comparison_attempted = False

    def __eq__(self, other: object) -> bool:
        self.comparison_attempted = True
        raise AssertionError("equality must not run before exact-type validation")

    def __hash__(self) -> int:
        self.comparison_attempted = True
        raise AssertionError("hashing must not run before exact-type validation")


class _Mapper:
    def __init__(self, **overrides: object) -> None:
        self.values: dict[str, object] = {
            "execution_target_id": "broker.paper",
            "mapper_id": "mapper.test",
            "mapper_version": "1.0.0",
            "mapping_policy_fingerprint": POLICY_FINGERPRINT,
            "instrument_namespace": "vendor",
        }
        self.values.update(overrides)
        self.accesses = {name: 0 for name in self.values}
        self.map_calls = 0
        self.received_identity: ExternalInstrumentIdentity | None = None
        self.output_overrides: dict[str, object] = {}
        self.raise_on_second_read = False
        self.mapping_error: BaseException | None = None

    def _metadata(self, name: str) -> object:
        self.accesses[name] += 1
        if self.raise_on_second_read and self.accesses[name] > 1:
            raise AssertionError(f"{name} was read more than once")
        return self.values[name]

    @property
    def execution_target_id(self) -> str:
        return self._metadata("execution_target_id")  # type: ignore[return-value]

    @property
    def mapper_id(self) -> str:
        return self._metadata("mapper_id")  # type: ignore[return-value]

    @property
    def mapper_version(self) -> str:
        return self._metadata("mapper_version")  # type: ignore[return-value]

    @property
    def mapping_policy_fingerprint(self) -> str:
        return self._metadata("mapping_policy_fingerprint")  # type: ignore[return-value]

    @property
    def instrument_namespace(self) -> str:
        return self._metadata("instrument_namespace")  # type: ignore[return-value]

    def map_order(
        self,
        *,
        specification: execution_planning.BrokerNeutralOrderSpecification,
        external_instrument_identity: ExternalInstrumentIdentity,
    ) -> BrokerNativeOrderRepresentation:
        self.map_calls += 1
        self.received_identity = external_instrument_identity
        if self.mapping_error is not None:
            raise self.mapping_error
        price_choice = specification.limit_price_choice
        values: dict[str, object] = {
            "external_instrument_identity": external_instrument_identity,
            "side_token": "acquire.native",
            "quantity": specification.instruction.quantity,
            "order_type_token": "immediate.native",
            "limit_price": None if price_choice is None else price_choice.limit_price,
            "limit_price_currency": (
                None if price_choice is None else price_choice.trading_currency
            ),
            "time_in_force_token": "policy.native",
            "session_participation_token": "session.native",
        }
        values.update(self.output_overrides)
        return construct_broker_native_order_representation(**values)  # type: ignore[arg-type]


class _IncompleteMapper:
    pass


class _RepresentationSubclass(BrokerNativeOrderRepresentation):
    pass


class _SpecificationSubclass(execution_planning.BrokerNeutralOrderSpecification):
    pass


class _ProfileSubclass(execution_planning.BrokerExecutionCapabilityProfile):
    pass


class _CompatibilitySubclass(
    execution_planning.BrokerExecutionStructuralCompatibilityResult
):
    pass


class _InstrumentMappingSubclass(InstrumentMapping):
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


def _canonical() -> CanonicalInstrument:
    return CanonicalInstrument(
        CanonicalInstrumentId("instrument.AAPL"),
        TradingInstrumentIdentity("AAPL", "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )


def _resolution(canonical: CanonicalInstrument) -> InstrumentResolution:
    external = ExternalInstrumentIdentity("vendor", "AAPL", "XNAS")
    relation = InstrumentMapping(
        external,
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        BASE - timedelta(days=1),
        None,
    )
    return resolve_instrument_mapping(external, [relation], BASE)


def _intent(canonical: CanonicalInstrument) -> OrderIntent:
    signal = TradingSignal(
        TradingSignalSourceIdentity("strategy", "1"),
        "event",
        canonical.trading_identity,
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


def _translation(canonical: CanonicalInstrument) -> PositionTargetTranslation:
    account = TradingAccountIdentity(
        "broker", "account-1", TradingEnvironment.PAPER, canonical.trading_currency
    )
    source = StateSnapshotSourceIdentity("snapshot", "1")
    context = RiskEvaluationContext(
        _intent(canonical),
        _resolution(canonical),
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
            [PositionRecord(canonical.instrument_id, Decimal("4"))],
        ),
        OpenOrderExposureSnapshot(account, source, BASE - timedelta(seconds=8), []),
        MarketQuoteCollectionSnapshot(
            source,
            BASE - timedelta(seconds=7),
            [MarketQuote(canonical.instrument_id, last=Decimal("190"))],
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


def _sources(*, style: OrderStyle = OrderStyle.MARKET) -> tuple[object, ...]:
    canonical = _canonical()
    instruction = derive_broker_neutral_execution_instruction(_translation(canonical))
    assert instruction is not None
    specification = construct_broker_neutral_order_specification(
        instruction=instruction,
        canonical_instrument=canonical,
        order_style_choice=OrderStyleChoice(style),
        limit_price_choice=None
        if style is OrderStyle.MARKET
        else LimitPriceChoice(Decimal("190.00"), "USD"),
        time_in_force_choice=TimeInForceChoice(TimeInForce.DAY),
        session_participation_choice=SessionParticipationChoice(
            SessionParticipation.REGULAR_ONLY
        ),
    )
    profile = construct_broker_execution_capability_profile(
        execution_target_id="broker.paper",
        supported_asset_classes=(InstrumentAssetClass.EQUITY,),
        supported_trading_currencies=("USD",),
        supported_venues=("NASDAQ",),
        supported_order_combinations=(
            (style, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),
        ),
    )
    compatibility = evaluate_broker_execution_structural_compatibility(
        specification=specification, capability_profile=profile
    )
    relation = InstrumentMapping(
        ExternalInstrumentIdentity("vendor", "AAPL", "XNAS"),
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        instruction.plan_as_of - timedelta(days=1),
        None,
    )
    return specification, profile, compatibility, relation


def _map(
    *,
    mapper: _Mapper | None = None,
    style: OrderStyle = OrderStyle.MARKET,
    sources: tuple[object, ...] | None = None,
) -> tuple[BrokerNativeOrderMapping, _Mapper, tuple[object, ...]]:
    actual_sources = sources or _sources(style=style)
    actual_mapper = mapper or _Mapper()
    result = map_broker_native_order(
        specification=actual_sources[0],
        capability_profile=actual_sources[1],
        compatibility_result=actual_sources[2],
        instrument_mapping=actual_sources[3],
        mapper=actual_mapper,
    )  # type: ignore[arg-type]
    return result, actual_mapper, actual_sources


def _rewrite(target: object, name: str, value: object) -> None:
    object.__setattr__(target, name, value)


def test_exact_public_api_and_schemas() -> None:
    additions = [
        "BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA",
        "BrokerNativeOrderRepresentation",
        "construct_broker_native_order_representation",
        "BROKER_NATIVE_ORDER_MAPPING_SCHEMA",
        "BrokerNativeOrderMapping",
        "BrokerNativeOrderMapper",
        "map_broker_native_order",
    ]
    assert execution_planning.__all__[-7:] == additions
    assert len(execution_planning.__all__) == 41
    assert (
        BROKER_NATIVE_ORDER_REPRESENTATION_SCHEMA
        == "broker_native_order_representation/v1"
    )
    assert BROKER_NATIVE_ORDER_MAPPING_SCHEMA == "broker_native_order_mapping/v1"


def test_exact_fields_and_signatures() -> None:
    assert [field.name for field in fields(BrokerNativeOrderRepresentation)] == [
        "external_instrument_identity",
        "side_token",
        "quantity",
        "order_type_token",
        "limit_price",
        "limit_price_currency",
        "time_in_force_token",
        "session_participation_token",
        "schema_version",
        "fingerprint",
    ]
    assert [field.name for field in fields(BrokerNativeOrderMapping)] == [
        "execution_target_id",
        "mapper_id",
        "mapper_version",
        "mapping_policy_fingerprint",
        "instrument_namespace",
        "order_specification_fingerprint",
        "capability_profile_fingerprint",
        "structural_compatibility_result_fingerprint",
        "instrument_mapping_fingerprint",
        "native_order",
        "schema_version",
        "fingerprint",
    ]
    expected = (
        (
            construct_broker_native_order_representation,
            [
                "external_instrument_identity",
                "side_token",
                "quantity",
                "order_type_token",
                "limit_price",
                "limit_price_currency",
                "time_in_force_token",
                "session_participation_token",
            ],
        ),
        (
            map_broker_native_order,
            [
                "specification",
                "capability_profile",
                "compatibility_result",
                "instrument_mapping",
                "mapper",
            ],
        ),
    )
    for function, names in expected:
        signature = inspect.signature(function)
        assert list(signature.parameters) == names
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            and parameter.default is inspect.Parameter.empty
            for parameter in signature.parameters.values()
        )


def test_factory_ownership_and_no_extra_surface() -> None:
    with pytest.raises(TypeError):
        BrokerNativeOrderRepresentation()
    with pytest.raises(TypeError):
        BrokerNativeOrderMapping()
    assert not hasattr(execution_planning, "construct_broker_native_order_mapping")
    assert not hasattr(execution_planning, "BrokerNativeOrderMappingRequest")


def test_runtime_protocol_shape_and_mapper_version() -> None:
    assert isinstance(_Mapper(), BrokerNativeOrderMapper)
    assert not isinstance(_IncompleteMapper(), BrokerNativeOrderMapper)
    assert isinstance(BrokerNativeOrderMapper.mapper_version, property)


def test_metadata_is_snapshotted_once_and_map_order_invoked_once() -> None:
    mapper = _Mapper()
    mapper.raise_on_second_read = True
    result, mapper, _ = _map(mapper=mapper)
    assert mapper.accesses == {name: 1 for name in mapper.values}
    assert mapper.map_calls == 1
    assert result.mapper_version == "1.0.0"


def test_mapper_operation_is_bound_and_invoked_exactly_once() -> None:
    class BindingCountingMapper(_Mapper):
        def __init__(self) -> None:
            super().__init__()
            self.map_order_accesses = 0

        def __getattribute__(self, name: str) -> object:
            if name == "map_order":
                accesses = object.__getattribute__(self, "map_order_accesses") + 1
                object.__setattr__(self, "map_order_accesses", accesses)
                if accesses > 1:
                    raise AssertionError("map_order was read more than once")
            return super().__getattribute__(name)

    mapper = BindingCountingMapper()
    mapper.raise_on_second_read = True
    _map(mapper=mapper)
    assert mapper.accesses == {name: 1 for name in mapper.values}
    assert mapper.map_order_accesses == 1
    assert mapper.map_calls == 1


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("execution_target_id", "!target"),
        ("mapper_id", "!mapper"),
        ("mapper_version", ""),
        ("mapper_version", "x" * 65),
        ("mapper_version", "has space"),
        ("mapper_version", "é"),
        ("mapping_policy_fingerprint", "sha256:BAD"),
        ("instrument_namespace", "Vendor"),
        ("instrument_namespace", "vendor/name"),
    ],
)
def test_mapper_metadata_grammar(name: str, value: object) -> None:
    mapper = _Mapper(**{name: value})
    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=mapper)
    assert mapper.map_calls == 0


@pytest.mark.parametrize(
    "name",
    [
        "execution_target_id",
        "mapper_id",
        "mapper_version",
        "mapping_policy_fingerprint",
        "instrument_namespace",
    ],
)
def test_mapper_metadata_string_subclasses_are_rejected(name: str) -> None:
    mapper = _Mapper(**{name: _StringSubclass(str(_Mapper().values[name]))})
    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=mapper)


def test_protocol_shape_does_not_replace_metadata_validation() -> None:
    mapper = _Mapper(mapper_version=1)
    assert isinstance(mapper, BrokerNativeOrderMapper)
    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=mapper)


def test_mapper_property_and_operation_exceptions_propagate() -> None:
    class RaisingMapper(_Mapper):
        @property
        def mapper_id(self) -> str:
            raise RuntimeError("metadata boom")

    with pytest.raises(RuntimeError, match="metadata boom"):
        _map(mapper=RaisingMapper())
    mapper = _Mapper()
    mapper.mapping_error = AssertionError("mapping boom")
    with pytest.raises(AssertionError, match="mapping boom"):
        _map(mapper=mapper)


@pytest.mark.parametrize(
    "token",
    [
        "B",
        "buy.target",
        "LMT",
        "DAY",
        "extended?yes",
        "!" * 128,
    ],
)
def test_opaque_tokens_accept_shape_without_semantic_assumptions(token: str) -> None:
    mapper = _Mapper()
    mapper.output_overrides = {
        "side_token": token,
        "order_type_token": token,
        "time_in_force_token": token,
        "session_participation_token": token,
    }
    result, _, _ = _map(mapper=mapper)
    assert result.native_order.side_token == token


@pytest.mark.parametrize("token", ["", "x" * 129, "has space", "tab\t", "é"])
def test_opaque_token_grammar_rejects_invalid_shape(token: str) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        construct_broker_native_order_representation(
            external_instrument_identity=ExternalInstrumentIdentity(
                "vendor", "AAPL", "XNAS"
            ),
            side_token=token,
            quantity=Decimal("1"),
            order_type_token="type",
            limit_price=None,
            limit_price_currency=None,
            time_in_force_token="tif",
            session_participation_token="session",
        )


def test_opaque_tokens_are_not_semantically_reinterpreted() -> None:
    mapper = _Mapper()
    mapper.output_overrides = {
        "side_token": "opposite-looking",
        "order_type_token": "limit-looking",
        "time_in_force_token": "unknown-policy",
        "session_participation_token": "closed-looking",
    }
    result, _, _ = _map(mapper=mapper)
    assert result.native_order.order_type_token == "limit-looking"


@pytest.mark.parametrize("quantity", [Decimal("1"), Decimal("1.0"), Decimal("1.00")])
def test_quantity_scale_is_nonsemantic(quantity: Decimal) -> None:
    result = construct_broker_native_order_representation(
        external_instrument_identity=ExternalInstrumentIdentity(
            "vendor", "AAPL", "XNAS"
        ),
        side_token="side",
        quantity=quantity,
        order_type_token="type",
        limit_price=None,
        limit_price_currency=None,
        time_in_force_token="tif",
        session_participation_token="session",
    )
    assert result.quantity.as_tuple() == Decimal("1").as_tuple()
    assert result.to_dict()["quantity"] == "1"


@pytest.mark.parametrize(
    "quantity",
    [
        Decimal("0"),
        Decimal("-0"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-1"),
        1,
        1.0,
    ],
)
def test_invalid_native_quantities_are_rejected(quantity: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        construct_broker_native_order_representation(
            external_instrument_identity=ExternalInstrumentIdentity(
                "vendor", "AAPL", "XNAS"
            ),
            side_token="side",
            quantity=quantity,
            order_type_token="type",  # type: ignore[arg-type]
            limit_price=None,
            limit_price_currency=None,
            time_in_force_token="tif",
            session_participation_token="session",
        )


def test_noncanonical_retained_decimal_fails_after_refingerprinting() -> None:
    result, _, _ = _map()
    native = result.native_order
    refingerprinted = canonical_fingerprint(native._fingerprint_payload())
    _rewrite(native, "quantity", Decimal("6.0"))
    _rewrite(native, "fingerprint", refingerprinted)
    with pytest.raises(
        ExecutionPlanningCorrespondenceError, match="already be canonical"
    ):
        native._validate()


def test_market_and_limit_price_correspondence() -> None:
    market, _, _ = _map()
    assert market.native_order.limit_price is None
    assert market.native_order.limit_price_currency is None
    limit, _, _ = _map(style=OrderStyle.LIMIT)
    assert limit.native_order.limit_price == Decimal("190")
    assert limit.native_order.limit_price_currency == "USD"


@pytest.mark.parametrize(
    "overrides",
    [
        {"limit_price": Decimal("1"), "limit_price_currency": "USD"},
        {"limit_price": None, "limit_price_currency": "USD"},
    ],
)
def test_market_native_price_is_rejected(overrides: dict[str, object]) -> None:
    mapper = _Mapper()
    mapper.output_overrides = overrides
    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=mapper)


@pytest.mark.parametrize(
    "overrides",
    [
        {"limit_price": None, "limit_price_currency": None},
        {"limit_price": Decimal("191"), "limit_price_currency": "USD"},
        {"limit_price": Decimal("190"), "limit_price_currency": "EUR"},
    ],
)
def test_limit_native_price_and_currency_must_correspond(
    overrides: dict[str, object],
) -> None:
    mapper = _Mapper()
    mapper.output_overrides = overrides
    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=mapper, style=OrderStyle.LIMIT)


def test_instrument_mapping_reverse_use_reconstructs_identity_without_search() -> None:
    result, mapper, sources = _map()
    relation = sources[3]
    assert isinstance(relation, InstrumentMapping)
    assert mapper.received_identity is not relation.external_identity
    assert mapper.received_identity is not None
    assert mapper.received_identity.to_dict() == relation.external_identity.to_dict()
    assert result.instrument_mapping_fingerprint == relation.fingerprint


def test_mapping_half_open_validity_boundaries() -> None:
    specification, profile, compatibility, _ = _sources()
    plan = specification.instruction.plan_as_of
    cases = (
        (plan, plan + timedelta(seconds=1), True),
        (plan - timedelta(seconds=1), plan + timedelta(microseconds=1), True),
        (plan - timedelta(seconds=1), plan, False),
        (plan + timedelta(microseconds=1), None, False),
        (plan - timedelta(seconds=1), None, True),
    )
    for valid_from, expires_at, accepted in cases:
        relation = InstrumentMapping(
            ExternalInstrumentIdentity("vendor", "AAPL", "XNAS"),
            specification.canonical_instrument,
            InstrumentMappingSourceIdentity("mapping", "1"),
            valid_from,
            expires_at,
        )
        arguments = dict(
            specification=specification,
            capability_profile=profile,
            compatibility_result=compatibility,
            instrument_mapping=relation,
            mapper=_Mapper(),
        )
        if accepted:
            map_broker_native_order(**arguments)
        else:
            with pytest.raises(ExecutionPlanningValidationError, match="inactive"):
                map_broker_native_order(**arguments)


def test_wrong_canonical_instrument_and_namespace_are_rejected() -> None:
    specification, profile, compatibility, relation = _sources()
    wrong_canonical = CanonicalInstrument(
        CanonicalInstrumentId("instrument.MSFT"),
        TradingInstrumentIdentity("MSFT", "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )
    wrong_relation = InstrumentMapping(
        relation.external_identity,
        wrong_canonical,
        relation.source,
        relation.valid_from,
        relation.expires_at,
    )
    with pytest.raises(ExecutionPlanningValidationError, match="instrument"):
        map_broker_native_order(
            specification=specification,
            capability_profile=profile,
            compatibility_result=compatibility,
            instrument_mapping=wrong_relation,
            mapper=_Mapper(),
        )
    mapper = _Mapper(instrument_namespace="other")
    with pytest.raises(ExecutionPlanningValidationError, match="namespace"):
        map_broker_native_order(
            specification=specification,
            capability_profile=profile,
            compatibility_result=compatibility,
            instrument_mapping=relation,
            mapper=mapper,
        )
    assert mapper.map_calls == 0


def test_incompatible_result_is_rejected_before_mapper_access() -> None:
    specification, _, _, relation = _sources()
    profile = construct_broker_execution_capability_profile(
        execution_target_id="broker.paper",
        supported_asset_classes=(InstrumentAssetClass.ETF,),
        supported_trading_currencies=("USD",),
        supported_venues=("NASDAQ",),
        supported_order_combinations=(
            (OrderStyle.MARKET, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),
        ),
    )
    compatibility = evaluate_broker_execution_structural_compatibility(
        specification=specification, capability_profile=profile
    )
    mapper = _Mapper()
    with pytest.raises(ExecutionPlanningValidationError, match="compatible"):
        map_broker_native_order(
            specification=specification,
            capability_profile=profile,
            compatibility_result=compatibility,
            instrument_mapping=relation,
            mapper=mapper,
        )
    assert mapper.accesses == {name: 0 for name in mapper.values}
    assert mapper.map_calls == 0


def test_cross_source_fingerprint_mismatch_precedes_mapper_call() -> None:
    specification, profile, compatibility, relation = _sources()
    _rewrite(
        compatibility,
        "order_specification_fingerprint",
        POLICY_FINGERPRINT,
    )
    _rewrite(
        compatibility,
        "fingerprint",
        canonical_fingerprint(compatibility._fingerprint_payload()),
    )
    mapper = _Mapper()
    with pytest.raises(ExecutionPlanningValidationError, match="specification"):
        map_broker_native_order(
            specification=specification,
            capability_profile=profile,
            compatibility_result=compatibility,
            instrument_mapping=relation,
            mapper=mapper,
        )
    assert mapper.map_calls == 0


@pytest.mark.parametrize("source_index", range(4))
def test_wrong_source_runtime_types_are_rejected(source_index: int) -> None:
    sources = list(_sources())
    sources[source_index] = object()
    mapper = _Mapper()
    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=mapper, sources=tuple(sources))
    assert mapper.map_calls == 0


@pytest.mark.parametrize(
    ("source_index", "source_type"),
    [
        (0, _SpecificationSubclass),
        (1, _ProfileSubclass),
        (2, _CompatibilitySubclass),
        (3, _InstrumentMappingSubclass),
    ],
)
def test_source_subclasses_are_rejected(
    source_index: int,
    source_type: type[object],
) -> None:
    sources = list(_sources())
    sources[source_index] = object.__new__(source_type)
    mapper = _Mapper()
    with pytest.raises(ExecutionPlanningValidationError, match="exact runtime type"):
        _map(mapper=mapper, sources=tuple(sources))
    assert mapper.map_calls == 0


def test_mapper_output_must_be_exact_runtime_type() -> None:
    class BadMapper(_Mapper):
        def map_order(self, **kwargs: object) -> BrokerNativeOrderRepresentation:
            native = super().map_order(**kwargs)  # type: ignore[arg-type]
            subclass = object.__new__(_RepresentationSubclass)
            for retained_field in fields(BrokerNativeOrderRepresentation):
                _rewrite(
                    subclass, retained_field.name, getattr(native, retained_field.name)
                )
            return subclass

    with pytest.raises(ExecutionPlanningValidationError):
        _map(mapper=BadMapper())


def test_corrupted_exact_mapper_output_is_validation_error() -> None:
    class CorruptedOutputMapper(_Mapper):
        def __init__(self) -> None:
            super().__init__()
            self.corrupted_output: BrokerNativeOrderRepresentation | None = None

        def map_order(self, **kwargs: object) -> BrokerNativeOrderRepresentation:
            native = super().map_order(**kwargs)  # type: ignore[arg-type]
            canonical_value_fingerprint = canonical_fingerprint(
                native._fingerprint_payload()
            )
            _rewrite(native, "quantity", Decimal("6.0"))
            _rewrite(native, "fingerprint", canonical_value_fingerprint)
            self.corrupted_output = native
            return native

    mapper = CorruptedOutputMapper()
    with pytest.raises(ExecutionPlanningValidationError, match="malformed native"):
        _map(mapper=mapper)
    assert type(mapper.corrupted_output) is BrokerNativeOrderRepresentation
    with pytest.raises(
        ExecutionPlanningCorrespondenceError, match="already be canonical"
    ):
        mapper.corrupted_output._validate()


def test_native_external_identity_and_quantity_must_correspond() -> None:
    mapper = _Mapper()
    mapper.output_overrides = {
        "external_instrument_identity": ExternalInstrumentIdentity(
            "vendor", "MSFT", "XNAS"
        )
    }
    with pytest.raises(ExecutionPlanningValidationError, match="external identity"):
        _map(mapper=mapper)
    mapper = _Mapper()
    mapper.output_overrides = {"quantity": Decimal("7")}
    with pytest.raises(ExecutionPlanningValidationError, match="quantity"):
        _map(mapper=mapper)


def test_projection_key_order_fingerprint_and_json_safety() -> None:
    result, _, _ = _map()
    assert list(result.native_order.to_dict()) == [
        "schema_version",
        "external_instrument_identity",
        "side_token",
        "quantity",
        "order_type_token",
        "limit_price",
        "limit_price_currency",
        "time_in_force_token",
        "session_participation_token",
        "fingerprint",
    ]
    assert list(result.to_dict()) == [
        "schema_version",
        "execution_target_id",
        "mapper_id",
        "mapper_version",
        "mapping_policy_fingerprint",
        "instrument_namespace",
        "order_specification_fingerprint",
        "capability_profile_fingerprint",
        "structural_compatibility_result_fingerprint",
        "instrument_mapping_fingerprint",
        "native_order",
        "fingerprint",
    ]
    assert result.fingerprint == canonical_fingerprint(result._fingerprint_payload())
    json.dumps(result.to_dict(), allow_nan=False)


def test_parent_child_namespace_invariant_survives_refingerprinting() -> None:
    result, _, _ = _map()
    _rewrite(result, "instrument_namespace", "other")
    _rewrite(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError, match="namespace"):
        result._validate()


def test_nested_namespace_rewrite_survives_complete_refingerprinting() -> None:
    result, _, _ = _map()
    native = result.native_order
    _rewrite(
        native,
        "external_instrument_identity",
        ExternalInstrumentIdentity("other", "AAPL", "XNAS"),
    )
    _rewrite(
        native, "fingerprint", canonical_fingerprint(native._fingerprint_payload())
    )
    _rewrite(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError, match="namespace"):
        result._validate()


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("native", "schema_version", "wrong/v1"),
        ("native", "side_token", _StringSubclass("side")),
        ("mapping", "schema_version", "wrong/v1"),
        ("mapping", "mapper_id", _StringSubclass("mapper.test")),
        ("mapping", "mapping_policy_fingerprint", "sha256:BAD"),
    ],
)
def test_retained_corruption_is_rejected(
    target: str, field: str, value: object
) -> None:
    result, _, _ = _map()
    artifact = result.native_order if target == "native" else result
    _rewrite(artifact, field, value)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        artifact._validate()


@pytest.mark.parametrize(
    "field",
    [
        "order_specification_fingerprint",
        "capability_profile_fingerprint",
        "structural_compatibility_result_fingerprint",
        "instrument_mapping_fingerprint",
    ],
)
def test_mapping_provenance_fingerprints_require_exact_grammar(field: str) -> None:
    result, _, _ = _map()
    _rewrite(result, field, "sha256:BAD")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result._validate()


def test_deleted_slots_and_stale_fingerprints_are_rejected() -> None:
    result, _, _ = _map()
    object.__delattr__(result.native_order, "side_token")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.native_order._validate()
    result, _, _ = _map()
    object.__delattr__(result, "native_order")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result._validate()
    result, _, _ = _map()
    _rewrite(result, "fingerprint", POLICY_FINGERPRINT)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result._validate()


def test_equality_spoof_is_rejected_before_comparison() -> None:
    spoof = _EqualitySpoof()
    result, _, _ = _map()
    _rewrite(result, "mapper_id", spoof)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result._validate()
    assert not spoof.comparison_attempted


def test_mapping_is_self_contained_and_does_not_retain_upstream_sources() -> None:
    result, mapper, sources = _map()
    retained_values = [getattr(result, item.name) for item in fields(result)]
    assert mapper not in retained_values
    assert all(source not in retained_values for source in sources)
    assert not hasattr(result, "__weakref__")
    original_projection = result.to_dict()
    _rewrite(sources[3], "fingerprint", POLICY_FINGERPRINT)
    assert result.to_dict() == original_projection


def test_owned_nested_native_order_is_independently_revalidated() -> None:
    result, _, _ = _map()
    _rewrite(result.native_order, "fingerprint", POLICY_FINGERPRINT)
    with pytest.raises(ExecutionPlanningCorrespondenceError, match="native_order"):
        result._validate()


def test_no_registry_attestation_search_or_submission_surface() -> None:
    source = inspect.getsource(mapping_module)
    for forbidden in (
        "WeakKeyDictionary",
        "weakref",
        "attestation",
        "resolve_instrument_mapping",
        "submit_order",
        "account_id",
        "broker_sdk",
    ):
        assert forbidden not in source


def test_public_documentation_defines_opaque_non_authorizing_boundary() -> None:
    documentation = " ".join(
        part
        for part in (
            mapping_module.__doc__,
            BrokerNativeOrderMapper.__doc__,
            BrokerNativeOrderMapping.__doc__,
            map_broker_native_order.__doc__,
        )
        if part
    ).lower()
    assert "opaque" in documentation
    assert "mapper-conformance" in documentation
    assert "not authorization" in documentation
    assert "broker acceptance" in documentation


def test_mapper_target_must_match_capability_profile() -> None:
    mapper = _Mapper(execution_target_id="broker.other")
    with pytest.raises(ExecutionPlanningValidationError, match="target"):
        _map(mapper=mapper)
    assert mapper.map_calls == 0


def test_incomplete_protocol_object_is_rejected_after_domain_preconditions() -> None:
    specification, profile, compatibility, relation = _sources()
    with pytest.raises(
        ExecutionPlanningValidationError, match="BrokerNativeOrderMapper"
    ):
        map_broker_native_order(
            specification=specification,
            capability_profile=profile,
            compatibility_result=compatibility,
            instrument_mapping=relation,
            mapper=_IncompleteMapper(),  # type: ignore[arg-type]
        )


def test_representation_price_cardinality_is_independent_of_opaque_token() -> None:
    external = ExternalInstrumentIdentity("vendor", "AAPL", "XNAS")
    absent = construct_broker_native_order_representation(
        external_instrument_identity=external,
        side_token="side",
        quantity=Decimal("1"),
        order_type_token="anything",
        limit_price=None,
        limit_price_currency=None,
        time_in_force_token="tif",
        session_participation_token="session",
    )
    present = construct_broker_native_order_representation(
        external_instrument_identity=external,
        side_token="side",
        quantity=Decimal("1"),
        order_type_token="anything",
        limit_price=Decimal("10.00"),
        limit_price_currency="USD",
        time_in_force_token="tif",
        session_participation_token="session",
    )
    assert absent.limit_price is None
    assert present.limit_price == Decimal("10")


@pytest.mark.parametrize(
    ("price", "currency"),
    [
        (None, "USD"),
        (Decimal("1"), None),
        (Decimal("0"), "USD"),
        (Decimal("NaN"), "USD"),
        (Decimal("1"), "usd"),
    ],
)
def test_representation_rejects_invalid_price_cardinality_and_values(
    price: object,
    currency: object,
) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        construct_broker_native_order_representation(
            external_instrument_identity=ExternalInstrumentIdentity(
                "vendor", "AAPL", "XNAS"
            ),
            side_token="side",
            quantity=Decimal("1"),
            order_type_token="type",
            limit_price=price,
            limit_price_currency=currency,  # type: ignore[arg-type]
            time_in_force_token="tif",
            session_participation_token="session",
        )
