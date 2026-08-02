"""Private bounded canonicalization for structural risk values."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import cast

from market_platform.risk.errors import RiskValidationError

_POLICY_ID_PATTERN = re.compile(r"[a-z][a-z0-9._-]{0,63}", flags=re.ASCII)
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


def policy_id(value: object) -> str:
    if type(value) is not str or _POLICY_ID_PATTERN.fullmatch(value) is None:
        raise RiskValidationError("policy_id must match [a-z][a-z0-9._-]{0,63}")
    return value


def visible_ascii(value: object, field_name: str, maximum: int) -> str:
    if type(value) is not str:
        raise RiskValidationError(f"{field_name} must be a string")
    if not 1 <= len(value) <= maximum:
        raise RiskValidationError(
            f"{field_name} length must be between 1 and {maximum}"
        )
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise RiskValidationError(f"{field_name} must contain visible ASCII only")
    return value


def optional_fingerprint(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return required_fingerprint(value, field_name)


def required_fingerprint(value: object, field_name: str) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise RiskValidationError(
            f"{field_name} must be sha256 followed by 64 lowercase hex digits"
        )
    return value


def canonical_timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not datetime:
        raise RiskValidationError(f"{field_name} must be an exact datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise RiskValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def require_canonical_timestamp(value: object, field_name: str) -> datetime:
    canonical = canonical_timestamp(value, field_name)
    retained = cast("datetime", value)
    if retained.tzinfo is not UTC or retained.isoformat() != canonical.isoformat():
        raise RiskValidationError(f"{field_name} must retain canonical UTC state")
    return canonical


def timestamp_text(value: datetime) -> str:
    return require_canonical_timestamp(value, "timestamp").isoformat()


def nonnegative_duration(value: object, field_name: str) -> timedelta:
    if type(value) is not timedelta:
        raise RiskValidationError(f"{field_name} must be an exact timedelta")
    if value < timedelta(0):
        raise RiskValidationError(f"{field_name} must be nonnegative")
    return value


def duration_microseconds_text(value: timedelta, field_name: str) -> str:
    duration = nonnegative_duration(value, field_name)
    total = (
        duration.days * 86_400_000_000
        + duration.seconds * 1_000_000
        + duration.microseconds
    )
    return str(total)
