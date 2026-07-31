"""Private bounded canonicalization for trading-state domain values."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from re import Pattern
from typing import cast

from market_platform.trading_state.errors import TradingStateValidationError

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)

DECIMAL_TEXT_LIMIT = 256
DECIMAL_DIGIT_LIMIT = 128
DECIMAL_FRACTIONAL_DIGIT_LIMIT = 64


def require_pattern_text(
    value: object,
    field_name: str,
    pattern: Pattern[str],
    description: str,
) -> str:
    """Require an exact string matching one bounded ASCII grammar."""

    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    if pattern.fullmatch(value) is None:
        raise TradingStateValidationError(f"{field_name} must match {description}")
    return value


def require_visible_ascii(
    value: object,
    field_name: str,
    maximum_length: int,
) -> str:
    """Require bounded nonempty visible ASCII without whitespace."""

    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    observed = len(value)
    if observed > maximum_length:
        raise TradingStateValidationError(
            f"{field_name} exceeds maximum {maximum_length}; observed {observed}"
        )
    if not value:
        raise TradingStateValidationError(f"{field_name} must not be empty")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise TradingStateValidationError(
            f"{field_name} must contain visible ASCII without whitespace"
        )
    return value


def optional_fingerprint(value: object, field_name: str) -> str | None:
    """Require an optional lowercase repository SHA-256 fingerprint."""

    if value is None:
        return None
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string or None")
    if _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise TradingStateValidationError(
            f"{field_name} must be a lowercase sha256 fingerprint"
        )
    return value


def canonical_timestamp(value: object, field_name: str) -> datetime:
    """Require an exact aware datetime and physically normalize it to UTC."""

    if type(value) is not datetime:
        raise TypeError(f"{field_name} must be a datetime")
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise TradingStateValidationError(f"{field_name} must be timezone-aware")
    return timestamp.astimezone(UTC)


def require_canonical_timestamp(value: object, field_name: str) -> datetime:
    """Require an already canonical physical UTC datetime."""

    canonical = canonical_timestamp(value, field_name)
    timestamp = cast(datetime, value)
    if timestamp.tzinfo is not UTC or timestamp.isoformat() != canonical.isoformat():
        raise TradingStateValidationError(f"{field_name} must use canonical UTC")
    return canonical


def timestamp_text(value: datetime) -> str:
    """Project one canonical UTC timestamp."""

    return require_canonical_timestamp(value, "timestamp").isoformat()


def canonical_decimal(
    value: object,
    field_name: str,
    *,
    allow_negative: bool,
    allow_zero: bool,
) -> tuple[Decimal, str]:
    """Canonicalize one exact Decimal after bounded pre-allocation checks."""

    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise TradingStateValidationError(f"{field_name} must be finite")
    if value.is_zero() and value.is_signed():
        raise TradingStateValidationError(f"{field_name} must not be negative zero")
    if value.is_zero():
        if not allow_zero:
            if not allow_negative:
                raise TradingStateValidationError(
                    f"{field_name} must be strictly positive"
                )
            raise TradingStateValidationError(f"{field_name} must be nonzero")
        return Decimal("0"), "0"
    if value.is_signed() and not allow_negative:
        raise TradingStateValidationError(f"{field_name} must be strictly positive")

    digit_count, fractional_digit_count, text_length = _project_canonical_decimal_size(
        value
    )
    if digit_count > DECIMAL_DIGIT_LIMIT:
        raise TradingStateValidationError(
            f"{field_name} exceeds digit maximum {DECIMAL_DIGIT_LIMIT}; "
            f"observed {digit_count}"
        )
    if fractional_digit_count > DECIMAL_FRACTIONAL_DIGIT_LIMIT:
        raise TradingStateValidationError(
            f"{field_name} exceeds fractional digit maximum "
            f"{DECIMAL_FRACTIONAL_DIGIT_LIMIT}; "
            f"observed {fractional_digit_count}"
        )
    if text_length > DECIMAL_TEXT_LIMIT:
        raise TradingStateValidationError(
            f"{field_name} exceeds text maximum {DECIMAL_TEXT_LIMIT}; "
            f"observed {text_length}"
        )

    text = _fixed_point_decimal_text(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return Decimal(text), text


def require_canonical_decimal(
    value: object,
    field_name: str,
    *,
    allow_negative: bool,
    allow_zero: bool,
) -> tuple[Decimal, str]:
    """Require an exact Decimal already in canonical tuple state."""

    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be a Decimal")
    canonical, text = canonical_decimal(
        value,
        field_name,
        allow_negative=allow_negative,
        allow_zero=allow_zero,
    )
    if value.as_tuple() != canonical.as_tuple():
        raise TradingStateValidationError(
            f"{field_name} must retain canonical Decimal state"
        )
    return canonical, text


def require_exact_container(
    value: object,
    field_name: str,
    maximum_count: int,
    *,
    minimum_count: int = 0,
) -> tuple[object, ...]:
    """Bound and copy an exact built-in list or tuple."""

    if type(value) not in (list, tuple):
        raise TypeError(f"{field_name} must be an exact built-in list or tuple")
    container = (
        cast("list[object]", value)
        if type(value) is list
        else cast("tuple[object, ...]", value)
    )
    observed = len(container)
    if observed < minimum_count:
        raise TradingStateValidationError(
            f"{field_name} requires at least {minimum_count}; observed {observed}"
        )
    if observed > maximum_count:
        raise TradingStateValidationError(
            f"{field_name} exceeds maximum {maximum_count}; observed {observed}"
        )
    return container if type(container) is tuple else tuple(container)


def _project_canonical_decimal_size(
    value: Decimal,
) -> tuple[int, int, int]:
    decimal_tuple = value.as_tuple()
    digits = decimal_tuple.digits
    exponent = decimal_tuple.exponent
    if not isinstance(exponent, int):
        raise TradingStateValidationError("Decimal value must be finite")

    trailing_zero_count = 0
    for digit in reversed(digits):
        if digit != 0:
            break
        trailing_zero_count += 1
    canonical_digit_count = len(digits) - trailing_zero_count
    canonical_exponent = exponent + trailing_zero_count
    if canonical_exponent >= 0:
        output_digit_count = canonical_digit_count + canonical_exponent
        text_length = output_digit_count
    else:
        fractional_digit_count = -canonical_exponent
        decimal_position = canonical_digit_count + canonical_exponent
        integer_digit_count = max(decimal_position, 1)
        output_digit_count = integer_digit_count + fractional_digit_count
        text_length = output_digit_count + 1
        if value.is_signed():
            text_length += 1
        return output_digit_count, fractional_digit_count, text_length

    if value.is_signed():
        text_length += 1
    return output_digit_count, 0, text_length


def _fixed_point_decimal_text(value: Decimal) -> str:
    return format(value, "f")


__all__: list[str] = []
