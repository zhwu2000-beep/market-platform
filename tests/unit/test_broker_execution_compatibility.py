"""Focused tests for v0.67 structural execution compatibility."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA,
    BrokerExecutionCapabilityProfile,
    BrokerExecutionStructuralCompatibilityOutcome,
    BrokerExecutionStructuralCompatibilityReason,
    BrokerExecutionStructuralCompatibilityResult,
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
    construct_broker_neutral_order_specification,
    derive_broker_neutral_execution_instruction,
    evaluate_broker_execution_structural_compatibility,
    translate_position_target,
)
from market_platform.execution_planning import compatibility as compatibility_module
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
R = BrokerExecutionStructuralCompatibilityReason


class _ForeignReason(StrEnum):
    VALUE = "unsupported_venue"


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


class _SpecificationSubclass(execution_planning.BrokerNeutralOrderSpecification):
    pass


class _ProfileSubclass(BrokerExecutionCapabilityProfile):
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
    asset_class: InstrumentAssetClass = InstrumentAssetClass.EQUITY,
    currency: str = "USD",
    venue: str = "NASDAQ",
) -> CanonicalInstrument:
    return CanonicalInstrument(
        CanonicalInstrumentId("instrument.AAPL"),
        TradingInstrumentIdentity("AAPL", venue),
        asset_class,
        currency,
    )


def _resolution(canonical: CanonicalInstrument) -> InstrumentResolution:
    external = ExternalInstrumentIdentity("vendor", "AAPL", "XNAS")
    mapping = InstrumentMapping(
        external,
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        BASE - timedelta(days=1),
        None,
    )
    return resolve_instrument_mapping(external, [mapping], BASE)


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
    resolution = _resolution(canonical)
    instrument_id = canonical.instrument_id
    context = RiskEvaluationContext(
        _intent(canonical),
        resolution,
        AccountCashSnapshot(
            account,
            source,
            BASE - timedelta(seconds=10),
            [CashBalance(canonical.trading_currency, Decimal("1000"))],
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


def _specification(
    *,
    style: OrderStyle = OrderStyle.MARKET,
    tif: TimeInForce = TimeInForce.DAY,
    session: SessionParticipation = SessionParticipation.REGULAR_ONLY,
    asset_class: InstrumentAssetClass = InstrumentAssetClass.EQUITY,
    currency: str = "USD",
    venue: str = "NASDAQ",
):
    canonical = _canonical(asset_class=asset_class, currency=currency, venue=venue)
    instruction = derive_broker_neutral_execution_instruction(_translation(canonical))
    assert instruction is not None
    return construct_broker_neutral_order_specification(
        instruction=instruction,
        canonical_instrument=canonical,
        order_style_choice=OrderStyleChoice(style),
        limit_price_choice=(
            None
            if style is OrderStyle.MARKET
            else LimitPriceChoice(Decimal("190"), currency)
        ),
        time_in_force_choice=TimeInForceChoice(tif),
        session_participation_choice=SessionParticipationChoice(session),
    )


def _profile(
    *,
    assets: tuple[InstrumentAssetClass, ...] = (InstrumentAssetClass.EQUITY,),
    currencies: tuple[str, ...] = ("USD",),
    venues: tuple[str, ...] = ("NASDAQ",),
    combinations: tuple[tuple[OrderStyle, TimeInForce, SessionParticipation], ...] = (
        (OrderStyle.MARKET, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),
    ),
) -> BrokerExecutionCapabilityProfile:
    return construct_broker_execution_capability_profile(
        execution_target_id="broker.paper",
        supported_asset_classes=assets,
        supported_trading_currencies=currencies,
        supported_venues=venues,
        supported_order_combinations=combinations,
    )


def _evaluate(
    **profile_overrides: object,
) -> BrokerExecutionStructuralCompatibilityResult:
    return evaluate_broker_execution_structural_compatibility(
        specification=_specification(),
        capability_profile=_profile(**profile_overrides),  # type: ignore[arg-type]
    )


def test_exact_compatibility_public_api_additions_exist() -> None:
    assert (
        execution_planning.BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA
        is (BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA)
    )
    assert execution_planning.BrokerExecutionStructuralCompatibilityOutcome is (
        BrokerExecutionStructuralCompatibilityOutcome
    )
    assert execution_planning.BrokerExecutionStructuralCompatibilityReason is (
        BrokerExecutionStructuralCompatibilityReason
    )
    assert execution_planning.BrokerExecutionStructuralCompatibilityResult is (
        BrokerExecutionStructuralCompatibilityResult
    )
    assert execution_planning.evaluate_broker_execution_structural_compatibility is (
        evaluate_broker_execution_structural_compatibility
    )


def test_schema_and_enum_values_are_exact_without_aliases() -> None:
    assert (
        BROKER_EXECUTION_STRUCTURAL_COMPATIBILITY_RESULT_SCHEMA
        == "broker_execution_structural_compatibility_result/v1"
    )
    assert [
        (item.name, item.value)
        for item in BrokerExecutionStructuralCompatibilityOutcome
    ] == [
        ("COMPATIBLE", "compatible"),
        ("INCOMPATIBLE", "incompatible"),
    ]
    assert [item.value for item in R] == [
        "unsupported_asset_class",
        "unsupported_trading_currency",
        "unsupported_venue",
        "unsupported_order_style",
        "unsupported_time_in_force",
        "unsupported_session_participation",
        "unsupported_order_combination",
    ]
    assert len(R.__members__) == 7


def test_reason_rank_is_exhaustive_unique_and_contiguous() -> None:
    assert tuple(compatibility_module._REASON_RANK) == tuple(R)
    assert set(compatibility_module._REASON_RANK.values()) == set(range(7))


def test_evaluator_signature_is_exact_keyword_only_and_required() -> None:
    signature = inspect.signature(evaluate_broker_execution_structural_compatibility)
    assert list(signature.parameters) == ["specification", "capability_profile"]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )


def test_result_direct_construction_is_rejected_and_field_order_is_exact() -> None:
    with pytest.raises(TypeError):
        BrokerExecutionStructuralCompatibilityResult()
    result = _evaluate()
    assert [item.name for item in fields(result)] == [
        "capability_profile_fingerprint",
        "order_specification_fingerprint",
        "outcome",
        "rejection_reasons",
        "schema_version",
        "fingerprint",
    ]


def test_compatible_market_result_has_exact_empty_tuple_and_list() -> None:
    result = _evaluate()
    assert result.outcome is BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE
    assert type(result.rejection_reasons) is tuple
    assert result.rejection_reasons == ()
    assert result.to_dict()["rejection_reasons"] == []


def test_compatible_limit_result() -> None:
    specification = _specification(
        style=OrderStyle.LIMIT,
        tif=TimeInForce.GTC,
        session=SessionParticipation.REGULAR_AND_EXTENDED,
    )
    profile = _profile(
        combinations=(
            (
                OrderStyle.LIMIT,
                TimeInForce.GTC,
                SessionParticipation.REGULAR_AND_EXTENDED,
            ),
        )
    )
    result = evaluate_broker_execution_structural_compatibility(
        specification=specification, capability_profile=profile
    )
    assert result.outcome is BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE


@pytest.mark.parametrize(
    ("profile_overrides", "reason"),
    [
        ({"assets": (InstrumentAssetClass.ETF,)}, R.UNSUPPORTED_ASSET_CLASS),
        ({"currencies": ("EUR",)}, R.UNSUPPORTED_TRADING_CURRENCY),
        ({"venues": ("NYSE",)}, R.UNSUPPORTED_VENUE),
        (
            {
                "combinations": (
                    (
                        OrderStyle.LIMIT,
                        TimeInForce.DAY,
                        SessionParticipation.REGULAR_ONLY,
                    ),
                )
            },
            R.UNSUPPORTED_ORDER_STYLE,
        ),
        (
            {
                "combinations": (
                    (
                        OrderStyle.MARKET,
                        TimeInForce.GTC,
                        SessionParticipation.REGULAR_ONLY,
                    ),
                )
            },
            R.UNSUPPORTED_TIME_IN_FORCE,
        ),
        (
            {
                "combinations": (
                    (
                        OrderStyle.MARKET,
                        TimeInForce.DAY,
                        SessionParticipation.REGULAR_AND_EXTENDED,
                    ),
                )
            },
            R.UNSUPPORTED_SESSION_PARTICIPATION,
        ),
    ],
)
def test_each_individual_rejection_reason(
    profile_overrides: dict[str, object],
    reason: BrokerExecutionStructuralCompatibilityReason,
) -> None:
    result = _evaluate(**profile_overrides)
    assert result.outcome is BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE
    assert result.rejection_reasons == (reason,)


def test_exact_combination_reason_only_when_each_component_is_supported() -> None:
    combinations = (
        (OrderStyle.MARKET, TimeInForce.GTC, SessionParticipation.REGULAR_ONLY),
        (OrderStyle.LIMIT, TimeInForce.DAY, SessionParticipation.REGULAR_AND_EXTENDED),
    )
    assert _evaluate(combinations=combinations).rejection_reasons == (
        R.UNSUPPORTED_ORDER_COMBINATION,
    )


@pytest.mark.parametrize(
    ("combination", "expected"),
    [
        (
            (OrderStyle.LIMIT, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),
            R.UNSUPPORTED_ORDER_STYLE,
        ),
        (
            (OrderStyle.MARKET, TimeInForce.GTC, SessionParticipation.REGULAR_ONLY),
            R.UNSUPPORTED_TIME_IN_FORCE,
        ),
        (
            (
                OrderStyle.MARKET,
                TimeInForce.DAY,
                SessionParticipation.REGULAR_AND_EXTENDED,
            ),
            R.UNSUPPORTED_SESSION_PARTICIPATION,
        ),
    ],
)
def test_combination_reason_is_suppressed_for_unsupported_component(
    combination: tuple[OrderStyle, TimeInForce, SessionParticipation],
    expected: BrokerExecutionStructuralCompatibilityReason,
) -> None:
    assert _evaluate(combinations=(combination,)).rejection_reasons == (expected,)


def test_multiple_reasons_are_canonical_and_combination_is_suppressed() -> None:
    result = _evaluate(
        assets=(InstrumentAssetClass.ETF,),
        currencies=("EUR",),
        venues=("NYSE",),
        combinations=(
            (
                OrderStyle.LIMIT,
                TimeInForce.GTC,
                SessionParticipation.REGULAR_AND_EXTENDED,
            ),
        ),
    )
    assert result.rejection_reasons == (
        R.UNSUPPORTED_ASSET_CLASS,
        R.UNSUPPORTED_TRADING_CURRENCY,
        R.UNSUPPORTED_VENUE,
        R.UNSUPPORTED_ORDER_STYLE,
        R.UNSUPPORTED_TIME_IN_FORCE,
        R.UNSUPPORTED_SESSION_PARTICIPATION,
    )


def test_asset_currency_and_venue_domains_are_independently_composable() -> None:
    specification = _specification(
        asset_class=InstrumentAssetClass.ETF, currency="EUR", venue="NYSE"
    )
    profile = _profile(
        assets=(InstrumentAssetClass.EQUITY, InstrumentAssetClass.ETF),
        currencies=("EUR", "USD"),
        venues=("NASDAQ", "NYSE"),
    )
    result = evaluate_broker_execution_structural_compatibility(
        specification=specification, capability_profile=profile
    )
    assert result.outcome is BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE


def test_source_fingerprints_are_bound_at_evaluation_time_only() -> None:
    specification = _specification()
    profile = _profile()
    result = evaluate_broker_execution_structural_compatibility(
        specification=specification, capability_profile=profile
    )
    assert result.capability_profile_fingerprint == profile.fingerprint
    assert result.order_specification_fingerprint == specification.fingerprint
    object.__setattr__(profile, "fingerprint", "sha256:" + "0" * 64)
    assert result.to_dict()["capability_profile_fingerprint"] != profile.fingerprint


def test_result_retains_no_sources_registry_attestation_or_weak_reference() -> None:
    result = _evaluate()
    slots = set(result.__slots__)
    assert slots == {
        "capability_profile_fingerprint",
        "order_specification_fingerprint",
        "outcome",
        "rejection_reasons",
        "schema_version",
        "fingerprint",
    }
    source = inspect.getsource(compatibility_module)
    assert "weakref" not in source
    assert "attestation" not in source
    assert "origin_registry" not in source


def test_projection_and_fingerprint_payload_key_order_are_exact_and_json_safe() -> None:
    result = _evaluate()
    projection = result.to_dict()
    assert list(projection) == [
        "schema_version",
        "capability_profile_fingerprint",
        "order_specification_fingerprint",
        "outcome",
        "rejection_reasons",
        "fingerprint",
    ]
    payload = projection.copy()
    payload.pop("fingerprint")
    assert list(payload) == [
        "schema_version",
        "capability_profile_fingerprint",
        "order_specification_fingerprint",
        "outcome",
        "rejection_reasons",
    ]
    assert result.fingerprint == canonical_fingerprint(payload)
    json.dumps(projection)


def test_projection_and_fingerprint_are_deterministic() -> None:
    assert _evaluate().to_dict() == _evaluate().to_dict()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("capability_profile_fingerprint", "bad"),
        ("order_specification_fingerprint", "bad"),
        ("outcome", "compatible"),
        ("rejection_reasons", []),
        ("schema_version", "wrong/v1"),
        ("fingerprint", "sha256:" + "0" * 64),
    ],
)
def test_malformed_result_state_is_rejected(field_name: str, value: object) -> None:
    result = _evaluate()
    object.__setattr__(result, field_name, value)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    ("outcome", "reasons"),
    [
        (
            BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE,
            (R.UNSUPPORTED_VENUE,),
        ),
        (BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE, ()),
        (
            BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE,
            (R.UNSUPPORTED_VENUE, R.UNSUPPORTED_VENUE),
        ),
        (
            BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE,
            (R.UNSUPPORTED_VENUE, R.UNSUPPORTED_ASSET_CLASS),
        ),
        (
            BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE,
            ("unsupported_venue",),
        ),
        (
            BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE,
            (_ForeignReason.VALUE,),
        ),
    ],
)
def test_outcome_and_reason_invariant_corruption_is_rejected(
    outcome: object, reasons: object
) -> None:
    result = _evaluate(venues=("NYSE",))
    object.__setattr__(result, "outcome", outcome)
    object.__setattr__(result, "rejection_reasons", reasons)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_outcome_reason_invariants_survive_top_level_refingerprinting() -> None:
    contradictions = (
        (
            BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE,
            (R.UNSUPPORTED_VENUE,),
        ),
        (BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE, ()),
    )
    for outcome, reasons in contradictions:
        result = _evaluate(venues=("NYSE",))
        object.__setattr__(result, "outcome", outcome)
        object.__setattr__(result, "rejection_reasons", reasons)
        object.__setattr__(
            result,
            "fingerprint",
            canonical_fingerprint(result._fingerprint_payload()),
        )
        with pytest.raises(ExecutionPlanningCorrespondenceError):
            result.to_dict()


def test_result_subclasses_and_equality_spoofs_are_rejected_before_comparison() -> None:
    equality_spoof = _EqualitySpoof()
    values: tuple[object, ...] = (
        _StringSubclass("unsupported_venue"),
        equality_spoof,
    )
    for value in values:
        result = _evaluate(venues=("NYSE",))
        object.__setattr__(result, "rejection_reasons", (value,))
        with pytest.raises(ExecutionPlanningCorrespondenceError):
            result.to_dict()
    assert not equality_spoof.comparison_attempted


@pytest.mark.parametrize(
    "field_name",
    [item.name for item in fields(BrokerExecutionStructuralCompatibilityResult)],
)
def test_deleted_result_slots_are_rejected(field_name: str) -> None:
    result = _evaluate()
    object.__delattr__(result, field_name)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_exact_source_runtime_types_are_required() -> None:
    specification = _specification()
    profile = _profile()
    with pytest.raises(ExecutionPlanningValidationError):
        evaluate_broker_execution_structural_compatibility(
            specification=object(),  # type: ignore[arg-type]
            capability_profile=profile,
        )
    with pytest.raises(ExecutionPlanningValidationError):
        evaluate_broker_execution_structural_compatibility(
            specification=specification,
            capability_profile=object(),  # type: ignore[arg-type]
        )


def test_source_subclasses_are_rejected() -> None:
    specification_subclass = object.__new__(_SpecificationSubclass)
    profile_subclass = object.__new__(_ProfileSubclass)
    with pytest.raises(ExecutionPlanningValidationError):
        evaluate_broker_execution_structural_compatibility(
            specification=specification_subclass,
            capability_profile=_profile(),
        )
    with pytest.raises(ExecutionPlanningValidationError):
        evaluate_broker_execution_structural_compatibility(
            specification=_specification(),
            capability_profile=profile_subclass,
        )


def test_corrupted_sources_are_rejected_before_evaluation() -> None:
    specification = _specification()
    profile = _profile()
    object.__setattr__(specification, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        evaluate_broker_execution_structural_compatibility(
            specification=specification, capability_profile=profile
        )
    specification = _specification()
    object.__setattr__(profile, "supported_venues", ("nasdaq",))
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        evaluate_broker_execution_structural_compatibility(
            specification=specification, capability_profile=profile
        )


def test_limit_price_remains_specification_responsibility() -> None:
    specification = _specification(style=OrderStyle.LIMIT)
    profile = _profile(
        combinations=(
            (OrderStyle.LIMIT, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),
        )
    )
    assert (
        evaluate_broker_execution_structural_compatibility(
            specification=specification, capability_profile=profile
        ).outcome
        is BrokerExecutionStructuralCompatibilityOutcome.COMPATIBLE
    )
    assert "limit_price" not in BrokerExecutionStructuralCompatibilityResult.__slots__


def test_normal_incompatibility_never_raises() -> None:
    result = _evaluate(venues=("NYSE",))
    assert result.outcome is BrokerExecutionStructuralCompatibilityOutcome.INCOMPATIBLE


def test_no_timestamp_authorization_mapping_submission_or_lifecycle_state() -> None:
    names = set(BrokerExecutionStructuralCompatibilityResult.__slots__)
    forbidden = {
        "timestamp",
        "account",
        "authorization",
        "mapping",
        "submission",
        "lifecycle",
        "quantity",
        "tick_size",
        "price_collar",
        "broker_response",
    }
    assert names.isdisjoint(forbidden)


def test_public_model_documentation_defines_bounded_independent_structural_scope(
) -> None:
    profile_docs = " ".join(
        (
            inspect.getdoc(execution_planning.capability) or "",
            inspect.getdoc(BrokerExecutionCapabilityProfile) or "",
        )
    ).lower()
    result_docs = " ".join(
        (
            inspect.getdoc(compatibility_module) or "",
            inspect.getdoc(BrokerExecutionStructuralCompatibilityResult) or "",
            inspect.getdoc(evaluate_broker_execution_structural_compatibility) or "",
        )
    ).lower()
    assert "independent structural" in profile_docs
    assert "structurally composable" in profile_docs
    assert "structural compatibility" in result_docs
    assert "not complete broker executability" in result_docs


def test_aapl_nasdaq_historical_identity_is_unchanged() -> None:
    assert _canonical().trading_identity.instrument_fingerprint == (
        "sha256:dc586683e7966f5f6a9060934d37a28a594fe22b6cd42f40b5f5228e13cba433"
    )


def test_controlled_unrelated_runtime_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(payload: object) -> str:
        raise RuntimeError("controlled")

    monkeypatch.setattr(compatibility_module, "canonical_fingerprint", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        _evaluate()
