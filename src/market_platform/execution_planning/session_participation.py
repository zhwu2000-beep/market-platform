"""Explicit caller-authored session-participation choices."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import required_retained_attribute
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)

SESSION_PARTICIPATION_CHOICE_SCHEMA = "session_participation_choice/v1"


class SessionParticipation(StrEnum):
    """Requested category of session participation."""

    REGULAR_ONLY = "regular_only"
    REGULAR_AND_EXTENDED = "regular_and_extended"


@dataclass(frozen=True, slots=True)
class SessionParticipationChoice:
    """Canonical caller-authored session-participation choice."""

    session_participation: SessionParticipation
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.session_participation) is not SessionParticipation:
            raise ExecutionPlanningValidationError(
                "session_participation must be an exact SessionParticipation value"
            )
        object.__setattr__(self, "schema_version", SESSION_PARTICIPATION_CHOICE_SCHEMA)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )
        self._validate()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": SESSION_PARTICIPATION_CHOICE_SCHEMA,
            "session_participation": self.session_participation.value,
        }

    def _validate(self) -> tuple[SessionParticipation, str, str]:
        session_participation = required_retained_attribute(
            self, "session_participation", "session-participation choice"
        )
        if type(session_participation) is not SessionParticipation:
            raise ExecutionPlanningCorrespondenceError(
                "retained session_participation is malformed"
            )

        schema_version = required_retained_attribute(
            self, "schema_version", "session-participation choice"
        )
        if (
            type(schema_version) is not str
            or schema_version != SESSION_PARTICIPATION_CHOICE_SCHEMA
        ):
            raise ExecutionPlanningCorrespondenceError(
                "retained schema_version is malformed"
            )

        fingerprint = required_retained_attribute(
            self, "fingerprint", "session-participation choice"
        )
        expected_fingerprint = canonical_fingerprint(
            self._fingerprint_payload()
        )
        if type(fingerprint) is not str or fingerprint != expected_fingerprint:
            raise ExecutionPlanningCorrespondenceError(
                "retained fingerprint is malformed"
            )

        return session_participation, schema_version, fingerprint

    def to_dict(self) -> dict[str, object]:
        """Return the validated deterministic JSON-safe projection."""

        session_participation, schema_version, fingerprint = self._validate()
        return {
            "schema_version": schema_version,
            "session_participation": session_participation.value,
            "fingerprint": fingerprint,
        }


__all__ = [
    "SESSION_PARTICIPATION_CHOICE_SCHEMA",
    "SessionParticipation",
    "SessionParticipationChoice",
]
