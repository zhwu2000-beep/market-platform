"""Focused tests for v0.69 broker-neutral execution authorization."""

from __future__ import annotations

import inspect
import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import market_platform.execution_planning as execution_planning
from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning import (
    BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA,
    BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA,
    BrokerNeutralExecutionAuthorization,
    BrokerNeutralExecutionAuthorizationPolicyIdentity,
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
    OrderStyle,
    OrderStyleChoice,
    SessionParticipation,
    SessionParticipationChoice,
    TimeInForce,
    TimeInForceChoice,
    authorize_broker_neutral_execution,
    construct_broker_execution_capability_profile,
    construct_broker_native_order_representation,
    construct_broker_neutral_execution_authorization_policy_identity,
    construct_broker_neutral_order_specification,
    derive_broker_neutral_execution_instruction,
    evaluate_broker_execution_structural_compatibility,
    map_broker_native_order,
    translate_position_target,
)
from market_platform.execution_planning import authorization as authorization_module
from market_platform.execution_planning import translation as translation_module
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
    RiskDecision,
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
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
    PositionRecord,
    StateSnapshotSourceIdentity,
    TradingAccountIdentity,
    TradingEnvironment,
)

BASE = datetime(2026, 1, 2, 15, tzinfo=UTC)
MAPPING_POLICY = canonical_fingerprint({"schema_version": "mapping_policy/v1"})


class _StringSubclass(str):
    pass


class _Mapper:
    execution_target_id = "broker.paper"
    mapper_id = "mapper.test"
    mapper_version = "1"
    mapping_policy_fingerprint = MAPPING_POLICY
    instrument_namespace = "vendor"

    def map_order(self, *, specification, external_instrument_identity):  # type: ignore[no-untyped-def]
        price = specification.limit_price_choice
        return construct_broker_native_order_representation(
            external_instrument_identity=external_instrument_identity,
            side_token="X1",
            quantity=specification.instruction.quantity,
            order_type_token="TYPE-7",
            limit_price=None if price is None else price.limit_price,
            limit_price_currency=None if price is None else price.trading_currency,
            time_in_force_token="ABC",
            session_participation_token="SESSION_Z",
        )


def _policy(version: str = "1") -> StructuralRiskPolicy:
    return StructuralRiskPolicy(
        "structural.default",
        version,
        None,
        timedelta(minutes=5),
        timedelta(minutes=5),
        timedelta(minutes=5),
        timedelta(minutes=1),
        timedelta(seconds=30),
        QuoteEvidenceRequirement.LAST,
    )


def _canonical(symbol: str = "AAPL") -> CanonicalInstrument:
    return CanonicalInstrument(
        CanonicalInstrumentId(f"instrument.{symbol}"),
        TradingInstrumentIdentity(symbol, "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )


def _intent(canonical: CanonicalInstrument, *, expired: bool = False) -> OrderIntent:
    signal = TradingSignal(
        TradingSignalSourceIdentity("strategy", "1"),
        "event",
        canonical.trading_identity,
        "1m",
        TradingTargetPosition.LONG,
        Decimal("10"),
        BASE - timedelta(hours=2),
        BASE - timedelta(hours=2),
        BASE - timedelta(minutes=30) if expired else BASE + timedelta(hours=2),
    )
    return create_order_intent_from_signal(
        signal, ExactTargetPositionIntentPolicy(), BASE - timedelta(hours=1)
    )


def _context(
    canonical: CanonicalInstrument,
    *,
    policy_version: str = "1",
    account_id: str = "account-1",
    expired: bool = False,
    intent_canonical: CanonicalInstrument | None = None,
) -> RiskEvaluationContext:
    external = ExternalInstrumentIdentity("vendor", "AAPL", "XNAS")
    relation = InstrumentMapping(
        external,
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        BASE - timedelta(days=1),
        None,
    )
    resolution: InstrumentResolution = resolve_instrument_mapping(
        external, [relation], BASE
    )
    account = TradingAccountIdentity(
        "broker", account_id, TradingEnvironment.PAPER, "USD"
    )
    source = StateSnapshotSourceIdentity("snapshot", "1")
    return RiskEvaluationContext(
        _intent(
            canonical if intent_canonical is None else intent_canonical, expired=expired
        ),
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
        _policy(policy_version),
        BASE,
    )


def _bundle(
    *,
    authorization_offset: timedelta = timedelta(),
    policy_version: str = "1",
    account_id: str = "account-1",
) -> dict[str, object]:
    canonical = _canonical()
    context = _context(canonical, policy_version=policy_version, account_id=account_id)
    decision = evaluate_structural_risk(context)
    translation = translate_position_target(context, decision, BASE)
    instruction = derive_broker_neutral_execution_instruction(translation)
    assert instruction is not None
    specification = construct_broker_neutral_order_specification(
        instruction=instruction,
        canonical_instrument=canonical,
        order_style_choice=OrderStyleChoice(OrderStyle.MARKET),
        limit_price_choice=None,
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
            (OrderStyle.MARKET, TimeInForce.DAY, SessionParticipation.REGULAR_ONLY),
        ),
    )
    compatibility = evaluate_broker_execution_structural_compatibility(
        specification=specification, capability_profile=profile
    )
    relation = InstrumentMapping(
        ExternalInstrumentIdentity("vendor", "AAPL", "XNAS"),
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        BASE - timedelta(days=1),
        None,
    )
    mapping = map_broker_native_order(
        specification=specification,
        capability_profile=profile,
        compatibility_result=compatibility,
        instrument_mapping=relation,
        mapper=_Mapper(),
    )
    return {
        "risk_context": context,
        "risk_decision": decision,
        "position_target_translation": translation,
        "specification": specification,
        "compatibility_result": compatibility,
        "native_order_mapping": mapping,
        "authorization_policy_identity": (
            construct_broker_neutral_execution_authorization_policy_identity(
                policy_id="platform.default", policy_version="1"
            )
        ),
        "authorization_as_of": BASE + authorization_offset,
    }


def _authorize(**overrides: object) -> BrokerNeutralExecutionAuthorization:
    values = _bundle()
    values.update(overrides)
    return authorize_broker_neutral_execution(**values)  # type: ignore[arg-type]


def _rewrite(target: object, name: str, value: object) -> None:
    object.__setattr__(target, name, value)


def test_exact_public_api_schemas_fields_and_signatures() -> None:
    additions = [
        "BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA",
        "BrokerNeutralExecutionAuthorizationPolicyIdentity",
        "construct_broker_neutral_execution_authorization_policy_identity",
        "BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA",
        "BrokerNeutralExecutionAuthorization",
        "authorize_broker_neutral_execution",
    ]
    assert execution_planning.__all__[-6:] == additions
    assert len(execution_planning.__all__) == 47
    assert (
        BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_POLICY_IDENTITY_SCHEMA
        == "broker_neutral_execution_authorization_policy_identity/v1"
    )
    assert (
        BROKER_NEUTRAL_EXECUTION_AUTHORIZATION_SCHEMA
        == "broker_neutral_execution_authorization/v1"
    )
    assert [
        item.name for item in fields(BrokerNeutralExecutionAuthorizationPolicyIdentity)
    ] == ["policy_id", "policy_version", "schema_version", "fingerprint"]
    assert [item.name for item in fields(BrokerNeutralExecutionAuthorization)] == [
        "authorization_policy_id",
        "authorization_policy_version",
        "authorization_policy_identity_fingerprint",
        "risk_context_fingerprint",
        "risk_decision_fingerprint",
        "position_target_translation_fingerprint",
        "order_specification_fingerprint",
        "structural_compatibility_result_fingerprint",
        "broker_native_order_mapping_fingerprint",
        "execution_target_id",
        "account_fingerprint",
        "evidence_as_of",
        "authorization_as_of",
        "schema_version",
        "fingerprint",
    ]
    factory = inspect.signature(
        construct_broker_neutral_execution_authorization_policy_identity
    )
    evaluator = inspect.signature(authorize_broker_neutral_execution)
    assert list(factory.parameters) == ["policy_id", "policy_version"]
    assert list(evaluator.parameters) == [
        "risk_context",
        "risk_decision",
        "position_target_translation",
        "specification",
        "compatibility_result",
        "native_order_mapping",
        "authorization_policy_identity",
        "authorization_as_of",
    ]
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        and parameter.default is inspect.Parameter.empty
        for parameter in (*factory.parameters.values(), *evaluator.parameters.values())
    )


def test_no_extra_authorization_surface() -> None:
    assert "configuration_fingerprint" not in {
        item.name for item in fields(BrokerNeutralExecutionAuthorizationPolicyIdentity)
    }
    assert not hasattr(execution_planning, "ExecutionAuthorizationPolicy")
    assert not hasattr(execution_planning, "AuthorizationOutcome")
    assert not hasattr(
        execution_planning, "construct_broker_neutral_execution_authorization"
    )
    with pytest.raises(TypeError):
        BrokerNeutralExecutionAuthorizationPolicyIdentity()
    with pytest.raises(TypeError):
        BrokerNeutralExecutionAuthorization()


@pytest.mark.parametrize("policy_id", ["a", "A", "1", "platform.default", "x" * 128])
def test_policy_id_valid_boundaries(policy_id: str) -> None:
    assert (
        construct_broker_neutral_execution_authorization_policy_identity(
            policy_id=policy_id, policy_version="1"
        ).policy_id
        == policy_id
    )


@pytest.mark.parametrize(
    "policy_id",
    [
        "",
        ".bad",
        "-bad",
        "bad/name",
        "bad name",
        "?",
        "x" * 129,
        _StringSubclass("valid"),
    ],
)
def test_policy_id_invalid(policy_id: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        construct_broker_neutral_execution_authorization_policy_identity(
            policy_id=policy_id, policy_version="1"
        )  # type: ignore[arg-type]


@pytest.mark.parametrize("version", ["!", "1", "1.0.0+rule", "~" * 64])
def test_policy_version_valid_boundaries(version: str) -> None:
    assert (
        construct_broker_neutral_execution_authorization_policy_identity(
            policy_id="policy", policy_version=version
        ).policy_version
        == version
    )


@pytest.mark.parametrize(
    "version", ["", "x" * 65, " ", "a b", "\n", chr(0xE9), _StringSubclass("1")]
)
def test_policy_version_invalid(version: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        construct_broker_neutral_execution_authorization_policy_identity(
            policy_id="policy", policy_version=version
        )  # type: ignore[arg-type]


def test_policy_projection_and_fingerprint_are_deterministic() -> None:
    first = construct_broker_neutral_execution_authorization_policy_identity(
        policy_id="policy", policy_version="1"
    )
    second = construct_broker_neutral_execution_authorization_policy_identity(
        policy_id="policy", policy_version="1"
    )
    assert list(first.to_dict()) == [
        "schema_version",
        "policy_id",
        "policy_version",
        "fingerprint",
    ]
    assert first.to_dict() == second.to_dict()


def test_success_projection_and_provenance() -> None:
    result = _authorize()
    assert list(result.to_dict()) == [
        "schema_version",
        "authorization_policy_id",
        "authorization_policy_version",
        "authorization_policy_identity_fingerprint",
        "risk_context_fingerprint",
        "risk_decision_fingerprint",
        "position_target_translation_fingerprint",
        "order_specification_fingerprint",
        "structural_compatibility_result_fingerprint",
        "broker_native_order_mapping_fingerprint",
        "execution_target_id",
        "account_fingerprint",
        "evidence_as_of",
        "authorization_as_of",
        "fingerprint",
    ]
    assert result.evidence_as_of == BASE and result.authorization_as_of == BASE
    assert result.execution_target_id == "broker.paper"
    assert json.loads(json.dumps(result.to_dict())) == result.to_dict()


def test_later_authorization_time_and_offset_canonicalization() -> None:
    later = _authorize(authorization_as_of=BASE + timedelta(minutes=1))
    offset = _authorize(
        authorization_as_of=(BASE + timedelta(hours=8)).replace(
            tzinfo=timezone(timedelta(hours=8))
        )
    )
    assert later.authorization_as_of == BASE + timedelta(minutes=1)
    assert offset.authorization_as_of == BASE
    assert offset.authorization_as_of.tzinfo is UTC


@pytest.mark.parametrize(
    "value",
    [
        BASE - timedelta(microseconds=1),
        datetime(2026, 1, 2, 15),
        "2026-01-02T15:00:00Z",
        1,
    ],
)
def test_invalid_authorization_time(value: object) -> None:
    with pytest.raises(ExecutionPlanningValidationError):
        _authorize(authorization_as_of=value)


def test_risk_replay_occurs_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _bundle()
    calls = 0
    original = authorization_module.evaluate_structural_risk

    def counted(context: RiskEvaluationContext) -> RiskDecision:
        nonlocal calls
        calls += 1
        return original(context)

    monkeypatch.setattr(authorization_module, "evaluate_structural_risk", counted)
    monkeypatch.setattr(translation_module, "evaluate_structural_risk", counted)
    authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]
    assert calls == 1


@pytest.mark.parametrize("source_name", ["risk_context", "risk_decision"])
def test_deleted_retained_risk_source_is_correspondence_error(
    source_name: str,
) -> None:
    bundle = _bundle()
    object.__delattr__(bundle[source_name], "fingerprint")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source_name",
    [
        "risk_context",
        "risk_decision",
        "position_target_translation",
        "specification",
        "compatibility_result",
        "native_order_mapping",
        "authorization_policy_identity",
    ],
)
def test_exact_source_runtime_types(source_name: str) -> None:
    bundle = _bundle()
    source = bundle[source_name]
    subclass = type(f"{type(source).__name__}Subclass", (type(source),), {})
    bundle[source_name] = object.__new__(subclass)
    with pytest.raises(ExecutionPlanningValidationError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


def test_corrupted_source_is_correspondence_error() -> None:
    bundle = _bundle()
    _rewrite(
        bundle["native_order_mapping"],
        "fingerprint",
        canonical_fingerprint({"schema_version": "stale/v1"}),
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field_name,new_value",
    [("authorization_policy_id", "other"), ("authorization_policy_version", "2")],
)
def test_policy_cross_field_invariant_survives_refingerprinting(
    field_name: str, new_value: str
) -> None:
    result = _authorize()
    _rewrite(result, field_name, new_value)
    _rewrite(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_policy_fingerprint_only_rewrite_survives_refingerprinting() -> None:
    result = _authorize()
    _rewrite(
        result,
        "authorization_policy_identity_fingerprint",
        canonical_fingerprint({"schema_version": "other/v1"}),
    )
    _rewrite(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_coherent_policy_rewrite_is_valid_value_boundary() -> None:
    result = _authorize()
    identity = construct_broker_neutral_execution_authorization_policy_identity(
        policy_id="other", policy_version="2"
    )
    _rewrite(result, "authorization_policy_id", identity.policy_id)
    _rewrite(result, "authorization_policy_version", identity.policy_version)
    _rewrite(result, "authorization_policy_identity_fingerprint", identity.fingerprint)
    _rewrite(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    assert result.to_dict()["authorization_policy_id"] == "other"


@pytest.mark.parametrize("field_name", ["evidence_as_of", "authorization_as_of"])
def test_noncanonical_retained_datetime_survives_coherent_refingerprinting(
    field_name: str,
) -> None:
    result = _authorize()
    projection = result.to_dict()
    projection.pop("fingerprint")
    noncanonical = getattr(result, field_name).astimezone(timezone(timedelta(hours=1)))
    projection[field_name] = noncanonical.isoformat()
    _rewrite(result, field_name, noncanonical)
    _rewrite(result, "fingerprint", canonical_fingerprint(projection))
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_time_ordering_survives_refingerprinting() -> None:
    result = _authorize()
    _rewrite(result, "authorization_as_of", BASE - timedelta(seconds=1))
    _rewrite(
        result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


@pytest.mark.parametrize(
    "field_name",
    [
        "risk_context_fingerprint",
        "risk_decision_fingerprint",
        "position_target_translation_fingerprint",
        "order_specification_fingerprint",
        "structural_compatibility_result_fingerprint",
        "broker_native_order_mapping_fingerprint",
        "account_fingerprint",
    ],
)
def test_malformed_retained_fingerprints(field_name: str) -> None:
    result = _authorize()
    _rewrite(result, field_name, "sha256:BAD")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_deleted_authorization_state_is_correspondence_error() -> None:
    result = _authorize()
    object.__delattr__(result, "account_fingerprint")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        result.to_dict()


def test_source_mutation_does_not_rewrite_authorization() -> None:
    bundle = _bundle()
    result = authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]
    before = result.to_dict()
    _rewrite(bundle["native_order_mapping"], "execution_target_id", "other")
    assert result.to_dict() == before


def test_no_retained_sources_registry_or_effect_surface() -> None:
    result = _authorize()
    names = {item.name for item in fields(result)}
    assert not names & {
        "risk_context",
        "risk_decision",
        "position_target_translation",
        "specification",
        "compatibility_result",
        "native_order_mapping",
        "authorization_policy_identity",
        "registry",
        "attestation",
        "weak_reference",
    }
    source = inspect.getsource(authorization_module)
    assert "ExecutionPlanningUnavailableError" not in source
    assert "datetime.now" not in source and "time.time" not in source
    assert "configuration_fingerprint" not in source


def test_rejected_risk_bundle_is_validation_not_unavailable() -> None:
    bundle = _bundle()
    context = _context(_canonical(), expired=True)
    decision = evaluate_structural_risk(context)
    bundle["risk_context"] = context
    bundle["risk_decision"] = decision
    with pytest.raises(ExecutionPlanningValidationError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


def test_indeterminate_risk_bundle_is_validation_not_unavailable() -> None:
    bundle = _bundle()
    context = _context(_canonical(), intent_canonical=_canonical(symbol="MSFT"))
    decision = evaluate_structural_risk(context)
    assert decision.outcome is RiskDecisionOutcome.INDETERMINATE
    bundle["risk_context"] = context
    bundle["risk_decision"] = decision
    with pytest.raises(ExecutionPlanningValidationError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


def test_valid_context_decision_mismatch_is_validation_error() -> None:
    bundle = _bundle()
    other = _bundle(policy_version="2")
    bundle["risk_context"] = other["risk_context"]
    with pytest.raises(ExecutionPlanningValidationError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source_name",
    [
        "position_target_translation",
        "specification",
        "compatibility_result",
        "native_order_mapping",
    ],
)
def test_valid_cross_source_mismatch_is_validation_error(source_name: str) -> None:
    bundle = _bundle()
    other = _bundle(policy_version="2")
    bundle[source_name] = other[source_name]
    with pytest.raises(ExecutionPlanningValidationError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


def test_valid_account_mismatch_is_validation_error() -> None:
    bundle = _bundle()
    other = _bundle(account_id="account-2")
    bundle["risk_context"] = other["risk_context"]
    bundle["risk_decision"] = other["risk_decision"]
    with pytest.raises(ExecutionPlanningValidationError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "source_name",
    [
        "risk_context",
        "risk_decision",
        "position_target_translation",
        "specification",
        "compatibility_result",
        "native_order_mapping",
        "authorization_policy_identity",
    ],
)
def test_each_corrupted_source_preserves_correspondence_error(source_name: str) -> None:
    bundle = _bundle()
    _rewrite(
        bundle[source_name],
        "fingerprint",
        canonical_fingerprint({"schema_version": "stale/v1"}),
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        authorize_broker_neutral_execution(**bundle)  # type: ignore[arg-type]


def test_policy_identity_deleted_state_is_correspondence_error() -> None:
    identity = construct_broker_neutral_execution_authorization_policy_identity(
        policy_id="policy", policy_version="1"
    )
    object.__delattr__(identity, "policy_version")
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        identity.to_dict()


def test_policy_identity_stale_fingerprint_is_correspondence_error() -> None:
    identity = construct_broker_neutral_execution_authorization_policy_identity(
        policy_id="policy", policy_version="1"
    )
    _rewrite(
        identity, "fingerprint", canonical_fingerprint({"schema_version": "stale/v1"})
    )
    with pytest.raises(ExecutionPlanningCorrespondenceError):
        identity.to_dict()
