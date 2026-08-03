"""Explicit reusable order-style choices without order specification semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.execution_planning._canonical import required_retained_attribute
from market_platform.execution_planning.errors import (
    ExecutionPlanningCorrespondenceError,
    ExecutionPlanningValidationError,
)

ORDER_STYLE_CHOICE_SCHEMA = "order_style_choice/v1"


class OrderStyle(StrEnum):
    """One explicit broker-neutral order-style label."""

    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True, slots=True)
class OrderStyleChoice:
    """One explicit caller-authored style choice, never an order specification."""

    style: OrderStyle
    schema_version: str = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.style) is not OrderStyle:
            raise ExecutionPlanningValidationError("style must be an OrderStyle")
        object.__setattr__(self, "schema_version", ORDER_STYLE_CHOICE_SCHEMA)
        object.__setattr__(
            self,
            "fingerprint",
            canonical_fingerprint(self._fingerprint_payload()),
        )
        self._validate()

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "style": self.style.value,
        }

    def _validate(self) -> None:
        retained = {
            name: required_retained_attribute(self, name, "order style choice")
            for name in ("style", "schema_version", "fingerprint")
        }
        style = retained["style"]
        if type(style) is not OrderStyle:
            raise ExecutionPlanningCorrespondenceError(
                "order style choice retains invalid style"
            )
        if retained["schema_version"] != ORDER_STYLE_CHOICE_SCHEMA:
            raise ExecutionPlanningCorrespondenceError(
                "order style choice schema_version is invalid"
            )
        expected = canonical_fingerprint(
            {
                "schema_version": retained["schema_version"],
                "style": style.value,
            }
        )
        if retained["fingerprint"] != expected:
            raise ExecutionPlanningCorrespondenceError(
                "order style choice fingerprint does not match content"
            )

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic caller-authored choice projection."""

        self._validate()
        return {
            "schema_version": self.schema_version,
            "style": self.style.value,
            "fingerprint": self.fingerprint,
        }


__all__ = [
    "ORDER_STYLE_CHOICE_SCHEMA",
    "OrderStyle",
    "OrderStyleChoice",
]
