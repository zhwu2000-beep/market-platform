"""Private bounded canonicalization for instrument-domain models."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from re import Pattern

from market_platform.instruments.errors import InstrumentValidationError

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


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
        raise InstrumentValidationError(f"{field_name} must match {description}")
    return value


def require_visible_ascii(
    value: object,
    field_name: str,
    maximum_length: int,
) -> str:
    """Require nonempty whitespace-free visible ASCII within a fixed bound."""

    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string")
    observed = len(value)
    if observed > maximum_length:
        raise InstrumentValidationError(
            f"{field_name} exceeds maximum length "
            f"{maximum_length}; observed {observed}"
        )
    if not value:
        raise InstrumentValidationError(f"{field_name} must not be empty")
    if any(not 0x21 <= ord(character) <= 0x7E for character in value):
        raise InstrumentValidationError(
            f"{field_name} must contain visible ASCII without whitespace"
        )
    return value


def optional_fingerprint(value: object, field_name: str) -> str | None:
    """Validate an optional repository-format SHA-256 fingerprint."""

    if value is None:
        return None
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string or None")
    if _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise InstrumentValidationError(
            f"{field_name} must be a lowercase sha256 fingerprint"
        )
    return value


def canonical_timestamp(value: object, field_name: str) -> datetime:
    """Require a truly aware datetime and normalize it physically to UTC."""

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InstrumentValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def require_canonical_timestamp(value: object, field_name: str) -> datetime:
    """Require an already canonical UTC datetime representation."""

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    canonical = canonical_timestamp(value, field_name)
    if value.tzinfo is not UTC or value.isoformat() != canonical.isoformat():
        raise InstrumentValidationError(f"{field_name} must use canonical UTC")
    return canonical


def timestamp_text(value: datetime) -> str:
    """Project a canonical UTC datetime deterministically."""

    return require_canonical_timestamp(value, "timestamp").isoformat()


__all__ = [
    "canonical_timestamp",
    "optional_fingerprint",
    "require_canonical_timestamp",
    "require_pattern_text",
    "require_visible_ascii",
    "timestamp_text",
]
