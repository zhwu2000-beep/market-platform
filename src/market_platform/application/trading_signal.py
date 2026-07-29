"""Immutable inputs, requests, and responses for trading-signal operations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from market_platform._fingerprint import canonical_fingerprint
from market_platform.application.errors import (
    TradingApplicationCorrespondenceError,
    TradingApplicationRequestError,
    TradingApplicationResourceLimitError,
)
from market_platform.trading import (
    EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION,
    ORDER_INTENT_SCHEMA_VERSION,
    TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
    TRADING_SIGNAL_SCHEMA_VERSION,
    TRADING_SIGNAL_SOURCE_SCHEMA_VERSION,
    ExactTargetPositionIntentPolicy,
    OrderIntent,
    TradingInstrumentIdentity,
    TradingSignal,
    TradingTargetPosition,
)

TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION = (
    "trading_signal_application_request/v1"
)
TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION = (
    "trading_signal_application_response/v1"
)
ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION = "order_intent_application_request/v1"
ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION = (
    "order_intent_application_response/v1"
)

_TRADING_SIGNAL_IDEMPOTENCY_SCHEMA_VERSION = "trading_signal_idempotency/v1"
_EXACT_TARGET_POLICY_METHODOLOGY = "exact_target_position"
_EXACT_TARGET_POLICY_VERSION = "1.0.0"
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

_SOURCE_ID_LIMIT = 128
_SOURCE_VERSION_LIMIT = 64
_SOURCE_EVENT_ID_LIMIT = 256
_SYMBOL_LIMIT = 64
_VENUE_LIMIT = 32
_TIMEFRAME_LIMIT = 32
_TIMESTAMP_TEXT_LIMIT = 64
_DECIMAL_TEXT_LIMIT = 256
_DECIMAL_DIGIT_LIMIT = 128
_DECIMAL_FRACTIONAL_DIGIT_LIMIT = 64
_FIXED_POLICY_FINGERPRINT = canonical_fingerprint(
    {
        "schema_version": EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION,
        "methodology": _EXACT_TARGET_POLICY_METHODOLOGY,
        "version": _EXACT_TARGET_POLICY_VERSION,
        "configuration": {},
    }
)


@dataclass(frozen=True, slots=True)
class TradingSignalSourceApplicationInput:
    """Normalized passive source identity input."""

    source_id: str = field(repr=False)
    source_version: str = field(repr=False)
    configuration_fingerprint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _visible_ascii_text(self.source_id, "source_id", _SOURCE_ID_LIMIT),
        )
        object.__setattr__(
            self,
            "source_version",
            _visible_ascii_text(
                self.source_version,
                "source_version",
                _SOURCE_VERSION_LIMIT,
            ),
        )
        object.__setattr__(
            self,
            "configuration_fingerprint",
            _optional_fingerprint(
                self.configuration_fingerprint,
                "configuration_fingerprint",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "configuration_fingerprint": self.configuration_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class TradingInstrumentApplicationInput:
    """Normalized canonical symbol and venue input."""

    symbol: str
    venue: str

    def __post_init__(self) -> None:
        symbol = _visible_ascii_text(self.symbol, "symbol", _SYMBOL_LIMIT)
        venue = _visible_ascii_text(self.venue, "venue", _VENUE_LIMIT)
        if ":" in symbol:
            raise TradingApplicationRequestError(
                "symbol must not include a venue prefix separated by ':'"
            )
        instrument = TradingInstrumentIdentity(symbol=symbol, venue=venue)
        object.__setattr__(self, "symbol", instrument.symbol)
        object.__setattr__(self, "venue", instrument.venue)

    def to_dict(self) -> dict[str, object]:
        return {"symbol": self.symbol, "venue": self.venue}


@dataclass(frozen=True, slots=True)
class TradingTargetPositionApplicationInput:
    """Normalized exact target-position input."""

    position: TradingTargetPosition
    units: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.position, TradingTargetPosition):
            raise TradingApplicationRequestError(
                "target.position must be a TradingTargetPosition"
            )
        units, _ = _canonical_decimal(self.units, "target.units")
        if self.position is TradingTargetPosition.FLAT:
            if not units.is_zero():
                raise TradingApplicationRequestError("flat target.units must be zero")
        elif units <= 0:
            raise TradingApplicationRequestError(
                "long and short target.units must be greater than zero"
            )
        object.__setattr__(self, "units", units)

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position.value,
            "units": _canonical_decimal_text(self.units),
        }


@dataclass(frozen=True, slots=True)
class TradingSignalApplicationInput:
    """Complete normalized semantic input for one TradingSignal."""

    source: TradingSignalSourceApplicationInput = field(repr=False)
    source_event_id: str = field(repr=False)
    instrument: TradingInstrumentApplicationInput
    timeframe: str | None
    target: TradingTargetPositionApplicationInput
    generated_at: datetime
    valid_from: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.source, TradingSignalSourceApplicationInput):
            raise TradingApplicationRequestError(
                "signal.source must be a TradingSignalSourceApplicationInput"
            )
        if not isinstance(self.instrument, TradingInstrumentApplicationInput):
            raise TradingApplicationRequestError(
                "signal.instrument must be a TradingInstrumentApplicationInput"
            )
        if not isinstance(self.target, TradingTargetPositionApplicationInput):
            raise TradingApplicationRequestError(
                "signal.target must be a TradingTargetPositionApplicationInput"
            )
        source_event_id = _visible_ascii_text(
            self.source_event_id,
            "source_event_id",
            _SOURCE_EVENT_ID_LIMIT,
        )
        timeframe = (
            None
            if self.timeframe is None
            else _visible_ascii_text(
                self.timeframe,
                "timeframe",
                _TIMEFRAME_LIMIT,
            )
        )
        generated_at = _canonical_timestamp(self.generated_at, "generated_at")
        valid_from = _canonical_timestamp(self.valid_from, "valid_from")
        expires_at = _canonical_timestamp(self.expires_at, "expires_at")
        if generated_at > valid_from:
            raise TradingApplicationRequestError(
                "generated_at must be earlier than or equal to valid_from"
            )
        if valid_from >= expires_at:
            raise TradingApplicationRequestError(
                "valid_from must be earlier than expires_at"
            )
        object.__setattr__(self, "source_event_id", source_event_id)
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "generated_at", generated_at)
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "expires_at", expires_at)

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "source": self.source.to_dict(),
            "source_event_id": self.source_event_id,
            "instrument": self.instrument.to_dict(),
            "timeframe": self.timeframe,
            "target": self.target.to_dict(),
            "generated_at": _timestamp_text(self.generated_at),
            "valid_from": _timestamp_text(self.valid_from),
            "expires_at": _timestamp_text(self.expires_at),
        }

    def to_dict(self) -> dict[str, object]:
        return self._fingerprint_payload()


@dataclass(frozen=True, slots=True)
class TradingSignalApplicationRequest:
    """Normalized application request to create one TradingSignal."""

    signal: TradingSignalApplicationInput = field(repr=False)
    schema_version: str = field(
        init=False,
        default=TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION,
    )
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.signal, TradingSignalApplicationInput):
            raise TradingApplicationRequestError(
                "signal must be a TradingSignalApplicationInput"
            )
        object.__setattr__(
            self,
            "request_fingerprint",
            canonical_fingerprint(
                {
                    "schema_version": self.schema_version,
                    "signal": self.signal._fingerprint_payload(),
                }
            ),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> TradingSignalApplicationRequest:
        from market_platform.application.trading_signal_codec import (
            decode_trading_signal_application_request,
        )

        return decode_trading_signal_application_request(payload)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "signal": self.signal.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class OrderIntentApplicationRequest:
    """Normalized application request to create one pre-risk OrderIntent."""

    signal: TradingSignalApplicationInput = field(repr=False)
    decision_as_of: datetime
    schema_version: str = field(
        init=False,
        default=ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION,
    )
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.signal, TradingSignalApplicationInput):
            raise TradingApplicationRequestError(
                "signal must be a TradingSignalApplicationInput"
            )
        decision_as_of = _canonical_timestamp(
            self.decision_as_of,
            "decision_as_of",
        )
        object.__setattr__(self, "decision_as_of", decision_as_of)
        object.__setattr__(
            self,
            "request_fingerprint",
            canonical_fingerprint(
                {
                    "schema_version": self.schema_version,
                    "signal": self.signal._fingerprint_payload(),
                    "decision_as_of": _timestamp_text(decision_as_of),
                    "policy_fingerprint": _FIXED_POLICY_FINGERPRINT,
                }
            ),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> OrderIntentApplicationRequest:
        from market_platform.application.trading_signal_codec import (
            decode_order_intent_application_request,
        )

        return decode_order_intent_application_request(payload)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "signal": self.signal.to_dict(),
            "decision_as_of": _timestamp_text(self.decision_as_of),
        }


@dataclass(frozen=True, slots=True, init=False)
class CreateTradingSignalApplicationResponse:
    """Factory-only response retaining one complete TradingSignal."""

    request_fingerprint: str
    signal: TradingSignal = field(repr=False)
    schema_version: str

    def __init__(self) -> None:
        raise TypeError(
            "CreateTradingSignalApplicationResponse is created by "
            "CreateTradingSignalApplicationService.execute()"
        )

    @classmethod
    def _create(
        cls,
        request: TradingSignalApplicationRequest,
        signal: TradingSignal,
    ) -> CreateTradingSignalApplicationResponse:
        if not isinstance(request, TradingSignalApplicationRequest):
            raise TypeError("request must be a TradingSignalApplicationRequest")
        if not isinstance(signal, TradingSignal):
            raise TypeError("signal must be a TradingSignal")
        if (
            request.schema_version != TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION
            or request.request_fingerprint
            != _signal_request_fingerprint(request.signal)
        ):
            raise TradingApplicationCorrespondenceError(
                "request_fingerprint does not match the signal request"
            )
        _validate_signal_correspondence(request.signal, signal)
        instance = cls.__new__(cls)
        object.__setattr__(
            instance,
            "request_fingerprint",
            request.request_fingerprint,
        )
        object.__setattr__(instance, "signal", signal)
        object.__setattr__(
            instance,
            "schema_version",
            TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION,
        )
        return instance

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_fingerprint": self.request_fingerprint,
            "signal": self.signal.to_dict(),
        }


@dataclass(frozen=True, slots=True, init=False)
class CreateOrderIntentApplicationResponse:
    """Factory-only response retaining one complete pre-risk OrderIntent."""

    request_fingerprint: str
    intent: OrderIntent = field(repr=False)
    schema_version: str

    def __init__(self) -> None:
        raise TypeError(
            "CreateOrderIntentApplicationResponse is created by "
            "CreateOrderIntentApplicationService.execute()"
        )

    @classmethod
    def _create(
        cls,
        request: OrderIntentApplicationRequest,
        intent: OrderIntent,
    ) -> CreateOrderIntentApplicationResponse:
        if not isinstance(request, OrderIntentApplicationRequest):
            raise TypeError("request must be an OrderIntentApplicationRequest")
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be an OrderIntent")
        if (
            request.schema_version != ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION
            or request.request_fingerprint != _intent_request_fingerprint(request)
        ):
            raise TradingApplicationCorrespondenceError(
                "request_fingerprint does not match the intent request"
            )
        _validate_intent_correspondence(request, intent)
        instance = cls.__new__(cls)
        object.__setattr__(
            instance,
            "request_fingerprint",
            request.request_fingerprint,
        )
        object.__setattr__(instance, "intent", intent)
        object.__setattr__(
            instance,
            "schema_version",
            ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION,
        )
        return instance

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_fingerprint": self.request_fingerprint,
            "signal": self.intent.source_signal.to_dict(),
            "intent": self.intent.to_dict(),
        }


def _visible_ascii_text(value: object, field_name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise TradingApplicationRequestError(f"{field_name} must be a string")
    if len(value) > limit:
        raise TradingApplicationResourceLimitError(
            f"{field_name} exceeds limit {limit}; observed length {len(value)}"
        )
    if not value:
        raise TradingApplicationRequestError(f"{field_name} must not be empty")
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise TradingApplicationRequestError(
            f"{field_name} must contain visible ASCII without whitespace"
        )
    return value


def _optional_fingerprint(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise TradingApplicationRequestError(
            f"{field_name} must be a sha256 fingerprint or null"
        )
    return value


def _canonical_decimal(
    value: object,
    field_name: str,
) -> tuple[Decimal, str]:
    if type(value) is not Decimal:
        raise TradingApplicationRequestError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise TradingApplicationRequestError(f"{field_name} must be finite")
    if value.is_zero() and value.is_signed():
        raise TradingApplicationRequestError(f"{field_name} must not be negative zero")
    if value < 0:
        raise TradingApplicationRequestError(f"{field_name} must not be negative")
    if value.is_zero():
        return Decimal("0"), "0"
    digit_count, fractional_digit_count, text_length = (
        _project_canonical_decimal_size(value)
    )
    if digit_count > _DECIMAL_DIGIT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{field_name} exceeds digit limit {_DECIMAL_DIGIT_LIMIT}; "
            f"observed digits {digit_count}"
        )
    if fractional_digit_count > _DECIMAL_FRACTIONAL_DIGIT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{field_name} exceeds fractional digit limit "
            f"{_DECIMAL_FRACTIONAL_DIGIT_LIMIT}; "
            f"observed fractional digits {fractional_digit_count}"
        )
    if text_length > _DECIMAL_TEXT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{field_name} exceeds limit {_DECIMAL_TEXT_LIMIT}; "
            f"observed length {text_length}"
        )
    text = _fixed_point_decimal_text(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return Decimal(text), text


def _project_canonical_decimal_size(value: Decimal) -> tuple[int, int, int]:
    decimal_tuple = value.as_tuple()
    digits = decimal_tuple.digits
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise TradingApplicationRequestError("target.units must be finite")
    trailing_zero_count = 0
    for digit in reversed(digits):
        if digit != 0:
            break
        trailing_zero_count += 1
    canonical_digit_count = len(digits) - trailing_zero_count
    canonical_exponent = exponent + trailing_zero_count
    if canonical_exponent >= 0:
        output_digit_count = canonical_digit_count + canonical_exponent
        return output_digit_count, 0, output_digit_count
    fractional_digit_count = -canonical_exponent
    decimal_position = canonical_digit_count + canonical_exponent
    integer_digit_count = max(decimal_position, 1)
    output_digit_count = integer_digit_count + fractional_digit_count
    return output_digit_count, fractional_digit_count, output_digit_count + 1


def _fixed_point_decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _canonical_decimal_text(value: Decimal) -> str:
    return _canonical_decimal(value, "target.units")[1]


def _canonical_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TradingApplicationRequestError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TradingApplicationRequestError(f"{field_name} must be timezone-aware")
    normalized = value.astimezone(UTC)
    text = normalized.isoformat()
    if len(text) > _TIMESTAMP_TEXT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{field_name} exceeds limit {_TIMESTAMP_TEXT_LIMIT}; "
            f"observed length {len(text)}"
        )
    return normalized


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _source_fingerprint(signal: TradingSignalApplicationInput) -> str:
    return canonical_fingerprint(
        {
            "schema_version": TRADING_SIGNAL_SOURCE_SCHEMA_VERSION,
            **signal.source.to_dict(),
        }
    )


def _instrument_fingerprint(signal: TradingSignalApplicationInput) -> str:
    return canonical_fingerprint(
        {
            "schema_version": TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
            **signal.instrument.to_dict(),
        }
    )


def _idempotency_key(signal: TradingSignalApplicationInput) -> str:
    return canonical_fingerprint(
        {
            "schema_version": _TRADING_SIGNAL_IDEMPOTENCY_SCHEMA_VERSION,
            "source_fingerprint": _source_fingerprint(signal),
            "source_event_id": signal.source_event_id,
        }
    )


def _signal_request_fingerprint(signal: TradingSignalApplicationInput) -> str:
    return canonical_fingerprint(
        {
            "schema_version": TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION,
            "signal": signal._fingerprint_payload(),
        }
    )


def _intent_request_fingerprint(request: OrderIntentApplicationRequest) -> str:
    return canonical_fingerprint(
        {
            "schema_version": ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION,
            "signal": request.signal._fingerprint_payload(),
            "decision_as_of": _timestamp_text(request.decision_as_of),
            "policy_fingerprint": _FIXED_POLICY_FINGERPRINT,
        }
    )


def _signal_fingerprint(signal: TradingSignalApplicationInput) -> str:
    return canonical_fingerprint(
        {
            "schema_version": TRADING_SIGNAL_SCHEMA_VERSION,
            "source": {
                "schema_version": TRADING_SIGNAL_SOURCE_SCHEMA_VERSION,
                **signal.source.to_dict(),
            },
            "source_fingerprint": _source_fingerprint(signal),
            "source_event_id": signal.source_event_id,
            "instrument": {
                "schema_version": TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION,
                **signal.instrument.to_dict(),
            },
            "timeframe": signal.timeframe,
            "target_position": signal.target.position.value,
            "target_units": _canonical_decimal_text(signal.target.units),
            "generated_at": _timestamp_text(signal.generated_at),
            "valid_from": _timestamp_text(signal.valid_from),
            "expires_at": _timestamp_text(signal.expires_at),
        }
    )


def _validate_signal_correspondence(
    requested: TradingSignalApplicationInput,
    actual: TradingSignal,
) -> None:
    _require_exact_canonical_decimal_correspondence(
        actual.target_units,
        requested.target.units,
        "TradingSignal.target_units",
    )
    if (
        actual.schema_version != TRADING_SIGNAL_SCHEMA_VERSION
        or actual.source.schema_version != TRADING_SIGNAL_SOURCE_SCHEMA_VERSION
        or actual.source.source_id != requested.source.source_id
        or actual.source.source_version != requested.source.source_version
        or actual.source.configuration_fingerprint
        != requested.source.configuration_fingerprint
        or actual.source.source_fingerprint != _source_fingerprint(requested)
        or actual.source_event_id != requested.source_event_id
        or actual.instrument.schema_version
        != TRADING_INSTRUMENT_IDENTITY_SCHEMA_VERSION
        or actual.instrument.symbol != requested.instrument.symbol
        or actual.instrument.venue != requested.instrument.venue
        or actual.instrument.instrument_fingerprint
        != _instrument_fingerprint(requested)
        or actual.timeframe != requested.timeframe
        or actual.target_position is not requested.target.position
        or actual.generated_at != requested.generated_at
        or actual.valid_from != requested.valid_from
        or actual.expires_at != requested.expires_at
        or requested.generated_at.tzinfo is not UTC
        or requested.valid_from.tzinfo is not UTC
        or requested.expires_at.tzinfo is not UTC
        or actual.generated_at.tzinfo is not UTC
        or actual.valid_from.tzinfo is not UTC
        or actual.expires_at.tzinfo is not UTC
        or actual.idempotency_key != _idempotency_key(requested)
        or actual.signal_fingerprint != _signal_fingerprint(requested)
    ):
        raise TradingApplicationCorrespondenceError(
            "TradingSignal does not correspond to the application request"
        )


def _intent_fingerprint(intent: OrderIntent) -> str:
    return canonical_fingerprint(
        {
            "schema_version": ORDER_INTENT_SCHEMA_VERSION,
            "source_signal_fingerprint": intent.source_signal_fingerprint,
            "source_idempotency_key": intent.source_idempotency_key,
            "instrument": {
                "schema_version": intent.instrument.schema_version,
                "symbol": intent.instrument.symbol,
                "venue": intent.instrument.venue,
            },
            "target_position": intent.target_position.value,
            "target_units": _canonical_decimal_text(intent.target_units),
            "policy_fingerprint": intent.policy_fingerprint,
            "decision_as_of": _timestamp_text(intent.decision_as_of),
            "valid_from": _timestamp_text(intent.valid_from),
            "expires_at": _timestamp_text(intent.expires_at),
        }
    )


def _validate_intent_correspondence(
    request: OrderIntentApplicationRequest,
    intent: OrderIntent,
) -> None:
    _validate_signal_correspondence(request.signal, intent.source_signal)
    _require_exact_canonical_decimal_correspondence(
        intent.target_units,
        request.signal.target.units,
        "OrderIntent.target_units",
    )
    if (
        intent.schema_version != ORDER_INTENT_SCHEMA_VERSION
        or not isinstance(intent.policy, ExactTargetPositionIntentPolicy)
        or intent.policy.schema_version
        != EXACT_TARGET_POSITION_INTENT_POLICY_SCHEMA_VERSION
        or intent.policy.methodology != _EXACT_TARGET_POLICY_METHODOLOGY
        or intent.policy.version != _EXACT_TARGET_POLICY_VERSION
        or intent.policy_fingerprint != _FIXED_POLICY_FINGERPRINT
        or intent.decision_as_of != request.decision_as_of
        or request.decision_as_of.tzinfo is not UTC
        or intent.valid_from != request.decision_as_of
        or intent.expires_at != request.signal.expires_at
        or intent.decision_as_of.tzinfo is not UTC
        or intent.valid_from.tzinfo is not UTC
        or intent.expires_at.tzinfo is not UTC
        or intent.instrument != intent.source_signal.instrument
        or intent.target_position is not request.signal.target.position
        or intent.source_idempotency_key != _idempotency_key(request.signal)
        or intent.source_signal_fingerprint != _signal_fingerprint(request.signal)
        or intent.intent_fingerprint != _intent_fingerprint(intent)
    ):
        raise TradingApplicationCorrespondenceError(
            "OrderIntent does not correspond to the application request"
        )


def _require_exact_canonical_decimal_correspondence(
    actual: object,
    expected: object,
    field_name: str,
) -> None:
    if type(actual) is not Decimal or type(expected) is not Decimal:
        raise TradingApplicationCorrespondenceError(
            f"{field_name} must retain an exact canonical Decimal"
        )
    try:
        canonical_expected, expected_text = _canonical_decimal(
            expected,
            "target.units",
        )
        _, actual_text = _canonical_decimal(actual, "target.units")
    except TradingApplicationRequestError as exc:
        raise TradingApplicationCorrespondenceError(
            f"{field_name} must retain an exact canonical Decimal"
        ) from exc
    if (
        expected.as_tuple() != canonical_expected.as_tuple()
        or actual.as_tuple() != expected.as_tuple()
        or actual_text != expected_text
    ):
        raise TradingApplicationCorrespondenceError(
            f"{field_name} does not match canonical application units"
        )


__all__ = [
    "ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION",
    "ORDER_INTENT_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION",
    "TRADING_SIGNAL_APPLICATION_RESPONSE_SCHEMA_VERSION",
    "CreateOrderIntentApplicationResponse",
    "CreateTradingSignalApplicationResponse",
    "OrderIntentApplicationRequest",
    "TradingInstrumentApplicationInput",
    "TradingSignalApplicationInput",
    "TradingSignalApplicationRequest",
    "TradingSignalSourceApplicationInput",
    "TradingTargetPositionApplicationInput",
]
