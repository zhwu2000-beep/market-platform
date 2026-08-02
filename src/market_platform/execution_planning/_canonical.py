"""Private bounded canonical values for execution planning."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)

_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}", flags=re.ASCII)


def required_fingerprint(value: object, field_name: str) -> str:
    """Require an exact lowercase repository SHA-256 fingerprint."""

    if type(value) is not str:
        raise ExecutionPlanningValidationError(f"{field_name} must be a string")
    if _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ExecutionPlanningValidationError(
            f"{field_name} must be a lowercase sha256 fingerprint"
        )
    return value


def canonical_plan_time(value: object, field_name: str) -> datetime:
    """Require an exact aware datetime physically stored in canonical UTC."""

    if type(value) is not datetime:
        raise ExecutionPlanningValidationError(f"{field_name} must be a datetime")
    timestamp = value
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ExecutionPlanningValidationError(
            f"{field_name} must be timezone-aware"
        )
    canonical = timestamp.astimezone(UTC)
    if timestamp.tzinfo is not UTC or timestamp.isoformat() != canonical.isoformat():
        raise ExecutionPlanningValidationError(
            f"{field_name} must use canonical UTC"
        )
    return canonical


def timestamp_text(value: datetime) -> str:
    """Project one canonical UTC timestamp."""

    return canonical_plan_time(value, "timestamp").isoformat()


def required_retained_attribute(
    value: object,
    attribute_name: str,
    subject: str,
) -> object:
    """Retrieve one known retained slot and translate only missing state."""

    try:
        return object.__getattribute__(value, attribute_name)
    except AttributeError as error:
        raise ExecutionPlanningCorrespondenceError(
            f"{subject} is missing required retained state"
        ) from error


__all__: list[str] = []
