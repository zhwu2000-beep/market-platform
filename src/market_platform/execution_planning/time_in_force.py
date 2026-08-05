"""Explicit caller-authored time-in-force choices."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import cast

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import required_retained_attribute
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)

TIME_IN_FORCE_CHOICE_SCHEMA = "time_in_force_choice/v1"


class TimeInForce(StrEnum):
    """One explicit broker-neutral requested time-in-force label."""

    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


@dataclass(frozen=True, slots=True)
class TimeInForceChoice:
    """One timeless caller-authored time-in-force choice."""

    time_in_force: TimeInForce
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.time_in_force) is not TimeInForce:
            raise ExecutionPlanningValidationError(
                "time_in_force must be a TimeInForce"
            )
        object.__setattr__(self, "schema_version", TIME_IN_FORCE_CHOICE_SCHEMA)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )
        self._validate()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "time_in_force": self.time_in_force.value,
        }

    def _validate(self) -> dict[str, object]:
        retained = {
            name: required_retained_attribute(self, name, "time-in-force choice")
            for name in ("time_in_force", "schema_version", "fingerprint")
        }
        time_in_force = retained["time_in_force"]
        if type(time_in_force) is not TimeInForce:
            raise ExecutionPlanningCorrespondenceError(
                "time-in-force choice retains invalid time_in_force"
            )
        schema_version = retained["schema_version"]
        if (
            type(schema_version) is not str
            or schema_version != TIME_IN_FORCE_CHOICE_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "time-in-force choice schema_version is invalid"
            )
        expected = canonical_fingerprint(
            {
                "schema_version": TIME_IN_FORCE_CHOICE_SCHEMA,
                "time_in_force": time_in_force.value,
            }
        )
        fingerprint = retained["fingerprint"]
        if type(fingerprint) is not str or fingerprint != expected:
            raise ExecutionPlanningCorrespondenceError(
                "time-in-force choice fingerprint does not match content"
            )
        return retained

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic caller-authored choice projection."""

        retained = self._validate()
        return {
            "schema_version": retained["schema_version"],
            "time_in_force": cast(TimeInForce, retained["time_in_force"]).value,
            "fingerprint": retained["fingerprint"],
        }


__all__ = [
    "TIME_IN_FORCE_CHOICE_SCHEMA",
    "TimeInForce",
    "TimeInForceChoice",
]
