"""Broker-neutral acquisition and disposal instructions without order semantics."""

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
    ExecutionPlanningValidationError,
)
from market_platform.execution_planning.quantities import require_retained_quantity
from market_platform.execution_planning.translation import (
    POSITION_TARGET_TRANSLATION_SCHEMA,
    PositionDeltaAction,
    PositionTargetTranslation,
)
from market_platform.instruments import CanonicalInstrumentId

BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA = "broker_neutral_execution_instruction/v1"
_TOKEN = object()
_BINDING_SENTINEL = object()


class ExecutionInstructionSide(StrEnum):
    """Exact acquisition or disposal direction."""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True, init=False)
class BrokerNeutralExecutionInstruction:
    """One bounded non-executable acquisition or disposal proposal."""

    side: ExecutionInstructionSide
    quantity: Decimal
    source_translation_fingerprint: str
    canonical_instrument_id: CanonicalInstrumentId
    canonical_instrument_fingerprint: str
    account_fingerprint: str
    plan_as_of: datetime
    _source_translation: PositionTargetTranslation = field(repr=False, compare=False)
    _constructor_state: tuple[object, ...] = field(repr=False, compare=False)
    _constructor_binding: tuple[object, object] = field(repr=False, compare=False)
    _token: object = field(repr=False, compare=False)
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __init__(self) -> None:
        raise TypeError(
            "BrokerNeutralExecutionInstruction must be created by "
            "derive_broker_neutral_execution_instruction()"
        )

    @classmethod
    def _create(
        cls,
        *,
        source: PositionTargetTranslation,
        side: ExecutionInstructionSide,
        quantity: Decimal,
        token: object,
    ) -> BrokerNeutralExecutionInstruction:
        if token is not _TOKEN:
            raise TypeError("execution instruction construction is factory-owned")
        if type(source) is not PositionTargetTranslation:
            raise ExecutionPlanningValidationError(
                "source must be a PositionTargetTranslation"
            )
        source.to_dict()
        if type(side) is not ExecutionInstructionSide:
            raise ExecutionPlanningValidationError(
                "side must be an ExecutionInstructionSide"
            )
        value, text = require_retained_quantity(quantity, "quantity", delta=True)
        if value.is_zero() or value.is_signed():
            raise ExecutionPlanningValidationError("quantity must be positive")
        instrument_id = _canonical_id(source.canonical_instrument_id)
        source_fingerprint = required_fingerprint(
            source.fingerprint, "source_translation_fingerprint"
        )
        instrument_fingerprint = required_fingerprint(
            source.canonical_instrument_fingerprint, "canonical_instrument_fingerprint"
        )
        account_fingerprint = required_fingerprint(
            source.account_fingerprint, "account_fingerprint"
        )
        plan_as_of = canonical_plan_time(source.plan_as_of, "plan_as_of")
        state: tuple[object, ...] = (
            side.value,
            text,
            source_fingerprint,
            instrument_id.instrument_id,
            instrument_fingerprint,
            account_fingerprint,
            timestamp_text(plan_as_of),
            BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
        )
        result = object.__new__(cls)
        values: dict[str, object] = {
            "side": side,
            "quantity": value,
            "source_translation_fingerprint": source_fingerprint,
            "canonical_instrument_id": instrument_id,
            "canonical_instrument_fingerprint": instrument_fingerprint,
            "account_fingerprint": account_fingerprint,
            "plan_as_of": plan_as_of,
            "_source_translation": source,
            "_constructor_state": state,
            "_constructor_binding": (_BINDING_SENTINEL, state),
            "_token": _TOKEN,
            "schema_version": BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA,
        }
        for name, retained in values.items():
            object.__setattr__(result, name, retained)
        object.__setattr__(
            result, "fingerprint", canonical_fingerprint(result._fingerprint_payload())
        )
        result._validate()
        return result

    def _fingerprint_payload(self) -> dict[str, object]:
        _, text = require_retained_quantity(self.quantity, "quantity", delta=True)
        return {
            "schema_version": self.schema_version,
            "side": self.side.value,
            "quantity": text,
            "source_translation_fingerprint": self.source_translation_fingerprint,
            "canonical_instrument_id": self.canonical_instrument_id.to_dict(),
            "canonical_instrument_fingerprint": self.canonical_instrument_fingerprint,
            "account_fingerprint": self.account_fingerprint,
            "plan_as_of": timestamp_text(self.plan_as_of),
        }

    def _validate(self) -> None:
        names = (
            "_token",
            "_source_translation",
            "_constructor_state",
            "_constructor_binding",
            "side",
            "quantity",
            "source_translation_fingerprint",
            "canonical_instrument_id",
            "canonical_instrument_fingerprint",
            "account_fingerprint",
            "plan_as_of",
            "schema_version",
            "fingerprint",
        )
        retained = {
            name: required_retained_attribute(
                self, name, "broker-neutral execution instruction"
            )
            for name in names
        }
        if retained["_token"] is not _TOKEN:
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction construction token is invalid"
            )
        state, binding = (
            retained["_constructor_state"],
            retained["_constructor_binding"],
        )
        if (
            type(binding) is not tuple
            or len(cast(tuple[object, ...], binding)) != 2
            or cast(tuple[object, ...], binding)[0] is not _BINDING_SENTINEL
            or cast(tuple[object, ...], binding)[1] is not state
        ):
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction constructor binding is invalid"
            )
        if type(state) is not tuple or len(cast(tuple[object, ...], state)) != 8:
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction constructor state is invalid"
            )
        if cast(tuple[object, ...], state) != _state_projection(retained):
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction contradicts constructor state"
            )
        source = retained["_source_translation"]
        if type(source) is not PositionTargetTranslation:
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction source translation is invalid"
            )
        canonical_source = source
        canonical_source.to_dict()
        _require_source_correspondence(retained, canonical_source)
        if retained["schema_version"] != BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA:
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction schema_version is invalid"
            )
        if retained["fingerprint"] != canonical_fingerprint(
            self._fingerprint_payload()
        ):
            raise ExecutionPlanningCorrespondenceError(
                "execution instruction fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the constant-sized deterministic instruction projection."""
        self._validate()
        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


def derive_broker_neutral_execution_instruction(
    translation: PositionTargetTranslation,
) -> BrokerNeutralExecutionInstruction | None:
    """Derive zero or one non-executable instruction from one translation."""
    if type(translation) is not PositionTargetTranslation:
        raise ExecutionPlanningValidationError(
            "translation must be a PositionTargetTranslation"
        )
    translation.to_dict()
    if translation.schema_version != POSITION_TARGET_TRANSLATION_SCHEMA:
        raise ExecutionPlanningCorrespondenceError(
            "source translation schema_version is invalid"
        )
    if translation.action is PositionDeltaAction.NO_ACTION:
        return None
    side = (
        ExecutionInstructionSide.BUY
        if translation.action is PositionDeltaAction.BUY
        else ExecutionInstructionSide.SELL
        if translation.action is PositionDeltaAction.SELL
        else None
    )
    if side is None:
        raise ExecutionPlanningCorrespondenceError(
            "source translation action is invalid"
        )
    return BrokerNeutralExecutionInstruction._create(
        source=translation,
        side=side,
        quantity=_absolute_delta(translation.delta_quantity),
        token=_TOKEN,
    )


def _absolute_delta(value: object) -> Decimal:
    canonical, _ = require_retained_quantity(value, "delta_quantity", delta=True)
    state = canonical.as_tuple()
    if not isinstance(state.exponent, int):
        raise ExecutionPlanningCorrespondenceError(
            "source translation delta is not finite"
        )
    result = Decimal((0, state.digits, state.exponent))
    if result.is_zero():
        raise ExecutionPlanningCorrespondenceError(
            "actionable source translation delta must be nonzero"
        )
    return result


def _canonical_id(value: object) -> CanonicalInstrumentId:
    if type(value) is not CanonicalInstrumentId:
        raise ExecutionPlanningCorrespondenceError("canonical instrument ID is invalid")
    retained = value
    instrument_id = required_retained_attribute(
        retained, "instrument_id", "canonical instrument ID"
    )
    if type(instrument_id) is not str:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID is not canonical"
        )
    try:
        reconstructed = CanonicalInstrumentId(instrument_id)
    except (TypeError, ValueError) as error:
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID is not canonical"
        ) from error
    if retained.to_dict() != reconstructed.to_dict():
        raise ExecutionPlanningCorrespondenceError(
            "canonical instrument ID does not match reconstruction"
        )
    return reconstructed


def _state_projection(retained: dict[str, object]) -> tuple[object, ...]:
    side = retained["side"]
    if type(side) is not ExecutionInstructionSide:
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction side is invalid"
        )
    try:
        quantity, text = require_retained_quantity(
            retained["quantity"], "quantity", delta=True
        )
        source = required_fingerprint(
            retained["source_translation_fingerprint"], "source_translation_fingerprint"
        )
        instrument = required_fingerprint(
            retained["canonical_instrument_fingerprint"],
            "canonical_instrument_fingerprint",
        )
        account = required_fingerprint(
            retained["account_fingerprint"], "account_fingerprint"
        )
        plan_as_of = canonical_plan_time(retained["plan_as_of"], "plan_as_of")
    except ExecutionPlanningValidationError as error:
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction retains noncanonical state"
        ) from error
    if quantity.is_zero() or quantity.is_signed():
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction quantity must be positive"
        )
    instrument_id = _canonical_id(retained["canonical_instrument_id"])
    return (
        side.value,
        text,
        source,
        instrument_id.instrument_id,
        instrument,
        account,
        timestamp_text(plan_as_of),
        retained["schema_version"],
    )


def _require_source_correspondence(
    retained: dict[str, object], source: PositionTargetTranslation
) -> None:
    side = cast(ExecutionInstructionSide, retained["side"])
    expected_action = (
        PositionDeltaAction.BUY
        if side is ExecutionInstructionSide.BUY
        else PositionDeltaAction.SELL
    )
    if source.action is not expected_action:
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction side contradicts source translation"
        )
    expected_quantity = _absolute_delta(source.delta_quantity)
    actual_quantity, _ = require_retained_quantity(
        retained["quantity"], "quantity", delta=True
    )
    if actual_quantity.as_tuple() != expected_quantity.as_tuple():
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction quantity contradicts source translation"
        )
    if (
        _canonical_id(retained["canonical_instrument_id"]).to_dict()
        != _canonical_id(source.canonical_instrument_id).to_dict()
    ):
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction instrument contradicts source translation"
        )
    if (
        retained["source_translation_fingerprint"] != source.fingerprint
        or retained["canonical_instrument_fingerprint"]
        != source.canonical_instrument_fingerprint
        or retained["account_fingerprint"] != source.account_fingerprint
        or retained["plan_as_of"] != source.plan_as_of
    ):
        raise ExecutionPlanningCorrespondenceError(
            "execution instruction evidence contradicts source translation"
        )


__all__ = [
    "BROKER_NEUTRAL_EXECUTION_INSTRUCTION_SCHEMA",
    "BrokerNeutralExecutionInstruction",
    "ExecutionInstructionSide",
    "derive_broker_neutral_execution_instruction",
]
