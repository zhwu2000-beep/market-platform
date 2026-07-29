"""Deterministic pre-risk Order Intent construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from market_platform._fingerprint import canonical_fingerprint
from market_platform.trading._canonical import (
    canonical_decimal,
    canonical_timestamp,
    timestamp_text,
)
from market_platform.trading.instrument import TradingInstrumentIdentity
from market_platform.trading.policy import ExactTargetPositionIntentPolicy
from market_platform.trading.signal import (
    TradingSignal,
    TradingSignalTemporalStatus,
    TradingTargetPosition,
    evaluate_trading_signal_temporal_status,
)

ORDER_INTENT_SCHEMA_VERSION = "order_intent/v1"


class TradingSignalTemporalError(ValueError):
    """Base error for deterministic signal temporal inapplicability."""


class TradingSignalNotYetValidError(TradingSignalTemporalError):
    """Raised when conversion is attempted before signal validity."""


class TradingSignalExpiredError(TradingSignalTemporalError):
    """Raised when conversion is attempted at or after signal expiry."""


@dataclass(frozen=True, slots=True, init=False)
class OrderIntent:
    """Immutable pre-risk target-position proposal."""

    source_signal: TradingSignal = field(repr=False)
    policy: ExactTargetPositionIntentPolicy = field(repr=False)
    decision_as_of: datetime
    valid_from: datetime
    expires_at: datetime
    schema_version: str
    intent_fingerprint: str

    def __init__(self) -> None:
        raise TypeError(
            "OrderIntent must be created with create_order_intent_from_signal()"
        )

    @classmethod
    def _create(
        cls,
        *,
        source_signal: TradingSignal,
        policy: ExactTargetPositionIntentPolicy,
        decision_as_of: datetime,
    ) -> OrderIntent:
        if not isinstance(source_signal, TradingSignal):
            raise TypeError("source_signal must be a TradingSignal")
        if not isinstance(policy, ExactTargetPositionIntentPolicy):
            raise TypeError("policy must be an ExactTargetPositionIntentPolicy")
        canonical_as_of = canonical_timestamp(decision_as_of, "decision_as_of")
        _raise_for_inactive_signal(source_signal, canonical_as_of)
        canonical_expiry = _require_canonical_utc_datetime(
            source_signal.expires_at,
            "source_signal.expires_at",
        )

        intent = object.__new__(cls)
        object.__setattr__(intent, "source_signal", source_signal)
        object.__setattr__(intent, "policy", policy)
        object.__setattr__(intent, "decision_as_of", canonical_as_of)
        object.__setattr__(intent, "valid_from", canonical_as_of)
        object.__setattr__(intent, "expires_at", canonical_expiry)
        object.__setattr__(intent, "schema_version", ORDER_INTENT_SCHEMA_VERSION)
        object.__setattr__(
            intent,
            "intent_fingerprint",
            canonical_fingerprint(intent._fingerprint_payload()),
        )
        intent._validate()
        return intent

    @property
    def source_signal_fingerprint(self) -> str:
        return self.source_signal.signal_fingerprint

    @property
    def source_idempotency_key(self) -> str:
        return self.source_signal.idempotency_key

    @property
    def instrument(self) -> TradingInstrumentIdentity:
        return self.source_signal.instrument

    @property
    def target_position(self) -> TradingTargetPosition:
        return self.source_signal.target_position

    @property
    def target_units(self) -> Decimal:
        return self.source_signal.target_units

    @property
    def policy_fingerprint(self) -> str:
        return self.policy.policy_fingerprint

    def _fingerprint_payload(self) -> dict[str, object]:
        _, target_units_text = canonical_decimal(self.target_units, "target_units")
        return {
            "schema_version": self.schema_version,
            "source_signal_fingerprint": self.source_signal_fingerprint,
            "source_idempotency_key": self.source_idempotency_key,
            "instrument": {
                "schema_version": self.instrument.schema_version,
                "symbol": self.instrument.symbol,
                "venue": self.instrument.venue,
            },
            "target_position": self.target_position.value,
            "target_units": target_units_text,
            "policy_fingerprint": self.policy_fingerprint,
            "decision_as_of": timestamp_text(self.decision_as_of),
            "valid_from": timestamp_text(self.valid_from),
            "expires_at": timestamp_text(self.expires_at),
        }

    def _validate(self) -> None:
        if not isinstance(self.source_signal, TradingSignal):
            raise TypeError("source_signal must be a TradingSignal")
        if not isinstance(self.policy, ExactTargetPositionIntentPolicy):
            raise TypeError("policy must be an ExactTargetPositionIntentPolicy")
        decision_as_of = _require_canonical_utc_datetime(
            self.decision_as_of,
            "decision_as_of",
        )
        valid_from = _require_canonical_utc_datetime(
            self.valid_from,
            "valid_from",
        )
        expires_at = _require_canonical_utc_datetime(
            self.expires_at,
            "expires_at",
        )
        source_valid_from = _require_canonical_utc_datetime(
            self.source_signal.valid_from,
            "source_signal.valid_from",
        )
        source_expires_at = _require_canonical_utc_datetime(
            self.source_signal.expires_at,
            "source_signal.expires_at",
        )
        if valid_from != decision_as_of:
            raise ValueError("valid_from must equal decision_as_of")
        if expires_at != source_expires_at:
            raise ValueError("expires_at must equal source signal expiry")
        if decision_as_of < source_valid_from:
            raise ValueError("decision_as_of must not precede signal validity")
        if decision_as_of >= source_expires_at:
            raise ValueError("decision_as_of must be earlier than signal expiry")
        if self.schema_version != ORDER_INTENT_SCHEMA_VERSION:
            raise ValueError("OrderIntent schema_version is invalid")
        expected_fingerprint = canonical_fingerprint(self._fingerprint_payload())
        if self.intent_fingerprint != expected_fingerprint:
            raise ValueError("intent_fingerprint must match OrderIntent content")

    def to_dict(self) -> dict[str, object]:
        """Return a bounded deterministic JSON-safe intent summary."""

        _, target_units_text = canonical_decimal(self.target_units, "target_units")
        return {
            "schema_version": self.schema_version,
            "source_signal_fingerprint": self.source_signal_fingerprint,
            "source_idempotency_key": self.source_idempotency_key,
            "instrument": self.instrument.to_dict(),
            "target_position": self.target_position.value,
            "target_units": target_units_text,
            "policy_fingerprint": self.policy_fingerprint,
            "decision_as_of": timestamp_text(self.decision_as_of),
            "valid_from": timestamp_text(self.valid_from),
            "expires_at": timestamp_text(self.expires_at),
            "intent_fingerprint": self.intent_fingerprint,
        }


def create_order_intent_from_signal(
    signal: TradingSignal,
    policy: ExactTargetPositionIntentPolicy,
    as_of: datetime,
) -> OrderIntent:
    """Create one exact-target Order Intent from an active signal."""

    if not isinstance(signal, TradingSignal):
        raise TypeError("signal must be a TradingSignal")
    if not isinstance(policy, ExactTargetPositionIntentPolicy):
        raise TypeError("policy must be an ExactTargetPositionIntentPolicy")
    decision_as_of = canonical_timestamp(as_of, "as_of")
    status = evaluate_trading_signal_temporal_status(signal, decision_as_of)
    if status is TradingSignalTemporalStatus.NOT_YET_VALID:
        raise TradingSignalNotYetValidError(
            "signal "
            f"{signal.signal_fingerprint} is not yet valid at "
            f"{timestamp_text(decision_as_of)}"
        )
    if status is TradingSignalTemporalStatus.EXPIRED:
        raise TradingSignalExpiredError(
            "signal "
            f"{signal.signal_fingerprint} is expired at "
            f"{timestamp_text(decision_as_of)}"
        )
    return OrderIntent._create(
        source_signal=signal,
        policy=policy,
        decision_as_of=decision_as_of,
    )


def _raise_for_inactive_signal(
    signal: TradingSignal,
    decision_as_of: datetime,
) -> None:
    status = evaluate_trading_signal_temporal_status(signal, decision_as_of)
    if status is TradingSignalTemporalStatus.NOT_YET_VALID:
        raise TradingSignalNotYetValidError(
            "signal "
            f"{signal.signal_fingerprint} is not yet valid at "
            f"{timestamp_text(decision_as_of)}"
        )
    if status is TradingSignalTemporalStatus.EXPIRED:
        raise TradingSignalExpiredError(
            "signal "
            f"{signal.signal_fingerprint} is expired at "
            f"{timestamp_text(decision_as_of)}"
        )


def _require_canonical_utc_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    canonical_value = canonical_timestamp(value, field_name)
    if value.tzinfo is not UTC:
        raise ValueError(f"{field_name} must use canonical UTC")
    if value.isoformat() != canonical_value.isoformat():
        raise ValueError(f"{field_name} must use canonical UTC")
    return canonical_value


__all__ = [
    "ORDER_INTENT_SCHEMA_VERSION",
    "OrderIntent",
    "TradingSignalExpiredError",
    "TradingSignalNotYetValidError",
    "TradingSignalTemporalError",
    "create_order_intent_from_signal",
]
