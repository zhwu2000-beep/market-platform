"""Strict dictionary codecs for trading-signal application requests."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation

from market_platform.application.errors import (
    TradingApplicationRequestError,
    TradingApplicationResourceLimitError,
    UnsupportedTradingApplicationSchemaError,
)
from market_platform.application.trading_signal import (
    _DECIMAL_DIGIT_LIMIT,
    _DECIMAL_FRACTIONAL_DIGIT_LIMIT,
    _DECIMAL_TEXT_LIMIT,
    _TIMESTAMP_TEXT_LIMIT,
    ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION,
    TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION,
    OrderIntentApplicationRequest,
    TradingInstrumentApplicationInput,
    TradingSignalApplicationInput,
    TradingSignalApplicationRequest,
    TradingSignalSourceApplicationInput,
    TradingTargetPositionApplicationInput,
)
from market_platform.trading import TradingTargetPosition

_DECIMAL_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?"
    r"(?P<timezone>Z|(?P<offset_sign>[+-])"
    r"(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2}))$"
)


def decode_trading_signal_application_request(
    payload: Mapping[str, object],
) -> TradingSignalApplicationRequest:
    """Strictly decode one create-TradingSignal application request."""

    root = _object(payload, "request", {"schema_version", "signal"})
    schema = _string(root["schema_version"], "request.schema_version")
    if schema != TRADING_SIGNAL_APPLICATION_REQUEST_SCHEMA_VERSION:
        raise UnsupportedTradingApplicationSchemaError(
            "unsupported trading signal application schema"
        )
    return TradingSignalApplicationRequest(
        signal=_signal(root["signal"], "request.signal")
    )


def decode_order_intent_application_request(
    payload: Mapping[str, object],
) -> OrderIntentApplicationRequest:
    """Strictly decode one create-OrderIntent application request."""

    root = _object(
        payload,
        "request",
        {"schema_version", "signal", "decision_as_of"},
    )
    schema = _string(root["schema_version"], "request.schema_version")
    if schema != ORDER_INTENT_APPLICATION_REQUEST_SCHEMA_VERSION:
        raise UnsupportedTradingApplicationSchemaError(
            "unsupported order intent application schema"
        )
    return OrderIntentApplicationRequest(
        signal=_signal(root["signal"], "request.signal"),
        decision_as_of=_timestamp(
            root["decision_as_of"],
            "request.decision_as_of",
        ),
    )


def _signal(payload: object, path: str) -> TradingSignalApplicationInput:
    value = _object(
        payload,
        path,
        {
            "source",
            "source_event_id",
            "instrument",
            "timeframe",
            "target",
            "generated_at",
            "valid_from",
            "expires_at",
        },
    )
    source = _object(
        value["source"],
        f"{path}.source",
        {"source_id", "source_version", "configuration_fingerprint"},
    )
    instrument = _object(
        value["instrument"],
        f"{path}.instrument",
        {"symbol", "venue"},
    )
    target = _object(
        value["target"],
        f"{path}.target",
        {"position", "units"},
    )
    configuration_fingerprint = source["configuration_fingerprint"]
    if configuration_fingerprint is not None:
        configuration_fingerprint = _string(
            configuration_fingerprint,
            f"{path}.source.configuration_fingerprint",
        )
    timeframe = value["timeframe"]
    if timeframe is not None:
        timeframe = _string(timeframe, f"{path}.timeframe")
    position_text = _string(target["position"], f"{path}.target.position")
    try:
        position = TradingTargetPosition(position_text)
    except ValueError as exc:
        raise TradingApplicationRequestError(
            f"{path}.target.position must be long, flat, or short"
        ) from exc
    return TradingSignalApplicationInput(
        source=TradingSignalSourceApplicationInput(
            source_id=_string(source["source_id"], f"{path}.source.source_id"),
            source_version=_string(
                source["source_version"],
                f"{path}.source.source_version",
            ),
            configuration_fingerprint=configuration_fingerprint,
        ),
        source_event_id=_string(
            value["source_event_id"],
            f"{path}.source_event_id",
        ),
        instrument=TradingInstrumentApplicationInput(
            symbol=_string(instrument["symbol"], f"{path}.instrument.symbol"),
            venue=_string(instrument["venue"], f"{path}.instrument.venue"),
        ),
        timeframe=timeframe,
        target=TradingTargetPositionApplicationInput(
            position=position,
            units=_decimal(target["units"], f"{path}.target.units"),
        ),
        generated_at=_timestamp(
            value["generated_at"],
            f"{path}.generated_at",
        ),
        valid_from=_timestamp(value["valid_from"], f"{path}.valid_from"),
        expires_at=_timestamp(value["expires_at"], f"{path}.expires_at"),
    )


def _object(
    payload: object,
    path: str,
    expected_keys: set[str],
) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise TradingApplicationRequestError(f"{path} must be an object")
    actual_keys = set(payload)
    if any(not isinstance(key, str) for key in actual_keys):
        raise TradingApplicationRequestError(f"{path} keys must be strings")
    missing = expected_keys - actual_keys
    unknown = actual_keys - expected_keys
    if missing:
        raise TradingApplicationRequestError(
            f"{path} missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise TradingApplicationRequestError(
            f"{path} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    return payload


def _string(payload: object, path: str) -> str:
    if not isinstance(payload, str):
        raise TradingApplicationRequestError(f"{path} must be a string")
    return payload


def _decimal(payload: object, path: str) -> Decimal:
    text = _string(payload, path)
    if len(text) > _DECIMAL_TEXT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{path} exceeds limit {_DECIMAL_TEXT_LIMIT}; observed length {len(text)}"
        )
    if _DECIMAL_PATTERN.fullmatch(text) is None:
        raise TradingApplicationRequestError(
            f"{path} must be a nonnegative fixed-point decimal string"
        )
    integer, separator, fraction = text.partition(".")
    digit_count = len(integer) + len(fraction)
    if digit_count > _DECIMAL_DIGIT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{path} exceeds digit limit {_DECIMAL_DIGIT_LIMIT}; "
            f"observed digits {digit_count}"
        )
    if separator and len(fraction) > _DECIMAL_FRACTIONAL_DIGIT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{path} exceeds fractional digit limit "
            f"{_DECIMAL_FRACTIONAL_DIGIT_LIMIT}; "
            f"observed fractional digits {len(fraction)}"
        )
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise TradingApplicationRequestError(
            f"{path} must be a valid fixed-point decimal"
        ) from exc


def _timestamp(payload: object, path: str) -> datetime:
    text = _string(payload, path)
    if len(text) > _TIMESTAMP_TEXT_LIMIT:
        raise TradingApplicationResourceLimitError(
            f"{path} exceeds limit {_TIMESTAMP_TEXT_LIMIT}; observed length {len(text)}"
        )
    match = _TIMESTAMP_PATTERN.fullmatch(text)
    if match is None:
        raise TradingApplicationRequestError(
            f"{path} must be a strict timezone-aware RFC-3339 timestamp"
        )
    if match.group("timezone") != "Z":
        offset_sign = match.group("offset_sign")
        offset_hour = int(match.group("offset_hour"))
        offset_minute = int(match.group("offset_minute"))
        if (
            offset_hour > 23
            or offset_minute > 59
            or (offset_sign == "-" and offset_hour == 0 and offset_minute == 0)
        ):
            raise TradingApplicationRequestError(
                f"{path} must declare a valid known RFC-3339 offset"
            )
    normalized_text = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized_text)
    except ValueError as exc:
        raise TradingApplicationRequestError(
            f"{path} must be a valid timezone-aware RFC-3339 timestamp"
        ) from exc


__all__ = [
    "decode_order_intent_application_request",
    "decode_trading_signal_application_request",
]
