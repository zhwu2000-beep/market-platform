"""Private canonical values shared by trading-domain models."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_decimal(value: object, field_name: str) -> tuple[Decimal, str]:
    """Validate and return an exact nonnegative Decimal and fixed-point text."""

    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value.is_zero() and value.is_signed():
        raise ValueError(f"{field_name} must not be negative zero")
    if value.is_zero():
        return Decimal("0"), "0"
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if not text:
        text = "0"
    return Decimal(text), text


def canonical_timestamp(value: object, field_name: str) -> datetime:
    """Require an aware datetime and normalize it to UTC."""

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def timestamp_text(value: datetime) -> str:
    """Return the repository-standard deterministic UTC timestamp text."""

    return value.astimezone(UTC).isoformat()


def required_text(
    value: object,
    field_name: str,
    *,
    uppercase: bool = False,
    reject_surrounding_whitespace: bool = False,
) -> str:
    """Validate a required string under an explicit normalization policy."""

    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    if reject_surrounding_whitespace and text != value:
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return text.upper() if uppercase else text


def optional_fingerprint(value: object, field_name: str) -> str | None:
    """Validate an optional repository SHA-256 fingerprint."""

    if value is None:
        return None
    if not isinstance(value, str) or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a sha256 fingerprint or None")
    return value


__all__: list[str] = []
