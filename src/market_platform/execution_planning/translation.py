"""Factory-owned deterministic position target translation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import (
    canonical_plan_time,
    required_fingerprint,
    required_retained_attribute,
    timestamp_text,
)
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningUnavailableError,
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.quantities import (
    canonical_source_quantity,
    exact_subtract,
    quantity_sign,
    require_retained_quantity,
    signed_target_quantity,
)
from market_platform.instruments import (
    CanonicalInstrumentId,
    InstrumentDomainError,
    InstrumentResolution,
)
from market_platform.risk import (
    EvidenceCoverageScope,
    RiskDecision,
    RiskDecisionOutcome,
    RiskDomainError,
    RiskEvaluationContext,
    RiskEvidenceCoverage,
    StructuralRiskPolicy,
    evaluate_structural_risk,
)
from market_platform.trading import OrderIntent, TradingTargetPosition
from market_platform.trading_state import (
    AccountCashSnapshot,
    CashBalance,
    MarketQuote,
    MarketQuoteCollectionSnapshot,
    OpenOrderExposure,
    OpenOrderExposureSnapshot,
    PositionCollectionSnapshot,
    PositionRecord,
)

POSITION_TARGET_TRANSLATION_SCHEMA = "position_target_translation/v1"

_TRANSLATION_TOKEN = object()
_CONSTRUCTOR_BINDING_SENTINEL = object()


class PositionDeltaAction(StrEnum):
    """Exact action implied by a signed target-minus-current delta."""

    BUY = "buy"
    SELL = "sell"
    NO_ACTION = "no_action"


@dataclass(frozen=True, slots=True, init=False)
class PositionTargetTranslation:
    """Bounded mechanical target/current/delta evidence, never an order."""

    action: PositionDeltaAction
    risk_context_fingerprint: str
    risk_decision_fingerprint: str
    order_intent_fingerprint: str
    canonical_instrument_id: CanonicalInstrumentId
    canonical_instrument_fingerprint: str
    account_fingerprint: str
    position_snapshot_fingerprint: str
    open_order_snapshot_fingerprint: str
    plan_as_of: datetime
    target_quantity: Decimal
    current_quantity: Decimal
    delta_quantity: Decimal
    _constructor_state: tuple[object, ...] = field(repr=False, compare=False)
    _constructor_binding: tuple[object, object] = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "PositionTargetTranslation must be created by "
            "translate_position_target()"
        )

    @classmethod
    def _create(
        cls,
        *,
        action: PositionDeltaAction,
        risk_context_fingerprint: str,
        risk_decision_fingerprint: str,
        order_intent_fingerprint: str,
        canonical_instrument_id: CanonicalInstrumentId,
        canonical_instrument_fingerprint: str,
        account_fingerprint: str,
        position_snapshot_fingerprint: str,
        open_order_snapshot_fingerprint: str,
        plan_as_of: datetime,
        target_quantity: Decimal,
        current_quantity: Decimal,
        delta_quantity: Decimal,
        _token: object,
    ) -> PositionTargetTranslation:
        if _token is not _TRANSLATION_TOKEN:
            raise TypeError("position translation construction is factory-owned")
        if type(action) is not PositionDeltaAction:
            raise ExecutionPlanningValidationError(
                "action must be a PositionDeltaAction"
            )
        canonical_id = _canonical_instrument_id(canonical_instrument_id)
        plan_time = canonical_plan_time(plan_as_of, "plan_as_of")
        target, target_text = require_retained_quantity(
            target_quantity, "target_quantity"
        )
        current, current_text = require_retained_quantity(
            current_quantity, "current_quantity"
        )
        delta, delta_text = require_retained_quantity(
            delta_quantity, "delta_quantity", delta=True
        )
        fingerprints = tuple(
            required_fingerprint(value, name)
            for name, value in (
                ("risk_context_fingerprint", risk_context_fingerprint),
                ("risk_decision_fingerprint", risk_decision_fingerprint),
                ("order_intent_fingerprint", order_intent_fingerprint),
                (
                    "canonical_instrument_fingerprint",
                    canonical_instrument_fingerprint,
                ),
                ("account_fingerprint", account_fingerprint),
                ("position_snapshot_fingerprint", position_snapshot_fingerprint),
                (
                    "open_order_snapshot_fingerprint",
                    open_order_snapshot_fingerprint,
                ),
            )
        )
        state: tuple[object, ...] = (
            action.value,
            fingerprints[0],
            fingerprints[1],
            fingerprints[2],
            canonical_id.instrument_id,
            fingerprints[3],
            fingerprints[4],
            fingerprints[5],
            fingerprints[6],
            timestamp_text(plan_time),
            target_text,
            current_text,
            delta_text,
        )
        translation = object.__new__(cls)
        values: dict[str, object] = {
            "action": action,
            "risk_context_fingerprint": fingerprints[0],
            "risk_decision_fingerprint": fingerprints[1],
            "order_intent_fingerprint": fingerprints[2],
            "canonical_instrument_id": canonical_id,
            "canonical_instrument_fingerprint": fingerprints[3],
            "account_fingerprint": fingerprints[4],
            "position_snapshot_fingerprint": fingerprints[5],
            "open_order_snapshot_fingerprint": fingerprints[6],
            "plan_as_of": plan_time,
            "target_quantity": target,
            "current_quantity": current,
            "delta_quantity": delta,
            "_constructor_state": state,
            "_constructor_binding": (_CONSTRUCTOR_BINDING_SENTINEL, state),
            "_token": _TRANSLATION_TOKEN,
            "schema_version": POSITION_TARGET_TRANSLATION_SCHEMA,
        }
        for name, value in values.items():
            object.__setattr__(translation, name, value)
        object.__setattr__(
            translation,
            "fingerprint",
            canonical_fingerprint(translation._fingerprint_payload()),
        )
        translation._validate()
        return translation

    def _fingerprint_payload(self) -> dict[str, object]:
        _, target = require_retained_quantity(
            self.target_quantity, "target_quantity"
        )
        _, current = require_retained_quantity(
            self.current_quantity, "current_quantity"
        )
        _, delta = require_retained_quantity(
            self.delta_quantity, "delta_quantity", delta=True
        )
        return {
            "schema_version": self.schema_version,
            "action": self.action.value,
            "risk_context_fingerprint": self.risk_context_fingerprint,
            "risk_decision_fingerprint": self.risk_decision_fingerprint,
            "order_intent_fingerprint": self.order_intent_fingerprint,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "canonical_instrument_fingerprint": (
                self.canonical_instrument_fingerprint
            ),
            "account_fingerprint": self.account_fingerprint,
            "position_snapshot_fingerprint": self.position_snapshot_fingerprint,
            "open_order_snapshot_fingerprint": (
                self.open_order_snapshot_fingerprint
            ),
            "plan_as_of": timestamp_text(self.plan_as_of),
            "target_quantity": target,
            "current_quantity": current,
            "delta_quantity": delta,
        }

    def _validate(self) -> None:
        retained = {
            name: required_retained_attribute(
                self, name, "position target translation"
            )
            for name in (
                "_token",
                "_constructor_binding",
                "_constructor_state",
                "action",
                "risk_context_fingerprint",
                "risk_decision_fingerprint",
                "order_intent_fingerprint",
                "canonical_instrument_id",
                "canonical_instrument_fingerprint",
                "account_fingerprint",
                "position_snapshot_fingerprint",
                "open_order_snapshot_fingerprint",
                "plan_as_of",
                "target_quantity",
                "current_quantity",
                "delta_quantity",
                "schema_version",
                "fingerprint",
            )
        }
        if retained["_token"] is not _TRANSLATION_TOKEN:
            raise ExecutionPlanningCorrespondenceError(
                "position translation construction token is invalid"
            )
        binding = retained["_constructor_binding"]
        state = retained["_constructor_state"]
        if (
            type(binding) is not tuple
            or len(cast(tuple[object, ...], binding)) != 2
            or cast(tuple[object, ...], binding)[0]
            is not _CONSTRUCTOR_BINDING_SENTINEL
            or cast(tuple[object, ...], binding)[1] is not state
        ):
            raise ExecutionPlanningCorrespondenceError(
                "position translation constructor binding is invalid"
            )
        if type(state) is not tuple or len(cast(tuple[object, ...], state)) != 13:
            raise ExecutionPlanningCorrespondenceError(
                "position translation constructor state is invalid"
            )
        expected_state = _retained_state_projection(retained)
        if cast(tuple[object, ...], state) != expected_state:
            raise ExecutionPlanningCorrespondenceError(
                "position translation contradicts constructor state"
            )
        if retained["schema_version"] != POSITION_TARGET_TRANSLATION_SCHEMA:
            raise ExecutionPlanningCorrespondenceError(
                "position translation schema_version is invalid"
            )
        action = retained["action"]
        if type(action) is not PositionDeltaAction:
            raise ExecutionPlanningCorrespondenceError(
                "position translation action is invalid"
            )
        target = cast(Decimal, retained["target_quantity"])
        current = cast(Decimal, retained["current_quantity"])
        delta = cast(Decimal, retained["delta_quantity"])
        expected_delta, _ = exact_subtract(target, current)
        if delta.as_tuple() != expected_delta.as_tuple():
            raise ExecutionPlanningCorrespondenceError(
                "delta_quantity must equal target minus current"
            )
        if action is not _action_for_delta(delta):
            raise ExecutionPlanningCorrespondenceError(
                "position translation action contradicts delta"
            )
        expected_fingerprint = canonical_fingerprint(self._fingerprint_payload())
        if retained["fingerprint"] != expected_fingerprint:
            raise ExecutionPlanningCorrespondenceError(
                "position translation fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the constant-sized deterministic translation projection."""

        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def translate_position_target(
    context: RiskEvaluationContext,
    decision: RiskDecision,
    plan_as_of: datetime,
) -> PositionTargetTranslation:
    """Derive one mechanical signed target translation from approved evidence."""

    if type(context) is not RiskEvaluationContext:
        raise ExecutionPlanningValidationError(
            "context must be a RiskEvaluationContext"
        )
    if type(decision) is not RiskDecision:
        raise ExecutionPlanningValidationError("decision must be a RiskDecision")
    canonical_time = canonical_plan_time(plan_as_of, "plan_as_of")
    canonical_context = _reconstruct_context(context)
    canonical_decision = _corresponding_decision(canonical_context, decision)
    if canonical_decision.outcome is not RiskDecisionOutcome.APPROVED:
        raise ExecutionPlanningUnavailableError(
            "structural risk decision is not approved"
        )
    if (
        canonical_decision.findings
        or canonical_decision.common_account_fingerprint is None
    ):
        raise ExecutionPlanningCorrespondenceError(
            "approved risk decision retains impossible state"
        )
    if (
        canonical_context.coverage.positions
        is not EvidenceCoverageScope.COMPLETE_ACCOUNT
        or canonical_context.coverage.open_orders
        is not EvidenceCoverageScope.COMPLETE_ACCOUNT
    ):
        raise ExecutionPlanningCorrespondenceError(
            "approved risk evidence coverage is inconsistent"
        )
    if (
        canonical_time != canonical_context.evaluation_as_of
        or canonical_time != canonical_decision.evaluation_as_of
    ):
        raise ExecutionPlanningUnavailableError(
            "plan_as_of must equal structural risk evaluation time"
        )
    canonical = canonical_context.instrument_resolution.mapping.canonical_instrument
    target_id = _canonical_instrument_id(canonical.instrument_id)
    current = Decimal("0")
    for position in canonical_context.position_snapshot.positions:
        if _instrument_ids_equal(position.instrument_id, target_id):
            current, _ = canonical_source_quantity(
                position.quantity, "current_quantity", allow_negative=True
            )
            break
    for exposure in canonical_context.open_order_snapshot.exposures:
        if _instrument_ids_equal(exposure.instrument_id, target_id):
            raise ExecutionPlanningUnavailableError(
                "target instrument has open-order exposure"
            )
    signal = canonical_context.order_intent.source_signal
    if type(signal.target_position) is not TradingTargetPosition:
        raise ExecutionPlanningCorrespondenceError(
            "order intent target direction is invalid"
        )
    magnitude, _ = canonical_source_quantity(
        signal.target_units,
        "target_quantity",
        allow_negative=False,
    )
    target = signed_target_quantity(signal.target_position.value, magnitude)
    target, _ = canonical_source_quantity(
        target, "target_quantity", allow_negative=True
    )
    delta, _ = exact_subtract(target, current)
    return PositionTargetTranslation._create(
        action=_action_for_delta(delta),
        risk_context_fingerprint=canonical_context.fingerprint,
        risk_decision_fingerprint=canonical_decision.fingerprint,
        order_intent_fingerprint=canonical_context.order_intent.intent_fingerprint,
        canonical_instrument_id=target_id,
        canonical_instrument_fingerprint=canonical.fingerprint,
        account_fingerprint=canonical_decision.common_account_fingerprint,
        position_snapshot_fingerprint=(
            canonical_context.position_snapshot.fingerprint
        ),
        open_order_snapshot_fingerprint=(
            canonical_context.open_order_snapshot.fingerprint
        ),
        plan_as_of=canonical_time,
        target_quantity=target,
        current_quantity=current,
        delta_quantity=delta,
        _token=_TRANSLATION_TOKEN,
    )


def _reconstruct_context(context: RiskEvaluationContext) -> RiskEvaluationContext:
    names = (
        "order_intent",
        "instrument_resolution",
        "cash_snapshot",
        "position_snapshot",
        "open_order_snapshot",
        "quote_snapshot",
        "coverage",
        "policy",
        "evaluation_as_of",
        "schema_version",
        "fingerprint",
    )
    values = {
        name: required_retained_attribute(context, name, "risk evaluation context")
        for name in names
    }
    _preflight_retained_snapshots(
        values["cash_snapshot"],
        values["position_snapshot"],
        values["open_order_snapshot"],
        values["quote_snapshot"],
    )
    try:
        reconstructed = RiskEvaluationContext(
            order_intent=cast(OrderIntent, values["order_intent"]),
            instrument_resolution=cast(
                InstrumentResolution, values["instrument_resolution"]
            ),
            cash_snapshot=cast(AccountCashSnapshot, values["cash_snapshot"]),
            position_snapshot=cast(
                PositionCollectionSnapshot, values["position_snapshot"]
            ),
            open_order_snapshot=cast(
                OpenOrderExposureSnapshot, values["open_order_snapshot"]
            ),
            quote_snapshot=cast(
                MarketQuoteCollectionSnapshot, values["quote_snapshot"]
            ),
            coverage=cast(RiskEvidenceCoverage, values["coverage"]),
            policy=cast(StructuralRiskPolicy, values["policy"]),
            evaluation_as_of=cast(datetime, values["evaluation_as_of"]),
        )
        original_projection = context.to_dict()
        reconstructed_projection = reconstructed.to_dict()
    except RiskDomainError as error:
        raise ExecutionPlanningCorrespondenceError(
            "risk evaluation context is not canonical"
        ) from error
    if (
        values["schema_version"] != reconstructed.schema_version
        or values["fingerprint"] != reconstructed.fingerprint
        or original_projection != reconstructed_projection
    ):
        raise ExecutionPlanningCorrespondenceError(
            "risk evaluation context does not match public reconstruction"
        )
    return reconstructed


def _preflight_retained_snapshots(
    cash: object,
    positions: object,
    open_orders: object,
    quotes: object,
) -> None:
    """Require exact snapshot structure before public reconstruction."""

    _preflight_retained_snapshot(
        cash,
        snapshot_type=AccountCashSnapshot,
        subject="cash snapshot",
        header_fields=(
            "account",
            "source",
            "as_of",
            "balances",
            "schema_version",
            "fingerprint",
        ),
        collection_field="balances",
        row_type=CashBalance,
        row_subject="cash balance",
        row_fields=("currency", "amount"),
    )
    _preflight_retained_snapshot(
        positions,
        snapshot_type=PositionCollectionSnapshot,
        subject="position snapshot",
        header_fields=(
            "account",
            "source",
            "as_of",
            "positions",
            "schema_version",
            "fingerprint",
        ),
        collection_field="positions",
        row_type=PositionRecord,
        row_subject="position row",
        row_fields=("instrument_id", "quantity"),
    )
    _preflight_retained_snapshot(
        open_orders,
        snapshot_type=OpenOrderExposureSnapshot,
        subject="open-order snapshot",
        header_fields=(
            "account",
            "source",
            "as_of",
            "exposures",
            "schema_version",
            "fingerprint",
        ),
        collection_field="exposures",
        row_type=OpenOrderExposure,
        row_subject="open-order exposure",
        row_fields=("external_order_id", "instrument_id", "remaining_quantity"),
    )
    _preflight_retained_snapshot(
        quotes,
        snapshot_type=MarketQuoteCollectionSnapshot,
        subject="quote snapshot",
        header_fields=(
            "source",
            "as_of",
            "quotes",
            "schema_version",
            "fingerprint",
        ),
        collection_field="quotes",
        row_type=MarketQuote,
        row_subject="market quote",
        row_fields=("instrument_id", "bid", "ask", "last"),
    )


def _preflight_retained_snapshot(
    snapshot: object,
    *,
    snapshot_type: type[object],
    subject: str,
    header_fields: tuple[str, ...],
    collection_field: str,
    row_type: type[object],
    row_subject: str,
    row_fields: tuple[str, ...],
) -> None:
    if type(snapshot) is not snapshot_type:
        raise ExecutionPlanningCorrespondenceError(
            f"{subject} has invalid runtime type"
        )
    retained = {
        name: required_retained_attribute(snapshot, name, subject)
        for name in header_fields
    }
    rows = retained[collection_field]
    if type(rows) is not tuple:
        raise ExecutionPlanningCorrespondenceError(
            f"{subject} row collection has invalid runtime type"
        )
    for row in cast(tuple[object, ...], rows):
        if type(row) is not row_type:
            raise ExecutionPlanningCorrespondenceError(
                f"{row_subject} has invalid runtime type"
            )
        for field_name in row_fields:
            required_retained_attribute(row, field_name, row_subject)


def _corresponding_decision(
    context: RiskEvaluationContext,
    decision: RiskDecision,
) -> RiskDecision:
    try:
        canonical = evaluate_structural_risk(context)
        supplied_projection = decision.to_dict()
        canonical_projection = canonical.to_dict()
    except RiskDomainError as error:
        raise ExecutionPlanningCorrespondenceError(
            "risk decision is not canonical"
        ) from error
    if supplied_projection != canonical_projection:
        raise ExecutionPlanningCorrespondenceError(
            "risk decision does not correspond to risk context"
        )
    return canonical


def _canonical_instrument_id(value: object) -> CanonicalInstrumentId:
    if type(value) is not CanonicalInstrumentId:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID has invalid runtime type"
        )
    retained = value
    try:
        instrument_id = required_retained_attribute(
            retained, "instrument_id", "canonical instrument ID"
        )
        reconstructed = CanonicalInstrumentId(cast(str, instrument_id))
    except (TypeError, InstrumentDomainError) as error:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID cannot be reconstructed"
        ) from error
    if retained.to_dict() != reconstructed.to_dict():
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID does not match reconstruction"
        )
    return reconstructed


def _instrument_ids_equal(
    first: CanonicalInstrumentId,
    second: CanonicalInstrumentId,
) -> bool:
    return type(first) is CanonicalInstrumentId and first.to_dict() == second.to_dict()


def _action_for_delta(delta: Decimal) -> PositionDeltaAction:
    sign = quantity_sign(delta)
    if sign > 0:
        return PositionDeltaAction.BUY
    if sign < 0:
        return PositionDeltaAction.SELL
    return PositionDeltaAction.NO_ACTION


def _retained_state_projection(retained: dict[str, object]) -> tuple[object, ...]:
    action = retained["action"]
    if type(action) is not PositionDeltaAction:
        raise ExecutionPlanningCorrespondenceError(
            "position translation action is invalid"
        )
    canonical_id = _canonical_instrument_id(retained["canonical_instrument_id"])
    try:
        plan_time = canonical_plan_time(retained["plan_as_of"], "plan_as_of")
    except ExecutionPlanningValidationError as error:
        raise ExecutionPlanningCorrespondenceError(
            "position translation plan time is not canonical"
        ) from error
    _, target = require_retained_quantity(
        retained["target_quantity"], "target_quantity"
    )
    _, current = require_retained_quantity(
        retained["current_quantity"], "current_quantity"
    )
    _, delta = require_retained_quantity(
        retained["delta_quantity"], "delta_quantity", delta=True
    )
    fingerprint_names = (
        "risk_context_fingerprint",
        "risk_decision_fingerprint",
        "order_intent_fingerprint",
        "canonical_instrument_fingerprint",
        "account_fingerprint",
        "position_snapshot_fingerprint",
        "open_order_snapshot_fingerprint",
    )
    try:
        fingerprints = tuple(
            required_fingerprint(retained[name], name) for name in fingerprint_names
        )
    except ExecutionPlanningValidationError as error:
        raise ExecutionPlanningCorrespondenceError(
            "position translation evidence is not canonical"
        ) from error
    return (
        action.value,
        fingerprints[0],
        fingerprints[1],
        fingerprints[2],
        canonical_id.instrument_id,
        fingerprints[3],
        fingerprints[4],
        fingerprints[5],
        fingerprints[6],
        timestamp_text(plan_time),
        target,
        current,
        delta,
    )


__all__ = [
    "POSITION_TARGET_TRANSLATION_SCHEMA",
    "PositionDeltaAction",
    "PositionTargetTranslation",
    "translate_position_target",
]
