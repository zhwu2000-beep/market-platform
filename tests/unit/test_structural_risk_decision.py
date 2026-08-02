"""Focused tests for v0.59 structural risk decision foundations."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from enum import StrEnum
from itertools import permutations, product

import pytest

from market_platform._fingerprint import canonical_fingerprint
from market_platform.instruments import (
    CanonicalInstrument,
    CanonicalInstrumentId,
    ExternalInstrumentIdentity,
    InstrumentAssetClass,
    InstrumentMapping,
    InstrumentMappingSourceIdentity,
    resolve_instrument_mapping,
)
from market_platform.risk import (
    RISK_DECISION_SCHEMA_VERSION,
    RISK_EVALUATION_CONTEXT_SCHEMA_VERSION,
    STRUCTURAL_RISK_POLICY_SCHEMA_VERSION,
    EvidenceCoverageScope,
    QuoteEvidenceRequirement,
    RiskCorrespondenceError,
    RiskDecision,
    RiskDecisionOutcome,
    RiskEvaluationContext,
    RiskEvidenceCoverage,
    RiskFinding,
    RiskReasonCode,
    RiskValidationError,
    StructuralRiskPolicy,
    evaluate_structural_risk,
)
from market_platform.risk.decision import create_risk_decision
from market_platform.risk.findings import (
    canonical_findings,
    create_finding,
)
from market_platform.trading import (
    ExactTargetPositionIntentPolicy,
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
    TradingStateDomainError,
)

BASE = datetime(2025, 1, 2, 12, tzinfo=UTC)


class _UndefinedOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None


class _DurationSubclass(timedelta):
    pass


class _ForeignEnum(StrEnum):
    VALUE = "last"


class _EnumLikeProxy:
    value = "last"


def _policy(**changes: object) -> StructuralRiskPolicy:
    values: dict[str, object] = {
        "policy_id": "structural.default",
        "policy_version": "1.0.0",
        "configuration_fingerprint": None,
        "maximum_cash_age": timedelta(minutes=5),
        "maximum_position_age": timedelta(minutes=5),
        "maximum_open_order_age": timedelta(minutes=5),
        "maximum_quote_age": timedelta(minutes=1),
        "maximum_state_skew": timedelta(seconds=30),
        "quote_requirement": QuoteEvidenceRequirement.LAST,
    }
    values.update(changes)
    return StructuralRiskPolicy(**values)  # type: ignore[arg-type]


def _intent(
    *,
    symbol: str = "AAPL",
    venue: str = "NASDAQ",
    valid_from: datetime = BASE - timedelta(hours=2),
    expires_at: datetime = BASE + timedelta(hours=2),
):
    signal = TradingSignal(
        source=TradingSignalSourceIdentity("strategy", "1.0.0"),
        source_event_id="event-1",
        instrument=TradingInstrumentIdentity(symbol, venue),
        timeframe="1m",
        target_position=TradingTargetPosition.LONG,
        target_units=Decimal("10"),
        generated_at=valid_from - timedelta(minutes=1),
        valid_from=valid_from,
        expires_at=expires_at,
    )
    return create_order_intent_from_signal(
        signal,
        ExactTargetPositionIntentPolicy(),
        valid_from,
    )


def _resolution(
    *,
    symbol: str = "AAPL",
    resolved_as_of: datetime = BASE,
    valid_from: datetime = BASE - timedelta(days=1),
    expires_at: datetime | None = None,
):
    external = ExternalInstrumentIdentity("vendor", symbol, "XNAS")
    canonical = CanonicalInstrument(
        CanonicalInstrumentId(f"instrument.{symbol}"),
        TradingInstrumentIdentity(symbol, "NASDAQ"),
        InstrumentAssetClass.EQUITY,
        "USD",
    )
    mapping = InstrumentMapping(
        external,
        canonical,
        InstrumentMappingSourceIdentity("mapping", "1"),
        valid_from,
        expires_at,
    )
    return resolve_instrument_mapping(external, [mapping], resolved_as_of)


def _account(
    *,
    institution_namespace: str = "broker",
    account_id: str = "account-1",
    environment: TradingEnvironment = TradingEnvironment.PAPER,
    base_currency: str = "USD",
) -> TradingAccountIdentity:
    return TradingAccountIdentity(
        institution_namespace,
        account_id,
        environment,
        base_currency,
    )


def _context(
    *,
    intent=None,
    resolution=None,
    cash_account=None,
    position_account=None,
    order_account=None,
    cash_as_of: datetime = BASE - timedelta(seconds=10),
    position_as_of: datetime = BASE - timedelta(seconds=9),
    order_as_of: datetime = BASE - timedelta(seconds=8),
    snapshot_source=None,
    cash_balances=None,
    positions=None,
    open_orders=None,
    quote_as_of: datetime = BASE - timedelta(seconds=7),
    quotes=None,
    coverage=None,
    policy=None,
    evaluation_as_of: datetime = BASE,
) -> RiskEvaluationContext:
    shared_account = _account()
    source = snapshot_source or StateSnapshotSourceIdentity("snapshot", "1")
    resolution = resolution or _resolution()
    target_id = resolution.mapping.canonical_instrument.instrument_id
    return RiskEvaluationContext(
        order_intent=intent or _intent(),
        instrument_resolution=resolution,
        cash_snapshot=AccountCashSnapshot(
            cash_account or shared_account,
            source,
            cash_as_of,
            cash_balances
            if cash_balances is not None
            else [CashBalance("USD", Decimal("1000"))],
        ),
        position_snapshot=PositionCollectionSnapshot(
            position_account or shared_account,
            source,
            position_as_of,
            positions if positions is not None else [],
        ),
        open_order_snapshot=OpenOrderExposureSnapshot(
            order_account or shared_account,
            source,
            order_as_of,
            open_orders if open_orders is not None else [],
        ),
        quote_snapshot=MarketQuoteCollectionSnapshot(
            source,
            quote_as_of,
            quotes
            if quotes is not None
            else [MarketQuote(target_id, last=Decimal("190"))],
        ),
        coverage=coverage
        or RiskEvidenceCoverage(
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
        ),
        policy=policy or _policy(),
        evaluation_as_of=evaluation_as_of,
    )


def _codes(decision: RiskDecision) -> tuple[RiskReasonCode, ...]:
    return tuple(finding.reason_code for finding in decision.findings)


def test_exact_public_schema_and_enum_inventory() -> None:
    assert {
        STRUCTURAL_RISK_POLICY_SCHEMA_VERSION,
        RISK_EVALUATION_CONTEXT_SCHEMA_VERSION,
        RISK_DECISION_SCHEMA_VERSION,
    } == {
        "structural_risk_policy/v1",
        "risk_evaluation_context/v1",
        "risk_decision/v1",
    }
    assert {item.value for item in RiskDecisionOutcome} == {
        "approved",
        "rejected",
        "indeterminate",
    }
    assert {item.value for item in QuoteEvidenceRequirement} == {
        "any_price",
        "last",
        "bid_and_ask",
    }
    assert {item.value for item in EvidenceCoverageScope} == {
        "unverified",
        "complete_account",
        "target_instrument",
    }
    assert len(RiskReasonCode) == 21


@pytest.mark.parametrize(
    "value",
    ["a", "a" * 64, "policy.default", "p-1_v.2"],
)
def test_policy_id_accepts_exact_grammar(value: str) -> None:
    assert _policy(policy_id=value).policy_id == value


@pytest.mark.parametrize(
    "value",
    ["", "A", "1policy", ".policy", "policy/x", "policy:x", "a" * 65, "策略"],
)
def test_policy_id_rejects_invalid_grammar(value: str) -> None:
    with pytest.raises(RiskValidationError):
        _policy(policy_id=value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a b",
        "\x00",
        "\x7f",
        "\N{NO-BREAK SPACE}",
        "\N{ZERO WIDTH SPACE}",
        "ｖ１",
        "é",
        "v" * 65,
    ],
)
def test_policy_version_requires_bounded_visible_ascii(value: str) -> None:
    with pytest.raises(RiskValidationError):
        _policy(policy_version=value)


def test_policy_fingerprint_and_timedelta_projection_are_complete() -> None:
    policy = _policy(maximum_quote_age=timedelta(seconds=5))
    assert policy.to_dict()["maximum_quote_age_microseconds"] == "5000000"
    assert _policy(maximum_cash_age=timedelta.max).to_dict()[
        "maximum_cash_age_microseconds"
    ] == "86399999999999999999"
    assert policy == _policy(maximum_quote_age=timedelta(seconds=5))
    variants = (
        _policy(policy_id="other"),
        _policy(policy_version="2"),
        _policy(configuration_fingerprint="sha256:" + "a" * 64),
        _policy(maximum_cash_age=timedelta(seconds=1)),
        _policy(maximum_position_age=timedelta(seconds=1)),
        _policy(maximum_open_order_age=timedelta(seconds=1)),
        _policy(maximum_quote_age=timedelta(seconds=1)),
        _policy(maximum_state_skew=timedelta(seconds=1)),
        _policy(quote_requirement=QuoteEvidenceRequirement.BID_AND_ASK),
    )
    assert all(item.fingerprint != policy.fingerprint for item in variants)


def test_policy_rejects_wrong_duration_enum_and_fingerprint_state() -> None:
    for name in (
        "maximum_cash_age",
        "maximum_position_age",
        "maximum_open_order_age",
        "maximum_quote_age",
        "maximum_state_skew",
    ):
        with pytest.raises(RiskValidationError):
            _policy(**{name: timedelta(microseconds=-1)})
        with pytest.raises(RiskValidationError):
            _policy(**{name: _DurationSubclass(seconds=1)})
    with pytest.raises(RiskValidationError):
        _policy(configuration_fingerprint="SHA256:" + "A" * 64)


@pytest.mark.parametrize(
    "value",
    ["last", "any_price", _ForeignEnum.VALUE, object(), _EnumLikeProxy()],
)
def test_policy_quote_requirement_uses_risk_validation_boundary(value: object) -> None:
    with pytest.raises(RiskValidationError):
        _policy(quote_requirement=value)


def test_policy_fabrication_is_rejected_by_context() -> None:
    policy = _policy()
    object.__setattr__(policy, "policy_id", "INVALID")
    with pytest.raises(RiskCorrespondenceError):
        _context(policy=policy)


def test_coverage_combinations_and_projection_are_exact() -> None:
    adequate = RiskEvidenceCoverage(
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.TARGET_INSTRUMENT,
    )
    assert adequate.to_dict() == {
        "cash": "complete_account",
        "positions": "complete_account",
        "open_orders": "complete_account",
        "quotes": "target_instrument",
    }
    RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    invalid = (
        (EvidenceCoverageScope.TARGET_INSTRUMENT,) * 3
        + (EvidenceCoverageScope.TARGET_INSTRUMENT,),
        (
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
        ),
    )
    for values in invalid:
        with pytest.raises(RiskValidationError):
            RiskEvidenceCoverage(*values)
    with pytest.raises(RiskValidationError):
        RiskEvidenceCoverage(
            "complete_account",
            adequate.positions,
            adequate.open_orders,
            adequate.quotes,
        )


def test_approved_context_and_decision_are_bounded_and_json_safe() -> None:
    context = _context()
    projection = context.to_dict()
    assert "balances" not in repr(projection)
    assert "positions" not in projection["snapshots"]
    decision = evaluate_structural_risk(context)
    assert decision.outcome is RiskDecisionOutcome.APPROVED
    assert decision.findings == ()
    assert (
        decision.common_account_fingerprint == context.cash_snapshot.account.fingerprint
    )
    assert decision.schema_version == RISK_DECISION_SCHEMA_VERSION
    assert isinstance(decision.to_dict(), dict)


def test_context_normalizes_utc_and_rejects_invalid_time() -> None:
    offset = timezone(timedelta(hours=8))
    context = _context(evaluation_as_of=BASE.astimezone(offset))
    assert context.evaluation_as_of.tzinfo is UTC
    with pytest.raises(RiskValidationError):
        _context(evaluation_as_of=BASE.replace(tzinfo=None))
    with pytest.raises(RiskValidationError):
        _context(evaluation_as_of=BASE.replace(tzinfo=_UndefinedOffset()))


def test_context_fingerprint_significance() -> None:
    baseline = _context()
    variants = (
        _context(policy=_policy(policy_version="2")),
        _context(evaluation_as_of=BASE + timedelta(microseconds=1)),
        _context(
            coverage=RiskEvidenceCoverage(
                EvidenceCoverageScope.UNVERIFIED,
                EvidenceCoverageScope.COMPLETE_ACCOUNT,
                EvidenceCoverageScope.COMPLETE_ACCOUNT,
                EvidenceCoverageScope.TARGET_INSTRUMENT,
            )
        ),
        _context(cash_as_of=BASE - timedelta(seconds=11)),
        _context(position_as_of=BASE - timedelta(seconds=11)),
        _context(order_as_of=BASE - timedelta(seconds=11)),
        _context(quote_as_of=BASE - timedelta(seconds=11)),
    )
    assert all(item.fingerprint != baseline.fingerprint for item in variants)


def test_valid_cross_object_mismatches_enter_context() -> None:
    context = _context(
        intent=_intent(symbol="MSFT"),
        position_account=_account(account_id="different"),
    )
    assert isinstance(context, RiskEvaluationContext)


def test_context_rejects_fabricated_released_models() -> None:
    intent = _intent()
    object.__setattr__(intent.source_signal.instrument, "symbol", "aapl")
    with pytest.raises(RiskCorrespondenceError):
        _context(intent=intent)
    context = _context()
    object.__setattr__(context.cash_snapshot, "fingerprint", "sha256:" + "0" * 64)
    with pytest.raises(RiskCorrespondenceError):
        RiskEvaluationContext(
            context.order_intent,
            context.instrument_resolution,
            context.cash_snapshot,
            context.position_snapshot,
            context.open_order_snapshot,
            context.quote_snapshot,
            context.coverage,
            context.policy,
            context.evaluation_as_of,
        )


@pytest.mark.parametrize(
    ("evaluation", "expected"),
    [
        (BASE - timedelta(hours=3), RiskReasonCode.INTENT_NOT_YET_VALID),
        (BASE + timedelta(hours=2), RiskReasonCode.INTENT_EXPIRED),
        (BASE + timedelta(hours=3), RiskReasonCode.INTENT_EXPIRED),
    ],
)
def test_intent_half_open_boundaries_reject_and_stop(
    evaluation: datetime,
    expected: RiskReasonCode,
) -> None:
    decision = evaluate_structural_risk(_context(evaluation_as_of=evaluation))
    assert decision.outcome is RiskDecisionOutcome.REJECTED
    assert _codes(decision) == (expected,)


def test_resolution_time_activity_and_instrument_stage() -> None:
    future = evaluate_structural_risk(
        _context(resolution=_resolution(resolved_as_of=BASE + timedelta(seconds=1)))
    )
    assert _codes(future) == (RiskReasonCode.RESOLUTION_FUTURE_DATED,)
    inactive_resolution = _resolution(
        resolved_as_of=BASE - timedelta(minutes=1),
        expires_at=BASE,
    )
    inactive = evaluate_structural_risk(_context(resolution=inactive_resolution))
    assert _codes(inactive) == (RiskReasonCode.MAPPING_INACTIVE,)
    mismatch = evaluate_structural_risk(_context(intent=_intent(symbol="MSFT")))
    assert _codes(mismatch) == (RiskReasonCode.INSTRUMENT_MISMATCH,)
    assert mismatch.outcome is RiskDecisionOutcome.INDETERMINATE


def test_resolution_before_or_equal_evaluation_is_accepted() -> None:
    for resolved in (BASE - timedelta(days=1), BASE):
        assert (
            evaluate_structural_risk(
                _context(resolution=_resolution(resolved_as_of=resolved))
            ).outcome
            is RiskDecisionOutcome.APPROVED
        )


@pytest.mark.parametrize(
    "changed",
    [
        _account(account_id="different"),
        _account(environment=TradingEnvironment.LIVE),
        _account(base_currency="EUR"),
    ],
)
def test_account_mismatch_is_indeterminate_and_auditable(changed) -> None:
    context = _context(position_account=changed)
    decision = evaluate_structural_risk(context)
    assert _codes(decision) == (RiskReasonCode.ACCOUNT_MISMATCH,)
    assert decision.common_account_fingerprint is None
    assert (
        decision.cash_account_fingerprint == context.cash_snapshot.account.fingerprint
    )
    assert decision.position_account_fingerprint == changed.fingerprint


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("cash_as_of", RiskReasonCode.CASH_STALE),
        ("position_as_of", RiskReasonCode.POSITION_STALE),
        ("order_as_of", RiskReasonCode.OPEN_ORDER_STALE),
        ("quote_as_of", RiskReasonCode.QUOTE_STALE),
    ],
)
def test_freshness_exact_and_one_over_boundaries(
    field: str, code: RiskReasonCode
) -> None:
    maximum = timedelta(minutes=1)
    exact = _context(
        **{field: BASE - maximum},
        policy=_policy(
            maximum_cash_age=maximum,
            maximum_position_age=maximum,
            maximum_open_order_age=maximum,
            maximum_quote_age=maximum,
            maximum_state_skew=timedelta(minutes=2),
        ),
    )
    assert code not in _codes(evaluate_structural_risk(exact))
    stale = _context(
        **{field: BASE - maximum - timedelta(microseconds=1)},
        policy=exact.policy,
    )
    assert code in _codes(evaluate_structural_risk(stale))


def test_future_freshness_findings_are_all_collected() -> None:
    future = BASE + timedelta(microseconds=1)
    decision = evaluate_structural_risk(
        _context(
            cash_as_of=future,
            position_as_of=future,
            order_as_of=future,
            quote_as_of=future,
        )
    )
    assert _codes(decision)[:4] == (
        RiskReasonCode.CASH_FUTURE_DATED,
        RiskReasonCode.POSITION_FUTURE_DATED,
        RiskReasonCode.OPEN_ORDER_FUTURE_DATED,
        RiskReasonCode.QUOTE_FUTURE_DATED,
    )


def test_skew_exact_boundary_and_one_over() -> None:
    policy = _policy(maximum_state_skew=timedelta(seconds=30))
    exact = _context(
        cash_as_of=BASE - timedelta(seconds=30),
        position_as_of=BASE,
        order_as_of=BASE,
        quote_as_of=BASE,
        policy=policy,
    )
    assert RiskReasonCode.EXCESSIVE_STATE_SKEW not in _codes(
        evaluate_structural_risk(exact)
    )
    excessive = replace(
        exact,
        cash_snapshot=replace(
            exact.cash_snapshot,
            as_of=BASE - timedelta(seconds=30, microseconds=1),
        ),
    )
    assert RiskReasonCode.EXCESSIVE_STATE_SKEW in _codes(
        evaluate_structural_risk(excessive)
    )


def test_all_inadequate_coverage_findings_are_collected() -> None:
    coverage = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    decision = evaluate_structural_risk(_context(coverage=coverage, quotes=[]))
    assert _codes(decision)[-4:] == (
        RiskReasonCode.CASH_COVERAGE_INADEQUATE,
        RiskReasonCode.POSITION_COVERAGE_INADEQUATE,
        RiskReasonCode.OPEN_ORDER_COVERAGE_INADEQUATE,
        RiskReasonCode.QUOTE_COVERAGE_INADEQUATE,
    )
    assert RiskReasonCode.QUOTE_MISSING not in _codes(decision)


@pytest.mark.parametrize(
    ("requirement", "quote_kwargs", "expected"),
    [
        (QuoteEvidenceRequirement.ANY_PRICE, {"bid": Decimal("1")}, None),
        (QuoteEvidenceRequirement.ANY_PRICE, {"ask": Decimal("2")}, None),
        (QuoteEvidenceRequirement.LAST, {"last": Decimal("1.5")}, None),
        (
            QuoteEvidenceRequirement.LAST,
            {"bid": Decimal("1")},
            RiskReasonCode.QUOTE_INSUFFICIENT,
        ),
        (
            QuoteEvidenceRequirement.BID_AND_ASK,
            {"bid": Decimal("1"), "ask": Decimal("2")},
            None,
        ),
        (
            QuoteEvidenceRequirement.BID_AND_ASK,
            {"last": Decimal("1.5")},
            RiskReasonCode.QUOTE_INSUFFICIENT,
        ),
    ],
)
def test_quote_modes_are_exact(requirement, quote_kwargs, expected) -> None:
    target = _resolution().mapping.canonical_instrument.instrument_id
    decision = evaluate_structural_risk(
        _context(
            quotes=[MarketQuote(target, **quote_kwargs)],
            policy=_policy(quote_requirement=requirement),
        )
    )
    assert expected in _codes(decision) if expected else not decision.findings


def test_missing_target_quote_is_indeterminate() -> None:
    unrelated = CanonicalInstrumentId("instrument.MSFT")
    decision = evaluate_structural_risk(
        _context(quotes=[MarketQuote(unrelated, last=Decimal("10"))])
    )
    assert _codes(decision) == (RiskReasonCode.QUOTE_MISSING,)


def test_findings_are_guarded_bounded_sorted_and_duplicate_free() -> None:
    with pytest.raises(TypeError):
        RiskFinding()
    fingerprint = "sha256:" + "a" * 64
    finding = create_finding(RiskReasonCode.QUOTE_MISSING, "quotes", fingerprint)
    assert finding.to_dict()["evidence_fingerprints"] == [fingerprint]
    with pytest.raises(RiskValidationError):
        create_finding(
            RiskReasonCode.QUOTE_MISSING,
            "quotes",
            *(f"sha256:{index:064x}" for index in range(5)),
        )
    with pytest.raises(RiskValidationError):
        canonical_findings([finding, finding])
    many = [
        create_finding(reason, subject)
        for reason in list(RiskReasonCode)[:4]
        for subject in (
            "intent",
            "mapping",
            "instrument",
            "account",
            "cash",
            "positions",
            "open_orders",
            "quotes",
            "state",
        )
    ]
    assert len(canonical_findings(many[:32])) == 32
    with pytest.raises(RiskValidationError):
        canonical_findings(many[:33])


def test_finding_order_is_input_neutral() -> None:
    items = [
        create_finding(RiskReasonCode.QUOTE_MISSING, "quotes"),
        create_finding(RiskReasonCode.CASH_STALE, "cash"),
        create_finding(RiskReasonCode.EXCESSIVE_STATE_SKEW, "state"),
    ]
    expected = canonical_findings(items)
    assert all(
        canonical_findings(list(order)) == expected for order in permutations(items)
    )


def test_decision_is_factory_only_and_rejects_impossible_fabrication() -> None:
    with pytest.raises(TypeError):
        RiskDecision()
    context = _context()
    approved = evaluate_structural_risk(context)
    object.__setattr__(approved, "outcome", RiskDecisionOutcome.INDETERMINATE)
    object.__setattr__(
        approved,
        "fingerprint",
        create_risk_decision(
            context,
            RiskDecisionOutcome.APPROVED,
            [],
        ).fingerprint,
    )
    with pytest.raises(RiskCorrespondenceError):
        approved.to_dict()


def test_state_drift_changes_context_and_decision_identity() -> None:
    first_context = _context()
    second_context = _context(evaluation_as_of=BASE + timedelta(microseconds=1))
    first = evaluate_structural_risk(first_context)
    second = evaluate_structural_risk(second_context)
    assert first_context.fingerprint != second_context.fingerprint
    assert first.fingerprint != second.fingerprint


def test_released_trading_identity_fingerprint_remains_exact() -> None:
    assert TradingInstrumentIdentity("AAPL", "NASDAQ").instrument_fingerprint == (
        "sha256:dc586683e7966f5f6a9060934d37a28a594fe22b6cd42f40b5f5228e13cba433"
    )


def test_public_models_are_frozen_slotted_and_derived_fields_are_not_init() -> None:
    for model in (
        StructuralRiskPolicy,
        RiskEvidenceCoverage,
        RiskEvaluationContext,
        RiskFinding,
        RiskDecision,
    ):
        assert hasattr(model, "__slots__")
    for model in (StructuralRiskPolicy, RiskEvaluationContext, RiskDecision):
        derived = {item.name for item in fields(model) if not item.init}
        assert "fingerprint" in derived


def test_package_has_no_financial_execution_or_external_effect_surface() -> None:
    import market_platform.risk as risk

    forbidden = {
        "ExecutionPlan",
        "RiskPolicyIdentity",
        "valid_until",
        "revalidate_risk_decision",
        "target_delta",
        "net_open_order_exposure",
    }
    assert forbidden.isdisjoint(set(dir(risk)))


def test_reason_code_order_is_exact() -> None:
    assert tuple(reason.value for reason in RiskReasonCode) == (
        "intent_not_yet_valid",
        "intent_expired",
        "resolution_future_dated",
        "mapping_inactive",
        "instrument_mismatch",
        "account_mismatch",
        "cash_future_dated",
        "cash_stale",
        "position_future_dated",
        "position_stale",
        "open_order_future_dated",
        "open_order_stale",
        "quote_future_dated",
        "quote_stale",
        "excessive_state_skew",
        "cash_coverage_inadequate",
        "position_coverage_inadequate",
        "open_order_coverage_inadequate",
        "quote_coverage_inadequate",
        "quote_missing",
        "quote_insufficient",
    )


def test_every_semantically_valid_coverage_combination_is_constructible() -> None:
    account_scopes = (
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
    )
    quote_scopes = (
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.TARGET_INSTRUMENT,
    )
    combinations = [
        (*account_values, quote_scope)
        for account_values in product(account_scopes, repeat=3)
        for quote_scope in quote_scopes
    ]
    assert len(combinations) == 16
    assert all(RiskEvidenceCoverage(*values) for values in combinations)


@pytest.mark.parametrize(
    "values",
    [
        (
            EvidenceCoverageScope.TARGET_INSTRUMENT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
        ),
        (
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
        ),
        (
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
            EvidenceCoverageScope.TARGET_INSTRUMENT,
        ),
        (
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
            EvidenceCoverageScope.COMPLETE_ACCOUNT,
        ),
    ],
)
def test_each_semantically_invalid_coverage_scope_is_rejected(values) -> None:
    with pytest.raises(RiskValidationError):
        RiskEvidenceCoverage(*values)


def test_fabricated_coverage_state_is_rejected_by_context() -> None:
    coverage = RiskEvidenceCoverage(
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.TARGET_INSTRUMENT,
    )
    object.__setattr__(coverage, "cash", EvidenceCoverageScope.TARGET_INSTRUMENT)
    with pytest.raises(RiskCorrespondenceError):
        _context(coverage=coverage)


def test_context_projection_is_exact_bounded_and_makes_no_atomicity_claim() -> None:
    context = _context()
    projection = context.to_dict()
    assert set(projection) == {
        "schema_version",
        "order_intent",
        "instrument_resolution",
        "account_evidence",
        "snapshots",
        "coverage",
        "policy_fingerprint",
        "evaluation_as_of",
        "fingerprint",
    }
    assert set(projection["snapshots"]) == {
        "cash_fingerprint",
        "position_fingerprint",
        "open_order_fingerprint",
        "quote_fingerprint",
    }
    rendered = repr(projection).lower()
    for excluded in ("balances", "exposures", "'quotes': [", "atomic", "bundle"):
        assert excluded not in rendered


def test_every_context_evidence_family_is_identity_significant() -> None:
    baseline = _context()
    target = baseline.instrument_resolution.mapping.canonical_instrument.instrument_id
    microsoft_resolution = _resolution(symbol="MSFT")
    variants = (
        _context(
            intent=_intent(symbol="MSFT"),
            resolution=microsoft_resolution,
        ),
        _context(cash_account=_account(account_id="cash-2")),
        _context(position_account=_account(account_id="position-2")),
        _context(order_account=_account(account_id="order-2")),
        _context(
            snapshot_source=StateSnapshotSourceIdentity("snapshot", "2"),
        ),
        _context(cash_balances=[CashBalance("USD", Decimal("999"))]),
        _context(positions=[PositionRecord(target, Decimal("1"))]),
        _context(
            open_orders=[OpenOrderExposure("order-1", target, Decimal("1"))],
        ),
        _context(quotes=[MarketQuote(target, last=Decimal("191"))]),
    )
    assert all(item.fingerprint != baseline.fingerprint for item in variants)
    assert all(
        evaluate_structural_risk(item).fingerprint
        != evaluate_structural_risk(baseline).fingerprint
        for item in variants
    )


def test_nested_released_instrument_state_is_independently_reconstructed() -> None:
    for target_name in ("external", "canonical", "source", "mapping", "resolution"):
        resolution = _resolution()
        targets = {
            "external": resolution.external_identity,
            "canonical": resolution.mapping.canonical_instrument,
            "source": resolution.mapping.source,
            "mapping": resolution.mapping,
            "resolution": resolution,
        }
        target = targets[target_name]
        field_name = "schema_version" if target_name == "resolution" else "fingerprint"
        object.__setattr__(target, field_name, "invalid")
        with pytest.raises(RiskCorrespondenceError):
            _context(resolution=resolution)


def test_nested_snapshot_rows_and_policy_state_are_independently_reconstructed(
) -> None:
    context = _context()
    object.__setattr__(context.cash_snapshot.balances[0], "amount", Decimal("999"))
    with pytest.raises(RiskCorrespondenceError):
        replace(context)

    policy = _policy()
    object.__setattr__(policy, "maximum_cash_age", timedelta(seconds=-1))
    with pytest.raises(RiskCorrespondenceError):
        _context(policy=policy)


@pytest.mark.parametrize(
    "evaluation",
    [BASE, BASE + timedelta(hours=1) - timedelta(microseconds=1)],
)
def test_intent_exact_valid_and_one_before_expiry_are_active(
    evaluation: datetime,
) -> None:
    intent = _intent(valid_from=BASE, expires_at=BASE + timedelta(hours=1))
    context = _context(
        intent=intent,
        cash_as_of=evaluation,
        position_as_of=evaluation,
        order_as_of=evaluation,
        quote_as_of=evaluation,
        evaluation_as_of=evaluation,
    )
    assert evaluate_structural_risk(context).outcome is RiskDecisionOutcome.APPROVED


def test_mapping_is_active_one_microsecond_before_half_open_expiry() -> None:
    evaluation = BASE - timedelta(microseconds=1)
    resolution = _resolution(
        resolved_as_of=BASE - timedelta(days=1),
        expires_at=BASE,
    )
    decision = evaluate_structural_risk(
        _context(
            resolution=resolution,
            cash_as_of=evaluation,
            position_as_of=evaluation,
            order_as_of=evaluation,
            quote_as_of=evaluation,
            evaluation_as_of=evaluation,
        )
    )
    assert decision.outcome is RiskDecisionOutcome.APPROVED


def test_institution_mismatch_is_account_mismatch() -> None:
    decision = evaluate_structural_risk(
        _context(position_account=_account(institution_namespace="other"))
    )
    assert _codes(decision) == (RiskReasonCode.ACCOUNT_MISMATCH,)


def test_account_stage_stops_freshness_coverage_and_quote_evaluation() -> None:
    coverage = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    decision = evaluate_structural_risk(
        _context(
            position_account=_account(account_id="different"),
            cash_as_of=BASE - timedelta(days=1),
            coverage=coverage,
            quotes=[],
        )
    )
    assert _codes(decision) == (RiskReasonCode.ACCOUNT_MISMATCH,)


def test_prior_stage_stops_allow_auditable_mismatched_account_references() -> None:
    expired = evaluate_structural_risk(
        _context(
            intent=_intent(expires_at=BASE),
            position_account=_account(account_id="different"),
        )
    )
    assert _codes(expired) == (RiskReasonCode.INTENT_EXPIRED,)
    assert expired.common_account_fingerprint is None

    future_resolution = evaluate_structural_risk(
        _context(
            resolution=_resolution(resolved_as_of=BASE + timedelta(seconds=1)),
            position_account=_account(account_id="different"),
        )
    )
    assert _codes(future_resolution) == (RiskReasonCode.RESOLUTION_FUTURE_DATED,)
    assert future_resolution.common_account_fingerprint is None


def test_each_inadequate_coverage_scope_is_reported_independently() -> None:
    expected = {
        "cash": RiskReasonCode.CASH_COVERAGE_INADEQUATE,
        "positions": RiskReasonCode.POSITION_COVERAGE_INADEQUATE,
        "open_orders": RiskReasonCode.OPEN_ORDER_COVERAGE_INADEQUATE,
        "quotes": RiskReasonCode.QUOTE_COVERAGE_INADEQUATE,
    }
    for field_name, reason in expected.items():
        scopes = {
            "cash": EvidenceCoverageScope.COMPLETE_ACCOUNT,
            "positions": EvidenceCoverageScope.COMPLETE_ACCOUNT,
            "open_orders": EvidenceCoverageScope.COMPLETE_ACCOUNT,
            "quotes": EvidenceCoverageScope.TARGET_INSTRUMENT,
        }
        scopes[field_name] = EvidenceCoverageScope.UNVERIFIED
        coverage = RiskEvidenceCoverage(**scopes)  # type: ignore[arg-type]
        assert _codes(evaluate_structural_risk(_context(coverage=coverage))) == (
            reason,
        )


def test_empty_snapshots_depend_on_coverage_and_quote_evidence() -> None:
    adequate = evaluate_structural_risk(
        _context(cash_balances=[], positions=[], open_orders=[], quotes=[])
    )
    assert _codes(adequate) == (RiskReasonCode.QUOTE_MISSING,)

    unverified = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    inadequate = evaluate_structural_risk(
        _context(
            cash_balances=[],
            positions=[],
            open_orders=[],
            quotes=[],
            coverage=unverified,
        )
    )
    assert _codes(inadequate) == (
        RiskReasonCode.CASH_COVERAGE_INADEQUATE,
        RiskReasonCode.POSITION_COVERAGE_INADEQUATE,
        RiskReasonCode.OPEN_ORDER_COVERAGE_INADEQUATE,
        RiskReasonCode.QUOTE_COVERAGE_INADEQUATE,
    )


def test_finding_enum_subject_and_evidence_constraints_are_exact() -> None:
    fingerprint = "sha256:" + "a" * 64
    with pytest.raises(RiskValidationError):
        create_finding("quote_missing", "quotes")  # type: ignore[arg-type]
    for subject in ("", "position", "order", "message", "state "):
        with pytest.raises(RiskValidationError):
            create_finding(RiskReasonCode.QUOTE_MISSING, subject)
    with pytest.raises(RiskValidationError):
        create_finding(
            RiskReasonCode.QUOTE_MISSING,
            "quotes",
            fingerprint,
            fingerprint,
        )


def test_decision_rejects_impossible_outcomes_stages_and_evidence() -> None:
    context = _context()
    quote_fingerprint = context.quote_snapshot.fingerprint
    quote_finding = create_finding(
        RiskReasonCode.QUOTE_MISSING,
        "quotes",
        quote_fingerprint,
    )
    intent_finding = create_finding(
        RiskReasonCode.INTENT_EXPIRED,
        "intent",
        context.order_intent.intent_fingerprint,
    )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(context, RiskDecisionOutcome.APPROVED, [quote_finding])
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(context, RiskDecisionOutcome.REJECTED, [quote_finding])
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(context, RiskDecisionOutcome.INDETERMINATE, [])
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            RiskDecisionOutcome.INDETERMINATE,
            [intent_finding],
        )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            RiskDecisionOutcome.REJECTED,
            [intent_finding, quote_finding],
        )
    wrong_subject = create_finding(
        RiskReasonCode.QUOTE_MISSING,
        "cash",
        quote_fingerprint,
    )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            RiskDecisionOutcome.INDETERMINATE,
            [wrong_subject],
        )
    wrong_evidence = create_finding(
        RiskReasonCode.QUOTE_MISSING,
        "quotes",
        context.cash_snapshot.fingerprint,
    )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            RiskDecisionOutcome.INDETERMINATE,
            [wrong_evidence],
        )


def test_decision_rejects_downstream_findings_at_resolution_stage() -> None:
    context = _context()
    findings = [
        create_finding(
            RiskReasonCode.RESOLUTION_FUTURE_DATED,
            "mapping",
            context.instrument_resolution.mapping.fingerprint,
        ),
        create_finding(
            RiskReasonCode.CASH_STALE,
            "cash",
            context.cash_snapshot.fingerprint,
        ),
    ]
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            RiskDecisionOutcome.INDETERMINATE,
            findings,
        )


def test_decision_common_account_and_retained_references_are_guarded() -> None:
    approved = evaluate_structural_risk(_context())
    object.__setattr__(approved, "common_account_fingerprint", None)
    with pytest.raises(RiskCorrespondenceError):
        approved.to_dict()

    mismatch = evaluate_structural_risk(
        _context(position_account=_account(account_id="different"))
    )
    object.__setattr__(
        mismatch,
        "common_account_fingerprint",
        mismatch.cash_account_fingerprint,
    )
    with pytest.raises(RiskCorrespondenceError):
        mismatch.to_dict()

    for field_name in (
        "context_fingerprint",
        "order_intent_fingerprint",
        "source_signal_fingerprint",
        "mapping_fingerprint",
        "canonical_instrument_fingerprint",
        "cash_account_fingerprint",
        "position_account_fingerprint",
        "open_order_account_fingerprint",
        "cash_snapshot_fingerprint",
        "position_snapshot_fingerprint",
        "open_order_snapshot_fingerprint",
        "quote_snapshot_fingerprint",
        "policy_fingerprint",
    ):
        decision = evaluate_structural_risk(_context())
        object.__setattr__(decision, field_name, "sha256:" + "0" * 64)
        with pytest.raises(RiskCorrespondenceError):
            decision.to_dict()


def test_decision_schema_time_instrument_and_ordering_are_guarded() -> None:
    decision = evaluate_structural_risk(_context())
    object.__setattr__(decision, "schema_version", "risk_decision/v2")
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()

    decision = evaluate_structural_risk(_context())
    object.__setattr__(decision, "evaluation_as_of", BASE + timedelta(microseconds=1))
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()

    decision = evaluate_structural_risk(_context())
    object.__setattr__(
        decision,
        "canonical_instrument_id",
        CanonicalInstrumentId("instrument.MSFT"),
    )
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()

    coverage = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    decision = evaluate_structural_risk(_context(coverage=coverage))
    object.__setattr__(decision, "findings", tuple(reversed(decision.findings)))
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()


def test_context_and_evaluator_require_exact_runtime_types() -> None:
    context = _context()
    with pytest.raises(RiskCorrespondenceError):
        evaluate_structural_risk("context")  # type: ignore[arg-type]
    with pytest.raises(RiskCorrespondenceError):
        replace(context, quote_snapshot=context.cash_snapshot)


def test_skew_uses_only_the_four_snapshot_timestamps() -> None:
    policy = _policy(maximum_state_skew=timedelta(seconds=1))
    first = _context(
        cash_as_of=BASE - timedelta(seconds=3),
        position_as_of=BASE - timedelta(seconds=2),
        order_as_of=BASE - timedelta(seconds=1),
        quote_as_of=BASE,
        policy=policy,
    )
    second = _context(
        intent=_intent(valid_from=BASE - timedelta(days=2)),
        resolution=_resolution(
            resolved_as_of=BASE - timedelta(hours=12),
            valid_from=BASE - timedelta(days=3),
        ),
        cash_as_of=BASE - timedelta(seconds=3),
        position_as_of=BASE - timedelta(seconds=2),
        order_as_of=BASE - timedelta(seconds=1),
        quote_as_of=BASE,
        policy=policy,
    )
    assert _codes(evaluate_structural_risk(first)) == (
        RiskReasonCode.EXCESSIVE_STATE_SKEW,
    )
    assert _codes(evaluate_structural_risk(second)) == (
        RiskReasonCode.EXCESSIVE_STATE_SKEW,
    )


def test_instrument_mismatch_evidence_must_match_the_context() -> None:
    context = _context(intent=_intent(symbol="MSFT"))
    finding = create_finding(
        RiskReasonCode.INSTRUMENT_MISMATCH,
        "instrument",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
    )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            RiskDecisionOutcome.INDETERMINATE,
            [finding],
        )


@pytest.mark.parametrize(
    "target_name",
    [
        "resolution_mapping",
        "resolution_external",
        "mapping_external",
        "canonical",
        "canonical_id",
        "trading_identity",
        "mapping_source",
    ],
)
def test_nested_resolution_wrong_types_use_correspondence_boundary(
    target_name: str,
) -> None:
    context = _context()
    resolution = _resolution()
    mapping = resolution.mapping
    canonical = mapping.canonical_instrument
    targets = {
        "resolution_mapping": (resolution, "mapping"),
        "resolution_external": (resolution, "external_identity"),
        "mapping_external": (mapping, "external_identity"),
        "canonical": (mapping, "canonical_instrument"),
        "canonical_id": (canonical, "instrument_id"),
        "trading_identity": (canonical, "trading_identity"),
        "mapping_source": (mapping, "source"),
    }
    owner, field_name = targets[target_name]
    object.__setattr__(owner, field_name, object())
    with pytest.raises(RiskCorrespondenceError):
        replace(context, instrument_resolution=resolution)


def test_recomputed_malformed_mapping_source_is_rejected() -> None:
    resolution = _resolution()
    source = resolution.mapping.source
    object.__setattr__(source, "source_id", "invalid source")
    object.__setattr__(
        source,
        "fingerprint",
        canonical_fingerprint(source._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        _context(resolution=resolution)


@pytest.mark.parametrize(
    "snapshot_name",
    ["cash_snapshot", "position_snapshot", "open_order_snapshot", "quote_snapshot"],
)
@pytest.mark.parametrize(
    ("error_type", "expected_type"),
    [
        (TradingStateDomainError, RiskCorrespondenceError),
        (TypeError, TypeError),
        (ValueError, ValueError),
        (RuntimeError, RuntimeError),
        (AssertionError, AssertionError),
    ],
)
def test_snapshot_projection_exception_matrix(
    monkeypatch: pytest.MonkeyPatch,
    snapshot_name: str,
    error_type: type[BaseException],
    expected_type: type[BaseException],
) -> None:
    context = _context()
    snapshot = getattr(context, snapshot_name)

    def raise_projection_error(self) -> dict[str, object]:
        raise error_type("projection probe")

    monkeypatch.setattr(type(snapshot), "to_dict", raise_projection_error)
    with pytest.raises(expected_type) as caught:
        replace(context)
    if error_type is TradingStateDomainError:
        assert isinstance(caught.value.__cause__, TradingStateDomainError)
        assert str(caught.value.__cause__) == "projection probe"
    else:
        assert str(caught.value) == "projection probe"


def test_decision_factory_rejects_false_approved_results() -> None:
    unverified = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.COMPLETE_ACCOUNT,
        EvidenceCoverageScope.TARGET_INSTRUMENT,
    )
    target = _resolution().mapping.canonical_instrument.instrument_id
    contexts = (
        _context(cash_as_of=BASE - timedelta(days=1)),
        _context(cash_as_of=BASE + timedelta(microseconds=1)),
        _context(coverage=unverified),
        _context(quotes=[]),
        _context(
            quotes=[MarketQuote(target, bid=Decimal("189"))],
            policy=_policy(quote_requirement=QuoteEvidenceRequirement.LAST),
        ),
    )
    for context in contexts:
        with pytest.raises(RiskCorrespondenceError):
            create_risk_decision(context, RiskDecisionOutcome.APPROVED, [])


def test_decision_factory_rejects_every_false_finding_family() -> None:
    context = _context()
    snapshot_fingerprints = (
        context.cash_snapshot.fingerprint,
        context.position_snapshot.fingerprint,
        context.open_order_snapshot.fingerprint,
        context.quote_snapshot.fingerprint,
    )
    false_findings = (
        create_finding(
            RiskReasonCode.INTENT_NOT_YET_VALID,
            "intent",
            context.order_intent.intent_fingerprint,
        ),
        create_finding(
            RiskReasonCode.INTENT_EXPIRED,
            "intent",
            context.order_intent.intent_fingerprint,
        ),
        create_finding(
            RiskReasonCode.RESOLUTION_FUTURE_DATED,
            "mapping",
            context.instrument_resolution.mapping.fingerprint,
        ),
        create_finding(
            RiskReasonCode.MAPPING_INACTIVE,
            "mapping",
            context.instrument_resolution.mapping.fingerprint,
        ),
        create_finding(
            RiskReasonCode.INSTRUMENT_MISMATCH,
            "instrument",
            "sha256:" + "a" * 64,
            "sha256:" + "b" * 64,
        ),
        create_finding(
            RiskReasonCode.ACCOUNT_MISMATCH,
            "account",
            context.cash_snapshot.account.fingerprint,
        ),
        create_finding(
            RiskReasonCode.CASH_STALE,
            "cash",
            context.cash_snapshot.fingerprint,
        ),
        create_finding(
            RiskReasonCode.EXCESSIVE_STATE_SKEW,
            "state",
            *snapshot_fingerprints,
        ),
        create_finding(
            RiskReasonCode.CASH_COVERAGE_INADEQUATE,
            "cash",
            context.cash_snapshot.fingerprint,
        ),
        create_finding(
            RiskReasonCode.QUOTE_INSUFFICIENT,
            "quotes",
            context.quote_snapshot.fingerprint,
        ),
    )
    for finding in false_findings:
        outcome = (
            RiskDecisionOutcome.REJECTED
            if finding.reason_code
            in {
                RiskReasonCode.INTENT_NOT_YET_VALID,
                RiskReasonCode.INTENT_EXPIRED,
            }
            else RiskDecisionOutcome.INDETERMINATE
        )
        with pytest.raises(RiskCorrespondenceError):
            create_risk_decision(context, outcome, [finding])


def test_decision_factory_rejects_omitted_extra_altered_and_unordered_findings(
) -> None:
    unverified = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    context = _context(coverage=unverified, quotes=[])
    canonical = evaluate_structural_risk(context)
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            canonical.outcome,
            canonical.findings[:-1],
        )
    extra = create_finding(
        RiskReasonCode.QUOTE_MISSING,
        "quotes",
        context.quote_snapshot.fingerprint,
    )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            canonical.outcome,
            [*canonical.findings, extra],
        )
    altered = create_finding(
        RiskReasonCode.CASH_COVERAGE_INADEQUATE,
        "cash",
        "sha256:" + "f" * 64,
    )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            canonical.outcome,
            [altered, *canonical.findings[1:]],
        )
    with pytest.raises(RiskCorrespondenceError):
        create_risk_decision(
            context,
            canonical.outcome,
            list(reversed(canonical.findings)),
        )


def test_decision_factory_accepts_only_exact_canonical_results() -> None:
    contexts = (
        _context(),
        _context(intent=_intent(expires_at=BASE)),
        _context(cash_as_of=BASE - timedelta(days=1)),
    )
    expected = (
        RiskDecisionOutcome.APPROVED,
        RiskDecisionOutcome.REJECTED,
        RiskDecisionOutcome.INDETERMINATE,
    )
    for context, outcome in zip(contexts, expected, strict=True):
        canonical = evaluate_structural_risk(context)
        recreated = create_risk_decision(
            context,
            canonical.outcome,
            list(canonical.findings),
        )
        assert canonical.outcome is outcome
        assert recreated.fingerprint == canonical.fingerprint


def test_recomputed_fingerprint_cannot_validate_false_context_result() -> None:
    context = _context(cash_as_of=BASE - timedelta(days=1))
    decision = evaluate_structural_risk(context)
    object.__setattr__(decision, "outcome", RiskDecisionOutcome.APPROVED)
    object.__setattr__(decision, "findings", ())
    object.__setattr__(
        decision,
        "fingerprint",
        canonical_fingerprint(decision._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()
    with pytest.raises(RiskCorrespondenceError):
        decision._validate(context)


def test_context_free_validation_rejects_finding_and_account_mutations() -> None:
    coverage = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    context = _context(coverage=coverage, quotes=[])

    def mutated_decision() -> RiskDecision:
        return evaluate_structural_risk(context)

    omitted = mutated_decision()
    object.__setattr__(omitted, "findings", omitted.findings[:-1])
    object.__setattr__(
        omitted,
        "fingerprint",
        canonical_fingerprint(omitted._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        omitted.to_dict()

    added = mutated_decision()
    false_finding = create_finding(
        RiskReasonCode.QUOTE_MISSING,
        "quotes",
        context.quote_snapshot.fingerprint,
    )
    object.__setattr__(
        added,
        "findings",
        canonical_findings([*added.findings, false_finding]),
    )
    object.__setattr__(
        added,
        "fingerprint",
        canonical_fingerprint(added._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        added.to_dict()

    altered = mutated_decision()
    first = altered.findings[0]
    changed = create_finding(
        first.reason_code,
        first.subject,
        "sha256:" + "f" * 64,
    )
    object.__setattr__(altered, "findings", (changed, *altered.findings[1:]))
    object.__setattr__(
        altered,
        "fingerprint",
        canonical_fingerprint(altered._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        altered.to_dict()

    matching = evaluate_structural_risk(_context())
    object.__setattr__(matching, "common_account_fingerprint", None)
    object.__setattr__(
        matching,
        "fingerprint",
        canonical_fingerprint(matching._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        matching.to_dict()

    mismatch_context = _context(position_account=_account(account_id="other"))
    mismatch = evaluate_structural_risk(mismatch_context)
    object.__setattr__(
        mismatch,
        "common_account_fingerprint",
        mismatch.cash_account_fingerprint,
    )
    object.__setattr__(
        mismatch,
        "fingerprint",
        canonical_fingerprint(mismatch._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        mismatch.to_dict()


def test_private_decision_attestation_is_required_and_context_bound() -> None:
    missing = evaluate_structural_risk(_context())
    object.__delattr__(missing, "_canonical_result")
    with pytest.raises(RiskCorrespondenceError):
        missing.to_dict()

    wrong_type = evaluate_structural_risk(_context())
    object.__setattr__(wrong_type, "_canonical_result", object())
    with pytest.raises(RiskCorrespondenceError):
        wrong_type.to_dict()

    approved = evaluate_structural_risk(_context())
    stale = evaluate_structural_risk(
        _context(cash_as_of=BASE - timedelta(days=1))
    )
    object.__setattr__(
        approved,
        "_canonical_result",
        object.__getattribute__(stale, "_canonical_result"),
    )
    with pytest.raises(RiskCorrespondenceError):
        approved.to_dict()


def test_constructor_state_rejects_synchronized_decision_mutations() -> None:
    def refingerprint(decision: RiskDecision) -> None:
        object.__setattr__(
            decision,
            "fingerprint",
            canonical_fingerprint(decision._fingerprint_payload()),
        )

    stale_context = _context(cash_as_of=BASE - timedelta(days=1))
    false_approved = evaluate_structural_risk(stale_context)
    false_approved_result = object.__getattribute__(
        false_approved, "_canonical_result"
    )
    object.__setattr__(
        false_approved_result, "outcome", RiskDecisionOutcome.APPROVED
    )
    object.__setattr__(false_approved_result, "findings", ())
    object.__setattr__(false_approved, "outcome", RiskDecisionOutcome.APPROVED)
    object.__setattr__(false_approved, "findings", ())
    refingerprint(false_approved)
    with pytest.raises(RiskCorrespondenceError):
        false_approved.to_dict()

    altered_evidence = evaluate_structural_risk(stale_context)
    altered_result = object.__getattribute__(altered_evidence, "_canonical_result")
    finding = altered_evidence.findings[0]
    changed_evidence = create_finding(
        finding.reason_code,
        finding.subject,
        "sha256:" + "f" * 64,
    )
    object.__setattr__(altered_result, "findings", (changed_evidence,))
    object.__setattr__(altered_evidence, "findings", (changed_evidence,))
    refingerprint(altered_evidence)
    with pytest.raises(RiskCorrespondenceError):
        altered_evidence.to_dict()

    in_place_evidence = evaluate_structural_risk(stale_context)
    in_place_finding = in_place_evidence.findings[0]
    object.__setattr__(
        in_place_finding,
        "evidence_fingerprints",
        ("sha256:" + "e" * 64,),
    )
    refingerprint(in_place_evidence)
    with pytest.raises(RiskCorrespondenceError):
        in_place_evidence.to_dict()

    changed_reason = evaluate_structural_risk(stale_context)
    reason_result = object.__getattribute__(changed_reason, "_canonical_result")
    false_reason = create_finding(
        RiskReasonCode.POSITION_STALE,
        "positions",
        changed_reason.position_snapshot_fingerprint,
    )
    object.__setattr__(reason_result, "findings", (false_reason,))
    object.__setattr__(changed_reason, "findings", (false_reason,))
    refingerprint(changed_reason)
    with pytest.raises(RiskCorrespondenceError):
        changed_reason.to_dict()

    changed_subject = evaluate_structural_risk(stale_context)
    subject_result = object.__getattribute__(changed_subject, "_canonical_result")
    false_subject = create_finding(
        RiskReasonCode.CASH_STALE,
        "state",
        changed_subject.cash_snapshot_fingerprint,
    )
    object.__setattr__(subject_result, "findings", (false_subject,))
    object.__setattr__(changed_subject, "findings", (false_subject,))
    refingerprint(changed_subject)
    with pytest.raises(RiskCorrespondenceError):
        changed_subject.to_dict()

    matching = evaluate_structural_risk(_context())
    matching_result = object.__getattribute__(matching, "_canonical_result")
    object.__setattr__(matching_result, "common_account_fingerprint", None)
    object.__setattr__(matching, "common_account_fingerprint", None)
    refingerprint(matching)
    with pytest.raises(RiskCorrespondenceError):
        matching.to_dict()

    mismatch_context = _context(position_account=_account(account_id="other"))
    mismatch = evaluate_structural_risk(mismatch_context)
    mismatch_result = object.__getattribute__(mismatch, "_canonical_result")
    object.__setattr__(
        mismatch_result,
        "common_account_fingerprint",
        mismatch.cash_account_fingerprint,
    )
    object.__setattr__(
        mismatch,
        "common_account_fingerprint",
        mismatch.cash_account_fingerprint,
    )
    refingerprint(mismatch)
    with pytest.raises(RiskCorrespondenceError):
        mismatch.to_dict()


def test_well_formed_forged_constructor_state_is_identity_rejected() -> None:
    decision = evaluate_structural_risk(
        _context(cash_as_of=BASE - timedelta(days=1))
    )
    result = object.__getattribute__(decision, "_canonical_result")
    binding = object.__getattribute__(result, "_constructor_binding")
    forged_state = (
        decision.context_fingerprint,
        RiskDecisionOutcome.APPROVED,
        (),
        decision.common_account_fingerprint,
    )
    assert forged_state is not binding[1]
    object.__setattr__(result, "outcome", RiskDecisionOutcome.APPROVED)
    object.__setattr__(result, "findings", ())
    object.__setattr__(result, "_constructor_state", forged_state)
    object.__setattr__(decision, "outcome", RiskDecisionOutcome.APPROVED)
    object.__setattr__(decision, "findings", ())
    object.__setattr__(
        decision,
        "fingerprint",
        canonical_fingerprint(decision._fingerprint_payload()),
    )
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()


def test_equal_constructor_state_replacement_is_identity_rejected() -> None:
    decision = evaluate_structural_risk(
        _context(cash_as_of=BASE - timedelta(days=1))
    )
    result = object.__getattribute__(decision, "_canonical_result")
    binding = object.__getattribute__(result, "_constructor_binding")
    original_state = object.__getattribute__(result, "_constructor_state")
    equal_state = tuple([*original_state])
    assert equal_state == original_state
    assert equal_state is not original_state
    assert binding[1] is original_state
    object.__setattr__(result, "_constructor_state", equal_state)
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()


def test_malformed_constructor_binding_is_rejected() -> None:
    context = _context(cash_as_of=BASE - timedelta(days=1))
    reference = evaluate_structural_risk(context)
    reference_result = object.__getattribute__(reference, "_canonical_result")
    reference_binding = object.__getattribute__(
        reference_result, "_constructor_binding"
    )
    reference_state = object.__getattribute__(reference_result, "_constructor_state")
    sentinel = reference_binding[0]
    equal_state = tuple([*reference_state])
    foreign = evaluate_structural_risk(_context())
    foreign_binding = object.__getattribute__(
        object.__getattribute__(foreign, "_canonical_result"),
        "_constructor_binding",
    )
    malformed_bindings: tuple[object, ...] = (
        object(),
        list(reference_binding),
        (),
        (sentinel,),
        (object(), reference_state),
        (sentinel, object()),
        (sentinel, equal_state),
        foreign_binding,
    )
    for malformed in malformed_bindings:
        decision = evaluate_structural_risk(context)
        result = object.__getattribute__(decision, "_canonical_result")
        object.__setattr__(result, "_constructor_binding", malformed)
        with pytest.raises(RiskCorrespondenceError):
            decision.to_dict()


def test_foreign_constructor_binding_state_combinations_are_rejected() -> None:
    context_pairs = (
        (_context(), _context(intent=_intent(expires_at=BASE))),
        (_context(intent=_intent(expires_at=BASE)), _context()),
        (_context(cash_as_of=BASE - timedelta(days=1)), _context()),
    )
    for target_context, donor_context in context_pairs:
        target = evaluate_structural_risk(target_context)
        donor = evaluate_structural_risk(donor_context)
        target_result = object.__getattribute__(target, "_canonical_result")
        donor_result = object.__getattribute__(donor, "_canonical_result")
        object.__setattr__(
            target_result,
            "_constructor_binding",
            object.__getattribute__(donor_result, "_constructor_binding"),
        )
        with pytest.raises(RiskCorrespondenceError):
            target.to_dict()


@pytest.mark.parametrize(
    "attribute_name",
    (
        "_token",
        "_constructor_binding",
        "_constructor_state",
        "context_fingerprint",
        "outcome",
        "findings",
        "common_account_fingerprint",
    ),
)
def test_missing_canonical_result_state_is_correspondence_error(
    attribute_name: str,
) -> None:
    decision = evaluate_structural_risk(_context())
    result = object.__getattribute__(decision, "_canonical_result")
    object.__delattr__(result, attribute_name)
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()


def test_malformed_constructor_state_is_rejected() -> None:
    coverage = RiskEvidenceCoverage(
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
        EvidenceCoverageScope.UNVERIFIED,
    )
    context = _context(coverage=coverage, quotes=[])

    def decision_and_state() -> tuple[RiskDecision, tuple[object, ...]]:
        decision = evaluate_structural_risk(context)
        result = object.__getattribute__(decision, "_canonical_result")
        return decision, object.__getattribute__(result, "_constructor_state")

    canonical_decision, canonical_state = decision_and_state()
    finding = canonical_decision.findings[0]
    altered_finding = create_finding(
        finding.reason_code,
        finding.subject,
        "sha256:" + "f" * 64,
    )
    other = evaluate_structural_risk(
        _context(cash_as_of=BASE - timedelta(days=1))
    )
    other_state = object.__getattribute__(
        object.__getattribute__(other, "_canonical_result"),
        "_constructor_state",
    )
    malformed_states: tuple[object, ...] = (
        object(),
        list(canonical_state),
        canonical_state[:-1],
        ("sha256:" + "a" * 64, *canonical_state[1:]),
        (canonical_state[0], "indeterminate", *canonical_state[2:]),
        (
            canonical_state[0],
            canonical_state[1],
            list(canonical_state[2]),
            canonical_state[3],
        ),
        (
            canonical_state[0],
            canonical_state[1],
            (altered_finding, *canonical_decision.findings[1:]),
            canonical_state[3],
        ),
        (
            canonical_state[0],
            canonical_state[1],
            tuple(reversed(canonical_decision.findings)),
            canonical_state[3],
        ),
        (
            canonical_state[0],
            canonical_state[1],
            (canonical_decision.findings[0], *canonical_decision.findings),
            canonical_state[3],
        ),
        (*canonical_state[:3], "sha256:" + "b" * 64),
        other_state,
    )
    for malformed in malformed_states:
        decision, _ = decision_and_state()
        result = object.__getattribute__(decision, "_canonical_result")
        object.__setattr__(result, "_constructor_state", malformed)
        with pytest.raises(RiskCorrespondenceError):
            decision.to_dict()


@pytest.mark.parametrize(
    ("attribute_name", "replacement"),
    (
        ("context_fingerprint", "sha256:" + "a" * 64),
        ("outcome", RiskDecisionOutcome.APPROVED),
        ("findings", ()),
        ("common_account_fingerprint", None),
    ),
)
def test_canonical_result_semantic_mutation_is_rejected(
    attribute_name: str,
    replacement: object,
) -> None:
    decision = evaluate_structural_risk(
        _context(cash_as_of=BASE - timedelta(days=1))
    )
    result = object.__getattribute__(decision, "_canonical_result")
    object.__setattr__(result, attribute_name, replacement)
    with pytest.raises(RiskCorrespondenceError):
        decision.to_dict()


def test_canonical_decisions_retain_valid_private_attestation() -> None:
    contexts = (
        _context(),
        _context(intent=_intent(expires_at=BASE)),
        _context(cash_as_of=BASE - timedelta(days=1)),
    )
    for context in contexts:
        decision = evaluate_structural_risk(context)
        first = decision.to_dict()
        decision._validate()
        decision._validate(context)
        assert decision.to_dict() == first
        result = object.__getattribute__(decision, "_canonical_result")
        constructor_state = object.__getattribute__(result, "_constructor_state")
        constructor_binding = object.__getattribute__(
            result, "_constructor_binding"
        )
        assert type(constructor_state) is tuple
        assert type(constructor_binding) is tuple
        assert len(constructor_binding) == 2
        assert constructor_binding[1] is constructor_state
        assert constructor_state[2] == decision.findings
        if decision.findings:
            assert constructor_state[2] is not decision.findings
            assert all(
                retained is not constructed
                for retained, constructed in zip(
                    decision.findings,
                    constructor_state[2],
                    strict=True,
                )
            )
        assert "_canonical_result" not in first
        assert "_constructor_state" not in first
        assert "_constructor_binding" not in first


@pytest.mark.parametrize(
    ("owner_name", "attribute_name"),
    (
        ("resolution", "mapping"),
        ("resolution", "external_identity"),
        ("resolution", "resolved_as_of"),
        ("resolution", "schema_version"),
        ("mapping", "external_identity"),
        ("mapping", "canonical_instrument"),
        ("mapping", "source"),
        ("mapping", "valid_from"),
        ("mapping", "expires_at"),
        ("mapping", "schema_version"),
        ("mapping", "fingerprint"),
        ("canonical", "instrument_id"),
        ("canonical", "trading_identity"),
        ("canonical", "asset_class"),
        ("canonical", "trading_currency"),
        ("canonical", "schema_version"),
        ("canonical", "fingerprint"),
        ("external", "namespace"),
        ("external", "external_symbol"),
        ("external", "external_venue"),
        ("external", "schema_version"),
        ("external", "fingerprint"),
        ("source", "source_id"),
        ("source", "source_version"),
        ("source", "configuration_fingerprint"),
        ("source", "schema_version"),
        ("source", "fingerprint"),
        ("canonical_id", "instrument_id"),
        ("trading_identity", "symbol"),
        ("trading_identity", "venue"),
        ("trading_identity", "schema_version"),
        ("trading_identity", "instrument_fingerprint"),
    ),
)
def test_missing_resolution_retained_state_is_correspondence_error(
    owner_name: str,
    attribute_name: str,
) -> None:
    context = _context()
    resolution = context.instrument_resolution
    mapping = resolution.mapping
    canonical = mapping.canonical_instrument
    owners = {
        "resolution": resolution,
        "mapping": mapping,
        "canonical": canonical,
        "external": resolution.external_identity,
        "source": mapping.source,
        "canonical_id": canonical.instrument_id,
        "trading_identity": canonical.trading_identity,
    }
    object.__delattr__(owners[owner_name], attribute_name)
    with pytest.raises(RiskCorrespondenceError):
        replace(context)


def test_context_projection_remains_bounded_for_large_snapshot() -> None:
    positions = [
        PositionRecord(
            CanonicalInstrumentId(f"instrument.LARGE{index:04d}"),
            Decimal("1"),
        )
        for index in range(250)
    ]
    projection = _context(positions=positions).to_dict()
    rendered = repr(projection)
    assert len(rendered) < 3_000
    assert "instrument.LARGE" not in rendered
