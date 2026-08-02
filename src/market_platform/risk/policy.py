"""Immutable structural risk policy and quote requirements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum

from market_platform._fingerprint import canonical_fingerprint
from market_platform.risk._canonical import (
    duration_microseconds_text,
    nonnegative_duration,
    optional_fingerprint,
    policy_id,
    visible_ascii,
)
from market_platform.risk.errors import (
    RiskCorrespondenceError,
    RiskValidationError,
)

STRUCTURAL_RISK_POLICY_SCHEMA_VERSION = "structural_risk_policy/v1"


class QuoteEvidenceRequirement(StrEnum):
    """Required target-instrument quote fields."""

    ANY_PRICE = "any_price"
    LAST = "last"
    BID_AND_ASK = "bid_and_ask"


@dataclass(frozen=True, slots=True)
class StructuralRiskPolicy:
    """Exact passive thresholds for structural risk evaluation."""

    policy_id: str
    policy_version: str
    configuration_fingerprint: str | None
    maximum_cash_age: timedelta
    maximum_position_age: timedelta
    maximum_open_order_age: timedelta
    maximum_quote_age: timedelta
    maximum_state_skew: timedelta
    quote_requirement: QuoteEvidenceRequirement
    schema_version: str = field(
        init=False, default=STRUCTURAL_RISK_POLICY_SCHEMA_VERSION
    )
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", policy_id(self.policy_id))
        object.__setattr__(
            self,
            "policy_version",
            visible_ascii(self.policy_version, "policy_version", 64),
        )
        object.__setattr__(
            self,
            "configuration_fingerprint",
            optional_fingerprint(
                self.configuration_fingerprint, "configuration_fingerprint"
            ),
        )
        for name in _DURATION_FIELDS:
            object.__setattr__(
                self, name, nonnegative_duration(getattr(self, name), name)
            )
        if type(self.quote_requirement) is not QuoteEvidenceRequirement:
            raise RiskValidationError(
                "quote_requirement must be a QuoteEvidenceRequirement"
            )
        object.__setattr__(
            self, "fingerprint", canonical_fingerprint(self._fingerprint_payload())
        )

    def _fingerprint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "configuration_fingerprint": self.configuration_fingerprint,
            **{
                f"{name}_microseconds": duration_microseconds_text(
                    getattr(self, name), name
                )
                for name in _DURATION_FIELDS
            },
            "quote_requirement": self.quote_requirement.value,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the bounded deterministic policy projection."""

        return {**self._fingerprint_payload(), "fingerprint": self.fingerprint}


_DURATION_FIELDS = (
    "maximum_cash_age",
    "maximum_position_age",
    "maximum_open_order_age",
    "maximum_quote_age",
    "maximum_state_skew",
)


def require_policy_correspondence(value: object) -> StructuralRiskPolicy:
    if type(value) is not StructuralRiskPolicy:
        raise RiskCorrespondenceError("policy has invalid runtime type")
    policy = value
    try:
        reconstructed = StructuralRiskPolicy(
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            configuration_fingerprint=policy.configuration_fingerprint,
            maximum_cash_age=policy.maximum_cash_age,
            maximum_position_age=policy.maximum_position_age,
            maximum_open_order_age=policy.maximum_open_order_age,
            maximum_quote_age=policy.maximum_quote_age,
            maximum_state_skew=policy.maximum_state_skew,
            quote_requirement=policy.quote_requirement,
        )
    except (TypeError, ValueError) as error:
        raise RiskCorrespondenceError(
            "policy retains invalid canonical state"
        ) from error
    if (
        policy.schema_version != reconstructed.schema_version
        or policy.fingerprint != reconstructed.fingerprint
        or policy.to_dict() != reconstructed.to_dict()
        or any(
            getattr(policy, name) != getattr(reconstructed, name)
            for name in _DURATION_FIELDS
        )
    ):
        raise RiskCorrespondenceError("policy does not match public reconstruction")
    return policy


__all__ = [
    "STRUCTURAL_RISK_POLICY_SCHEMA_VERSION",
    "QuoteEvidenceRequirement",
    "StructuralRiskPolicy",
]
