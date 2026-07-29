"""Immutable source-attributed trading signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.trading._canonical import (
    canonical_decimal,
    canonical_timestamp,
    optional_fingerprint,
    required_text,
    timestamp_text,
)
from market_platform.trading.instrument import TradingInstrumentIdentity

TRADING_SIGNAL_SOURCE_SCHEMA_VERSION = "trading_signal_source/v1"
TRADING_SIGNAL_SCHEMA_VERSION = "trading_signal/v1"
_TRADING_SIGNAL_IDEMPOTENCY_SCHEMA_VERSION = "trading_signal_idempotency/v1"


class TradingTargetPosition(StrEnum):
    """Exact target-position direction, independent of transaction side."""

    LONG = "long"
    FLAT = "flat"
    SHORT = "short"


class TradingSignalTemporalStatus(StrEnum):
    """Temporal applicability of a trading signal."""

    NOT_YET_VALID = "not_yet_valid"
    ACTIVE = "active"
    EXPIRED = "expired"


class TradingSignalEventConsistency(StrEnum):
    """Relationship between two source events."""

    IDENTICAL = "identical"
    CONFLICTING_CONTENT = "conflicting_content"
    UNRELATED = "unrelated"


@dataclass(frozen=True, slots=True)
class TradingSignalSourceIdentity:
    """Stable identity of one trading-signal producer configuration."""

    source_id: str = field(repr=False)
    source_version: str = field(repr=False)
    configuration_fingerprint: str | None = None
    schema_version: str = field(
        init=False,
        default=TRADING_SIGNAL_SOURCE_SCHEMA_VERSION,
    )
    source_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        source_id = required_text(
            self.source_id,
            "source_id",
            reject_surrounding_whitespace=True,
        )
        source_version = required_text(
            self.source_version,
            "source_version",
            reject_surrounding_whitespace=True,
        )
        configuration_fingerprint = optional_fingerprint(
            self.configuration_fingerprint,
            "configuration_fingerprint",
        )
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "source_version", source_version)
        object.__setattr__(
            self,
            "configuration_fingerprint",
            configuration_fingerprint,
        )
        object.__setattr__(
            self,
            "source_fingerprint",
            canonical_fingerprint(
                {
                    "schema_version": self.schema_version,
                    "source_id": source_id,
                    "source_version": source_version,
                    "configuration_fingerprint": configuration_fingerprint,
                }
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-safe source projection."""

        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "configuration_fingerprint": self.configuration_fingerprint,
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class TradingSignal:
    """One canonical recommendation for an exact target position."""

    source: TradingSignalSourceIdentity = field(repr=False)
    source_event_id: str = field(repr=False)
    instrument: TradingInstrumentIdentity
    timeframe: str | None
    target_position: TradingTargetPosition
    target_units: Decimal
    generated_at: datetime
    valid_from: datetime
    expires_at: datetime
    schema_version: str = field(init=False, default=TRADING_SIGNAL_SCHEMA_VERSION)
    idempotency_key: str = field(init=False)
    signal_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source, TradingSignalSourceIdentity):
            raise TypeError("source must be a TradingSignalSourceIdentity")
        source_event_id = required_text(
            self.source_event_id,
            "source_event_id",
            reject_surrounding_whitespace=True,
        )
        if not isinstance(self.instrument, TradingInstrumentIdentity):
            raise TypeError("instrument must be a TradingInstrumentIdentity")
        timeframe = (
            None
            if self.timeframe is None
            else required_text(self.timeframe, "timeframe")
        )
        if not isinstance(self.target_position, TradingTargetPosition):
            raise TypeError("target_position must be a TradingTargetPosition")
        target_units, target_units_text = canonical_decimal(
            self.target_units,
            "target_units",
        )
        _validate_target_units(self.target_position, target_units)
        generated_at = canonical_timestamp(self.generated_at, "generated_at")
        valid_from = canonical_timestamp(self.valid_from, "valid_from")
        expires_at = canonical_timestamp(self.expires_at, "expires_at")
        if generated_at > valid_from:
            raise ValueError(
                "generated_at must be earlier than or equal to valid_from"
            )
        if valid_from >= expires_at:
            raise ValueError("valid_from must be earlier than expires_at")

        object.__setattr__(self, "source_event_id", source_event_id)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "target_units", target_units)
        object.__setattr__(self, "generated_at", generated_at)
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(
            self,
            "idempotency_key",
            canonical_fingerprint(
                {
                    "schema_version": _TRADING_SIGNAL_IDEMPOTENCY_SCHEMA_VERSION,
                    "source_fingerprint": self.source.source_fingerprint,
                    "source_event_id": source_event_id,
                }
            ),
        )
        object.__setattr__(
            self,
            "signal_fingerprint",
            canonical_fingerprint(
                self._fingerprint_payload(target_units_text)
            ),
        )

    def _fingerprint_payload(self, target_units_text: str) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": _source_identity_payload(self.source),
            "source_fingerprint": self.source.source_fingerprint,
            "source_event_id": self.source_event_id,
            "instrument": _instrument_identity_payload(self.instrument),
            "timeframe": self.timeframe,
            "target_position": self.target_position.value,
            "target_units": target_units_text,
            "generated_at": timestamp_text(self.generated_at),
            "valid_from": timestamp_text(self.valid_from),
            "expires_at": timestamp_text(self.expires_at),
        }

    def to_dict(self) -> dict[str, object]:
        """Return deterministic canonical signal content and identities."""

        _, target_units_text = canonical_decimal(self.target_units, "target_units")
        return {
            "schema_version": self.schema_version,
            "source": self.source.to_dict(),
            "source_event_id": self.source_event_id,
            "idempotency_key": self.idempotency_key,
            "instrument": self.instrument.to_dict(),
            "timeframe": self.timeframe,
            "target_position": self.target_position.value,
            "target_units": target_units_text,
            "generated_at": timestamp_text(self.generated_at),
            "valid_from": timestamp_text(self.valid_from),
            "expires_at": timestamp_text(self.expires_at),
            "signal_fingerprint": self.signal_fingerprint,
        }


def evaluate_trading_signal_temporal_status(
    signal: TradingSignal,
    as_of: datetime,
) -> TradingSignalTemporalStatus:
    """Evaluate signal validity at an explicit caller-supplied instant."""

    if not isinstance(signal, TradingSignal):
        raise TypeError("signal must be a TradingSignal")
    normalized_as_of = canonical_timestamp(as_of, "as_of")
    if normalized_as_of < signal.valid_from:
        return TradingSignalTemporalStatus.NOT_YET_VALID
    if normalized_as_of >= signal.expires_at:
        return TradingSignalTemporalStatus.EXPIRED
    return TradingSignalTemporalStatus.ACTIVE


def compare_trading_signal_event_consistency(
    first: TradingSignal,
    second: TradingSignal,
) -> TradingSignalEventConsistency:
    """Classify two signals without persistence or mutation."""

    if not isinstance(first, TradingSignal):
        raise TypeError("first must be a TradingSignal")
    if not isinstance(second, TradingSignal):
        raise TypeError("second must be a TradingSignal")
    if first.idempotency_key != second.idempotency_key:
        return TradingSignalEventConsistency.UNRELATED
    if first.signal_fingerprint == second.signal_fingerprint:
        return TradingSignalEventConsistency.IDENTICAL
    return TradingSignalEventConsistency.CONFLICTING_CONTENT


def _validate_target_units(
    target_position: TradingTargetPosition,
    target_units: Decimal,
) -> None:
    if target_position is TradingTargetPosition.FLAT:
        if not target_units.is_zero():
            raise ValueError("flat target_units must be zero")
        return
    if target_units <= 0:
        raise ValueError("long and short target_units must be greater than zero")


def _source_identity_payload(
    source: TradingSignalSourceIdentity,
) -> dict[str, object]:
    return {
        "schema_version": source.schema_version,
        "source_id": source.source_id,
        "source_version": source.source_version,
        "configuration_fingerprint": source.configuration_fingerprint,
    }


def _instrument_identity_payload(
    instrument: TradingInstrumentIdentity,
) -> dict[str, object]:
    return {
        "schema_version": instrument.schema_version,
        "symbol": instrument.symbol,
        "venue": instrument.venue,
    }


__all__ = [
    "TRADING_SIGNAL_SCHEMA_VERSION",
    "TRADING_SIGNAL_SOURCE_SCHEMA_VERSION",
    "TradingSignal",
    "TradingSignalEventConsistency",
    "TradingSignalSourceIdentity",
    "TradingSignalTemporalStatus",
    "TradingTargetPosition",
    "compare_trading_signal_event_consistency",
    "evaluate_trading_signal_temporal_status",
]
